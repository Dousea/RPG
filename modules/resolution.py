"""What the validator looked up for an accepted action.

The simulation applies these instead of resolving names again, so it acts on
exactly the entities the legality check saw.
"""

from dataclasses import dataclass

from .entity.item import ItemEntity
from .entity.npc import NpcEntity
from .item import BaseItem
from .location import Location


@dataclass(frozen=True)
class StayPut:
    """A move with no destination."""

    location: Location


@dataclass(frozen=True)
class ShuffleInZone:
    """A bare direction that leads nowhere: a few steps within the zone."""

    location: Location
    direction: str


@dataclass(frozen=True)
class MoveToSpot:
    """A spot inside the current zone; an empty `place` means the zone itself."""

    location: Location
    place: str


@dataclass(frozen=True)
class MoveToZone:
    location: Location
    place: str
    hops: int


@dataclass(frozen=True)
class MoveBlocked:
    """A walk toward `target` stopped by a locked door after `hops` hops."""

    location: Location
    place: str
    hops: int
    target: Location


MoveOutcome = StayPut | ShuffleInZone | MoveToSpot | MoveToZone | MoveBlocked


@dataclass(frozen=True)
class HeldItem:
    """An item entity on the ground or in the inventory."""

    entity: ItemEntity


@dataclass(frozen=True)
class NewItem:
    """An item to create, not yet anywhere in the world."""

    item: BaseItem


@dataclass(frozen=True)
class TargetNpc:
    npc: NpcEntity


@dataclass(frozen=True)
class NpcDestination:
    npc: NpcEntity
    location: Location


@dataclass(frozen=True)
class TimeSpan:
    """In-game minutes to pass; `clamped` when the request exceeded the cap."""

    minutes: int
    clamped: bool


Resolution = MoveOutcome | HeldItem | NewItem | TargetNpc | NpcDestination | TimeSpan | None
