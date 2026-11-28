"""Comprehensive pytest suite for the C++20 Pokémon GO PvP battle engine."""

from __future__ import annotations

import math

import pytest

from pogo_lab.battle import (
    Action,
    BattleConfig,
    BattleEngine,
    ChargedMoveData,
    ElementType,
    FastMoveData,
    GreedyBot,
    MoveBuffData,
    Phase,
    PokemonData,
    PokemonState,
    RandomBot,
    TypeChartData,
    Winner,
    calculate_damage,
    create_engine,
    play_battle,
    stat_stage_multiplier,
    to_team_data,
)
from pogo_lab.data import load_game_data
from pogo_lab.pokemon import Pokemon


def _make_neutral_chart() -> TypeChartData:
    chart = TypeChartData()
    chart.set_multiplier(ElementType.WATER, ElementType.FIRE, 1.6)
    chart.set_multiplier(ElementType.FIRE, ElementType.WATER, 0.625)
    chart.set_multiplier(ElementType.FIGHTING, ElementType.NORMAL, 1.6)
    chart.set_multiplier(ElementType.FIGHTING, ElementType.GHOST, 0.390625)
    return chart


def _make_mon(
    *,
    attack: float = 120.0,
    defense: float = 120.0,
    max_hp: int = 150,
    types: tuple[ElementType, ElementType] = (ElementType.NORMAL, ElementType.NONE),
    is_shadow: bool = False,
    fast_power: int = 6,
    fast_energy: int = 7,
    fast_turns: int = 2,
    fast_type: ElementType = ElementType.NORMAL,
    charged: list[ChargedMoveData] | None = None,
) -> PokemonData:
    mon = PokemonData()
    mon.attack = attack
    mon.defense = defense
    mon.max_hp = max_hp
    mon.types = [types[0], types[1]]
    mon.is_shadow = is_shadow

    fm = FastMoveData()
    fm.type = fast_type
    fm.power = fast_power
    fm.energy_gain = fast_energy
    fm.turns = fast_turns
    mon.fast_move = fm

    cm_list = [ChargedMoveData(), ChargedMoveData()]
    if charged:
        for i, cm in enumerate(charged[:2]):
            cm_list[i] = cm
        mon.num_charged_moves = len(charged[:2])
    else:
        mon.num_charged_moves = 0
    mon.charged_moves = cm_list
    return mon


def _make_cm(
    *,
    power: int = 60,
    energy_cost: int = 35,
    move_type: ElementType = ElementType.NORMAL,
    user_atk: int = 0,
    user_def: int = 0,
    opp_atk: int = 0,
    opp_def: int = 0,
    buff_prob: float = 0.0,
) -> ChargedMoveData:
    cm = ChargedMoveData()
    cm.type = move_type
    cm.power = power
    cm.energy_cost = energy_cost
    buff = MoveBuffData()
    buff.user_attack = user_atk
    buff.user_defense = user_def
    buff.opponent_attack = opp_atk
    buff.opponent_defense = opp_def
    buff.probability = buff_prob
    cm.buff = buff
    return cm


# ---------------------------------------------------------------------------
# Damage & Mechanics
# ---------------------------------------------------------------------------


def test_stat_stage_multipliers() -> None:
    assert stat_stage_multiplier(0) == pytest.approx(1.0)
    assert stat_stage_multiplier(1) == pytest.approx(1.25)
    assert stat_stage_multiplier(2) == pytest.approx(1.5)
    assert stat_stage_multiplier(4) == pytest.approx(2.0)
    assert stat_stage_multiplier(10) == pytest.approx(2.0)  # clamped
    assert stat_stage_multiplier(-1) == pytest.approx(4.0 / 5.0)
    assert stat_stage_multiplier(-2) == pytest.approx(4.0 / 6.0)
    assert stat_stage_multiplier(-4) == pytest.approx(0.5)
    assert stat_stage_multiplier(-10) == pytest.approx(0.5)  # clamped


def test_damage_formula_stab_shadow_type_and_stages() -> None:
    chart = _make_neutral_chart()
    atk = _make_mon(
        attack=130.0,
        types=(ElementType.WATER, ElementType.NONE),
        is_shadow=True,
    )
    dfn = _make_mon(
        defense=110.0,
        types=(ElementType.FIRE, ElementType.NONE),
        is_shadow=True,
    )
    atk_state = PokemonState()
    atk_state.atk_stage = 1  # 1.25x
    def_state = PokemonState()
    def_state.def_stage = -1  # 0.8x

    dmg = calculate_damage(atk, atk_state, dfn, def_state, 80, ElementType.WATER, chart)

    eff_atk = 130.0 * 1.25 * 1.2
    eff_def = 110.0 * 0.8 * (5.0 / 6.0)
    expected = math.floor(0.5 * 80 * (eff_atk / eff_def) * 1.2 * 1.6 * 1.3) + 1
    assert dmg == expected

    # Minimum damage is always 1 even at 0 power.
    min_dmg = calculate_damage(atk, atk_state, dfn, def_state, 0, ElementType.NORMAL, chart)
    assert min_dmg == 1


