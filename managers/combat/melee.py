"""The player's melee swing: crits, the damage chain and what a hit does to a zombie (melee)."""

import logging
import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum, auto

from data import melee as melee_k
from data.character import skills as skill_k
from data.character import traits as trait_k
from data.melee import condition_word
from data.zombies import lore as zombie_lore
from managers.body.stats.status_effects import (
    crit_penalty,
    damage_after_status_effects,
    player_status_effect_levels,
)
from managers.character.skills import SkillEngine, skill_levels
from managers.combat import weapons
from managers.zombies.attack import weapon_level
from managers.zombies.dress import make_crawler
from managers.zombies.noise import Sound
from modules.body.parts import BodyLocation, BodyPart
from modules.body.stats import CharacterStat, Stats, StatusEffect
from modules.character.equipment import CharacterHoldableSlot
from modules.entity.item import ItemEntity
from modules.entity.player import PlayerEntity
from modules.entity.zombie import AttackSide, ZombieEntity, ZombieState
from modules.item import ClothingItem, MeleeWeaponItem
from modules.world.location import World

logger = logging.getLogger(__name__)

HUNTING = (ZombieState.CHASING, ZombieState.ATTACKING)

_OPPOSITE_SIDE = {
    AttackSide.FRONT: AttackSide.BEHIND,
    AttackSide.BEHIND: AttackSide.FRONT,
    AttackSide.LEFT: AttackSide.RIGHT,
    AttackSide.RIGHT: AttackSide.LEFT,
}


class SwingKind(Enum):
    HIT = auto()
    FLOOR_ATTACK = auto()
    SHOVE = auto()
    STOMP = auto()


def crit_skill_level(weapon: MeleeWeaponItem, skills: Mapping[str, int]) -> int:
    """The level the crit chance reads: the last of the weapon's categories in the fixed check order."""
    level = skills.get(melee_k.CATEGORY_SKILL[melee_k.CRIT_SKILL_ORDER[0]], 0)
    for category in melee_k.CRIT_SKILL_ORDER:
        if category in weapon.categories:
            level = skills.get(melee_k.CATEGORY_SKILL[category], 0)
    return level


def crit_chance(
    weapon: MeleeWeaponItem,
    *,
    skills: Mapping[str, int],
    endurance: int,
    heavy_load: int,
    panic: int,
    shove: bool,
    behind: bool,
    bare_unaware: bool,
) -> int:
    """The percent chance a swing crits, before `no_criticals` stops it."""
    if weapon.no_criticals:
        return 0
    status_effect_penalty = crit_penalty(endurance, heavy_load, panic)
    if shove:
        percent = int(
            melee_k.SHOVE_CRIT_BASE
            + melee_k.SHOVE_CRIT_PER_STRENGTH * skills.get(skill_k.STRENGTH, 0)
            - status_effect_penalty
        )
    else:
        raw = (
            weapon.critical_chance * melee_k.SHARPNESS
            + melee_k.CRIT_PER_SKILL_LEVEL * crit_skill_level(weapon, skills)
            - status_effect_penalty
        )
        percent = int(min(max(raw, melee_k.CRIT_CLAMP_MIN), melee_k.CRIT_CLAMP_MAX))
    if behind:
        percent += (
            melee_k.BEHIND_CRIT_BONUS_BARE_UNAWARE if bare_unaware else melee_k.BEHIND_CRIT_BONUS
        )
    return percent


def skill_damage_mod(weapon: MeleeWeaponItem, skills: Mapping[str, int]) -> float:
    level = max(
        (
            skills.get(melee_k.CATEGORY_SKILL[category], 0)
            for category in weapon.categories
            if category in melee_k.WEAPON_LEVEL_CATEGORIES
        ),
        default=0,
    )
    if level >= melee_k.SKILL_DAMAGE_MOD_HIGH_LEVEL:
        return melee_k.SKILL_DAMAGE_MOD_HIGH
    if level >= melee_k.SKILL_DAMAGE_MOD_MID_LEVEL:
        return melee_k.SKILL_DAMAGE_MOD_MID
    return 1.0


