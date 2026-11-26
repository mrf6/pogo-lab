"""Loaders that construct typed Pokémon GO data objects from raw JSON files."""

from __future__ import annotations

import json
from collections.abc import Mapping
from pathlib import Path
from typing import Any

from pogo_lab.data.classes import (
    BaseStats,
    ChargedMove,
    FastMove,
    GameData,
    MoveBuff,
    Species,
    Type,
    TypeChart,
)

DEFAULT_DATA_DIR = Path(__file__).resolve().parents[3] / "data"


def _read_json(path: Path) -> dict[str, Any]:
    with path.open("r", encoding="utf-8") as handle:
        data = json.load(handle)
    if not isinstance(data, dict):
        raise ValueError(f"Expected JSON object in {path}, got {type(data).__name__}")
    return data


def load_type_chart(path: Path | None = None) -> TypeChart:
    """Load the 18x18 type effectiveness chart from JSON."""
    raw = _read_json(path or DEFAULT_DATA_DIR / "types.json")
    multipliers: dict[Type, dict[Type, float]] = {}
    for attack_key, matchups in raw.items():
        attack_type = Type(attack_key)
        multipliers[attack_type] = {
            Type(defender_key): float(value) for defender_key, value in matchups.items()
        }
    return TypeChart(multipliers=multipliers)


def load_fast_moves(path: Path | None = None) -> dict[str, FastMove]:
    """Load fast moves keyed by move ID."""
    raw = _read_json(path or DEFAULT_DATA_DIR / "fast_moves.json")
    moves: dict[str, FastMove] = {}
    for move_id, entry in raw.items():
        moves[move_id] = FastMove(
            id=move_id,
            name=str(entry["name"]),
            type=Type(entry["type"]),
            power=int(entry["power"]),
            energy_gain=int(entry["energy_gain"]),
            turns=int(entry["turns"]),
        )
    return moves


def load_charged_moves(path: Path | None = None) -> dict[str, ChargedMove]:
    """Load charged moves keyed by move ID."""
    raw = _read_json(path or DEFAULT_DATA_DIR / "charged_moves.json")
    moves: dict[str, ChargedMove] = {}
    for move_id, entry in raw.items():
        raw_buff = entry.get("buff")
        buff = (
            MoveBuff(
                user_attack=int(raw_buff["user_attack"]),
                user_defense=int(raw_buff["user_defense"]),
                opponent_attack=int(raw_buff["opponent_attack"]),
                opponent_defense=int(raw_buff["opponent_defense"]),
                probability=float(raw_buff["probability"]),
            )
            if raw_buff is not None
            else None
        )
        moves[move_id] = ChargedMove(
            id=move_id,
            name=str(entry["name"]),
            type=Type(entry["type"]),
            power=int(entry["power"]),
            energy_cost=int(entry["energy_cost"]),
            buff=buff,
        )
    return moves


def load_species(
    path: Path | None = None,
    *,
    fast_moves: Mapping[str, FastMove],
    charged_moves: Mapping[str, ChargedMove],
) -> dict[str, Species]:
    """Load Pokémon species keyed by species ID, resolving move references."""
    raw = _read_json(path or DEFAULT_DATA_DIR / "pokemon.json")
    species_map: dict[str, Species] = {}
    for species_id, entry in raw.items():
        raw_stats = entry["base_stats"]
        try:
            resolved_fast = tuple(fast_moves[move_id] for move_id in entry["fast_moves"])
        except KeyError as exc:
            raise KeyError(f"Unknown fast move {exc.args[0]!r} for species {species_id!r}") from exc
        try:
            resolved_charged = tuple(charged_moves[move_id] for move_id in entry["charged_moves"])
        except KeyError as exc:
            raise KeyError(
                f"Unknown charged move {exc.args[0]!r} for species {species_id!r}"
            ) from exc

        species_map[species_id] = Species(
            id=species_id,
            name=str(entry["name"]),
            types=tuple(Type(t) for t in entry["types"]),
            base_stats=BaseStats(
                attack=int(raw_stats["attack"]),
                defense=int(raw_stats["defense"]),
                hp=int(raw_stats["hp"]),
            ),
            fast_moves=resolved_fast,
            charged_moves=resolved_charged,
        )
    return species_map


def load_game_data(data_dir: Path | None = None) -> GameData:
    """Load type chart, fast moves, charged moves, and species from a data directory."""
    directory = data_dir or DEFAULT_DATA_DIR
    type_chart = load_type_chart(directory / "types.json")
    fast_moves = load_fast_moves(directory / "fast_moves.json")
    charged_moves = load_charged_moves(directory / "charged_moves.json")
    species = load_species(
        directory / "pokemon.json",
        fast_moves=fast_moves,
        charged_moves=charged_moves,
    )
    return GameData(
        type_chart=type_chart,
        fast_moves=fast_moves,
        charged_moves=charged_moves,
        species=species,
    )
