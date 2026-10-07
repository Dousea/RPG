"""What the player does to doors, windows and planks: open, close, board up, pry off, break (spec 13)."""

import random

from data import melee as melee_k
from data.character import skills as skill_k
from data.character import traits as trait_k
from data.items import ITEMS
from data.world import barriers as k
from managers import carry
from managers.character.skills import SkillEngine, skill_levels
from managers.combat.melee import MeleeEngine
from managers.combat.weapons import equipped_weapon
from managers.game import GameManager
from managers.world.barriers import BARRIER, door_damage, plank_condition, plank_health, weapon_hit
from managers.zombies import thumping
from managers.zombies.attack import weapon_level
from managers.zombies.noise import Sound, barrier_hit_sound, hammer_sound, pry_sound
from managers.zombies.population import ZombieLoop, shut_behind
from modules.body.stats import CharacterStat
from modules.entity.barrier import BarrierEntity, BarrierKind
from modules.entity.item import ItemEntity
from modules.item import MeleeWeaponItem
from modules.resolution import BarricadeKit, PryTarget
from modules.units import minutes_from_timed_action_frames


def unbarricade_minutes(carpentry: int, *, handy: bool) -> int:
    """Minutes to pry a plank off: 200 frames less 5 per Carpentry level and 20 for Handy."""
    frames = k.UNBARRICADE_TIME_FRAMES_BASE - k.UNBARRICADE_TIME_FRAMES_PER_CARPENTRY * carpentry
    if handy:
        frames -= k.UNBARRICADE_TIME_FRAMES_HANDY_BONUS
    return minutes_from_timed_action_frames(frames)


