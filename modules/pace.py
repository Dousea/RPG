"""How fast the player is moving (spec 09)."""

from enum import StrEnum


class Pace(StrEnum):
    WALK = "walk"
    RUN = "run"
    SNEAK = "sneak"
    STILL = "still"
