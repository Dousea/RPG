"""Time cost of each action, in in-game minutes (spec 01).

A row is a fixed number of minutes or a function of the resolved action. The
validator's `resolved` dict is the second argument, so a function never
re-derives what the check already decided.
"""

from collections.abc import Callable
from typing import Any

from modules.action import (
    AddGoalAction,
    AddRelationshipNoteAction,
    AnyAction,
    AttackAction,
    DiscoverFlagAction,
    DropAction,
    MoveAction,
    NpcMoveAction,
    NpcStatusAction,
    RemoveGoalAction,
    SetFlagAction,
    SleepAction,
    StatusAddAction,
    StatusRemoveAction,
    TakeAction,
    UpdateConditionAction,
    UpdateInventoryAction,
    UpdateRelationshipAction,
    UseItemAction,
    WaitAction,
)
from modules.item import ConsumableItem

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

CostFunction = Callable[[AnyAction, dict[str, Any]], int]


def zone_hop_minutes() -> int:
    """Minutes per zone hop; every pace costs the walking figure until zombies land."""
    return ZONE_HOP_MIN


def _use_item_minutes(action: AnyAction, resolved: dict[str, Any]) -> int:
    item = resolved["item_entity"].item
    return item.eat_minutes if isinstance(item, ConsumableItem) else QUICK_ACTION_MIN


def _move_minutes(action: AnyAction, resolved: dict[str, Any]) -> int:
    kind = resolved["kind"]
    if kind == "zone":
        return resolved["hops"] * zone_hop_minutes()
    if kind == "blocked":
        return max(resolved["hops"] * zone_hop_minutes(), WALK_TO_BARRIER_MIN)
    if kind == "spot":
        return QUICK_ACTION_MIN if resolved.get("place") else 0
    if kind == "shuffle":
        return QUICK_ACTION_MIN
    return 0


def _spent_minutes(action: AnyAction, resolved: dict[str, Any]) -> int:
    return resolved["minutes"]


TIME_COSTS: dict[type, int | CostFunction] = {
    AttackAction: SWING_MIN,
    TakeAction: QUICK_ACTION_MIN,
    DropAction: QUICK_ACTION_MIN,
    UseItemAction: _use_item_minutes,
    MoveAction: _move_minutes,
    WaitAction: _spent_minutes,
    SleepAction: _spent_minutes,
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


MULTIPLIED_ACTIONS: tuple[type, ...] = (TakeAction, DropAction, UseItemAction)  # spec 01


def action_minutes(action: AnyAction, resolved: dict[str, Any]) -> int:
    """Whole minutes an accepted action takes, before any multiplier."""
    cost = TIME_COSTS.get(type(action), 0)
    return cost(action, resolved) if callable(cost) else cost
