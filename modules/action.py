"""Typed action-plan model: what the parser LLM may propose.

Mirrors the AnyEvent/AnyModifier/AnyEffect pattern in `event.py`/`modifier.py`/
`effect.py`. Parsing here only recognizes shape (right verb, right number of
arguments) -- it never touches game state and never resolves an item/NPC/
location name to a real entity. That is the Action Validator's job
(`managers/validator.py`); this module's only contract is "is this a
well-formed proposal at all."

The line grammar is unchanged from the old single-call `ACTIONS:` format (the
local model is tuned to it) with two exceptions: `UPDATE_CONDITION health` is
retired (player HP is never LLM-authoritative -- see docs/01-engine-authority.md)
and `ATTACK`/`USE_ITEM` are added so combat and item effects have an entry
point into the Simulation Core instead of being narrated as raw HP deltas.
"""

from collections.abc import Callable
from dataclasses import dataclass

NARRATIVE_CONDITION_FIELDS = ("sleep", "infection_risk")
NUMERIC_CONDITION_FIELDS = ("hunger", "thirst", "morale")


@dataclass
class MoveAction:
    destination: str


@dataclass
class TakeAction:
    item_name: str


@dataclass
class DropAction:
    item_name: str


@dataclass
class AttackAction:
    target_name: str


@dataclass
class UseItemAction:
    item_name: str


@dataclass
class TimeAdvanceAction:
    time_of_day: str


@dataclass
class StatusAddAction:
    status: str


@dataclass
class StatusRemoveAction:
    status: str


@dataclass
class UpdateConditionAction:
    """hunger/thirst/morale/sleep/infection_risk only -- never health."""

    field_name: str
    raw_value: str


@dataclass
class AddGoalAction:
    horizon: str
    goal_text: str


@dataclass
class RemoveGoalAction:
    horizon: str
    goal_text: str


@dataclass
class UpdateRelationshipAction:
    npc_name: str
    axis: str
    amount: int


@dataclass
class AddRelationshipNoteAction:
    npc_name: str
    note: str


@dataclass
class SetFlagAction:
    flag_name: str
    value: bool


@dataclass
class DiscoverFlagAction:
    """The player has learned a world flag's state, whatever it is. Setting a
    flag (engine ground truth) and discovering it (player knowledge) are
    separate actions -- see docs/11-knowledge-firewall.md."""

    flag_name: str


@dataclass
class UpdateInventoryAction:
    item_name: str
    operation: str  # ADD / REMOVE / UPDATE_CONDITION / UPDATE_QUANTITY
    value: str


@dataclass
class NpcMoveAction:
    npc_name: str
    destination: str


@dataclass
class NpcStatusAction:
    npc_name: str
    operation: str  # ADD / REMOVE
    status: str


AnyAction = (
    MoveAction
    | TakeAction
    | DropAction
    | AttackAction
    | UseItemAction
    | TimeAdvanceAction
    | StatusAddAction
    | StatusRemoveAction
    | UpdateConditionAction
    | AddGoalAction
    | RemoveGoalAction
    | UpdateRelationshipAction
    | AddRelationshipNoteAction
    | SetFlagAction
    | DiscoverFlagAction
    | UpdateInventoryAction
    | NpcMoveAction
    | NpcStatusAction
)


@dataclass
class ParseFailure:
    """A line that never became an action -- rejected before validation, and
    therefore before narration, unlike the old post-hoc [CONTINUITY] path."""

    raw: str
    reason: str


class _ActionParseError(ValueError):
    """Internal control flow only; callers see it folded into ParseFailure."""


def _parse_move_to(args: str) -> MoveAction:
    if not args:
        raise _ActionParseError("MOVE_TO needs a destination.")
    return MoveAction(destination=args)


def _parse_take(args: str) -> TakeAction:
    if not args:
        raise _ActionParseError("TAKE needs an item name.")
    return TakeAction(item_name=args)


def _parse_drop(args: str) -> DropAction:
    if not args:
        raise _ActionParseError("DROP needs an item name.")
    return DropAction(item_name=args)


def _parse_attack(args: str) -> AttackAction:
    if not args:
        raise _ActionParseError("ATTACK needs a target.")
    return AttackAction(target_name=args)


