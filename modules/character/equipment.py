from enum import StrEnum


class CharacterHoldableSlot(StrEnum):
    RIGHT_HAND = "right_hand"
    LEFT_HAND = "left_hand"


class CharacterArmorSlot(StrEnum):
    SHOULDERS = "shoulders"  # For backpacks, etc.


AnyCharacterEquipmentSlot = CharacterHoldableSlot | CharacterArmorSlot
