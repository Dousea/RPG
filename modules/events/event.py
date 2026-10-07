from dataclasses import dataclass
from typing import Any

from modules.entity import BaseEntity
from modules.entity.player import PlayerEntity
from modules.item import AppliableItem, ConsumableItem, MeleeWeaponItem, RangedWeaponItem
from modules.story.quest import QuestStyle


@dataclass
class QuestCompletionEvent:
    source: PlayerEntity
    styles: list[QuestStyle]  # e.g., [QuestStyle.NON_VIOLENT, QuestStyle.STEALTH]


@dataclass
class WeaponTakeDamageEvent[T: BaseEntity = BaseEntity, U: BaseEntity = BaseEntity]:
    source: T  # Could be player, an object, etc.
    weapon: MeleeWeaponItem | RangedWeaponItem
    damage: int
    target: U  # The one that took the damage


@dataclass
class WeaponDealDamageEvent[T: BaseEntity = BaseEntity, U: BaseEntity = BaseEntity]:
    source: T  # The one dealing the damage
    weapon: MeleeWeaponItem | RangedWeaponItem
    damage: int
    target: U  # Could be player, an object, etc.


@dataclass
class ApplyItemEvent[T: BaseEntity = BaseEntity, U: BaseEntity = BaseEntity]:
    source: T  # The one applying the item
    item: AppliableItem
    target: U  # Could be player, an object, etc.


@dataclass
class ConsumeItemEvent[T: BaseEntity = BaseEntity]:
    source: T  # The one consuming the item
    item: ConsumableItem


AnyEvent = (
    QuestCompletionEvent
    | WeaponTakeDamageEvent[Any, Any]
    | WeaponDealDamageEvent[Any, Any]
    | ApplyItemEvent[Any, Any]
    | ConsumeItemEvent[Any]
)
