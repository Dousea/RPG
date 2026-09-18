from dataclasses import dataclass

from .character.faction import CharacterFaction
from .character.player import PlayerAttribute
from .character.state import CharacterCondition


@dataclass
class XPMultiplicativeModifier:
    multiplier: float


@dataclass
class DamageMultiplicativeModifier:
    multiplier: float


@dataclass
class XPModifier:
    amount: int


@dataclass
class HPModifier:
    amount: int


@dataclass
class ConditionsModifier:
    conditions: dict[CharacterCondition, bool]


@dataclass
class AttributesModifier:
    attributes: dict[PlayerAttribute, int]


@dataclass
class AffinityModifier:
    source_id: str
    target_id: str
    amount: int


@dataclass
class ReputationModifier:
    source_faction: CharacterFaction
    target_faction: CharacterFaction
    amount: int


AnyModifier = (
    XPMultiplicativeModifier
    | DamageMultiplicativeModifier
    | ConditionsModifier
    | AttributesModifier
    | HPModifier
    | XPModifier
    | AffinityModifier
    | ReputationModifier
)
