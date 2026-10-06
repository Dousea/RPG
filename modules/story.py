"""Conditions and effects of story beats (spec 10, Story beats).

Plain data: `managers/story.py` evaluates conditions and `managers/simulation.py`
applies effects, each with one `match`.
"""

from dataclasses import dataclass


@dataclass(frozen=True)
class ClockAtOrPast:
    minute: int


@dataclass(frozen=True)
class PlayerInZone:
    zone_id: str


@dataclass(frozen=True)
class FlagDiscovered:
    flag: str


@dataclass(frozen=True)
class OutbreakStarted:
    pass


@dataclass(frozen=True)
class BeatFiredAgo:
    beat_id: str
    minutes: int


@dataclass(frozen=True)
class AllOf:
    conditions: tuple["Condition", ...]


Condition = ClockAtOrPast | PlayerInZone | FlagDiscovered | OutbreakStarted | BeatFiredAgo | AllOf


@dataclass(frozen=True)
class StartOutbreak:
    """The dead start walking at the current minute (spec 09)."""


@dataclass(frozen=True)
class SetFlag:
    flag: str


@dataclass(frozen=True)
class DiscoverFlag:
    flag: str


@dataclass(frozen=True)
class MoveNpc:
    npc_id: str
    zone_id: str


@dataclass(frozen=True)
class AddNpcStatus:
    npc_id: str
    status: str


@dataclass(frozen=True)
class RemoveNpcStatus:
    npc_id: str
    status: str


Effect = StartOutbreak | SetFlag | DiscoverFlag | MoveNpc | AddNpcStatus | RemoveNpcStatus