# ---------------------------------------------------------------------------
# Fast Moves, Lockouts & Energy Cap
# ---------------------------------------------------------------------------


def test_fast_move_lockout_and_energy_cap() -> None:
    chart = _make_neutral_chart()
    engine = BattleEngine(chart)
    mon0 = _make_mon(fast_power=5, fast_energy=40, fast_turns=3, max_hp=200)
    mon1 = _make_mon(fast_power=1, fast_energy=1, fast_turns=1, max_hp=200)
    engine.reset([mon0], [mon1], seed=1)

    # Turn 0 -> starts 3-turn fast move; locked for turns 1 and 2.
    engine.step(Action.FAST_MOVE, Action.WAIT)
    assert engine.state().turn == 1
    assert engine.state().teams[0].fast_move_cooldown == 2
    assert engine.state().teams[0].active.energy == 0
    assert engine.legal_actions(0) == [Action.WAIT]

    engine.step(Action.WAIT, Action.WAIT)
    assert engine.state().teams[0].fast_move_cooldown == 1
    assert engine.state().teams[0].active.energy == 0

    # 3rd turn completes fast move: energy gained & damage applied.
    engine.step(Action.WAIT, Action.WAIT)
    assert engine.state().turn == 3
    assert engine.state().teams[0].fast_move_cooldown == 0
    assert engine.state().teams[0].active.energy == 40
    assert engine.state().teams[1].active.hp < 200

    # Two more 3-turn fast moves: 40 + 40 + 40 = 120 -> capped at 100.
    for _ in range(2):
        engine.step(Action.FAST_MOVE, Action.WAIT)
        engine.step(Action.WAIT, Action.WAIT)
        engine.step(Action.WAIT, Action.WAIT)
    assert engine.state().teams[0].active.energy == 100


# ---------------------------------------------------------------------------
# Normal 1-Turn Swap (Highest Priority) & Catching
# ---------------------------------------------------------------------------


def test_normal_swap_catches_4_turn_fast_move_after_3_turn_fast_move() -> None:
    chart = _make_neutral_chart()
    engine = BattleEngine(chart)

    lead0 = _make_mon(fast_power=3, fast_energy=5, fast_turns=3, max_hp=150)
    back0 = _make_mon(fast_power=3, fast_energy=5, fast_turns=2, max_hp=150)
    lead1 = _make_mon(fast_power=20, fast_energy=10, fast_turns=4, max_hp=150)

    engine.reset([lead0, back0], [lead1], seed=42)

    # Turns 0, 1, 2: P0 executes 3-turn move, P1 is 3 turns into 4-turn move.
    engine.step(Action.FAST_MOVE, Action.FAST_MOVE)
    engine.step(Action.WAIT, Action.WAIT)
    engine.step(Action.WAIT, Action.WAIT)
    assert engine.state().teams[0].fast_move_cooldown == 0
    assert engine.state().teams[1].fast_move_cooldown == 1
    assert engine.state().teams[0].pokemon[0].hp == 150
    assert engine.state().teams[0].pokemon[1].hp == 150

    # Turn 3: P0 switches to slot 1 while P1's 4-turn fast move finishes -> lands on slot 1!
    engine.step(Action.SWITCH_1, Action.WAIT)
    st = engine.state()
    assert st.turn == 4
    assert st.teams[0].active_idx == 1
    assert st.teams[0].switch_timer == 90  # 45 seconds
    assert st.teams[0].pokemon[0].hp == 150  # original lead unharmed
    assert st.teams[0].pokemon[1].hp < 150  # switched-in Pokemon took the damage!


