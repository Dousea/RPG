from enum import StrEnum


class Attribute(StrEnum):
    AGILITY = "agility"
    STRENGTH = "strength"
    INTELLIGENCE = "intelligence"
    WILLPOWER = "willpower"
    LUCK = "luck"
    CHARISMA = "charisma"


class Condition(StrEnum):
    POISONED = "poisoned"
    STUNNED = "stunned"
    BURNED = "burned"
    FROZEN = "frozen"
    PANIC = "panic"


class HoldableSlot(StrEnum):
    RIGHT_HAND = "right_hand"
    LEFT_HAND = "left_hand"


class ArmorSlot(StrEnum):
    HEAD = "head"
    TORSO = "torso"
    LEGS = "legs"
    FEET = "feet"
    SHOULDERS = "shoulders"  # For backpacks, etc.


class AccessorySlot(StrEnum):
    ACCESSORY_1 = "accessory_1"  # For watches, etc.
    ACCESSORY_2 = "accessory_2"


EquipmentSlot = HoldableSlot | ArmorSlot | AccessorySlot
