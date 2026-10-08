"""Loading and validating the lorebook (world-lore: Loading and validation)."""

import json
import logging
import re
from dataclasses import dataclass
from functools import cache
from pathlib import Path
from typing import Any

from data.items import ITEMS
from data.story import lore as lore_k
from data.story.beats import STORY_BEATS
from data.story.npcs import build_starting_npcs
from data.story.topics import TOPICS
from data.world.locations import build_starting_locations
from modules.story.beats import (
    AllOf,
    BeatFiredAgo,
    Condition,
    DiscoverFlag,
    FlagDiscovered,
    ItemHeld,
    PlayerInZone,
)
from modules.story.lore import LoreEntry, LoreFormatError, Position, parse_entry

logger = logging.getLogger(__name__)

ZONE_KEY_PREFIX = "zone_"
NPC_KEY_PREFIX = "npc_"
_NUMBER = re.compile(r"(?<![A-Za-z0-9-])\d+(?![A-Za-z0-9-])")


class LorebookError(ValueError):
    """The lorebook breaks a rule; the message names the entry and the field."""


@dataclass(frozen=True)
class KnownIds:
    """The ids an entry may name, from the data modules that define them."""

    flags: frozenset[str]
    beats: frozenset[str]
    items: frozenset[str]
    zones: frozenset[str]
    npcs: frozenset[str]


@dataclass(frozen=True)
class Lorebook:
    entries: dict[str, LoreEntry]

    def system_entries(self) -> list[LoreEntry]:
        return [e for e in self.entries.values() if e.position is Position.SYSTEM]

    def world_entries(self) -> list[LoreEntry]:
        return [e for e in self.entries.values() if e.position is Position.WORLD]


def known_ids() -> KnownIds:
    """Every flag a beat or topic discovers, and the beat, item, zone and NPC ids."""
    flags = {topic.discovers for topic in TOPICS.values() if topic.discovers}
    flags.update(
        effect.flag
        for beat in STORY_BEATS.values()
        for effect in beat.effects
        if isinstance(effect, DiscoverFlag)
    )
    return KnownIds(
        flags=frozenset(flags),
        beats=frozenset(STORY_BEATS),
        items=frozenset(ITEMS),
        zones=frozenset(build_starting_locations()),
        npcs=frozenset(build_starting_npcs()),
    )


def holds_number(text: str) -> bool:
    """A digit that touches no letter or hyphen: "day 3" is a number, "VX-7" is a name."""
    return _NUMBER.search(text) is not None


def _condition_problem(condition: Condition, known: KnownIds) -> str | None:
    match condition:
        case FlagDiscovered(flag=flag) if flag not in known.flags:
            return f"unknown flag {flag!r}"
        case BeatFiredAgo(beat_id=beat_id) if beat_id not in known.beats:
            return f"unknown beat {beat_id!r}"
        case ItemHeld(item_id=item_id) if item_id not in known.items:
            return f"unknown item {item_id!r}"
        case PlayerInZone(zone_id=zone_id) if zone_id not in known.zones:
            return f"unknown zone {zone_id!r}"
        case AllOf(conditions=parts):
            return next(
                (problem for part in parts if (problem := _condition_problem(part, known))), None
            )
    return None


def _key_problem(key: str, known: KnownIds) -> str | None:
    if not key.strip():
        return "blank key"
    if key.startswith(ZONE_KEY_PREFIX) and key not in known.zones:
        return f"unknown zone {key!r}"
    if key.startswith(NPC_KEY_PREFIX) and key not in known.npcs:
        return f"unknown NPC {key!r}"
    return None


