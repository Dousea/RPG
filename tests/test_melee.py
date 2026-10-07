"""Spec 11: the melee swing, its crits and its damage chain."""

import dataclasses
import random
import unittest

from data.items import ITEMS
from data.melee import BARE_HANDS
from managers.game import GameManager
from managers.melee import MeleeEngine, crit_chance, hit_split, hits_taken_factor
from managers.skills import SkillEngine
from modules.body import BodyLocation
from modules.character.equipment import CharacterHoldableSlot
from modules.character.skills import SkillState
from modules.entity.item import ItemEntity
from modules.entity.zombie import AttackSide, ZombieEntity, ZombieState
from modules.item import MeleeWeaponItem
from modules.stats import CharacterStat, Stats


class FixedRng(random.Random):
    """`uniform` returns a fixed share of the range; `randrange` answers from a script.

    `by_size` answers a `randrange` of that size first; with nothing scripted left,
    `randrange(n)` answers n - 1, so no chance fires.
    """

    def __init__(
        self,
        fraction: float = 0.0,
        script: list[int] | None = None,
        by_size: dict[int, int] | None = None,
    ):
        super().__init__(0)
        self.fraction = fraction
        self.script = list(script or [])
        self.by_size = dict(by_size or {})

    def uniform(self, a: float, b: float) -> float:
        return a + self.fraction * (b - a)

    def randrange(self, start: int, stop: int | None = None, step: int = 1) -> int:
        count = start if stop is None else stop
        if count in self.by_size:
            return self.by_size[count]
        return self.script.pop(0) if self.script else count - 1


def melee_item(item_id: str) -> MeleeWeaponItem:
    item = ITEMS[item_id]
    assert isinstance(item, MeleeWeaponItem)
    return item


CROWBAR = melee_item("item_crowbar")


def make_zombie(
    number: int = 1,
    *,
    gap: float = 1.0,
    health: float = 100.0,
    state: ZombieState = ZombieState.CHASING,
    facing_cos: float = 1.0,
    side: AttackSide | None = None,
) -> ZombieEntity:
    return ZombieEntity(
        zombie_id=f"z{number}",
        zone_id="zone_street",
        health=health,
        speed_type=3,
        speed_mod=0.6,
        lunger=False,
        strength=3,
        memory=800,
        sight=2,
        hearing=2,
        state=state,
        gap=gap,
        facing_cos=facing_cos,
        side=side,
    )


def street_game(*, weapon: str | None = None, blunt: int = 0) -> GameManager:
    gm = GameManager()
    gm.player.current_location_id = "zone_street"
    SkillEngine().set_level(gm.player, "long_blunt", blunt)
    if weapon is not None:
        hold(gm, weapon)
    return gm


def hold(gm: GameManager, item_id: str) -> ItemEntity:
    entity = ItemEntity(item=ITEMS[item_id])
    item = entity.item
    assert isinstance(item, MeleeWeaponItem)
    for slot in item.slots:
        assert isinstance(slot, CharacterHoldableSlot)
        gm.player.equipment[slot] = entity
    return entity


def add(gm: GameManager, zombie: ZombieEntity) -> ZombieEntity:
    gm.world.zombies[zombie.zombie_id] = zombie
    return zombie


def swing(gm: GameManager, target: str = "z1", *, rng=None, shove: bool = False, now: int = 0):
    engine = MeleeEngine(rng or FixedRng(), SkillEngine())
    return engine.swing(gm.player, gm.world, now, target, shove=shove)


def skills(**levels: int) -> dict[str, int]:
    return {"long_blunt": 0, "short_blunt": 0, "axe": 0, "long_blade": 0, "spear": 0, **levels}


def chance(weapon: MeleeWeaponItem, **kwargs) -> int:
    params = {
        "skills": skills(),
        "endurance": 0,
        "heavy_load": 0,
        "panic": 0,
        "shove": False,
        "behind": False,
        "bare_unaware": False,
    }
    params.update(kwargs)
    return crit_chance(weapon, **params)


