"""The player's survival stats and the status effect kinds derived from them (spec 02)."""

import logging
from dataclasses import dataclass
from enum import Enum

logger = logging.getLogger(__name__)


class CharacterStat(Enum):
    HUNGER = "hunger"
    THIRST = "thirst"
    FATIGUE = "fatigue"
    ENDURANCE = "endurance"
    STRESS = "stress"
    PANIC = "panic"
    IDLENESS = "idleness"
    BOREDOM = "boredom"
    UNHAPPINESS = "unhappiness"
    PAIN = "pain"
    INTOXICATION = "intoxication"
    FOOD_SICKNESS = "food_sickness"
    ZOMBIE_INFECTION = "zombie_infection"
    TEMPERATURE = "temperature"
    WETNESS = "wetness"
    SICKNESS = "sickness"

    @property
    def min(self) -> float:
        return STAT_RANGES[self].min

    @property
    def max(self) -> float:
        return STAT_RANGES[self].max

    @property
    def default(self) -> float:
        return STAT_RANGES[self].default


@dataclass(frozen=True)
class StatRange:
    min: float
    max: float
    default: float


STAT_RANGES: dict[CharacterStat, StatRange] = {  # spec 02
    CharacterStat.HUNGER: StatRange(0, 1, 0),
    CharacterStat.THIRST: StatRange(0, 1, 0),
    CharacterStat.FATIGUE: StatRange(0, 1, 0),
    CharacterStat.ENDURANCE: StatRange(0, 1, 1),
    CharacterStat.STRESS: StatRange(0, 1, 0),
    CharacterStat.PANIC: StatRange(0, 100, 0),
    CharacterStat.IDLENESS: StatRange(0, 1, 0),
    CharacterStat.BOREDOM: StatRange(0, 100, 0),
    CharacterStat.UNHAPPINESS: StatRange(0, 100, 0),
    CharacterStat.PAIN: StatRange(0, 100, 0),
    CharacterStat.INTOXICATION: StatRange(0, 100, 0),
    CharacterStat.FOOD_SICKNESS: StatRange(0, 100, 0),
    CharacterStat.ZOMBIE_INFECTION: StatRange(0, 100, 0),
    CharacterStat.TEMPERATURE: StatRange(20, 40, 37),
    CharacterStat.WETNESS: StatRange(0, 100, 0),
    CharacterStat.SICKNESS: StatRange(0, 1, 0),
}


class Stats:
    """A clamped mapping of every `CharacterStat` to its current value."""

    def __init__(self) -> None:
        self._values: dict[CharacterStat, float] = {stat: stat.default for stat in CharacterStat}

    def get(self, stat: CharacterStat) -> float:
        return self._values[stat]

    def set(self, stat: CharacterStat, value: float) -> None:
        self._values[stat] = max(stat.min, min(stat.max, value))

    def add(self, stat: CharacterStat, amount: float) -> None:
        self.set(stat, self._values[stat] + amount)

    def remove(self, stat: CharacterStat, amount: float) -> None:
        self.set(stat, self._values[stat] - amount)

    def reset(self, stat: CharacterStat | None = None) -> None:
        """Return one stat, or every stat, to its default."""
        for each in CharacterStat if stat is None else (stat,):
            self._values[each] = each.default

    def to_dict(self) -> dict[str, float]:
        return {stat.value: value for stat, value in self._values.items()}

    @classmethod
    def from_dict(cls, data: dict[str, float]) -> "Stats":
        stats = cls()
        for name, value in data.items():
            try:
                stat = CharacterStat(name)
            except ValueError:
                logger.warning(f"Dropping unknown stat '{name}'.")
                continue
            stats.set(stat, float(value))
        return stats


class StatusEffect(Enum):
    HUNGRY = "hungry"
    THIRST = "thirst"
    TIRED = "tired"
    ENDURANCE = "endurance"
    STRESS = "stress"
    PANIC = "panic"
    BORED = "bored"
    UNHAPPY = "unhappy"
    PAIN = "pain"
    DRUNK = "drunk"
    SICK = "sick"
    FOOD_EATEN = "food_eaten"
