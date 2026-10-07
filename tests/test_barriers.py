"""Spec 13: barrier rules, damage, vision and the stress thumps cause (pure)."""

import random
import unittest

from data.barriers import WINDOW_HEALTH_DOUBLE, WINDOW_HEALTH_SINGLE, build_starting_barriers
from data.items import ITEMS
from managers.barriers import (
    Target,
    barriers_of,
    blocks,
    can_see_through,
    d_b,
    door_damage,
    hammer_mod,
    plank_condition,
    plank_health,
    sound_stress,
    thump,
    thumpable_for,
    weapon_hit,
)
from managers.game import GameManager
from modules.entity.barrier import BarrierEntity, BarrierKind
from modules.item import MeleeWeaponItem

HOME = "zone_home"
BUILDING = "zone_building"


def door() -> BarrierEntity:
    return build_starting_barriers()["door_apartment"]


def window(max_health: int = WINDOW_HEALTH_SINGLE) -> BarrierEntity:
    return BarrierEntity(
        barrier_id="window_test",
        kind=BarrierKind.WINDOW,
        zones=(BUILDING, "zone_street"),
        inside_zone=BUILDING,
        name="lobby window",
        health=max_health,
        max_health=max_health,
    )


def weapon(item_id: str) -> MeleeWeaponItem:
    item = ITEMS[item_id]
    assert isinstance(item, MeleeWeaponItem)
    return item


class ShippedBarrierTests(unittest.TestCase):
    """Spec 13, The shipped barriers."""

    def test_the_apartment_door_is_a_locked_500_health_door_with_its_key(self):
        barrier = door()
        self.assertEqual(barrier.kind, BarrierKind.DOOR)
        self.assertEqual((barrier.health, barrier.max_health), (500, 500))
        self.assertEqual(barrier.zones, (HOME, BUILDING))
        self.assertEqual(barrier.inside_zone, HOME)
        self.assertTrue(barrier.locked)
        self.assertFalse(barrier.open)
        self.assertEqual(barrier.key_id, "item_apartment_key")

    def test_the_lobby_door_is_a_closed_unlocked_500_health_door(self):
        barrier = build_starting_barriers()["door_lobby"]
        self.assertEqual(barrier.zones, (BUILDING, "zone_street"))
        self.assertEqual(barrier.inside_zone, BUILDING)
        self.assertFalse(barrier.locked)
        self.assertFalse(barrier.open)
        self.assertEqual(barrier.health, 500)

    def test_the_only_shipped_window_is_the_shop_window(self):
        windows = {
            b.barrier_id for b in build_starting_barriers().values() if b.kind == BarrierKind.WINDOW
        }
        self.assertEqual(windows, {"window_bodega"})

    def test_the_building_zones_are_the_apartment_block(self):
        locations = GameManager().world.locations
        self.assertEqual(locations[HOME].building, "apartment_block")
        self.assertEqual(locations[BUILDING].building, "apartment_block")
        self.assertIsNone(locations["zone_street"].building)
        self.assertIsNone(locations["zone_neighborhood"].building)


class BlockingTests(unittest.TestCase):
    """Spec 13, What a barrier stops."""

    def test_a_closed_door_blocks_and_an_open_or_broken_one_does_not(self):
        barrier = door()
        self.assertTrue(blocks(barrier))
        barrier.open = True
        self.assertFalse(blocks(barrier))
        barrier.open = False
        barrier.broken = True
        self.assertFalse(blocks(barrier))

    def test_a_plank_blocks_whatever_the_door_is_doing(self):
        barrier = door()
        barrier.open = True
        barrier.barricades[HOME] = [1000]
        self.assertTrue(blocks(barrier))

    def test_a_smashed_window_does_not_block_unless_planked(self):
        barrier = window()
        barrier.broken = True
        self.assertFalse(blocks(barrier))
        barrier.barricades[BUILDING] = [500]
        self.assertTrue(blocks(barrier))


class VisionTests(unittest.TestCase):
    """Spec 13, What a barrier stops: vision."""

    def test_a_closed_door_blocks_sight_and_an_open_one_does_not(self):
        barrier = door()
        self.assertFalse(can_see_through(barrier))
        barrier.open = True
        self.assertTrue(can_see_through(barrier))

    def test_glass_does_not_block_sight(self):
        self.assertTrue(can_see_through(window()))

    def test_three_planks_block_sight_and_two_do_not(self):
        barrier = window()
        barrier.barricades[BUILDING] = [1000, 1000]
        self.assertTrue(can_see_through(barrier))
        barrier.barricades[BUILDING] = [1000, 1000, 1000]
        self.assertFalse(can_see_through(barrier))


