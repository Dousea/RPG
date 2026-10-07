"""The player's melee swing: crits, the damage chain and what a hit does to a zombie (spec 11)."""

import logging
import random
from collections.abc import Mapping
from dataclasses import dataclass, field
from enum import Enum, auto

from data import melee as k
from data import skills as skill_k
from data import traits as trait_k
from data import zombie_lore as zombie_k
from data.melee import condition_word
from managers.combat import equipped_weapon, held_entity
from managers.noise import Sound
from managers.skills import SkillEngine, skill_levels
from managers.stats.status_effects import (
    crit_penalty,
    damage_after_status_effects,
    player_status_effect_levels,
)
from managers.zombie_attack import weapon_level
from modules.body import BodyLocation
from modules.character.equipment import CharacterHoldableSlot
from modules.entity.item import ItemEntity
from modules.entity.player import PlayerEntity
from modules.entity.zombie import AttackSide, ZombieEntity, ZombieState
from modules.item import ClothingItem, MeleeWeaponItem
from modules.location import World
from modules.stats import CharacterStat, Stats, StatusEffect

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
    level = skills.get(k.CATEGORY_SKILL[k.CRIT_SKILL_ORDER[0]], 0)
    for category in k.CRIT_SKILL_ORDER:
        if category in weapon.categories:
            level = skills.get(k.CATEGORY_SKILL[category], 0)
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
            k.SHOVE_CRIT_BASE
            + k.SHOVE_CRIT_PER_STRENGTH * skills.get(skill_k.STRENGTH, 0)
            - status_effect_penalty
        )
    else:
        raw = (
            weapon.critical_chance * k.SHARPNESS
            + k.CRIT_PER_SKILL_LEVEL * crit_skill_level(weapon, skills)
            - status_effect_penalty
        )
        percent = int(min(max(raw, k.CRIT_CLAMP_MIN), k.CRIT_CLAMP_MAX))
    if behind:
        percent += k.BEHIND_CRIT_BONUS_BARE_UNAWARE if bare_unaware else k.BEHIND_CRIT_BONUS
    return percent


def skill_damage_mod(weapon: MeleeWeaponItem, skills: Mapping[str, int]) -> float:
    level = max(
        (
            skills.get(k.CATEGORY_SKILL[category], 0)
            for category in weapon.categories
            if category in k.WEAPON_LEVEL_CATEGORIES
        ),
        default=0,
    )
    if level >= k.SKILL_DAMAGE_MOD_HIGH_LEVEL:
        return k.SKILL_DAMAGE_MOD_HIGH
    if level >= k.SKILL_DAMAGE_MOD_MID_LEVEL:
        return k.SKILL_DAMAGE_MOD_MID
    return 1.0


def hit_split(damage: float, n: int, stats: Stats) -> float:
    """The damage one target takes after the share by target number and the panic and stress cuts."""
    return damage_after_status_effects(damage / (k.HIT_SPLIT_DIVISOR_PER_N * n), stats)


def hits_taken_factor(hits_taken: int) -> float:
    """The ramp a zombie's own hit count puts on the damage it takes."""
    if hits_taken < k.HITS_TAKEN_RAMP_FROM:
        return 1.0
    return k.HITS_TAKEN_RAMP_FACTOR * (hits_taken - k.HITS_TAKEN_RAMP_OFFSET)


def shoe_power(player: PlayerEntity) -> float:
    shoes = player.worn.get(BodyLocation.SHOES)
    if shoes is None or not isinstance(shoes.item, ClothingItem):
        return k.BAREFOOT_STOMP_POWER
    return shoes.item.stomp_power


