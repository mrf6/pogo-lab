"""Bridge utilities converting Python GameData and Pokemon models to C++ engine structs."""

from __future__ import annotations

from collections.abc import Sequence

from pogolab.battle._core import (
    BattleConfig,
    BattleEngine,
    ChargedMoveData,
    ElementType,
    FastMoveData,
    MoveBuffData,
    PokemonData,
    TypeChartData,
)
from pogolab.data.classes import ChargedMove, FastMove, GameData, MoveBuff, Type, TypeChart
from pogolab.pokemon import Pokemon

_TYPE_MAP: dict[Type, ElementType] = {
    Type.NORMAL: ElementType.NORMAL,
    Type.FIRE: ElementType.FIRE,
    Type.WATER: ElementType.WATER,
    Type.GRASS: ElementType.GRASS,
    Type.ELECTRIC: ElementType.ELECTRIC,
    Type.ICE: ElementType.ICE,
    Type.FIGHTING: ElementType.FIGHTING,
    Type.POISON: ElementType.POISON,
    Type.GROUND: ElementType.GROUND,
    Type.FLYING: ElementType.FLYING,
    Type.PSYCHIC: ElementType.PSYCHIC,
    Type.BUG: ElementType.BUG,
    Type.ROCK: ElementType.ROCK,
    Type.GHOST: ElementType.GHOST,
    Type.DRAGON: ElementType.DRAGON,
    Type.DARK: ElementType.DARK,
    Type.STEEL: ElementType.STEEL,
    Type.FAIRY: ElementType.FAIRY,
}


def to_element_type(element: Type) -> ElementType:
    """Convert a Python ``Type`` enum to the C++ ``ElementType`` enum."""
    return _TYPE_MAP[element]


def to_type_chart_data(type_chart: TypeChart) -> TypeChartData:
    """Convert a Python ``TypeChart`` into the C++ ``TypeChartData`` matrix."""
    data = TypeChartData()
    for atk_type, row in type_chart.multipliers.items():
        cpp_atk = _TYPE_MAP[atk_type]
        for def_type, mult in row.items():
            data.set_multiplier(cpp_atk, _TYPE_MAP[def_type], float(mult))
    return data


def to_fast_move_data(move: FastMove) -> FastMoveData:
    """Convert a Python ``FastMove`` into a C++ ``FastMoveData``."""
    data = FastMoveData()
    data.type = _TYPE_MAP[move.type]
    data.power = move.power
    data.energy_gain = move.energy_gain
    data.turns = move.turns
    return data


def to_buff_data(buff: MoveBuff | None) -> MoveBuffData:
    """Convert an optional Python ``MoveBuff`` into a C++ ``MoveBuffData``."""
    data = MoveBuffData()
    if buff is not None:
        data.user_attack = buff.user_attack
        data.user_defense = buff.user_defense
        data.opponent_attack = buff.opponent_attack
        data.opponent_defense = buff.opponent_defense
        data.probability = float(buff.probability)
    return data


def to_charged_move_data(move: ChargedMove) -> ChargedMoveData:
    """Convert a Python ``ChargedMove`` into a C++ ``ChargedMoveData``."""
    data = ChargedMoveData()
    data.type = _TYPE_MAP[move.type]
    data.power = move.power
    data.energy_cost = move.energy_cost
    data.buff = to_buff_data(move.buff)
    return data


def to_pokemon_data(pokemon: Pokemon) -> PokemonData:
    """Convert a configured Python ``Pokemon`` into a C++ ``PokemonData``."""
    if pokemon.fast_move is None:
        raise ValueError(f"Pokemon '{pokemon.species.id}' must have a fast_move assigned")

    stats = pokemon.stats
    data = PokemonData()
    data.attack = float(stats.attack)
    data.defense = float(stats.defense)
    data.max_hp = int(stats.hp)
    data.is_shadow = pokemon.is_shadow

    types = pokemon.species.types
    t0 = _TYPE_MAP[types[0]] if len(types) >= 1 else ElementType.NONE
    t1 = _TYPE_MAP[types[1]] if len(types) >= 2 else ElementType.NONE
    data.types = [t0, t1]

    data.fast_move = to_fast_move_data(pokemon.fast_move)

    charged_list = [ChargedMoveData(), ChargedMoveData()]
    for idx, move in enumerate(pokemon.charged_moves):
        charged_list[idx] = to_charged_move_data(move)
    data.charged_moves = charged_list
    data.num_charged_moves = len(pokemon.charged_moves)
    return data


def to_team_data(team: Sequence[Pokemon]) -> list[PokemonData]:
    """Convert a sequence of 1-3 configured ``Pokemon`` into C++ ``PokemonData`` objects."""
    return [to_pokemon_data(mon) for mon in team]


def create_engine(game_data: GameData, config: BattleConfig | None = None) -> BattleEngine:
    """Create a ``BattleEngine`` initialized with the project's ``GameData`` type chart."""
    chart = to_type_chart_data(game_data.type_chart)
    return BattleEngine(chart, config if config is not None else BattleConfig())
