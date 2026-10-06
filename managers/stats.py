"""Survival stat engine: drivers that move the player's stats over game time (spec 02)."""

import dataclasses
import logging
import math
from dataclasses import dataclass, field
from typing import Protocol

from data import survival as k
from data.status_effects import (
    BLEEDING_LEVEL_CAP,
    CRIT_PENALTY_ENDURANCE,
    CRIT_PENALTY_HEAVY_LOAD,
    CRIT_PENALTY_PANIC,
    DEFENCE_PENALTY_DRUNK,
    DEFENCE_PENALTY_ENDURANCE,
    DEFENCE_PENALTY_TIRED,
    MELEE_DAMAGE_FLOOR,
    PANIC_MELEE_PENALTY_PER_LEVEL,
    STATUS_EFFECT_THRESHOLDS,
    STRESS_MELEE_PENALTY_PER_LEVEL,
    FOOD_EATEN_DRAIN_per_hour,
)
from modules.entity.player import PlayerEntity
from modules.stats import CharacterStat, Stats, StatusEffect

logger = logging.getLogger(__name__)

HOURS_PER_MINUTE = 1 / 60


def status_effect_level(status_effect: StatusEffect, value: float) -> int:
    """The 0 to 4 level a stat value gives a status effect; endurance counts downward."""
    spec = STATUS_EFFECT_THRESHOLDS[status_effect]
    level = 0
    for index, threshold in enumerate(spec.thresholds, start=1):
        if (value <= threshold) if spec.inverted else (value > threshold):
            level = index
    return level


def sick_value(stats: Stats) -> float:
    """The number the Sick status effect reads; wound infection joins it with the health spec."""
    worst = max(
        stats.get(CharacterStat.FOOD_SICKNESS),
        stats.get(CharacterStat.ZOMBIE_INFECTION),
    )
    return worst / 100 + stats.get(CharacterStat.SICKNESS)


def bleeding_level(bleeding_parts: int, neck: bool) -> int:
    """The Bleeding status effect level: bleeding body parts capped at 4, or 4 if the neck bleeds."""
    if neck:
        return BLEEDING_LEVEL_CAP
    return min(bleeding_parts, BLEEDING_LEVEL_CAP)


def status_effect_levels(
    stats: Stats,
    food_eaten_timer: float = 0.0,
    hit_points: int | None = None,
    bleeding: int = 0,
) -> dict[StatusEffect, int]:
    """Every status effect's current level, in table order.

    Injured is off when `hit_points` is not given or is 0; `bleeding` is the
    Bleeding level, 0 until the health spec supplies it.
    """
    levels: dict[StatusEffect, int] = {}
    for status_effect, spec in STATUS_EFFECT_THRESHOLDS.items():
        if status_effect is StatusEffect.FOOD_EATEN:
            levels[status_effect] = status_effect_level(status_effect, food_eaten_timer)
        elif status_effect is StatusEffect.SICK:
            levels[status_effect] = status_effect_level(status_effect, sick_value(stats))
        elif status_effect is StatusEffect.INJURED:
            injured = hit_points is not None and hit_points > 0
            levels[status_effect] = (
                status_effect_level(status_effect, 100 - (hit_points or 0)) if injured else 0
            )
        elif status_effect is StatusEffect.BLEEDING:
            levels[status_effect] = bleeding
        else:
            assert spec.stat is not None
            levels[status_effect] = status_effect_level(status_effect, stats.get(spec.stat))
    return levels


def melee_status_effect_penalty(stats: Stats) -> float:
    """Damage the Panic and Stress status effects subtract from a melee hit (level 2 and up)."""
    penalty = 0.0
    panic = status_effect_level(StatusEffect.PANIC, stats.get(CharacterStat.PANIC))
    if panic >= 2:
        penalty += PANIC_MELEE_PENALTY_PER_LEVEL * panic
    stress = status_effect_level(StatusEffect.STRESS, stats.get(CharacterStat.STRESS))
    if stress >= 2:
        penalty += STRESS_MELEE_PENALTY_PER_LEVEL * stress
    return penalty


def damage_after_status_effects(damage: float, stats: Stats) -> float:
    """A melee hit less the status effect penalty, floored at the minimum damage."""
    reduced = damage - melee_status_effect_penalty(stats)
    return MELEE_DAMAGE_FLOOR if reduced < 0 else reduced


def crit_penalty(endurance: int, heavy_load: int, panic: int) -> float:
    """Crit chance points lost to the Endurance, Heavy Load and Panic levels."""
    return (
        CRIT_PENALTY_ENDURANCE * endurance
        + CRIT_PENALTY_HEAVY_LOAD * heavy_load
        + CRIT_PENALTY_PANIC * panic
    )


def defence_penalty(endurance: int, tired: int, drunk: int) -> int:
    """Defence points lost to the Endurance, Tired and Drunk levels."""
    return (
        DEFENCE_PENALTY_ENDURANCE * endurance
        + DEFENCE_PENALTY_TIRED * tired
        + DEFENCE_PENALTY_DRUNK * drunk
    )


