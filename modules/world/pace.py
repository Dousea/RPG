"""How fast the player is moving (zombies)."""

from enum import StrEnum


class Pace(StrEnum):
    WALK = "walk"
    RUN = "run"
    SNEAK = "sneak"
    STILL = "still"