class ThumpableOrderTests(unittest.TestCase):
    """Spec 13, Each thump: the first target that exists."""

    def test_a_door_is_hit_on_the_zombies_side_then_the_far_side_then_itself(self):
        barrier = door()
        self.assertEqual(thumpable_for(barrier, BUILDING), Target("barrier", BUILDING))
        barrier.barricades[HOME] = [1000]
        self.assertEqual(thumpable_for(barrier, BUILDING), Target("barricade", HOME))
        barrier.barricades[BUILDING] = [1000]
        self.assertEqual(thumpable_for(barrier, BUILDING), Target("barricade", BUILDING))
        self.assertEqual(thumpable_for(barrier, HOME), Target("barricade", HOME))

    def test_a_window_is_hit_between_the_zombies_side_and_the_far_side(self):
        barrier = window()
        barrier.barricades["zone_street"] = [500]
        barrier.barricades[BUILDING] = [500]
        self.assertEqual(thumpable_for(barrier, "zone_street"), Target("barricade", "zone_street"))
        barrier.barricades["zone_street"] = []
        self.assertEqual(thumpable_for(barrier, "zone_street"), Target("barrier", "zone_street"))
        barrier.broken = True
        self.assertEqual(thumpable_for(barrier, "zone_street"), Target("barricade", BUILDING))

    def test_an_open_unplanked_door_has_nothing_to_hit(self):
        barrier = door()
        barrier.open = True
        self.assertIsNone(thumpable_for(barrier, BUILDING))


class ThumpDamageTests(unittest.TestCase):
    """Spec 13, Each thump."""

    def test_a_door_takes_nothing_from_one_thumper_and_3_from_two(self):
        barrier = door()
        thump(barrier, BUILDING, thumpers=1)
        self.assertEqual(barrier.health, 500)
        thump(barrier, BUILDING, thumpers=2)
        self.assertEqual(barrier.health, 497)

    def test_a_barricade_takes_3_from_one_thumper_on_the_outermost_plank_only(self):
        barrier = door()
        barrier.barricades[HOME] = [1000, 900]
        thump(barrier, BUILDING, thumpers=1)
        self.assertEqual(barrier.barricades[HOME], [1000, 897])

    def test_damage_past_zero_is_lost_and_the_plank_goes(self):
        barrier = door()
        barrier.barricades[HOME] = [1000, 2]
        result = thump(barrier, BUILDING, thumpers=1)
        self.assertEqual(barrier.barricades[HOME], [1000])
        self.assertTrue(result.plank_broke)
        self.assertFalse(result.gave)

    def test_the_last_plank_leaves_the_door_for_the_next_thump(self):
        barrier = door()
        barrier.barricades[HOME] = [3]
        thump(barrier, BUILDING, thumpers=1)
        self.assertEqual(barrier.barricades[HOME], [])
        self.assertEqual(barrier.health, 500)

    def test_a_door_breaks_at_zero_health(self):
        barrier = door()
        barrier.health = 3
        result = thump(barrier, BUILDING, thumpers=2)
        self.assertTrue(barrier.broken)
        self.assertEqual(barrier.health, 0)
        self.assertTrue(result.gave)
        self.assertFalse(blocks(barrier))

    def test_a_window_takes_3_from_one_thumper_and_smashes(self):
        barrier = window()
        for _ in range(16):
            thump(barrier, "zone_street", thumpers=1)
        self.assertFalse(barrier.broken)
        result = thump(barrier, "zone_street", thumpers=1)
        self.assertTrue(barrier.broken)
        self.assertTrue(result.gave)


