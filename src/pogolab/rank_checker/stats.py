"""Pokémon GO CPM table, effective stats, and CP calculations."""

from __future__ import annotations

import math
from dataclasses import dataclass

from pogolab.data.classes import BaseStats, IVs

# Official Pokémon GO CP Multipliers for levels 1.0 through 51.0 (0.5 increments)
_CPM_VALUES: tuple[float, ...] = (
    0.0939999967813491,
    0.135137430784308,
    0.166397869586944,
    0.192650914456886,
    0.215732470154762,
    0.236572655026622,
    0.255720049142837,
    0.273530381100769,
    0.290249884128570,
    0.306057381335773,
    0.321087598800659,
    0.335445032295077,
    0.349212676286697,
    0.362457748778790,
    0.375235587358474,
    0.387592411085168,
    0.399567276239395,
    0.411193549517250,
    0.422500014305114,
    0.432926413410414,
    0.443107545375824,
    0.453059953871985,
    0.462798386812210,
    0.472336077786704,
    0.481684952974319,
    0.490855810259008,
    0.499858438968658,
    0.508701756943992,
    0.517393946647644,
    0.525942508771329,
    0.534354329109191,
    0.542635762230353,
    0.550792694091796,
    0.558830599438087,
    0.566754519939422,
    0.574569148039264,
    0.582278907299041,
    0.589887911977272,
    0.597400009632110,
    0.604823657502073,
    0.612157285213470,
    0.619404110566050,
    0.626567125320434,
    0.633649181622743,
    0.640652954578399,
    0.647580963301656,
    0.654435634613037,
    0.661219263506722,
    0.667934000492096,
    0.674581899290818,
    0.681164920330047,
    0.687684905887771,
    0.694143652915954,
    0.700542893277978,
    0.706884205341339,
    0.713169102333341,
    0.719399094581604,
    0.725575616972598,
    0.731700003147125,
    0.734741011137376,
    0.737769484519958,
    0.740785574597326,
    0.743789434432983,
    0.746781208702482,
    0.749761044979095,
    0.752729105305821,
    0.755685508251190,
    0.758630366519684,
    0.761563837528228,
    0.764486065255226,
    0.767397165298461,
    0.770297273971590,
    0.773186504840850,
    0.776064945942412,
    0.778932750225067,
    0.781790064808426,
    0.784636974334716,
    0.787473583646825,
    0.790300011634826,
    0.792803950958807,
    0.795300006866455,
    0.797803921486970,
    0.800300002098083,
    0.802803892322847,
    0.805299997329711,
    0.807803863460723,
    0.810299992561340,
    0.812803834895026,
    0.815299987792968,
    0.817803806620319,
    0.820299983024597,
    0.822803778631297,
    0.825299978256225,
    0.827803750922782,
    0.830299973487854,
    0.832803753381377,
    0.835300028324127,
    0.837803755931569,
    0.840300023555755,
    0.842803729034748,
    0.845300018787384,
)

LEVELS: tuple[float, ...] = tuple(1.0 + 0.5 * i for i in range(len(_CPM_VALUES)))
CP_MULTIPLIERS: dict[float, float] = dict(zip(LEVELS, _CPM_VALUES, strict=True))

MIN_LEVEL: float = 1.0
MAX_LEVEL: float = 51.0


def validate_level(level: float, *, max_level: float = MAX_LEVEL) -> None:
    """Validate that a Pokémon level is in [1.0, max_level] in 0.5 steps."""
    if not (MIN_LEVEL <= level <= max_level) or (level * 2) % 1 != 0:
        raise ValueError(
            f"Level must be between {MIN_LEVEL} and {max_level} in 0.5 steps, got {level}"
        )


@dataclass(frozen=True, slots=True)
class EffectiveStats:
    """Computed battle stats for a Pokémon at a given level and IV spread."""

    attack: float
    defense: float
    stamina: float
    hp: int

    @property
    def stat_product(self) -> float:
        """Return the PvP stat product (attack * defense * floored HP)."""
        return self.attack * self.defense * self.hp


def calculate_stats(base_stats: BaseStats, ivs: IVs, level: float) -> EffectiveStats:
    """Calculate effective attack, defense, stamina, and floored HP at ``level``."""
    validate_level(level)
    cpm = CP_MULTIPLIERS[level]
    attack = (base_stats.attack + ivs.attack) * cpm
    defense = (base_stats.defense + ivs.defense) * cpm
    stamina = (base_stats.hp + ivs.hp) * cpm
    hp = max(10, math.floor(stamina))
    return EffectiveStats(attack=attack, defense=defense, stamina=stamina, hp=hp)


def calculate_cp(base_stats: BaseStats, ivs: IVs, level: float) -> int:
    """Calculate Pokémon GO CP at ``level`` (floored, minimum 10)."""
    validate_level(level)
    cpm = CP_MULTIPLIERS[level]
    attack = (base_stats.attack + ivs.attack) * cpm
    defense = (base_stats.defense + ivs.defense) * cpm
    stamina = (base_stats.hp + ivs.hp) * cpm
    return max(10, math.floor(attack * math.sqrt(defense) * math.sqrt(stamina) / 10.0))


def max_level_for_cp(
    base_stats: BaseStats,
    ivs: IVs,
    *,
    cp_cap: int | None = 1500,
    max_level: float = 50.0,
) -> float | None:
    """Return the highest half-level <= ``max_level`` whose CP does not exceed ``cp_cap``.

    If ``cp_cap`` is ``None`` (Master League), returns ``max_level``.
    Returns ``None`` if even level 1.0 exceeds ``cp_cap``.
    """
    validate_level(max_level)
    if cp_cap is None:
        return max_level
    if cp_cap < 10:
        return None

    # Precompute the level-independent factor so each binary-search step is just one multiply.
    base_cp_factor = (
        (base_stats.attack + ivs.attack)
        * math.sqrt(base_stats.defense + ivs.defense)
        * math.sqrt(base_stats.hp + ivs.hp)
        / 10.0
    )

    lo = 0
    hi = int((max_level - MIN_LEVEL) * 2)
    best = -1

    while lo <= hi:
        mid = (lo + hi) // 2
        cpm = _CPM_VALUES[mid]
        cp = max(10, math.floor(base_cp_factor * cpm * cpm))
        if cp <= cp_cap:
            best = mid
            lo = mid + 1
        else:
            hi = mid - 1

    return LEVELS[best] if best >= 0 else None
