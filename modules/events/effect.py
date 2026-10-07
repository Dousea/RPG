from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

from modules.entity import BaseEntity
from modules.events.event import (
    ApplyItemEvent,
    ConsumeItemEvent,
    QuestCompletionEvent,
    WeaponDealDamageEvent,
    WeaponTakeDamageEvent,
)
from modules.events.modifier import AnyModifier


@dataclass
class QuestCompletedEffect:
    effect: Callable[[QuestCompletionEvent], AnyModifier | None]
    condition: Callable[[QuestCompletionEvent], bool] = lambda _: True  # Default to always true


@dataclass
class WeaponDamageTakenEffect[T: BaseEntity = BaseEntity, U: BaseEntity = BaseEntity]:
    effect: Callable[[WeaponTakeDamageEvent[T, U]], AnyModifier | None]
    condition: Callable[[WeaponTakeDamageEvent[T, U]], bool] = lambda _: True


@dataclass
class WeaponDamageDealtEffect[T: BaseEntity = BaseEntity, U: BaseEntity = BaseEntity]:
    effect: Callable[[WeaponDealDamageEvent[T, U]], AnyModifier | None]
    condition: Callable[[WeaponDealDamageEvent[T, U]], bool] = lambda _: True


@dataclass
class ItemAppliedEffect[T: BaseEntity = BaseEntity, U: BaseEntity = BaseEntity]:
    effect: Callable[[ApplyItemEvent[T, U]], AnyModifier | None]
    condition: Callable[[ApplyItemEvent[T, U]], bool] = lambda _: True


@dataclass
class ItemConsumedEffect[T: BaseEntity = BaseEntity]:
    effect: Callable[[ConsumeItemEvent[T]], AnyModifier | None]
    condition: Callable[[ConsumeItemEvent[T]], bool] = lambda _: True


AnyEffect = (
    QuestCompletedEffect
    | WeaponDamageTakenEffect[Any, Any]
    | WeaponDamageDealtEffect[Any, Any]
    | ItemAppliedEffect[Any, Any]
    | ItemConsumedEffect[Any]
)
