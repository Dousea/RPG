"""What the validator looked up for an accepted action.

The simulation applies these instead of resolving names again, so it acts on
exactly the entities the legality check saw.
"""

from dataclasses import dataclass

from .body import BodyPart
from .character.exercise import ExerciseDefinition
from .entity.barrier import BarrierEntity
from .entity.corpse import CorpseEntity
from .entity.item import ItemEntity
from .entity.npc import NpcEntity
from .location import Location
from .pace import Pace
from .room import ContainerEntity, RoomEntity


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
    barrier: BarrierEntity | None = None


@dataclass(frozen=True)
class MoveToRoom:
    """A room of the current zone (spec 25)."""

    location: Location
    room: RoomEntity


MoveOutcome = StayPut | ShuffleInZone | MoveToSpot | MoveToRoom | MoveToZone | MoveBlocked


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
class TargetCorpse:
    """A corpse to search, and the minutes the player needs to walk up to it (spec 14)."""

    corpse_id: str
    approach_minutes: int


@dataclass(frozen=True)
class TargetRoom:
    """A room to go through: the unopened containers in layout order; `walk` when the player is elsewhere (spec 25)."""

    room: RoomEntity
    containers: tuple[ContainerEntity, ...]
    walk: bool


@dataclass(frozen=True)
class TargetContainer:
    """A container to open, in its room; `walk` when the player is elsewhere (spec 25)."""

    room: RoomEntity
    container: ContainerEntity
    walk: bool


@dataclass(frozen=True)
class Transfer:
    """Items that move from one place to another, and the timed-action frames the move takes (spec 25).

    `source` is the bag, corpse or container they leave (None for the ground or the pack); `target` is
    the bag or container they go into (None for the pack or the floor).
    """

    entities: tuple[ItemEntity, ...]
    frames: float
    source: ItemEntity | CorpseEntity | ContainerEntity | None = None
    target: ItemEntity | ContainerEntity | None = None


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
class FirstAidTarget:
    """The body part a treatment is for and the item it uses, if any."""

    part: BodyPart
    entity: ItemEntity | None = None


@dataclass(frozen=True)
class TargetBarrier:
    """A door or window of the player's zone; `walk` when the player must first get to it (spec 13)."""

    barrier: BarrierEntity
    walk: bool


@dataclass(frozen=True)
class BarricadeKit:
    """The barrier and the hammer, plank and nails that board it up (spec 13)."""

    barrier: BarrierEntity
    hammer: ItemEntity
    plank: ItemEntity
    nails: ItemEntity
    walk: bool


@dataclass(frozen=True)
class PryTarget:
    """The barrier and the tool that pries a plank off it (spec 13)."""

    barrier: BarrierEntity
    tool: ItemEntity
    walk: bool


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
    | TargetCorpse
    | TargetRoom
    | TargetContainer
    | Transfer
    | TargetBarrier
    | BarricadeKit
    | PryTarget
    | TimeSpan
    | ExercisePlan
    | FirstAidTarget
    | None
)