def test_normal_swap_catches_charged_move() -> None:
    chart = _make_neutral_chart()
    config = BattleConfig()
    config.initial_shields = 0
    engine = BattleEngine(chart, config)

    lead0 = _make_mon(fast_power=1, fast_energy=50, fast_turns=1, max_hp=200)
    back0 = _make_mon(fast_power=1, fast_energy=50, fast_turns=1, max_hp=200)
    nuke = _make_cm(power=100, energy_cost=35)
    lead1 = _make_mon(fast_power=1, fast_energy=50, fast_turns=1, max_hp=200, charged=[nuke])

    engine.reset([lead0, back0], [lead1], seed=7)
    engine.step(Action.WAIT, Action.FAST_MOVE)  # P1 now has 50 energy (dealt 1 fast-move dmg)
    lead0_hp_before = engine.state().teams[0].pokemon[0].hp

    # P0 switches on the exact turn P1 throws the Charged Move -> back0 catches it!
    engine.step(Action.SWITCH_1, Action.CHARGED_MOVE_0)
    st = engine.state()
    assert st.teams[0].active_idx == 1
    assert st.teams[0].pokemon[0].hp == lead0_hp_before
    assert st.teams[0].pokemon[1].hp < 200


# ---------------------------------------------------------------------------
# Self-Debuff Before In-Progress Fast Move & 0-Turn Post-CM Switch
# ---------------------------------------------------------------------------


def test_self_debuff_applies_before_in_progress_fast_move_and_zero_turn_post_cm_switch() -> None:
    chart = _make_neutral_chart()
    config = BattleConfig()
    config.initial_shields = 0
    engine = BattleEngine(chart, config)

    # Close-Combat-style self-debuff (-2 user defense, 100% prob).
    self_debuff_cm = _make_cm(power=40, energy_cost=35, user_def=-2, buff_prob=1.0)
    lead0 = _make_mon(
        attack=120.0,
        defense=120.0,
        max_hp=200,
        fast_power=1,
        fast_energy=50,
        fast_turns=1,
        charged=[self_debuff_cm],
    )
    back0 = _make_mon(max_hp=200)
    lead1 = _make_mon(
        attack=120.0,
        defense=120.0,
        max_hp=200,
        fast_power=20,
        fast_energy=10,
        fast_turns=3,
    )

    # Compute expected damage with 0 def stage vs -2 def stage.
    neutral_state = PokemonState()
    debuffed_state = PokemonState()
    debuffed_state.def_stage = -2
    dmg_neutral = calculate_damage(
        lead1, neutral_state, lead0, neutral_state, 20, ElementType.NORMAL, chart
    )
    dmg_debuffed = calculate_damage(
        lead1, neutral_state, lead0, debuffed_state, 20, ElementType.NORMAL, chart
    )
    assert dmg_debuffed > dmg_neutral

    engine.reset([lead0, back0], [lead1], seed=11)
    # Turn 0: P0 gains 50 energy (1-turn fast move); P1 starts 3-turn fast move.
    engine.step(Action.FAST_MOVE, Action.FAST_MOVE)
    assert engine.state().teams[0].active.hp == 200
    assert engine.state().teams[1].pending_fast_move is True

    # Turn 1: P0 throws self-debuffing CM while P1's fast move is in progress.
    turn_before_cm = engine.state().turn
    engine.step(Action.CHARGED_MOVE_0, Action.WAIT)
    st = engine.state()

    # 1. Self-debuff applied BEFORE P1's in-progress fast move landed on lead0!
    assert st.teams[0].pokemon[0].def_stage == -2
    assert st.teams[0].pokemon[0].hp == 200 - dmg_debuffed
    assert st.teams[0].pokemon[1].hp == 200  # back0 untouched

    # 2. Universal clock advanced by charged_move_turns (16).
    assert st.turn == turn_before_cm + config.charged_move_turns

    # 3. Engine offers 0-turn PostChargedSwitch because P0 can voluntarily switch.
    assert st.phase == Phase.POST_CHARGED_SWITCH
    turn_at_post_cm = st.turn

    # P0 takes the 0-turn switch: turn does NOT advance, outgoing stages reset!
    engine.step(Action.SWITCH_1, Action.WAIT)
    st = engine.state()
    assert st.phase == Phase.TURN
    assert st.turn == turn_at_post_cm  # 0 turns spent!
    assert st.teams[0].active_idx == 1
    assert st.teams[0].pokemon[0].def_stage == 0  # stat stages reset on switch
    assert st.teams[0].switch_timer == config.switch_timer_turns


# ---------------------------------------------------------------------------
# CMP (Base Effective Attack Only — Ignores Shadow & Stat Stages)
# ---------------------------------------------------------------------------


