from dataclasses import dataclass

import player


@dataclass
class XPMultiplier:
    multiplier: float


@dataclass
class DamageMultiplier:
    multiplier: float


@dataclass
class XPAdjustment:
    amount: int


@dataclass
class HPAdjustment:
    amount: int


@dataclass
class Conditions:
    conditions: dict[player.Condition, bool]


@dataclass
class Attributes:
    attributes: dict[player.Attribute, int]


Modifier = (
    XPMultiplier
    | DamageMultiplier
    | Conditions
    | Attributes
    | HPAdjustment
    | XPAdjustment
)
