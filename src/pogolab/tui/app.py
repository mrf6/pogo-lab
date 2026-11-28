"""Textual TUI application for pogolab."""

from __future__ import annotations

from collections.abc import Mapping

from rich.markup import escape
from textual import events, on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Center, Horizontal, Vertical
from textual.reactive import reactive
from textual.screen import Screen
from textual.suggester import Suggester
from textual.widgets import DataTable, Footer, Input, OptionList, Static
from textual.widgets.option_list import Option

from pogolab.data import GameData, IVs, Species, load_game_data
from pogolab.rank_checker import RankedSpread, rank_species
from pogolab.tui.helpers import (
    IV_FLOORS,
    LEAGUES,
    TYPE_COLORS,
    format_ivs,
    format_level,
    parse_lookup,
    search_species,
)

MAX_TABLE_ROWS = 100

LOGO_ART = """
██████╗  ██████╗  ██████╗  ██████╗ ██╗      █████╗ ██████╗
██╔══██╗██╔═══██╗██╔════╝ ██╔═══██╗██║     ██╔══██╗██╔══██╗
██████╔╝██║   ██║██║  ███╗██║   ██║██║     ███████║██████╔╝
██╔═══╝ ██║   ██║██║   ██║██║   ██║██║     ██╔══██║██╔══██╗
██║     ╚██████╔╝╚██████╔╝╚██████╔╝███████╗██║  ██║██████╔╝
╚═╝      ╚═════╝  ╚═════╝  ╚═════╝ ╚══════╝╚═╝  ╚═╝╚═════╝
""".strip("\n")


class SpeciesSuggester(Suggester):
    """Inline prefix suggester for Pokémon species names."""

    def __init__(self, species: Mapping[str, Species]) -> None:
        super().__init__(use_cache=False, case_sensitive=False)
        self._species = species

    async def get_suggestion(self, value: str) -> str | None:
        cleaned = value.strip()
        if not cleaned:
            return None
        matches = search_species(cleaned, self._species, limit=1)
        if not matches:
            return None
        top_name = matches[0].name
        if top_name.lower().startswith(cleaned.lower()):
            # Preserve the user's typed prefix so Textual renders the inline ghost suffix.
            return value + top_name[len(cleaned) :]
        return None


class HomeScreen(Screen[None]):
    """Landing screen with ASCII art and mode selection."""

    BINDINGS = [
        Binding("1", "open_rank_checker", "IV Rank Checker"),
        Binding("up", "move_up", "Up", show=False),
        Binding("down", "move_down", "Down", show=False),
        Binding("enter", "activate_selected", "Open", show=False),
    ]

    selected_index: reactive[int] = reactive(0)

    def compose(self) -> ComposeResult:
        with Vertical(id="home-container"):
            with Center():
                yield Static(LOGO_ART, id="home-logo")
            yield Static(
                "Pokémon GO Data Analysis & Battle Simulations",
                id="home-subtitle",
            )
            with Center():
                with Vertical(id="home-menu"):
                    yield Static(
                        "▶ 1.  IV Rank Checker",
                        id="menu-rank",
                        classes="menu-item -selected",
                    )
                    yield Static(
                        "  2.  Battle Sim (WIP)",
                        id="menu-battle",
                        classes="menu-item -disabled",
                    )
            yield Static("Navigate with ↑/↓", id="home-hint")
        yield Footer()

    def watch_selected_index(self, selected_index: int) -> None:
        if not self.is_mounted:
            return
        rank_item = self.query_one("#menu-rank", Static)
        battle_item = self.query_one("#menu-battle", Static)
        rank_item.set_class(selected_index == 0, "-selected")
        battle_item.set_class(selected_index == 1, "-selected")
        rank_item.update(
            "▶ 1.  IV Rank Checker" if selected_index == 0 else "  1.  IV Rank Checker"
        )
        battle_item.update(
            "▶ 2.  Battle Sim (WIP)" if selected_index == 1 else "  2.  Battle Sim (WIP)"
        )

    def action_move_up(self) -> None:
        self.selected_index = (self.selected_index - 1) % 2

    def action_move_down(self) -> None:
        self.selected_index = (self.selected_index + 1) % 2

    def action_activate_selected(self) -> None:
        if self.selected_index == 0:
            self.action_open_rank_checker()

    def action_open_rank_checker(self) -> None:
        app = self.app
        assert isinstance(app, PogoLabApp)
        app.push_screen(RankScreen(app.game_data))

    def on_click(self, event: events.Click) -> None:
        if event.widget is not None and event.widget.id == "menu-rank":
            self.selected_index = 0
            self.action_open_rank_checker()


