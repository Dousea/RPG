"""Exercise: rep timing, what a rep does, regularity and stiffness over time (spec 08)."""

import math
import random

from data.character import exercises as exercise_k
from data.character.skills import FITNESS, STRENGTH
from data.world.clock import MINUTES_PER_HOUR
from managers import carry
from managers.body.stats.status_effects import player_status_effect_levels, status_effect_level
from managers.character.skills import SkillEngine, fitness_level, skill_levels
from modules.body.stats import CharacterStat, StatusEffect
from modules.character.exercise import ExerciseDefinition
from modules.entity.player import PlayerEntity

STRENGTH_REGIONS = {"arms": exercise_k.XP_ARMS_STRENGTH, "chest": exercise_k.XP_CHEST_STRENGTH}
FITNESS_REGIONS = {"legs": exercise_k.XP_LEGS_FITNESS, "abs": exercise_k.XP_ABS_FITNESS}


def endurance_level(player: PlayerEntity) -> int:
    return status_effect_level(StatusEffect.ENDURANCE, player.stats.get(CharacterStat.ENDURANCE))


def tired_level(player: PlayerEntity) -> int:
    return status_effect_level(StatusEffect.TIRED, player.stats.get(CharacterStat.FATIGUE))


def rep_speed(fitness: int, endurance_status_effect_level: int) -> float:
    """The animation speed: faster with Fitness, slower when winded, never below 1 when struggling."""
    speed = (
        fitness / exercise_k.SPEED_FITNESS_DIVISOR / exercise_k.SPEED_FITNESS_SCALE
        - endurance_status_effect_level / exercise_k.SPEED_ENDURANCE_DIVISOR
    )
    speed = min(speed, exercise_k.SPEED_MAX)
    return exercise_k.SPEED_STRUGGLE_VALUE if speed < exercise_k.SPEED_STRUGGLE_BELOW else speed


def reps_per_minute(
    exercise: ExerciseDefinition, fitness: int, endurance_status_effect_level: int
) -> float:
    speed = rep_speed(fitness, endurance_status_effect_level)
    return exercise_k.REP_SECONDS_PER_GAME_MINUTE * speed / exercise.rep_period_s


def starting_regularity(occupation_id: str, seed: int) -> dict[str, float]:
    """Each exercise's regularity at the start, drawn once from the world seed."""
    bounds = exercise_k.STARTING_REGULARITY.get(occupation_id)
    if bounds is None:
        return {exercise_id: 0.0 for exercise_id in exercise_k.EXERCISES}
    rng = random.Random(seed)
    return {exercise_id: float(rng.randrange(*bounds)) for exercise_id in exercise_k.EXERCISES}


class ExerciseEngine:
    """Applies reps to the player and runs the 10-minute boundary for regularity and stiffness."""

    def __init__(self, skills: SkillEngine) -> None:
        self._skills = skills

    def do_rep(self, player: PlayerEntity, exercise: ExerciseDefinition, now: int) -> list[str]:
        """One rep: regularity, endurance, future stiffness, XP. Returns level-change facts."""
        state = player.exercise
        fitness = fitness_level(skill_levels(player))
        gain = (
            exercise_k.REGULARITY_GAIN
            * math.log(exercise_k.REGULARITY_LOG_NUMERATOR)
            / math.log(
                fitness / exercise_k.REGULARITY_FITNESS_DIVISOR
                + exercise_k.REGULARITY_FITNESS_OFFSET
            )
        )
        regularity = min(exercise_k.REGULARITY_MAX, state.regularity.get(exercise.id, 0.0) + gain)
        state.regularity[exercise.id] = regularity
        state.last_done_minute[exercise.id] = now

        heavy = exercise_k.HEAVY_FACTOR if exercise.heavy else 1.0
        load_level = player_status_effect_levels(player)[StatusEffect.HEAVY_LOAD]
        cost = (
            carry.fitness_endurance_mult(load_level)
            * exercise_k.ENDURANCE_PER_REP
            * math.log(
                regularity / exercise_k.ENDURANCE_REGULARITY_DIVISOR
                + exercise_k.ENDURANCE_REGULARITY_OFFSET
            )
            / math.log(exercise_k.ENDURANCE_LOG_BASE_ARG)
            * heavy
        )
        player.stats.remove(CharacterStat.ENDURANCE, cost)

        stiffness = (
            exercise_k.STIFFNESS_PER_REP
            * (exercise_k.STIFFNESS_REGULARITY_BASE - regularity)
            / exercise_k.STIFFNESS_REGULARITY_DIVISOR
            * heavy
            * (1 + tired_level(player) // exercise_k.TIRED_STIFFNESS_DIVISOR)
        )
        for region in exercise.regions:
            held = state.future_stiffness.get(region, 0.0)
            state.future_stiffness[region] = min(exercise_k.STIFFNESS_CAP, held + stiffness)
            if state.region_timers.get(region, 0) <= 0:
                state.region_timers[region] = exercise_k.STIFFNESS_TIMER_TICKS

        facts: list[str] = []
        for region in exercise.regions:
            if region in STRENGTH_REGIONS:
                amount = STRENGTH_REGIONS[region] * exercise.xp_mod
                facts.extend(self._skills.add_xp(player, STRENGTH, amount))
            if region in FITNESS_REGIONS:
                amount = FITNESS_REGIONS[region] * exercise.xp_mod
                facts.extend(self._skills.add_xp(player, FITNESS, amount))
        return facts

    def tick(self, player: PlayerEntity, now: int) -> None:
        """One 10-minute boundary: regularity decay, then the region timers and drains."""
        state = player.exercise
        grace = exercise_k.REGULARITY_GRACE_HOURS * MINUTES_PER_HOUR
        for exercise_id, last in state.last_done_minute.items():
            if now - last > grace:
                held = state.regularity.get(exercise_id, 0.0)
                state.regularity[exercise_id] = max(0.0, held - exercise_k.REGULARITY_DECAY)
        for region in exercise_k.REGION_PARTS:
            timer = state.region_timers.get(region)
            if timer is None:
                continue
            if timer > 0:
                state.region_timers[region] = timer - 1
                continue
            self._drain(player, region)

    def _drain(self, player: PlayerEntity, region: str) -> None:
        state = player.exercise
        waiting = state.future_stiffness.get(region, 0.0)
        unit = min(exercise_k.STIFFNESS_DRAIN_PER_TICK, waiting)
        for part in exercise_k.REGION_PARTS[region]:
            player.body[part].stiffness += exercise_k.STIFFNESS_PER_UNIT * unit
        state.future_stiffness[region] = waiting - unit
        if state.future_stiffness[region] <= 0:
            del state.future_stiffness[region]
            del state.region_timers[region]
