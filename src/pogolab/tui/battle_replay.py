"""Deterministic battle recording, team generation, and display helpers for the Battle Sim TUI."""

from __future__ import annotations

import random
from collections.abc import Sequence
from dataclasses import dataclass

from pogolab.battle import (
    Action,
    BattleBot,
    BattleState,
    Phase,
    Winner,
    create_engine,
    to_team_data,
)
from pogolab.data import ChargedMove, GameData, Type
from pogolab.pokemon import Pokemon
from pogolab.tui.helpers import TYPE_COLORS

GREAT_LEAGUE_META_IDS: tuple[str, ...] = (
    "azumarill",
    "altaria",
    "skarmory",
    "swampert",
    "registeel",
    "stunfisk_galarian",
    "medicham",
    "trevenant",
    "lickitung",
    "clodsire",
    "annihilape",
    "feraligatr",
    "gligar",
    "whiscash",
    "mandibuzz",
    "sableye",
    "talonflame",
    "venusaur",
    "poliwrath",
    "dewgong",
)

PLAYBACK_SPEEDS: tuple[float, ...] = (0.25, 0.5, 1.0, 2.0, 4.0)
BASE_TURN_SECONDS: float = 0.5


@dataclass(frozen=True, slots=True)
class PokemonSnapshot:
    """Immutable per-Pokémon state captured at a single battle step."""

    hp: int
    max_hp: int
    energy: int
    atk_stage: int
    def_stage: int
    is_alive: bool


@dataclass(frozen=True, slots=True)
class TeamSnapshot:
    """Immutable per-team state captured at a single battle step."""

    active_idx: int
    shields: int
    switch_timer: int
    fast_move_cooldown: int
    pokemon: tuple[PokemonSnapshot, ...]

    @property
    def active(self) -> PokemonSnapshot:
        return self.pokemon[self.active_idx]

    def bench_indices(self) -> tuple[int, ...]:
        return tuple(idx for idx in range(len(self.pokemon)) if idx != self.active_idx)


@dataclass(frozen=True, slots=True)
class FastMoveProgress:
    """Fast move windup and impact state for one player on a recorded step."""

    elapsed: int = 0
    total: int = 0
    landed: bool = False

    @property
    def is_active(self) -> bool:
        return self.elapsed > 0 and self.total > 0

    @property
    def ratio(self) -> float:
        if self.total <= 0:
            return 0.0
        return max(0.0, min(1.0, self.elapsed / self.total))


@dataclass(frozen=True, slots=True)
class BattleSnapshot:
    """Immutable battle state snapshot + structured turn log for one recorded step."""

    step_index: int
    turn: int
    phase: Phase
    winner: Winner
    teams: tuple[TeamSnapshot, TeamSnapshot]
    actions: tuple[Action | None, Action | None]
    fast_move_used: tuple[bool, bool]
    fast_move_progress: tuple[FastMoveProgress, FastMoveProgress]
    charged_move_used: tuple[int | None, int | None]
    log_entries: tuple[str, ...]


@dataclass(frozen=True, slots=True)
class BattleReplay:
    """Complete pre-recorded battle for instant deterministic scrubbing."""

    teams: tuple[tuple[Pokemon, ...], tuple[Pokemon, ...]]
    snapshots: tuple[BattleSnapshot, ...]
    seed: int
    max_turns: int
    winner: Winner


def _snapshot_state(state: BattleState) -> tuple[TeamSnapshot, TeamSnapshot]:
    team_snaps: list[TeamSnapshot] = []
    for player in (0, 1):
        team = state.teams[player]
        mons = tuple(
            PokemonSnapshot(
                hp=int(team.pokemon[i].hp),
                max_hp=int(team.pokemon[i].max_hp),
                energy=int(team.pokemon[i].energy),
                atk_stage=int(team.pokemon[i].atk_stage),
                def_stage=int(team.pokemon[i].def_stage),
                is_alive=bool(team.pokemon[i].is_alive),
            )
            for i in range(team.team_size)
        )
        team_snaps.append(
            TeamSnapshot(
                active_idx=int(team.active_idx),
                shields=int(team.shields),
                switch_timer=int(team.switch_timer),
                fast_move_cooldown=int(team.fast_move_cooldown),
                pokemon=mons,
            )
        )
    return (team_snaps[0], team_snaps[1])


def _charged_move_index(action: Action) -> int | None:
    if action == Action.CHARGED_MOVE_0:
        return 0
    if action == Action.CHARGED_MOVE_1:
        return 1
    return None


