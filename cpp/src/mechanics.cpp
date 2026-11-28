#include "pogolab/mechanics.hpp"

#include <algorithm>
#include <cmath>

namespace pogolab::battle {

float stat_stage_multiplier(int stage) noexcept {
    const int clamped = std::clamp(stage, kMinStatStage, kMaxStatStage);
    if (clamped >= 0) {
        return static_cast<float>(4 + clamped) / 4.0f;
    }
    return 4.0f / static_cast<float>(4 - clamped);
}

int calculate_damage(const PokemonData& attacker_data,
                     const PokemonState& attacker_state,
                     const PokemonData& defender_data,
                     const PokemonState& defender_state,
                     int move_power,
                     ElementType move_type,
                     const TypeChartData& type_chart) noexcept {
    const float atk_shadow = attacker_data.is_shadow ? kShadowAttackMultiplier : 1.0f;
    const float def_shadow = defender_data.is_shadow ? kShadowDefenseMultiplier : 1.0f;

    const float eff_atk =
        attacker_data.attack * stat_stage_multiplier(attacker_state.atk_stage) * atk_shadow;
    const float eff_def =
        defender_data.defense * stat_stage_multiplier(defender_state.def_stage) * def_shadow;

    const float stab = attacker_data.has_type(move_type) ? kStabMultiplier : 1.0f;
    const float type_eff = type_chart.effectiveness(move_type, defender_data.types);

    const float raw = 0.5f * static_cast<float>(move_power) * (eff_atk / eff_def) * stab *
                      type_eff * kPvpBonusMultiplier;
    return static_cast<int>(std::floor(raw)) + 1;
}

int resolve_cmp(const PokemonData& p0, const PokemonData& p1, SplitMix64& rng) noexcept {
    // CMP uses base effective Attack only (excludes stat stages and Shadow bonus).
    if (p0.attack > p1.attack) {
        return 0;
    }
    if (p1.attack > p0.attack) {
        return 1;
    }
    return rng.next_bool() ? 1 : 0;
}

bool apply_buff(const MoveBuffData& buff,
                PokemonState& attacker_state,
                PokemonState& defender_state,
                SplitMix64& rng) noexcept {
    if (!buff.has_effect()) {
        return false;
    }
    if (buff.probability < 1.0f && rng.next_float() >= buff.probability) {
        return false;
    }

    auto clamp_stage = [](int value) -> int8_t {
        return static_cast<int8_t>(std::clamp(value, kMinStatStage, kMaxStatStage));
    };

    attacker_state.atk_stage = clamp_stage(attacker_state.atk_stage + buff.user_attack);
    attacker_state.def_stage = clamp_stage(attacker_state.def_stage + buff.user_defense);
    defender_state.atk_stage = clamp_stage(defender_state.atk_stage + buff.opponent_attack);
    defender_state.def_stage = clamp_stage(defender_state.def_stage + buff.opponent_defense);
    return true;
}

}  // namespace pogolab::battle
