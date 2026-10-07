from dataclasses import dataclass

from modules.character.faction import CharacterFaction
from modules.character.state import CharacterCondition


@dataclass
class DamageMultiplicativeModifier:
    multiplier: float


@dataclass
class XPModifier:
    amount: int


@dataclass
class ConditionsModifier:
    conditions: dict[CharacterCondition, bool]


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
    DamageMultiplicativeModifier
    | ConditionsModifier
    | XPModifier
    | AffinityModifier
    | ReputationModifier
)
