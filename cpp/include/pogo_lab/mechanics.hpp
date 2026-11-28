#pragma once

#include "pogo_lab/data.hpp"
#include "pogo_lab/state.hpp"

namespace pogo_lab::battle {

// Returns the stat multiplier for a stage in [-4, +4].
[[nodiscard]] float stat_stage_multiplier(int stage) noexcept;

// Computes PvP damage with full charge (1.0x):
// floor(0.5 * power * (atk / def) * stab * shadow * type_eff * 1.3) + 1.
[[nodiscard]] int calculate_damage(const PokemonData& attacker_data,
                                   const PokemonState& attacker_state,
                                   const PokemonData& defender_data,
                                   const PokemonState& defender_state,
                                   int move_power,
                                   ElementType move_type,
                                   const TypeChartData& type_chart) noexcept;

// Resolves Charge Move Priority (returns 0 or 1).
// Uses raw effective Attack only (ignores stat stages and Shadow multiplier).
[[nodiscard]] int resolve_cmp(const PokemonData& p0,
                              const PokemonData& p1,
                              SplitMix64& rng) noexcept;

// Rolls and applies a charged move's stat-stage buff/debuff.
// Returns true if the buff triggered.
bool apply_buff(const MoveBuffData& buff,
                PokemonState& attacker_state,
                PokemonState& defender_state,
                SplitMix64& rng) noexcept;

}  // namespace pogo_lab::battle