class CritChanceTests(unittest.TestCase):
    """Spec 11, Crits."""

    def test_a_weapon_chance_adds_skill_and_subtracts_status_effects(self):
        # 20 + 3 x 2 - 5 x 1 - 1.3 x 2 = 18.4, truncated
        self.assertEqual(
            chance(CROWBAR, skills=skills(long_blunt=2), endurance=1, panic=2),
            18,
        )

    def test_heavy_load_takes_five_a_level(self):
        self.assertEqual(chance(CROWBAR, heavy_load=2), 10)

    def test_the_chance_clamps_to_ten_and_ninety(self):
        high = dataclasses.replace(CROWBAR, critical_chance=100.0)
        self.assertEqual(chance(high), 90)
        low = dataclasses.replace(CROWBAR, critical_chance=0.0)
        self.assertEqual(chance(low, endurance=4), 10)

    def test_from_behind_adds_five_after_the_clamp(self):
        high = dataclasses.replace(CROWBAR, critical_chance=100.0)
        self.assertEqual(chance(high, behind=True), 95)
        self.assertEqual(chance(CROWBAR, behind=True), 25)

    def test_bare_hands_against_an_unaware_zombie_from_behind_add_thirty(self):
        # shove: 35 + 2 x Strength 5
        self.assertEqual(chance(BARE_HANDS, shove=True, skills=skills(strength=5)), 45)
        self.assertEqual(
            chance(
                BARE_HANDS, shove=True, skills=skills(strength=5), behind=True, bare_unaware=True
            ),
            75,
        )
        self.assertEqual(chance(BARE_HANDS, shove=True, skills=skills(strength=5), behind=True), 50)

    def test_a_shove_chance_has_no_clamp_and_loses_status_effects(self):
        self.assertEqual(
            chance(BARE_HANDS, shove=True, skills=skills(strength=0), endurance=2, panic=1), 23
        )

    def test_the_last_listed_category_names_the_skill(self):
        both = dataclasses.replace(CROWBAR, categories=("blunt", "axe"))
        self.assertEqual(chance(both, skills=skills(long_blunt=9, axe=1)), 23)
        small = dataclasses.replace(CROWBAR, categories=("smallblunt", "blunt"))
        self.assertEqual(chance(small, skills=skills(long_blunt=9, short_blunt=2)), 26)

    def test_no_criticals_zeroes_the_chance(self):
        plain = dataclasses.replace(CROWBAR, no_criticals=True)
        self.assertEqual(chance(plain, behind=True), 0)


def stats(panic_level: int, stress_level: int) -> Stats:
    """Stats whose Panic and Stress status effects sit at the given levels."""
    values = Stats()
    values.set(CharacterStat.PANIC, (0, 7, 31, 66, 81)[panic_level])
    values.set(CharacterStat.STRESS, (0, 0.26, 0.51, 0.76, 0.91)[stress_level])
    return values


class DamageTermTests(unittest.TestCase):
    """Spec 11, Damage."""

    def test_panic_two_and_stress_three_subtract_half_from_the_split(self):
        # 1.0 / (0.5 x 1) = 2.0, less 0.1 x 2 and 0.1 x 3
        self.assertAlmostEqual(hit_split(1.0, 1, stats(2, 3)), 1.5)

    def test_panic_and_stress_below_two_change_nothing(self):
        self.assertAlmostEqual(hit_split(1.0, 1, stats(1, 1)), 2.0)

    def test_a_negative_split_becomes_a_tenth(self):
        self.assertAlmostEqual(hit_split(0.1, 1, stats(2, 3)), 0.1)

    def test_the_split_halves_for_each_extra_target(self):
        self.assertAlmostEqual(hit_split(1.0, 1, stats(0, 0)), 2.0)
        self.assertAlmostEqual(hit_split(1.0, 2, stats(0, 0)), 1.0)
        self.assertAlmostEqual(hit_split(1.0, 3, stats(0, 0)), 2 / 3)

    def test_the_hits_taken_ramp(self):
        self.assertEqual([hits_taken_factor(n) for n in (1, 2, 3)], [1, 1, 1])
        self.assertEqual(hits_taken_factor(4), 3.0)
        self.assertEqual(hits_taken_factor(5), 4.5)


