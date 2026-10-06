"""Time cost of each action, in in-game minutes (spec 01).

A row is a fixed number of minutes or a function of the action and what the
validator resolved for it, so a function never re-derives what the check
already decided.
"""

from collections.abc import Callable

from modules.action.parser import TALK_TURN_MINUTES
from modules.action.types import (
    AddGoalAction,
    AddRelationshipNoteAction,
    AnyAction,
    AskAction,
    AttackAction,
    DropAction,
    ExerciseAction,
    GiveAction,
    MoveAction,
    RemoveGoalAction,
    ShoutAction,
    SleepAction,
    StanceAction,
    TakeAction,
    TakeOffAction,
    TalkAction,
    UseItemAction,
    WaitAction,
    WearAction,
)
from modules.entity.item import ItemEntity
from modules.item import ConsumableItem
from modules.pace import Pace
from modules.resolution import (
    ExercisePlan,
    HeldItem,
    MoveBlocked,
    MoveToSpot,
    MoveToZone,
    Resolution,
    ShuffleInZone,
    TargetZombie,
    TimeSpan,
)

SWING_MIN = 1  # spec 01
QUICK_ACTION_MIN = 1  # spec 01
WALK_TO_BARRIER_MIN = 1  # spec 01
WINDOW_CLIMB_MIN = 1  # spec 01
WEAR_MINUTES = 1  # spec 01
TAKE_OFF_MINUTES = 1  # spec 01
ZONE_HOP_MIN = 10  # spec 01
ZONE_HOP_RUNNING_MIN = 5  # spec 01
ZONE_HOP_SNEAKING_MIN = 20  # spec 01
MAX_PLAN_ACTIONS = 5  # spec 10: actions resolved per turn
NONE_TURN_MINUTES = 1  # spec 10

CostFunction = Callable[[AnyAction, Resolution], int]


HOP_MINUTES_BY_PACE = {  # spec 09
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
    TakeAction: QUICK_ACTION_MIN,
    DropAction: QUICK_ACTION_MIN,
    WearAction: WEAR_MINUTES,
    TakeOffAction: TAKE_OFF_MINUTES,
    UseItemAction: _use_item_minutes,
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
    UseItemAction,
    WearAction,
    TakeOffAction,
)  # spec 01


def action_minutes(action: AnyAction, resolved: Resolution) -> int:
    """Whole minutes an accepted action takes, before any multiplier."""
    cost = TIME_COSTS.get(type(action), 0)
    return cost(action, resolved) if callable(cost) else cost
