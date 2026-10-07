"""Wording of the state questions that check the narrator's story."""

ZOMBIE_DEATH_QUESTION = "By the end of the story, has the zombie been killed or put down for good?"
ZOMBIE_DEATH_OPTIONS: tuple[tuple[str, str], ...] = (
    ("yes", "The story says or implies the zombie is dead or will not get up again."),
    ("no", "The zombie is still alive, even if hurt or knocked down."),
    ("unclear", "The story does not say."),
)
ZOMBIE_DEAD_FACT = "The zombie is dead at the end of this turn."
ZOMBIE_ALIVE_FACT = "The zombie is still alive at the end of this turn."
