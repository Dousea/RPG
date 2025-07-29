from dataclasses import dataclass
from enum import StrEnum

from effect import AnyEffect


class PlayerAttribute(StrEnum):
    AGILITY = "agility"
    STRENGTH = "strength"
    INTELLIGENCE = "intelligence"
    WILLPOWER = "willpower"
    LUCK = "luck"
    CHARISMA = "charisma"


@dataclass
class PlayerPerk:
    id: str
    name: str
    description: str
    effects: list[AnyEffect]


@dataclass
class PlayerTrait:
    id: str
    name: str
    description: str
    effects: list[AnyEffect]
