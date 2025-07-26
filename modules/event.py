from dataclasses import dataclass

import entity
import item
import quest


@dataclass
class QuestCompletion:
    source: entity.Player
    experience_points_gained: int
    styles: list[quest.QuestStyle]  # e.g., [QuestStyle.NON_VIOLENT, QuestStyle.STEALTH]


@dataclass
class WeaponTakeDamage[
    T: entity.Entity = entity.Entity, U: entity.Entity = entity.Entity
]:
    source: T  # Could be player, an object, etc.
    weapon: item.MeleeWeapon | item.RangedWeapon
    damage: int
    target: U  # The one that took the damage


@dataclass
class WeaponDealDamage[
    T: entity.Entity = entity.Entity, U: entity.Entity = entity.Entity
]:
    source: T  # The one dealing the damage
    weapon: item.MeleeWeapon | item.RangedWeapon
    damage: int
    target: U  # Could be player, an object, etc.


@dataclass
class ApplyItem[T: entity.Entity = entity.Entity, U: entity.Entity = entity.Entity]:
    source: T  # The one applying the item
    item: item.Appliable
    target: U  # Could be player, an object, etc.


@dataclass
class ConsumeItem[T: entity.Entity = entity.Entity]:
    source: T  # The one consuming the item
    item: item.Consumable
