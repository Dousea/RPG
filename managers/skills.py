"""Skill XP: gains and losses, levels, the loss timers and the trait swap (spec 08)."""

import math
from collections.abc import Mapping

from data import melee as melee_k
from data import skills as k
from modules.character.skills import SkillState
from modules.entity.player import PlayerEntity
from modules.item import MeleeWeaponItem
from modules.stats import CharacterStat


def skill_levels(player: PlayerEntity) -> dict[str, int]:
    """Each skill's level; Fitness and Strength read 5 when the character has none recorded."""
    levels = {skill_id: state.level for skill_id, state in player.skills.items()}
    levels.setdefault(k.FITNESS, k.DEFAULT_FITNESS_LEVEL)
    levels.setdefault(k.STRENGTH, k.DEFAULT_FITNESS_LEVEL)
    return levels


def fitness_level(skills: Mapping[str, int]) -> int:
    return skills.get(k.FITNESS, k.DEFAULT_FITNESS_LEVEL)


def level_word(level: int) -> str:
    """The word for a level from 1 up; empty at 0."""
    if level < 1:
        return ""
    for highest, word in k.LEVEL_WORDS:
        if level <= highest:
            return word
    return k.LEVEL_WORDS[-1][1]


def skill_progress(skill_id: str, state: SkillState) -> float:
    """How far a skill is from its level to the next, from 0 to 1; 1 at level 10."""
    if state.level >= k.MAX_LEVEL:
        return 1.0
    floor = k.total_xp_for_level(skill_id, state.level)
    ceiling = k.total_xp_for_level(skill_id, state.level + 1)
    return max(0.0, min(1.0, (state.xp - floor) / (ceiling - floor)))


def _boost_multiplier(skill_id: str, boost: int) -> float:
    if skill_id in k.PASSIVE_SKILLS:
        return 1.0
    if skill_id == k.RUNNING:
        if boost <= 0:
            return 1.0
        if boost == 1:
            return k.RUNNING_BOOST_ONE_MULTIPLIER
    return k.BOOST_MULTIPLIER[max(0, min(max(k.BOOST_MULTIPLIER), boost))]


def _trait_multiplier(skill_id: str, traits: list[str]) -> float:
    mult = 1.0
    passive = skill_id in k.PASSIVE_SKILLS
    if k.FAST_LEARNER_ID in traits and not passive:
        mult *= k.FAST_LEARNER_MULT
    if k.SLOW_LEARNER_ID in traits and not passive and skill_id != k.RUNNING:
        mult *= k.SLOW_LEARNER_MULT
    if k.RELUCTANT_FIGHTER_ID in traits and skill_id in k.RELUCTANT_FIGHTER_SKILLS:
        mult *= k.RELUCTANT_FIGHTER_MULT
    if k.CRAFTY_ID in traits and k.SKILLS[skill_id].category == k.CRAFTING:
        mult *= k.CRAFTY_MULT
    return mult


def trait_for_level(skill_id: str, level: int) -> str | None:
    """The Strength or Fitness trait that goes with `level`, or None at the middle level."""
    for highest, trait in k.TRAIT_BY_LEVEL[skill_id]:
        if level <= highest:
            return trait
    return None


