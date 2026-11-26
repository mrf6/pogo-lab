"""Configured Pokémon instance model with rank- and IV-based constructors."""

from __future__ import annotations

from dataclasses import dataclass

from pogo_lab.data.classes import ChargedMove, FastMove, IVs, Species
from pogo_lab.rank_checker.ranking import RankedSpread, get_rank_by_ivs, get_spread_by_rank
from pogo_lab.rank_checker.stats import (
    EffectiveStats,
    calculate_cp,
    calculate_stats,
    max_level_for_cp,
    validate_level,
)


@dataclass(frozen=True, slots=True)
class Pokemon:
    """A configured Pokémon instance ready for ranking or battle simulation."""

    species: Species
    level: float
    ivs: IVs
    fast_move: FastMove | None = None
    charged_moves: tuple[ChargedMove, ...] = ()
    is_shadow: bool = False

    def __post_init__(self) -> None:
        validate_level(self.level)
        if len(self.charged_moves) > 2:
            raise ValueError(
                f"Pokemon can have at most 2 charged moves, got {len(self.charged_moves)}"
            )

    @classmethod
    def from_rank(
        cls,
        species: Species,
        rank: int = 1,
        *,
        cp_cap: int | None = 1500,
        max_level: float = 50.0,
        iv_floor: int = 0,
        fast_move: FastMove | None = None,
        charged_moves: tuple[ChargedMove, ...] = (),
        is_shadow: bool = False,
    ) -> Pokemon:
        """Create a Pokémon whose level and IVs correspond to a PvP stat-product ``rank``."""
        spread = get_spread_by_rank(
            species,
            rank,
            cp_cap=cp_cap,
            max_level=max_level,
            iv_floor=iv_floor,
        )
        return cls(
            species=species,
            level=spread.level,
            ivs=spread.ivs,
            fast_move=fast_move,
            charged_moves=charged_moves,
            is_shadow=is_shadow,
        )

    @classmethod
    def from_ivs(
        cls,
        species: Species,
        ivs: IVs,
        *,
        cp_cap: int | None = 1500,
        max_level: float = 50.0,
        fast_move: FastMove | None = None,
        charged_moves: tuple[ChargedMove, ...] = (),
        is_shadow: bool = False,
    ) -> Pokemon:
        """Create a Pokémon at the highest legal level for ``ivs`` under ``cp_cap``."""
        level = max_level_for_cp(
            species.base_stats,
            ivs,
            cp_cap=cp_cap,
            max_level=max_level,
        )
        if level is None:
            raise ValueError(f"{species.id} with {ivs} exceeds cp_cap={cp_cap} even at level 1.0")
        return cls(
            species=species,
            level=level,
            ivs=ivs,
            fast_move=fast_move,
            charged_moves=charged_moves,
            is_shadow=is_shadow,
        )

    @property
    def stats(self) -> EffectiveStats:
        """Effective attack, defense, stamina, and floored HP at this Pokémon's level and IVs."""
        return calculate_stats(self.species.base_stats, self.ivs, self.level)

    @property
    def cp(self) -> int:
        """Combat Power at this Pokémon's level and IVs."""
        return calculate_cp(self.species.base_stats, self.ivs, self.level)

    def rank(
        self,
        *,
        cp_cap: int | None = 1500,
        max_level: float = 50.0,
        iv_floor: int = 0,
    ) -> RankedSpread:
        """Return this Pokémon's IV ranking under the specified league constraints."""
        return get_rank_by_ivs(
            self.species,
            self.ivs,
            cp_cap=cp_cap,
            max_level=max_level,
            iv_floor=iv_floor,
        )
