"""A few words for what an action would have done, for facts about actions that never ran."""

from modules.action.parser import ParseFailure
from modules.action.types import (
    AddGoalAction,
    AddRelationshipNoteAction,
    AnyAction,
    AttackAction,
    BandageAction,
    BarricadeAction,
    CarryAction,
    CloseAction,
    DisinfectAction,
    DropAction,
    EquipAction,
    ExerciseAction,
    GiveAction,
    MoveAction,
    OpenAction,
    PutAction,
    RemoveBandageAction,
    RemoveGoalAction,
    RequestAction,
    SearchAction,
    ShoutAction,
    ShoveAction,
    SleepAction,
    StanceAction,
    TakeAction,
    TakeOffAction,
    TalkAction,
    UnbarricadeAction,
    UnequipAction,
    UseItemAction,
    WaitAction,
    WearAction,
)

# What each TALK approach does to the NPC named after it.
TALK_WORDS: dict[str, str] = {
    "chat": "chat with",
    "compliment": "compliment",
    "flirt": "flirt with",
    "confide": "confide in",
    "comfort": "comfort",
    "argue": "argue with",
    "insult": "insult",
    "threaten": "threaten",
}


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
        case TakeAction(all_items=True, from_name=source) if source:
            return f"take everything from {source}"
        case TakeAction(all_items=True):
            return "take everything here"
        case TakeAction(item_name=name, from_name=source) if source:
            return f"take the {name} from {source}"
        case TakeAction(item_name=name):
            return f"take the {name}"
        case SearchAction(target_name=name):
            return f"search {name}"
        case DropAction(corpse=True):
            return "put the body down"
        case DropAction(item_name=name):
            return f"drop the {name}"
        case PutAction(item_name=name, target_name=bag):
            return f"put the {name} in the {bag}"
        case CarryAction(corpse_name=name):
            return f"pick up {name}"
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
        case TalkAction(npc_name=npc, approach=approach) if approach in TALK_WORDS:
            return f"{TALK_WORDS[approach]} {npc}"
        case RequestAction(npc_name=npc, request="follow"):
            return f"ask {npc} to come along"
        case RequestAction(npc_name=npc, request="stay"):
            return f"ask {npc} to stay put"
        case RequestAction(npc_name=npc, request="give", argument=item):
            return f"ask {npc} for the {item}"
        case RequestAction(npc_name=npc, request="about", argument=topic):
            return f"ask {npc} about the {topic.replace('_', ' ')}"
        case GiveAction(item_name=item, npc_name=npc):
            return f"give the {item} to {npc}"
    return action.verb.lower().replace("_", " ")
