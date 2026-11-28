"""Interactive Bot-vs-Bot Battle Sim Visualizer screen for the pogolab TUI."""

from __future__ import annotations

import random

from PIL import Image as PILImage
from rich.markup import escape
from rich.style import Style
from rich.text import Text
from textual.app import ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical, VerticalScroll
from textual.reactive import reactive
from textual.screen import Screen
from textual.timer import Timer
from textual.widget import Widget
from textual.widgets import Footer, Static
from textual_image.widget import Image as TerminalImage

from pogolab.battle import GreedyBot, Phase, Winner
from pogolab.data import FastMove, GameData
from pogolab.tui.battle_replay import (
    BASE_TURN_SECONDS,
    PLAYBACK_SPEEDS,
    BattleReplay,
    BattleSnapshot,
    FastMoveProgress,
    darken_hex,
    format_shields,
    format_stat_stages,
    format_type_badges,
    generate_random_gl_teams,
    record_battle,
    render_charged_energy_bar,
    render_compact_hp_bar,
    render_hp_bar,
)
from pogolab.tui.helpers import TYPE_COLORS
from pogolab.tui.sprites import SpriteData, load_sprites, sprite_to_pil

_PHASE_LABELS: dict[Phase, tuple[str, str]] = {
    Phase.TURN: ("TURN", "#3B82F6"),
    Phase.SHIELD_DECISION: ("SHIELD", "#F59E0B"),
    Phase.FORCED_SWITCH: ("SWITCH", "#A855F7"),
    Phase.POST_CHARGED_SWITCH: ("POST-CM", "#EC4899"),
    Phase.FINISHED: ("FINISHED", "#22C55E"),
}


class FastMoveMeter(Widget):
    """Fast move box whose background fills left-to-right across the move's turn duration."""

    def __init__(self, *, id: str | None = None, classes: str | None = None) -> None:
        super().__init__(id=id, classes=classes)
        self._move: FastMove | None = None
        self._progress: FastMoveProgress = FastMoveProgress()

    @property
    def progress(self) -> FastMoveProgress:
        return self._progress

    def set_state(self, move: FastMove | None, progress: FastMoveProgress) -> None:
        self._move = move
        self._progress = progress
        self.set_class(progress.is_active, "-active-move")
        self.set_class(progress.is_active and not progress.landed, "-charging-move")
        self.set_class(progress.landed, "-impact-move")
        self.refresh()

    def _fit_line(self, text: str, width: int) -> str:
        inner = max(1, width - 2)
        if len(text) > inner:
            clipped = text[: max(1, inner - 1)] + "…"
        else:
            clipped = text.ljust(inner)
        return f" {clipped} "

    def _paint_line(
        self,
        text: str,
        *,
        width: int,
        fill_cols: int,
        fill_bg: str | None,
        unfilled_fg: str,
        filled_fg: str,
        bold: bool = False,
        dim: bool = False,
    ) -> Text:
        padded = self._fit_line(text, width)
        result = Text()
        if fill_bg is None or fill_cols <= 0:
            result.append(padded, style=Style(color=unfilled_fg, bold=bold, dim=dim))
            return result

        split = min(len(padded), fill_cols)
        if split > 0:
            result.append(
                padded[:split],
                style=Style(color=filled_fg, bgcolor=fill_bg, bold=bold),
            )
        if split < len(padded):
            result.append(
                padded[split:],
                style=Style(color=unfilled_fg, bold=bold, dim=dim),
            )
        return result

    def render(self) -> Text:
        width = max(18, self.content_size.width)
        move = self._move
        progress = self._progress

        if move is None:
            return Text(" FAST MOVE\n —", style=Style(dim=True))

        type_color = TYPE_COLORS.get(move.type, "#888888")
        if progress.landed:
            fill_cols = width
            fill_bg: str | None = darken_hex(type_color, 0.58)
            step_badge = f"{progress.elapsed}/{progress.total}"
        elif progress.is_active:
            fill_cols = max(1, round(progress.ratio * width))
            fill_bg = darken_hex(type_color, 0.42)
            step_badge = f"{progress.elapsed}/{progress.total}"
        else:
            fill_cols = 0
            fill_bg = None
            step_badge = ""

        inner = max(1, width - 2)
        left_header = "FAST MOVE"
        if step_badge:
            gap = max(1, inner - len(left_header) - len(step_badge))
            header_text = f"{left_header}{' ' * gap}{step_badge}"
        else:
            header_text = left_header

        stats_text = f"{move.turns}t • +{move.energy_gain}e • {move.power}p"

        line0 = self._paint_line(
            header_text,
            width=width,
            fill_cols=fill_cols,
            fill_bg=fill_bg,
            unfilled_fg="#9CA3AF",
            filled_fg="#F8FAFC",
            bold=progress.landed,
            dim=not progress.is_active,
        )
        line1 = self._paint_line(
            move.name,
            width=width,
            fill_cols=fill_cols,
            fill_bg=fill_bg,
            unfilled_fg=type_color,
            filled_fg="#FFFFFF",
            bold=True,
        )
        line2 = self._paint_line(
            stats_text,
            width=width,
            fill_cols=fill_cols,
            fill_bg=fill_bg,
            unfilled_fg="#9CA3AF",
            filled_fg="#E2E8F0",
            dim=not progress.is_active,
        )

        combined = Text()
        combined.append_text(line0)
        combined.append("\n")
        combined.append_text(line1)
        combined.append("\n")
        combined.append_text(line2)
        return combined


