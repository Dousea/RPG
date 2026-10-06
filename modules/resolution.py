"""What the validator looked up for an accepted action.

The simulation applies these instead of resolving names again, so it acts on
exactly the entities the legality check saw.
"""

from dataclasses import dataclass

from .character.exercise import ExerciseDefinition
from .entity.item import ItemEntity
from .entity.npc import NpcEntity
from .location import Location
from .pace import Pace


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
    pace: Pace = Pace.WALK


@dataclass(frozen=True)
class MoveBlocked:
    """A walk toward `target` stopped by a locked door after `hops` hops."""

    location: Location
    place: str
    hops: int
    target: Location
    pace: Pace = Pace.WALK


MoveOutcome = StayPut | ShuffleInZone | MoveToSpot | MoveToZone | MoveBlocked


@dataclass(frozen=True)
class HeldItem:
    """An item entity on the ground or in the inventory."""

    entity: ItemEntity


@dataclass(frozen=True)
class TargetZombie:
    """A zombie to attack, and the minutes the player needs to walk up to it."""

    zombie_id: str
    approach_minutes: int


@dataclass(frozen=True)
class TargetNpc:
    npc: NpcEntity


@dataclass(frozen=True)
class NpcItem:
    """An NPC and an item that moves between them and the player."""

    npc: NpcEntity
    entity: ItemEntity


@dataclass(frozen=True)
class NpcTopic:
    """An NPC and the id of a topic the player asked about."""

    npc: NpcEntity
    topic_id: str


@dataclass(frozen=True)
class TimeSpan:
    """In-game minutes to pass; `clamped` when the request exceeded the cap."""

    minutes: int
    clamped: bool


@dataclass(frozen=True)
class ExercisePlan:
    """The exercise to do and the minutes asked for."""

    exercise: ExerciseDefinition
    minutes: int


Resolution = (
    MoveOutcome
    | HeldItem
    | TargetNpc
    | NpcItem
    | NpcTopic
    | TargetZombie
    | TimeSpan
    | ExercisePlan
    | None
)
