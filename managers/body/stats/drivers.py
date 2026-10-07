"""Stat drivers: each moves some survival stats over a chunk of game time (spec 02)."""

from collections.abc import Mapping
from dataclasses import dataclass, field
from typing import Protocol

from data import carry as carry_k
from data.body import survival as k
from data.body.thermal import Metabolic
from data.character import skills as skill_k
from data.character import traits as trait_k
from data.zombies import lore as zombie_k
from managers import carry
from managers.body.stats.status_effects import status_effect_level
from managers.character.skills import fitness_level
from modules.body.stats import CharacterStat, Stats, StatusEffect
from modules.entity.player import PlayerEntity
from modules.world.weather import WeatherSample


@dataclass(frozen=True)
class BodyMultipliers:
    """Energy, fluids and fatigue multipliers from the thermoregulator; 1 until body temperature lands."""

    energy: float = 1.0
    fluids: float = 1.0
    fatigue: float = 1.0


@dataclass(frozen=True)
class StatContext:
    """What a chunk of game time is, for the drivers that read it."""

    asleep: bool = False
    resting: bool = False
    exercising: bool = False
    walking: bool = False
    sneaking: bool = False
    indoors: bool = False
    talking: bool = False
    npcs_present: bool = False
    bed_type: str = k.DEFAULT_BED_TYPE
    hours_survived: float = 0.0
    new_zombies_seen: int = 0
    sound_stress: float = 0.0  # spec 13: stress from barrier sounds over the chunk
    weather: WeatherSample | None = None
    body: BodyMultipliers = field(default_factory=BodyMultipliers)
    skills: Mapping[str, int] = field(default_factory=dict[str, int])
    corpse_count: int = 0
    corpse_defence: float = 0.0
    traits: frozenset[str] = frozenset()
    food_eaten_level: int = 0
    floor: int = 0
    power_on: bool = True
    metabolic: Metabolic = Metabolic.DEFAULT
    carry_ratio: float = 0.0  # spec 25: carried weight over capacity
    heavy_load: int = 0  # spec 25: the Heavy Load level
    carrying_corpse: bool = False  # spec 25
    wearer: PlayerEntity | None = None


class StatDriver(Protocol):
    def apply(self, stats: Stats, hours: float, ctx: StatContext) -> None: ...


def trait_mult(table: dict[str, float], traits: frozenset[str]) -> float:
    """The product of the factors of the traits in `table` that the character has."""
    mult = 1.0
    for trait, value in table.items():
        if trait in traits:
            mult *= value
    return mult


def _recovery_mod(ctx: StatContext) -> float:
    levels = skill_k.ENDURANCE_RECOVERY_BY_FITNESS
    return levels[max(0, min(len(levels) - 1, fitness_level(ctx.skills)))]


class HungerDriver:
    def apply(self, stats: Stats, hours: float, ctx: StatContext) -> None:
        appetite = (1 - stats.get(CharacterStat.HUNGER)) * trait_mult(
            trait_k.APPETITE_TRAIT_MULT, ctx.traits
        )
        if ctx.asleep:
            if ctx.food_eaten_level == 0:
                rate = k.HUNGER_INCREASE_WHILE_ASLEEP_per_hour
                stats.add(CharacterStat.HUNGER, rate * appetite * hours)
            return
        if ctx.food_eaten_level == 0:
            rate = (
                k.HUNGER_INCREASE_WHEN_EXERCISE_per_hour / k.HUNGER_EXERCISE_FASTED_DIVISOR
                if ctx.exercising
                else k.HUNGER_INCREASE_per_hour
            )
        else:
            rate = (
                k.HUNGER_INCREASE_WHEN_EXERCISE_per_hour
                if ctx.exercising
                else k.HUNGER_INCREASE_WHEN_WELL_FED_per_hour
            )
        stats.add(CharacterStat.HUNGER, rate * appetite * hours * ctx.body.energy)


class ThirstDriver:
    def apply(self, stats: Stats, hours: float, ctx: StatContext) -> None:
        if ctx.asleep:
            stats.add(CharacterStat.THIRST, k.THIRST_SLEEPING_INCREASE_per_hour * hours)
            return
        rate = k.THIRST_INCREASE_per_hour * trait_mult(trait_k.THIRST_TRAIT_MULT, ctx.traits)
        if ctx.exercising:
            rate *= k.THIRST_EXERCISE_MULTIPLIER
        stats.add(CharacterStat.THIRST, rate * hours * ctx.body.fluids)