def _switch_target_index(action: Action) -> int | None:
    if action == Action.SWITCH_0:
        return 0
    if action == Action.SWITCH_1:
        return 1
    if action == Action.SWITCH_2:
        return 2
    return None


def _build_step_log(
    prev_turn: int,
    prev_phase: Phase,
    prev_teams: tuple[TeamSnapshot, TeamSnapshot],
    next_turn: int,
    next_winner: Winner,
    next_teams: tuple[TeamSnapshot, TeamSnapshot],
    actions: tuple[Action, Action],
    teams_meta: tuple[tuple[Pokemon, ...], tuple[Pokemon, ...]],
) -> tuple[str, ...]:
    """Generate human-readable log lines describing what happened during a single engine step."""
    lines: list[str] = []
    prefix = f"T{next_turn:03d}"

    for player in (0, 1):
        action = actions[player]
        p_label = f"P{player + 1}"
        prev_team = prev_teams[player]
        active_mon = teams_meta[player][prev_team.active_idx]

        switch_idx = _switch_target_index(action)
        if switch_idx is not None and switch_idx < len(teams_meta[player]):
            incoming = teams_meta[player][switch_idx].species.name
            lines.append(f"{prefix} {p_label} switched in {incoming}")
        elif prev_phase == Phase.SHIELD_DECISION:
            if action == Action.SHIELD:
                lines.append(f"{prefix} {p_label} used a Shield!")
            elif action == Action.NO_SHIELD:
                lines.append(f"{prefix} {p_label} did not shield")
        else:
            cm_idx = _charged_move_index(action)
            if cm_idx is not None and cm_idx < len(active_mon.charged_moves):
                move_name = active_mon.charged_moves[cm_idx].name
                lines.append(f"{prefix} {p_label} {active_mon.species.name} threw {move_name}!")
            elif action == Action.FAST_MOVE and active_mon.fast_move is not None:
                fm_name = active_mon.fast_move.name
                lines.append(f"{prefix} {p_label} {active_mon.species.name} used {fm_name}")

    # Report charged-move damage and stat-stage changes cleanly once per player
    for player in (0, 1):
        p_label = f"P{player + 1}"
        prev_team = prev_teams[player]
        next_team = next_teams[player]
        active_idx = prev_team.active_idx
        active_name = teams_meta[player][active_idx].species.name
        prev_mon = prev_team.pokemon[active_idx]
        next_mon = next_team.pokemon[active_idx]

        if prev_phase == Phase.SHIELD_DECISION and next_mon.hp < prev_mon.hp:
            dmg = prev_mon.hp - next_mon.hp
            lines.append(f"{prefix} {p_label} {active_name} took {dmg} damage")

        if prev_team.active_idx == next_team.active_idx:
            atk_diff = next_mon.atk_stage - prev_mon.atk_stage
            def_diff = next_mon.def_stage - prev_mon.def_stage
            if atk_diff != 0:
                sign = "+" if atk_diff > 0 else ""
                lines.append(f"{prefix} {p_label} {active_name} Atk {sign}{atk_diff}")
            if def_diff != 0:
                sign = "+" if def_diff > 0 else ""
                lines.append(f"{prefix} {p_label} {active_name} Def {sign}{def_diff}")

    # Report faints cleanly
    for player in (0, 1):
        for idx in range(len(teams_meta[player])):
            was_alive = prev_teams[player].pokemon[idx].is_alive
            now_alive = next_teams[player].pokemon[idx].is_alive
            if was_alive and not now_alive:
                fainted_name = teams_meta[player][idx].species.name
                lines.append(f"{prefix} P{player + 1} {fainted_name} fainted!")

    if next_winner != Winner.NONE:
        if next_winner == Winner.PLAYER_0:
            lines.append(f"{prefix} Battle finished — Player 1 wins!")
        elif next_winner == Winner.PLAYER_1:
            lines.append(f"{prefix} Battle finished — Player 2 wins!")
        else:
            lines.append(f"{prefix} Battle finished — Tie!")
    elif not lines and next_turn != prev_turn:
        lines.append(f"{prefix} Turn advanced")

    return tuple(lines)


