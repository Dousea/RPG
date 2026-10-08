"""Wording of the state questions that check the narrator's story."""

ZOMBIE_DEATH_QUESTION = "By the end of the story, has the zombie been killed or put down for good?"
ZOMBIE_DEATH_OPTIONS: tuple[tuple[str, str], ...] = (
    ("yes", "The story says or implies the zombie is dead or will not get up again."),
    ("no", "The zombie is still alive, even if hurt or knocked down."),
    ("unclear", "The story does not say."),
)
ZOMBIE_DEAD_FACT = "The zombie is dead at the end of this turn."
ZOMBIE_ALIVE_FACT = "The zombie is still alive at the end of this turn."

REFUSED_ACTION_QUESTION = "Does the story say that {name} managed to {action}?"
REFUSED_ACTION_OPTIONS: tuple[tuple[str, str], ...] = (
    ("yes", "The story says or clearly shows that this happened."),
    ("no", "The story says it did not happen, or shows something else happening instead."),
    ("unclear", "The story does not say."),
)
REFUSED_ACTION_FACT = "{name} does not {action}: {reason}"

FOUND_NOTHING_QUESTION = "Does the story say that {name}'s search found nothing at all?"
FOUND_NOTHING_OPTIONS: tuple[tuple[str, str], ...] = (
    ("yes", "The story says the search turned up nothing, or that the place was bare or empty."),
    ("no", "The story names at least one thing that was found."),
    ("unclear", "The story does not say."),
)
FOUND_ITEMS_FACT = "{name}'s search turns things up; the story names what was found."

PLAN_QUESTION = (
    'Is "{action}" something the player asked for, or a step needed to do what they asked?'
)
PLAN_OPTIONS: tuple[tuple[str, str], ...] = (
    ("yes", "It is what the player asked for, part of it, or a step needed for it."),
    ("no", "It is something else: the player did not ask for it and it does not lead there."),
    ("unclear", "Cannot tell."),
)
UNSUPPORTED_QUESTION = 'Given these verbs:\n{verbs}\ndoes one of them do "{action}"?'
UNSUPPORTED_OPTIONS: tuple[tuple[str, str], ...] = (
    ("yes", "One of the listed verbs does what is described."),
    ("no", "None of the listed verbs does it."),
    ("unclear", "Cannot tell."),
)
PLAN_NOT_UNDERSTOOD_FACT = (
    "Refused: {name}'s request wasn't understood as an action; the player can rephrase it."
)
PLAN_REFUSED_FACT = "Refused: {name} can't do that here, and does not {action}."
