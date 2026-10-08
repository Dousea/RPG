"""Lorebook entries and the JSON that describes them (world-lore: The lorebook).

Pure: nothing here opens a file. `managers/story/lorebook.py` loads and validates.
"""

from dataclasses import dataclass
from enum import StrEnum
from typing import Any

from modules.story.beats import (
    AllOf,
    BeatFiredAgo,
    ClockAtOrPast,
    Condition,
    FlagDiscovered,
    ItemHeld,
    OutbreakStarted,
    PlayerInZone,
)


class LoreFormatError(ValueError):
    """The JSON for a condition or an entry has the wrong shape."""


class Position(StrEnum):
    SYSTEM = "system"
    WORLD = "world"


@dataclass(frozen=True)
class LoreEntry:
    """`when` is when the player could know the entry, not when it became true."""

    entry_id: str
    content: str
    position: Position
    constant: bool = False
    keys: tuple[str, ...] = ()
    order: int = 0
    when: Condition | None = None
    replaced_by: str | None = None
    stage: bool = False
    sticky: int | None = None
    semantic: bool = True
    comment: str = ""


def _is_count(value: object) -> bool:
    return isinstance(value, int) and not isinstance(value, bool) and value >= 0


def _text(value: object, what: str) -> str:
    if not isinstance(value, str):
        raise LoreFormatError(f"{what} must be a string")
    return value


def parse_condition(raw: object) -> Condition:
    """One condition object: exactly one of the keys in the conditions table."""
    if not isinstance(raw, dict):
        raise LoreFormatError("a condition must be an object")
    fields = {str(key): value for key, value in raw.items()}  # pyright: ignore[reportUnknownVariableType, reportUnknownArgumentType]
    if set(fields) == {"beat", "minutes"}:
        beat, minutes = fields["beat"], fields["minutes"]
        if not _is_count(minutes):
            raise LoreFormatError("minutes must be an int, 0 or more")
        return BeatFiredAgo(_text(beat, "beat"), int(minutes))
    if len(fields) != 1:
        raise LoreFormatError(f"a condition holds exactly one condition, got {sorted(fields)}")

    (kind, value), *_ = fields.items()
    match kind:
        case "clock":
            if not _is_count(value):
                raise LoreFormatError("clock must be an int, 0 or more")
            return ClockAtOrPast(int(value))
        case "zone":
            return PlayerInZone(_text(value, "zone"))
        case "flag":
            return FlagDiscovered(_text(value, "flag"))
        case "outbreak":
            if value is not True:
                raise LoreFormatError("outbreak must be true")
            return OutbreakStarted()
        case "beat":
            return BeatFiredAgo(_text(value, "beat"), 0)
        case "item":
            return ItemHeld(_text(value, "item"))
        case "all":
            if not isinstance(value, list) or not value:
                raise LoreFormatError("all must be a non-empty list")
            return AllOf(tuple(parse_condition(part) for part in value))  # pyright: ignore[reportUnknownVariableType]
    raise LoreFormatError(f"unknown condition {kind!r}")


_FIELDS = frozenset(
    {
        "id",
        "content",
        "position",
        "comment",
        "keys",
        "constant",
        "order",
        "when",
        "replaced_by",
        "stage",
        "sticky",
        "semantic",
    }
)


def parse_entry(raw: dict[str, Any]) -> LoreEntry:
    """One entry object. Raises `LoreFormatError` for an unknown field, a missing or mistyped one."""
    unknown = sorted(set(raw) - _FIELDS)
    if unknown:
        raise LoreFormatError(f"unknown field {unknown[0]!r}")
    for required in ("id", "content", "position"):
        if required not in raw:
            raise LoreFormatError(f"missing field {required!r}")

    try:
        position = Position(_text(raw["position"], "position"))
    except ValueError as error:
        raise LoreFormatError("position must be 'system' or 'world'") from error

    keys = raw.get("keys", [])
    if not isinstance(keys, list) or not all(isinstance(key, str) for key in keys):  # pyright: ignore[reportUnknownVariableType]
        raise LoreFormatError("keys must be a list of strings")

    flags = {name: raw.get(name, False) for name in ("constant", "stage", "semantic")}
    for name, flag in flags.items():
        if not isinstance(flag, bool):
            raise LoreFormatError(f"{name} must be true or false")
    if "semantic" in raw and (position is Position.SYSTEM or raw.get("constant") or not keys):
        raise LoreFormatError("semantic belongs on keyed entries only")

    order = raw.get("order", 0)
    if isinstance(order, bool) or not isinstance(order, int):
        raise LoreFormatError("order must be an int")
    sticky = raw.get("sticky")
    if sticky is not None and (isinstance(sticky, bool) or not isinstance(sticky, int)):
        raise LoreFormatError("sticky must be an int")
    replaced_by = raw.get("replaced_by")
    if replaced_by is not None:
        replaced_by = _text(replaced_by, "replaced_by")

    return LoreEntry(
        entry_id=_text(raw["id"], "id"),
        content=_text(raw["content"], "content"),
        position=position,
        constant=flags["constant"],
        keys=tuple(keys),  # pyright: ignore[reportUnknownArgumentType]
        order=order,
        when=parse_condition(raw["when"]) if "when" in raw else None,
        replaced_by=replaced_by,
        stage=flags["stage"],
        sticky=sticky,
        semantic=raw.get("semantic", True),
        comment=_text(raw.get("comment", ""), "comment"),
    )