class BarrierActions:
    """Resolves the barrier verbs; `sounds` are the player's own, heard in the minute they spend."""

    def __init__(
        self,
        manager: GameManager,
        rng: random.Random,
        skills: SkillEngine,
        melee: MeleeEngine,
        loop: ZombieLoop,
    ) -> None:
        self._manager = manager
        self._rng = rng
        self._skills = skills
        self._melee = melee
        self._loop = loop
        self.sounds: list[Sound] = []

    @property
    def _name(self) -> str:
        return self._manager.player.appearance.forename

    def _levels(self) -> dict[str, int]:
        return skill_levels(self._manager.player)

    def reach(self, barrier: BarrierEntity) -> None:
        """The player stands at the barrier from now until their next move."""
        self._manager.player.at_barrier = barrier.barrier_id

    def open(self, barrier: BarrierEntity) -> list[str]:
        """Open it; thumpers behind it are let go. From the inside it also unlocks."""
        self._open(barrier)
        return [k.OPEN_FACT.format(name=self._name, barrier=barrier.name)]

    def _open(self, barrier: BarrierEntity) -> frozenset[str]:
        manager = self._manager
        self.reach(barrier)
        barrier.open = True
        if manager.player.current_location_id == barrier.inside_zone:
            barrier.locked = False
        return thumping.release(manager.world, manager.player, barrier)

    def close(self, barrier: BarrierEntity) -> list[str]:
        self.reach(barrier)
        barrier.open = False
        return [k.CLOSE_FACT.format(name=self._name, barrier=barrier.name)]

    def open_to_cross(self, barrier: BarrierEntity) -> frozenset[str] | None:
        """Open a closed barrier on the way through; returns who that released, None if it was not closed."""
        if barrier.open or barrier.broken:
            return None
        return self._open(barrier)

    def close_behind(
        self, barrier: BarrierEntity, previous_id: str, released: frozenset[str]
    ) -> None:
        """Shut a door the player had to open; chasers left behind, but not those just released, pound on it."""
        manager = self._manager
        barrier.open = False
        shut_behind(manager.world, manager.player, barrier, previous_id, self._rng, released)

    def barricade(self, kit: BarricadeKit) -> list[str]:
        """Nail one plank on the player's side; the hammer may wear, the plank and a nail are spent."""
        manager = self._manager
        player = manager.player
        barrier = kit.barrier
        self.reach(barrier)
        carpentry = self._levels().get(skill_k.CARPENTRY, 0)
        facts = self._wear_hammer(kit.hammer, carpentry)
        plank = kit.plank
        assert isinstance(plank.item, MeleeWeaponItem)
        health = plank_health(plank.condition, plank.item.condition_max, carpentry)
        barrier.barricades[player.current_location_id].append(health)
        self._discard(plank)
        self._spend_nail(kit.nails)
        self.sounds.append(hammer_sound(carpentry))
        facts.insert(0, k.BARRICADE_FACT.format(name=self._name, barrier=barrier.name))
        facts.extend(self._skills.add_xp(player, skill_k.CARPENTRY, k.BARRICADE_XP_CARPENTRY))
        return facts

    def unbarricade(self, target: PryTarget) -> list[str]:
        """Pry the outermost plank off the player's side and keep it."""
        manager = self._manager
        player = manager.player
        barrier = target.barrier
        self.reach(barrier)
        health = barrier.barricades[player.current_location_id].pop()
        plank_item = ITEMS[k.PLANK_ITEM_ID]
        assert isinstance(plank_item, MeleeWeaponItem)
        plank = ItemEntity(item=plank_item)
        plank.condition = plank_condition(health, plank_item.condition_max)
        if not carry.over_the_limit(player, extra=[plank]):
            player.inventory.append(plank)
        else:
            manager.current_location.entities.append(plank)
        self.sounds.append(pry_sound())
        facts = [k.UNBARRICADE_FACT.format(name=self._name, barrier=barrier.name)]
        facts.extend(
            self._skills.add_xp(player, skill_k.CARPENTRY, k.UNBARRICADE_XP_CARPENTRY, chain=False)
        )
        facts.extend(
            self._skills.add_xp(player, skill_k.STRENGTH, k.UNBARRICADE_XP_STRENGTH, chain=False)
        )
        return facts

    def hit(self, barrier: BarrierEntity, now: int) -> list[str]:
        """One swing at the barrier: damage, the break, endurance, weapon wear and noise."""
        manager = self._manager
        player, world = manager.player, manager.world
        self.reach(barrier)
        weapon = equipped_weapon(player)
        melee = weapon if isinstance(weapon, MeleeWeaponItem) else None
        side = player.current_location_id
        levels = self._levels()
        result = weapon_hit(barrier, side, door_damage(melee), levels[skill_k.STRENGTH], self._rng)
        facts = [self._hit_fact(melee, barrier)]
        if result.plank_broke:
            facts.append(k.PLANK_BREAKS_FACT.format(barrier=barrier.name))
        self.sounds.append(barrier_hit_sound())
        if result.gave:
            broke = thumping.gave_way(world, player, self._rng, barrier, side)
            facts.append(thumping.break_fact(barrier))
            for sound in broke.sounds:
                self._loop.add_barrier_sound(sound)
            self._loop.add_sound_stress(broke.stress)
        facts.extend(self._melee.strike_object(player, world, manager.narrative.minutes).facts)
        if (
            result.target is not None
            and result.target.kind == BARRIER
            and barrier.kind == BarrierKind.DOOR
        ):
            self._exert(levels)
        return facts

    def _hit_fact(self, weapon: MeleeWeaponItem | None, barrier: BarrierEntity) -> str:
        if weapon is None:
            looks = self._manager.player.appearance
            return k.HIT_HANDS_FACT.format(
                name=self._name, barrier=barrier.name, possessive=looks.possessive
            )
        return k.HIT_FACT.format(name=self._name, weapon=weapon.name.lower(), barrier=barrier.name)

    def _exert(self, levels: dict[str, int]) -> None:
        player = self._manager.player
        cost = k.DOOR_HIT_ENDURANCE_BY_FITNESS[levels[skill_k.FITNESS]]
        if trait_k.JOGGER_ID in player.traits:
            cost *= k.JOGGER_DOOR_ENDURANCE_MULT
        player.stats.remove(CharacterStat.ENDURANCE, cost)

    def _discard(self, entity: ItemEntity) -> None:
        """Take an item out of the hands or the pack."""
        carry.take_out(self._manager.player, entity)

    def _spend_nail(self, nails: ItemEntity) -> None:
        nails.uses -= 1
        if nails.uses <= 0:
            self._discard(nails)

    def _wear_hammer(self, hammer: ItemEntity, carpentry: int) -> list[str]:
        """The hammer loses 1 condition with chance 1 / (6 x wear number + Carpentry + upkeep)."""
        player = self._manager.player
        item = hammer.item
        assert isinstance(item, MeleeWeaponItem)
        levels = self._levels()
        upkeep = levels.get(melee_k.MAINTENANCE_SKILL, 0) + weapon_level(player) // 2
        odds = int(item.condition_lower_chance * k.HAMMER_WEAR_MULT) + carpentry + upkeep
        if self._rng.randrange(max(odds, 1)) != 0:
            return []
        before = melee_k.condition_word(hammer.condition, item.condition_max)
        hammer.condition -= 1
        after = melee_k.condition_word(hammer.condition, item.condition_max)
        name = item.name.lower()
        if hammer.condition <= 0:
            self._discard(hammer)
            player.inventory.append(hammer)
            return [melee_k.BREAK_FACT.format(weapon=name)]
        if after != before:
            return [melee_k.WEAR_FACTS[after].format(weapon=name)]
        return []