class RankScreen(Screen[None]):
    """Interactive PvP IV rank checker screen."""

    BINDINGS = [
        Binding("shift+tab", "cycle_league", "League", priority=True),
        Binding("ctrl+b", "toggle_best_buddy", "Best Buddy", priority=True),
        Binding("ctrl+f", "cycle_iv_floor", "IV Floor", priority=True),
        Binding("escape", "back_or_dismiss", "Home"),
    ]

    league_index: reactive[int] = reactive(0)
    iv_floor_index: reactive[int] = reactive(0)
    best_buddy: reactive[bool] = reactive(False)
    selected_species_id: reactive[str] = reactive("")
    lookup_query: reactive[str] = reactive("")

    def __init__(self, game_data: GameData) -> None:
        super().__init__()
        self.game_data = game_data
        self._current_matches: list[Species] = []

    @property
    def current_species(self) -> Species | None:
        if not self.selected_species_id:
            return None
        return self.game_data.species.get(self.selected_species_id)

    def compose(self) -> ComposeResult:
        with Horizontal(id="league-bar"):
            for index, league in enumerate(LEAGUES):
                classes = f"league-pill league-{league.key}"
                if index == 0:
                    classes += " -active"
                yield Static(league.label, id=f"league-pill-{index}", classes=classes)

        with Horizontal(id="top-panel"):
            with Vertical(id="inputs-column"):
                yield Static("Pokémon (Tab to autocomplete)", classes="field-label")
                yield Input(
                    placeholder="Type Pokémon name...",
                    suggester=SpeciesSuggester(self.game_data.species),
                    id="species-input",
                )

                yield Static(
                    "IVs or Rank (e.g. 0/15/15 or #1)",
                    id="lookup-label",
                    classes="field-label",
                )
                yield Input(placeholder="0/15/15 or #1", id="lookup-input")

            yield Static(id="summary-card")

        yield DataTable(id="rank-table", cursor_type="row", zebra_stripes=True)
        yield OptionList(id="species-suggestions")
        yield Footer()

    def on_mount(self) -> None:
        table = self.query_one("#rank-table", DataTable)
        table.add_columns(
            "Rank",
            "IVs",
            "Lv",
            "CP",
            "Atk",
            "Def",
            "HP",
            "Stat Prod",
            "% Max",
        )
        self._refresh_rank_view()
        self.query_one("#species-input", Input).focus()

    def watch_league_index(self, league_index: int) -> None:
        if not self.is_mounted:
            return
        for index in range(len(LEAGUES)):
            pill = self.query_one(f"#league-pill-{index}", Static)
            pill.set_class(index == league_index, "-active")
        self._refresh_rank_view()

    def watch_iv_floor_index(self) -> None:
        if self.is_mounted:
            self._refresh_rank_view()

    def watch_best_buddy(self) -> None:
        if self.is_mounted:
            self._refresh_rank_view()

    def watch_selected_species_id(self) -> None:
        if self.is_mounted:
            self._refresh_rank_view()

    def watch_lookup_query(self) -> None:
        if self.is_mounted:
            self._refresh_rank_view()

    def action_cycle_league(self) -> None:
        self.league_index = (self.league_index + 1) % len(LEAGUES)

    def action_toggle_best_buddy(self) -> None:
        self.best_buddy = not self.best_buddy

    def action_cycle_iv_floor(self) -> None:
        self.iv_floor_index = (self.iv_floor_index + 1) % len(IV_FLOORS)

    def action_back_or_dismiss(self) -> None:
        suggestions = self.query_one("#species-suggestions", OptionList)
        if suggestions.has_class("-visible"):
            self._hide_suggestions()
            return
        self.app.pop_screen()

    def _set_species_input_text(self, text: str) -> None:
        species_input = self.query_one("#species-input", Input)
        with species_input.prevent(Input.Changed):
            species_input.value = text
            species_input.cursor_position = len(text)

    def _position_suggestions(self) -> None:
        species_input = self.query_one("#species-input", Input)
        suggestions = self.query_one("#species-suggestions", OptionList)
        region = species_input.region
        suggestions.styles.offset = (region.x, region.bottom)
        suggestions.styles.width = region.width

    def on_resize(self) -> None:
        suggestions = self.query_one("#species-suggestions", OptionList)
        if suggestions.has_class("-visible"):
            self.call_after_refresh(self._position_suggestions)

    def _hide_suggestions(self) -> None:
        suggestions = self.query_one("#species-suggestions", OptionList)
        suggestions.remove_class("-visible")

    def _select_species(self, species: Species) -> None:
        self._current_matches = []
        self._set_species_input_text(species.name)
        self._hide_suggestions()
        self.selected_species_id = species.id

    @on(Input.Changed, "#species-input")
    def _on_species_input_changed(self, event: Input.Changed) -> None:
        query = event.value.strip()
        suggestions = self.query_one("#species-suggestions", OptionList)
        suggestions.clear_options()

        if not query:
            self._current_matches = []
            self._hide_suggestions()
            self.selected_species_id = ""
            return

        matches = search_species(query, self.game_data.species, limit=8)
        self._current_matches = matches

        if not matches:
            self._hide_suggestions()
            return

        for sp in matches:
            suggestions.add_option(Option(sp.name, id=sp.id))

        self._position_suggestions()
        suggestions.add_class("-visible")

        first = matches[0]
        if query.lower() in (first.name.lower(), first.id.lower()):
            self.selected_species_id = first.id

    @on(Input.Submitted, "#species-input")
    def _on_species_input_submitted(self) -> None:
        if self._current_matches:
            self._select_species(self._current_matches[0])

    @on(OptionList.OptionSelected, "#species-suggestions")
    def _on_suggestion_selected(self, event: OptionList.OptionSelected) -> None:
        species_id = event.option.id
        if species_id and species_id in self.game_data.species:
            self._select_species(self.game_data.species[species_id])
            self.query_one("#species-input", Input).focus()

    @on(Input.Changed, "#lookup-input")
    def _on_lookup_changed(self, event: Input.Changed) -> None:
        self.lookup_query = event.value

    def on_key(self, event: events.Key) -> None:
        species_input = self.query_one("#species-input", Input)
        if self.focused is not species_input:
            return

        if event.key == "tab" and self._current_matches:
            top = self._current_matches[0]
            if species_input.value.strip().lower() != top.name.lower():
                self._select_species(top)
                event.prevent_default()
                event.stop()
                return

        if event.key == "down":
            suggestions = self.query_one("#species-suggestions", OptionList)
            if suggestions.has_class("-visible") and suggestions.option_count > 0:
                suggestions.focus()
                suggestions.highlighted = 0
                event.stop()

    def _format_type_badges(self, species: Species) -> str:
        badges = []
        for pokemon_type in species.types:
            color = TYPE_COLORS.get(pokemon_type, "#888888")
            badges.append(f"[bold black on {color}] {pokemon_type.value.upper()} [/]")
        return " ".join(badges)

    def _add_spread_row(self, table: DataTable, spread: RankedSpread, *, marker: str = "") -> None:
        rank_label = f"{marker}#{spread.rank}"
        table.add_row(
            rank_label,
            format_ivs(spread.ivs),
            format_level(spread.level),
            str(spread.cp),
            f"{spread.stats.attack:.1f}",
            f"{spread.stats.defense:.1f}",
            str(spread.stats.hp),
            f"{spread.stat_product:,.0f}",
            f"{spread.stat_product_pct:.2f}%",
            key=str(spread.rank),
        )

    def _refresh_rank_view(self) -> None:
        species = self.current_species
        league = LEAGUES[self.league_index]
        iv_floor = IV_FLOORS[self.iv_floor_index]
        max_level = 51.0 if self.best_buddy else 50.0
        bb_tag = "Lv 51 (Best Buddy)" if self.best_buddy else "Lv 50"

        summary = self.query_one("#summary-card", Static)
        table = self.query_one("#rank-table", DataTable)

        if species is None:
            summary.update(
                "[bold]No Pokémon selected[/bold]\n"
                f"[dim]League:[/dim] [bold {league.color}]{league.name}[/]   "
                f"[dim]Cap:[/dim] {bb_tag}   "
                f"[dim]IV Floor:[/dim] {iv_floor.label}\n\n"
                "[dim]Type a Pokémon name on the left and press Tab or Enter "
                "to inspect base stats and PvP IV rankings.[/dim]"
            )
            table.clear()
            return

        rank_table = rank_species(
            species,
            cp_cap=league.cp_cap,
            max_level=max_level,
            iv_floor=iv_floor.floor,
        )

        matched_spread: RankedSpread | None = None
        lookup_error: str | None = None
        if self.lookup_query.strip():
            try:
                parsed = parse_lookup(self.lookup_query)
                if isinstance(parsed, IVs):
                    matched_spread = rank_table.by_ivs(parsed)
                elif isinstance(parsed, int):
                    matched_spread = rank_table.by_rank(parsed)
            except ValueError as exc:
                lookup_error = str(exc)

        stats = species.base_stats
        header_line = (
            f"[bold]{escape(species.name)}[/bold]  {self._format_type_badges(species)}    "
            f"[dim]Base:[/dim] {stats.attack} Atk / {stats.defense} Def / {stats.hp} HP"
        )
        constraint_line = (
            f"[dim]League:[/dim] [bold {league.color}]{league.name}[/]   "
            f"[dim]Cap:[/dim] {bb_tag}   "
            f"[dim]IV Floor:[/dim] {iv_floor.label}   "
            f"[dim]Eligible:[/dim] {len(rank_table):,}"
        )

        if lookup_error:
            detail_line = f"[bold red]Lookup:[/bold red] {escape(lookup_error)}"
        elif matched_spread is not None:
            detail_line = (
                f"[bold green]Match:[/bold green] "
                f"Rank [bold]#{matched_spread.rank}[/bold]  •  "
                f"IVs [bold]{format_ivs(matched_spread.ivs)}[/bold]  •  "
                f"Lv {format_level(matched_spread.level)}  •  "
                f"[bold]{matched_spread.cp} CP[/bold]  •  "
                f"{matched_spread.stat_product_pct:.2f}% max"
            )
        elif len(rank_table) > 0:
            top = rank_table.by_rank(1)
            detail_line = (
                f"[dim]Rank #1:[/dim] "
                f"[bold]{format_ivs(top.ivs)}[/bold]  •  "
                f"Lv {format_level(top.level)}  •  "
                f"[bold]{top.cp} CP[/bold]  •  "
                f"Stat Prod {top.stat_product:,.0f}"
            )
        else:
            detail_line = "[yellow]No eligible IV spreads for this league and IV floor.[/yellow]"

        summary.update(f"{header_line}\n{constraint_line}\n{detail_line}")

        table.clear()

        displayed = rank_table.spreads[:MAX_TABLE_ROWS]
        highlight_row_index: int | None = None

        for row_idx, spread in enumerate(displayed):
            is_match = matched_spread is not None and spread.rank == matched_spread.rank
            self._add_spread_row(table, spread, marker="▶ " if is_match else "")
            if is_match:
                highlight_row_index = row_idx

        if matched_spread is not None and matched_spread.rank > MAX_TABLE_ROWS:
            self._add_spread_row(table, matched_spread, marker="▶ ")
            highlight_row_index = len(displayed)

        if highlight_row_index is not None and table.row_count > 0:
            table.move_cursor(row=highlight_row_index)


class PogoLabApp(App[None]):
    """Interactive terminal UI for Pokémon GO PvP IV rankings and future simulations."""

    TITLE = "pogolab"
    SUB_TITLE = "Pokémon GO PvP Lab"
    CSS_PATH = "styles.tcss"
    ENABLE_COMMAND_PALETTE = False

    BINDINGS = [
        Binding("ctrl+c", "quit", "Quit", priority=True),
    ]

    def __init__(self, game_data: GameData | None = None) -> None:
        super().__init__()
        self.game_data = game_data or load_game_data()

    def on_mount(self) -> None:
        self.push_screen(HomeScreen())


def run_tui() -> None:
    """Launch the pogolab Textual TUI."""
    PogoLabApp().run()
