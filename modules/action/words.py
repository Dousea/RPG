"""A few words for what an action would have done, for facts about actions that never ran."""

from modules.action.types import (
    AddGoalAction,
    AddRelationshipNoteAction,
    AnyAction,
    AttackAction,
    DropAction,
    ExerciseAction,
    MoveAction,
    RemoveGoalAction,
    ShoutAction,
    SleepAction,
    StanceAction,
    TakeAction,
    TakeOffAction,
    UseItemAction,
    WaitAction,
    WearAction,
)


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
