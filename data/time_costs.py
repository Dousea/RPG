"""Time cost of each action, in in-game minutes (clock).

A row is a fixed number of minutes or a function of the action and what the
validator resolved for it, so a function never re-derives what the check
already decided.
"""

from collections.abc import Callable

from data.carry import CARRY_CORPSE_MIN
from data.world.barriers import BARRICADE_MIN, UNBARRICADE_MIN
from modules import units
from modules.action.parser import TALK_TURN_MINUTES
from modules.action.types import (
    AddGoalAction,
    AddRelationshipNoteAction,
    AnyAction,
    AskAction,
    AttackAction,
    BandageAction,
    BarricadeAction,
    CarryAction,
    CloseAction,
    DisinfectAction,
    DropAction,
    EquipAction,
    ExerciseAction,
    GiveAction,
    MoveAction,
    OpenAction,
    PutAction,
    RemoveBandageAction,
    RemoveGoalAction,
    SearchAction,
    ShoutAction,
    ShoveAction,
    SleepAction,
    StanceAction,
    TakeAction,
    TakeOffAction,
    TalkAction,
    UnbarricadeAction,
    UnequipAction,
    UseItemAction,
    WaitAction,
    WearAction,
)
from modules.entity.item import ItemEntity
from modules.item import ConsumableItem
from modules.resolution import (
    ExercisePlan,
    HeldItem,
    MoveBlocked,
    MoveToRoom,
    MoveToSpot,
    MoveToZone,
    Resolution,
    ShuffleInZone,
    TargetCorpse,
    TargetZombie,
    TimeSpan,
    Transfer,
)
from modules.world.pace import Pace

SWING_MIN = 1  # melee
SEARCH_MIN = 1  # zombie-lifecycle
OPEN_CONTAINER_MIN = 1  # carrying-and-loot
MOVE_ROOM_MIN = 1  # carrying-and-loot
EQUIP_MIN = 1  # clock
UNEQUIP_MIN = 1  # clock
QUICK_ACTION_MIN = 1  # clock
WALK_TO_BARRIER_MIN = 1  # clock
WINDOW_CLIMB_MIN = 1  # clock
WEAR_MINUTES = 1  # clock
TAKE_OFF_MINUTES = 1  # clock
FIRST_AID_MINUTES = 1  # health
ZONE_HOP_MIN = 10  # clock
ZONE_HOP_RUNNING_MIN = 5  # clock
ZONE_HOP_SNEAKING_MIN = 20  # clock
MAX_PLAN_ACTIONS = 5  # llm-contract: actions resolved per turn
NONE_TURN_MINUTES = 1  # llm-contract

CostFunction = Callable[[AnyAction, Resolution], int]


HOP_MINUTES_BY_PACE = {  # zombies
    Pace.WALK: ZONE_HOP_MIN,
    Pace.RUN: ZONE_HOP_RUNNING_MIN,
    Pace.SNEAK: ZONE_HOP_SNEAKING_MIN,
}


def zone_hop_minutes(pace: Pace = Pace.WALK) -> int:
    """Minutes one zone hop takes at a pace."""
    return HOP_MINUTES_BY_PACE[pace]


def _attack_minutes(action: AnyAction, resolved: Resolution) -> int:
    """The swing, plus the walk up to a zombie that is not yet in reach."""
    if isinstance(resolved, TargetZombie):
        return resolved.approach_minutes + SWING_MIN
    return SWING_MIN


def _search_minutes(action: AnyAction, resolved: Resolution) -> int:
    """The walk up to a corpse that is not yet in reach, plus the minute going through it.

    A room or container search is charged per container as it is opened."""
    match resolved:
        case TargetCorpse(approach_minutes=approach):
            return approach + SEARCH_MIN
    return SEARCH_MIN


