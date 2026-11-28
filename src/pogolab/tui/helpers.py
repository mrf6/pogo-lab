"""Pure helper functions and presets shared by the TUI and future CLI commands."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass

from pogolab.data.classes import IVs, Species, Type


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
    IVFloorPreset(0, "0 (Wild Catch)"),
    IVFloorPreset(1, "1 (Good Friend)"),
    IVFloorPreset(2, "2 (Great Friend)"),
    IVFloorPreset(3, "3 (Ultra Friend)"),
    IVFloorPreset(4, "4 (Weather Boost)"),
    IVFloorPreset(5, "5 (Best Friend)"),
    IVFloorPreset(6, "6 (Shadow Raid)"),
    IVFloorPreset(10, "10 (Raid / Egg)"),
    IVFloorPreset(12, "12 (Lucky)"),
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
    """Parse an IV spread (``0/15/15``) or rank (``123``).

    Returns ``None`` for empty input and raises ``ValueError`` for invalid formats.
    """
    cleaned = raw.strip()
    if not cleaned:
        return None

    if cleaned.isdigit():
        rank = int(cleaned)
        if rank < 1:
            raise ValueError("Rank must be >= 1")
        return rank

    if "/" in cleaned:
        parts = cleaned.split("/")
        if len(parts) == 3 and all(part.isdigit() for part in parts):
            atk, defn, hp = (int(part) for part in parts)
            if not (0 <= atk <= 15 and 0 <= defn <= 15 and 0 <= hp <= 15):
                raise ValueError("IVs must be between 0 and 15")
            return IVs(attack=atk, defense=defn, hp=hp)

    raise ValueError("Use IVs (e.g. 0/15/15) or Rank (e.g. 123)")


def rank_color(rank: int, total: int) -> str:
    """Return a hex color scaling smoothly from green -> yellow -> red across ``1..total``."""
    if total <= 1:
        t = 0.0
    else:
        t = min(1.0, max(0.0, (rank - 1) / (total - 1)))

    # Green (#22C55E) -> Yellow (#EAB308) -> Red (#EF4444)
    if t <= 0.5:
        u = t * 2.0
        r = round(34 + (234 - 34) * u)
        g = round(197 + (179 - 197) * u)
        b = round(94 + (8 - 94) * u)
    else:
        u = (t - 0.5) * 2.0
        r = round(234 + (239 - 234) * u)
        g = round(179 + (68 - 179) * u)
        b = round(8 + (68 - 8) * u)
    return f"#{r:02X}{g:02X}{b:02X}"


def format_ivs(ivs: IVs) -> str:
    """Format an IV spread as ``atk/def/hp``."""
    return f"{ivs.attack}/{ivs.defense}/{ivs.hp}"


def format_level(level: float) -> str:
    """Format a Pokémon level consistently to one decimal place."""
    return f"{level:.1f}"
