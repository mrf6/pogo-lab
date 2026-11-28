"""Unit and headless Textual Pilot tests for the pogolab TUI."""

from __future__ import annotations

import asyncio
import random

import pytest
from textual.containers import Vertical
from textual.widgets import DataTable, Input, OptionList
from textual_image.widget import Image as TerminalImage

from pogolab import IVs, Pokemon, load_game_data
from pogolab.battle import GreedyBot, Winner
from pogolab.data.classes import ChargedMove, Type
from pogolab.tui import PogoLabApp
from pogolab.tui.app import HomeScreen, RankScreen
from pogolab.tui.battle_replay import (
    GREAT_LEAGUE_META_IDS,
    PLAYBACK_SPEEDS,
    darken_hex,
    generate_random_gl_teams,
    record_battle,
    render_charged_energy_bar,
    render_precise_bar,
)
from pogolab.tui.battle_screen import BattleScreen, FastMoveMeter
from pogolab.tui.helpers import LEAGUES, TYPE_COLORS, parse_lookup, rank_color, search_species
from pogolab.tui.sprites import load_sprites, sprite_to_pil


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
    assert parse_lookup("1") == 1
    assert parse_lookup("123") == 123

    for invalid in ("0 15 15", "0,15,15", "0-15-15", "#1", "#0", "0", "16/15/15", "not-valid"):
        with pytest.raises(ValueError):
            parse_lookup(invalid)


def test_rank_color_scaling():
    assert rank_color(1, 4096) == "#22C55E"
    assert rank_color(109, 217) == "#EAB308"
    assert rank_color(216, 216) == "#EF4444"
    assert rank_color(1, 1) == "#22C55E"


def test_home_screen_and_league_cycling():
    game_data = load_game_data()

    async def run() -> None:
        app = PogoLabApp(game_data=game_data)
        async with app.run_test(size=(120, 40)) as pilot:
            await pilot.pause()

            assert app.ENABLE_COMMAND_PALETTE is False
            assert isinstance(app.screen, HomeScreen)
            assert app.screen.selected_index == 0

            # Up/Down arrows navigate menu; Enter on index 1 opens BattleScreen
            await pilot.press("down")
            await pilot.pause()
            assert app.screen.selected_index == 1
            await pilot.press("enter")
            await pilot.pause()
            assert isinstance(app.screen, BattleScreen)

            # Esc returns to HomeScreen; pressing 2 also opens BattleScreen
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)
            await pilot.press("2")
            await pilot.pause()
            assert isinstance(app.screen, BattleScreen)
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)

            # Up returns to Rank Checker (index 0)
            await pilot.press("up")
            await pilot.pause()
            assert app.screen.selected_index == 0

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

            # Pressing Tab completes the top prefix match in-place and populates table + sprite
            await pilot.press("tab")
            await pilot.pause()
            assert rank_screen.selected_species_id == "dragonite"
            assert species_input.value == "Dragonite"
            assert not suggestions.has_class("-visible")
            assert table.row_count == 100
            sprite_view = rank_screen.query_one("#summary-sprite", TerminalImage)
            assert sprite_view.has_class("-visible")
            assert sprite_view.image is not None

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

            # Clearing the Pokémon input resets selection, empties rank table, and hides sprite
            species_input.value = ""
            await pilot.pause()
            assert rank_screen.selected_species_id == ""
            assert table.row_count == 0
            assert not sprite_view.has_class("-visible")

    asyncio.run(run())


def test_sprites_load_and_render():
    game_data = load_game_data()
    sprites = load_sprites()
    assert len(sprites) == len(game_data.species)

    azumarill = sprites["azumarill"]
    pil_img = sprite_to_pil(azumarill, scale=2)
    expected_side = max(azumarill.width, azumarill.height) * 2
    assert pil_img.mode == "RGBA"
    assert pil_img.size == (expected_side, expected_side)

    unpadded = sprite_to_pil(azumarill, scale=1, square_pad=False)
    assert unpadded.size == (azumarill.width, azumarill.height)


