"""The per-turn JSON schema for the parser's plan, and the plan read back into actions.

The schema constrains what the parser model may emit; it changes no rule. Each
JSON action is turned back into the action line the grammar in
`modules/action/parser.py` accepts and goes through `parse_action_plan`, so
validation, refusals and facts are the same for both formats. Pure: the caller
decodes the JSON text and sends the schema.
"""

from collections.abc import Callable, Mapping
from dataclasses import dataclass
from typing import Any

from modules.action.parser import (
    GOAL_HORIZON_LABELS,
    REQUEST_LABELS,
    TALK_APPROACH_LABELS,
    UNSUPPORTED_TEXT_MAX_CHARS,
    ParseFailure,
    Verb,
    parse_action_plan,
)
from modules.action.types import UNTIL_IT_GIVES, AnyAction

JsonObject = dict[str, Any]

STANCE_LABELS = ("sneak", "stand")
ALL_WORD = "all"


@dataclass(frozen=True)
class SceneChoices:
    """The closed sets of names the scene offers, each in the order the prompt lists them."""

    items_here: tuple[str, ...] = ()
    carried: tuple[str, ...] = ()
    held: tuple[str, ...] = ()
    wearable: tuple[str, ...] = ()
    worn: tuple[str, ...] = ()
    npcs: tuple[str, ...] = ()
    zombie_ids: tuple[str, ...] = ()
    corpse_ids: tuple[str, ...] = ()
    corpse_items: tuple[str, ...] = ()
    bags: tuple[str, ...] = ()
    rooms: tuple[str, ...] = ()
    containers: tuple[str, ...] = ()
    open_containers: tuple[str, ...] = ()
    container_items: tuple[str, ...] = ()
    bag_items: tuple[str, ...] = ()
    hurt_parts: tuple[str, ...] = ()
    bandaged_parts: tuple[str, ...] = ()
    bandages: tuple[str, ...] = ()
    disinfectants: tuple[str, ...] = ()
    npc_items: tuple[str, ...] = ()
    topics: tuple[str, ...] = ()
    barriers: tuple[str, ...] = ()
    exercises: tuple[str, ...] = ()
    exercise_minutes: tuple[int, ...] = ()
    times_of_day: tuple[str, ...] = ()


def _string() -> JsonObject:
    return {"type": "string"}


def _speech_property() -> JsonObject:
    return {
        "type": "string",
        "description": (
            "The character's words. Quote them from the input when the player quoted them; "
            "otherwise the gist of what the player said they say, in the character's voice. "
            "Empty only when the input gives no words at all."
        ),
    }


def _one_of(names: tuple[str, ...]) -> JsonObject:
    return {"type": "string", "enum": list(dict.fromkeys(names))}


def _branch(
    verb: str, required: Mapping[str, JsonObject], optional: Mapping[str, JsonObject] | None = None
) -> JsonObject:
    properties: JsonObject = {"verb": {"const": verb}, **required, **(optional or {})}
    return {
        "type": "object",
        "properties": properties,
        "required": ["verb", *required],
        "additionalProperties": False,
    }


def _duration_pattern(times_of_day: tuple[str, ...]) -> str:
    """Spans such as 10m, 2h, 1h30m, and 'until <time of day>' or 'until HH:MM'."""
    span = r"[1-9]\d{0,2}h(?:[0-5]?\dm)?|[1-9]\d{0,2}m"
    clock = r"(?:[01]?\d|2[0-3]):[0-5]\d"
    until = "|".join([*times_of_day, clock])
    return f"^(?:{span}|until (?:{until}))$"


