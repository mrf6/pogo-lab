#pragma once

#include <cstdint>

namespace pogo_lab::battle {

inline constexpr int kNumTypes = 18;
inline constexpr int kMaxTeamSize = 3;
inline constexpr int kMaxChargedMoves = 2;
inline constexpr int kMinStatStage = -4;
inline constexpr int kMaxStatStage = 4;

inline constexpr float kPvpBonusMultiplier = 1.3f;
inline constexpr float kStabMultiplier = 1.2f;
inline constexpr float kShadowAttackMultiplier = 1.2f;
inline constexpr float kShadowDefenseMultiplier = 5.0f / 6.0f;

enum class ElementType : std::uint8_t {
    Normal = 0,
    Fire = 1,
    Water = 2,
    Grass = 3,
    Electric = 4,
    Ice = 5,
    Fighting = 6,
    Poison = 7,
    Ground = 8,
    Flying = 9,
    Psychic = 10,
    Bug = 11,
    Rock = 12,
    Ghost = 13,
    Dragon = 14,
    Dark = 15,
    Steel = 16,
    Fairy = 17,
    None = 255,
};

enum class Phase : std::uint8_t {
    Turn = 0,
    ShieldDecision = 1,
    PostChargedSwitch = 2,
    ForcedSwitch = 3,
    Finished = 4,
};

enum class Action : std::uint8_t {
    Wait = 0,
    FastMove = 1,
    ChargedMove0 = 2,
    ChargedMove1 = 3,
    Switch0 = 4,
    Switch1 = 5,
    Switch2 = 6,
    Shield = 7,
    NoShield = 8,
};

enum class Winner : std::uint8_t {
    None = 0,
    Player0 = 1,
    Player1 = 2,
    Tie = 3,
};

struct BattleConfig {
    int max_turns = 600;               // 5 minutes (300s * 2 turns/s)
    int switch_timer_turns = 90;       // 45 seconds (45s * 2 turns/s)
    int charged_move_turns = 16;       // 8 seconds (8s * 2 turns/s)
    int faint_switch_max_turns = 24;   // 12 seconds (12s * 2 turns/s)
    int initial_shields = 2;
    int max_energy = 100;
};

}  // namespace pogo_lab::battle
