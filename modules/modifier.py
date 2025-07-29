from dataclasses import dataclass

import character.condition
import character.faction
import character.player


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
    conditions: dict[character.condition.Condition, bool]


@dataclass
class Attributes:
    attributes: dict[character.player.Attribute, int]


@dataclass
class AffinityAdjustment:
    target_npc_id: str
    amount: int


@dataclass
class ReputationAdjustment:
    target_faction: character.faction.Faction
    amount: int


Modifier = (
    XPMultiplier
    | DamageMultiplier
    | Conditions
    | Attributes
    | HPAdjustment
    | XPAdjustment
    | AffinityAdjustment
    | ReputationAdjustment
)