class PlankHealthTests(unittest.TestCase):
    """Spec 13, `BARRICADE`: plank health and removal."""

    def test_a_full_plank_is_1000_at_carpentry_0_and_1500_at_10(self):
        self.assertEqual(plank_health(10, 10, 0), 1000)
        self.assertEqual(plank_health(10, 10, 10), 1500)

    def test_a_full_plank_at_carpentry_5_is_1220(self):
        self.assertEqual(plank_health(10, 10, 5), 1220)

    def test_a_half_worn_plank_is_500_at_carpentry_0(self):
        self.assertEqual(plank_health(5, 10, 0), 500)

    def test_the_plank_health_truncates_before_and_after_the_mod(self):
        self.assertEqual(plank_health(7, 10, 2), 770)
        self.assertEqual(plank_health(3, 10, 3), 342)

    def test_removing_a_plank_returns_the_matching_condition(self):
        self.assertEqual(plank_condition(1000, 10), 10)
        self.assertEqual(plank_condition(500, 10), 5)
        self.assertEqual(plank_condition(1500, 10), 10)

    def test_a_plank_never_comes_back_below_condition_1(self):
        self.assertEqual(plank_condition(10, 10), 1)
        self.assertEqual(plank_condition(1, 10), 1)

    def test_the_hammer_is_quieter_with_carpentry(self):
        self.assertEqual(
            [hammer_mod(level) for level in (0, 1, 2, 3, 4, 10)], [1.0, 1.0, 0.8, 0.6, 0.4, 0.4]
        )


class WeaponHitTests(unittest.TestCase):
    """Spec 13, Breaking through."""

    def hit(self, item_id: str, strength: int, barrier: BarrierEntity, seed: int = 1):
        return weapon_hit(
            barrier, HOME, door_damage(weapon(item_id)), strength, random.Random(seed)
        )

    def test_a_crowbar_does_16_to_a_door_at_strength_5_and_40_to_a_plank(self):
        barrier = door()
        rng = random.Random(0)
        while True:
            result = weapon_hit(barrier, HOME, 8, 5, rng)
            if result.damage == 16:
                break
        self.assertEqual(result.damage, 16)
        planked = door()
        planked.barricades[HOME] = [1000]
        result = weapon_hit(planked, HOME, 8, 5, random.Random(1))
        self.assertEqual(result.damage, 40)
        self.assertEqual(planked.barricades[HOME], [960])

    def test_the_extra_6_times_hit_lands_on_a_roll_of_0_in_10_only(self):
        class Fixed(random.Random):
            def __init__(self, roll: int):
                super().__init__(0)
                self.roll = roll

            def randrange(self, *args, **kwargs):
                return self.roll

        lucky = weapon_hit(door(), HOME, 8, 5, Fixed(0))
        plain = weapon_hit(door(), HOME, 8, 5, Fixed(1))
        self.assertEqual(lucky.damage, 16 + 48)
        self.assertEqual(plain.damage, 16)

    def test_a_hammer_does_18_to_a_door_and_45_to_a_plank(self):
        results = {weapon_hit(door(), HOME, 9, 5, random.Random(seed)).damage for seed in range(60)}
        self.assertIn(18, results)
        self.assertLessEqual(results, {18, 18 + 54})
        planked = door()
        planked.barricades[HOME] = [1000]
        self.assertEqual(weapon_hit(planked, HOME, 9, 5, random.Random(1)).damage, 45)

    def test_the_extra_hit_comes_one_time_in_ten_and_adds_six_times_the_damage(self):
        extras = 0
        for seed in range(2000):
            result = weapon_hit(door(), HOME, 8, 5, random.Random(seed))
            if result.damage == 16 + 48:
                extras += 1
            else:
                self.assertEqual(result.damage, 16)
        self.assertTrue(120 < extras < 280)

    def test_strength_scales_the_door_damage_and_5_keeps_1(self):
        expected = {0: 8, 4: 16, 5: 16, 10: 27}
        for level, damage in expected.items():
            with self.subTest(level=level):
                seen = {
                    weapon_hit(door(), HOME, 8, level, random.Random(seed)).damage
                    for seed in range(200)
                }
                self.assertIn(damage, seen)

    def test_strength_5_does_less_door_damage_than_strength_4(self):
        def best(level: int) -> int:
            return min(
                weapon_hit(door(), HOME, 50, level, random.Random(s)).damage for s in range(20)
            )

        self.assertEqual(best(4), 102)
        self.assertEqual(best(5), 100)

    def test_any_hit_smashes_a_window_even_bare_handed(self):
        barrier = window(WINDOW_HEALTH_DOUBLE)
        result = weapon_hit(barrier, "zone_street", 0, 5, random.Random(1))
        self.assertTrue(barrier.broken)
        self.assertTrue(result.gave)

    def test_bare_hands_do_nothing_to_a_door_or_a_plank(self):
        barrier = door()
        self.assertEqual(weapon_hit(barrier, HOME, 0, 5, random.Random(1)).damage, 0)
        self.assertEqual(barrier.health, 500)
        barrier.barricades[HOME] = [1000]
        weapon_hit(barrier, HOME, 0, 5, random.Random(1))
        self.assertEqual(barrier.barricades[HOME], [1000])

    def test_a_hit_goes_to_the_players_side_barricade_first(self):
        barrier = door()
        barrier.barricades[HOME] = [1000]
        barrier.barricades[BUILDING] = [1000]
        weapon_hit(barrier, HOME, 8, 5, random.Random(1))
        self.assertEqual(barrier.barricades[HOME], [960])
        self.assertEqual(barrier.barricades[BUILDING], [1000])

    def test_a_hand_axe_does_40_to_a_door_at_strength_5_and_100_to_a_plank(self):
        axe_damage = door_damage(weapon("item_hand_axe"))
        seen = {
            weapon_hit(door(), HOME, axe_damage, 5, random.Random(seed)).damage
            for seed in range(200)
        }
        self.assertIn(40, seen)
        planked = door()
        planked.barricades[HOME] = [1000]
        result = weapon_hit(planked, HOME, axe_damage, 5, random.Random(1))
        self.assertEqual(result.damage, 100)
        self.assertEqual(planked.barricades[HOME], [900])

    def test_an_open_unplanked_barrier_cannot_be_hit(self):
        barrier = door()
        barrier.open = True
        result = weapon_hit(barrier, HOME, 8, 5, random.Random(1))
        self.assertIsNone(result.target)

    def test_the_door_damage_is_the_weapons_and_bare_hands_have_none(self):
        self.assertEqual(door_damage(weapon("item_crowbar")), 8)
        self.assertEqual(door_damage(weapon("item_hammer")), 9)
        self.assertEqual(door_damage(weapon("item_kitchen_knife")), 1)
        self.assertEqual(door_damage(None), 0)