class BattleScreen(Screen[None]):
    """Bot-vs-Bot Great League Battle Sim Visualizer with deterministic replay scrubbing."""

    BINDINGS = [
        Binding("p", "toggle_play", "Play/Pause", priority=True),
        Binding("left", "prev_step", "Prev", priority=True),
        Binding("right", "next_step", "Next", priority=True),
        Binding("up", "speed_up", "Faster", priority=True),
        Binding("down", "speed_down", "Slower", priority=True),
        Binding("tab", "toggle_log", "Log", priority=True),
        Binding("r", "roll_matchup", "New Matchup", priority=True),
        Binding("escape", "go_home", "Home", priority=True),
    ]

    step_index: reactive[int] = reactive(0)
    is_playing: reactive[bool] = reactive(False)
    speed_index: reactive[int] = reactive(2)  # 1.0x
    show_log: reactive[bool] = reactive(False)

    def __init__(
        self,
        game_data: GameData,
        *,
        replay: BattleReplay | None = None,
        seed: int | None = None,
    ) -> None:
        super().__init__()
        self.game_data = game_data
        self._sprites: dict[str, SpriteData] = load_sprites()
        self._pil_cache: dict[tuple[str, bool, bool, int], PILImage.Image] = {}
        self._widget_sprite_keys: dict[str, tuple[str, bool, bool, int] | None] = {}
        self._playback_timer: Timer | None = None
        self._rng = random.Random(seed)
        self.replay: BattleReplay = replay if replay is not None else self._build_random_replay()

    @property
    def playback_speed(self) -> float:
        return PLAYBACK_SPEEDS[self.speed_index]

    @property
    def current_snapshot(self) -> BattleSnapshot:
        return self.replay.snapshots[self.step_index]

    def _build_random_replay(self) -> BattleReplay:
        team0, team1 = generate_random_gl_teams(self.game_data, rng=self._rng)
        battle_seed = self._rng.randint(1, 2**31 - 1)
        return record_battle(
            self.game_data,
            team0,
            team1,
            GreedyBot(),
            GreedyBot(),
            seed=battle_seed,
        )

    def _get_sprite_pil(
        self,
        species_id: str,
        *,
        flip_x: bool,
        fainted: bool,
        scale: int,
    ) -> PILImage.Image | None:
        key = (species_id, flip_x, fainted, scale)
        cached = self._pil_cache.get(key)
        if cached is not None:
            return cached
        sprite = self._sprites.get(species_id)
        if sprite is None:
            return None
        rendered = sprite_to_pil(
            sprite,
            flip_x=flip_x,
            fainted=fainted,
            scale=scale,
            square_pad=True,
        )
        self._pil_cache[key] = rendered
        return rendered

    def _set_sprite(
        self,
        widget_id: str,
        species_id: str | None,
        *,
        flip_x: bool,
        fainted: bool,
        scale: int,
    ) -> None:
        key = (species_id, flip_x, fainted, scale) if species_id is not None else None
        if self._widget_sprite_keys.get(widget_id) == key:
            return
        self._widget_sprite_keys[widget_id] = key
        widget = self.query_one(f"#{widget_id}", TerminalImage)
        if species_id is None:
            widget.image = None
            return
        widget.image = self._get_sprite_pil(
            species_id,
            flip_x=flip_x,
            fainted=fainted,
            scale=scale,
        )

    def _compose_move_column(self, player: int) -> ComposeResult:
        with Vertical(id=f"p{player}-moves", classes="moves-column"):
            yield FastMoveMeter(id=f"p{player}-fast-move", classes="move-box fast-move-box")
            yield Static(id=f"p{player}-cm-0", classes="move-box charged-move-box")
            yield Static(id=f"p{player}-cm-1", classes="move-box charged-move-box")

    def _compose_pokemon_side(self, player: int) -> ComposeResult:
        with Vertical(id=f"p{player}-side", classes="pokemon-side"):
            with Vertical(id=f"p{player}-active-card", classes="active-card"):
                yield Static(id=f"p{player}-active-header", classes="active-header")
                yield Static(id=f"p{player}-active-hp", classes="active-hp")
                yield Static(id=f"p{player}-active-meta", classes="active-meta")
                with Center(classes="active-sprite-wrap"):
                    yield TerminalImage(
                        id=f"p{player}-active-sprite",
                        classes="active-sprite",
                    )

            with Horizontal(id=f"p{player}-bench", classes="bench-row"):
                for slot in (0, 1):
                    with Vertical(id=f"p{player}-bench-{slot}", classes="bench-slot"):
                        with Center(classes="bench-sprite-wrap"):
                            yield TerminalImage(
                                id=f"p{player}-bench-sprite-{slot}",
                                classes="bench-sprite",
                            )
                        yield Static(id=f"p{player}-bench-hp-{slot}", classes="bench-hp")
                yield Static(id=f"p{player}-switch-timer", classes="switch-timer")

    def compose(self) -> ComposeResult:
        with Horizontal(id="battle-header"):
            yield Static(id="battle-clock")
            yield Static(id="battle-status")

        with Horizontal(id="battle-arena"):
            # Left = Player 0 (moves on far left, active+bench facing right)
            with Horizontal(id="p0-panel", classes="player-panel"):
                yield from self._compose_move_column(0)
                yield from self._compose_pokemon_side(0)

            # Right = Player 1 (mirrored: active+bench facing left, moves on far right)
            with Horizontal(id="p1-panel", classes="player-panel"):
                yield from self._compose_pokemon_side(1)
                yield from self._compose_move_column(1)

        with Vertical(id="battle-log-panel"):
            yield Static(
                "[bold]Battle Turn Log[/bold]  [dim](Tab to hide)[/dim]",
                id="battle-log-title",
            )
            with VerticalScroll(id="battle-log-scroll"):
                yield Static("", id="battle-log-content")

        yield Footer()

    def on_mount(self) -> None:
        self._render_snapshot()

    def on_unmount(self) -> None:
        self._stop_timer()

    def _stop_timer(self) -> None:
        if self._playback_timer is not None:
            self._playback_timer.stop()
            self._playback_timer = None

    def _sync_timer(self) -> None:
        self._stop_timer()
        if self.is_playing and self.is_mounted:
            interval = BASE_TURN_SECONDS / self.playback_speed
            self._playback_timer = self.set_interval(interval, self._advance_playback)

    def _advance_playback(self) -> None:
        last_idx = len(self.replay.snapshots) - 1
        if self.step_index < last_idx:
            self.step_index += 1
        else:
            self.is_playing = False

    def watch_step_index(self) -> None:
        if self.is_mounted:
            self._render_snapshot()

    def watch_is_playing(self) -> None:
        self._sync_timer()
        if self.is_mounted:
            self._render_header()

    def watch_speed_index(self) -> None:
        self._sync_timer()
        if self.is_mounted:
            self._render_header()

    def watch_show_log(self, show_log: bool) -> None:
        if not self.is_mounted:
            return
        panel = self.query_one("#battle-log-panel", Vertical)
        panel.set_class(show_log, "-visible")
        if show_log:
            self._render_log()

    def action_toggle_play(self) -> None:
        if not self.is_playing and self.step_index >= len(self.replay.snapshots) - 1:
            self.step_index = 0
        self.is_playing = not self.is_playing

    def action_prev_step(self) -> None:
        self.is_playing = False
        if self.step_index > 0:
            self.step_index -= 1

    def action_next_step(self) -> None:
        self.is_playing = False
        if self.step_index < len(self.replay.snapshots) - 1:
            self.step_index += 1

    def action_speed_up(self) -> None:
        if self.speed_index < len(PLAYBACK_SPEEDS) - 1:
            self.speed_index += 1

    def action_speed_down(self) -> None:
        if self.speed_index > 0:
            self.speed_index -= 1

    def action_toggle_log(self) -> None:
        self.show_log = not self.show_log

    def action_roll_matchup(self) -> None:
        self.is_playing = False
        self.replay = self._build_random_replay()
        self._widget_sprite_keys.clear()
        if self.step_index == 0:
            self._render_snapshot()
        else:
            self.step_index = 0

    def action_go_home(self) -> None:
        self.is_playing = False
        self.app.pop_screen()

    def _render_header(self) -> None:
        snap = self.current_snapshot
        seconds = snap.turn * BASE_TURN_SECONDS
        phase_text, phase_color = _PHASE_LABELS.get(snap.phase, (str(snap.phase), "#9CA3AF"))
        total_steps = len(self.replay.snapshots) - 1

        clock = self.query_one("#battle-clock", Static)
        clock.update(
            f"[bold]Turn {snap.turn}[/bold][dim]/{self.replay.max_turns}[/dim] "
            f"[dim]({seconds:.1f}s)[/dim]   "
            f"[bold black on {phase_color}] {phase_text} [/]   "
            f"[dim]Step {snap.step_index}/{total_steps}[/dim]"
        )

        speed_str = f"{self.playback_speed:g}x"
        play_badge = (
            f"[bold #22C55E]▶ Playing {speed_str}[/]"
            if self.is_playing
            else f"[bold #EAB308]⏸ Paused {speed_str}[/]"
        )
        winner_text = ""
        if snap.winner == Winner.PLAYER_0:
            winner_text = "   [bold #38BDF8]★ Player 1 Wins![/]"
        elif snap.winner == Winner.PLAYER_1:
            winner_text = "   [bold #F472B6]★ Player 2 Wins![/]"
        elif snap.winner == Winner.TIE:
            winner_text = "   [bold #FACC15]★ Tie![/]"

        status = self.query_one("#battle-status", Static)
        status.update(f"{play_badge}{winner_text}   [dim]Greedy vs Greedy[/dim]")

    def _render_player(self, player: int, snap: BattleSnapshot) -> None:
        team_meta = self.replay.teams[player]
        team_snap = snap.teams[player]
        active_idx = team_snap.active_idx
        active_mon = team_meta[active_idx]
        active_state = team_snap.active
        flip_x = player == 0

        # Active Pokémon header, HP, shields, stat stages
        p_tag = "[bold #38BDF8]P1[/]" if player == 0 else "[bold #F472B6]P2[/]"
        header = self.query_one(f"#p{player}-active-header", Static)
        header.update(
            f"{p_tag}  [bold]{escape(active_mon.species.name)}[/bold]  "
            f"[dim]{active_mon.cp} CP[/dim]  {format_type_badges(active_mon.species.types)}"
        )

        hp_widget = self.query_one(f"#p{player}-active-hp", Static)
        hp_widget.update(render_hp_bar(active_state.hp, active_state.max_hp))

        meta_widget = self.query_one(f"#p{player}-active-meta", Static)
        meta_widget.update(
            f"Shields: {format_shields(team_snap.shields)}   "
            f"{format_stat_stages(active_state.atk_stage, active_state.def_stage)}"
        )

        self._set_sprite(
            f"p{player}-active-sprite",
            active_mon.species.id,
            flip_x=flip_x,
            fainted=not active_state.is_alive,
            scale=3,
        )

        # Fast move loading-meter box
        fast_box = self.query_one(f"#p{player}-fast-move", FastMoveMeter)
        fast_box.set_state(active_mon.fast_move, snap.fast_move_progress[player])

        # Charged move boxes (modulo energy meter)
        for cm_idx in (0, 1):
            cm_box = self.query_one(f"#p{player}-cm-{cm_idx}", Static)
            cm_fired = snap.charged_move_used[player] == cm_idx
            cm_box.set_class(cm_fired, "-active-move")
            if cm_idx < len(active_mon.charged_moves):
                cm = active_mon.charged_moves[cm_idx]
                cm_color = TYPE_COLORS.get(cm.type, "#888888")
                bar = render_charged_energy_bar(cm, active_state.energy)
                fired_marker = "[bold #FACC15]★[/] " if cm_fired else ""
                cm_title = f"{fired_marker}[bold {cm_color}]{escape(cm.name)}[/]"
                cm_box.update(
                    f"{cm_title} [dim]({cm.energy_cost}e)[/dim]\n"
                    f"{bar}\n"
                    f"[dim]Energy: {active_state.energy}/100[/dim]"
                )
            else:
                cm_box.update("[dim]—[/dim]")

        # Bench (2 benched Pokémon sprites with only HP bars + team switch timer)
        bench_indices = team_snap.bench_indices()
        for slot in (0, 1):
            hp_label = self.query_one(f"#p{player}-bench-hp-{slot}", Static)
            if slot < len(bench_indices):
                mon_idx = bench_indices[slot]
                benched_mon = team_meta[mon_idx]
                benched_state = team_snap.pokemon[mon_idx]
                self._set_sprite(
                    f"p{player}-bench-sprite-{slot}",
                    benched_mon.species.id,
                    flip_x=flip_x,
                    fainted=not benched_state.is_alive,
                    scale=2,
                )
                hp_label.update(render_compact_hp_bar(benched_state.hp, benched_state.max_hp))
            else:
                self._set_sprite(
                    f"p{player}-bench-sprite-{slot}",
                    None,
                    flip_x=flip_x,
                    fainted=False,
                    scale=2,
                )
                hp_label.update("")

        timer_widget = self.query_one(f"#p{player}-switch-timer", Static)
        if team_snap.switch_timer > 0:
            timer_secs = team_snap.switch_timer * BASE_TURN_SECONDS
            timer_widget.update(
                f"[dim]Switch[/dim]\n"
                f"[bold #F59E0B]{team_snap.switch_timer}t[/]\n"
                f"[dim]({timer_secs:.1f}s)[/dim]"
            )
        else:
            timer_widget.update("[dim]Switch[/dim]\n[bold #22C55E]Ready[/]")

    def _render_log(self) -> None:
        lines: list[str] = []
        for idx in range(self.step_index + 1):
            snap = self.replay.snapshots[idx]
            is_current = idx == self.step_index
            for entry in snap.log_entries:
                escaped = escape(entry)
                if is_current:
                    lines.append(f"[bold #FACC15]▶ {escaped}[/]")
                else:
                    lines.append(f"  [dim]{escaped}[/dim]")
        content = self.query_one("#battle-log-content", Static)
        content.update("\n".join(lines))
        scroll = self.query_one("#battle-log-scroll", VerticalScroll)
        scroll.scroll_end(animate=False)

    def _render_snapshot(self) -> None:
        snap = self.current_snapshot
        self._render_header()
        self._render_player(0, snap)
        self._render_player(1, snap)
        if self.show_log:
            self._render_log()
