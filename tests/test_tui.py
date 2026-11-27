"""Unit and headless Textual Pilot tests for the pogo-lab TUI."""

from __future__ import annotations

import asyncio

import pytest
from textual.widgets import DataTable, Input, OptionList

from pogo_lab import IVs, load_game_data
from pogo_lab.tui import PogoLabApp
from pogo_lab.tui.app import HomeScreen, RankScreen
from pogo_lab.tui.helpers import LEAGUES, parse_lookup, search_species


def test_search_species_prefix_only():
    game_data = load_game_data()

    matches = search_species("azum", game_data.species)
    assert matches
    assert matches[0].id == "azumarill"

    exact = search_species("abra", game_data.species)
    assert exact[0].id == "abra"

    # Substring-only queries should not match when autocomplete is prefix-only
    marill_matches = search_species("marill", game_data.species)
    assert marill_matches
    assert all(sp.name.lower().startswith("marill") for sp in marill_matches)
    assert search_species("zumar", game_data.species) == []
    assert search_species("   ", game_data.species) == []


def test_parse_lookup_ivs_and_rank():
    assert parse_lookup("") is None
    assert parse_lookup("0/15/15") == IVs(0, 15, 15)
    assert parse_lookup("0 15 15") == IVs(0, 15, 15)
    assert parse_lookup("#1") == 1
    assert parse_lookup("42") == 42

    with pytest.raises(ValueError):
        parse_lookup("16/15/15")
    with pytest.raises(ValueError):
        parse_lookup("#0")
    with pytest.raises(ValueError):
        parse_lookup("not-valid")


def test_home_screen_and_league_cycling():
    game_data = load_game_data()

    async def run() -> None:
        app = PogoLabApp(game_data=game_data)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            assert app.ENABLE_COMMAND_PALETTE is False
            assert isinstance(app.screen, HomeScreen)
            assert app.screen.selected_index == 0

            # Up/Down arrows navigate menu; Enter on WIP item (index 1) stays on HomeScreen
            await pilot.press("down")
            await pilot.pause()
            assert app.screen.selected_index == 1
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)

            # Up returns to Rank Checker (index 0); pressing 2 stays on HomeScreen
            await pilot.press("up")
            await pilot.pause()
            assert app.screen.selected_index == 0
            await pilot.press("2")
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)

            # Pressing Enter (or 1) opens RankScreen
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, RankScreen)

            rank_screen = app.screen
            assert rank_screen.league_index == 0
            assert rank_screen.selected_species_id == ""
            assert rank_screen.query_one("#species-input", Input).value == ""
            assert [league.label for league in LEAGUES] == [
                "Great League (1500 CP Limit)",
                "Ultra League (2500 CP Limit)",
                "Master League (No CP Limit)",
            ]
            table = rank_screen.query_one("#rank-table", DataTable)
            assert table.row_count == 0

            # Shift+Tab cycles Great -> Ultra -> Master -> Great
            await pilot.press("shift+tab")
            await pilot.pause()
            assert rank_screen.league_index == 1
            assert LEAGUES[rank_screen.league_index].cp_cap == 2500

            await pilot.press("shift+tab")
            await pilot.pause()
            assert rank_screen.league_index == 2
            assert LEAGUES[rank_screen.league_index].cp_cap is None

            await pilot.press("shift+tab")
            await pilot.pause()
            assert rank_screen.league_index == 0
            assert LEAGUES[rank_screen.league_index].cp_cap == 1500

            # Esc returns to HomeScreen when suggestions are closed
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)

    asyncio.run(run())


def test_tui_inline_preview_tab_autocomplete_and_lookup():
    game_data = load_game_data()

    async def run() -> None:
        app = PogoLabApp(game_data=game_data)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()
            await pilot.press("1")
            await pilot.pause()

            rank_screen = app.screen
            assert isinstance(rank_screen, RankScreen)

            species_input = rank_screen.query_one("#species-input", Input)
            lookup_input = rank_screen.query_one("#lookup-input", Input)
            summary_card = rank_screen.query_one("#summary-card")
            table = rank_screen.query_one("#rank-table", DataTable)
            suggestions = rank_screen.query_one("#species-suggestions", OptionList)

            # Capture layout regions before suggestions open
            lookup_region_before = lookup_input.region
            summary_region_before = summary_card.region
            table_region_before = table.region

            # Typing a prefix shows inline suggestion preview and floating dropdown
            species_input.focus()
            species_input.value = "dragonit"
            await pilot.pause()
            assert suggestions.has_class("-visible")
            assert species_input._suggestion.lower() == "dragonite"

            # Suggestions show Pokémon names only (no types in parentheses)
            option_labels = [
                str(suggestions.get_option_at_index(i).prompt)
                for i in range(suggestions.option_count)
            ]
            assert option_labels == ["Dragonite"]

            # Dropdown overlays existing UI without resizing or shifting elements
            assert lookup_input.region == lookup_region_before
            assert summary_card.region == summary_region_before
            assert table.region == table_region_before
            assert suggestions.region.x == species_input.region.x
            assert suggestions.region.y == species_input.region.bottom
            assert suggestions.region.width == species_input.region.width

            # Pressing Tab completes the top prefix match in-place and populates table
            await pilot.press("tab")
            await pilot.pause()
            assert rank_screen.selected_species_id == "dragonite"
            assert species_input.value == "Dragonite"
            assert not suggestions.has_class("-visible")
            assert table.row_count == 100

            # Lookup specific IV spread and toggle Best Buddy / IV floor
            lookup_input.value = "0/15/15"
            await pilot.pause()

            assert rank_screen.best_buddy is False
            await pilot.press("ctrl+b")
            await pilot.pause()
            assert rank_screen.best_buddy is True

            assert rank_screen.iv_floor_index == 0
            await pilot.press("ctrl+f")
            await pilot.pause()
            assert rank_screen.iv_floor_index == 1

            # Clearing the Pokémon input resets selection and empties the rank table
            species_input.value = ""
            await pilot.pause()
            assert rank_screen.selected_species_id == ""
            assert table.row_count == 0

    asyncio.run(run())
