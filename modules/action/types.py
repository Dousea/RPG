"""The typed actions the parser LLM may propose, as the validator and simulation see them.

Each action names its verb (`verb`), the key into `modules.action.parser.VERBS` and the
validator and resolver tables.
"""

from dataclasses import dataclass
from typing import ClassVar


@dataclass
class MoveAction:
    verb: ClassVar[str] = "MOVE_TO"
    destination: str
    run: bool = False


@dataclass
class StanceAction:
    """Start or stop sneaking; takes no time."""

    verb: ClassVar[str] = "STANCE"
    sneaking: bool


@dataclass
class TakeAction:
    verb: ClassVar[str] = "TAKE"
    item_name: str


@dataclass
class DropAction:
    verb: ClassVar[str] = "DROP"
    item_name: str


@dataclass
class WearAction:
    verb: ClassVar[str] = "WEAR"
    item_name: str


@dataclass
class TakeOffAction:
    verb: ClassVar[str] = "TAKE_OFF"
    item_name: str


@dataclass
class AttackAction:
    verb: ClassVar[str] = "ATTACK"
    target_name: str


@dataclass
class ShoveAction:
    """One shove at a zombie, bare-handed whatever is held (spec 11)."""

    verb: ClassVar[str] = "SHOVE"
    target_name: str


@dataclass
class OpenAction:
    """Open a door or window of the player's zone (spec 13)."""

    verb: ClassVar[str] = "OPEN"
    barrier_name: str


@dataclass
class CloseAction:
    verb: ClassVar[str] = "CLOSE"
    barrier_name: str


@dataclass
class BarricadeAction:
    """Nail one plank across a door or window on the player's side (spec 13)."""

    verb: ClassVar[str] = "BARRICADE"
    barrier_name: str


@dataclass
class UnbarricadeAction:
    """Pry the outermost plank off the player's side (spec 13)."""

    verb: ClassVar[str] = "UNBARRICADE"
    barrier_name: str


@dataclass
class EquipAction:
    """Take a carried item in hand."""

    verb: ClassVar[str] = "EQUIP"
    item_name: str


@dataclass
class UnequipAction:
    """Put a held item back in the inventory."""

    verb: ClassVar[str] = "UNEQUIP"
    item_name: str


@dataclass
class UseItemAction:
    verb: ClassVar[str] = "USE_ITEM"
    item_name: str


@dataclass
class BandageAction:
    """Bandage a part; an empty `part_name` picks the part most in need, an empty `item_name` the best bandage."""

    verb: ClassVar[str] = "BANDAGE"
    part_name: str = ""
    item_name: str = ""


@dataclass
class RemoveBandageAction:
    verb: ClassVar[str] = "REMOVE_BANDAGE"
    part_name: str


@dataclass
class DisinfectAction:
    verb: ClassVar[str] = "DISINFECT"
    part_name: str
    item_name: str = ""


@dataclass
class Duration:
    """How long a WAIT or SLEEP lasts: a fixed span, or until a clock time.

    Exactly one field is set. `until_time_of_day` is a band name the validator
    checks; `until_minute_of_day` is minutes after midnight, already in range.
    """

    minutes: int | None = None
    until_time_of_day: str | None = None
    until_minute_of_day: int | None = None


@dataclass
class WaitAction:
    verb: ClassVar[str] = "WAIT"
    duration: Duration


@dataclass
class SleepAction:
    """`duration` is None for sleeping until woken."""

    verb: ClassVar[str] = "SLEEP"
    duration: Duration | None = None


@dataclass
class ExerciseAction:
    """`minutes` is None for the default."""

    verb: ClassVar[str] = "EXERCISE"
    exercise_name: str
    minutes: int | None = None


@dataclass
class ShoutAction:
    """A shout into the world; it takes no time of its own."""

    verb: ClassVar[str] = "SHOUT"


@dataclass
class TalkAction:
    """Say something to an NPC in one of the closed `TALK` approaches."""

    verb: ClassVar[str] = "TALK"
    npc_name: str
    approach: str


@dataclass
class AskAction:
    """A request of an NPC; `argument` is the item for `give`, the topic for `about`."""

    verb: ClassVar[str] = "ASK"
    npc_name: str
    request: str
    argument: str = ""


@dataclass
class GiveAction:
    verb: ClassVar[str] = "GIVE"
    item_name: str
    npc_name: str


@dataclass
class AddGoalAction:
    verb: ClassVar[str] = "ADD_GOAL"
    horizon: str
    goal_text: str


@dataclass
class RemoveGoalAction:
    verb: ClassVar[str] = "REMOVE_GOAL"
    horizon: str
    goal_text: str


@dataclass
class AddRelationshipNoteAction:
    verb: ClassVar[str] = "ADD_RELATIONSHIP_NOTE"
    npc_name: str
    note: str


AnyAction = (
    MoveAction
    | StanceAction
    | TakeAction
    | DropAction
    | WearAction
    | TakeOffAction
    | AttackAction
    | ShoveAction
    | OpenAction
    | CloseAction
    | BarricadeAction
    | UnbarricadeAction
    | EquipAction
    | UnequipAction
    | UseItemAction
    | BandageAction
    | RemoveBandageAction
    | DisinfectAction
    | WaitAction
    | SleepAction
    | ExerciseAction
    | ShoutAction
    | TalkAction
    | AskAction
    | GiveAction
    | AddGoalAction
    | RemoveGoalAction
    | AddRelationshipNoteAction
)