class OneTargetChainTests(unittest.TestCase):
    """Spec 11, Damage: the chain for one target, in the order written."""

    def test_a_crowbar_hit_at_blunt_zero(self):
        # roll 0.6, Strength 5 x1.0, split 1.2, reach 1.6, not-facing none (facing 1),
        # x1.5, x0.3 (weapon level 0): 1.2 x 1.6 x 1.5 x 0.3 = 0.864, x0.15
        gm = street_game(weapon="item_crowbar")
        zombie = add(gm, make_zombie())
        swing(gm)
        self.assertAlmostEqual(zombie.health, 100 - 0.864 * 0.15)
        self.assertEqual(zombie.hits_taken, 1)

    def test_a_zombie_not_facing_the_player_takes_half_as_much_again(self):
        gm = street_game(weapon="item_crowbar")
        zombie = add(gm, make_zombie(facing_cos=0.2))
        swing(gm)
        self.assertAlmostEqual(zombie.health, 100 - 0.864 * 1.5 * 0.15)

    def test_the_weapon_level_adds_a_tenth_a_level(self):
        # Blunt 3: skill_mod 1.1 and weapon level 2 -> x0.5 instead of x0.3
        gm = street_game(weapon="item_crowbar", blunt=3)
        zombie = add(gm, make_zombie())
        swing(gm)
        split = 0.6 * 1.1 / 0.5
        self.assertAlmostEqual(zombie.health, 100 - split * 1.6 * 1.5 * 0.5 * 0.15)

    def test_the_fourth_hit_takes_triple(self):
        gm = street_game(weapon="item_crowbar")
        zombie = add(gm, make_zombie())
        zombie.hits_taken = 3
        swing(gm)
        self.assertAlmostEqual(zombie.health, 100 - 0.864 * 3 * 0.15)
        self.assertEqual(zombie.hits_taken, 4)

    def test_the_fifth_hit_takes_four_and_a_half(self):
        gm = street_game(weapon="item_crowbar")
        zombie = add(gm, make_zombie())
        zombie.hits_taken = 4
        swing(gm)
        self.assertAlmostEqual(zombie.health, 100 - 0.864 * 4.5 * 0.15)

    def test_the_damage_roll_runs_from_min_to_max(self):
        gm = street_game(weapon="item_crowbar")
        zombie = add(gm, make_zombie())
        swing(gm, rng=FixedRng(fraction=1.0, by_size={2: 0}))
        self.assertAlmostEqual(zombie.health, 100 - (1.15 / 0.5) * 1.6 * 1.5 * 0.3 * 0.15)

    def test_a_crit_multiplies_by_the_weapon_multiplier(self):
        gm = street_game(weapon="item_crowbar")
        zombie = add(gm, make_zombie())
        swing(gm, rng=FixedRng(script=[0]))
        self.assertAlmostEqual(zombie.health, 100 - 0.864 * 2.5 * 0.15)

    def test_panic_and_stress_cut_the_split(self):
        gm = street_game(weapon="item_crowbar")
        gm.player.stats.set(CharacterStat.PANIC, 51)
        gm.player.stats.set(CharacterStat.STRESS, 0.6)
        from managers.stats.status_effects import player_status_effect_levels
        from modules.stats import StatusEffect

        levels = player_status_effect_levels(gm.player)
        panic, stress = levels[StatusEffect.PANIC], levels[StatusEffect.STRESS]
        self.assertGreaterEqual(panic, 2)
        self.assertGreaterEqual(stress, 2)
        zombie = add(gm, make_zombie())
        swing(gm)
        split = 1.2 - 0.1 * panic - 0.1 * stress
        self.assertAlmostEqual(zombie.health, 100 - split * 1.6 * 1.5 * 0.3 * 0.15)


class SeveralTargetsTests(unittest.TestCase):
    """Spec 11, A swing: more than one zombie."""

    def test_the_second_target_takes_the_split_of_one(self):
        gm = street_game(weapon="item_crowbar")
        first = add(gm, make_zombie(1, gap=1))
        second = add(gm, make_zombie(2, gap=1))
        swing(gm, "z1")
        self.assertAlmostEqual(first.health, 100 - 0.864 * 0.15)
        self.assertAlmostEqual(second.health, 100 - 0.432 * 0.15)

    def test_a_crowbar_hits_three_and_a_knife_one(self):
        gm = street_game(weapon="item_crowbar")
        zombies = [add(gm, make_zombie(n)) for n in range(1, 5)]
        swing(gm, "z1")
        self.assertEqual([z.hits_taken for z in zombies], [1, 1, 1, 0])
        gm = street_game()
        hold(gm, "item_kitchen_knife")
        zombies = [add(gm, make_zombie(n)) for n in range(1, 4)]
        swing(gm, "z1")
        self.assertEqual([z.hits_taken for z in zombies], [1, 0, 0])

    def test_nearest_first_and_only_within_reach(self):
        gm = street_game(weapon="item_crowbar")
        target = add(gm, make_zombie(1, gap=1))
        far = add(gm, make_zombie(2, gap=3))
        near = add(gm, make_zombie(3, gap=1))
        swing(gm, "z1")
        self.assertEqual((target.hits_taken, near.hits_taken, far.hits_taken), (1, 1, 0))

    def test_a_zombie_on_the_opposite_side_is_not_hit(self):
        gm = street_game(weapon="item_crowbar")
        target = add(gm, make_zombie(1, side=AttackSide.FRONT))
        behind = add(gm, make_zombie(2, side=AttackSide.BEHIND))
        left = add(gm, make_zombie(3, side=AttackSide.LEFT))
        right = add(gm, make_zombie(4, side=AttackSide.RIGHT))
        swing(gm, "z1")
        self.assertEqual(
            [z.hits_taken for z in (target, behind, left, right)],
            [1, 0, 1, 1],
        )
        gm = street_game(weapon="item_crowbar")
        target = add(gm, make_zombie(1, side=AttackSide.LEFT))
        right = add(gm, make_zombie(2, side=AttackSide.RIGHT))
        swing(gm, "z1")
        self.assertEqual(right.hits_taken, 0)

    def test_a_standing_swing_skips_a_zombie_on_the_floor(self):
        gm = street_game(weapon="item_crowbar")
        target = add(gm, make_zombie(1))
        down = add(gm, make_zombie(2))
        down.down_until = 5
        swing(gm, "z1", now=0)
        self.assertEqual((target.hits_taken, down.hits_taken), (1, 0))