def test_battle_replay_generation_and_modulo_energy_bar():
    game_data = load_game_data()
    sprites = load_sprites()

    assert len(GREAT_LEAGUE_META_IDS) == 20
    for species_id in GREAT_LEAGUE_META_IDS:
        assert species_id in game_data.species
        assert species_id in sprites

    team0, team1 = generate_random_gl_teams(game_data, rng=random.Random(42))
    assert len(team0) == 3
    assert len(team1) == 3
    assert len({mon.species.id for mon in (*team0, *team1)}) == 6
    for mon in (*team0, *team1):
        assert mon.cp <= 1500
        assert mon.fast_move is not None
        assert len(mon.charged_moves) == 2

    replay = record_battle(game_data, team0, team1, GreedyBot(), GreedyBot(), seed=99)
    assert len(replay.snapshots) > 5
    assert replay.snapshots[0].step_index == 0
    assert replay.snapshots[0].turn == 0
    assert replay.winner in (Winner.PLAYER_0, Winner.PLAYER_1, Winner.TIE)
    assert replay.snapshots[-1].winner == replay.winner

    # Modulo energy bar shading across 1st, 2nd, and 3rd cycles for a 35-energy move
    cheap_move = ChargedMove(
        id="hydro_cannon",
        name="Hydro Cannon",
        type=Type.WATER,
        power=80,
        energy_cost=35,
    )
    base = TYPE_COLORS[Type.WATER]
    cycle2 = darken_hex(base, 0.72)
    cycle3 = darken_hex(base, 0.48)

    bar_cycle1 = render_charged_energy_bar(cheap_move, 20)
    assert base in bar_cycle1
    assert "×" not in bar_cycle1

    bar_cycle2 = render_charged_energy_bar(cheap_move, 50)
    assert cycle2 in bar_cycle2
    assert "1×" in bar_cycle2

    bar_cycle3 = render_charged_energy_bar(cheap_move, 100)
    assert cycle3 in bar_cycle3
    assert "2×" in bar_cycle3

    # Eighth-block sub-cell precision emits partial block glyphs for fractional fills
    half_cell = render_precise_bar(0.5 / 10, width=10, fg_color="#22C55E", bg_color="#2A2E37")
    assert "▌" in half_cell
    quarter_cell = render_precise_bar(0.25 / 10, width=10, fg_color="#22C55E", bg_color="#2A2E37")
    assert "▎" in quarter_cell


def test_fast_move_loading_progress_aligns_with_damage():
    game_data = load_game_data()
    # Azumarill with Bubble (3-turn fast move) vs Altaria with Dragon Breath (1-turn fast move)
    azu_sp = game_data.species["azumarill"]
    alt_sp = game_data.species["altaria"]
    bubble = next(mv for mv in azu_sp.fast_moves if mv.turns == 3)
    dbreath = next(mv for mv in alt_sp.fast_moves if mv.turns == 1)

    team0 = (
        Pokemon(azu_sp, cp_cap=1500, fast_move=bubble, charged_moves=azu_sp.charged_moves[:2]),
    )
    team1 = (
        Pokemon(alt_sp, cp_cap=1500, fast_move=dbreath, charged_moves=alt_sp.charged_moves[:2]),
    )
    replay = record_battle(game_data, team0, team1, GreedyBot(), GreedyBot(), seed=7)

    # Step 0: idle
    assert replay.snapshots[0].fast_move_progress[0].elapsed == 0
    assert replay.snapshots[0].fast_move_progress[0].landed is False

    # Step 1: 3-turn Bubble is at 1/3 (charging, no damage yet); 1-turn Dragon Breath is 1/1 landed
    p0_t1 = replay.snapshots[1].fast_move_progress[0]
    p1_t1 = replay.snapshots[1].fast_move_progress[1]
    assert (p0_t1.elapsed, p0_t1.total, p0_t1.landed) == (1, 3, False)
    assert (p1_t1.elapsed, p1_t1.total, p1_t1.landed) == (1, 1, True)
    assert replay.snapshots[1].teams[1].active.hp == replay.snapshots[0].teams[1].active.hp

    # Step 2: Bubble is at 2/3 (still charging)
    p0_t2 = replay.snapshots[2].fast_move_progress[0]
    assert (p0_t2.elapsed, p0_t2.total, p0_t2.landed) == (2, 3, False)
    assert replay.snapshots[2].teams[1].active.hp == replay.snapshots[0].teams[1].active.hp

    # Step 3: Bubble reaches 3/3 (landed!) and damage + energy apply on this exact turn
    p0_t3 = replay.snapshots[3].fast_move_progress[0]
    assert (p0_t3.elapsed, p0_t3.total, p0_t3.landed) == (3, 3, True)
    assert replay.snapshots[3].teams[1].active.hp < replay.snapshots[0].teams[1].active.hp
    assert replay.snapshots[3].teams[0].active.energy == bubble.energy_gain

    # Charged-move damage is logged on SHIELD_DECISION resolution steps
    all_logs = [entry for snap in replay.snapshots for entry in snap.log_entries]
    assert any("took " in entry and "damage" in entry for entry in all_logs)


