from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from enum import StrEnum

import character.condition
import character.equipment
import character.player
import item
import perk
import trait


@dataclass
class Entity(ABC):
    @property
    def id(self) -> int:
        return id(self)

    @property
    def hit_points(self) -> int:
        return self._hit_points

    @hit_points.setter
    def hit_points(self, value: int):
        if value < 0:
            value = 0
        elif value > self.max_hit_points:
            value = self.max_hit_points
        self._hit_points = value

    @property
    @abstractmethod
    def max_hit_points(self) -> int:
        pass

    def __post_init__(self):
        self.hit_points = self.max_hit_points


@dataclass
class Player(Entity):
    name: str
    experience_points: int = 0
    level: int = 1
    max_inventory_size: int = 20
    inventory: list[item.Item] = field(default_factory=list[item.Item])
    hunger: int = 100
    thirst: int = 100
    morale: int = 100
    attributes: dict[character.player.Attribute, int] = field(
        default_factory=lambda: {
            character.player.Attribute.AGILITY: 3,
            character.player.Attribute.STRENGTH: 3,
            character.player.Attribute.INTELLIGENCE: 3,
            character.player.Attribute.WILLPOWER: 3,
            character.player.Attribute.LUCK: 3,
            character.player.Attribute.CHARISMA: 3,
        }
    )
    equipment: dict[character.equipment.EquipmentSlot, item.Equippable | None] = field(
        default_factory=lambda: {
            **{slot: None for slot in character.equipment.HoldableSlot},
            **{slot: None for slot in character.equipment.ArmorSlot},
            **{slot: None for slot in character.equipment.AccessorySlot},
        }
    )
    traits: list[trait.Trait] = field(default_factory=list[trait.Trait])
    perks: list[perk.Perk] = field(default_factory=list[perk.Perk])
    conditions: list[character.condition.Condition] = field(
        default_factory=list[character.condition.Condition]
    )

    @property
    def max_hit_points(self) -> int:
        return 100


@dataclass
class Item(Entity):
    item: item.Item

    @property
    def max_hit_points(self) -> int:
        return self.item.max_hit_points


class LockState(StrEnum):
    LOCKED = "locked"
    UNLOCKED = "unlocked"


class Unlockable(Entity):
    state: LockState = LockState.UNLOCKED
    key_id: str | None = None  # The item_id of the key that unlocks it

    def unlock(self, key: item.Item) -> bool:
        if self.state == LockState.LOCKED and self.key_id == key.id:
            self.state = LockState.UNLOCKED
            return True
        return False


@dataclass
class Door(Unlockable):
    leads_to: str  # The location_id it connects to

    @property
    def max_hit_points(self) -> int:
        return 100


@dataclass
class Container(Unlockable):
    items: list[Item] = field(default_factory=list[Item])

    @property
    def max_hit_points(self) -> int:
        return 50