def hit_split(damage: float, n: int, stats: Stats) -> float:
    """The damage one target takes after the share by target number and the panic and stress cuts."""
    return damage_after_status_effects(damage / (melee_k.HIT_SPLIT_DIVISOR_PER_N * n), stats)


def hits_taken_factor(hits_taken: int) -> float:
    """The ramp a zombie's own hit count puts on the damage it takes."""
    if hits_taken < melee_k.HITS_TAKEN_RAMP_FROM:
        return 1.0
    return melee_k.HITS_TAKEN_RAMP_FACTOR * (hits_taken - melee_k.HITS_TAKEN_RAMP_OFFSET)


def hit_part(kind: SwingKind, rng: random.Random) -> BodyPart:
    """The part of a zombie a swing lands on: a floor attack or stomp aims at the head or neck."""
    if kind in (SwingKind.FLOOR_ATTACK, SwingKind.STOMP):
        parts = zombie_lore.FLOOR_HIT_PARTS
    else:
        parts = zombie_lore.STANDING_HIT_PARTS
    return parts[rng.randrange(len(parts))]


def zombie_defence(zombie: ZombieEntity, part: BodyPart) -> float:
    """The percent of a hit on `part` that the zombie's clothes soak up, at most 85."""
    scratch = bite = 0.0
    for entity in zombie.worn.values():
        item = entity.item
        if not isinstance(item, ClothingItem) or part not in item.covers or part in entity.holes:
            continue
        share = item.neck_protection if part == BodyPart.NECK and item.neck_protection < 1 else 1.0
        scratch += item.scratch_defense * share
        bite += item.bite_defense * share
    scratch = min(scratch, zombie_lore.ZOMBIE_PART_DEFENCE_CAP)
    bite = min(bite, zombie_lore.ZOMBIE_PART_DEFENCE_CAP)
    defence = (
        scratch * zombie_lore.ZOMBIE_SCRATCH_WEIGHT + bite
    ) * zombie_lore.ZOMBIE_ARMOUR_FACTOR
    return min(defence, float(zombie_lore.ZOMBIE_MAX_DEFENCE))


def shoe_power(player: PlayerEntity) -> float:
    shoes = player.worn.get(BodyLocation.SHOES)
    if shoes is None or not isinstance(shoes.item, ClothingItem):
        return melee_k.BAREFOOT_STOMP_POWER
    return shoes.item.stomp_power


@dataclass
class SwingResult:
    """What one swing did: facts for the narrator, sounds for the zombies, kills to remove."""

    facts: list[str] = field(default_factory=list[str])
    sounds: list[Sound] = field(default_factory=list[Sound])
    killed: list[str] = field(default_factory=list[str])
    stuck_knives: dict[str, ItemEntity] = field(default_factory=dict[str, ItemEntity])


@dataclass
class _Swing:
    """Everything the hits of one swing share."""

    player: PlayerEntity
    world: World
    now: int
    kind: SwingKind
    weapon: MeleeWeaponItem
    weapon_entity: ItemEntity | None
    levels: Mapping[str, int]
    status_effects: Mapping[StatusEffect, int]
    crit: bool
    close_kill: bool
    hit_count: int
    result: SwingResult


