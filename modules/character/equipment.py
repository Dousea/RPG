from enum import StrEnum


class CharacterHoldableSlot(StrEnum):
    RIGHT_HAND = "right_hand"
    LEFT_HAND = "left_hand"


class CharacterArmorSlot(StrEnum):
    HEAD = "head"
    TORSO = "torso"
    LEGS = "legs"
    FEET = "feet"
    SHOULDERS = "shoulders"  # For backpacks, etc.


class CharacterAccessorySlot(StrEnum):
    ACCESSORY_1 = "accessory_1"  # For watches, etc.
    ACCESSORY_2 = "accessory_2"


AnyCharacterEquipmentSlot = CharacterHoldableSlot | CharacterArmorSlot | CharacterAccessorySlot