def _verb_branch(name: str, choices: SceneChoices) -> JsonObject | None:
    """The schema branch for one verb, or None when a required closed set is empty."""
    text = _string()
    match name:
        case "MOVE_TO":
            return _branch(name, {"destination": text}, {"run": {"type": "boolean"}})
        case "STANCE":
            return _branch(name, {"stance": _one_of(STANCE_LABELS)})
        case "WAIT":
            pattern = {"type": "string", "pattern": _duration_pattern(choices.times_of_day)}
            return _branch(name, {"duration": pattern})
        case "SLEEP":
            pattern = {"type": "string", "pattern": _duration_pattern(choices.times_of_day)}
            return _branch(name, {}, {"duration": pattern})
        case "TAKE":
            return _take_branch(name, choices)
        case "SEARCH" | "CARRY":
            nearest = ("corpse",) if choices.corpse_ids else ()
            places = (*choices.rooms, *choices.containers) if name == "SEARCH" else ()
            return _target_branch(name, (*choices.corpse_ids, *nearest, *places))
        case "PUT":
            targets = (*choices.bags, *choices.open_containers)
            if not choices.carried or not targets:
                return None
            return _branch(name, {"item": _one_of(choices.carried), "bag": _one_of(targets)})
        case "DROP" | "USE_ITEM" | "EQUIP":
            return _item_branch(name, choices.carried)
        case "WEAR":
            return _item_branch(name, choices.wearable)
        case "TAKE_OFF":
            return _item_branch(name, choices.worn)
        case "UNEQUIP":
            return _item_branch(name, choices.held)
        case "BANDAGE":
            return _first_aid_branch(name, choices.hurt_parts, choices.bandages)
        case "DISINFECT":
            return _first_aid_branch(name, choices.hurt_parts, choices.disinfectants)
        case "REMOVE_BANDAGE":
            if not choices.bandaged_parts:
                return None
            return _branch(name, {"body_part": _one_of(choices.bandaged_parts)})
        case "EXERCISE":
            if not choices.exercises:
                return None
            minutes: JsonObject = {"type": "integer", "enum": list(choices.exercise_minutes)}
            return _branch(
                name,
                {"exercise": _one_of(choices.exercises)},
                {"minutes": minutes} if choices.exercise_minutes else None,
            )
        case "ATTACK":
            nearest = ("zombie",) if choices.zombie_ids else ()
            return _target_branch(name, (*choices.npcs, *choices.zombie_ids, *nearest))
        case "OPEN" | "CLOSE" | "LOCK" | "UNLOCK" | "BARRICADE" | "UNBARRICADE":
            return _target_branch(name, choices.barriers)
        case "SHOVE":
            return _target_branch(name, choices.zombie_ids)
        case "SHOUT":
            return _branch(name, {})
        case "TALK":
            if not choices.npcs:
                return None
            return _branch(
                name,
                {
                    "npc": _one_of(choices.npcs),
                    "approach": _one_of(TALK_APPROACH_LABELS),
                    "speech": _speech_property(),
                },
            )
        case "GIVE":
            if not choices.carried or not choices.npcs:
                return None
            return _branch(name, {"item": _one_of(choices.carried), "npc": _one_of(choices.npcs)})
        case "ADD_GOAL" | "REMOVE_GOAL":
            return _branch(name, {"horizon": _one_of(GOAL_HORIZON_LABELS), "text": text})
        case "ADD_RELATIONSHIP_NOTE":
            if not choices.npcs:
                return None
            return _branch(name, {"npc": _one_of(choices.npcs), "note": text})
        case "UNSUPPORTED":
            return _branch(
                name, {"text": {"type": "string", "maxLength": UNSUPPORTED_TEXT_MAX_CHARS}}
            )
    return None


def _take_branch(name: str, choices: SceneChoices) -> JsonObject | None:
    """TAKE an item off the ground, from a searched corpse or out of a carried bag when one is named; or all."""
    names = (
        *choices.items_here,
        *choices.corpse_items,
        *choices.bag_items,
        *choices.container_items,
    )
    if not names:
        return None
    sources = (
        *(choices.corpse_ids if choices.corpse_items else ()),
        *choices.bags,
        *(choices.open_containers if choices.container_items else ()),
    )
    optional = {"from": _one_of(sources)} if sources else None
    return _branch(name, {"item": _one_of((*names, ALL_WORD))}, optional)


def _item_branch(name: str, names: tuple[str, ...]) -> JsonObject | None:
    return _branch(name, {"item": _one_of(names)}) if names else None


def _target_branch(name: str, names: tuple[str, ...]) -> JsonObject | None:
    return _branch(name, {"target": _one_of(names)}) if names else None


def _first_aid_branch(
    name: str, parts: tuple[str, ...], items: tuple[str, ...]
) -> JsonObject | None:
    if not parts:
        return None
    return _branch(name, {"body_part": _one_of(parts)}, {"item": _one_of(items)} if items else None)