class FatigueDriver:
    def apply(self, stats: Stats, hours: float, ctx: StatContext) -> None:
        fatigue = stats.get(CharacterStat.FATIGUE)
        if ctx.asleep:
            rate = (
                k.SLEEP_FATIGUE_LOW_per_hour
                if fatigue <= k.SLEEP_FATIGUE_LOW_THRESHOLD
                else k.SLEEP_FATIGUE_HIGH_per_hour
            )
            bed = k.BED_MULTIPLIERS.get(ctx.bed_type, k.BED_MULTIPLIERS[k.DEFAULT_BED_TYPE])
            recovery = trait_mult(trait_k.SLEEP_RECOVERY_TRAIT_MULT, ctx.traits)
            hours_needed = trait_mult(trait_k.SLEEP_HOURS_TRAIT_MULT, ctx.traits)
            stats.remove(CharacterStat.FATIGUE, rate * bed * recovery / hours_needed * hours)
            return
        loss = max(k.FATIGUE_ENDURANCE_FLOOR, 1 - stats.get(CharacterStat.ENDURANCE))
        gain = k.FATIGUE_INCREASE_per_hour * loss * hours * ctx.body.fatigue
        gain *= trait_mult(trait_k.FATIGUE_GAIN_TRAIT_MULT, ctx.traits)
        if ctx.resting:
            gain /= k.FATIGUE_RESTING_DIVISOR
        stats.add(CharacterStat.FATIGUE, gain)


class StressDriver:
    def apply(self, stats: Stats, hours: float, ctx: StatContext) -> None:
        stats.add(CharacterStat.STRESS, ctx.sound_stress)
        stats.remove(CharacterStat.STRESS, k.STRESS_DECREASE_per_hour * hours)


class EnduranceDriver:
    def apply(self, stats: Stats, hours: float, ctx: StatContext) -> None:
        fatigue = stats.get(CharacterStat.FATIGUE)
        recovery = _recovery_mod(ctx)
        if ctx.asleep:
            delta = k.SLEEPING_ENDURANCE_REGEN_per_hour * recovery
        elif ctx.exercising:
            drain = k.EXERCISE_ENDURANCE_DRAIN_per_hour
            if ctx.carrying_corpse and ctx.walking:
                drain = carry_k.CORPSE_CARRY_ENDURANCE_DRAIN_per_hour
            delta = -drain * carry_k.HEAVY_ENDURANCE_MULT[ctx.heavy_load]
        elif ctx.resting:
            delta = (
                k.IMOBILE_ENDURANCE_INCREASE_per_hour
                * k.SITTING_ENDURANCE_MULTIPLIER
                * (1 - k.SITTING_FATIGUE_PENALTY * fatigue)
                * recovery
            )
        elif ctx.walking:
            level = status_effect_level(StatusEffect.ENDURANCE, stats.get(CharacterStat.ENDURANCE))
            if ctx.heavy_load >= carry_k.OVERLOAD_MIN_LEVEL:
                sneak = k.SNEAK_ENDURANCE_FACTOR if ctx.sneaking else 1.0
                drain = carry.walk_drain_per_hour(ctx.heavy_load, ctx.traits)
                delta = -drain * sneak
            elif ctx.heavy_load > carry_k.REGENERATES_UP_TO_LEVEL:
                delta = 0.0
            elif level >= k.WALKING_DRAIN_ENDURANCE_LEVEL:
                sneak = k.SNEAK_ENDURANCE_FACTOR if ctx.sneaking else 1.0
                delta = -k.WALKING_ENDURANCE_DRAIN_per_hour * sneak
            else:
                delta = (
                    k.IMOBILE_ENDURANCE_INCREASE_per_hour
                    / k.WALKING_ENDURANCE_DIVISOR
                    * (1 - fatigue)
                    * recovery
                )
        elif ctx.heavy_load > carry_k.REGENERATES_UP_TO_LEVEL:
            delta = 0.0
        else:
            delta = (
                k.IMOBILE_ENDURANCE_INCREASE_per_hour
                * (1 - k.STANDING_FATIGUE_PENALTY * fatigue)
                * recovery
            )
        stats.add(CharacterStat.ENDURANCE, delta * hours)


class IdlenessDriver:
    def apply(self, stats: Stats, hours: float, ctx: StatContext) -> None:
        if ctx.asleep:
            return
        if ctx.exercising:
            stats.reset(CharacterStat.IDLENESS)
        elif ctx.resting:
            rate = k.IDLE_INCREASE_per_hour
            if ctx.indoors:
                rate += k.IDLE_INDOORS_BONUS_per_hour
            stats.add(CharacterStat.IDLENESS, rate * hours)
        else:
            stats.remove(CharacterStat.IDLENESS, k.IDLE_DECREASE_per_hour * hours)