def player_status_effect_levels(player: PlayerEntity) -> dict[StatusEffect, int]:
    return status_effect_levels(player.stats, player.food_eaten_timer, player.hit_points)


def food_eaten_level(player: PlayerEntity) -> int:
    return status_effect_level(StatusEffect.FOOD_EATEN, player.food_eaten_timer)


def active_status_effects(player: PlayerEntity) -> list[tuple[StatusEffect, int, str]]:
    """Status effects above level 0 as (type, level, name), in table order."""
    return [
        (status_effect, level, STATUS_EFFECT_THRESHOLDS[status_effect].names[level - 1])
        for status_effect, level in player_status_effect_levels(player).items()
        if level > 0
    ]


def level_change_facts(
    before: dict[StatusEffect, int], after: dict[StatusEffect, int]
) -> list[str]:
    """One fact per status effect whose level changed, in table order."""
    facts: list[str] = []
    for status_effect, level in after.items():
        if level == before[status_effect]:
            continue
        names = STATUS_EFFECT_THRESHOLDS[status_effect].names
        if level == 0:
            facts.append(f"Orton is no longer {names[before[status_effect] - 1]}.")
        else:
            facts.append(f"Orton is now {names[level - 1]}.")
    return facts


@dataclass(frozen=True)
class BodyMultipliers:
    """Energy, fluids and fatigue multipliers from the thermoregulator; 1 until body temperature lands."""

    energy: float = 1.0
    fluids: float = 1.0
    fatigue: float = 1.0


@dataclass(frozen=True)
class SkillLevels:
    """Fitness and Strength levels; 5 each until skills land."""

    fitness: int = 5
    strength: int = 5


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
    weather: object | None = None
    body: BodyMultipliers = field(default_factory=BodyMultipliers)
    skills: SkillLevels = field(default_factory=SkillLevels)
    corpse_count: int = 0
    corpse_defence: float = 0.0
    traits: frozenset[str] = frozenset()
    food_eaten_level: int = 0


class StatDriver(Protocol):
    def apply(self, stats: Stats, hours: float, ctx: StatContext) -> None: ...


def _recovery_mod(ctx: StatContext) -> float:
    return k.RECOVERY_MOD_STUB


class HungerDriver:
    def apply(self, stats: Stats, hours: float, ctx: StatContext) -> None:
        appetite = 1 - stats.get(CharacterStat.HUNGER)
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
        rate = k.THIRST_INCREASE_per_hour
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
            stats.remove(CharacterStat.FATIGUE, rate * bed * hours)
            return
        loss = max(k.FATIGUE_ENDURANCE_FLOOR, 1 - stats.get(CharacterStat.ENDURANCE))
        gain = k.FATIGUE_INCREASE_per_hour * loss * hours * ctx.body.fatigue
        if ctx.resting:
            gain /= k.FATIGUE_RESTING_DIVISOR
        stats.add(CharacterStat.FATIGUE, gain)


class StressDriver:
    def apply(self, stats: Stats, hours: float, ctx: StatContext) -> None:
        stats.remove(CharacterStat.STRESS, k.STRESS_DECREASE_per_hour * hours)