def _transfer_minutes(action: AnyAction, resolved: Resolution) -> int:
    """A move of items: its frames by the shared rule."""
    if isinstance(resolved, Transfer):
        return units.minutes_from_timed_action_frames(resolved.frames)
    return QUICK_ACTION_MIN


def _carry_minutes(action: AnyAction, resolved: Resolution) -> int:
    """The walk up to a body that is not yet in reach, plus the minute picking it up."""
    if isinstance(resolved, TargetCorpse):
        return resolved.approach_minutes + CARRY_CORPSE_MIN
    return CARRY_CORPSE_MIN


def _use_item_minutes(action: AnyAction, resolved: Resolution) -> int:
    match resolved:
        case HeldItem(entity=ItemEntity(item=ConsumableItem() as item)):
            return item.eat_minutes
    return QUICK_ACTION_MIN


def _move_minutes(action: AnyAction, resolved: Resolution) -> int:
    match resolved:
        case MoveToZone(hops=hops, pace=pace):
            return hops * zone_hop_minutes(pace)
        case MoveBlocked(hops=hops, pace=pace):
            return max(hops * zone_hop_minutes(pace), WALK_TO_BARRIER_MIN)
        case MoveToRoom():
            return MOVE_ROOM_MIN
        case MoveToSpot(place=place):
            return QUICK_ACTION_MIN if place else 0
        case ShuffleInZone():
            return QUICK_ACTION_MIN
    return 0


def _spent_minutes(action: AnyAction, resolved: Resolution) -> int:
    return resolved.minutes if isinstance(resolved, TimeSpan) else 0


def _exercise_minutes(action: AnyAction, resolved: Resolution) -> int:
    """The chosen minutes of an exercise plan, or the minutes run when it stops early."""
    match resolved:
        case ExercisePlan(minutes=minutes) | TimeSpan(minutes=minutes):
            return minutes
    return 0


TIME_COSTS: dict[type, int | CostFunction] = {
    AttackAction: _attack_minutes,
    OpenAction: 0,
    CloseAction: 0,
    BarricadeAction: BARRICADE_MIN,
    UnbarricadeAction: UNBARRICADE_MIN,
    ShoveAction: _attack_minutes,
    SearchAction: _search_minutes,
    EquipAction: EQUIP_MIN,
    UnequipAction: UNEQUIP_MIN,
    TakeAction: _transfer_minutes,
    DropAction: _transfer_minutes,
    PutAction: _transfer_minutes,
    CarryAction: _carry_minutes,
    WearAction: WEAR_MINUTES,
    TakeOffAction: TAKE_OFF_MINUTES,
    UseItemAction: _use_item_minutes,
    BandageAction: FIRST_AID_MINUTES,
    RemoveBandageAction: FIRST_AID_MINUTES,
    DisinfectAction: FIRST_AID_MINUTES,
    MoveAction: _move_minutes,
    StanceAction: 0,
    WaitAction: _spent_minutes,
    SleepAction: _spent_minutes,
    ExerciseAction: _exercise_minutes,
    ShoutAction: 0,
    TalkAction: TALK_TURN_MINUTES,
    AskAction: TALK_TURN_MINUTES,
    GiveAction: TALK_TURN_MINUTES,
    AddGoalAction: 0,
    RemoveGoalAction: 0,
    AddRelationshipNoteAction: 0,
}


MULTIPLIED_ACTIONS: tuple[type, ...] = (
    TakeAction,
    DropAction,
    PutAction,
    UseItemAction,
    WearAction,
    TakeOffAction,
    EquipAction,
    UnequipAction,
    BandageAction,
    RemoveBandageAction,
    DisinfectAction,
    BarricadeAction,
    UnbarricadeAction,
)  # health: 13


def action_minutes(action: AnyAction, resolved: Resolution) -> int:
    """Whole minutes an accepted action takes, before any multiplier."""
    cost = TIME_COSTS.get(type(action), 0)
    return cost(action, resolved) if callable(cost) else cost
