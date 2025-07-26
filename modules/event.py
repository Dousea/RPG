from dataclasses import dataclass
from typing import Any

import item
import player
import quest


Entity = player.Player | Any # Could be any entity that can interact with items or events


@dataclass
class QuestCompletion:
    source: player.Player
    experience_points_gained: int
    styles: list[quest.QuestStyle]  # e.g., [QuestStyle.NON_VIOLENT, QuestStyle.STEALTH]


@dataclass
class WeaponTakeDamage:
    source: Entity  # Could be player, an object, etc.
    weapon: item.MeleeWeapon | item.RangedWeapon
    damage: int
    target: Entity  # The one that took the damage


@dataclass
class WeaponDealDamage:
    source: Entity  # The one dealing the damage
    weapon: item.MeleeWeapon | item.RangedWeapon
    damage: int
    target: Entity  # Could be player, an object, etc.


@dataclass
class ApplyItem:
    source: Entity  # The one applying the item
    item: item.Appliable
    target: Entity  # Could be player, an object, etc.


@dataclass
class ConsumeItem:
    source: Any
    item: item.Consumable


Type = QuestCompletion | WeaponTakeDamage | WeaponDealDamage | ApplyItem | ConsumeItem
