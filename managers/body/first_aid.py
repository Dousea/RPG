"""Treatment: bandages, disinfectant, painkillers and antibiotics (spec 12)."""

import random

from data.body import health as body_k
from data.character import traits as trait_k
from data.items import ALCOHOL_WIPES_ID, ITEMS
from data.zombies import lore as zombie_lore
from managers import carry
from managers.body.health import clear_bandage
from managers.character.skills import SkillEngine, skill_levels
from modules.body.parts import BodyPart
from modules.body.stats import CharacterStat
from modules.entity.item import ItemEntity
from modules.entity.player import PlayerEntity
from modules.item import MedicalItem

_PART_BY_WORD: dict[str, BodyPart] = {
    **{word: BodyPart(value) for value, word in zombie_lore.BODY_PART_WORDS.items()},
    **{part.value.replace("_", " "): part for part in BodyPart},
    **body_k.PART_ALIASES,
}


def part_word(part: BodyPart) -> str:
    return zombie_lore.BODY_PART_WORDS[part.value]


def find_part(name: str) -> BodyPart | None:
    """The part a name refers to, or None."""
    return _PART_BY_WORD.get(" ".join(name.casefold().replace("_", " ").split()))


def most_needed_part(player: PlayerEntity) -> BodyPart | None:
    """The unbandaged part with the highest need: bleeding 100, an open scratch 50, an open bite 50."""
    best: BodyPart | None = None
    best_score = -1
    for part, state in player.body.items():
        if state.bandaged or not state.injured:
            continue
        score = 0
        if state.bleeding_time > 0:
            score += body_k.MOST_NEEDED_BLEEDING
        if state.scratch_time > 0:
            score += body_k.MOST_NEEDED_SCRATCH
        if state.bite_time > 0:
            score += body_k.MOST_NEEDED_BITE
        if score > best_score:
            best, best_score = part, score
    return best


def bandage_items(player: PlayerEntity) -> list[ItemEntity]:
    """Carried bandages, best first: an alcohol bandage, then the most powerful, dirty ones last."""
    found = [
        entity
        for entity in carry.carried_items(player)
        if isinstance(entity.item, MedicalItem) and entity.item.bandage_power > 0
    ]
    return sorted(found, key=_bandage_rank)


def _bandage_rank(entity: ItemEntity) -> tuple[bool, bool, float]:
    item = entity.item
    assert isinstance(item, MedicalItem)
    return (item.dirty, not item.alcoholic, -item.bandage_power)


def disinfectant_items(player: PlayerEntity) -> list[ItemEntity]:
    """Carried alcohol items with uses left, wipes before a bottle."""
    found = [
        entity
        for entity in carry.carried_items(player)
        if isinstance(entity.item, MedicalItem)
        and entity.item.alcohol_power > 0
        and entity.uses > 0
    ]
    return sorted(found, key=lambda entity: entity.item.id != ALCOHOL_WIPES_ID)


class FirstAid:
    """Applies the treatments the validator accepted."""

    def __init__(self, rng: random.Random, skills: SkillEngine) -> None:
        self._rng = rng
        self._skills = skills

    def bandage(self, player: PlayerEntity, part: BodyPart, entity: ItemEntity) -> list[str]:
        item = entity.item
        assert isinstance(item, MedicalItem)
        state = player.body[part]
        level = skill_levels(player).get(body_k.FIRST_AID_SKILL, 0)
        facts: list[str] = []
        if trait_k.FEAR_OF_BLOOD_ID in player.traits and state.bleeding_time > 0:
            player.stats.add(CharacterStat.PANIC, body_k.FEAR_OF_BLOOD_PANIC)
        life = 0.0
        if not item.dirty:
            life = self._rng.uniform(*body_k.BANDAGE_LIFE_RANGE) * (level + 1) + item.bandage_power
        facts.append(
            body_k.BANDAGE_FACT.format(name=player.appearance.forename, part=part_word(part))
        )
        if state.bandage_xp_ready and life > 0:
            facts.extend(self._skills.add_xp(player, body_k.FIRST_AID_SKILL, body_k.BANDAGE_XP))
            state.bandage_xp_ready = False
        state.bandage = item.id
        state.bandage_life = life
        state.bandage_alcoholic = item.alcoholic
        carry.take_out(player, entity)
        return facts

    def remove_bandage(self, player: PlayerEntity, part: BodyPart) -> list[str]:
        state = player.body[part]
        assert state.bandage is not None
        item = ITEMS[state.bandage]
        assert isinstance(item, MedicalItem)
        soaked = state.bandage_life <= 0
        returned: str | None = item.id
        if soaked and not item.reusable_bandage:
            returned = item.dirty_version
        if returned is not None:
            player.inventory.append(ItemEntity(item=ITEMS[returned]))
        clear_bandage(state)
        fact = body_k.REMOVE_DIRTY_BANDAGE_FACT if soaked else body_k.REMOVE_BANDAGE_FACT
        return [fact.format(name=player.appearance.forename, part=part_word(part))]

    def disinfect(self, player: PlayerEntity, part: BodyPart, entity: ItemEntity) -> list[str]:
        state = player.body[part]
        level = skill_levels(player).get(body_k.FIRST_AID_SKILL, 0)
        state.alcohol += body_k.DISINFECT_ALCOHOL
        state.extra_pain += (
            body_k.DISINFECT_EXTRA_PAIN_BASE - level * body_k.DISINFECT_EXTRA_PAIN_PER_FIRST_AID
        )
        self._spend_use(player, entity)
        return [body_k.DISINFECT_FACT.format(name=player.appearance.forename, part=part_word(part))]

    def take_pill(self, player: PlayerEntity, entity: ItemEntity) -> list[str]:
        player.pain_effect_minutes = body_k.PAINKILLER_MINUTES
        self._spend_use(player, entity)
        return [body_k.PAINKILLER_FACT.format(name=player.appearance.forename)]

    def take_antibiotic(self, player: PlayerEntity, entity: ItemEntity) -> list[str]:
        item = entity.item
        assert isinstance(item, MedicalItem)
        player.reduce_infection_power = item.reduce_infection_power
        self._spend_use(player, entity)
        return [body_k.ANTIBIOTIC_FACT.format(name=player.appearance.forename)]

    @staticmethod
    def _spend_use(player: PlayerEntity, entity: ItemEntity) -> None:
        entity.uses -= 1
        if entity.uses <= 0:
            carry.take_out(player, entity)
