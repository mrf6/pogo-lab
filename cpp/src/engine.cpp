#include "pogolab/engine.hpp"

#include <algorithm>
#include <cmath>
#include <stdexcept>

#include "pogolab/mechanics.hpp"

namespace pogolab::battle {

namespace {

constexpr int action_to_switch_slot(Action action) noexcept {
    switch (action) {
        case Action::Switch0:
            return 0;
        case Action::Switch1:
            return 1;
        case Action::Switch2:
            return 2;
        default:
            return -1;
    }
}

constexpr Action switch_slot_to_action(int slot) noexcept {
    switch (slot) {
        case 0:
            return Action::Switch0;
        case 1:
            return Action::Switch1;
        case 2:
            return Action::Switch2;
        default:
            return Action::Wait;
    }
}

constexpr int action_to_charged_idx(Action action) noexcept {
    if (action == Action::ChargedMove0) {
        return 0;
    }
    if (action == Action::ChargedMove1) {
        return 1;
    }
    return -1;
}

}  // namespace

BattleEngine::BattleEngine(TypeChartData type_chart, BattleConfig config)
    : type_chart_(type_chart), config_(config) {}

void BattleEngine::reset(const std::vector<PokemonData>& team0,
                         const std::vector<PokemonData>& team1,
                         std::uint64_t seed) {
    if (team0.empty() || team0.size() > static_cast<std::size_t>(kMaxTeamSize)) {
        throw std::invalid_argument("team0 must contain between 1 and 3 Pokemon");
    }
    if (team1.empty() || team1.size() > static_cast<std::size_t>(kMaxTeamSize)) {
        throw std::invalid_argument("team1 must contain between 1 and 3 Pokemon");
    }

    rng_ = SplitMix64(seed);
    state_ = BattleState{};
    state_.turn = 0;
    state_.phase = Phase::Turn;
    state_.winner = Winner::None;

    const std::array<const std::vector<PokemonData>*, 2> inputs = {&team0, &team1};
    for (int p = 0; p < 2; ++p) {
        auto& td = team_data_[static_cast<std::size_t>(p)];
        auto& ts = state_.teams[static_cast<std::size_t>(p)];
        ts = TeamState{};
        ts.team_size = static_cast<int>(inputs[static_cast<std::size_t>(p)]->size());
        ts.active_idx = 0;
        ts.shields = config_.initial_shields;
        ts.switch_timer = 0;
        ts.fast_move_cooldown = 0;
        ts.pending_fast_move = false;
        ts.faint_wait_turns = 0;

        for (int i = 0; i < ts.team_size; ++i) {
            const PokemonData& pd = (*inputs[static_cast<std::size_t>(p)])[static_cast<std::size_t>(i)];
            if (pd.max_hp <= 0) {
                throw std::invalid_argument("Pokemon max_hp must be positive");
            }
            if (pd.fast_move.turns <= 0) {
                throw std::invalid_argument("Fast move turns must be positive");
            }
            if (pd.num_charged_moves < 0 || pd.num_charged_moves > kMaxChargedMoves) {
                throw std::invalid_argument("num_charged_moves must be between 0 and 2");
            }
            td[static_cast<std::size_t>(i)] = pd;

            auto& ps = ts.pokemon[static_cast<std::size_t>(i)];
            ps = PokemonState{};
            ps.hp = pd.max_hp;
            ps.max_hp = pd.max_hp;
            ps.energy = 0;
            ps.revealed = (i == 0);  // Lead is visible at Turn 0.
        }
    }

    sync_rng_state();
}

const PokemonData& BattleEngine::pokemon_data(int player, int slot) const {
    if (player < 0 || player > 1) {
        throw std::out_of_range("player must be 0 or 1");
    }
    const int size = state_.teams[static_cast<std::size_t>(player)].team_size;
    if (slot < 0 || slot >= size) {
        throw std::out_of_range("slot out of range for team");
    }
    return team_data_[static_cast<std::size_t>(player)][static_cast<std::size_t>(slot)];
}

bool BattleEngine::can_switch_to(int player, int slot, bool forced) const noexcept {
    const auto& ts = state_.teams[static_cast<std::size_t>(player)];
    if (slot < 0 || slot >= ts.team_size || slot == ts.active_idx) {
        return false;
    }
    if (!ts.pokemon[static_cast<std::size_t>(slot)].is_alive()) {
        return false;
    }
    if (!forced && ts.switch_timer > 0) {
        return false;
    }
    return true;
}

bool BattleEngine::can_voluntary_switch(int player) const noexcept {
    const auto& ts = state_.teams[static_cast<std::size_t>(player)];
    if (ts.switch_timer > 0) {
        return false;
    }
    for (int i = 0; i < ts.team_size; ++i) {
        if (i != ts.active_idx && ts.pokemon[static_cast<std::size_t>(i)].is_alive()) {
            return true;
        }
    }
    return false;
}

bool BattleEngine::is_action_legal(int player, Action action) const noexcept {
    if (player < 0 || player > 1) {
        return false;
    }
    const auto& ts = state_.teams[static_cast<std::size_t>(player)];

    switch (state_.phase) {
        case Phase::Finished:
            return action == Action::Wait;

        case Phase::ShieldDecision: {
            const int defender = 1 - state_.cm_attacker;
            if (player == defender) {
                return action == Action::Shield || action == Action::NoShield;
            }
            return action == Action::Wait;
        }

        case Phase::PostChargedSwitch: {
            if (action == Action::Wait) {
                return true;
            }
            const int slot = action_to_switch_slot(action);
            return slot >= 0 && can_switch_to(player, slot, /*forced=*/false);
        }

        case Phase::ForcedSwitch: {
            if (ts.active().is_alive()) {
                return action == Action::Wait;
            }
            if (action == Action::Wait) {
                return ts.faint_wait_turns < config_.faint_switch_max_turns;
            }
            const int slot = action_to_switch_slot(action);
            return slot >= 0 && can_switch_to(player, slot, /*forced=*/true);
        }

        case Phase::Turn: {
            if (ts.fast_move_cooldown > 0) {
                return action == Action::Wait;
            }
            if (action == Action::Wait || action == Action::FastMove) {
                return true;
            }
            const int cm_idx = action_to_charged_idx(action);
            if (cm_idx >= 0) {
                const auto& pd = active_data(player);
                return cm_idx < pd.num_charged_moves &&
                       ts.active().energy >= pd.charged_moves[static_cast<std::size_t>(cm_idx)].energy_cost;
            }
            const int slot = action_to_switch_slot(action);
            if (slot >= 0) {
                return can_switch_to(player, slot, /*forced=*/false);
            }
            return false;
        }
    }
    return false;
}

std::vector<Action> BattleEngine::legal_actions(int player) const {
    if (player < 0 || player > 1) {
        throw std::out_of_range("player must be 0 or 1");
    }

    std::vector<Action> actions;
    actions.reserve(6);
    const auto& ts = state_.teams[static_cast<std::size_t>(player)];

    switch (state_.phase) {
        case Phase::Finished:
            actions.push_back(Action::Wait);
            break;

        case Phase::ShieldDecision:
            if (player == 1 - state_.cm_attacker) {
                actions.push_back(Action::Shield);
                actions.push_back(Action::NoShield);
            } else {
                actions.push_back(Action::Wait);
            }
            break;

        case Phase::PostChargedSwitch:
            actions.push_back(Action::Wait);
            for (int i = 0; i < ts.team_size; ++i) {
                if (can_switch_to(player, i, /*forced=*/false)) {
                    actions.push_back(switch_slot_to_action(i));
                }
            }
            break;

        case Phase::ForcedSwitch:
            if (ts.active().is_alive()) {
                actions.push_back(Action::Wait);
            } else {
                for (int i = 0; i < ts.team_size; ++i) {
                    if (can_switch_to(player, i, /*forced=*/true)) {
                        actions.push_back(switch_slot_to_action(i));
                    }
                }
                if (ts.faint_wait_turns < config_.faint_switch_max_turns) {
                    actions.push_back(Action::Wait);
                }
            }
            break;

        case Phase::Turn:
            if (ts.fast_move_cooldown > 0) {
                actions.push_back(Action::Wait);
            } else {
                actions.push_back(Action::Wait);
                actions.push_back(Action::FastMove);
                const auto& pd = active_data(player);
                for (int i = 0; i < pd.num_charged_moves; ++i) {
                    if (ts.active().energy >= pd.charged_moves[static_cast<std::size_t>(i)].energy_cost) {
                        actions.push_back(i == 0 ? Action::ChargedMove0 : Action::ChargedMove1);
                    }
                }
                for (int i = 0; i < ts.team_size; ++i) {
                    if (can_switch_to(player, i, /*forced=*/false)) {
                        actions.push_back(switch_slot_to_action(i));
                    }
                }
            }
            break;
    }
    return actions;
}

void BattleEngine::step(Action action0, Action action1) {
    if (state_.phase == Phase::Finished) {
        return;
    }
    if (!is_action_legal(0, action0)) {
        throw std::invalid_argument("Illegal action for player 0");
    }
    if (!is_action_legal(1, action1)) {
        throw std::invalid_argument("Illegal action for player 1");
    }

    switch (state_.phase) {
        case Phase::Turn:
            step_turn(action0, action1);
            break;
        case Phase::ShieldDecision:
            step_shield_decision(action0, action1);
            break;
        case Phase::PostChargedSwitch:
            step_post_charged_switch(action0, action1);
            break;
        case Phase::ForcedSwitch:
            step_forced_switch(action0, action1);
            break;
        case Phase::Finished:
            break;
    }

    sync_rng_state();
}

void BattleEngine::perform_switch(int player, int slot, bool voluntary) noexcept {
    auto& ts = state_.teams[static_cast<std::size_t>(player)];
    ts.active().reset_stages();
    ts.active_idx = slot;
    ts.active().revealed = true;
    ts.fast_move_cooldown = 0;
    ts.pending_fast_move = false;
    ts.faint_wait_turns = 0;
    if (voluntary) {
        ts.switch_timer = config_.switch_timer_turns;
    }
}

void BattleEngine::advance_clock(int turns, bool skip_timer_p0, bool skip_timer_p1) noexcept {
    if (turns <= 0) {
        return;
    }
    state_.turn += turns;
    const std::array<bool, 2> skip = {skip_timer_p0, skip_timer_p1};
    for (int p = 0; p < 2; ++p) {
        if (!skip[static_cast<std::size_t>(p)]) {
            auto& timer = state_.teams[static_cast<std::size_t>(p)].switch_timer;
            timer = std::max(0, timer - turns);
        }
    }
}

void BattleEngine::resolve_timeout() noexcept {
    const int alive0 = state_.teams[0].alive_count();
    const int alive1 = state_.teams[1].alive_count();
    if (alive0 > alive1) {
        state_.winner = Winner::Player0;
    } else if (alive1 > alive0) {
        state_.winner = Winner::Player1;
    } else {
        const float ratio0 = state_.teams[0].remaining_hp_ratio();
        const float ratio1 = state_.teams[1].remaining_hp_ratio();
        constexpr float kEps = 1e-6f;
        if (ratio0 > ratio1 + kEps) {
            state_.winner = Winner::Player0;
        } else if (ratio1 > ratio0 + kEps) {
            state_.winner = Winner::Player1;
        } else {
            state_.winner = Winner::Tie;
        }
    }
    state_.phase = Phase::Finished;
}

bool BattleEngine::check_battle_end() noexcept {
    const int alive0 = state_.teams[0].alive_count();
    const int alive1 = state_.teams[1].alive_count();
    if (alive0 == 0 && alive1 == 0) {
        state_.winner = Winner::Tie;
        state_.phase = Phase::Finished;
        return true;
    }
    if (alive0 == 0) {
        state_.winner = Winner::Player1;
        state_.phase = Phase::Finished;
        return true;
    }
    if (alive1 == 0) {
        state_.winner = Winner::Player0;
        state_.phase = Phase::Finished;
        return true;
    }
    if (state_.turn >= config_.max_turns) {
        resolve_timeout();
        return true;
    }
    return false;
}

void BattleEngine::step_turn(Action action0, Action action1) {
    const std::array<Action, 2> actions = {action0, action1};
    std::array<bool, 2> swapped = {false, false};

    // 1. Voluntary 1-turn swaps have highest priority.
    // Incoming Pokemon will receive any fast move or charged move landing this turn.
    for (int p = 0; p < 2; ++p) {
        const int slot = action_to_switch_slot(actions[static_cast<std::size_t>(p)]);
        if (slot >= 0) {
            perform_switch(p, slot, /*voluntary=*/true);
            swapped[static_cast<std::size_t>(p)] = true;
        }
    }

    // 2. Start fast moves for free players who chose FastMove.
    for (int p = 0; p < 2; ++p) {
        if (!swapped[static_cast<std::size_t>(p)] &&
            actions[static_cast<std::size_t>(p)] == Action::FastMove) {
            auto& ts = state_.teams[static_cast<std::size_t>(p)];
            ts.pending_fast_move = true;
            ts.fast_move_cooldown = active_data(p).fast_move.turns;
        }
    }

    // 3. Check for Charged Moves.
    const int cm0 = swapped[0] ? -1 : action_to_charged_idx(actions[0]);
    const int cm1 = swapped[1] ? -1 : action_to_charged_idx(actions[1]);

    if (cm0 >= 0 || cm1 >= 0) {
        if (cm0 >= 0 && cm1 >= 0) {
            const int cmp_winner = resolve_cmp(active_data(0), active_data(1), rng_);
            const int cmp_loser = 1 - cmp_winner;
            state_.cm_attacker = static_cast<int8_t>(cmp_winner);
            state_.cm_move_idx = static_cast<int8_t>(cmp_winner == 0 ? cm0 : cm1);
            state_.cmp_queued_player = static_cast<int8_t>(cmp_loser);
            state_.cmp_queued_move_idx = static_cast<int8_t>(cmp_loser == 0 ? cm0 : cm1);
        } else if (cm0 >= 0) {
            state_.cm_attacker = 0;
            state_.cm_move_idx = static_cast<int8_t>(cm0);
            state_.cmp_queued_player = -1;
            state_.cmp_queued_move_idx = -1;
        } else {
            state_.cm_attacker = 1;
            state_.cm_move_idx = static_cast<int8_t>(cm1);
            state_.cmp_queued_player = -1;
            state_.cmp_queued_move_idx = -1;
        }
        begin_charged_move();
        return;
    }

    // 4. Normal turn without Charged Moves: advance fast-move cooldowns and register hits.
    std::array<int, 2> fm_damage = {0, 0};
    std::array<int, 2> fm_energy = {0, 0};

    for (int p = 0; p < 2; ++p) {
        auto& ts = state_.teams[static_cast<std::size_t>(p)];
        if (ts.fast_move_cooldown > 0) {
            --ts.fast_move_cooldown;
            if (ts.fast_move_cooldown == 0 && ts.pending_fast_move) {
                const int def = 1 - p;
                const auto& atk_data = active_data(p);
                const auto& def_data = active_data(def);
                fm_damage[static_cast<std::size_t>(p)] = calculate_damage(
                    atk_data, ts.active(), def_data, state_.teams[static_cast<std::size_t>(def)].active(),
                    atk_data.fast_move.power, atk_data.fast_move.type, type_chart_);
                fm_energy[static_cast<std::size_t>(p)] = atk_data.fast_move.energy_gain;
                ts.pending_fast_move = false;
            }
        }
    }

    // Apply fast move damage and energy simultaneously.
    for (int p = 0; p < 2; ++p) {
        if (fm_damage[static_cast<std::size_t>(p)] > 0) {
            const int def = 1 - p;
            auto& def_state = state_.teams[static_cast<std::size_t>(def)].active();
            def_state.hp = std::max(0, def_state.hp - fm_damage[static_cast<std::size_t>(p)]);
        }
        if (fm_energy[static_cast<std::size_t>(p)] > 0) {
            auto& atk_state = state_.teams[static_cast<std::size_t>(p)].active();
            atk_state.energy = std::min(config_.max_energy, atk_state.energy + fm_energy[static_cast<std::size_t>(p)]);
        }
    }

    // Advance universal clock by 1 turn (don't tick down a switch timer just set this turn).
    advance_clock(1, /*skip_timer_p0=*/swapped[0], /*skip_timer_p1=*/swapped[1]);

    if (check_battle_end()) {
        return;
    }

    // Check for faints.
    if (!state_.teams[0].active().is_alive() || !state_.teams[1].active().is_alive()) {
        for (int p = 0; p < 2; ++p) {
            if (!state_.teams[static_cast<std::size_t>(p)].active().is_alive()) {
                state_.teams[static_cast<std::size_t>(p)].fast_move_cooldown = 0;
                state_.teams[static_cast<std::size_t>(p)].pending_fast_move = false;
                state_.teams[static_cast<std::size_t>(p)].faint_wait_turns = 0;
            }
        }
        state_.phase = Phase::ForcedSwitch;
    } else {
        state_.phase = Phase::Turn;
    }
}

void BattleEngine::begin_charged_move() {
    const int a = state_.cm_attacker;
    const int d = 1 - a;
    const int move_idx = state_.cm_move_idx;

    const auto& atk_data = active_data(a);
    const auto& move = atk_data.charged_moves[static_cast<std::size_t>(move_idx)];

    auto& atk_state = state_.teams[static_cast<std::size_t>(a)].active();
    atk_state.energy = std::max(0, atk_state.energy - move.energy_cost);
    atk_state.revealed_charged[static_cast<std::size_t>(move_idx)] = true;

    if (state_.teams[static_cast<std::size_t>(d)].shields > 0) {
        state_.phase = Phase::ShieldDecision;
    } else {
        resolve_charged_move(/*shielded=*/false);
    }
}

void BattleEngine::step_shield_decision(Action action0, Action action1) {
    const int defender = 1 - state_.cm_attacker;
    const Action def_action = (defender == 0) ? action0 : action1;
    resolve_charged_move(/*shielded=*/def_action == Action::Shield);
}

void BattleEngine::resolve_charged_move(bool shielded) {
    const int a = state_.cm_attacker;
    const int d = 1 - a;
    const int move_idx = state_.cm_move_idx;

    const auto& atk_data = active_data(a);
    const auto& def_data = active_data(d);
    const auto& move = atk_data.charged_moves[static_cast<std::size_t>(move_idx)];

    auto& atk_team = state_.teams[static_cast<std::size_t>(a)];
    auto& def_team = state_.teams[static_cast<std::size_t>(d)];
    auto& atk_state = atk_team.active();
    auto& def_state = def_team.active();

    // 1. Apply Charged Move damage (1 if shielded).
    int cm_damage = 1;
    if (shielded) {
        def_team.shields = std::max(0, def_team.shields - 1);
    } else {
        cm_damage = calculate_damage(atk_data, atk_state, def_data, def_state,
                                     move.power, move.type, type_chart_);
    }
    def_state.hp = std::max(0, def_state.hp - cm_damage);

    // 2. Apply buff/debuff BEFORE opponent's in-progress fast move damage is calculated.
    apply_buff(move.buff, atk_state, def_state, rng_);

    // 3. Resolve opponent's in-progress fast move (lands on original attacker with updated stages).
    if (def_team.pending_fast_move) {
        const int fm_damage = calculate_damage(
            def_data, def_state, atk_data, atk_state,
            def_data.fast_move.power, def_data.fast_move.type, type_chart_);
        atk_state.hp = std::max(0, atk_state.hp - fm_damage);
        def_state.energy = std::min(config_.max_energy, def_state.energy + def_data.fast_move.energy_gain);
        def_team.pending_fast_move = false;
        def_team.fast_move_cooldown = 0;
    }

    // 4. Advance universal clock for the Charged Move animation/window.
    advance_clock(config_.charged_move_turns);

    state_.cm_attacker = -1;
    state_.cm_move_idx = -1;

    // 5. Check battle end / timeout.
    if (check_battle_end()) {
        state_.cmp_queued_player = -1;
        state_.cmp_queued_move_idx = -1;
        return;
    }

    // 6. Check faints.
    if (!atk_state.is_alive() || !def_state.is_alive()) {
        state_.cmp_queued_player = -1;
        state_.cmp_queued_move_idx = -1;
        for (int p = 0; p < 2; ++p) {
            if (!state_.teams[static_cast<std::size_t>(p)].active().is_alive()) {
                state_.teams[static_cast<std::size_t>(p)].fast_move_cooldown = 0;
                state_.teams[static_cast<std::size_t>(p)].pending_fast_move = false;
                state_.teams[static_cast<std::size_t>(p)].faint_wait_turns = 0;
            }
        }
        state_.phase = Phase::ForcedSwitch;
        return;
    }

    // 7. If a second CMP Charged Move was queued, resolve it immediately.
    if (state_.cmp_queued_player >= 0) {
        state_.cm_attacker = state_.cmp_queued_player;
        state_.cm_move_idx = state_.cmp_queued_move_idx;
        state_.cmp_queued_player = -1;
        state_.cmp_queued_move_idx = -1;
        begin_charged_move();
        return;
    }

    // 8. Offer 0-turn post-CM switch if either player can voluntarily switch.
    if (can_voluntary_switch(0) || can_voluntary_switch(1)) {
        state_.phase = Phase::PostChargedSwitch;
    } else {
        state_.phase = Phase::Turn;
    }
}

void BattleEngine::step_post_charged_switch(Action action0, Action action1) {
    const std::array<Action, 2> actions = {action0, action1};
    for (int p = 0; p < 2; ++p) {
        const int slot = action_to_switch_slot(actions[static_cast<std::size_t>(p)]);
        if (slot >= 0) {
            // 0-turn switch: no clock advance, incoming Pokemon acts on the next Turn.
            perform_switch(p, slot, /*voluntary=*/true);
        }
    }
    state_.phase = Phase::Turn;
}

void BattleEngine::step_forced_switch(Action action0, Action action1) {
    const std::array<Action, 2> actions = {action0, action1};
    bool anyone_waited = false;

    for (int p = 0; p < 2; ++p) {
        auto& ts = state_.teams[static_cast<std::size_t>(p)];
        if (ts.active().is_alive()) {
            continue;
        }
        const int slot = action_to_switch_slot(actions[static_cast<std::size_t>(p)]);
        if (slot >= 0) {
            perform_switch(p, slot, /*voluntary=*/false);
        } else {
            // Waiting out the faint switch clock (1 turn at a time, up to faint_switch_max_turns).
            ++ts.faint_wait_turns;
            anyone_waited = true;
        }
    }

    if (anyone_waited) {
        advance_clock(1);
        if (check_battle_end()) {
            return;
        }
    }

    if (state_.teams[0].active().is_alive() && state_.teams[1].active().is_alive()) {
        state_.teams[0].faint_wait_turns = 0;
        state_.teams[1].faint_wait_turns = 0;
        state_.phase = Phase::Turn;
    } else {
        state_.phase = Phase::ForcedSwitch;
    }
}

BattleState BattleEngine::blind_state(int player) const noexcept {
    BattleState copy = state_;
    if (player < 0 || player > 1) {
        return copy;
    }
    const int opp = 1 - player;
    auto& opp_team = copy.teams[static_cast<std::size_t>(opp)];
    for (int i = 0; i < opp_team.team_size; ++i) {
        auto& ps = opp_team.pokemon[static_cast<std::size_t>(i)];
        ps.energy = -1;  // Exact opponent energy is hidden in blind PvP.
        if (!ps.revealed) {
            ps.hp = -1;
            ps.max_hp = -1;
            ps.atk_stage = 0;
            ps.def_stage = 0;
            ps.revealed_charged = {false, false};
        }
    }
    copy.rng_state = 0;
    return copy;
}

}  // namespace pogolab::battle