class StressFromSoundsTests(unittest.TestCase):
    """Spec 13, Stress from sounds."""

    def test_a_thump_at_d_b_4_adds_0_00384(self):
        self.assertAlmostEqual(sound_stress(4, 20, deaf=False), 0.00384, places=6)

    def test_a_break_at_d_b_4_adds_0_00288(self):
        self.assertAlmostEqual(sound_stress(4, 10, deaf=False), 0.00288, places=6)

    def test_a_sound_beyond_its_radius_adds_nothing(self):
        self.assertEqual(sound_stress(20, 20, deaf=False), 0.0)
        self.assertEqual(sound_stress(25, 20, deaf=False), 0.0)

    def test_deaf_gets_none(self):
        self.assertEqual(sound_stress(4, 20, deaf=True), 0.0)


class DistanceTests(unittest.TestCase):
    """Spec 13, The player's distance to a barrier."""

    def setUp(self):
        self.gm = GameManager()

    def test_at_the_barrier_it_is_1_tile(self):
        self.gm.player.at_barrier = "door_apartment"
        barrier = self.gm.world.barriers["door_apartment"]
        self.assertEqual(d_b(self.gm.world, self.gm.player, barrier), 1)

    def test_otherwise_it_is_half_the_zone(self):
        expected = {"zone_home": 4, "zone_building": 10, "zone_street": 20}
        for zone_id, tiles in expected.items():
            with self.subTest(zone=zone_id):
                self.gm.player.current_location_id = zone_id
                barrier = barriers_of(self.gm.world, zone_id)[0]
                self.assertEqual(d_b(self.gm.world, self.gm.player, barrier), tiles)

    def test_being_at_one_barrier_leaves_the_zones_other_barrier_half_a_zone_away(self):
        self.gm.player.current_location_id = "zone_building"
        self.gm.player.at_barrier = "door_apartment"
        world, player = self.gm.world, self.gm.player
        self.assertEqual(d_b(world, player, world.barriers["door_apartment"]), 1)
        self.assertEqual(d_b(world, player, world.barriers["door_lobby"]), 10)


if __name__ == "__main__":
    unittest.main()
