"""Skills: what a skill is and the XP and level a character holds in it (skills)."""

from dataclasses import dataclass


@dataclass(frozen=True)
class SkillDefinition:
    """`passive` skills (Fitness, Strength) have the larger XP table and lose XP when untrained."""

    id: str
    name: str
    category: str
    passive: bool = False


@dataclass
class SkillState:
    """`xp` is the total, not the progress inside the level."""

    level: int = 0
    xp: float = 0.0