class MeleeEngine:
    """Resolves the player's swings against zombies with an injected RNG."""

    def __init__(self, rng: random.Random, skills: SkillEngine) -> None:
        self._rng = rng
        self._skills = skills

    def swing(
        self,
        player: PlayerEntity,
        world: World,
        now: int,
        target_id: str,
        *,
        shove: bool = False,
    ) -> SwingResult:
        """One swing at `target_id` at clock minute `now`, hitting what the weapon reaches."""
        result = SwingResult()
        target = world.zombies[target_id]
        held = weapons.equipped_weapon(player)
        held_melee = held if isinstance(held, MeleeWeaponItem) and not shove else None
        weapon = held_melee or melee_k.BARE_HANDS
        kind = self._kind(shove, target.on_floor(now), held_melee is not None)
        targets = self.reach(world, player, target, shove=shove, now=now)
        levels = skill_levels(player)
        status_effects = player_status_effect_levels(player)
        close_kill = weapon.is_stab and _hunters(world, player) <= melee_k.CLOSE_KILL_MAX_HUNTERS
        crit = self._roll_crit(kind, weapon, target, levels, status_effects, close_kill)
        swing = _Swing(
            player=player,
            world=world,
            now=now,
            kind=kind,
            weapon=weapon,
            weapon_entity=weapons.held_entity(player) if held_melee else None,
            levels=levels,
            status_effects=status_effects,
            crit=crit,
            close_kill=close_kill,
            hit_count=len(targets),
            result=result,
        )
        was_attacking = target.state == ZombieState.ATTACKING
        self._drain_swing(swing)
        for index, zombie in enumerate(targets, start=1):
            self._hit(swing, zombie, index, was_attacking)
        for zombie in targets:
            if zombie.zombie_id in result.killed:
                continue
            self._knock(zombie, now, crit=crit, result=result)
            if zombie.state not in HUNTING:
                zombie.state = ZombieState.CHASING
            zombie.time_since_seen = 0.0
            zombie.has_chased = True
            zombie.facing_cos = 1.0
        return result

    def strike_object(self, player: PlayerEntity, world: World, now: int) -> SwingResult:
        """What a swing at a door, window or barricade costs the player: endurance and weapon wear."""
        held = weapons.equipped_weapon(player)
        held_melee = held if isinstance(held, MeleeWeaponItem) else None
        result = SwingResult()
        swing = _Swing(
            player=player,
            world=world,
            now=now,
            kind=SwingKind.HIT,
            weapon=held_melee or melee_k.BARE_HANDS,
            weapon_entity=weapons.held_entity(player) if held_melee else None,
            levels=skill_levels(player),
            status_effects=player_status_effect_levels(player),
            crit=False,
            close_kill=False,
            hit_count=1,
            result=result,
        )
        self._drain_swing(swing)
        if swing.weapon_entity is not None:
            self._wear(swing)
        return result

    def _knock(self, zombie: ZombieEntity, now: int, *, crit: bool, result: SwingResult) -> None:
        """A crit or a hit on the floor keeps it down; any other hit staggers it.

        A zombie a hit flagged crawls instead of getting up; a crawler is only ever staggered.
        """
        if zombie.crawling or not (crit or zombie.is_down(now)):
            zombie.staggered = True
        elif zombie.become_crawler:
            self._start_crawling(zombie, result)
        else:
            zombie.down_until = now + melee_k.DOWN_MINUTES
            zombie.staggered = False

    def _start_crawling(self, zombie: ZombieEntity, result: SwingResult) -> None:
        make_crawler(zombie, self._rng)
        zombie.staggered = True
        result.facts.append(zombie_lore.CRAWL_FACT.format(target=zombie.zombie_id))

    @staticmethod
    def _kind(shove: bool, down: bool, armed: bool) -> SwingKind:
        if shove or (not down and not armed):
            return SwingKind.SHOVE
        if down:
            return SwingKind.FLOOR_ATTACK if armed else SwingKind.STOMP
        return SwingKind.HIT

    @staticmethod
    def reach(
        world: World,
        player: PlayerEntity,
        target: ZombieEntity,
        *,
        shove: bool,
        now: int,
    ) -> list[ZombieEntity]:
        """The zombies a swing at `target` hits, rolling nothing: the target, then the nearest others in reach and in its posture, up to the swing's hit count."""
        held = weapons.equipped_weapon(player)
        melee = held if isinstance(held, MeleeWeaponItem) and not shove else None
        kind = MeleeEngine._kind(shove, target.on_floor(now), melee is not None)
        if kind == SwingKind.SHOVE:
            limit = (
                melee_k.SHOVE_HIT_COUNT_UNARMED if held is None else melee_k.SHOVE_HIT_COUNT_ARMED
            )
        elif kind == SwingKind.STOMP:
            limit = melee_k.STOMP_HIT_COUNT
        else:
            assert melee is not None
            limit = melee.max_hit_count
        return MeleeEngine._nearby(world, player, target, now)[:limit]

    @staticmethod
    def _nearby(
        world: World,
        player: PlayerEntity,
        target: ZombieEntity,
        now: int,
    ) -> list[ZombieEntity]:
        """The target, then every other zombie in reach and in its posture, nearest first."""
        others = sorted(
            (
                z
                for z in world.zombies.values()
                if z is not target
                and z.zone_id == player.current_location_id
                and z.gap <= zombie_lore.ATTACK_RANGE_TILES
                and z.on_floor(now) == target.on_floor(now)
                and not (
                    target.side is not None
                    and z.side is not None
                    and z.side == _OPPOSITE_SIDE[target.side]
                )
            ),
            key=lambda z: (z.gap, int(z.zombie_id[1:])),
        )
        return [target, *others]

    def _roll_crit(
        self,
        kind: SwingKind,
        weapon: MeleeWeaponItem,
        target: ZombieEntity,
        levels: Mapping[str, int],
        status_effects: Mapping[StatusEffect, int],
        close_kill: bool,
    ) -> bool:
        """Whether the swing crits: a knife only on a close kill, and then automatically from behind."""
        unaware = target.state in (ZombieState.IDLE, ZombieState.ALERTED)
        behind = target.facing_cos < melee_k.BEHIND_FACING_COS
        if weapon.is_stab:
            if not close_kill:
                return False
            if behind and unaware:
                return True
        chance = crit_chance(
            weapon,
            skills=levels,
            endurance=status_effects[StatusEffect.ENDURANCE],
            heavy_load=status_effects[StatusEffect.HEAVY_LOAD],
            panic=status_effects[StatusEffect.PANIC],
            shove=kind in (SwingKind.SHOVE, SwingKind.STOMP),
            behind=behind,
            bare_unaware=weapon is melee_k.BARE_HANDS and unaware,
        )
        return self._rng.randrange(100) < chance

    def _hit(self, swing: _Swing, zombie: ZombieEntity, index: int, was_attacking: bool) -> None:
        kind = swing.kind
        knife_death = swing.close_kill and swing.crit
        health_before = zombie.health
        dealt = split = 0.0
        killed = False
        if kind == SwingKind.SHOVE:
            name = swing.player.appearance.forename
            fact = melee_k.SHOVE_DOWN_FACT if swing.crit else melee_k.SHOVE_FACT
            swing.result.facts.append(fact.format(name=name, target=zombie.zombie_id))
        else:
            dealt, split = self._damage(swing, zombie, index, knife_death=knife_death)
            zombie.health -= dealt * melee_k.GLOBAL_MELEE_DAMAGE_REDUCTION_MULTIPLIER
            killed = zombie.health <= 0 or knife_death
            self._hit_facts(swing, zombie, killed=killed, jaw_stab=knife_death)
            if not killed:
                self._roll_crawler(swing, zombie)
        self._drain_hit(swing, dealt, health_before)
        self._award_xp(swing, split, killed=killed)
        self._add_noise(swing, jaw_stab=knife_death)
        if swing.weapon_entity is not None and kind != SwingKind.SHOVE:
            self._wear(swing)
        if killed:
            self._kill(swing, zombie)
        if knife_death:
            self._maybe_stick_knife(swing, zombie, was_attacking)

    def _damage(
        self, swing: _Swing, zombie: ZombieEntity, index: int, *, knife_death: bool
    ) -> tuple[float, float]:
        """The damage chain for one zombie: what it takes before the global cut, and its split."""
        kind, weapon, levels, status_effects = (
            swing.kind,
            swing.weapon,
            swing.levels,
            swing.status_effects,
        )
        roll = self._rng.uniform(weapon.min_damage, weapon.max_damage)
        damage = roll * skill_damage_mod(weapon, levels)
        damage *= melee_k.STRENGTH_DAMAGE_MOD[levels[skill_k.STRENGTH]]
        if kind != SwingKind.STOMP:
            damage = damage / melee_k.ARMS_PAIN_DIVISOR * melee_k.ARM_SPEED_FACTOR
        split = hit_split(damage, index, swing.player.stats)
        if kind == SwingKind.STOMP:
            split = (
                self._rng.uniform(melee_k.STOMP_ROLL_MIN, melee_k.STOMP_ROLL_MAX)
                + melee_k.STOMP_STRENGTH_BONUS * levels[skill_k.STRENGTH]
            ) * shoe_power(swing.player)
        split *= melee_k.TIRED_FACTOR[status_effects[StatusEffect.ENDURANCE]]
        split *= melee_k.TIRED_FACTOR[status_effects[StatusEffect.TIRED]]
        part = hit_part(kind, self._rng)
        if kind in (SwingKind.FLOOR_ATTACK, SwingKind.STOMP) and part == BodyPart.HEAD:
            split *= melee_k.HEAD_HIT_MULTIPLIER
        split *= 1 - zombie_defence(zombie, part) / 100
        zombie.hits_taken += 1
        split *= hits_taken_factor(zombie.hits_taken)
        reach = (
            melee_k.REACH_FACTOR_PER_TILE
            * min(melee_k.REACH_TILES, weapon.max_range)
            / weapon.max_range
        )
        if knife_death:
            reach *= melee_k.KNIFE_DEATH_REACH_MULTIPLIER
        dealt = split * reach
        if (
            kind in (SwingKind.HIT, SwingKind.FLOOR_ATTACK)
            and zombie.facing_cos < melee_k.NOT_FACING_COS
        ):
            dealt *= melee_k.NOT_FACING_MULTIPLIER
        dealt *= melee_k.NON_PLAYER_RECEIVED_DAMAGE_MULTIPLIER
        dealt *= (
            melee_k.BASE_WEAPON_DAMAGE_MULTIPLIER
            + melee_k.WEAPON_LEVEL_DAMAGE_STEP * weapon_level(swing.player)
        )
        crit_multiplier = weapon.crit_dmg_multiplier * melee_k.SHARPNESS_MULT
        if kind == SwingKind.FLOOR_ATTACK:
            dealt *= max(melee_k.FLOOR_ATTACK_MIN_CRIT_MULTIPLIER, crit_multiplier)
        if swing.crit:
            dealt *= max(melee_k.MIN_CRIT_MULTIPLIER, crit_multiplier)
        return dealt, split

    def _roll_crawler(self, swing: _Swing, zombie: ZombieEntity) -> None:
        """A weapon hit or stomp that does not kill may flag the zombie to crawl once it is down."""
        if zombie.crawling:
            return
        odds = (
            zombie_lore.CRAWLER_ONE_IN_STOMP
            if swing.kind == SwingKind.STOMP
            else zombie_lore.CRAWLER_ONE_IN_WEAPON
        )
        if self._rng.randrange(odds) == 0:
            zombie.become_crawler = True

    def _endurance_scale(self, swing: _Swing) -> float:
        """The factors both endurance drains share: weapon skill, Fitness, the weapon and the scale."""
        weapon = swing.weapon
        fatigue = 1.0
        for category in weapon.categories:
            if (
                category in melee_k.WEAPON_LEVEL_CATEGORIES
                and swing.levels.get(melee_k.CATEGORY_SKILL[category], 0)
                >= melee_k.WEAPON_FATIGUE_LEVEL
            ):
                fatigue = melee_k.WEAPON_FATIGUE_MOD_LEVEL8
        fitness = melee_k.FITNESS_FATIGUE_MOD[swing.levels[skill_k.FITNESS]]
        return fatigue * fitness * weapon.endurance_mod * melee_k.ENDURANCE_LOSS_SCALE

    def _drain_swing(self, swing: _Swing) -> None:
        loss = (
            max(swing.weapon.weight, melee_k.SWING_ENDURANCE_MIN_WEIGHT)
            * melee_k.SWING_ENDURANCE_WEIGHT_FACTOR
            * self._endurance_scale(swing)
        )
        if trait_k.ASTHMATIC_ID in swing.player.traits:
            loss *= melee_k.ASTHMATIC_ENDURANCE_MULTIPLIER
        swing.player.stats.remove(CharacterStat.ENDURANCE, loss)

    def _drain_hit(self, swing: _Swing, dealt: float, health_before: float) -> None:
        weapon = swing.weapon
        if swing.kind == SwingKind.SHOVE:
            hit_mod = 1.0
        elif swing.close_kill:
            hit_mod = melee_k.ENDURANCE_LOSS_CLOSE_KILL_MODIFIER
        else:
            hit_mod = min(1.0, min(dealt, health_before) / weapon.max_damage)
        loss = (
            weapon.weight
            * melee_k.HIT_ENDURANCE_WEIGHT_FACTOR
            * self._endurance_scale(swing)
            * hit_mod
        )
        if swing.kind == SwingKind.STOMP:
            loss *= melee_k.ENDURANCE_LOSS_FLOOR_SHOVE_MULTIPLIER
        swing.player.stats.remove(CharacterStat.ENDURANCE, loss)

    def _award_xp(self, swing: _Swing, split: float, *, killed: bool) -> None:
        player, weapon = swing.player, swing.weapon
        facts = self._skills.hit_xp(player, weapon, split, swing.hit_count)
        if not killed and weapon.knockback_on_no_death:
            facts.extend(
                self._skills.add_xp(player, skill_k.STRENGTH, melee_k.KNOCKBACK_STRENGTH_XP)
            )
        swing.result.facts.extend(facts)

    def _add_noise(self, swing: _Swing, *, jaw_stab: bool) -> None:
        sounds = swing.result.sounds
        sounds.append(Sound(melee_k.HIT_SOUND_ANY, melee_k.HIT_SOUND_ANY_VOLUME))
        if jaw_stab:
            sounds.append(Sound(melee_k.HIT_SOUND_STAB, melee_k.HIT_SOUND_STAB))
            return
        sounds.append(Sound(melee_k.HIT_SOUND_BASE, melee_k.HIT_SOUND_BASE))
        if swing.kind == SwingKind.STOMP or self._rng.randrange(melee_k.HIT_SOUND_LOUD_ODDS) == 0:
            sounds.append(Sound(melee_k.HIT_SOUND_LOUD, melee_k.HIT_SOUND_LOUD))
        elif self._rng.randrange(melee_k.HIT_SOUND_LOUDER_ODDS) == 0:
            sounds.append(Sound(melee_k.HIT_SOUND_LOUDER, melee_k.HIT_SOUND_LOUDER))

    def _wear(self, swing: _Swing) -> None:
        """Each hit with a weapon may wear it, and trains Maintenance."""
        player, weapon, entity = swing.player, swing.weapon, swing.weapon_entity
        assert entity is not None
        maintenance = swing.levels.get(melee_k.MAINTENANCE_SKILL, 0)
        odds = weapon.condition_lower_chance + maintenance + weapon_level(player) // 2
        if self._rng.randrange(max(odds, 1)) == 0:
            self._lose_condition(swing, entity)
        if (
            not weapon.no_maintenance_xp
            and self._rng.randrange(100) < melee_k.MAINTENANCE_XP_CHANCE
        ):
            if weapon.condition_lower_chance > melee_k.MAINTENANCE_XP_NUMERATOR_MIN:
                xp = melee_k.MAINTENANCE_XP_NUMERATOR / weapon.condition_lower_chance
            else:
                xp = melee_k.MAINTENANCE_XP_FIXED
            swing.result.facts.extend(self._skills.add_xp(player, melee_k.MAINTENANCE_SKILL, xp))

    @staticmethod
    def _lose_condition(swing: _Swing, entity: ItemEntity) -> None:
        weapon, player = swing.weapon, swing.player
        before = condition_word(entity.condition, weapon.condition_max)
        entity.condition -= 1
        after = condition_word(entity.condition, weapon.condition_max)
        name = weapon.name.lower()
        if entity.condition <= 0:
            for slot in CharacterHoldableSlot:
                if player.equipment[slot] is entity:
                    player.equipment[slot] = None
            player.inventory.append(entity)
            swing.weapon_entity = None
            swing.result.facts.append(melee_k.BREAK_FACT.format(weapon=name))
        elif after != before:
            swing.result.facts.append(melee_k.WEAR_FACTS[after].format(weapon=name))

    @staticmethod
    def _hit_facts(swing: _Swing, zombie: ZombieEntity, *, killed: bool, jaw_stab: bool) -> None:
        name = swing.player.appearance.forename
        label = zombie.zombie_id
        weapon_name = swing.weapon.name.lower()
        facts = swing.result.facts
        if jaw_stab:
            facts.append(melee_k.JAW_STAB_FACT.format(target=label))
        elif swing.kind == SwingKind.STOMP:
            facts.append(melee_k.STOMP_FACT.format(name=name, target=label))
        elif swing.kind == SwingKind.FLOOR_ATTACK:
            facts.append(
                melee_k.FLOOR_ATTACK_FACT.format(name=name, weapon=weapon_name, target=label)
            )
        elif killed:
            facts.append(melee_k.HIT_KILL_FACT.format(name=name, weapon=weapon_name, target=label))
        elif swing.crit:
            facts.append(melee_k.CRIT_FACT.format(target=label))
        else:
            facts.append(melee_k.HIT_FACT.format(name=name, weapon=weapon_name, target=label))
        if killed:
            facts.append(melee_k.KILL_FACT.format(target=label))

    @staticmethod
    def _kill(swing: _Swing, zombie: ZombieEntity) -> None:
        swing.result.killed.append(zombie.zombie_id)
        swing.player.stats.add(CharacterStat.STRESS, melee_k.KILL_STRESS_DELTA)
        swing.player.zombie_kills += 1

    def _maybe_stick_knife(self, swing: _Swing, zombie: ZombieEntity, was_attacking: bool) -> None:
        """The knife may stay in the jaw; it goes into the corpse the kill leaves."""
        base = (
            melee_k.STUCK_KNIFE_BASE_ATTACKING if was_attacking else melee_k.STUCK_KNIFE_BASE_OTHER
        )
        short_blade = swing.levels.get(melee_k.SHORT_BLADE_SKILL, 0)
        odds = base + melee_k.STUCK_KNIFE_PER_SHORT_BLADE * (short_blade + 1)
        entity = swing.weapon_entity
        if entity is None or self._rng.randrange(odds) != 0:
            return
        player = swing.player
        for slot in CharacterHoldableSlot:
            if player.equipment[slot] is entity:
                player.equipment[slot] = None
        swing.result.stuck_knives[zombie.zombie_id] = entity
        swing.result.facts.append(melee_k.STUCK_KNIFE_FACT.format(target=zombie.zombie_id))


def _hunters(world: World, player: PlayerEntity) -> int:
    """Zombies in the player's zone that are chasing or attacking."""
    return sum(
        1
        for z in world.zombies.values()
        if z.zone_id == player.current_location_id and z.state in HUNTING
    )
