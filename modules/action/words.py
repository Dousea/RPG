"""A few words for what an action would have done, for facts about actions that never ran."""

from modules.action.parser import ParseFailure
from modules.action.types import (
    AddGoalAction,
    AddRelationshipNoteAction,
    AnyAction,
    AttackAction,
    BandageAction,
    BarricadeAction,
    CloseAction,
    DisinfectAction,
    DropAction,
    EquipAction,
    ExerciseAction,
    MoveAction,
    OpenAction,
    RemoveBandageAction,
    RemoveGoalAction,
    ShoutAction,
    ShoveAction,
    SleepAction,
    StanceAction,
    TakeAction,
    TakeOffAction,
    UnbarricadeAction,
    UnequipAction,
    UseItemAction,
    WaitAction,
    WearAction,
)


def refusal_in_words(failure: ParseFailure, forename: str, subject: str) -> str:
    """A refusal fact for a line that never parsed: no raw text, grammar or numbers."""
    if failure.verb is None:
        return f"Refused: {forename}'s attempt isn't something {subject} can do here."
    return f"Refused: {forename} tried to {failure.verb.lower().replace('_', ' ')}, but it wasn't clear how."


def describe_action(action: AnyAction) -> str:
    match action:
        case MoveAction(destination=place):
            return f"go to {place}"
        case StanceAction(sneaking=True):
            return "start sneaking"
        case StanceAction():
            return "stop sneaking"
        case TakeAction(item_name=name):
            return f"take the {name}"
        case DropAction(item_name=name):
            return f"drop the {name}"
        case WearAction(item_name=name):
            return f"put on the {name}"
        case TakeOffAction(item_name=name):
            return f"take off the {name}"
        case UseItemAction(item_name=name):
            return f"use the {name}"
        case AttackAction(target_name=name):
            return f"attack {name}"
        case ShoveAction(target_name=name):
            return f"shove {name}"
        case OpenAction(barrier_name=name):
            return f"open the {name}"
        case CloseAction(barrier_name=name):
            return f"close the {name}"
        case BarricadeAction(barrier_name=name):
            return f"board up the {name}"
        case UnbarricadeAction(barrier_name=name):
            return f"pry the planks off the {name}"
        case EquipAction(item_name=name):
            return f"take the {name} in hand"
        case UnequipAction(item_name=name):
            return f"put the {name} away"
        case BandageAction(part_name=part):
            return f"bandage the {part}" if part else "bandage a wound"
        case RemoveBandageAction(part_name=part):
            return f"take the bandage off the {part}"
        case DisinfectAction(part_name=part):
            return f"disinfect the {part}"
        case WaitAction():
            return "wait"
        case SleepAction():
            return "sleep"
        case ExerciseAction(exercise_name=name):
            return f"do {name.lower()}"
        case ShoutAction():
            return "shout"
        case AddGoalAction() | RemoveGoalAction():
            return "think about their goals"
        case AddRelationshipNoteAction(npc_name=name):
            return f"make a note about {name}"
    return action.verb.lower().replace("_", " ")
