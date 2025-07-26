from dataclasses import dataclass

import modifier
import player
import weapon


@dataclass
class Item:
    id: str
    name: str
    description: str
    tags: list[str]


@dataclass
class Equippable(Item):
    slots: list[player.EquipmentSlot]

    def __post_init__(self):
        if not self.slots:
            raise ValueError("Equippable items must have at least one slot defined.")


@dataclass
class Armor(Equippable):
    defense: int

    def __post_init__(self):
        super().__post_init__()
        if not all(isinstance(slot, player.ArmorSlot) for slot in self.slots):
            raise ValueError("Armor can only use ArmorSlot instances")


@dataclass
class Accessory(Equippable):
    modifiers: list[modifier.Modifier]

    def __post_init__(self):
        super().__post_init__()
        if not all(isinstance(slot, player.AccessorySlot) for slot in self.slots):
            raise ValueError("Accessory can only use AccessorySlot instances")


@dataclass
class Holdable(Equippable):
    is_two_handed: bool

    def __post_init__(self):
        super().__post_init__()
        if not all(isinstance(slot, player.HoldableSlot) for slot in self.slots):
            raise ValueError("Holdable can only use HoldableSlot instances")
        if self.is_two_handed and len(self.slots) != 2:
            raise ValueError("Two-handed items must occupy exactly two slots.")


# Consumable is a type of Holdable that can be consumed for an effect.
@dataclass
class Consumable(Holdable):
    modifiers: list[modifier.Modifier]


# Appliable is a type of Holdable that can apply effects when used.
@dataclass
class Appliable(Holdable):
    modifiers: list[modifier.Modifier]


@dataclass
class MeleeWeapon(Holdable):
    type: weapon.MeleeType
    damage: int

    def __post_init__(self):
        super().__post_init__()
        if self.damage <= 0:
            raise ValueError("Weapon damage must be greater than zero.")


@dataclass
class RangedWeapon(Holdable):
    type: weapon.RangedType
    damage: int
    range: int

    def __post_init__(self):
        super().__post_init__()
        if self.damage <= 0:
            raise ValueError("Weapon damage must be greater than zero.")
        if self.range < 1:
            raise ValueError("Weapon range must be at least 1.")
