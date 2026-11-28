#pragma once

#include <array>
#include <cstdint>
#include <vector>

#include "pogolab/data.hpp"
#include "pogolab/state.hpp"
#include "pogolab/types.hpp"

namespace pogolab::battle {

class BattleEngine {
public:
    explicit BattleEngine(TypeChartData type_chart, BattleConfig config = {});

    // Initializes a new battle with 1-3 Pokemon per team.
    void reset(const std::vector<PokemonData>& team0,
               const std::vector<PokemonData>& team1,
               std::uint64_t seed = 0);

    // Advances the battle state machine by one decision step.
    void step(Action action0, Action action1);

    // Returns the list of legal actions for `player` (0 or 1) in the current phase.
    [[nodiscard]] std::vector<Action> legal_actions(int player) const;

    // Returns true if `action` is currently legal for `player` (0 or 1).
    [[nodiscard]] bool is_action_legal(int player, Action action) const noexcept;

    [[nodiscard]] const BattleState& state() const noexcept { return state_; }
    [[nodiscard]] const BattleConfig& config() const noexcept { return config_; }
    [[nodiscard]] const TypeChartData& type_chart() const noexcept { return type_chart_; }
    [[nodiscard]] bool is_done() const noexcept { return state_.phase == Phase::Finished; }

    // Returns a blind copy of the state from `player`'s perspective:
    // opponent's unrevealed backline HP/max_hp/stages are zeroed and exact opponent energy is masked (-1).
    [[nodiscard]] BattleState blind_state(int player) const noexcept;

    [[nodiscard]] const PokemonData& pokemon_data(int player, int slot) const;

private:
    TypeChartData type_chart_;
    BattleConfig config_;
    std::array<std::array<PokemonData, kMaxTeamSize>, 2> team_data_{};
    BattleState state_{};
    SplitMix64 rng_{};

    [[nodiscard]] const PokemonData& active_data(int player) const noexcept {
        return team_data_[static_cast<std::size_t>(player)]
                         [static_cast<std::size_t>(state_.teams[static_cast<std::size_t>(player)].active_idx)];
    }

    [[nodiscard]] bool can_voluntary_switch(int player) const noexcept;
    [[nodiscard]] bool can_switch_to(int player, int slot, bool forced) const noexcept;

    void step_turn(Action action0, Action action1);
    void step_shield_decision(Action action0, Action action1);
    void step_post_charged_switch(Action action0, Action action1);
    void step_forced_switch(Action action0, Action action1);

    void perform_switch(int player, int slot, bool voluntary) noexcept;
    void begin_charged_move();
    void resolve_charged_move(bool shielded);
    void advance_clock(int turns, bool skip_timer_p0 = false, bool skip_timer_p1 = false) noexcept;
    bool check_battle_end() noexcept;
    void resolve_timeout() noexcept;
    void sync_rng_state() noexcept { state_.rng_state = rng_.state; }
};

}  // namespace pogolab::battle
