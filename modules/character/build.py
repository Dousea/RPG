"""The choices a player makes on the creation screen (spec 07)."""

from dataclasses import dataclass

from modules.character.appearance import Appearance


@dataclass(frozen=True)
class CharacterBuild:
    """Choices only: no granted traits and no derived values."""

    appearance: Appearance
    occupation_id: str
    job_title: str = ""
    traits: tuple[str, ...] = ()
    outfit: tuple[str, ...] = ()


@dataclass(frozen=True)
class ResolvedCharacter:
    """A build with its derived values: what the occupation grants, skills and points."""

    granted_traits: tuple[str, ...]
    traits: tuple[str, ...]
    skills: dict[str, int]
    skill_boosts: dict[str, int]
    points_left: int
