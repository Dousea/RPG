from enum import StrEnum


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
