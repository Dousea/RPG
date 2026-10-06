"""A character's name and looks (spec 07)."""

from dataclasses import dataclass
from enum import StrEnum


class Gender(StrEnum):
    FEMALE = "female"
    MALE = "male"


@dataclass(frozen=True)
class Appearance:
    forename: str
    surname: str = ""
    gender: Gender = Gender.MALE
    skin_tone: int = 1
    hair_style: str = "short"
    hair_colour: str = "brown"
    beard_style: str = ""
    backstory: str = ""

    @property
    def full_name(self) -> str:
        return f"{self.forename} {self.surname}".strip()

    @property
    def subject(self) -> str:
        return "she" if self.gender == Gender.FEMALE else "he"

    @property
    def object(self) -> str:
        return "her" if self.gender == Gender.FEMALE else "him"

    @property
    def possessive(self) -> str:
        return "her" if self.gender == Gender.FEMALE else "his"
