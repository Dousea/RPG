"""Parsing of the parser LLM's ACTIONS lines into typed actions.

Parsing recognizes shape only (right verb, right number of arguments). It
never touches game state and never resolves an item, NPC or location name to
a real entity; that is the Action Validator's job (`managers/validator.py`).
`UPDATE_CONDITION health` is refused here because player HP is never
LLM-authoritative (docs/01-engine-authority.md).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass

from modules.action.types import (
    AddGoalAction,
    AddRelationshipNoteAction,
    AnyAction,
    AttackAction,
    DiscoverFlagAction,
    DropAction,
    Duration,
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

NARRATIVE_CONDITION_FIELDS = ("sleep", "infection_risk")
NUMERIC_CONDITION_FIELDS = ("hunger", "thirst", "morale")

# Goal horizons the model writes in place of the two real ones.
GOAL_HORIZON_SYNONYMS = {
    "short": "short_term",
    "shortterm": "short_term",
    "short_term": "short_term",
    "long": "long_term",
    "longterm": "long_term",
    "long_term": "long_term",
}

# Truthy/falsy words the model writes instead of a bare true/false.
_FLAG_VALUES = {
    "true": True,
    "yes": True,
    "1": True,
    "on": True,
    "false": False,
    "no": False,
    "0": False,
    "off": False,
}


def normalize_key(raw: str) -> str:
    """Fold an enum-ish argument into its canonical form.

    The parser LLM writes these as prose -- 'short_term:', 'Short Term',
    'short-term' -- and a strict match rejects all but one of them, silently
    dropping the state change while the story carries on as if it happened.
    """
    return raw.strip().strip(":,.;\"'").replace("-", "_").replace(" ", "_").casefold()


@dataclass
class ParseFailure:
    """A line that never became an action; rejected before validation and narration."""

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


_SPAN_PATTERN = re.compile(r"(?:(\d+)\s*h)?\s*(?:(\d+)\s*m)?")
_CLOCK_TIME_PATTERN = re.compile(r"(\d{1,2}):(\d{2})")
_TIME_OF_DAY_PATTERN = re.compile(r"[a-z]+")


def _parse_duration(verb: str, args: str) -> Duration:
    """Parse '10m', '2h', '1h30m', 'until <time of day>' or 'until HH:MM'."""
    text = args.strip().strip(".,;").casefold()
    if text.startswith("until "):
        target = text[len("until ") :].strip()
        clock = _CLOCK_TIME_PATTERN.fullmatch(target)
        if clock:
            hour, minute = int(clock.group(1)), int(clock.group(2))
            if hour > 23 or minute > 59:
                raise _ActionParseError(f"{verb} has no such clock time: '{target}'.")
            return Duration(until_minute_of_day=hour * 60 + minute)
        if _TIME_OF_DAY_PATTERN.fullmatch(target):
            return Duration(until_time_of_day=target)
        raise _ActionParseError(f"{verb} needs 'until <time of day>' or 'until HH:MM'.")
    span = _SPAN_PATTERN.fullmatch(text)
    if span is None or not (span.group(1) or span.group(2)):
        raise _ActionParseError(f"{verb} needs a duration like 10m, 2h, 1h30m or until night.")
    minutes = int(span.group(1) or 0) * 60 + int(span.group(2) or 0)
    if minutes <= 0:
        raise _ActionParseError(f"{verb} needs a duration longer than zero.")
    return Duration(minutes=minutes)


def _parse_wait(args: str) -> WaitAction:
    if not args:
        raise _ActionParseError("WAIT needs a duration.")
    return WaitAction(duration=_parse_duration("WAIT", args))


def _parse_sleep(args: str) -> SleepAction:
    if not args:
        return SleepAction()
    return SleepAction(duration=_parse_duration("SLEEP", args))


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
    field_name = normalize_key(field_name)
    raw_value = raw_value.strip().strip(".,;")
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


def _split_goal(args: str) -> tuple[str, str]:
    """Split '<horizon> <goal text>' tolerantly.

    The horizon may arrive as 'short_term', 'short-term', 'Short Term' or
    'short_term:' -- the model uses all of them. 'Short Term' costs a second
    word, so try the two-word reading before the one-word one. If neither
    matches a known synonym, fall back to the normalized first word so the
    validator's "Unknown goal horizon" rejection still fires downstream,
    instead of this function silently swallowing the whole line.
    """
    parts = args.split()
    if not parts:
        return "", ""
    for word_count in (2, 1):
        if len(parts) < word_count:
            continue
        horizon = GOAL_HORIZON_SYNONYMS.get(normalize_key(" ".join(parts[:word_count])))
        if horizon is not None:
            return horizon, " ".join(parts[word_count:]).strip()
    return normalize_key(parts[0]), " ".join(parts[1:]).strip()


def _parse_add_goal(args: str) -> AddGoalAction:
    horizon, goal = _split_goal(args)
    if not horizon or not goal:
        raise _ActionParseError("ADD_GOAL needs a horizon and goal text.")
    return AddGoalAction(horizon=horizon, goal_text=goal)


def _parse_remove_goal(args: str) -> RemoveGoalAction:
    horizon, goal = _split_goal(args)
    if not horizon or not goal:
        raise _ActionParseError("REMOVE_GOAL needs a horizon and goal text.")
    return RemoveGoalAction(horizon=horizon, goal_text=goal)


def _parse_update_relationship(args: str) -> UpdateRelationshipAction:
    parts = args.split()
    if len(parts) < 3:
        raise _ActionParseError("UPDATE_RELATIONSHIP needs a name, an axis, and an amount.")
    raw_amount, axis, name = (
        parts[-1].strip(".,;"),
        normalize_key(parts[-2]),
        " ".join(parts[:-2]),
    )
    if axis == "affinity":
        axis = "affection"
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
    value = _FLAG_VALUES.get(normalize_key(raw_value))
    if not flag or value is None:
        raise _ActionParseError(
            f"SET_FLAG needs a flag name and true/false, got '{raw_value.strip()}'."
        )
    return SetFlagAction(flag_name=normalize_key(flag), value=value)


def _parse_discover_flag(args: str) -> DiscoverFlagAction:
    flag = args.strip()
    if not flag:
        raise _ActionParseError("DISCOVER_FLAG needs a flag name.")
    return DiscoverFlagAction(flag_name=normalize_key(flag))


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
    "WAIT": _parse_wait,
    "SLEEP": _parse_sleep,
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