class BoredomDriver:
    def apply(self, stats: Stats, hours: float, ctx: StatContext) -> None:
        if ctx.asleep:
            return
        boredom = CharacterStat.BOREDOM
        idleness = stats.get(CharacterStat.IDLENESS)
        if not ctx.resting and not ctx.indoors:
            stats.remove(boredom, k.BOREDOM_DECREASE_per_hour * hours)
        else:
            if ctx.resting:
                stats.add(boredom, k.BOREDOM_INCREASE_per_hour * idleness * hours)
            else:
                busy = k.BOREDOM_INCREASE_per_hour / k.BOREDOM_BUSY_INCREASE_DIVISOR
                stats.add(boredom, busy * idleness * hours)
                if idleness < k.BOREDOM_BUSY_IDLENESS_LIMIT:
                    stats.remove(boredom, k.BOREDOM_BUSY_DECAY_per_hour * hours)
            if ctx.talking:
                stats.remove(boredom, k.BOREDOM_TALKING_DECAY_per_hour * hours)
            if ctx.npcs_present:
                stats.remove(boredom, k.BOREDOM_NPC_DECAY_per_hour * hours)
        if stats.get(CharacterStat.INTOXICATION) > k.BOREDOM_DRUNK_THRESHOLD:
            stats.remove(boredom, k.BOREDOM_DRUNK_DECAY_per_hour * hours)
        if stats.get(CharacterStat.PANIC) > k.BOREDOM_PANIC_RESET_THRESHOLD:
            stats.reset(boredom)


class UnhappinessDriver:
    def apply(self, stats: Stats, hours: float, ctx: StatContext) -> None:
        bored = status_effect_level(StatusEffect.BORED, stats.get(CharacterStat.BOREDOM))
        stress = status_effect_level(StatusEffect.STRESS, stats.get(CharacterStat.STRESS))
        gain = 0.0
        if bored >= k.UNHAPPINESS_STATUS_EFFECT_LEVEL:
            gain += k.UNHAPPINESS_INCREASE_per_hour * bored
        if stress >= k.UNHAPPINESS_STATUS_EFFECT_LEVEL:
            gain += k.UNHAPPINESS_INCREASE_per_hour * k.UNHAPPINESS_STRESS_FACTOR * stress
        stats.add(CharacterStat.UNHAPPINESS, gain * hours)


class PanicDriver:
    def apply(self, stats: Stats, hours: float, ctx: StatContext) -> None:
        gain = k.PANIC_PER_ZOMBIE * ctx.new_zombies_seen
        stats.add(CharacterStat.PANIC, gain * trait_mult(trait_k.PANIC_GAIN_TRAIT_MULT, ctx.traits))
        if trait_k.DESENSITIZED_ID in ctx.traits:
            stats.reset(CharacterStat.PANIC)
        months = min(k.PANIC_REDUCTION_MONTH_CAP, int(ctx.hours_survived // k.HOURS_PER_MONTH))
        rate = k.PANIC_REDUCTION_per_hour * (1 + months)
        if ctx.asleep:
            rate *= k.PANIC_REDUCTION_ASLEEP_FACTOR
        stats.remove(CharacterStat.PANIC, rate * hours)


class IntoxicationDriver:
    def apply(self, stats: Stats, hours: float, ctx: StatContext) -> None:
        stats.remove(CharacterStat.INTOXICATION, k.INTOXICATION_DECREASE_per_hour * hours)


class FoodSicknessDriver:
    """Corpses add sickness and, while they do, the usual decay stops (spec 14)."""

    def apply(self, stats: Stats, hours: float, ctx: StatContext) -> None:
        excess = min(
            max(ctx.corpse_count - k.CORPSE_SICKNESS_FREE_CORPSES, 0), k.CORPSE_SICKNESS_CORPSE_CAP
        )
        rate = (
            k.CORPSE_SICKNESS_per_hour
            * excess
            * (1 - ctx.corpse_defence / 100)
            * trait_mult(zombie_k.CORPSE_SICKNESS_TRAIT_MULT, ctx.traits)
        )
        if rate > 0:
            stats.add(CharacterStat.FOOD_SICKNESS, rate * hours)
        else:
            stats.remove(CharacterStat.FOOD_SICKNESS, k.FOOD_SICKNESS_DECREASE_per_hour * hours)


def default_drivers() -> list[StatDriver]:
    return [
        HungerDriver(),
        ThirstDriver(),
        FatigueDriver(),
        StressDriver(),
        EnduranceDriver(),
        IdlenessDriver(),
        BoredomDriver(),
        UnhappinessDriver(),
        PanicDriver(),
        IntoxicationDriver(),
        FoodSicknessDriver(),
    ]