class FloorAttackAndStompTests(unittest.TestCase):
    """Spec 11, Floor attacks and stomps."""

    def test_a_floor_attack_hits_the_head_times_three_and_the_floor_multiplier(self):
        # split 1.2 x3 (head), x1.6, x1.5, x0.3, x5 (floor attack): then x0.15
        gm = street_game(weapon="item_crowbar")
        zombie = add(gm, make_zombie())
        zombie.down_until = 5
        swing(gm, rng=FixedRng(by_size={2: 0}), now=0)
        self.assertAlmostEqual(zombie.health, 100 - 1.2 * 3 * 1.6 * 1.5 * 0.3 * 5 * 0.15)
        self.assertTrue(zombie.is_down(1))

    def test_a_floor_attack_landing_on_the_neck_takes_no_head_multiplier(self):
        # the neck is index 1 of the two floor parts: split 1.2, no x3, x1.6, x1.5, x0.3, x5, then x0.15
        gm = street_game(weapon="item_crowbar")
        zombie = add(gm, make_zombie())
        zombie.down_until = 5
        swing(gm, rng=FixedRng(by_size={2: 1}), now=0)
        self.assertAlmostEqual(zombie.health, 100 - 1.2 * 1.6 * 1.5 * 0.3 * 5 * 0.15)

    def test_a_floor_attack_on_a_zombie_not_facing_takes_half_as_much_again(self):
        facing = street_game(weapon="item_crowbar")
        away = street_game(weapon="item_crowbar")
        zombies = []
        for gm, cos in ((facing, 1.0), (away, 0.2)):
            zombie = add(gm, make_zombie(facing_cos=cos))
            zombie.down_until = 5
            swing(gm, now=0)
            zombies.append(zombie)
        self.assertAlmostEqual(100 - zombies[1].health, (100 - zombies[0].health) * 1.5)

    def test_a_stomp_in_trainers(self):
        # (0.7 + 0.2 x 5) x 1.8 = 3.06, x3 head, x reach 2/1.1, then the x1.5 every hit takes; no not-facing bonus
        gm = street_game()
        zombie = add(gm, make_zombie())
        zombie.down_until = 5
        swing(gm, rng=FixedRng(by_size={2: 0}), now=0)
        expected = 3.06 * 3 * (2 / 1.1) * 1.5 * 0.3 * 0.15
        self.assertAlmostEqual(zombie.health, 100 - expected)

    def test_a_barefoot_stomp_halves_the_power(self):
        gm = street_game()
        del gm.player.worn[BodyLocation.SHOES]
        zombie = add(gm, make_zombie())
        zombie.down_until = 5
        swing(gm, rng=FixedRng(by_size={2: 0}), now=0)
        expected = (1.7 * 0.5) * 3 * (2 / 1.1) * 1.5 * 0.3 * 0.15
        self.assertAlmostEqual(zombie.health, 100 - expected)


class ShoveTests(unittest.TestCase):
    """Spec 11, Shoves."""

    def test_a_shove_does_no_damage_and_leaves_hits_taken(self):
        gm = street_game(weapon="item_crowbar")
        zombie = add(gm, make_zombie())
        swing(gm, shove=True)
        self.assertEqual(zombie.health, 100)
        self.assertEqual(zombie.hits_taken, 0)

    def test_bare_hands_on_a_standing_zombie_shove(self):
        gm = street_game()
        zombie = add(gm, make_zombie())
        swing(gm)
        self.assertEqual(zombie.health, 100)
        self.assertEqual(zombie.hits_taken, 0)

    def test_a_shove_with_a_weapon_in_hand_does_not_wear_it(self):
        gm = street_game()
        entity = hold(gm, "item_crowbar")
        add(gm, make_zombie())
        swing(gm, shove=True, rng=FixedRng(script=[99, 0, 0, 0]))
        self.assertEqual(entity.condition, 15)

    def test_a_shove_wakes_an_idle_target(self):
        gm = street_game()
        zombie = add(gm, make_zombie(state=ZombieState.IDLE, facing_cos=-1.0))
        swing(gm, shove=True)
        self.assertEqual(zombie.state, ZombieState.CHASING)
        self.assertEqual(zombie.facing_cos, 1.0)


class KnockdownAndStaggerTests(unittest.TestCase):
    """Spec 11, Knockdowns and staggers."""

    def test_a_crit_knocks_the_zombie_down_for_this_minute_and_the_next(self):
        gm = street_game(weapon="item_crowbar")
        zombie = add(gm, make_zombie())
        swing(gm, rng=FixedRng(script=[0]), now=10)
        self.assertTrue(zombie.is_down(10))
        self.assertTrue(zombie.is_down(11))
        self.assertFalse(zombie.is_down(12))
        self.assertFalse(zombie.staggered)

    def test_a_hit_that_does_not_crit_staggers(self):
        gm = street_game(weapon="item_crowbar")
        zombie = add(gm, make_zombie())
        swing(gm, now=10)
        self.assertTrue(zombie.staggered)
        self.assertFalse(zombie.is_down(10))

    def test_a_hit_while_down_keeps_it_down_until_the_minute_after(self):
        gm = street_game(weapon="item_crowbar")
        zombie = add(gm, make_zombie())
        zombie.down_until = 11
        swing(gm, now=10)
        self.assertTrue(zombie.is_down(11))
        self.assertFalse(zombie.is_down(12))
        self.assertFalse(zombie.staggered)

    def test_a_shove_crit_knocks_down_and_otherwise_staggers(self):
        gm = street_game()
        zombie = add(gm, make_zombie())
        swing(gm, shove=True, rng=FixedRng(script=[0]), now=3)
        self.assertTrue(zombie.is_down(4))
        gm = street_game()
        other = add(gm, make_zombie())
        swing(gm, shove=True, now=3)
        self.assertTrue(other.staggered)
        self.assertFalse(other.is_down(3))

    def test_every_zombie_the_swing_hits_is_staggered(self):
        gm = street_game(weapon="item_crowbar")
        zombies = [add(gm, make_zombie(n)) for n in (1, 2)]
        swing(gm)
        self.assertEqual([z.staggered for z in zombies], [True, True])