def _request_branches(name: str, choices: SceneChoices) -> list[JsonObject]:
    """One branch per kind of request, so a request for an item or a topic must name one."""
    if not choices.npcs:
        return []
    npc = {"npc": _one_of(choices.npcs)}
    plain = tuple(r for r in REQUEST_LABELS if r not in ("give", "about"))
    asks = [_branch(name, {**npc, "request": _one_of(plain)})]
    if choices.npc_items:
        request = {"request": _one_of(("give",))}
        asks.append(_branch(name, {**npc, **request, "item": _one_of(choices.npc_items)}))
    if choices.topics:
        request = {"request": _one_of(("about",))}
        asks.append(_branch(name, {**npc, **request, "topic": _one_of(choices.topics)}))
    return asks


def _swings_property() -> JsonObject:
    return {
        "oneOf": [
            {"type": "integer", "minimum": 1},
            {"const": UNTIL_IT_GIVES},
        ],
        "description": (
            "How many swings at the door or window: 1 for a single hit, the number the player "
            f"said, or '{UNTIL_IT_GIVES}' for 'keep hitting it' or 'break it down'."
        ),
    }


def _attack_barrier_branch(choices: SceneChoices) -> JsonObject | None:
    if not choices.barriers:
        return None
    return _branch("ATTACK", {"target": _one_of(choices.barriers), "swings": _swings_property()})


def _verb_branches(name: str, choices: SceneChoices) -> list[JsonObject]:
    if name == "REQUEST":
        return _request_branches(name, choices)
    if name == "ATTACK":
        branches = (_verb_branch(name, choices), _attack_barrier_branch(choices))
        return [branch for branch in branches if branch is not None]
    branch = _verb_branch(name, choices)
    return [branch] if branch is not None else []


def build_plan_schema(verbs: list[Verb], choices: SceneChoices, max_actions: int) -> JsonObject:
    """The schema of `{"actions": [...]}` with one branch per listed verb that has a choice to make."""
    branches = [branch for verb in verbs for branch in _verb_branches(verb.name, choices)]
    actions: JsonObject = {"type": "array", "minItems": 0, "maxItems": max_actions}
    if branches:
        actions["items"] = {"anyOf": branches}
    else:
        actions["maxItems"] = 0
    return {
        "type": "object",
        "properties": {"actions": actions},
        "required": ["actions"],
        "additionalProperties": False,
    }


class _PlanShapeError(ValueError):
    """Internal control flow only; callers see it folded into ParseFailure."""


def _text(fields: JsonObject, key: str) -> str:
    value = fields.get(key, "")
    if not isinstance(value, str):
        raise _PlanShapeError(f"'{key}' must be text.")
    return " ".join(value.split())


def _line(verb: str, *parts: str) -> str:
    return " ".join([verb, *(part for part in parts if part)])


def _talk_line(fields: JsonObject) -> str:
    speech = _text(fields, "speech").replace('"', "'")
    return _line(
        "TALK", _text(fields, "npc"), _text(fields, "approach"), f'"{speech}"' if speech else ""
    )


def _move_line(fields: JsonObject) -> str:
    run = fields.get("run", False)
    if not isinstance(run, bool):
        raise _PlanShapeError("'run' must be true or false.")
    return _line("MOVE_TO", _text(fields, "destination"), "run" if run else "")


def _first_aid_line(verb: str, fields: JsonObject) -> str:
    part, item = _text(fields, "body_part"), _text(fields, "item")
    return _line(verb, part, f"with {item}" if item else "")


def _exercise_line(fields: JsonObject) -> str:
    minutes = fields.get("minutes")
    if minutes is not None and (not isinstance(minutes, int) or isinstance(minutes, bool)):
        raise _PlanShapeError("'minutes' must be a whole number.")
    return _line("EXERCISE", _text(fields, "exercise"), "" if minutes is None else str(minutes))


def _request_line(fields: JsonObject) -> str:
    request = _text(fields, "request")
    argument = _text(fields, "topic" if request == "about" else "item")
    return _line("REQUEST", _text(fields, "npc"), request, argument)


def _take_line(fields: JsonObject) -> str:
    source = _text(fields, "from")
    return _line("TAKE", _text(fields, "item"), f"from {source}" if source else "")


def _item_line(verb: str) -> Callable[[JsonObject], str]:
    return lambda fields: _line(verb, _text(fields, "item"))


def _target_line(verb: str) -> Callable[[JsonObject], str]:
    return lambda fields: _line(verb, _text(fields, "target"))


