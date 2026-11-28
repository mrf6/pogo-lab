"""PvP IV stat-product ranking engine."""

from __future__ import annotations

from collections.abc import Iterator
from dataclasses import dataclass
from functools import lru_cache

from pogolab.data.classes import BaseStats, IVs, Species
from pogolab.rank_checker.stats import (
    EffectiveStats,
    calculate_cp,
    calculate_stats,
    max_level_for_cp,
    validate_level,
)


@dataclass(frozen=True, slots=True)
class RankedSpread:
    """A single IV spread ranked by PvP stat product under a CP cap."""

    rank: int
    ivs: IVs
    level: float
    cp: int
    stats: EffectiveStats
    stat_product: float
    stat_product_pct: float


@dataclass(frozen=True, slots=True)
class RankTable:
    """Complete ranked IV table for a species under specific league constraints."""

    species_id: str
    cp_cap: int | None
    max_level: float
    iv_floor: int
    spreads: tuple[RankedSpread, ...]
    _by_ivs: dict[IVs, RankedSpread]

    def __len__(self) -> int:
        return len(self.spreads)

    def __iter__(self) -> Iterator[RankedSpread]:
        return iter(self.spreads)

    def by_rank(self, rank: int) -> RankedSpread:
        """Return the spread at 1-indexed ``rank``."""
        if not 1 <= rank <= len(self.spreads):
            raise ValueError(
                f"Rank must be between 1 and {len(self.spreads)} for {self.species_id} "
                f"(cp_cap={self.cp_cap}, max_level={self.max_level}, iv_floor={self.iv_floor}), "
                f"got {rank}"
            )
        return self.spreads[rank - 1]

    def by_ivs(self, ivs: IVs) -> RankedSpread:
        """Return the ranked spread for ``ivs``."""
        spread = self._by_ivs.get(ivs)
        if spread is None:
            raise ValueError(
                f"IVs {ivs} are not eligible for {self.species_id} "
                f"(cp_cap={self.cp_cap}, max_level={self.max_level}, iv_floor={self.iv_floor})"
            )
        return spread


@lru_cache(maxsize=256)
def _build_rank_table(
    species_id: str,
    base_stats: BaseStats,
    cp_cap: int | None,
    max_level: float,
    iv_floor: int,
) -> RankTable:
    validate_level(max_level)
    if not 0 <= iv_floor <= 15:
        raise ValueError(f"iv_floor must be between 0 and 15, got {iv_floor}")

    candidates: list[tuple[float, int, int, int, int, IVs, float, EffectiveStats]] = []
    for atk in range(iv_floor, 16):
        for defn in range(iv_floor, 16):
            for hp in range(iv_floor, 16):
                ivs = IVs(attack=atk, defense=defn, hp=hp)
                level = max_level_for_cp(
                    base_stats,
                    ivs,
                    cp_cap=cp_cap,
                    max_level=max_level,
                )
                if level is None:
                    continue
                stats = calculate_stats(base_stats, ivs, level)
                cp = calculate_cp(base_stats, ivs, level)
                candidates.append((stats.stat_product, cp, atk, defn, hp, ivs, level, stats))

    candidates.sort(key=lambda row: (row[0], row[1], row[2], row[3], row[4]), reverse=True)

    top_stat_product = candidates[0][0] if candidates else 0.0
    spreads: list[RankedSpread] = []
    by_ivs: dict[IVs, RankedSpread] = {}

    for index, (stat_product, cp, _, _, _, ivs, level, stats) in enumerate(candidates, start=1):
        pct = (stat_product / top_stat_product) * 100.0 if top_stat_product > 0 else 0.0
        spread = RankedSpread(
            rank=index,
            ivs=ivs,
            level=level,
            cp=cp,
            stats=stats,
            stat_product=stat_product,
            stat_product_pct=pct,
        )
        spreads.append(spread)
        by_ivs[ivs] = spread

    return RankTable(
        species_id=species_id,
        cp_cap=cp_cap,
        max_level=max_level,
        iv_floor=iv_floor,
        spreads=tuple(spreads),
        _by_ivs=by_ivs,
    )


def rank_species(
    species: Species,
    *,
    cp_cap: int | None = 1500,
    max_level: float = 50.0,
    iv_floor: int = 0,
) -> RankTable:
    """Return the cached PvP IV ``RankTable`` for ``species``."""
    return _build_rank_table(
        species.id,
        species.base_stats,
        cp_cap,
        max_level,
        iv_floor,
    )


def get_spread_by_rank(
    species: Species,
    rank: int,
    *,
    cp_cap: int | None = 1500,
    max_level: float = 50.0,
    iv_floor: int = 0,
) -> RankedSpread:
    """Look up the IVs, level, CP, and stats for ``species`` at 1-indexed ``rank``."""
    return rank_species(
        species,
        cp_cap=cp_cap,
        max_level=max_level,
        iv_floor=iv_floor,
    ).by_rank(rank)


def get_rank_by_ivs(
    species: Species,
    ivs: IVs,
    *,
    cp_cap: int | None = 1500,
    max_level: float = 50.0,
    iv_floor: int = 0,
) -> RankedSpread:
    """Look up the rank, max legal level, CP, and stats for ``species`` with ``ivs``."""
    return rank_species(
        species,
        cp_cap=cp_cap,
        max_level=max_level,
        iv_floor=iv_floor,
    ).by_ivs(ivs)
