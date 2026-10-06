"""A zombie's attack on the player: defence, drag-down, wounds and clothing (spec 09)."""

import math
import random
from dataclasses import dataclass
from enum import StrEnum

from data import skills as skill_k
from data import traits as trait_k
from data import zombie_lore as k
from managers.combat import equipped_weapon
from managers.skills import skill_levels
from managers.stats.status_effects import defence_penalty, player_status_effect_levels
from modules.body import BodyPart
from modules.entity.player import PlayerEntity
from modules.entity.zombie import AttackSide
from modules.item import ClothingItem, MeleeWeaponItem
from modules.stats import StatusEffect

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
    defended: bool = False
    dragged_down: bool = False
    blocked: bool = False
    wound: Wound | None = None


def weapon_level(player: PlayerEntity) -> int:
    """The held weapon's category skill less one (an axe takes its level whole), 0 to 10."""
    weapon = equipped_weapon(player)
    if not isinstance(weapon, MeleeWeaponItem):
        return 0
    levels = skill_levels(player)
    level = -1
    for category in weapon.skill_categories:
        if category == skill_k.AXE:
            level = levels.get(category, 0)
        else:
            level += levels.get(category, 0)
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
        k.DEFENCE_WEAPON_LEVEL_WEIGHT * weapon_level
        + k.DEFENCE_FITNESS_WEIGHT * fitness
        + k.DEFENCE_STRENGTH_WEIGHT * strength
        - k.DEFENCE_ATTACKER_PENALTY * attackers
        - defence_penalty(endurance, tired, drunk)
        - k.DEFENCE_HEAVY_LOAD_PENALTY * heavy_load
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
        heavy_load=0,
        tired=status_effects[StatusEffect.TIRED],
        drunk=status_effects[StatusEffect.DRUNK],
    )


def wound_odds(level: int, attackers: int, side: AttackSide, traits: list[str]) -> WoundOdds:
    """The thresholds for whether an attack wounds, and how badly."""
    extra = attackers - 1
    base = k.WOUND_BASE + k.MELEE_COMBAT_MOD[level] - k.WOUND_BASE_PER_EXTRA_ATTACKER * extra
    bite = k.WOUND_BITE - k.WOUND_BITE_PER_EXTRA_ATTACKER * extra
    laceration = k.WOUND_LACERATION - k.WOUND_LACERATION_PER_EXTRA_ATTACKER * extra
    if side == AttackSide.BEHIND:
        base -= k.BEHIND_BASE_PENALTY
        bite -= k.BEHIND_BITE_PENALTY
        laceration -= k.BEHIND_LACERATION_PENALTY
        if attackers > k.BEHIND_CROWD_ATTACKERS:
            bite -= k.BEHIND_CROWD_PENALTY
            laceration -= k.BEHIND_CROWD_PENALTY
    elif side in (AttackSide.LEFT, AttackSide.RIGHT):
        base -= k.SIDE_BASE_PENALTY
        bite -= k.SIDE_BITE_PENALTY
        laceration -= k.SIDE_LACERATION_PENALTY
    if trait_k.THICK_SKINNED_ID in traits:
        base = int(base * k.SKIN_FACTOR)
    if trait_k.THIN_SKINNED_ID in traits:
        base = int(base / k.SKIN_FACTOR)
    return WoundOdds(base=base, laceration=laceration, bite=bite)


def roll_body_part(rng: random.Random, side: AttackSide, attackers: int) -> BodyPart:
    """The part a zombie hits; a head or neck hit is often turned into an arm or the torso."""
    wide = rng.randrange(k.BODY_PART_WIDE_ODDS) == 0
    span = k.BODY_PART_ROLL_WIDE if wide else k.BODY_PART_ROLL_NARROW
    part = _BODY_PARTS[rng.randrange(span)]
    if side == AttackSide.BEHIND:
        neck_chance = k.NECK_FROM_BEHIND_PER_ATTACKER * attackers + k.NECK_FROM_BEHIND_BASE
        if rng.randrange(100) < neck_chance:
            part = BodyPart.NECK
    if part in (BodyPart.HEAD, BodyPart.NECK) and rng.randrange(100) > k.HEAD_RETRY_ABOVE[side]:
        part = _BODY_PARTS[rng.randrange(k.BODY_PART_RETRY_RANGE)]
    return part


def roll_wound_damage(rng: random.Random) -> float:
    return (
        rng.randrange(k.DAMAGE_THOUSANDTHS)
        / k.DAMAGE_THOUSANDTHS
        * (rng.randrange(k.DAMAGE_STEPS) + k.DAMAGE_OFFSET)
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
    chance = k.ZOMBIE_INFECTION_CHANCE_PERCENT[kind]
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
    return min(math.floor(total), k.CLOTHING_DEFENCE_CAP)


def apply_wound(player: PlayerEntity, wound: Wound) -> None:
    """Take the wound's damage off overall health, scaled by the part's weight."""
    player.fractional_hp_loss += wound.damage * k.BODY_PART_WEIGHT[wound.part]
    whole = math.floor(player.fractional_hp_loss)
    player.fractional_hp_loss -= whole
    player.hit_points -= whole


def resolve_attack(
    player: PlayerEntity, side: AttackSide, attackers: int, rng: random.Random
) -> AttackOutcome:
    """One zombie attack on the player, in the spec's order; a landed wound is applied."""
    outcome = AttackOutcome()
    if (
        side == AttackSide.FRONT
        and attackers <= k.DEFENCE_MAX_ATTACKERS
        and rng.randrange(100) < player_defence(player, attackers)
    ):
        outcome.defended = True
        return outcome
    if attackers >= k.DRAG_DOWN_ATTACKERS:
        outcome.dragged_down = True
        return outcome
    odds = wound_odds(weapon_level(player), attackers, side, player.traits)
    part = roll_body_part(rng, side, attackers)
    damage = roll_wound_damage(rng)
    kind = roll_wound_kind(rng, odds)
    if kind is None:
        return outcome
    if rng.randrange(100) < clothing_defence(player, part, kind):
        outcome.blocked = True
        return outcome
    for entity in player.layers_for(part):
        entity.holes.add(part)
    wound = Wound(kind, part, damage, roll_zombie_infection(kind, rng))
    apply_wound(player, wound)
    outcome.wound = wound
    return outcome