def test_battle_screen_controls_layout_and_scrubbing():
    game_data = load_game_data()

    async def run() -> None:
        app = PogoLabApp(game_data=game_data)
        async with app.run_test(size=(140, 42)) as pilot:
            await pilot.pause()
            await pilot.press("2")
            await pilot.pause()

            screen = app.screen
            assert isinstance(screen, BattleScreen)
            assert screen.step_index == 0
            assert screen.is_playing is False
            assert screen.playback_speed == 1.0
            assert screen.show_log is False

            # Mirrored layout: P0 moves left of P0 side; P1 moves right of P1 side
            p0_moves = screen.query_one("#p0-moves")
            p0_side = screen.query_one("#p0-side")
            p1_side = screen.query_one("#p1-side")
            p1_moves = screen.query_one("#p1-moves")
            assert p0_moves.region.x < p0_side.region.x
            assert p0_side.region.x < p1_side.region.x
            assert p1_side.region.x < p1_moves.region.x

            # Active and bench sprites render as square-padded PIL images
            for sprite_id in (
                "#p0-active-sprite",
                "#p1-active-sprite",
                "#p0-bench-sprite-0",
                "#p0-bench-sprite-1",
                "#p1-bench-sprite-0",
                "#p1-bench-sprite-1",
            ):
                img_widget = screen.query_one(sprite_id, TerminalImage)
                assert img_widget.image is not None
                assert img_widget.image.width == img_widget.image.height

            # Bench order: pokemon 1 | pokemon 2 | switch timer
            p0_b0 = screen.query_one("#p0-bench-0")
            p0_b1 = screen.query_one("#p0-bench-1")
            p0_sw = screen.query_one("#p0-switch-timer")
            assert p0_b0.region.x < p0_b1.region.x < p0_sw.region.x

            # Step forward/backward with Right / Left arrows
            await pilot.press("right")
            await pilot.pause()
            assert screen.step_index == 1
            # Step 1 in Greedy vs Greedy starts fast moves on both sides
            assert screen.query_one("#p0-fast-move", FastMoveMeter).has_class("-active-move")
            assert screen.query_one("#p1-fast-move", FastMoveMeter).has_class("-active-move")

            await pilot.press("left")
            await pilot.pause()
            assert screen.step_index == 0
            assert not screen.query_one("#p0-fast-move", FastMoveMeter).has_class("-active-move")

            # Speed controls Up / Down across PLAYBACK_SPEEDS
            await pilot.press("up")
            await pilot.pause()
            assert screen.playback_speed == 2.0
            await pilot.press("up")
            await pilot.pause()
            assert screen.playback_speed == 4.0
            await pilot.press("up")  # clamped at max
            await pilot.pause()
            assert screen.playback_speed == PLAYBACK_SPEEDS[-1]
            for _ in range(len(PLAYBACK_SPEEDS)):
                await pilot.press("down")
            await pilot.pause()
            assert screen.playback_speed == PLAYBACK_SPEEDS[0]

            # Play / Pause toggle with p
            await pilot.press("p")
            await pilot.pause()
            assert screen.is_playing is True
            await pilot.press("p")
            await pilot.pause()
            assert screen.is_playing is False

            # Tab toggles the battle turn log panel
            log_panel = screen.query_one("#battle-log-panel", Vertical)
            assert not log_panel.has_class("-visible")
            await pilot.press("tab")
            await pilot.pause()
            assert screen.show_log is True
            assert log_panel.has_class("-visible")
            await pilot.press("tab")
            await pilot.pause()
            assert screen.show_log is False
            assert not log_panel.has_class("-visible")

            # Pressing r rolls a fresh matchup and resets step_index to 0
            await pilot.press("right")
            await pilot.pause()
            assert screen.step_index == 1
            first_seed = screen.replay.seed
            await pilot.press("r")
            await pilot.pause()
            assert screen.step_index == 0
            assert screen.replay.seed != first_seed

            # Esc returns to HomeScreen
            await pilot.press("escape")
            await pilot.pause()
            assert isinstance(app.screen, HomeScreen)

    asyncio.run(run())