class SkillEngine:
    """Awards and removes skill XP and keeps the level-bound traits in step."""

    def add_xp(self, player: PlayerEntity, skill_id: str, amount: float) -> list[str]:
        """Add `amount` XP to a skill after the multipliers; returns the level-change facts."""
        if player.asleep:
            return []
        state = player.skills.setdefault(skill_id, SkillState())
        cap = k.total_xp_for_level(skill_id, k.MAX_LEVEL)
        if amount > 0 and state.xp >= cap:
            return []
        scaled = amount * _boost_multiplier(skill_id, player.skill_boosts.get(skill_id, 0))
        scaled *= _trait_multiplier(skill_id, player.traits) * k.GLOBAL_XP_MULTIPLIER
        state.xp = max(0.0, min(float(cap), state.xp + scaled))
        if amount > 0 and skill_id in k.PASSIVE_SKILLS:
            timer = player.loss_timers.get(skill_id, k.LOSS_TIMER_START)
            player.loss_timers[skill_id] = max(k.LOSS_TIMER_START, timer - k.LOSS_TIMER_GAIN_DROP)
        return self._settle_level(player, skill_id, state)

    def _settle_level(self, player: PlayerEntity, skill_id: str, state: SkillState) -> list[str]:
        name = k.SKILLS[skill_id].name
        before = state.level
        facts: list[str] = []
        while state.level < k.MAX_LEVEL and state.xp >= k.total_xp_for_level(
            skill_id, state.level + 1
        ):
            state.level += 1
            facts.append(k.SKILL_FACT_UP.format(name=name, level=state.level))
        while state.level > 0 and state.xp < k.total_xp_for_level(skill_id, state.level):
            state.level -= 1
            facts.append(k.SKILL_FACT_DOWN.format(name=name, level=state.level))
        if state.level != before and skill_id in k.PASSIVE_SKILLS:
            self.sync_trait(player, skill_id)
        return facts

    def sync_trait(self, player: PlayerEntity, skill_id: str) -> None:
        """Replace the Strength or Fitness trait with the one for the skill's level."""
        family = k.STRENGTH_TRAITS if skill_id == k.STRENGTH else k.FITNESS_TRAITS
        wanted = trait_for_level(skill_id, player.skills[skill_id].level)
        held = [t for t in player.traits if t in family]
        if held == ([wanted] if wanted else []):
            return
        player.traits[:] = [t for t in player.traits if t not in family]
        if wanted is not None:
            player.traits.append(wanted)

    def set_level(self, player: PlayerEntity, skill_id: str, level: int) -> None:
        """Set a skill to a level with exactly that level's total XP, without a fact."""
        player.skills[skill_id] = SkillState(level, float(k.total_xp_for_level(skill_id, level)))
        if skill_id in k.PASSIVE_SKILLS:
            self.sync_trait(player, skill_id)

    def tick(self, player: PlayerEntity, *, walking: bool) -> list[str]:
        """One 10-minute boundary: the loss timers run, and exhaustion trains Fitness."""
        facts: list[str] = []
        for skill_id in k.PASSIVE_SKILLS:
            facts.extend(self._run_loss_timer(player, skill_id))
        endurance = player.stats.get(CharacterStat.ENDURANCE)
        if endurance < k.EXHAUSTION_ENDURANCE_BELOW and not walking:
            facts.extend(self.add_xp(player, k.FITNESS, k.EXHAUSTION_FITNESS_XP_PER_TICK))
        return facts

    def _run_loss_timer(self, player: PlayerEntity, skill_id: str) -> list[str]:
        timer = player.loss_timers.get(skill_id, k.LOSS_TIMER_START) + k.LOSS_TIMER_STEP_PER_TICK
        facts: list[str] = []
        if timer > k.LOSS_TIMER_ACTIVE_ABOVE:
            step = math.floor(timer / k.LOSS_TIMER_DIVISOR)
            if step != player.loss_timer_steps.get(skill_id):
                player.loss_timer_steps[skill_id] = step
                facts = self.add_xp(player, skill_id, -k.LOSS_XP)
        if timer > k.LOSS_TIMER_RESET_ABOVE:
            timer = 0
        player.loss_timers[skill_id] = timer
        return facts

    def hit_xp(
        self, player: PlayerEntity, weapon: MeleeWeaponItem, split: float, hit_count: int
    ) -> list[str]:
        """XP for one melee hit: Fitness, Strength by the swing's hit count, and the categories."""
        facts: list[str] = []
        if player.stats.get(CharacterStat.ENDURANCE) > k.HIT_FITNESS_ENDURANCE_ABOVE:
            facts.extend(self.add_xp(player, k.FITNESS, k.HIT_FITNESS_XP))
        facts.extend(self.add_xp(player, k.STRENGTH, hit_count))
        category_xp = min(melee_k.HIT_XP_CATEGORY_CAP, melee_k.HIT_XP_SPLIT_FACTOR * split)
        for category in weapon.categories:
            facts.extend(self.add_xp(player, melee_k.CATEGORY_SKILL[category], category_xp))
        return facts