def generate_random_gl_teams(
    game_data: GameData,
    *,
    rng: random.Random | None = None,
    species_pool: Sequence[str] = GREAT_LEAGUE_META_IDS,
    team_size: int = 3,
) -> tuple[tuple[Pokemon, ...], tuple[Pokemon, ...]]:
    """Generate two random Great League teams with random movesets from ``species_pool``."""
    generator = rng if rng is not None else random.Random()

    eligible = [
        game_data.species[sid]
        for sid in species_pool
        if sid in game_data.species
        and game_data.species[sid].fast_moves
        and len(game_data.species[sid].charged_moves) >= 1
    ]
    total_needed = team_size * 2
    if len(eligible) < total_needed:
        raise ValueError(f"Need at least {total_needed} eligible species, found {len(eligible)}")

    chosen_species = generator.sample(eligible, total_needed)
    built: list[Pokemon] = []
    for sp in chosen_species:
        fast_move = generator.choice(sp.fast_moves)
        num_charged = min(2, len(sp.charged_moves))
        charged = tuple(
            sorted(
                generator.sample(sp.charged_moves, num_charged),
                key=lambda mv: (mv.energy_cost, mv.name),
            )
        )
        built.append(
            Pokemon(
                sp,
                cp_cap=1500,
                fast_move=fast_move,
                charged_moves=charged,
            )
        )

    return (tuple(built[:team_size]), tuple(built[team_size:]))


def _compute_fast_move_progress(
    prev_phase: Phase,
    prev_team: TeamSnapshot,
    prev_pending: bool,
    next_team: TeamSnapshot,
    next_pending: bool,
    action: Action,
    team_meta: tuple[Pokemon, ...],
) -> FastMoveProgress:
    """Compute fast move windup (1..N-1) and impact (N/N) progress."""
    active_mon = team_meta[next_team.active_idx]
    prev_mon = team_meta[prev_team.active_idx]
    prev_turns = prev_mon.fast_move.turns if prev_mon.fast_move is not None else 0
    next_turns = active_mon.fast_move.turns if active_mon.fast_move is not None else 0

    if prev_phase == Phase.TURN and action == Action.FAST_MOVE and prev_turns > 0:
        if next_pending and next_team.fast_move_cooldown > 0:
            elapsed = max(1, prev_turns - next_team.fast_move_cooldown)
            return FastMoveProgress(elapsed=elapsed, total=prev_turns, landed=False)
        return FastMoveProgress(elapsed=prev_turns, total=prev_turns, landed=True)

    if prev_phase == Phase.TURN and prev_pending and prev_turns > 0:
        if next_pending and next_team.fast_move_cooldown > 0:
            elapsed = max(1, prev_turns - next_team.fast_move_cooldown)
            return FastMoveProgress(elapsed=elapsed, total=prev_turns, landed=False)
        if next_team.active_idx == prev_team.active_idx and next_team.fast_move_cooldown == 0:
            return FastMoveProgress(elapsed=prev_turns, total=prev_turns, landed=True)

    if next_pending and next_team.fast_move_cooldown > 0 and next_turns > 0:
        elapsed = max(1, next_turns - next_team.fast_move_cooldown)
        return FastMoveProgress(elapsed=elapsed, total=next_turns, landed=False)

    return FastMoveProgress(elapsed=0, total=next_turns, landed=False)