class EnduranceDriver:
    def apply(self, stats: Stats, hours: float, ctx: StatContext) -> None:
        fatigue = stats.get(CharacterStat.FATIGUE)
        recovery = _recovery_mod(ctx)
        if ctx.asleep:
            delta = k.SLEEPING_ENDURANCE_REGEN_per_hour * recovery
        elif ctx.exercising:
            delta = -k.EXERCISE_ENDURANCE_DRAIN_per_hour
        elif ctx.resting:
            delta = (
                k.IMOBILE_ENDURANCE_INCREASE_per_hour
                * k.SITTING_ENDURANCE_MULTIPLIER
                * (1 - k.SITTING_FATIGUE_PENALTY * fatigue)
                * recovery
            )
        elif ctx.walking:
            level = status_effect_level(StatusEffect.ENDURANCE, stats.get(CharacterStat.ENDURANCE))
            if level >= k.WALKING_DRAIN_ENDURANCE_LEVEL:
                sneak = k.SNEAK_ENDURANCE_FACTOR if ctx.sneaking else 1.0
                delta = -k.WALKING_ENDURANCE_DRAIN_per_hour * sneak
            else:
                delta = (
                    k.IMOBILE_ENDURANCE_INCREASE_per_hour
                    / k.WALKING_ENDURANCE_DIVISOR
                    * (1 - fatigue)
                    * recovery
                )
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
        stats.add(CharacterStat.PANIC, k.PANIC_PER_ZOMBIE * ctx.new_zombies_seen)
        months = min(k.PANIC_REDUCTION_MONTH_CAP, int(ctx.hours_survived // k.HOURS_PER_MONTH))
        rate = k.PANIC_REDUCTION_per_hour * (1 + months)
        if ctx.asleep:
            rate *= k.PANIC_REDUCTION_ASLEEP_FACTOR
        stats.remove(CharacterStat.PANIC, rate * hours)


class IntoxicationDriver:
    def apply(self, stats: Stats, hours: float, ctx: StatContext) -> None:
        stats.remove(CharacterStat.INTOXICATION, k.INTOXICATION_DECREASE_per_hour * hours)


class FoodSicknessDriver:
    def apply(self, stats: Stats, hours: float, ctx: StatContext) -> None:
        if ctx.corpse_count > k.CORPSE_SICKNESS_FREE_CORPSES:
            excess = min(
                ctx.corpse_count - k.CORPSE_SICKNESS_FREE_CORPSES, k.CORPSE_SICKNESS_CORPSE_CAP
            )
            gain = k.CORPSE_SICKNESS_per_hour * excess * hours * (1 - ctx.corpse_defence / 100)
            stats.add(CharacterStat.FOOD_SICKNESS, gain)
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


WEAKENING_FACTS = {
    "starvation": "Orton is weakening from hunger.",
    "thirst": "Orton is weakening from thirst.",
    "fever": "Orton is weakening from fever.",
}


class StatsEngine:
    """Runs every registered driver over a span of minutes in chunks of at most 10.

    After `advance`, `minutes_advanced` is how many minutes actually passed (less
    than asked when the player died), `health_lost` is the fractional HP the
    status effects took, and `death_cause` is set when they took the last of it.
    """

    def __init__(self, drivers: list[StatDriver] | None = None) -> None:
        self._drivers: list[StatDriver] = drivers if drivers is not None else default_drivers()
        self.minutes_advanced = 0
        self.health_lost = 0.0
        self.death_cause = ""
        self._weakening_reported: set[str] = set()

    def register(self, driver: StatDriver) -> None:
        self._drivers.append(driver)

    def advance(self, player: PlayerEntity, minutes: int, ctx: StatContext) -> list[str]:
        """Advance the player's stats by `minutes`; returns status-effect-change and health facts."""
        self.minutes_advanced = 0
        self.health_lost = 0.0
        self.death_cause = ""
        self._weakening_reported = set()
        facts: list[str] = []
        remaining = minutes
        while remaining > 0:
            chunk = min(k.MAX_CHUNK_MINUTES, remaining)
            facts.extend(self._advance_chunk(player, chunk, ctx))
            self.minutes_advanced += chunk
            remaining -= chunk
            ctx = dataclasses.replace(ctx, new_zombies_seen=0)
            if self.death_cause:
                break
        return facts

    def _advance_chunk(self, player: PlayerEntity, minutes: int, ctx: StatContext) -> list[str]:
        stats = player.stats
        hours = minutes * HOURS_PER_MINUTE
        before = player_status_effect_levels(player)
        ctx = dataclasses.replace(ctx, food_eaten_level=food_eaten_level(player))
        for driver in self._drivers:
            driver.apply(stats, hours, ctx)
        player.food_eaten_timer = max(
            0.0, player.food_eaten_timer - FOOD_EATEN_DRAIN_per_hour * hours
        )
        drivers_done = player_status_effect_levels(player)
        health_facts = self._lose_health(player, drivers_done, hours)
        facts = level_change_facts(before, player_status_effect_levels(player))
        facts.extend(health_facts)
        return facts

    def _lose_health(
        self, player: PlayerEntity, levels: dict[StatusEffect, int], hours: float
    ) -> list[str]:
        stats = player.stats
        sources: list[tuple[float, str]] = []
        if levels[StatusEffect.HUNGRY] >= k.SEVERE_STATUS_EFFECT_LEVEL:
            sources.append((k.STARVING_HP_LOSS_per_hour, "starvation"))
        if levels[StatusEffect.THIRST] >= k.SEVERE_STATUS_EFFECT_LEVEL:
            sources.append((k.DYING_OF_THIRST_HP_LOSS_per_hour, "thirst"))
        if levels[StatusEffect.SICK] >= k.SEVERE_STATUS_EFFECT_LEVEL and stats.get(
            CharacterStat.FOOD_SICKNESS
        ) > stats.get(CharacterStat.ZOMBIE_INFECTION):
            sources.append((k.FEVER_HP_LOSS_per_hour, "fever"))
        if not sources:
            return []
        loss = sum(rate for rate, _ in sources) * hours
        self.health_lost += loss
        player.fractional_hp_loss += loss
        whole = math.floor(player.fractional_hp_loss)
        player.fractional_hp_loss -= whole
        player.hit_points -= whole
        if player.hit_points > 0:
            facts: list[str] = []
            for _, cause in sources:
                if cause not in self._weakening_reported:
                    self._weakening_reported.add(cause)
                    facts.append(WEAKENING_FACTS[cause])
            return facts
        player.fractional_hp_loss = 0.0
        cause = max(sources)[1]
        self.death_cause = f"Orton died of {cause}."
        return [self.death_cause]
