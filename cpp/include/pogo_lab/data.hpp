#pragma once

#include <array>
#include <cstdint>

#include "pogo_lab/types.hpp"

namespace pogo_lab::battle {

struct MoveBuffData {
    int8_t user_attack = 0;
    int8_t user_defense = 0;
    int8_t opponent_attack = 0;
    int8_t opponent_defense = 0;
    float probability = 0.0f;

    [[nodiscard]] constexpr bool has_effect() const noexcept {
        return probability > 0.0f &&
               (user_attack != 0 || user_defense != 0 || opponent_attack != 0 ||
                opponent_defense != 0);
    }
};

struct FastMoveData {
    ElementType type = ElementType::Normal;
    int power = 0;
    int energy_gain = 0;
    int turns = 1;
};

struct ChargedMoveData {
    ElementType type = ElementType::Normal;
    int power = 0;
    int energy_cost = 35;
    MoveBuffData buff{};
};

struct PokemonData {
    float attack = 100.0f;
    float defense = 100.0f;
    int max_hp = 100;
    std::array<ElementType, 2> types = {ElementType::Normal, ElementType::None};
    bool is_shadow = false;
    FastMoveData fast_move{};
    std::array<ChargedMoveData, kMaxChargedMoves> charged_moves{};
    int num_charged_moves = 0;

    [[nodiscard]] constexpr bool has_type(ElementType t) const noexcept {
        return t != ElementType::None && (types[0] == t || types[1] == t);
    }
};

struct TypeChartData {
    std::array<std::array<float, kNumTypes>, kNumTypes> multipliers{};

    TypeChartData() {
        for (auto& row : multipliers) {
            row.fill(1.0f);
        }
    }

    [[nodiscard]] float effectiveness(ElementType attack_type,
                                      const std::array<ElementType, 2>& defender_types) const noexcept {
        if (attack_type == ElementType::None) {
            return 1.0f;
        }
        const auto atk_idx = static_cast<std::size_t>(attack_type);
        float mult = 1.0f;
        for (ElementType def_type : defender_types) {
            if (def_type != ElementType::None) {
                mult *= multipliers[atk_idx][static_cast<std::size_t>(def_type)];
            }
        }
        return mult;
    }
};

}  // namespace pogo_lab::battle