def _parse_use_item(args: str) -> UseItemAction:
    if not args:
        raise _ActionParseError("USE_ITEM needs an item name.")
    return UseItemAction(item_name=args)


def _parse_time_advance(args: str) -> TimeAdvanceAction:
    if not args:
        raise _ActionParseError("TIME_ADVANCE needs a time of day.")
    return TimeAdvanceAction(time_of_day=args)


def _parse_status_add(args: str) -> StatusAddAction:
    if not args:
        raise _ActionParseError("STATUS_ADD needs a status name.")
    return StatusAddAction(status=args)


def _parse_status_remove(args: str) -> StatusRemoveAction:
    if not args:
        raise _ActionParseError("STATUS_REMOVE needs a status name.")
    return StatusRemoveAction(status=args)


def _parse_update_condition(args: str) -> UpdateConditionAction:
    field_name, _, raw_value = args.partition(" ")
    field_name = field_name.strip().casefold()
    raw_value = raw_value.strip()
    if not field_name or not raw_value:
        raise _ActionParseError("UPDATE_CONDITION needs a field and a value.")
    if field_name == "health":
        raise _ActionParseError(
            "UPDATE_CONDITION health is not an available action -- health only "
            "changes through combat or item effects, never a declared number."
        )
    if field_name not in NARRATIVE_CONDITION_FIELDS and field_name not in NUMERIC_CONDITION_FIELDS:
        raise _ActionParseError(f"Unknown condition field: '{field_name}'.")
    return UpdateConditionAction(field_name=field_name, raw_value=raw_value)


def _parse_add_goal(args: str) -> AddGoalAction:
    horizon, _, goal = args.partition(" ")
    horizon, goal = horizon.strip().casefold(), goal.strip()
    if not horizon or not goal:
        raise _ActionParseError("ADD_GOAL needs a horizon and goal text.")
    return AddGoalAction(horizon=horizon, goal_text=goal)


def _parse_remove_goal(args: str) -> RemoveGoalAction:
    horizon, _, goal = args.partition(" ")
    horizon, goal = horizon.strip().casefold(), goal.strip()
    if not horizon or not goal:
        raise _ActionParseError("REMOVE_GOAL needs a horizon and goal text.")
    return RemoveGoalAction(horizon=horizon, goal_text=goal)


def _parse_update_relationship(args: str) -> UpdateRelationshipAction:
    parts = args.split()
    if len(parts) < 3:
        raise _ActionParseError(
            "UPDATE_RELATIONSHIP needs a name, an axis, and an amount."
        )
    raw_amount, axis, name = parts[-1], parts[-2].casefold(), " ".join(parts[:-2])
    if not name:
        raise _ActionParseError("UPDATE_RELATIONSHIP needs an NPC name.")
    if axis not in ("affection", "trust"):
        raise _ActionParseError(f"Unknown relationship axis: '{axis}'.")
    try:
        amount = int(raw_amount)
    except ValueError:
        raise _ActionParseError(f"'{raw_amount}' is not a number.") from None
    return UpdateRelationshipAction(npc_name=name, axis=axis, amount=amount)


def _parse_add_relationship_note(args: str) -> AddRelationshipNoteAction:
    name, _, note = args.partition(" ")
    name, note = name.strip(), note.strip()
    if not name or not note:
        raise _ActionParseError("ADD_RELATIONSHIP_NOTE needs a name and note text.")
    return AddRelationshipNoteAction(npc_name=name, note=note)


def _parse_set_flag(args: str) -> SetFlagAction:
    flag, _, raw_value = args.partition(" ")
    flag = flag.strip()
    raw_value = raw_value.strip().casefold()
    if not flag or raw_value not in ("true", "false"):
        raise _ActionParseError(
            f"SET_FLAG needs a flag name and true/false, got '{raw_value}'."
        )
    return SetFlagAction(flag_name=flag, value=raw_value == "true")


def _parse_discover_flag(args: str) -> DiscoverFlagAction:
    flag = args.strip()
    if not flag:
        raise _ActionParseError("DISCOVER_FLAG needs a flag name.")
    return DiscoverFlagAction(flag_name=flag)


