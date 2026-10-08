"""A zombie's attack on the player: defence, drag-down, wounds and clothing (zombies)."""

import logging
import math
import random
from dataclasses import dataclass
from enum import StrEnum

from data import melee as melee_k
from data.character import skills as skill_k
from data.character import traits as trait_k
from data.zombies import lore as zombie_lore
from managers.body.health import land_wound
from managers.body.stats.status_effects import defence_penalty, player_status_effect_levels
from managers.character.skills import skill_levels
from managers.combat import weapons
from modules.body.parts import BodyPart
from modules.body.stats import StatusEffect
from modules.entity.player import PlayerEntity
from modules.entity.zombie import AttackSide
from modules.item import ClothingItem, MeleeWeaponItem

logger = logging.getLogger(__name__)

_BODY_PARTS = list(BodyPart)


class WoundKind(StrEnum):
    SCRATCH = "scratch"
    LACERATION = "laceration"
    BITE = "bite"


@dataclass(frozen=True)
class WoundOdds:
    """Percent thresholds: a roll above `base` wounds, above `laceration` and `bite` steps it up."""

    base: int
    laceration: int
    bite: int


@dataclass(frozen=True)
class Wound:
    kind: WoundKind
    part: BodyPart
    damage: float
    zombie_infected: bool


@dataclass
class AttackOutcome:
    idle: bool = False  # a crawler's attack that did nothing (zombie-lifecycle)
    defended: bool = False
    dragged_down: bool = False
    blocked: bool = False
    wound: Wound | None = None


def weapon_level(player: PlayerEntity) -> int:
    """The held weapon's category skill less one (an axe takes its level whole), 0 to 10."""
    weapon = weapons.equipped_weapon(player)
    if not isinstance(weapon, MeleeWeaponItem):
        return 0
    levels = skill_levels(player)
    level = -1
    for category in weapon.categories:
        skill_id = melee_k.CATEGORY_SKILL[category]
        if skill_id == skill_k.AXE:
            level = levels.get(skill_id, 0)
        else:
            level += levels.get(skill_id, 0)
    return min(max(level, 0), skill_k.MAX_LEVEL)


def defence_value(
    weapon_level: int,
    fitness: int,
    strength: int,
    attackers: int,
    *,
    endurance: int,
    heavy_load: int,
    tired: int,
    drunk: int,
) -> int:
    """The percent chance the player shoves a front attacker off."""
    return (
        zombie_lore.DEFENCE_WEAPON_LEVEL_WEIGHT * weapon_level
        + zombie_lore.DEFENCE_FITNESS_WEIGHT * fitness
        + zombie_lore.DEFENCE_STRENGTH_WEIGHT * strength
        - zombie_lore.DEFENCE_ATTACKER_PENALTY * attackers
        - defence_penalty(endurance, tired, drunk)
        - zombie_lore.DEFENCE_HEAVY_LOAD_PENALTY * heavy_load
    )


def player_defence(player: PlayerEntity, attackers: int) -> int:
    levels = skill_levels(player)
    status_effects = player_status_effect_levels(player)
    return defence_value(
        weapon_level(player),
        levels[skill_k.FITNESS],
        levels[skill_k.STRENGTH],
        attackers,
        endurance=status_effects[StatusEffect.ENDURANCE],
        heavy_load=status_effects[StatusEffect.HEAVY_LOAD],
        tired=status_effects[StatusEffect.TIRED],
        drunk=status_effects[StatusEffect.DRUNK],
    )


def wound_odds(level: int, attackers: int, side: AttackSide, traits: list[str]) -> WoundOdds:
    """The thresholds for whether an attack wounds, and how badly."""
    extra = attackers - 1
    base = (
        zombie_lore.WOUND_BASE
        + zombie_lore.MELEE_COMBAT_MOD[level]
        - zombie_lore.WOUND_BASE_PER_EXTRA_ATTACKER * extra
    )
    bite = zombie_lore.WOUND_BITE - zombie_lore.WOUND_BITE_PER_EXTRA_ATTACKER * extra
    laceration = (
        zombie_lore.WOUND_LACERATION - zombie_lore.WOUND_LACERATION_PER_EXTRA_ATTACKER * extra
    )
    if side == AttackSide.BEHIND:
        base -= zombie_lore.BEHIND_BASE_PENALTY
        bite -= zombie_lore.BEHIND_BITE_PENALTY
        laceration -= zombie_lore.BEHIND_LACERATION_PENALTY
        if attackers > zombie_lore.BEHIND_CROWD_ATTACKERS:
            bite -= zombie_lore.BEHIND_CROWD_PENALTY
            laceration -= zombie_lore.BEHIND_CROWD_PENALTY
    elif side in (AttackSide.LEFT, AttackSide.RIGHT):
        base -= zombie_lore.SIDE_BASE_PENALTY
        bite -= zombie_lore.SIDE_BITE_PENALTY
        laceration -= zombie_lore.SIDE_LACERATION_PENALTY
    if trait_k.THICK_SKINNED_ID in traits:
        base = int(base * zombie_lore.SKIN_FACTOR)
    if trait_k.THIN_SKINNED_ID in traits:
        base = int(base / zombie_lore.SKIN_FACTOR)
    return WoundOdds(base=base, laceration=laceration, bite=bite)


