from dataclasses import dataclass

import character.faction
import character.player
import character.state


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
    conditions: dict[character.state.Condition, bool]


@dataclass
class Attributes:
    attributes: dict[character.player.Attribute, int]


@dataclass
class AffinityAdjustment:
    source_id: str
    target_id: str
    amount: int


@dataclass
class ReputationAdjustment:
    source_faction: character.faction.Faction
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