_INVENTORY_OPERATIONS = ("ADD", "REMOVE", "UPDATE_CONDITION", "UPDATE_QUANTITY")


def _parse_update_inventory(args: str) -> UpdateInventoryAction:
    parts = args.split()
    index = next(
        (i for i, part in enumerate(parts) if part.upper() in _INVENTORY_OPERATIONS),
        None,
    )
    if index is None or index == 0:
        raise _ActionParseError(
            f"UPDATE_INVENTORY needs an item and one of {_INVENTORY_OPERATIONS}."
        )
    name = " ".join(parts[:index])
    operation = parts[index].upper()
    value = " ".join(parts[index + 1 :]).strip()
    return UpdateInventoryAction(item_name=name, operation=operation, value=value)


def _parse_npc_move(args: str) -> NpcMoveAction:
    name, separator, destination = args.partition(" TO ")
    name, destination = name.strip(), destination.strip()
    if not separator or not name or not destination:
        raise _ActionParseError("NPC_MOVE needs the form '<npc> TO <location>'.")
    return NpcMoveAction(npc_name=name, destination=destination)


_NPC_STATUS_OPERATIONS = ("ADD", "REMOVE")


def _parse_npc_status(args: str) -> NpcStatusAction:
    parts = args.split()
    index = next(
        (i for i, part in enumerate(parts) if part.upper() in _NPC_STATUS_OPERATIONS),
        None,
    )
    if index is None or index == 0:
        raise _ActionParseError("NPC_STATUS needs '<npc> ADD|REMOVE <status>'.")
    name = " ".join(parts[:index])
    operation = parts[index].upper()
    status = " ".join(parts[index + 1 :]).strip()
    if not status:
        raise _ActionParseError("NPC_STATUS needs a status name.")
    return NpcStatusAction(npc_name=name, operation=operation, status=status)


_PARSERS: dict[str, Callable[[str], AnyAction]] = {
    "MOVE_TO": _parse_move_to,
    "TAKE": _parse_take,
    "DROP": _parse_drop,
    "ATTACK": _parse_attack,
    "USE_ITEM": _parse_use_item,
    "TIME_ADVANCE": _parse_time_advance,
    "STATUS_ADD": _parse_status_add,
    "STATUS_REMOVE": _parse_status_remove,
    "UPDATE_CONDITION": _parse_update_condition,
    "ADD_GOAL": _parse_add_goal,
    "REMOVE_GOAL": _parse_remove_goal,
    "UPDATE_RELATIONSHIP": _parse_update_relationship,
    "ADD_RELATIONSHIP_NOTE": _parse_add_relationship_note,
    "SET_FLAG": _parse_set_flag,
    "DISCOVER_FLAG": _parse_discover_flag,
    "UPDATE_INVENTORY": _parse_update_inventory,
    "NPC_MOVE": _parse_npc_move,
    "NPC_STATUS": _parse_npc_status,
}


def parse_action_line(line: str) -> AnyAction | ParseFailure:
    """Parse one already-stripped, non-empty, non-'NONE' action line."""
    verb, _, remainder = line.partition(" ")
    handler = _PARSERS.get(verb.upper())
    if handler is None:
        return ParseFailure(raw=line, reason=f"Unknown action verb: '{verb}'.")
    try:
        return handler(remainder.strip())
    except _ActionParseError as exc:
        return ParseFailure(raw=line, reason=str(exc))


def parse_action_plan(lines: list[str]) -> tuple[list[AnyAction], list[ParseFailure]]:
    """Parse a full ACTIONS: block into well-formed proposals and failures.

    Failures are shape/vocabulary problems only (unknown verb, missing args,
    the retired health field) -- they are rejected before the Action Validator
    ever sees them, and therefore before any prose describing them exists.
    """
    actions: list[AnyAction] = []
    failures: list[ParseFailure] = []
    for raw in lines:
        stripped = raw.strip().lstrip("-").strip()
        if not stripped or stripped.upper() == "NONE":
            continue
        result = parse_action_line(stripped)
        if isinstance(result, ParseFailure):
            failures.append(result)
        else:
            actions.append(result)
    return actions, failures
