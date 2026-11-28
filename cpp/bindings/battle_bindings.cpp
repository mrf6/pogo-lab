#include <nanobind/nanobind.h>
#include <nanobind/stl/array.h>
#include <nanobind/stl/vector.h>

#include "pogo_lab/data.hpp"
#include "pogo_lab/engine.hpp"
#include "pogo_lab/mechanics.hpp"
#include "pogo_lab/state.hpp"
#include "pogo_lab/types.hpp"

namespace nb = nanobind;
using namespace pogo_lab::battle;

NB_MODULE(_core, m) {
    m.doc() = "C++20 Pokemon GO PvP battle simulation engine";

    nb::enum_<ElementType>(m, "ElementType")
        .value("NORMAL", ElementType::Normal)
        .value("FIRE", ElementType::Fire)
        .value("WATER", ElementType::Water)
        .value("GRASS", ElementType::Grass)
        .value("ELECTRIC", ElementType::Electric)
        .value("ICE", ElementType::Ice)
        .value("FIGHTING", ElementType::Fighting)
        .value("POISON", ElementType::Poison)
        .value("GROUND", ElementType::Ground)
        .value("FLYING", ElementType::Flying)
        .value("PSYCHIC", ElementType::Psychic)
        .value("BUG", ElementType::Bug)
        .value("ROCK", ElementType::Rock)
        .value("GHOST", ElementType::Ghost)
        .value("DRAGON", ElementType::Dragon)
        .value("DARK", ElementType::Dark)
        .value("STEEL", ElementType::Steel)
        .value("FAIRY", ElementType::Fairy)
        .value("NONE", ElementType::None);

    nb::enum_<Phase>(m, "Phase")
        .value("TURN", Phase::Turn)
        .value("SHIELD_DECISION", Phase::ShieldDecision)
        .value("POST_CHARGED_SWITCH", Phase::PostChargedSwitch)
        .value("FORCED_SWITCH", Phase::ForcedSwitch)
        .value("FINISHED", Phase::Finished);

    nb::enum_<Action>(m, "Action")
        .value("WAIT", Action::Wait)
        .value("FAST_MOVE", Action::FastMove)
        .value("CHARGED_MOVE_0", Action::ChargedMove0)
        .value("CHARGED_MOVE_1", Action::ChargedMove1)
        .value("SWITCH_0", Action::Switch0)
        .value("SWITCH_1", Action::Switch1)
        .value("SWITCH_2", Action::Switch2)
        .value("SHIELD", Action::Shield)
        .value("NO_SHIELD", Action::NoShield);

    nb::enum_<Winner>(m, "Winner")
        .value("NONE", Winner::None)
        .value("PLAYER_0", Winner::Player0)
        .value("PLAYER_1", Winner::Player1)
        .value("TIE", Winner::Tie);

    nb::class_<BattleConfig>(m, "BattleConfig")
        .def(nb::init<>())
        .def_rw("max_turns", &BattleConfig::max_turns)
        .def_rw("switch_timer_turns", &BattleConfig::switch_timer_turns)
        .def_rw("charged_move_turns", &BattleConfig::charged_move_turns)
        .def_rw("faint_switch_max_turns", &BattleConfig::faint_switch_max_turns)
        .def_rw("initial_shields", &BattleConfig::initial_shields)
        .def_rw("max_energy", &BattleConfig::max_energy);

    nb::class_<MoveBuffData>(m, "MoveBuffData")
        .def(nb::init<>())
        .def_rw("user_attack", &MoveBuffData::user_attack)
        .def_rw("user_defense", &MoveBuffData::user_defense)
        .def_rw("opponent_attack", &MoveBuffData::opponent_attack)
        .def_rw("opponent_defense", &MoveBuffData::opponent_defense)
        .def_rw("probability", &MoveBuffData::probability)
        .def("has_effect", &MoveBuffData::has_effect);

    nb::class_<FastMoveData>(m, "FastMoveData")
        .def(nb::init<>())
        .def_rw("type", &FastMoveData::type)
        .def_rw("power", &FastMoveData::power)
        .def_rw("energy_gain", &FastMoveData::energy_gain)
        .def_rw("turns", &FastMoveData::turns);

    nb::class_<ChargedMoveData>(m, "ChargedMoveData")
        .def(nb::init<>())
        .def_rw("type", &ChargedMoveData::type)
        .def_rw("power", &ChargedMoveData::power)
        .def_rw("energy_cost", &ChargedMoveData::energy_cost)
        .def_rw("buff", &ChargedMoveData::buff);

    nb::class_<PokemonData>(m, "PokemonData")
        .def(nb::init<>())
        .def_rw("attack", &PokemonData::attack)
        .def_rw("defense", &PokemonData::defense)
        .def_rw("max_hp", &PokemonData::max_hp)
        .def_rw("types", &PokemonData::types)
        .def_rw("is_shadow", &PokemonData::is_shadow)
        .def_rw("fast_move", &PokemonData::fast_move)
        .def_rw("charged_moves", &PokemonData::charged_moves)
        .def_rw("num_charged_moves", &PokemonData::num_charged_moves);

    nb::class_<TypeChartData>(m, "TypeChartData")
        .def(nb::init<>())
        .def_rw("multipliers", &TypeChartData::multipliers)
        .def("set_multiplier",
             [](TypeChartData& self, ElementType atk, ElementType def, float value) {
                 if (atk != ElementType::None && def != ElementType::None) {
                     self.multipliers[static_cast<std::size_t>(atk)]
                                     [static_cast<std::size_t>(def)] = value;
                 }
             })
        .def("effectiveness", &TypeChartData::effectiveness);

    nb::class_<PokemonState>(m, "PokemonState")
        .def(nb::init<>())
        .def_rw("hp", &PokemonState::hp)
        .def_rw("max_hp", &PokemonState::max_hp)
        .def_rw("energy", &PokemonState::energy)
        .def_rw("atk_stage", &PokemonState::atk_stage)
        .def_rw("def_stage", &PokemonState::def_stage)
        .def_rw("revealed", &PokemonState::revealed)
        .def_rw("revealed_charged", &PokemonState::revealed_charged)
        .def_prop_ro("is_alive", &PokemonState::is_alive);

    nb::class_<TeamState>(m, "TeamState")
        .def_ro("pokemon", &TeamState::pokemon)
        .def_ro("team_size", &TeamState::team_size)
        .def_ro("active_idx", &TeamState::active_idx)
        .def_ro("shields", &TeamState::shields)
        .def_ro("switch_timer", &TeamState::switch_timer)
        .def_ro("fast_move_cooldown", &TeamState::fast_move_cooldown)
        .def_ro("pending_fast_move", &TeamState::pending_fast_move)
        .def_ro("faint_wait_turns", &TeamState::faint_wait_turns)
        .def_prop_ro("active", [](const TeamState& ts) -> const PokemonState& { return ts.active(); })
        .def_prop_ro("alive_count", &TeamState::alive_count)
        .def_prop_ro("remaining_hp_ratio", &TeamState::remaining_hp_ratio);

    nb::class_<BattleState>(m, "BattleState")
        .def_ro("teams", &BattleState::teams)
        .def_ro("turn", &BattleState::turn)
        .def_ro("phase", &BattleState::phase)
        .def_ro("winner", &BattleState::winner)
        .def_ro("cm_attacker", &BattleState::cm_attacker)
        .def_ro("cm_move_idx", &BattleState::cm_move_idx)
        .def_ro("cmp_queued_player", &BattleState::cmp_queued_player)
        .def_ro("cmp_queued_move_idx", &BattleState::cmp_queued_move_idx)
        .def_ro("rng_state", &BattleState::rng_state);

    nb::class_<BattleEngine>(m, "BattleEngine")
        .def(nb::init<TypeChartData, BattleConfig>(),
             nb::arg("type_chart"),
             nb::arg("config") = BattleConfig{})
        .def("reset",
             &BattleEngine::reset,
             nb::arg("team0"),
             nb::arg("team1"),
             nb::arg("seed") = 0)
        .def("step", &BattleEngine::step, nb::arg("action0"), nb::arg("action1"))
        .def("legal_actions", &BattleEngine::legal_actions, nb::arg("player"))
        .def("is_action_legal", &BattleEngine::is_action_legal, nb::arg("player"), nb::arg("action"))
        .def("state", &BattleEngine::state, nb::rv_policy::reference_internal)
        .def("blind_state", &BattleEngine::blind_state, nb::arg("player"))
        .def("config", &BattleEngine::config, nb::rv_policy::reference_internal)
        .def("pokemon_data",
             &BattleEngine::pokemon_data,
             nb::arg("player"),
             nb::arg("slot"),
             nb::rv_policy::reference_internal)
        .def_prop_ro("is_done", &BattleEngine::is_done);

    m.def("stat_stage_multiplier", &stat_stage_multiplier, nb::arg("stage"));
    m.def("calculate_damage",
          &calculate_damage,
          nb::arg("attacker_data"),
          nb::arg("attacker_state"),
          nb::arg("defender_data"),
          nb::arg("defender_state"),
          nb::arg("move_power"),
          nb::arg("move_type"),
          nb::arg("type_chart"));
}
