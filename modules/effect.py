from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import entity
import event
import modifier


@dataclass
class Once:
    effect: Callable[[entity.Player], Any]


@dataclass
class QuestCompleted:
    effect: Callable[[event.QuestCompletion], modifier.Modifier | None]
    condition: Callable[[event.QuestCompletion], bool] = (
        lambda _: True
    )  # Default to always true


@dataclass
class WeaponDamageTaken[
    T: entity.Entity = entity.Entity, U: entity.Entity = entity.Entity
]:
    effect: Callable[[event.WeaponTakeDamage[T, U]], modifier.Modifier | None]
    condition: Callable[[event.WeaponTakeDamage[T, U]], bool] = lambda _: True


@dataclass
class WeaponDamageDealt[
    T: entity.Entity = entity.Entity, U: entity.Entity = entity.Entity
]:
    effect: Callable[[event.WeaponDealDamage[T, U]], modifier.Modifier | None]
    condition: Callable[[event.WeaponDealDamage[T, U]], bool] = lambda _: True


@dataclass
class ItemApplied[T: entity.Entity = entity.Entity, U: entity.Entity = entity.Entity]:
    effect: Callable[[event.ApplyItem[T, U]], modifier.Modifier | None]
    condition: Callable[[event.ApplyItem[T, U]], bool] = lambda _: True


@dataclass
class ItemConsumed[T: entity.Entity = entity.Entity]:
    effect: Callable[[event.ConsumeItem[T]], modifier.Modifier | None]
    condition: Callable[[event.ConsumeItem[T]], bool] = lambda _: True