class RecordingRng(FixedRng):
    """A `FixedRng` that notes the size of every `randrange` it answers."""

    def __init__(self, script: list[int] | None = None):
        super().__init__(script=script)
        self.sizes: list[int] = []

    def randrange(self, start: int, stop: int | None = None, step: int = 1) -> int:
        self.sizes.append(start if stop is None else stop)
        return super().randrange(start, stop, step)


class KnifeTests(unittest.TestCase):
    """Spec 11, The knife jaw stab."""

    def knife_game(self) -> GameManager:
        gm = street_game()
        hold(gm, "item_kitchen_knife")
        return gm

    def test_a_knife_never_crits_when_two_zombies_are_after_the_player(self):
        gm = self.knife_game()
        first = add(gm, make_zombie(1, health=1000))
        add(gm, make_zombie(2, health=1000))
        swing(gm, "z1", rng=FixedRng(script=[0, 0, 0]))
        self.assertTrue(first.staggered)
        self.assertFalse(first.is_down(0))

    def test_a_close_kill_that_crits_kills_any_zombie(self):
        gm = self.knife_game()
        add(gm, make_zombie(1, health=1000))
        result = swing(gm, "z1", rng=FixedRng(script=[0]))
        self.assertEqual(result.killed, ["z1"])
        self.assertEqual(gm.player.zombie_kills, 1)

    def test_a_close_kill_without_a_crit_is_an_ordinary_hit(self):
        gm = self.knife_game()
        zombie = add(gm, make_zombie(1, health=1000))
        result = swing(gm, "z1")
        self.assertEqual(result.killed, [])
        self.assertLess(zombie.health, 1000)

    def test_a_close_kill_from_behind_on_an_unaware_zombie_crits_without_a_roll(self):
        gm = self.knife_game()
        add(gm, make_zombie(1, health=1000, state=ZombieState.IDLE, facing_cos=-1.0))
        result = swing(gm, "z1")
        self.assertEqual(result.killed, ["z1"])

    def test_a_chasing_zombie_from_behind_still_needs_the_roll(self):
        gm = self.knife_game()
        add(gm, make_zombie(1, health=1000, facing_cos=-1.0))
        result = swing(gm, "z1")
        self.assertEqual(result.killed, [])

    def test_stuck_knife_odds_at_short_blade_zero_against_an_attacker_are_one_in_five(self):
        gm = self.knife_game()
        set_levels(gm, short_blade=0)
        add(gm, make_zombie(1, state=ZombieState.ATTACKING))
        rng = RecordingRng(script=[0])
        swing(gm, "z1", rng=rng)
        self.assertIn(5, rng.sizes)

    def test_stuck_knife_odds_against_any_other_zombie_use_eight(self):
        gm = self.knife_game()
        set_levels(gm, short_blade=2)
        add(gm, make_zombie(1, state=ZombieState.CHASING))
        rng = RecordingRng(script=[0])
        swing(gm, "z1", rng=rng)
        self.assertIn(14, rng.sizes)

    def test_a_stuck_knife_leaves_the_hand_and_goes_with_the_kill(self):
        gm = self.knife_game()
        set_levels(gm, short_blade=0)
        add(gm, make_zombie(1, state=ZombieState.ATTACKING))
        result = swing(gm, "z1", rng=FixedRng(script=[0], by_size={5: 0}))
        self.assertIsNone(gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND])
        self.assertEqual([e.item.id for e in result.stuck_knives.values()], ["item_kitchen_knife"])
        self.assertEqual(list(result.stuck_knives), ["z1"])
        ground = [e.item.id for e in gm.current_location.entities if isinstance(e, ItemEntity)]
        self.assertNotIn("item_kitchen_knife", ground)

    def test_a_knife_that_does_not_stick_stays_in_hand(self):
        gm = self.knife_game()
        add(gm, make_zombie(1, state=ZombieState.ATTACKING))
        swing(gm, "z1", rng=FixedRng(script=[0], by_size={5: 1}))
        self.assertIsNotNone(gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND])

    def test_a_kill_lowers_stress_by_two_hundredths(self):
        gm = self.knife_game()
        gm.player.stats.set(CharacterStat.STRESS, 0.5)
        add(gm, make_zombie(1, health=0.01))
        swing(gm, "z1", rng=FixedRng(script=[0]))
        self.assertAlmostEqual(gm.player.stats.get(CharacterStat.STRESS), 0.48)