def _attack_line(fields: JsonObject) -> str:
    swings = fields.get("swings")
    if swings is not None and (
        swings != UNTIL_IT_GIVES and (not isinstance(swings, int) or isinstance(swings, bool))
    ):
        raise _PlanShapeError(f"'swings' must be a whole number or '{UNTIL_IT_GIVES}'.")
    return _line("ATTACK", _text(fields, "target"), "" if swings is None else str(swings))


def _first_aid(verb: str) -> Callable[[JsonObject], str]:
    return lambda fields: _first_aid_line(verb, fields)


def _goal_line(verb: str) -> Callable[[JsonObject], str]:
    return lambda fields: _line(verb, _text(fields, "horizon"), _text(fields, "text"))


_LINE_BUILDERS: dict[str, Callable[[JsonObject], str]] = {
    "MOVE_TO": _move_line,
    "STANCE": lambda fields: _line("STANCE", _text(fields, "stance")),
    "WAIT": lambda fields: _line("WAIT", _text(fields, "duration")),
    "SLEEP": lambda fields: _line("SLEEP", _text(fields, "duration")),
    "TAKE": _take_line,
    "SEARCH": _target_line("SEARCH"),
    "CARRY": _target_line("CARRY"),
    "PUT": lambda fields: _line("PUT", _text(fields, "item"), "in", _text(fields, "bag")),
    "DROP": _item_line("DROP"),
    "USE_ITEM": _item_line("USE_ITEM"),
    "EQUIP": _item_line("EQUIP"),
    "UNEQUIP": _item_line("UNEQUIP"),
    "WEAR": _item_line("WEAR"),
    "TAKE_OFF": _item_line("TAKE_OFF"),
    "BANDAGE": _first_aid("BANDAGE"),
    "DISINFECT": _first_aid("DISINFECT"),
    "REMOVE_BANDAGE": lambda fields: _line("REMOVE_BANDAGE", _text(fields, "body_part")),
    "EXERCISE": _exercise_line,
    "ATTACK": _attack_line,
    "SHOVE": _target_line("SHOVE"),
    "OPEN": _target_line("OPEN"),
    "CLOSE": _target_line("CLOSE"),
    "LOCK": _target_line("LOCK"),
    "UNLOCK": _target_line("UNLOCK"),
    "BARRICADE": _target_line("BARRICADE"),
    "UNBARRICADE": _target_line("UNBARRICADE"),
    "SHOUT": lambda fields: "SHOUT",
    "TALK": _talk_line,
    "UNSUPPORTED": lambda fields: _line("UNSUPPORTED", _text(fields, "text")),
    "REQUEST": _request_line,
    "GIVE": lambda fields: _line(
        "GIVE", _text(fields, "item"), "to" if fields.get("npc") else "", _text(fields, "npc")
    ),
    "ADD_GOAL": _goal_line("ADD_GOAL"),
    "REMOVE_GOAL": _goal_line("REMOVE_GOAL"),
    "ADD_RELATIONSHIP_NOTE": lambda fields: _line(
        "ADD_RELATIONSHIP_NOTE", _text(fields, "npc"), _text(fields, "note")
    ),
}


def action_line(entry: object) -> str:
    """The grammar line for one JSON action; raises `_PlanShapeError` for a shape the schema forbids."""
    if not isinstance(entry, dict):
        raise _PlanShapeError("An action must be an object.")
    verb = entry.get("verb")
    builder = _LINE_BUILDERS.get(verb) if isinstance(verb, str) else None
    if builder is None:
        raise _PlanShapeError(f"Unknown action verb: '{verb}'.")
    return builder(entry)


def parse_plan(payload: object) -> tuple[list[AnyAction], list[ParseFailure]]:
    """Read a decoded `{"actions": [...]}` plan into actions and failures."""
    if not isinstance(payload, dict) or not isinstance(payload.get("actions"), list):
        return [], [ParseFailure(raw=str(payload), reason="The plan must be {'actions': [...]}.")]
    lines: list[str] = []
    failures: list[ParseFailure] = []
    for entry in payload["actions"]:
        try:
            lines.append(action_line(entry))
        except _PlanShapeError as exc:
            verb = entry.get("verb") if isinstance(entry, dict) else None
            known = verb if isinstance(verb, str) and verb in _LINE_BUILDERS else None
            failures.append(ParseFailure(raw=str(entry), reason=str(exc), verb=known))
    actions, line_failures = parse_action_plan(lines)
    return actions, [*failures, *line_failures]
