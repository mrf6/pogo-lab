"""Pure helper functions and presets shared by the TUI and future CLI commands."""

from __future__ import annotations

import re
from collections.abc import Mapping
from dataclasses import dataclass

from pogo_lab.data.classes import IVs, Species, Type


@dataclass(frozen=True, slots=True)
class League:
    """A PvP league CP-cap preset."""

    key: str
    name: str
    short_name: str
    cp_cap: int | None
    color: str

    @property
    def label(self) -> str:
        if self.cp_cap is None:
            return f"{self.name} (No CP Limit)"
        return f"{self.name} ({self.cp_cap} CP Limit)"


LEAGUES: tuple[League, ...] = (
    League(key="great", name="Great League", short_name="Great", cp_cap=1500, color="#3B82F6"),
    League(key="ultra", name="Ultra League", short_name="Ultra", cp_cap=2500, color="#EAB308"),
    League(key="master", name="Master League", short_name="Master", cp_cap=None, color="#A855F7"),
)


@dataclass(frozen=True, slots=True)
class IVFloorPreset:
    """Common Pokémon GO IV floor presets."""

    floor: int
    label: str


IV_FLOORS: tuple[IVFloorPreset, ...] = (
    IVFloorPreset(0, "Wild (0)"),
    IVFloorPreset(1, "Good Friend (1)"),
    IVFloorPreset(2, "Great Friend (2)"),
    IVFloorPreset(3, "Ultra Friend (3)"),
    IVFloorPreset(5, "Best Friend (5)"),
    IVFloorPreset(10, "Raid / Egg (10)"),
    IVFloorPreset(12, "Lucky (12)"),
)


TYPE_COLORS: dict[Type, str] = {
    Type.NORMAL: "#A8A77A",
    Type.FIRE: "#EE8130",
    Type.WATER: "#6390F0",
    Type.GRASS: "#7AC74C",
    Type.ELECTRIC: "#F7D02C",
    Type.ICE: "#96D9D6",
    Type.FIGHTING: "#C22E28",
    Type.POISON: "#A33EA1",
    Type.GROUND: "#E2BF65",
    Type.FLYING: "#A98FF3",
    Type.PSYCHIC: "#F95587",
    Type.BUG: "#A6B91A",
    Type.ROCK: "#B6A136",
    Type.GHOST: "#735797",
    Type.DRAGON: "#6F35FC",
    Type.DARK: "#705746",
    Type.STEEL: "#B7B7CE",
    Type.FAIRY: "#D685AD",
}


_IV_SPLIT_RE = re.compile(r"[\s/,-]+")


def search_species(
    query: str,
    species: Mapping[str, Species],
    *,
    limit: int = 8,
) -> list[Species]:
    """Return prefix-matching species ordered by exact match then alphabetical name."""
    cleaned = query.strip().lower()
    if not cleaned or limit <= 0:
        return []

    exact: list[Species] = []
    prefix: list[Species] = []

    for item in species.values():
        name_lower = item.name.lower()
        id_lower = item.id.lower()
        if cleaned == name_lower or cleaned == id_lower:
            exact.append(item)
        elif name_lower.startswith(cleaned) or id_lower.startswith(cleaned):
            prefix.append(item)

    exact.sort(key=lambda sp: sp.name.lower())
    prefix.sort(key=lambda sp: sp.name.lower())
    return (exact + prefix)[:limit]


def parse_lookup(raw: str) -> IVs | int | None:
    """Parse an IV spread (e.g. ``0/15/15``) or rank (e.g. ``#1`` or ``1``).

    Returns ``None`` for empty input and raises ``ValueError`` for invalid formats.
    """
    cleaned = raw.strip()
    if not cleaned:
        return None

    if cleaned.startswith("#"):
        rank_text = cleaned[1:].strip()
        if not rank_text.isdigit():
            raise ValueError(f"Invalid rank: {raw!r}")
        rank = int(rank_text)
        if rank < 1:
            raise ValueError("Rank must be >= 1")
        return rank

    if cleaned.isdigit():
        rank = int(cleaned)
        if rank < 1:
            raise ValueError("Rank must be >= 1")
        return rank

    parts = [part for part in _IV_SPLIT_RE.split(cleaned) if part]
    if len(parts) == 3 and all(part.isdigit() for part in parts):
        atk, defn, hp = (int(part) for part in parts)
        return IVs(attack=atk, defense=defn, hp=hp)

    raise ValueError("Use IVs like 0/15/15 or rank like #1")


def format_ivs(ivs: IVs) -> str:
    """Format an IV spread as ``atk/def/hp``."""
    return f"{ivs.attack}/{ivs.defense}/{ivs.hp}"


def format_level(level: float) -> str:
    """Format a Pokémon level consistently to one decimal place."""
    return f"{level:.1f}"
