from dataclasses import dataclass

from character.equipment import (
    AnyCharacterEquipmentSlot,
    CharacterAccessorySlot,
    CharacterArmorSlot,
    CharacterHoldableSlot,
)
from item import BaseItem, EquippableItem
from modifier import AnyModifier
from weapon import MeleeWeaponType, RangedWeaponType


@dataclass
class BaseItem:
    id: str
    name: str
    description: str
    max_hit_points: int
    tags: list[str]


@dataclass
class EquippableItem(BaseItem):
    slots: list[AnyCharacterEquipmentSlot]

    def __post_init__(self):
        if not self.slots:
            raise ValueError("Equippable items must have at least one slot defined.")


@dataclass
class ArmorItem(EquippableItem):
    defense: int

    def __post_init__(self):
        super().__post_init__()
        if not all(isinstance(slot, CharacterArmorSlot) for slot in self.slots):
            raise ValueError("Armor can only use ArmorSlot instances")


@dataclass
class AccessoryItem(EquippableItem):
    modifiers: list[AnyModifier]

    def __post_init__(self):
        super().__post_init__()
        if not all(isinstance(slot, CharacterAccessorySlot) for slot in self.slots):
            raise ValueError("Accessory can only use AccessorySlot instances")


@dataclass
class HoldableItem(EquippableItem):
    is_two_handed: bool

    def __post_init__(self):
        super().__post_init__()
        if not all(isinstance(slot, CharacterHoldableSlot) for slot in self.slots):
            raise ValueError("Holdable can only use HoldableSlot instances")
        if self.is_two_handed and len(self.slots) != 2:
            raise ValueError("Two-handed items must occupy exactly two slots.")


# Consumable is a type of Holdable that can be consumed for an effect.
@dataclass
class ConsumableItem(HoldableItem):
    modifiers: list[AnyModifier]


# Appliable is a type of Holdable that can apply effects when used.
@dataclass
class AppliableItem(HoldableItem):
    modifiers: list[AnyModifier]


@dataclass
class MeleeWeaponItem(HoldableItem):
    type: MeleeWeaponType
    damage: int

    def __post_init__(self):
        super().__post_init__()
        if self.damage <= 0:
            raise ValueError("Weapon damage must be greater than zero.")


@dataclass
class RangedWeaponItem(HoldableItem):
    type: RangedWeaponType
    damage: int
    range: int

    def __post_init__(self):
        super().__post_init__()
        if self.damage <= 0:
            raise ValueError("Weapon damage must be greater than zero.")
        if self.range < 1:
            raise ValueError("Weapon range must be at least 1.")
