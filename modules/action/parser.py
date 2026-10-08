"""Parsing of the parser LLM's ACTIONS lines into typed actions.

`VERBS` is the one registry of what the parser may propose. Parsing recognizes
shape only (right verb, right number of arguments). It never touches game state
and never resolves an item, NPC or location name to a real entity; that is the
Action Validator's job (`managers/validator.py`).
"""

import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Literal

from modules.action.types import (
    AddGoalAction,
    AddRelationshipNoteAction,
    AnyAction,
    AttackAction,
    BandageAction,
    BarricadeAction,
    CarryAction,
    CloseAction,
    DisinfectAction,
    DropAction,
    Duration,
    EquipAction,
    ExerciseAction,
    GiveAction,
    MoveAction,
    OpenAction,
    PutAction,
    RemoveBandageAction,
    RemoveGoalAction,
    RequestAction,
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

# Goal horizons the model writes in place of the two real ones.
GOAL_HORIZON_SYNONYMS = {
    "short": "short_term",
    "shortterm": "short_term",
    "short_term": "short_term",
    "long": "long_term",
    "longterm": "long_term",
    "long_term": "long_term",
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
    verb: str | None = None


class _ActionParseError(ValueError):
    """Internal control flow only; callers see it folded into ParseFailure."""


_RUN_SUFFIX_PATTERN = re.compile(r"(.*\S)[\s,]+(?:run|running)\.?", re.IGNORECASE)


def _parse_move_to(args: str) -> MoveAction:
    if not args:
        raise _ActionParseError("MOVE_TO needs a destination.")
    running = _RUN_SUFFIX_PATTERN.fullmatch(args)
    if running:
        return MoveAction(destination=running.group(1).rstrip(" ,"), run=True)
    return MoveAction(destination=args)


_STANCES = {"sneak": True, "stand": False}


def _parse_stance(args: str) -> StanceAction:
    sneaking = _STANCES.get(normalize_key(args))
    if sneaking is None:
        raise _ActionParseError("STANCE needs 'sneak' or 'stand'.")
    return StanceAction(sneaking=sneaking)


_TAKE_FROM_PATTERN = re.compile(r"(.+?)\s+from\s+(\S.*)", re.IGNORECASE)


_ALL_WORDS = frozenset({"all", "everything"})
_PUT_PATTERN = re.compile(r"(.+?)\s+(?:in|into)\s+(\S.*)", re.IGNORECASE)
CORPSE_WORDS = frozenset({"corpse", "the corpse", "a corpse", "body", "the body", "a body"})


def _parse_take(args: str) -> TakeAction:
    if not args or args.casefold().startswith("from "):
        raise _ActionParseError("TAKE needs an item name.")
    source = _TAKE_FROM_PATTERN.fullmatch(args)
    item, from_name = (source.group(1).strip(), source.group(2).strip()) if source else (args, None)
    return TakeAction(item_name=item, from_name=from_name, all_items=item.casefold() in _ALL_WORDS)


def _parse_put(args: str) -> PutAction:
    parts = _PUT_PATTERN.fullmatch(args)
    if not parts:
        raise _ActionParseError("PUT needs an item and a bag: PUT <item> in <bag>.")
    return PutAction(item_name=parts.group(1).strip(), target_name=parts.group(2).strip())


def _parse_carry(args: str) -> CarryAction:
    if not args:
        raise _ActionParseError("CARRY needs a corpse.")
    return CarryAction(corpse_name=args)


def _parse_search(args: str) -> SearchAction:
    if not args:
        raise _ActionParseError("SEARCH needs a corpse, a room or a container.")
    return SearchAction(target_name=args)


def _parse_drop(args: str) -> DropAction:
    if not args:
        raise _ActionParseError("DROP needs an item name.")
    return DropAction(item_name=args, corpse=args.casefold() in CORPSE_WORDS)


def _parse_wear(args: str) -> WearAction:
    if not args:
        raise _ActionParseError("WEAR needs an item name.")
    return WearAction(item_name=args)


def _parse_take_off(args: str) -> TakeOffAction:
    if not args:
        raise _ActionParseError("TAKE_OFF needs an item name.")
    return TakeOffAction(item_name=args)


def _parse_attack(args: str) -> AttackAction:
    if not args:
        raise _ActionParseError("ATTACK needs a target.")
    return AttackAction(target_name=args)


def _parse_shove(args: str) -> ShoveAction:
    if not args:
        raise _ActionParseError("SHOVE needs a target.")
    return ShoveAction(target_name=args)


def _parse_open(args: str) -> OpenAction:
    if not args:
        raise _ActionParseError("OPEN needs a door or window.")
    return OpenAction(barrier_name=args)


def _parse_close(args: str) -> CloseAction:
    if not args:
        raise _ActionParseError("CLOSE needs a door or window.")
    return CloseAction(barrier_name=args)


def _parse_barricade(args: str) -> BarricadeAction:
    if not args:
        raise _ActionParseError("BARRICADE needs a door or window.")
    return BarricadeAction(barrier_name=args)


def _parse_unbarricade(args: str) -> UnbarricadeAction:
    if not args:
        raise _ActionParseError("UNBARRICADE needs a door or window.")
    return UnbarricadeAction(barrier_name=args)


def _parse_equip(args: str) -> EquipAction:
    if not args:
        raise _ActionParseError("EQUIP needs an item name.")
    return EquipAction(item_name=args)


def _parse_unequip(args: str) -> UnequipAction:
    if not args:
        raise _ActionParseError("UNEQUIP needs an item name.")
    return UnequipAction(item_name=args)


def _parse_use_item(args: str) -> UseItemAction:
    if not args:
        raise _ActionParseError("USE_ITEM needs an item name.")
    return UseItemAction(item_name=args)


_WITH_PATTERN = re.compile(r"\s+with\s+", re.IGNORECASE)


def _split_with(args: str) -> tuple[str, str]:
    """Split 'left forearm with Bandage' into the part and the item; either may be empty."""
    text = args.strip()
    if text.casefold().startswith("with "):
        return "", text[len("with ") :].strip()
    match = _WITH_PATTERN.search(text)
    if match is None:
        return text, ""
    return text[: match.start()].strip(), text[match.end() :].strip()


def _parse_bandage(args: str) -> BandageAction:
    part, item = _split_with(args)
    return BandageAction(part_name=part, item_name=item)


def _parse_remove_bandage(args: str) -> RemoveBandageAction:
    if not args:
        raise _ActionParseError("REMOVE_BANDAGE needs a body part.")
    return RemoveBandageAction(part_name=args)


def _parse_disinfect(args: str) -> DisinfectAction:
    part, item = _split_with(args)
    if not part:
        raise _ActionParseError("DISINFECT needs a body part.")
    return DisinfectAction(part_name=part, item_name=item)


_SPAN_PATTERN = re.compile(r"(?:(\d+)\s*(?:h|hrs?|hours?))?\s*(?:(\d+)\s*(?:m|mins?|minutes?))?")
_CLOCK_TIME_PATTERN = re.compile(r"(\d{1,2}):(\d{2})")
_TIME_OF_DAY_PATTERN = re.compile(r"[a-z]+")


def _parse_duration(verb: str, args: str) -> Duration:
    """Parse '10m', '2h', '1h30m' (units may be spelled out), 'until <time of day>' or 'until HH:MM'."""
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


_EXERCISE_MINUTES_PATTERN = re.compile(r"(.*?)\s+(\d+)\s*(?:m|min|mins|minutes)?\.?")


def _parse_exercise(args: str) -> ExerciseAction:
    if not args:
        raise _ActionParseError("EXERCISE needs an exercise.")
    match = _EXERCISE_MINUTES_PATTERN.fullmatch(args.strip())
    if match is None:
        return ExerciseAction(exercise_name=args.strip().strip(".,;"))
    return ExerciseAction(exercise_name=match.group(1).strip(), minutes=int(match.group(2)))


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


def _parse_add_relationship_note(args: str) -> AddRelationshipNoteAction:
    name, _, note = args.partition(" ")
    name, note = name.strip(), note.strip()
    if not name or not note:
        raise _ActionParseError("ADD_RELATIONSHIP_NOTE needs a name and note text.")
    return AddRelationshipNoteAction(npc_name=name, note=note)


def _parse_shout(args: str) -> ShoutAction:
    return ShoutAction()


# The closed label sets live here because `modules/` cannot import `data/`;
# `data/social.py` keys its table on them.
TALK_APPROACH_LABELS = (
    "chat",
    "compliment",
    "flirt",
    "confide",
    "comfort",
    "argue",
    "insult",
    "threaten",
)
REQUEST_LABELS = ("follow", "stay", "give", "about")
GOAL_HORIZON_LABELS = ("short_term", "long_term")
TALK_SPEECH_MAX_CHARS = 300  # llm-contract: the words of a TALK that reach the narrator
TALK_TURN_MINUTES = 5  # llm-contract: one cost per turn, shared by TALK, REQUEST and GIVE


def _parse_talk(args: str) -> TalkAction:
    """The approach is the first label after the name; a quoted string after it is the speech."""
    words = args.split()
    index = next(
        (
            i
            for i, word in enumerate(words)
            if i > 0 and normalize_key(word) in TALK_APPROACH_LABELS
        ),
        None,
    )
    if index is None:
        raise _ActionParseError(
            f"TALK needs an NPC name and one of: {', '.join(TALK_APPROACH_LABELS)}."
        )
    spoken = " ".join(words[index + 1 :])
    quoted = re.fullmatch(r'"(.*)"', spoken.strip(), re.DOTALL)
    speech = quoted.group(1).strip()[:TALK_SPEECH_MAX_CHARS].strip() if quoted else ""
    return TalkAction(
        npc_name=" ".join(words[:index]), approach=normalize_key(words[index]), speech=speech
    )


def _parse_request(args: str) -> RequestAction:
    words = args.split()
    index = next(
        (i for i, word in enumerate(words) if i > 0 and normalize_key(word) in REQUEST_LABELS),
        None,
    )
    if index is None:
        raise _ActionParseError(
            f"REQUEST needs an NPC name and one of: {', '.join(REQUEST_LABELS)}."
        )
    request = normalize_key(words[index])
    argument = " ".join(words[index + 1 :]).strip(" .,;")
    if request == "about":
        argument = normalize_key(argument)
    if request in ("give", "about") and not argument:
        raise _ActionParseError(
            f"REQUEST ... {request} needs an {'item' if request == 'give' else 'topic'}."
        )
    if request in ("follow", "stay"):
        argument = ""
    return RequestAction(npc_name=" ".join(words[:index]), request=request, argument=argument)


_GIVE_SEPARATOR = re.compile(r"(.*\S)\s+to\s+(\S.*)", re.IGNORECASE)


def _parse_give(args: str) -> GiveAction:
    text = args.strip().rstrip(".,;")
    separated = _GIVE_SEPARATOR.fullmatch(text)
    if separated:
        return GiveAction(item_name=separated.group(1), npc_name=separated.group(2))
    *item_words, npc = text.split() or [""]
    if not item_words:
        raise _ActionParseError("GIVE needs an item and an NPC name.")
    return GiveAction(item_name=" ".join(item_words), npc_name=npc)


TargetKind = Literal[
    "npc",
    "zombie",
    "corpse",
    "room",
    "container",
    "item",
    "zone",
    "barrier",
    "body_part",
    "approach",
    "request",
    "duration",
    "text",
]


SceneKey = Literal[
    "goals",
    "items_here",
    "carried",
    "held",
    "wearable",
    "worn",
    "npcs_here",
    "threats",
    "corpses",
    "loot",
    "hurt",
    "barriers",
    "bags",
    "rooms",
    "opened",
    "stocked",
]


@dataclass(frozen=True)
class Verb:
    """One verb the parser may propose.

    `minutes` is the fixed cost, or None when the time is spent as the action runs.
    `listed_when` is the scene keys that put the verb in front of the model: it is
    listed when any is present, and always when empty. Unlisted verbs still parse.
    The validator and resolver for a verb are looked up by `name` in
    `managers/validator.py` and `managers/simulation.py`, which `modules/` cannot import.
    """

    name: str
    target_kinds: tuple[TargetKind, ...]
    parse: Callable[[str], AnyAction]
    gloss: str
    minutes: int | None
    listed_when: tuple[SceneKey, ...] = ()


def _verb(
    name: str,
    kinds: tuple[TargetKind, ...],
    parse: Callable[[str], AnyAction],
    gloss: str,
    minutes: int | None,
    listed_when: tuple[SceneKey, ...] = (),
) -> tuple[str, Verb]:
    return name, Verb(name, kinds, parse, gloss, minutes, listed_when)


VERBS: dict[str, Verb] = dict(
    [
        _verb(
            "MOVE_TO",
            ("zone", "room"),
            _parse_move_to,
            "a zone, a room of this building (e.g. 'the kitchen'), in/out, or a specific spot; add 'run' at the end to run",
            None,
        ),
        _verb(
            "STANCE", ("text",), _parse_stance, "sneak or stand: start or stop moving quietly", 0
        ),
        _verb("WAIT", ("duration",), _parse_wait, "10m, 2h, 1h30m, until night, until 14:30", None),
        _verb("SLEEP", ("duration",), _parse_sleep, "optional duration; same forms as WAIT", None),
        _verb(
            "TAKE",
            ("item",),
            _parse_take,
            "an item listed in [ITEMS HERE], '<item> from <corpse>' for a searched corpse in [CORPSES], "
            "'<item> from <bag>' for a carried bag, '<item> from <container>' for an opened one in [ROOMS], "
            "or 'all from <source>'",
            1,
            ("items_here", "loot", "bags", "stocked"),
        ),
        _verb(
            "PUT",
            ("item", "item"),
            _parse_put,
            "'<item> in <bag>': a carried item into a bag in [INVENTORY] or an opened container in [ROOMS]",
            1,
            ("bags", "opened"),
        ),
        _verb(
            "CARRY",
            ("corpse",),
            _parse_carry,
            "a corpse id from [CORPSES], or 'corpse' for the nearest; picks the body up in both arms",
            1,
            ("corpses",),
        ),
        _verb(
            "SEARCH",
            ("corpse", "room", "container"),
            _parse_search,
            "a corpse id from [CORPSES], or 'corpse' for the nearest; goes through its pockets and clothes once. "
            "Or a room or container from [ROOMS]: opens it, a minute for each container",
            None,
            ("corpses", "rooms"),
        ),
        _verb(
            "DROP",
            ("item",),
            _parse_drop,
            "a carried item, or 'corpse' for the body in your arms",
            1,
            ("carried",),
        ),
        _verb(
            "USE_ITEM",
            ("item",),
            _parse_use_item,
            "a carried item; eating and drinking too",
            None,
            ("carried",),
        ),
        _verb(
            "BANDAGE",
            ("body_part",),
            _parse_bandage,
            "a body part from [CONDITION], then optionally 'with <bandage>'",
            1,
            ("hurt",),
        ),
        _verb(
            "REMOVE_BANDAGE",
            ("body_part",),
            _parse_remove_bandage,
            "a bandaged body part from [CONDITION]; the bandage comes back to the inventory",
            1,
            ("hurt",),
        ),
        _verb(
            "DISINFECT",
            ("body_part",),
            _parse_disinfect,
            "a hurt, unbandaged body part, then optionally 'with <alcohol item>'",
            1,
            ("hurt",),
        ),
        _verb(
            "WEAR",
            ("item",),
            _parse_wear,
            "a carried garment; refused if something is already there",
            1,
            ("wearable",),
        ),
        _verb("TAKE_OFF", ("item",), _parse_take_off, "a worn garment", 1, ("worn",)),
        _verb(
            "EXERCISE",
            ("text",),
            _parse_exercise,
            "an exercise from [EXERCISES], then optional minutes (10-60, in steps of 10)",
            None,
        ),
        _verb(
            "ATTACK",
            ("npc", "zombie", "barrier"),
            _parse_attack,
            "an NPC name, a zombie id from [THREATS], 'zombie' for the nearest, or a door or window from [DOORS AND WINDOWS]",
            1,
            ("npcs_here", "threats", "barriers"),
        ),
        _verb(
            "OPEN",
            ("barrier",),
            _parse_open,
            "a door or window from [DOORS AND WINDOWS]; takes no time",
            0,
            ("barriers",),
        ),
        _verb(
            "CLOSE",
            ("barrier",),
            _parse_close,
            "a door or window from [DOORS AND WINDOWS]; takes no time",
            0,
            ("barriers",),
        ),
        _verb(
            "BARRICADE",
            ("barrier",),
            _parse_barricade,
            "a closed door or window from [DOORS AND WINDOWS]; nails one plank on this side, needs a hammer, a plank and a nail",
            1,
            ("barriers",),
        ),
        _verb(
            "UNBARRICADE",
            ("barrier",),
            _parse_unbarricade,
            "a door or window from [DOORS AND WINDOWS]; pries one plank off this side, needs a hammer, crowbar or similar",
            1,
            ("barriers",),
        ),
        _verb(
            "SHOVE",
            ("zombie",),
            _parse_shove,
            "a zombie id from [THREATS]; knocks it back with bare hands, whatever is held",
            1,
            ("threats",),
        ),
        _verb(
            "EQUIP",
            ("item",),
            _parse_equip,
            "a carried item into the hands; refused if the hands are full",
            1,
            ("carried",),
        ),
        _verb("UNEQUIP", ("item",), _parse_unequip, "the item in the hands", 1, ("held",)),
        _verb("SHOUT", (), _parse_shout, "call out loudly; zombies may hear it", 0),
        _verb(
            "TALK",
            ("npc", "approach"),
            _parse_talk,
            "say something to an NPC; the approach is how it is said",
            TALK_TURN_MINUTES,
            ("npcs_here",),
        ),
        _verb(
            "REQUEST",
            ("npc", "request"),
            _parse_request,
            "ask an NPC for something: follow, stay, give <item>, about <topic>",
            TALK_TURN_MINUTES,
            ("npcs_here",),
        ),
        _verb(
            "GIVE",
            ("item", "npc"),
            _parse_give,
            "hand a carried item to an NPC",
            TALK_TURN_MINUTES,
            ("npcs_here",),
        ),
        _verb(
            "ADD_GOAL",
            ("text",),
            _parse_add_goal,
            "short_term or long_term, then the goal text",
            0,
        ),
        _verb(
            "REMOVE_GOAL",
            ("text",),
            _parse_remove_goal,
            "short_term or long_term, then the goal text",
            0,
            ("goals",),
        ),
        _verb(
            "ADD_RELATIONSHIP_NOTE",
            ("npc", "text"),
            _parse_add_relationship_note,
            "an NPC name, then the character's own impression of them",
            0,
        ),
    ]
)

# Verbs the model once proposed outcomes through. The engine owns what they set,
# so a line using one is refused as not available.
# Verbs small models write for USE_ITEM although the prompt never lists them.
VERB_ALIASES = {"EAT": "USE_ITEM", "DRINK": "USE_ITEM"}

REMOVED_VERBS = frozenset(
    {
        "TIME_ADVANCE",
        "UPDATE_CONDITION",
        "UPDATE_RELATIONSHIP",
        "SET_FLAG",
        "DISCOVER_FLAG",
        "NPC_MOVE",
        "NPC_STATUS",
        "STATUS_ADD",
        "STATUS_REMOVE",
        "UPDATE_INVENTORY",
    }
)


def available_verbs(present: frozenset[SceneKey]) -> list[Verb]:
    """The verbs to show the model for a scene, in registry order."""
    return [
        verb
        for verb in VERBS.values()
        if not verb.listed_when or any(key in present for key in verb.listed_when)
    ]


def parse_action_line(line: str) -> AnyAction | ParseFailure:
    """Parse one already-stripped, non-empty, non-'NONE' action line."""
    name, _, remainder = line.partition(" ")
    name = name.upper()
    verb = VERBS.get(VERB_ALIASES.get(name, name))
    if verb is None:
        if name in REMOVED_VERBS:
            return ParseFailure(raw=line, reason=f"'{name}' is not an available action.")
        return ParseFailure(raw=line, reason=f"Unknown action verb: '{name}'.")
    try:
        return verb.parse(remainder.strip())
    except _ActionParseError as exc:
        return ParseFailure(raw=line, reason=str(exc), verb=verb.name)


def parse_action_plan(lines: list[str]) -> tuple[list[AnyAction], list[ParseFailure]]:
    """Parse a full ACTIONS: block into well-formed proposals and failures.

    Failures are shape/vocabulary problems only (unknown verb, missing args,
    a removed verb) -- they are rejected before the Action Validator
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