def _entry_problem(entry: LoreEntry, known: KnownIds) -> str | None:
    """The first rule this entry breaks on its own, or None."""
    keyed = not entry.constant
    if entry.position is Position.SYSTEM:
        extras = [
            name
            for name, present in (
                ("when", entry.when is not None),
                ("keys", bool(entry.keys)),
                ("sticky", entry.sticky is not None),
                ("replaced_by", entry.replaced_by is not None),
                ("stage", entry.stage),
            )
            if present
        ]

        if keyed:
            return "a system entry must be constant"
        if extras:
            return f"a system entry cannot have {extras[0]}"
    elif entry.constant and entry.keys:
        return "a constant entry cannot have keys"
    elif keyed and not entry.keys:
        return "a keyed entry needs keys"

    if entry.stage and not entry.constant:
        return "a stage entry must be constant"
    if entry.sticky is not None and (not keyed or not 1 <= entry.sticky <= lore_k.STICKY_MAX_TURNS):
        return f"sticky must be 1 to {lore_k.STICKY_MAX_TURNS} on a keyed entry"

    if len(entry.content) > lore_k.ENTRY_MAX_CHARS:
        return f"content is over {lore_k.ENTRY_MAX_CHARS} characters"
    if holds_number(entry.content):
        return "content holds a number"

    if entry.when is not None and (problem := _condition_problem(entry.when, known)):
        return f"when: {problem}"
    for key in entry.keys:
        if problem := _key_problem(key, known):
            return f"keys: {problem}"
    return None


def _replacement_problem(entries: dict[str, LoreEntry]) -> str | None:
    for entry in entries.values():
        seen = {entry.entry_id}
        target = entry.replaced_by
        while target is not None:
            if target not in entries:
                return f"{entry.entry_id}: replaced_by names no entry ({target!r})"
            if target in seen:
                return f"{entry.entry_id}: replaced_by makes a cycle through {target!r}"
            seen.add(target)
            target = entries[target].replaced_by
    return None


def validate_entries(entries: list[LoreEntry], known: KnownIds) -> Lorebook:
    """Check every rule over a list of entries; raises `LorebookError`, never skips one."""
    by_id: dict[str, LoreEntry] = {}
    for entry in entries:
        if entry.entry_id in by_id:
            raise LorebookError(f"{entry.entry_id}: duplicate id")
        by_id[entry.entry_id] = entry

    for entry in entries:
        problem = _entry_problem(entry, known)
        if problem:
            raise LorebookError(f"{entry.entry_id}: {problem}")

    problem = _replacement_problem(by_id)
    if problem:
        raise LorebookError(problem)

    system_chars = sum(len(e.content) for e in entries if e.position is Position.SYSTEM)
    if system_chars > lore_k.SYSTEM_MAX_CHARS:
        raise LorebookError(
            f"system entries total {system_chars} characters, over {lore_k.SYSTEM_MAX_CHARS}"
        )

    return Lorebook(by_id)


def load_lorebook(path: Path, known: KnownIds) -> Lorebook:
    """Read and validate a lorebook file."""
    try:
        data: Any = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, ValueError) as error:
        raise LorebookError(f"{path}: not readable JSON ({error})") from error
    if (
        not isinstance(data, dict)
        or set(data) != {"entries"}
        or not isinstance(data["entries"], list)
    ):  # pyright: ignore[reportUnknownArgumentType]
        raise LorebookError(f"{path}: expected an object with one key, 'entries', holding a list")

    entries: list[LoreEntry] = []
    for index, raw in enumerate(data["entries"]):  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
        label = raw.get("id", f"entry {index}") if isinstance(raw, dict) else f"entry {index}"  # pyright: ignore[reportUnknownVariableType, reportUnknownMemberType]
        if not isinstance(raw, dict):
            raise LorebookError(f"{label}: an entry must be an object")
        try:
            entries.append(parse_entry(raw))  # pyright: ignore[reportUnknownArgumentType]
        except LoreFormatError as error:
            raise LorebookError(f"{label}: {error}") from error

    return validate_entries(entries, known)


@cache
def get_lorebook() -> Lorebook:
    """The shipped lorebook, loaded once."""
    return load_lorebook(lore_k.LOREBOOK_PATH, known_ids())
