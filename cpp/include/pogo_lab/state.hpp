#pragma once

#include <array>
#include <cstdint>

#include "pogo_lab/types.hpp"

namespace pogo_lab::battle {

struct SplitMix64 {
    std::uint64_t state = 0x9e3779b97f4a7c15ULL;

    explicit constexpr SplitMix64(std::uint64_t seed = 0) noexcept
        : state(seed != 0 ? seed : 0x9e3779b97f4a7c15ULL) {}

    [[nodiscard]] constexpr std::uint64_t next_u64() noexcept {
        std::uint64_t z = (state += 0x9e3779b97f4a7c15ULL);
        z = (z ^ (z >> 30)) * 0xbf58476d1ce4e5b9ULL;
        z = (z ^ (z >> 27)) * 0x94d049bb133111ebULL;
        return z ^ (z >> 31);
    }

    // Returns a uniform float in [0.0, 1.0).
    [[nodiscard]] constexpr float next_float() noexcept {
        constexpr double kScale = 1.0 / 9007199254740992.0;  // 1 / 2^53
        return static_cast<float>(static_cast<double>(next_u64() >> 11) * kScale);
    }

    [[nodiscard]] constexpr bool next_bool() noexcept {
        return (next_u64() & 1ULL) != 0ULL;
    }
};

struct PokemonState {
    int hp = 0;
    int max_hp = 0;
    int energy = 0;
    int8_t atk_stage = 0;
    int8_t def_stage = 0;
    bool revealed = false;
    std::array<bool, kMaxChargedMoves> revealed_charged = {false, false};

    [[nodiscard]] constexpr bool is_alive() const noexcept {
        return hp > 0;
    }

    constexpr void reset_stages() noexcept {
        atk_stage = 0;
        def_stage = 0;
    }
};

struct TeamState {
    std::array<PokemonState, kMaxTeamSize> pokemon{};
    int team_size = 0;
    int active_idx = 0;
    int shields = 2;
    int switch_timer = 0;
    int fast_move_cooldown = 0;
    bool pending_fast_move = false;
    int faint_wait_turns = 0;

    [[nodiscard]] constexpr PokemonState& active() noexcept {
        return pokemon[static_cast<std::size_t>(active_idx)];
    }

    [[nodiscard]] constexpr const PokemonState& active() const noexcept {
        return pokemon[static_cast<std::size_t>(active_idx)];
    }

    [[nodiscard]] constexpr int alive_count() const noexcept {
        int count = 0;
        for (int i = 0; i < team_size; ++i) {
            if (pokemon[static_cast<std::size_t>(i)].is_alive()) {
                ++count;
            }
        }
        return count;
    }

    [[nodiscard]] constexpr float remaining_hp_ratio() const noexcept {
        int total_hp = 0;
        int total_max_hp = 0;
        for (int i = 0; i < team_size; ++i) {
            total_hp += pokemon[static_cast<std::size_t>(i)].hp;
            total_max_hp += pokemon[static_cast<std::size_t>(i)].max_hp;
        }
        if (total_max_hp <= 0) {
            return 0.0f;
        }
        return static_cast<float>(total_hp) / static_cast<float>(total_max_hp);
    }
};

struct BattleState {
    std::array<TeamState, 2> teams{};
    int turn = 0;
    Phase phase = Phase::Finished;
    Winner winner = Winner::None;

    // Active charged move awaiting shield decision / resolution.
    int8_t cm_attacker = -1;
    int8_t cm_move_idx = -1;

    // Secondary charged move queued from a simultaneous CMP tie.
    int8_t cmp_queued_player = -1;
    int8_t cmp_queued_move_idx = -1;

    std::uint64_t rng_state = 0;
};

}  // namespace pogo_lab::battle