def set_levels(gm: GameManager, **levels: int) -> None:
    for skill_id, level in levels.items():
        SkillEngine().set_level(gm.player, skill_id, level)


def endurance_spent(gm: GameManager) -> float:
    return 1.0 - gm.player.stats.get(CharacterStat.ENDURANCE)


class EnduranceTests(unittest.TestCase):
    """Spec 11, Endurance."""

    def test_a_crowbar_swing_that_connects_costs_about_eleven_thousandths(self):
        # swing 2 x 0.18 x 0.012 + hit 2 x 0.28 x 0.012 (the roll at its top, so hit_mod 1), Fitness 0
        gm = street_game(weapon="item_crowbar")
        set_levels(gm, fitness=0)
        add(gm, make_zombie())
        swing(gm, rng=FixedRng(fraction=1.0, by_size={2: 0}))
        self.assertAlmostEqual(endurance_spent(gm), 0.01104)

    def test_fitness_five_scales_both_drains_by_point_eight_five(self):
        gm = street_game(weapon="item_crowbar")
        add(gm, make_zombie())
        swing(gm, rng=FixedRng(fraction=1.0, by_size={2: 0}))
        self.assertAlmostEqual(endurance_spent(gm), 0.01104 * 0.85)

    def test_the_hit_drain_scales_with_the_share_of_the_top_damage_dealt(self):
        # the roll at its bottom: dealt 0.864 / max damage 1.15
        gm = street_game(weapon="item_crowbar")
        set_levels(gm, fitness=0)
        add(gm, make_zombie())
        swing(gm)
        self.assertAlmostEqual(endurance_spent(gm), 0.00432 + 0.00672 * (0.864 / 1.15))

    def test_the_hit_drain_is_capped_by_the_zombie_health_left(self):
        gm = street_game(weapon="item_crowbar")
        set_levels(gm, fitness=0)
        add(gm, make_zombie(health=0.115))
        swing(gm, rng=FixedRng(fraction=1.0, by_size={2: 0}))
        self.assertAlmostEqual(endurance_spent(gm), 0.00432 + 0.00672 * 0.1)

    def test_asthmatic_multiplies_the_swing_drain_by_one_point_two(self):
        gm = street_game(weapon="item_crowbar")
        set_levels(gm, fitness=0)
        gm.player.traits.append("asthmatic")
        add(gm, make_zombie())
        swing(gm, rng=FixedRng(fraction=1.0, by_size={2: 0}))
        self.assertAlmostEqual(endurance_spent(gm), 0.00432 * 1.2 + 0.00672)

    def test_a_shove_costs_the_bare_hands_swing_and_a_full_hit(self):
        gm = street_game(weapon="item_crowbar")
        set_levels(gm, fitness=0)
        add(gm, make_zombie())
        swing(gm, shove=True)
        self.assertAlmostEqual(endurance_spent(gm), 1 * 0.18 * 1.7 * 0.012 + 1 * 0.28 * 1.7 * 0.012)

    def test_a_stomp_costs_double_the_hit_drain(self):
        gm = street_game()
        set_levels(gm, fitness=0)
        zombie = add(gm, make_zombie(health=1000))
        zombie.down_until = 5
        swing(gm)
        # dealt far above the top damage, so hit_mod is 1
        self.assertAlmostEqual(endurance_spent(gm), 0.18 * 1.7 * 0.012 + 2 * 0.28 * 1.7 * 0.012)

    def test_a_close_kill_costs_a_fifth_of_the_hit_drain(self):
        gm = street_game()
        hold(gm, "item_kitchen_knife")
        set_levels(gm, fitness=0)
        add(gm, make_zombie(health=1000))
        swing(gm, rng=FixedRng(script=[0]))
        # knife weight 0.7 counts as 1 on the swing, but 0.7 on the hit
        self.assertAlmostEqual(endurance_spent(gm), 0.18 * 0.012 + 0.7 * 0.28 * 0.012 * 0.2)

    def test_blunt_level_eight_scales_both_drains_by_point_eight(self):
        gm = street_game(weapon="item_crowbar", blunt=8)
        set_levels(gm, fitness=0)
        add(gm, make_zombie())
        swing(gm, rng=FixedRng(fraction=1.0, by_size={2: 0}))
        self.assertAlmostEqual(endurance_spent(gm), 0.01104 * 0.8)


