"""The typed actions the parser LLM may propose, as the validator and simulation see them."""

from dataclasses import dataclass


@dataclass
class MoveAction:
    destination: str
    run: bool = False


@dataclass
class StanceAction:
    """Start or stop sneaking; takes no time."""

    sneaking: bool


@dataclass
class TakeAction:
    item_name: str


@dataclass
class DropAction:
    item_name: str


@dataclass
class WearAction:
    item_name: str


@dataclass
class TakeOffAction:
    item_name: str


@dataclass
class AttackAction:
    target_name: str


@dataclass
class UseItemAction:
    item_name: str


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
    duration: Duration


@dataclass
class SleepAction:
    """`duration` is None for sleeping until woken."""

    duration: Duration | None = None


@dataclass
class ExerciseAction:
    """`minutes` is None for the default."""

    exercise_name: str
    minutes: int | None = None


@dataclass
class StatusAddAction:
    status: str


@dataclass
class StatusRemoveAction:
    status: str


@dataclass
class UpdateConditionAction:
    """Parsed but always refused: the engine owns every survival stat."""

    field_name: str
    raw_value: str


@dataclass
class AddGoalAction:
    horizon: str
    goal_text: str


@dataclass
class RemoveGoalAction:
    horizon: str
    goal_text: str


@dataclass
class UpdateRelationshipAction:
    npc_name: str
    axis: str
    amount: int


@dataclass
class AddRelationshipNoteAction:
    npc_name: str
    note: str


@dataclass
class SetFlagAction:
    flag_name: str
    value: bool


@dataclass
class DiscoverFlagAction:
    """The player has learned a world flag's state, whatever it is. Setting a
    flag (engine ground truth) and discovering it (player knowledge) are
    separate actions -- see docs/11-knowledge-firewall.md."""

    flag_name: str


@dataclass
class UpdateInventoryAction:
    item_name: str
    operation: str  # ADD / REMOVE / UPDATE_CONDITION / UPDATE_QUANTITY
    value: str


@dataclass
class NpcMoveAction:
    npc_name: str
    destination: str


@dataclass
class NpcStatusAction:
    npc_name: str
    operation: str  # ADD / REMOVE
    status: str


AnyAction = (
    MoveAction
    | StanceAction
    | TakeAction
    | DropAction
    | WearAction
    | TakeOffAction
    | AttackAction
    | UseItemAction
    | WaitAction
    | SleepAction
    | ExerciseAction
    | StatusAddAction
    | StatusRemoveAction
    | UpdateConditionAction
    | AddGoalAction
    | RemoveGoalAction
    | UpdateRelationshipAction
    | AddRelationshipNoteAction
    | SetFlagAction
    | DiscoverFlagAction
    | UpdateInventoryAction
    | NpcMoveAction
    | NpcStatusAction
)
