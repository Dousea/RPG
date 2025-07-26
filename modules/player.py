from dataclasses import dataclass, field
from enum import StrEnum

import entity
import item
import perk
import trait


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


@dataclass
class Player(entity.Entity):
    name: str
    experience_points: int = 0
    level: int = 1
    max_inventory_size: int = 20
    inventory: list[item.Item] = field(default_factory=list[item.Item])
    hunger: int = 100
    thirst: int = 100
    morale: int = 100
    attributes: dict[Attribute, int] = field(
        default_factory=lambda: {
            Attribute.AGILITY: 3,
            Attribute.STRENGTH: 3,
            Attribute.INTELLIGENCE: 3,
            Attribute.WILLPOWER: 3,
            Attribute.LUCK: 3,
            Attribute.CHARISMA: 3,
        }
    )
    equipment: dict[EquipmentSlot, item.Equippable | None] = field(
        default_factory=lambda: {
            **{slot: None for slot in HoldableSlot},
            **{slot: None for slot in ArmorSlot},
            **{slot: None for slot in AccessorySlot},
        }
    )
    traits: list[trait.Trait] = field(default_factory=list[trait.Trait])
    perks: list[perk.Perk] = field(default_factory=list[perk.Perk])
    conditions: list[Condition] = field(default_factory=list[Condition])
