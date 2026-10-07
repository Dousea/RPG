"""Wording of the state questions that check the narrator's story."""

ZOMBIE_STATE_QUESTION = "At the end of the story, what state is the zombie in?"
ZOMBIE_STATE_OPTIONS: tuple[tuple[str, str], ...] = (
    ("standing", "Alive and still on its feet."),
    ("down", "Alive but knocked to the ground."),
    ("dead", "Dead or destroyed."),
    ("unclear", "The story does not say."),
)
ZOMBIE_DEAD_FACT = "The zombie is dead at the end of this turn."
ZOMBIE_ALIVE_FACT = "The zombie is still alive at the end of this turn."