@dataclass
class SwingResult:
    """What one swing did: facts for the narrator, sounds for the zombies, kills to remove."""

    facts: list[str] = field(default_factory=list[str])
    sounds: list[Sound] = field(default_factory=list[Sound])
    killed: list[str] = field(default_factory=list[str])


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
        held = equipped_weapon(player)
        held_melee = held if isinstance(held, MeleeWeaponItem) and not shove else None
        weapon = held_melee or k.BARE_HANDS
        kind = self._kind(shove, target.is_down(now), held_melee is not None)
        targets = self._targets(world, player, target, weapon, now)
        levels = skill_levels(player)
        status_effects = player_status_effect_levels(player)
        close_kill = weapon.is_stab and _hunters(world, player) <= k.CLOSE_KILL_MAX_HUNTERS
        crit = self._roll_crit(kind, weapon, target, levels, status_effects, close_kill)
        swing = _Swing(
            player=player,
            world=world,
            now=now,
            kind=kind,
            weapon=weapon,
            weapon_entity=held_entity(player) if held_melee else None,
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
            self._knock(zombie, now, crit=crit)
            if zombie.state not in HUNTING:
                zombie.state = ZombieState.CHASING
            zombie.time_since_seen = 0.0
            zombie.has_chased = True
            zombie.facing_cos = 1.0
        return result

    def strike_object(self, player: PlayerEntity, world: World, now: int) -> SwingResult:
        """What a swing at a door, window or barricade costs the player: endurance and weapon wear."""
        held = equipped_weapon(player)
        held_melee = held if isinstance(held, MeleeWeaponItem) else None
        result = SwingResult()
        swing = _Swing(
            player=player,
            world=world,
            now=now,
            kind=SwingKind.HIT,
            weapon=held_melee or k.BARE_HANDS,
            weapon_entity=held_entity(player) if held_melee else None,
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

    @staticmethod
    def _knock(zombie: ZombieEntity, now: int, *, crit: bool) -> None:
        """A crit or a hit on the floor keeps it down; any other hit staggers it."""
        if crit or zombie.is_down(now):
            zombie.down_until = now + k.DOWN_MINUTES
            zombie.staggered = False
        else:
            zombie.staggered = True

    @staticmethod
    def _kind(shove: bool, down: bool, armed: bool) -> SwingKind:
        if shove or (not down and not armed):
            return SwingKind.SHOVE
        if down:
            return SwingKind.FLOOR_ATTACK if armed else SwingKind.STOMP
        return SwingKind.HIT

    @staticmethod
    def _targets(
        world: World,
        player: PlayerEntity,
        target: ZombieEntity,
        weapon: MeleeWeaponItem,
        now: int,
    ) -> list[ZombieEntity]:
        """The target, then the nearest others in reach and in its posture, up to the hit count."""
        others = sorted(
            (
                z
                for z in world.zombies.values()
                if z is not target
                and z.zone_id == player.current_location_id
                and z.gap <= zombie_k.ATTACK_RANGE_TILES
                and z.is_down(now) == target.is_down(now)
                and not (
                    target.side is not None
                    and z.side is not None
                    and z.side == _OPPOSITE_SIDE[target.side]
                )
            ),
            key=lambda z: (z.gap, int(z.zombie_id[1:])),
        )
        return [target, *others][: weapon.max_hit_count]

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
        behind = target.facing_cos < k.BEHIND_FACING_COS
        if weapon.is_stab:
            if not close_kill:
                return False
            if behind and unaware:
                return True
        chance = crit_chance(
            weapon,
            skills=levels,
            endurance=status_effects[StatusEffect.ENDURANCE],
            heavy_load=k.HEAVY_LOAD_LEVEL,
            panic=status_effects[StatusEffect.PANIC],
            shove=kind in (SwingKind.SHOVE, SwingKind.STOMP),
            behind=behind,
            bare_unaware=weapon is k.BARE_HANDS and unaware,
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
            fact = k.SHOVE_DOWN_FACT if swing.crit else k.SHOVE_FACT
            swing.result.facts.append(fact.format(name=name, target=zombie.zombie_id))
        else:
            dealt, split = self._damage(swing, zombie, index, knife_death=knife_death)
            zombie.health -= dealt * k.GLOBAL_MELEE_DAMAGE_REDUCTION_MULTIPLIER
            killed = zombie.health <= 0 or knife_death
            self._hit_facts(swing, zombie, killed=killed, jaw_stab=knife_death)
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
        damage *= k.STRENGTH_DAMAGE_MOD[levels[skill_k.STRENGTH]]
        if kind != SwingKind.STOMP:
            damage = damage / k.ARMS_PAIN_DIVISOR * k.ARM_SPEED_FACTOR
        split = hit_split(damage, index, swing.player.stats)
        if kind == SwingKind.STOMP:
            split = (
                self._rng.uniform(k.STOMP_ROLL_MIN, k.STOMP_ROLL_MAX)
                + k.STOMP_STRENGTH_BONUS * levels[skill_k.STRENGTH]
            ) * shoe_power(swing.player)
        split *= k.TIRED_FACTOR[status_effects[StatusEffect.ENDURANCE]]
        split *= k.TIRED_FACTOR[status_effects[StatusEffect.TIRED]]
        if kind in (SwingKind.FLOOR_ATTACK, SwingKind.STOMP):
            split *= k.HEAD_HIT_MULTIPLIER
        split *= k.ZOMBIE_ARMOUR_FACTOR
        zombie.hits_taken += 1
        split *= hits_taken_factor(zombie.hits_taken)
        reach = k.REACH_FACTOR_PER_TILE * min(k.REACH_TILES, weapon.max_range) / weapon.max_range
        if knife_death:
            reach *= k.KNIFE_DEATH_REACH_MULTIPLIER
        dealt = split * reach
        if kind in (SwingKind.HIT, SwingKind.FLOOR_ATTACK) and zombie.facing_cos < k.NOT_FACING_COS:
            dealt *= k.NOT_FACING_MULTIPLIER
        dealt *= k.NON_PLAYER_RECEIVED_DAMAGE_MULTIPLIER
        dealt *= k.BASE_WEAPON_DAMAGE_MULTIPLIER + k.WEAPON_LEVEL_DAMAGE_STEP * weapon_level(
            swing.player
        )
        crit_multiplier = weapon.crit_dmg_multiplier * k.SHARPNESS_MULT
        if kind == SwingKind.FLOOR_ATTACK:
            dealt *= max(k.FLOOR_ATTACK_MIN_CRIT_MULTIPLIER, crit_multiplier)
        if swing.crit:
            dealt *= max(k.MIN_CRIT_MULTIPLIER, crit_multiplier)
        return dealt, split

    def _endurance_scale(self, swing: _Swing) -> float:
        """The factors both endurance drains share: weapon skill, Fitness, the weapon and the scale."""
        weapon = swing.weapon
        fatigue = 1.0
        for category in weapon.categories:
            if (
                category in k.WEAPON_LEVEL_CATEGORIES
                and swing.levels.get(k.CATEGORY_SKILL[category], 0) >= k.WEAPON_FATIGUE_LEVEL
            ):
                fatigue = k.WEAPON_FATIGUE_MOD_LEVEL8
        fitness = k.FITNESS_FATIGUE_MOD[swing.levels[skill_k.FITNESS]]
        return fatigue * fitness * weapon.endurance_mod * k.ENDURANCE_LOSS_SCALE

    def _drain_swing(self, swing: _Swing) -> None:
        loss = (
            max(swing.weapon.weight, k.SWING_ENDURANCE_MIN_WEIGHT)
            * k.SWING_ENDURANCE_WEIGHT_FACTOR
            * self._endurance_scale(swing)
        )
        if trait_k.ASTHMATIC_ID in swing.player.traits:
            loss *= k.ASTHMATIC_ENDURANCE_MULTIPLIER
        swing.player.stats.remove(CharacterStat.ENDURANCE, loss)

    def _drain_hit(self, swing: _Swing, dealt: float, health_before: float) -> None:
        weapon = swing.weapon
        if swing.kind == SwingKind.SHOVE:
            hit_mod = 1.0
        elif swing.close_kill:
            hit_mod = k.ENDURANCE_LOSS_CLOSE_KILL_MODIFIER
        else:
            hit_mod = min(1.0, min(dealt, health_before) / weapon.max_damage)
        loss = (
            weapon.weight * k.HIT_ENDURANCE_WEIGHT_FACTOR * self._endurance_scale(swing) * hit_mod
        )
        if swing.kind == SwingKind.STOMP:
            loss *= k.ENDURANCE_LOSS_FLOOR_SHOVE_MULTIPLIER
        swing.player.stats.remove(CharacterStat.ENDURANCE, loss)

    def _award_xp(self, swing: _Swing, split: float, *, killed: bool) -> None:
        player, weapon = swing.player, swing.weapon
        facts = self._skills.hit_xp(player, weapon, split, swing.hit_count)
        if not killed and weapon.knockback_on_no_death:
            facts.extend(self._skills.add_xp(player, skill_k.STRENGTH, k.KNOCKBACK_STRENGTH_XP))
        swing.result.facts.extend(facts)

    def _add_noise(self, swing: _Swing, *, jaw_stab: bool) -> None:
        sounds = swing.result.sounds
        sounds.append(Sound(k.HIT_SOUND_ANY, k.HIT_SOUND_ANY_VOLUME))
        if jaw_stab:
            sounds.append(Sound(k.HIT_SOUND_STAB, k.HIT_SOUND_STAB))
            return
        sounds.append(Sound(k.HIT_SOUND_BASE, k.HIT_SOUND_BASE))
        if swing.kind == SwingKind.STOMP or self._rng.randrange(k.HIT_SOUND_LOUD_ODDS) == 0:
            sounds.append(Sound(k.HIT_SOUND_LOUD, k.HIT_SOUND_LOUD))
        elif self._rng.randrange(k.HIT_SOUND_LOUDER_ODDS) == 0:
            sounds.append(Sound(k.HIT_SOUND_LOUDER, k.HIT_SOUND_LOUDER))

    def _wear(self, swing: _Swing) -> None:
        """Each hit with a weapon may wear it, and trains Maintenance."""
        player, weapon, entity = swing.player, swing.weapon, swing.weapon_entity
        assert entity is not None
        maintenance = swing.levels.get(k.MAINTENANCE_SKILL, 0)
        odds = weapon.condition_lower_chance + maintenance + weapon_level(player) // 2
        if self._rng.randrange(max(odds, 1)) == 0:
            self._lose_condition(swing, entity)
        if not weapon.no_maintenance_xp and self._rng.randrange(100) < k.MAINTENANCE_XP_CHANCE:
            if weapon.condition_lower_chance > k.MAINTENANCE_XP_NUMERATOR_MIN:
                xp = k.MAINTENANCE_XP_NUMERATOR / weapon.condition_lower_chance
            else:
                xp = k.MAINTENANCE_XP_FIXED
            swing.result.facts.extend(self._skills.add_xp(player, k.MAINTENANCE_SKILL, xp))

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
            swing.result.facts.append(k.BREAK_FACT.format(weapon=name))
        elif after != before:
            swing.result.facts.append(k.WEAR_FACTS[after].format(weapon=name))

    @staticmethod
    def _hit_facts(swing: _Swing, zombie: ZombieEntity, *, killed: bool, jaw_stab: bool) -> None:
        name = swing.player.appearance.forename
        label = zombie.zombie_id
        weapon_name = swing.weapon.name.lower()
        facts = swing.result.facts
        if jaw_stab:
            facts.append(k.JAW_STAB_FACT.format(target=label))
        elif swing.kind == SwingKind.STOMP:
            facts.append(k.STOMP_FACT.format(name=name, target=label))
        elif swing.kind == SwingKind.FLOOR_ATTACK:
            facts.append(k.FLOOR_ATTACK_FACT.format(name=name, weapon=weapon_name, target=label))
        elif killed:
            facts.append(k.HIT_KILL_FACT.format(name=name, weapon=weapon_name, target=label))
        elif swing.crit:
            facts.append(k.CRIT_FACT.format(target=label))
        else:
            facts.append(k.HIT_FACT.format(name=name, weapon=weapon_name, target=label))
        if killed:
            facts.append(k.KILL_FACT.format(target=label))

    @staticmethod
    def _kill(swing: _Swing, zombie: ZombieEntity) -> None:
        swing.result.killed.append(zombie.zombie_id)
        swing.player.stats.add(CharacterStat.STRESS, k.KILL_STRESS_DELTA)
        swing.player.zombie_kills += 1

    def _maybe_stick_knife(self, swing: _Swing, zombie: ZombieEntity, was_attacking: bool) -> None:
        """The knife may stay in the jaw; until corpses exist it falls to the zone floor."""
        base = k.STUCK_KNIFE_BASE_ATTACKING if was_attacking else k.STUCK_KNIFE_BASE_OTHER
        short_blade = swing.levels.get(k.SHORT_BLADE_SKILL, 0)
        odds = base + k.STUCK_KNIFE_PER_SHORT_BLADE * (short_blade + 1)
        entity = swing.weapon_entity
        if entity is None or self._rng.randrange(odds) != 0:
            return
        player = swing.player
        for slot in CharacterHoldableSlot:
            if player.equipment[slot] is entity:
                player.equipment[slot] = None
        swing.world.locations[player.current_location_id].entities.append(entity)
        swing.result.facts.append(k.STUCK_KNIFE_FACT.format(target=zombie.zombie_id))


def _hunters(world: World, player: PlayerEntity) -> int:
    """Zombies in the player's zone that are chasing or attacking."""
    return sum(
        1
        for z in world.zombies.values()
        if z.zone_id == player.current_location_id and z.state in HUNTING
    )
