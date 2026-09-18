from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum
from typing import TYPE_CHECKING

if TYPE_CHECKING:
    # Imported lazily to break the cycle:
    # effect -> entity.player -> character.player -> effect
    from ..effect import AnyEffect


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