def test_cmp_ignores_shadow_and_stat_stages() -> None:
    chart = _make_neutral_chart()
    config = BattleConfig()
    config.initial_shields = 0
    engine = BattleEngine(chart, config)

    # P0 has higher base Attack (125 vs 120) and is NOT shadow.
    # P1 is Shadow (effective damage Attack = 144 > 125) and gets +2 Atk buff,
    # yet P0 MUST still win CMP because CMP uses base Attack only.
    nuke = _make_cm(power=200, energy_cost=35)
    buff_cm = _make_cm(power=1, energy_cost=35, user_atk=2, buff_prob=1.0)
    mon0 = _make_mon(
        attack=125.0, max_hp=100, fast_power=1, fast_energy=50, fast_turns=1, charged=[nuke]
    )
    mon1 = _make_mon(
        attack=120.0,
        max_hp=100,
        is_shadow=True,
        fast_power=1,
        fast_energy=50,
        fast_turns=1,
        charged=[buff_cm, nuke],
    )

    engine.reset([mon0], [mon1], seed=99)
    engine.step(Action.FAST_MOVE, Action.FAST_MOVE)  # Both at 50 energy
    engine.step(Action.WAIT, Action.CHARGED_MOVE_0)  # P1 gets +2 Atk stage
    assert engine.state().teams[1].active.atk_stage == 2

    engine.step(Action.FAST_MOVE, Action.FAST_MOVE)  # P1 back to >= 50 energy
    # Simultaneous CMP: P0 wins CMP and KOs P1 before P1's nuke can fire!
    engine.step(Action.CHARGED_MOVE_0, Action.CHARGED_MOVE_1)
    assert engine.is_done
    assert engine.state().winner == Winner.PLAYER_0
    assert engine.state().teams[0].active.is_alive


def test_cmp_survivor_fires_queued_move_and_tie_is_seeded() -> None:
    chart = _make_neutral_chart()
    config = BattleConfig()
    config.initial_shields = 1
    engine = BattleEngine(chart, config)

    cm = _make_cm(power=30, energy_cost=35)
    mon0 = _make_mon(
        attack=120.0, max_hp=200, fast_power=1, fast_energy=50, fast_turns=1, charged=[cm]
    )
    mon1 = _make_mon(
        attack=120.0, max_hp=200, fast_power=1, fast_energy=50, fast_turns=1, charged=[cm]
    )

    first_attackers = set()
    for seed in range(1, 20):
        engine.reset([mon0], [mon1], seed=seed)
        engine.step(Action.FAST_MOVE, Action.FAST_MOVE)
        engine.step(Action.CHARGED_MOVE_0, Action.CHARGED_MOVE_0)
        assert engine.state().phase == Phase.SHIELD_DECISION
        first = engine.state().cm_attacker
        first_attackers.add(first)

        # First CM is shielded -> queued second CM must immediately trigger ShieldDecision.
        if first == 0:
            engine.step(Action.WAIT, Action.SHIELD)
        else:
            engine.step(Action.SHIELD, Action.WAIT)
        assert engine.state().phase == Phase.SHIELD_DECISION
        assert engine.state().cm_attacker == 1 - first

    # Across 19 seeds, exact Attack tie should have produced both winners.
    assert first_attackers == {0, 1}


# ---------------------------------------------------------------------------
# Shielding, Buffs on Shielded Moves, Faint Stall Clock & Timeout
# ---------------------------------------------------------------------------


def test_shield_deals_1_damage_and_still_applies_buffs() -> None:
    chart = _make_neutral_chart()
    engine = BattleEngine(chart)

    debuff_cm = _make_cm(power=100, energy_cost=35, opp_def=-2, buff_prob=1.0)
    mon0 = _make_mon(max_hp=150, fast_power=1, fast_energy=50, fast_turns=1, charged=[debuff_cm])
    mon1 = _make_mon(max_hp=150, fast_power=1, fast_energy=10, fast_turns=1)

    engine.reset([mon0], [mon1], seed=5)
    engine.step(Action.FAST_MOVE, Action.WAIT)
    hp_before_cm = engine.state().teams[1].active.hp
    engine.step(Action.CHARGED_MOVE_0, Action.WAIT)
    assert engine.state().phase == Phase.SHIELD_DECISION

    engine.step(Action.WAIT, Action.SHIELD)
    st = engine.state()
    assert st.teams[1].shields == 1
    assert st.teams[1].active.hp == hp_before_cm - 1  # exactly 1 damage through shield
    assert st.teams[1].active.def_stage == -2  # buff applied through shield


