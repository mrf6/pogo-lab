"""Core Pokémon GO data types."""

from __future__ import annotations

from collections.abc import Mapping, Sequence
from dataclasses import dataclass
from enum import StrEnum


class Type(StrEnum):
    """Elemental types in Pokémon GO."""

    NORMAL = "normal"
    FIRE = "fire"
    WATER = "water"
    GRASS = "grass"
    ELECTRIC = "electric"
    ICE = "ice"
    FIGHTING = "fighting"
    POISON = "poison"
    GROUND = "ground"
    FLYING = "flying"
    PSYCHIC = "psychic"
    BUG = "bug"
    ROCK = "rock"
    GHOST = "ghost"
    DRAGON = "dragon"
    DARK = "dark"
    STEEL = "steel"
    FAIRY = "fairy"


@dataclass(frozen=True, slots=True)
class TypeChart:
    """Type effectiveness multiplier matrix."""

    multipliers: Mapping[Type, Mapping[Type, float]]

    def effectiveness(self, attack_type: Type, defender_types: Sequence[Type]) -> float:
        """Return the combined damage multiplier against one or more defending types."""
        multiplier = 1.0
        attack_row = self.multipliers[attack_type]
        for defender_type in defender_types:
            multiplier *= attack_row[defender_type]
        return multiplier


@dataclass(frozen=True, slots=True)
class BaseStats:
    """Base attack, defense, and HP stats for a Pokémon species."""

    attack: int
    defense: int
    hp: int


@dataclass(frozen=True, slots=True)
class IVs:
    """Individual values (0-15) for a specific Pokémon instance."""

    attack: int
    defense: int
    hp: int

    def __post_init__(self) -> None:
        for name, value in (("attack", self.attack), ("defense", self.defense), ("hp", self.hp)):
            if not 0 <= value <= 15:
                raise ValueError(f"IV {name} must be between 0 and 15, got {value}")


@dataclass(frozen=True, slots=True)
class MoveBuff:
    """Stat-stage buff/debuff effect for a charged move."""

    user_attack: int
    user_defense: int
    opponent_attack: int
    opponent_defense: int
    probability: float


@dataclass(frozen=True, slots=True)
class FastMove:
    """A PvP fast move."""

    id: str
    name: str
    type: Type
    power: int
    energy_gain: int
    turns: int


@dataclass(frozen=True, slots=True)
class ChargedMove:
    """A PvP charged move."""

    id: str
    name: str
    type: Type
    power: int
    energy_cost: int
    buff: MoveBuff | None = None


@dataclass(frozen=True, slots=True)
class Species:
    """Static definition of a Pokémon species and its learnable movepool."""

    id: str
    name: str
    types: tuple[Type, ...]
    base_stats: BaseStats
    fast_moves: tuple[FastMove, ...]
    charged_moves: tuple[ChargedMove, ...]


@dataclass(frozen=True, slots=True)
class Pokemon:
    """A configured Pokémon instance ready for ranking or battle simulation."""

    species: Species
    level: float
    ivs: IVs
    fast_move: FastMove
    charged_moves: tuple[ChargedMove, ...]
    is_shadow: bool = False

    def __post_init__(self) -> None:
        if not (1.0 <= self.level <= 51.0) or (self.level * 2) % 1 != 0:
            raise ValueError(f"Level must be between 1.0 and 51.0 in 0.5 steps, got {self.level}")
        if not 1 <= len(self.charged_moves) <= 2:
            raise ValueError(
                f"Pokemon must have 1 or 2 charged moves, got {len(self.charged_moves)}"
            )


@dataclass(frozen=True, slots=True)
class GameData:
    """Container for all loaded static Pokémon GO game data."""

    type_chart: TypeChart
    fast_moves: dict[str, FastMove]
    charged_moves: dict[str, ChargedMove]
    species: dict[str, Species]
