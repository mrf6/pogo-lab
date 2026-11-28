"""Simple baseline bots for testing, debugging, and benchmarking the battle engine."""

from __future__ import annotations

import random
from typing import Protocol

from pogo_lab.battle._core import Action, BattleEngine, Phase, Winner


class BattleBot(Protocol):
    """Protocol for a battle-playing agent."""

    def choose_action(self, engine: BattleEngine, player: int) -> Action:
        """Choose a legal ``Action`` for ``player`` given the current engine state."""
        ...


class RandomBot:
    """Selects uniformly at random among legal actions."""

    def __init__(self, seed: int | None = None) -> None:
        self._rng = random.Random(seed)

    def choose_action(self, engine: BattleEngine, player: int) -> Action:
        actions = engine.legal_actions(player)
        return self._rng.choice(actions)


class GreedyBot:
    """Simple heuristic bot: fires highest-power affordable charged move, shields if available."""

    def choose_action(self, engine: BattleEngine, player: int) -> Action:
        actions = engine.legal_actions(player)
        if len(actions) == 1:
            return actions[0]

        state = engine.state()
        phase = state.phase

        if phase == Phase.SHIELD_DECISION:
            return Action.SHIELD if Action.SHIELD in actions else Action.NO_SHIELD

        if phase == Phase.FORCED_SWITCH:
            for action in actions:
                if action in (Action.SWITCH_0, Action.SWITCH_1, Action.SWITCH_2):
                    return action
            return Action.WAIT

        if phase == Phase.POST_CHARGED_SWITCH:
            return Action.WAIT

        # Normal Turn: prefer highest-power affordable charged move, else fast move.
        active_idx = state.teams[player].active_idx
        mon_data = engine.pokemon_data(player, active_idx)

        best_cm: Action | None = None
        best_power = -1
        for cm_idx, action in ((0, Action.CHARGED_MOVE_0), (1, Action.CHARGED_MOVE_1)):
            if action in actions:
                power = mon_data.charged_moves[cm_idx].power
                if power > best_power:
                    best_power = power
                    best_cm = action
        if best_cm is not None:
            return best_cm

        if Action.FAST_MOVE in actions:
            return Action.FAST_MOVE
        return actions[0]


def play_battle(
    engine: BattleEngine,
    bot0: BattleBot,
    bot1: BattleBot,
    *,
    max_steps: int = 5000,
) -> Winner:
    """Run a battle already initialized with ``engine.reset(...)`` to completion."""
    for _ in range(max_steps):
        if engine.is_done:
            return engine.state().winner
        a0 = bot0.choose_action(engine, 0)
        a1 = bot1.choose_action(engine, 1)
        engine.step(a0, a1)
    raise RuntimeError(f"Battle did not finish within {max_steps} decision steps")