class WearTests(unittest.TestCase):
    """Spec 11, Weapon condition."""

    def test_the_odds_use_wear_chance_maintenance_and_half_the_weapon_level(self):
        # 70 + Maintenance 4 + (Blunt 5 -> weapon level 4) // 2 = 76
        gm = street_game(weapon="item_crowbar", blunt=5)
        set_levels(gm, maintenance=4)
        add(gm, make_zombie())
        rng = RecordingRng()
        swing(gm, rng=rng)
        self.assertIn(76, rng.sizes)

    def test_a_wear_roll_that_fires_costs_one_condition(self):
        gm = street_game()
        entity = hold(gm, "item_crowbar")
        add(gm, make_zombie())
        swing(gm, rng=FixedRng(by_size={70: 0}))
        self.assertEqual(entity.condition, 14)

    def test_a_weapon_that_wears_into_a_new_word_says_so(self):
        gm = street_game()
        entity = hold(gm, "item_crowbar")
        entity.condition = 12
        add(gm, make_zombie())
        result = swing(gm, rng=FixedRng(by_size={70: 0}))
        self.assertIn("The crowbar is getting worn.", result.facts)

    def test_a_weapon_at_zero_leaves_the_hands_broken(self):
        gm = street_game()
        entity = hold(gm, "item_crowbar")
        entity.condition = 1
        add(gm, make_zombie())
        result = swing(gm, rng=FixedRng(by_size={70: 0}))
        self.assertTrue(entity.broken)
        self.assertIsNone(gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND])
        self.assertIsNone(gm.player.equipment[CharacterHoldableSlot.LEFT_HAND])
        self.assertIn(entity, gm.player.inventory)
        self.assertIn("The crowbar snaps.", result.facts)

    def test_a_broken_weapon_does_not_wear_or_snap_again_on_the_next_target(self):
        gm = street_game()
        entity = hold(gm, "item_crowbar")
        entity.condition = 1
        add(gm, make_zombie(1))
        add(gm, make_zombie(2))
        result = swing(gm, rng=FixedRng(by_size={70: 0}))
        self.assertEqual(entity.condition, 0)
        self.assertEqual(gm.player.inventory.count(entity), 1)
        self.assertEqual(result.facts.count("The crowbar snaps."), 1)

    def test_a_weapon_that_breaks_mid_swing_finishes_that_swing(self):
        gm = street_game()
        entity = hold(gm, "item_crowbar")
        entity.condition = 1
        add(gm, make_zombie(1))
        second = add(gm, make_zombie(2))
        swing(gm, rng=FixedRng(by_size={70: 0}))
        self.assertTrue(entity.broken)
        self.assertAlmostEqual(second.health, 100 - 0.432 * 0.15)

    def test_a_knife_that_breaks_on_a_jaw_stab_cannot_also_stick(self):
        gm = street_game()
        entity = hold(gm, "item_kitchen_knife")
        entity.condition = 1
        add(gm, make_zombie(1, state=ZombieState.ATTACKING))
        result = swing(gm, rng=FixedRng(script=[0], by_size={2: 0, 5: 0}))
        self.assertIn("The kitchen knife snaps.", result.facts)
        self.assertIn(entity, gm.player.inventory)
        ground = [e for e in gm.current_location.entities if e is entity]
        self.assertEqual(ground, [])

    def test_bare_hands_never_wear(self):
        gm = street_game()
        zombie = add(gm, make_zombie())
        zombie.down_until = 5
        result = swing(gm, rng=FixedRng(by_size={1: 0}))
        self.assertTrue(result.facts)