def roll_body_part(rng: random.Random, side: AttackSide, attackers: int) -> BodyPart:
    """The part a zombie hits; a head or neck hit is often turned into an arm or the torso."""
    wide = rng.randrange(zombie_lore.BODY_PART_WIDE_ODDS) == 0
    span = zombie_lore.BODY_PART_ROLL_WIDE if wide else zombie_lore.BODY_PART_ROLL_NARROW
    part = _BODY_PARTS[rng.randrange(span)]
    if side == AttackSide.BEHIND:
        neck_chance = (
            zombie_lore.NECK_FROM_BEHIND_PER_ATTACKER * attackers
            + zombie_lore.NECK_FROM_BEHIND_BASE
        )
        if rng.randrange(100) < neck_chance:
            part = BodyPart.NECK
    if (
        part in (BodyPart.HEAD, BodyPart.NECK)
        and rng.randrange(100) > zombie_lore.HEAD_RETRY_ABOVE[side]
    ):
        part = _BODY_PARTS[rng.randrange(zombie_lore.BODY_PART_RETRY_RANGE)]
    return part


_CRAWLER_REACH_PARTS = _BODY_PARTS[_BODY_PARTS.index(BodyPart.GROIN) :]
_CRAWLER_LEG_PARTS = _BODY_PARTS[_BODY_PARTS.index(BodyPart.UPPERLEG_L) :]


def roll_crawler_body_part(rng: random.Random) -> BodyPart:
    """The part a crawler bites: groin to foot one time in ten, else thigh to foot."""
    parts = (
        _CRAWLER_REACH_PARTS
        if rng.randrange(zombie_lore.CRAWLER_GROIN_ONE_IN) == 0
        else _CRAWLER_LEG_PARTS
    )
    return parts[rng.randrange(len(parts))]


def roll_wound_damage(rng: random.Random) -> float:
    return (
        rng.randrange(zombie_lore.DAMAGE_THOUSANDTHS)
        / zombie_lore.DAMAGE_THOUSANDTHS
        * (rng.randrange(zombie_lore.DAMAGE_STEPS) + zombie_lore.DAMAGE_OFFSET)
    )


def roll_wound_kind(rng: random.Random, odds: WoundOdds) -> WoundKind | None:
    """The kind of wound, or None when the blow only thumps."""
    if rng.randrange(100) <= odds.base:
        return None
    kind = WoundKind.SCRATCH
    if rng.randrange(100) > odds.laceration:
        kind = WoundKind.LACERATION
    if rng.randrange(100) > odds.bite:
        kind = WoundKind.BITE
    return kind


def roll_zombie_infection(kind: WoundKind, rng: random.Random) -> bool:
    chance = zombie_lore.ZOMBIE_INFECTION_CHANCE_PERCENT[kind]
    return chance >= 100 or rng.randrange(100) < chance


def clothing_defence(player: PlayerEntity, part: BodyPart, kind: WoundKind) -> int:
    """The percent of hits on `part` the clothing stops; a hole there removes an item's share."""
    total = 0.0
    for entity in player.layers_for(part):
        item = entity.item
        if not isinstance(item, ClothingItem) or part in entity.holes:
            continue
        share = item.bite_defense if kind == WoundKind.BITE else item.scratch_defense
        if part == BodyPart.NECK:
            share *= item.neck_protection
        total += share
    return min(math.floor(total), zombie_lore.CLOTHING_DEFENCE_CAP)


def apply_wound(player: PlayerEntity, wound: Wound, rng: random.Random) -> None:
    """Put the wound into its part, which scales the damage by the part's weight."""
    land_wound(player, wound.kind, wound.part, wound.damage, wound.zombie_infected, rng)


def resolve_attack(
    player: PlayerEntity,
    side: AttackSide,
    attackers: int,
    rng: random.Random,
    *,
    crawler: bool = False,
) -> AttackOutcome:
    """One zombie attack on the player, in the spec's order; a landed wound is applied.

    `attackers` counts the standing zombies on the player (at least 1). A crawler does nothing
    half the time, cannot be defended against, never drags down and bites the legs.
    """
    outcome = AttackOutcome()

    if crawler:
        idle_roll = rng.randrange(zombie_lore.CRAWLER_ATTACK_NOTHING_ONE_IN)
        if idle_roll != 0:
            logger.debug("Crawler attack does nothing (roll %s)", idle_roll)
            outcome.idle = True
            return outcome
    else:
        if side == AttackSide.FRONT and attackers <= zombie_lore.DEFENCE_MAX_ATTACKERS:
            defence_roll = rng.randrange(100)
            defence = player_defence(player, attackers)
            logger.debug(
                "Defence vs %s attackers from %s: chance %s, roll %s",
                attackers,
                side.name,
                defence,
                defence_roll,
            )
            if defence_roll < defence:
                outcome.defended = True
                return outcome
        if attackers >= zombie_lore.DRAG_DOWN_ATTACKERS:
            logger.debug("Dragged down by %s attackers", attackers)
            outcome.dragged_down = True
            return outcome

    odds = wound_odds(weapon_level(player), attackers, side, player.traits)
    part = roll_crawler_body_part(rng) if crawler else roll_body_part(rng, side, attackers)
    damage = roll_wound_damage(rng)
    kind = roll_wound_kind(rng, odds)

    logger.debug(
        "Attack from %s on %s: odds %s, wound %s, damage %.2f",
        side.name,
        part.name,
        odds,
        kind,
        damage,
    )
    if kind is None:
        return outcome

    clothing = clothing_defence(player, part, kind)
    block_roll = rng.randrange(100)
    logger.debug("Clothing on %s stops %s%%, roll %s", part.name, clothing, block_roll)
    if block_roll < clothing:
        outcome.blocked = True
        return outcome

    for entity in player.layers_for(part):
        entity.holes.add(part)
    infected = roll_zombie_infection(kind, rng)
    logger.debug(
        "Wound %s on %s: infection chance %s%%, infected=%s",
        kind,
        part.name,
        zombie_lore.ZOMBIE_INFECTION_CHANCE_PERCENT[kind],
        infected,
    )

    wound = Wound(kind, part, damage, infected)
    apply_wound(player, wound, rng)
    outcome.wound = wound
    return outcome
