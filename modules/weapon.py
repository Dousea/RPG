from enum import StrEnum


class MeleeWeaponType(StrEnum):
    BLUNT = "blunt"
    BLADE = "blade"


class RangedWeaponType(StrEnum):
    PISTOL = "pistol"
    RIFLE = "rifle"
    SHOTGUN = "shotgun"


AnyWeaponType = MeleeWeaponType | RangedWeaponType