class HitXpTests(unittest.TestCase):
    """Spec 11, XP."""

    def xp(self, gm: GameManager, skill_id: str) -> float:
        return gm.player.skills[skill_id].xp

    def test_a_crowbar_hit_trains_fitness_strength_and_blunt(self):
        gm = street_game(weapon="item_crowbar")
        add(gm, make_zombie())
        swing(gm)
        self.assertAlmostEqual(self.xp(gm, "fitness"), 37501)
        # Strength +1 for the hit and +2 for a hit that does not kill with a knockback weapon
        self.assertAlmostEqual(self.xp(gm, "strength"), 37503)
        # min(3, 0.9 x split 1.2) = 1.08, x0.25 (no boost) x1.3 (Fast Learner)
        self.assertAlmostEqual(self.xp(gm, "long_blunt"), 1.08 * 0.25 * 1.3)

    def test_a_hit_that_kills_gives_no_knockback_xp(self):
        gm = street_game(weapon="item_crowbar")
        add(gm, make_zombie(health=0.01))
        swing(gm)
        self.assertAlmostEqual(self.xp(gm, "strength"), 37501)

    def test_a_weapon_without_knockback_gives_only_the_hit_xp(self):
        gm = street_game()
        hold(gm, "item_kitchen_knife")
        add(gm, make_zombie(health=1000))
        swing(gm)
        self.assertAlmostEqual(self.xp(gm, "strength"), 37501)

    def test_a_shove_counts_for_the_knockback_and_trains_no_category(self):
        gm = street_game()
        add(gm, make_zombie())
        swing(gm, shove=True)
        self.assertAlmostEqual(self.xp(gm, "strength"), 37503)
        trained = {
            s for s, st in gm.player.skills.items() if st.xp and s not in ("fitness", "strength")
        }
        self.assertEqual(trained, set())

    def test_the_category_xp_is_capped_at_three(self):
        gm = street_game()
        hold(gm, "item_crowbar")
        zombie = add(gm, make_zombie())
        zombie.down_until = 5
        swing(gm, rng=FixedRng(fraction=1.0, by_size={2: 0}))
        self.assertAlmostEqual(self.xp(gm, "long_blunt"), 3 * 0.25 * 1.3)

    def test_no_fitness_xp_at_or_below_half_endurance(self):
        gm = street_game(weapon="item_crowbar")
        gm.player.stats.set(CharacterStat.ENDURANCE, 0.4)
        add(gm, make_zombie())
        swing(gm)
        self.assertAlmostEqual(self.xp(gm, "fitness"), 37500)

    def test_each_target_trains_strength_by_the_swings_hit_count(self):
        gm = street_game(weapon="item_crowbar")
        add(gm, make_zombie(1))
        add(gm, make_zombie(2))
        swing(gm)
        self.assertAlmostEqual(self.xp(gm, "strength"), 37500 + 2 * (2 + 2))

    def test_maintenance_xp_is_a_coin_flip_for_a_fixed_amount_or_by_wear_odds(self):
        gm = street_game()
        hold(gm, "item_kitchen_knife")
        add(gm, make_zombie(health=1000))
        swing(gm, rng=FixedRng(by_size={100: 0}))
        # +2 for a wear chance of 2 (not above 10), x0.25 x1.3
        self.assertAlmostEqual(self.xp(gm, "maintenance"), 2 * 0.25 * 1.3)
        gm = street_game(weapon="item_crowbar")
        add(gm, make_zombie())
        swing(gm, rng=FixedRng(by_size={100: 0}))
        # 20 / 70 because the wear chance is above 10
        self.assertAlmostEqual(self.xp(gm, "maintenance"), 20 / 70 * 0.25 * 1.3)

    def test_no_maintenance_xp_without_the_coin_flip_or_for_bare_hands(self):
        gm = street_game(weapon="item_crowbar")
        add(gm, make_zombie())
        swing(gm)
        self.assertEqual(self.xp(gm, "maintenance") if "maintenance" in gm.player.skills else 0, 0)


class HitNoiseTests(unittest.TestCase):
    """Spec 11, Noise."""

    def radii(self, result) -> list[tuple[float, float]]:
        return sorted((s.radius, s.volume) for s in result.sounds)

    def test_a_hit_makes_the_base_sounds(self):
        gm = street_game(weapon="item_crowbar")
        add(gm, make_zombie())
        result = swing(gm)
        self.assertEqual(self.radii(result), [(5, 1), (8, 8)])

    def test_one_hit_in_three_is_louder(self):
        gm = street_game(weapon="item_crowbar")
        add(gm, make_zombie())
        result = swing(gm, rng=FixedRng(by_size={3: 0}))
        self.assertEqual(self.radii(result), [(5, 1), (8, 8), (10, 10)])

    def test_otherwise_one_in_seven_is_louder_still(self):
        gm = street_game(weapon="item_crowbar")
        add(gm, make_zombie())
        result = swing(gm, rng=FixedRng(by_size={3: 1, 7: 0}))
        self.assertEqual(self.radii(result), [(5, 1), (8, 8), (16, 16)])

    def test_a_stomp_makes_eight_and_ten(self):
        gm = street_game()
        zombie = add(gm, make_zombie())
        zombie.down_until = 5
        result = swing(gm)
        self.assertEqual(self.radii(result), [(5, 1), (8, 8), (10, 10)])

    def test_a_shove_is_as_loud_as_a_hit(self):
        gm = street_game()
        add(gm, make_zombie())
        result = swing(gm, shove=True)
        self.assertEqual(self.radii(result), [(5, 1), (8, 8)])

    def test_a_jaw_stab_is_quiet(self):
        gm = street_game()
        hold(gm, "item_kitchen_knife")
        add(gm, make_zombie(health=1000))
        result = swing(gm, rng=FixedRng(script=[0]))
        self.assertEqual(self.radii(result), [(4, 4), (5, 1)])


if __name__ == "__main__":
    unittest.main()


class HeavyLoadCritTests(unittest.TestCase):
    """Spec 25, What Heavy Load does: the crit chance reads the live level."""

    def test_two_levels_of_load_take_a_crowbar_crit_from_20_to_10(self):
        light = street_game(weapon="item_crowbar")
        zombie = add(light, make_zombie())
        swing(light, rng=FixedRng(script=[15]), now=10)
        self.assertTrue(zombie.is_down(10))

        heavy = street_game(weapon="item_crowbar")
        heavy.player.skills["strength"] = SkillState(level=0)
        heavy.player.inventory.extend(
            ItemEntity(item=ITEMS[item_id]) for item_id in ("item_barbell", "item_hammer")
        )
        zombie = add(heavy, make_zombie())
        swing(heavy, rng=FixedRng(script=[15]), now=10)
        self.assertFalse(zombie.is_down(10))
        self.assertTrue(zombie.staggered)
