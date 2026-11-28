"""Configured Pokémon instance model with CP-cap-aware spread resolution."""

from __future__ import annotations

from dataclasses import dataclass

from pogolab.data.classes import ChargedMove, FastMove, IVs, Species
from pogolab.rank_checker.ranking import get_spread_by_rank
from pogolab.rank_checker.stats import (
    EffectiveStats,
    calculate_cp,
    calculate_stats,
    max_level_for_cp,
    validate_level,
)


def _resolve_spread(
    species: Species,
    *,
    cp_cap: int | None,
    max_level: float,
    rank: int | None,
    ivs: IVs | None,
) -> tuple[float, IVs]:
    """Resolve ``(level, ivs)`` from ``rank`` (default 1) or ``ivs``.

    Uses ``cp_cap`` and ``max_level`` to select or bound the Pokémon's level.
    """
    validate_level(max_level)
    if rank is not None and ivs is not None:
        raise ValueError("Cannot specify both 'rank' and 'ivs'")

    if ivs is None:
        target_rank = 1 if rank is None else rank
        spread = get_spread_by_rank(
            species,
            target_rank,
            cp_cap=cp_cap,
            max_level=max_level,
        )
        return spread.level, spread.ivs

    resolved_level = max_level_for_cp(
        species.base_stats,
        ivs,
        cp_cap=cp_cap,
        max_level=max_level,
    )
    if resolved_level is None:
        raise ValueError(f"{species.id} with {ivs} exceeds cp_cap={cp_cap} even at level 1.0")
    return resolved_level, ivs


@dataclass(frozen=True, slots=True, init=False)
class Pokemon:
    """A configured Pokémon instance ready for battle simulation."""

    species: Species
    level: float
    ivs: IVs
    fast_move: FastMove | None
    charged_moves: tuple[ChargedMove, ...]
    is_shadow: bool

    def __init__(
        self,
        species: Species,
        *,
        cp_cap: int | None = 1500,
        max_level: float = 50.0,
        rank: int | None = None,
        ivs: IVs | None = None,
        fast_move: FastMove | None = None,
        charged_moves: tuple[ChargedMove, ...] = (),
        is_shadow: bool = False,
    ) -> None:
        if len(charged_moves) > 2:
            raise ValueError(f"Pokemon can have at most 2 charged moves, got {len(charged_moves)}")

        resolved_level, resolved_ivs = _resolve_spread(
            species,
            cp_cap=cp_cap,
            max_level=max_level,
            rank=rank,
            ivs=ivs,
        )
        object.__setattr__(self, "species", species)
        object.__setattr__(self, "level", resolved_level)
        object.__setattr__(self, "ivs", resolved_ivs)
        object.__setattr__(self, "fast_move", fast_move)
        object.__setattr__(self, "charged_moves", charged_moves)
        object.__setattr__(self, "is_shadow", is_shadow)

    @property
    def stats(self) -> EffectiveStats:
        """Effective attack, defense, stamina, and floored HP at this Pokémon's level and IVs."""
        return calculate_stats(self.species.base_stats, self.ivs, self.level)

    @property
    def cp(self) -> int:
        """Combat Power at this Pokémon's level and IVs."""
        return calculate_cp(self.species.base_stats, self.ivs, self.level)
