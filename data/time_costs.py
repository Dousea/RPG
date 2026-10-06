"""Time cost of each action, in in-game minutes (spec 01).

A row is a fixed number of minutes or a function of the action and what the
validator resolved for it, so a function never re-derives what the check
already decided.
"""

from collections.abc import Callable

from modules.action.types import (
    AddGoalAction,
    AddRelationshipNoteAction,
    AnyAction,
    AttackAction,
    DiscoverFlagAction,
    DropAction,
    ExerciseAction,
    MoveAction,
    NpcMoveAction,
    NpcStatusAction,
    RemoveGoalAction,
    SetFlagAction,
    SleepAction,
    StatusAddAction,
    StatusRemoveAction,
    TakeAction,
    TakeOffAction,
    UpdateConditionAction,
    UpdateInventoryAction,
    UpdateRelationshipAction,
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
    MoveToSpot,
    MoveToZone,
    Resolution,
    ShuffleInZone,
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
TALK_MIN = 5  # spec 01
NONE_TURN_MIN = 1  # spec 01

CostFunction = Callable[[AnyAction, Resolution], int]


def zone_hop_minutes() -> int:
    """Minutes per zone hop; every pace costs the walking figure until zombies land."""
    return ZONE_HOP_MIN


def _use_item_minutes(action: AnyAction, resolved: Resolution) -> int:
    match resolved:
        case HeldItem(entity=ItemEntity(item=ConsumableItem() as item)):
            return item.eat_minutes
    return QUICK_ACTION_MIN


def _move_minutes(action: AnyAction, resolved: Resolution) -> int:
    match resolved:
        case MoveToZone(hops=hops):
            return hops * zone_hop_minutes()
        case MoveBlocked(hops=hops):
            return max(hops * zone_hop_minutes(), WALK_TO_BARRIER_MIN)
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
    AttackAction: SWING_MIN,
    TakeAction: QUICK_ACTION_MIN,
    DropAction: QUICK_ACTION_MIN,
    WearAction: WEAR_MINUTES,
    TakeOffAction: TAKE_OFF_MINUTES,
    UseItemAction: _use_item_minutes,
    MoveAction: _move_minutes,
    WaitAction: _spent_minutes,
    SleepAction: _spent_minutes,
    ExerciseAction: _exercise_minutes,
    StatusAddAction: 0,
    StatusRemoveAction: 0,
    UpdateConditionAction: 0,
    AddGoalAction: 0,
    RemoveGoalAction: 0,
    UpdateRelationshipAction: 0,
    AddRelationshipNoteAction: 0,
    SetFlagAction: 0,
    DiscoverFlagAction: 0,
    UpdateInventoryAction: 0,
    NpcMoveAction: 0,
    NpcStatusAction: 0,
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
