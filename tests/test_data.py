"""Tests for static Pokémon GO data files, models, and loaders."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from pogolab import Pokemon
from pogolab.data import (
    IVs,
    Type,
    load_game_data,
    load_species,
)


def test_load_game_data_end_to_end():
    game_data = load_game_data()

    assert len(game_data.type_chart.multipliers) == 18
    assert "charging_air_slash" in game_data.fast_moves
    assert "charging_psycho_cut" in game_data.fast_moves
    for alt_id in ("aegislash_blade", "morpeko_hangry", "minior_meteor"):
        assert alt_id in game_data.species
    assert (
        game_data.fast_moves["charging_psycho_cut"]
        in game_data.species["aegislash_shield"].fast_moves
    )


def test_type_chart_effectiveness():
    chart = load_game_data().type_chart

    # Single-type matchups
    assert chart.effectiveness(Type.FIRE, (Type.GRASS,)) == pytest.approx(1.6)
    assert chart.effectiveness(Type.NORMAL, (Type.GHOST,)) == pytest.approx(0.390625)

    # Dual-type matchups (4x weak and immunity + resistance)
    assert chart.effectiveness(Type.GROUND, (Type.POISON, Type.STEEL)) == pytest.approx(1.6 * 1.6)
    assert chart.effectiveness(Type.WATER, (Type.FIRE, Type.GROUND)) == pytest.approx(1.6 * 1.6)
    assert chart.effectiveness(Type.FIRE, (Type.GRASS, Type.WATER)) == pytest.approx(1.6 * 0.625)


def test_charged_move_buffs():
    charged_moves = load_game_data().charged_moves

    # Opponent debuff
    acid_spray = charged_moves["acid_spray"]
    assert acid_spray.buff is not None
    assert acid_spray.buff.opponent_defense == -2
    assert acid_spray.buff.user_attack == 0
    assert acid_spray.buff.probability == pytest.approx(1.0)

    # Self buff
    aeroblast = charged_moves["aeroblast"]
    assert aeroblast.buff is not None
    assert aeroblast.buff.user_attack == 2
    assert aeroblast.buff.probability == pytest.approx(0.125)

    # Both self buff and opponent debuff (Obstruct)
    obstruct = charged_moves["obstruct"]
    assert obstruct.buff is not None
    assert obstruct.buff.user_defense == 1
    assert obstruct.buff.opponent_defense == -1
    assert obstruct.buff.probability == pytest.approx(1.0)

    # No buff
    assert charged_moves["acrobatics"].buff is None


def test_species_and_pokemon_instance():
    game_data = load_game_data()
    azumarill = game_data.species["azumarill"]

    assert azumarill.name == "Azumarill"
    assert azumarill.types == (Type.WATER, Type.FAIRY)
    assert azumarill.base_stats.hp == 225
    assert game_data.fast_moves["bubble"] in azumarill.fast_moves
    assert game_data.charged_moves["ice_beam"] in azumarill.charged_moves

    # Mono-type species should not contain "none"
    blastoise = game_data.species["blastoise"]
    assert blastoise.types == (Type.WATER,)

    mon = Pokemon(
        species=azumarill,
        ivs=IVs(attack=0, defense=15, hp=15),
        fast_move=game_data.fast_moves["bubble"],
        charged_moves=(
            game_data.charged_moves["ice_beam"],
            game_data.charged_moves["play_rough"],
        ),
    )
    assert mon.species.id == "azumarill"
    assert mon.level == 45.5
    assert mon.is_shadow is False


def test_validation_errors(tmp_path: Path):
    with pytest.raises(ValueError, match="IV attack"):
        IVs(attack=16, defense=10, hp=10)

    game_data = load_game_data()
    azumarill = game_data.species["azumarill"]

    with pytest.raises(ValueError, match="Level"):
        Pokemon(
            species=azumarill,
            max_level=45.25,
            ivs=IVs(0, 15, 15),
            fast_move=game_data.fast_moves["bubble"],
            charged_moves=(game_data.charged_moves["ice_beam"],),
        )

    with pytest.raises(ValueError, match="at most 2 charged moves"):
        Pokemon(
            species=azumarill,
            ivs=IVs(0, 15, 15),
            fast_move=game_data.fast_moves["bubble"],
            charged_moves=(
                game_data.charged_moves["ice_beam"],
                game_data.charged_moves["play_rough"],
                game_data.charged_moves["hydro_pump"],
            ),
        )

    bad_pokemon = tmp_path / "pokemon.json"
    bad_pokemon.write_text(
        json.dumps(
            {
                "testmon": {
                    "name": "Testmon",
                    "types": ["normal"],
                    "base_stats": {"attack": 100, "defense": 100, "hp": 100},
                    "fast_moves": ["nonexistent_move"],
                    "charged_moves": ["acrobatics"],
                }
            }
        ),
        encoding="utf-8",
    )
    with pytest.raises(KeyError, match="nonexistent_move"):
        load_species(
            bad_pokemon,
            fast_moves=game_data.fast_moves,
            charged_moves=game_data.charged_moves,
        )
