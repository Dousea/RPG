from enum import StrEnum


class MeleeType(StrEnum):
    BLUNT = "blunt"
    BLADE = "blade"


class RangedType(StrEnum):
    PISTOL = "pistol"
    RIFLE = "rifle"
    SHOTGUN = "shotgun"


Type = MeleeType | RangedType