def test_faint_switch_clock_stall_and_timeout() -> None:
    chart = _make_neutral_chart()
    config = BattleConfig()
    config.initial_shields = 0
    config.faint_switch_max_turns = 24
    engine = BattleEngine(chart, config)

    # P0 switches first to start a 90-turn switch timer, then gets KO'd and stalls 24 turns.
    lead0 = _make_mon(max_hp=10, fast_power=1, fast_energy=1, fast_turns=1)
    back0 = _make_mon(max_hp=150, fast_power=1, fast_energy=1, fast_turns=1)
    lead1 = _make_mon(max_hp=150, fast_power=50, fast_energy=1, fast_turns=1)

    engine.reset([lead0, back0], [lead1], seed=3)
    engine.step(Action.WAIT, Action.FAST_MOVE)
    assert engine.state().phase == Phase.FORCED_SWITCH

    # P0 can WAIT up to 24 turns; each WAIT ticks the universal clock by 1 turn.
    start_turn = engine.state().turn
    for _ in range(24):
        assert Action.WAIT in engine.legal_actions(0)
        engine.step(Action.WAIT, Action.WAIT)

    assert engine.state().turn == start_turn + 24
    assert Action.WAIT not in engine.legal_actions(0)  # must switch now!
    assert engine.legal_actions(0) == [Action.SWITCH_1]

    engine.step(Action.SWITCH_1, Action.WAIT)
    assert engine.state().phase == Phase.TURN
    assert engine.state().teams[0].switch_timer == 0  # forced switch does not trigger timer


def test_timeout_tiebreaker_at_600_turns() -> None:
    chart = _make_neutral_chart()
    config = BattleConfig()
    config.max_turns = 10  # short clock for fast unit test
    engine = BattleEngine(chart, config)

    mon0 = _make_mon(max_hp=200, fast_power=5, fast_energy=1, fast_turns=1)
    mon1 = _make_mon(max_hp=200, fast_power=1, fast_energy=1, fast_turns=1)
    engine.reset([mon0], [mon1], seed=1)

    engine.step(Action.FAST_MOVE, Action.WAIT)  # P0 deals damage so P1 has lower HP%
    while not engine.is_done:
        engine.step(Action.WAIT, Action.WAIT)

    assert engine.state().turn == 10
    assert engine.state().winner == Winner.PLAYER_0


# ---------------------------------------------------------------------------
# Blind State Masking & Real GameData 3v3 Bot Battles
# ---------------------------------------------------------------------------


def test_blind_state_masks_hidden_opponent_info() -> None:
    chart = _make_neutral_chart()
    engine = BattleEngine(chart)
    team0 = [_make_mon(max_hp=150, fast_energy=20, fast_turns=1), _make_mon(max_hp=140)]
    team1 = [_make_mon(max_hp=160, fast_energy=25, fast_turns=1), _make_mon(max_hp=130)]

    engine.reset(team0, team1, seed=1)
    engine.step(Action.FAST_MOVE, Action.FAST_MOVE)

    blind0 = engine.blind_state(0)
    # Player 0 sees their own energy and backline HP.
    assert blind0.teams[0].pokemon[0].energy == 20
    assert blind0.teams[0].pokemon[1].hp == 140
    # Opponent's exact energy is hidden (-1), lead HP is visible, unrevealed backline is -1.
    assert blind0.teams[1].pokemon[0].energy == -1
    assert blind0.teams[1].pokemon[0].hp > 0
    assert blind0.teams[1].pokemon[1].revealed is False
    assert blind0.teams[1].pokemon[1].hp == -1
    assert blind0.teams[1].pokemon[1].max_hp == -1


def test_real_game_data_3v3_deterministic_battles() -> None:
    game_data = load_game_data()

    def build_mon(species_id: str) -> Pokemon:
        sp = game_data.species[species_id]
        return Pokemon(
            sp,
            cp_cap=1500,
            fast_move=sp.fast_moves[0],
            charged_moves=sp.charged_moves[:2],
        )

    all_ids = [
        sid for sid, sp in game_data.species.items() if sp.fast_moves and len(sp.charged_moves) >= 1
    ]
    team0 = to_team_data([build_mon(sid) for sid in all_ids[:3]])
    team1 = to_team_data([build_mon(sid) for sid in all_ids[3:6]])

    engine = create_engine(game_data)

    # GreedyBot vs RandomBot should finish cleanly and be 100% deterministic for a fixed seed.
    engine.reset(team0, team1, seed=12345)
    winner_a = play_battle(engine, GreedyBot(), RandomBot(seed=10))
    turn_a = engine.state().turn
    assert winner_a in (Winner.PLAYER_0, Winner.PLAYER_1, Winner.TIE)
    assert 0 < turn_a <= engine.config().max_turns

    engine.reset(team0, team1, seed=12345)
    winner_b = play_battle(engine, GreedyBot(), RandomBot(seed=10))
    turn_b = engine.state().turn
    assert winner_a == winner_b
    assert turn_a == turn_b