def record_battle(
    game_data: GameData,
    team0: Sequence[Pokemon],
    team1: Sequence[Pokemon],
    bot0: BattleBot,
    bot1: BattleBot,
    *,
    seed: int = 0,
    max_steps: int = 5000,
) -> BattleReplay:
    """Simulate a full battle and record per-step snapshots and turn log entries."""
    engine = create_engine(game_data)
    engine.reset(to_team_data(team0), to_team_data(team1), seed=seed)

    teams_tuple = (tuple(team0), tuple(team1))
    state = engine.state()
    initial_teams = _snapshot_state(state)
    lead0 = teams_tuple[0][initial_teams[0].active_idx].species.name
    lead1 = teams_tuple[1][initial_teams[1].active_idx].species.name
    init_fm0 = teams_tuple[0][initial_teams[0].active_idx].fast_move
    init_fm1 = teams_tuple[1][initial_teams[1].active_idx].fast_move

    snapshots: list[BattleSnapshot] = [
        BattleSnapshot(
            step_index=0,
            turn=int(state.turn),
            phase=state.phase,
            winner=state.winner,
            teams=initial_teams,
            actions=(None, None),
            fast_move_used=(False, False),
            fast_move_progress=(
                FastMoveProgress(elapsed=0, total=init_fm0.turns if init_fm0 else 0, landed=False),
                FastMoveProgress(elapsed=0, total=init_fm1.turns if init_fm1 else 0, landed=False),
            ),
            charged_move_used=(None, None),
            log_entries=(f"T000 Battle started: {lead0} vs {lead1}",),
        )
    ]

    for step_idx in range(1, max_steps + 1):
        if engine.is_done:
            break

        prev_state = engine.state()
        prev_turn = int(prev_state.turn)
        prev_phase = prev_state.phase
        prev_teams = snapshots[-1].teams
        prev_pending = (
            bool(prev_state.teams[0].pending_fast_move),
            bool(prev_state.teams[1].pending_fast_move),
        )

        a0 = bot0.choose_action(engine, 0)
        a1 = bot1.choose_action(engine, 1)
        engine.step(a0, a1)

        next_state = engine.state()
        next_teams = _snapshot_state(next_state)
        next_pending = (
            bool(next_state.teams[0].pending_fast_move),
            bool(next_state.teams[1].pending_fast_move),
        )
        fast_used = (
            prev_phase == Phase.TURN and a0 == Action.FAST_MOVE,
            prev_phase == Phase.TURN and a1 == Action.FAST_MOVE,
        )
        fast_progress = (
            _compute_fast_move_progress(
                prev_phase,
                prev_teams[0],
                prev_pending[0],
                next_teams[0],
                next_pending[0],
                a0,
                teams_tuple[0],
            ),
            _compute_fast_move_progress(
                prev_phase,
                prev_teams[1],
                prev_pending[1],
                next_teams[1],
                next_pending[1],
                a1,
                teams_tuple[1],
            ),
        )
        cm_used = (
            _charged_move_index(a0) if prev_phase == Phase.TURN else None,
            _charged_move_index(a1) if prev_phase == Phase.TURN else None,
        )
        log_entries = _build_step_log(
            prev_turn=prev_turn,
            prev_phase=prev_phase,
            prev_teams=prev_teams,
            next_turn=int(next_state.turn),
            next_winner=next_state.winner,
            next_teams=next_teams,
            actions=(a0, a1),
            teams_meta=teams_tuple,
        )

        snapshots.append(
            BattleSnapshot(
                step_index=step_idx,
                turn=int(next_state.turn),
                phase=next_state.phase,
                winner=next_state.winner,
                teams=next_teams,
                actions=(a0, a1),
                fast_move_used=fast_used,
                fast_move_progress=fast_progress,
                charged_move_used=cm_used,
                log_entries=log_entries,
            )
        )

    final_state = engine.state()
    return BattleReplay(
        teams=teams_tuple,
        snapshots=tuple(snapshots),
        seed=seed,
        max_turns=int(engine.config().max_turns),
        winner=final_state.winner,
    )


def darken_hex(hex_color: str, factor: float) -> str:
    """Return a darker ``#RRGGBB`` color scaled by ``factor`` in ``[0, 1]``."""
    clamped = max(0.0, min(1.0, factor))
    r = round(int(hex_color[1:3], 16) * clamped)
    g = round(int(hex_color[3:5], 16) * clamped)
    b = round(int(hex_color[5:7], 16) * clamped)
    return f"#{r:02X}{g:02X}{b:02X}"


def hp_bar_color(hp: int, max_hp: int) -> str:
    """Return green / yellow / red hex color for an HP ratio."""
    ratio = (hp / max_hp) if max_hp > 0 else 0.0
    if ratio > 0.5:
        return "#22C55E"
    if ratio > 0.2:
        return "#EAB308"
    return "#EF4444"


_EIGHTH_BLOCKS: tuple[str, ...] = ("", "▏", "▎", "▍", "▌", "▋", "▊", "▉", "█")


def render_precise_bar(
    ratio: float,
    *,
    width: int,
    fg_color: str,
    bg_color: str,
    min_nonzero: bool = False,
) -> str:
    """Render a sub-cell precision horizontal bar using Unicode eighth-blocks."""
    clamped = max(0.0, min(1.0, ratio))
    total_eighths = round(clamped * width * 8)
    if min_nonzero and clamped > 0.0 and total_eighths == 0:
        total_eighths = 1

    full_cells = total_eighths // 8
    rem_eighths = total_eighths % 8
    empty_cells = width - full_cells - (1 if rem_eighths > 0 else 0)

    parts: list[str] = []
    if full_cells > 0:
        parts.append(f"[{fg_color} on {bg_color}]{'█' * full_cells}[/]")
    if rem_eighths > 0:
        parts.append(f"[{fg_color} on {bg_color}]{_EIGHTH_BLOCKS[rem_eighths]}[/]")
    if empty_cells > 0:
        parts.append(f"[on {bg_color}]{' ' * empty_cells}[/]")
    return "".join(parts)


