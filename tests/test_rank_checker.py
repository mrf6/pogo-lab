"""Tests for PvP stat calculations, IV rank checking, and Pokemon constructors."""

from __future__ import annotations

import pytest

from pogo_lab import IVs, Pokemon, load_game_data
from pogo_lab.data import BaseStats
from pogo_lab.rank_checker import (
    CP_MULTIPLIERS,
    calculate_cp,
    calculate_stats,
    get_rank_by_ivs,
    get_spread_by_rank,
    max_level_for_cp,
    rank_species,
)


def test_cpm_table_covers_all_half_levels():
    assert len(CP_MULTIPLIERS) == 101
    assert 1.0 in CP_MULTIPLIERS
    assert 50.0 in CP_MULTIPLIERS
    assert 50.5 in CP_MULTIPLIERS
    assert 51.0 in CP_MULTIPLIERS
    values = list(CP_MULTIPLIERS.values())
    assert values == sorted(values)


def test_cp_and_hp_floors():
    tiny = BaseStats(attack=10, defense=10, hp=10)
    stats = calculate_stats(tiny, IVs(0, 0, 0), level=1.0)
    assert stats.hp == 10
    assert calculate_cp(tiny, IVs(0, 0, 0), level=1.0) == 10


def test_azumarill_great_league_rank_one():
    azumarill = load_game_data().species["azumarill"]

    rank1 = get_spread_by_rank(azumarill, 1, cp_cap=1500, max_level=50.0)
    assert rank1.rank == 1
    assert rank1.ivs == IVs(attack=0, defense=15, hp=15)
    assert rank1.level == 45.5
    assert rank1.cp == 1499
    assert rank1.stat_product_pct == pytest.approx(100.0)

    by_ivs = get_rank_by_ivs(azumarill, IVs(0, 15, 15), cp_cap=1500, max_level=50.0)
    assert by_ivs == rank1


def test_master_league_and_best_buddy():
    game_data = load_game_data()
    dragonite = game_data.species["dragonite"]

    ml_50 = get_spread_by_rank(dragonite, 1, cp_cap=None, max_level=50.0)
    assert ml_50.ivs == IVs(15, 15, 15)
    assert ml_50.level == 50.0

    ml_51 = get_spread_by_rank(dragonite, 1, cp_cap=None, max_level=51.0)
    assert ml_51.ivs == IVs(15, 15, 15)
    assert ml_51.level == 51.0
    assert ml_51.cp > ml_50.cp

    # Umbreon maxes under 2500 CP, so Best Buddy (L51) strictly improves Ultra League rank 1
    umbreon = game_data.species["umbreon"]
    ul_50 = get_spread_by_rank(umbreon, 1, cp_cap=2500, max_level=50.0)
    ul_51 = get_spread_by_rank(umbreon, 1, cp_cap=2500, max_level=51.0)
    assert ul_51.stat_product > ul_50.stat_product
    assert ul_51.level == 51.0


def test_rank_table_round_trip_and_iv_floor():
    dragonite = load_game_data().species["dragonite"]

    table = rank_species(dragonite, cp_cap=2500, max_level=50.0)
    assert len(table) == 4096
    for rank in (1, 10, 500, 4096):
        spread = table.by_rank(rank)
        assert spread.rank == rank
        assert spread.cp <= 2500
        assert table.by_ivs(spread.ivs) == spread

    raid_table = rank_species(dragonite, cp_cap=2500, max_level=50.0, iv_floor=10)
    assert len(raid_table) == 6**3
    for spread in raid_table:
        assert spread.ivs.attack >= 10
        assert spread.ivs.defense >= 10
        assert spread.ivs.hp >= 10

    with pytest.raises(ValueError, match="not eligible"):
        raid_table.by_ivs(IVs(0, 15, 15))

    with pytest.raises(ValueError, match="Rank must be between"):
        table.by_rank(0)

    with pytest.raises(ValueError, match="Rank must be between"):
        table.by_rank(4097)


def test_max_level_ineligible_for_cp_cap():
    dragonite = load_game_data().species["dragonite"]
    assert max_level_for_cp(dragonite.base_stats, IVs(15, 15, 15), cp_cap=10) is None


def test_pokemon_construction_and_validation():
    game_data = load_game_data()
    azumarill = game_data.species["azumarill"]
    charizard = game_data.species["charizard"]
    dragonite = game_data.species["dragonite"]

    # Default construction: Great League rank 1, no moves
    default_azu = Pokemon(azumarill)
    assert default_azu.level == 45.5
    assert default_azu.ivs == IVs(0, 15, 15)
    assert default_azu.fast_move is None
    assert default_azu.charged_moves == ()
    assert default_azu.cp == 1499
    assert default_azu.stats == calculate_stats(azumarill.base_stats, IVs(0, 15, 15), 45.5)

    # Explicit CP cap + rank
    ul_charizard = Pokemon(charizard, cp_cap=2500, rank=10)
    expected_ul = get_spread_by_rank(charizard, 10, cp_cap=2500)
    assert ul_charizard.ivs == expected_ul.ivs
    assert ul_charizard.level == expected_ul.level
    assert ul_charizard.cp <= 2500

    # Explicit IVs with auto-selected max legal level and independent moves
    by_ivs = Pokemon(
        azumarill,
        cp_cap=1500,
        ivs=IVs(0, 15, 15),
        fast_move=game_data.fast_moves["bubble"],
        charged_moves=(game_data.charged_moves["ice_beam"],),
    )
    assert by_ivs.level == 45.5
    assert by_ivs.cp == 1499
    assert by_ivs.fast_move == game_data.fast_moves["bubble"]
    assert len(by_ivs.charged_moves) == 1

    # Master League Best Buddy
    ml_dragonite = Pokemon(dragonite, cp_cap=None, max_level=51.0)
    assert ml_dragonite.ivs == IVs(15, 15, 15)
    assert ml_dragonite.level == 51.0
    assert ml_dragonite.cp > 2500

    # Specifying both rank and ivs raises ValueError
    with pytest.raises(ValueError, match="Cannot specify both 'rank' and 'ivs'"):
        Pokemon(azumarill, rank=1, ivs=IVs(0, 15, 15))

    # Ineligible CP cap raises ValueError
    with pytest.raises(ValueError, match="exceeds cp_cap=10"):
        Pokemon(dragonite, cp_cap=10, ivs=IVs(15, 15, 15))