def render_hp_bar(hp: int, max_hp: int, *, width: int = 18) -> str:
    """Render a high-precision Rich-markup HP bar with numeric readout."""
    ratio = (hp / max_hp) if max_hp > 0 else 0.0
    color = hp_bar_color(hp, max_hp)
    bar = render_precise_bar(
        ratio,
        width=width,
        fg_color=color,
        bg_color="#2A2E37",
        min_nonzero=hp > 0,
    )
    return f"{bar} {hp}/{max_hp}"


def render_compact_hp_bar(hp: int, max_hp: int, *, width: int = 9) -> str:
    """Render a compact high-precision Rich-markup HP bar for benched Pokémon."""
    ratio = (hp / max_hp) if max_hp > 0 else 0.0
    color = hp_bar_color(hp, max_hp) if hp > 0 else "#6B7280"
    return render_precise_bar(
        ratio,
        width=width,
        fg_color=color,
        bg_color="#2A2E37",
        min_nonzero=hp > 0,
    )


def render_charged_energy_bar(move: ChargedMove, energy: int, *, width: int = 14) -> str:
    """Render a sub-cell precision modulo-filling charged move energy bar.

    Cycle 1 (0..cost) fills in the move's type color over a dark track.
    Cycle 2 (cost..2*cost) fills in a darker shade over cycle 1's color.
    Cycle 3 (2*cost..100, when cost < 50) fills in an even darker shade over cycle 2's color.
    """
    cost = max(1, move.energy_cost)
    clamped_energy = max(0, min(100, energy))
    base_color = TYPE_COLORS.get(move.type, "#888888")
    cycle_colors = (
        base_color,
        darken_hex(base_color, 0.72),
        darken_hex(base_color, 0.48),
    )
    empty_color = "#2A2E37"

    full_charges = clamped_energy // cost
    remainder = clamped_energy % cost

    if clamped_energy == 0:
        ratio = 0.0
        fg_color = cycle_colors[0]
        bg_color = empty_color
    elif remainder == 0:
        cycle_idx = min(full_charges - 1, len(cycle_colors) - 1)
        ratio = 1.0
        fg_color = cycle_colors[cycle_idx]
        bg_color = cycle_colors[cycle_idx]
    else:
        cycle_idx = min(full_charges, len(cycle_colors) - 1)
        ratio = remainder / cost
        fg_color = cycle_colors[cycle_idx]
        if full_charges == 0:
            bg_color = empty_color
        else:
            bg_color = cycle_colors[min(full_charges - 1, len(cycle_colors) - 1)]

    bar = render_precise_bar(
        ratio,
        width=width,
        fg_color=fg_color,
        bg_color=bg_color,
        min_nonzero=clamped_energy > 0,
    )
    charge_tag = f" [bold]{full_charges}×[/]" if full_charges > 0 else ""
    return f"{bar}{charge_tag}"


def format_shields(shields: int, *, max_shields: int = 2) -> str:
    """Render remaining shields as visual icons."""
    used = max(0, max_shields - shields)
    parts = ["[bold #38BDF8]🛡[/]"] * shields + ["[dim #4B5563]◇[/]"] * used
    return " ".join(parts)


def format_stat_stages(atk_stage: int, def_stage: int) -> str:
    """Format non-zero attack/defense stat stage modifiers."""
    parts: list[str] = []
    if atk_stage != 0:
        color = "#22C55E" if atk_stage > 0 else "#EF4444"
        sign = "+" if atk_stage > 0 else ""
        parts.append(f"[{color}]Atk {sign}{atk_stage}[/]")
    if def_stage != 0:
        color = "#22C55E" if def_stage > 0 else "#EF4444"
        sign = "+" if def_stage > 0 else ""
        parts.append(f"[{color}]Def {sign}{def_stage}[/]")
    return "  ".join(parts) if parts else "[dim]Stages: 0/0[/dim]"


def format_type_badges(types: Sequence[Type]) -> str:
    """Format elemental types as colored Rich badges."""
    badges = []
    for pokemon_type in types:
        color = TYPE_COLORS.get(pokemon_type, "#888888")
        badges.append(f"[bold black on {color}] {pokemon_type.value.upper()} [/]")
    return " ".join(badges)
