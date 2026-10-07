"""Spec 14, Corpses: where they come from, how they rot and when they are removed."""

import random
import unittest

from data.items import ITEMS
from data.zombies.lore import ROT_WORDS, SKELETON_WORD
from managers.character.skills import SkillEngine
from managers.corpses import bodies as corpses
from managers.game import GameManager
from managers.zombies.population import PlayerMinute, ZombieLoop, per_chunk, start_outbreak
from modules.body.parts import BodyLocation, BodyPart
from modules.entity.corpse import CorpseEntity
from modules.entity.item import ItemEntity
from modules.item import ClothingItem
from tests.combat.test_melee import FixedRng, hold
from tests.support import ScriptedRandom
from tests.test_simulation import add_zombie, zombie_game

HOUR = 60


def corpse(**fields) -> CorpseEntity:
    values = {
        "corpse_id": "c1",
        "zone_id": "zone_street",
        "gap": 3.0,
        "female": False,
        "outfit": "generic01",
        "died_at": 0,
        "rot_at_death": 1,
    }
    values.update(fields)
    return CorpseEntity(**values)


class KillCorpseTests(unittest.TestCase):
    """Spec 14, Where corpses come from: a zombie the player kills."""

    def kill(self, rng=None, *, weapon="item_crowbar", health=0.001):
        gm = zombie_game()
        hold(gm, weapon)
        zombie = add_zombie(gm, gap=1, health=health)
        jacket = ItemEntity(item=ITEMS["item_jacket_police"])
        zombie.worn = {BodyLocation.JACKET: jacket}
        zombie.attached = ItemEntity(item=ITEMS["item_hand_axe"], condition=7)
        zombie.female = True
        zombie.outfit = "police"
        loop = ZombieLoop(gm, rng or FixedRng(), SkillEngine())
        loop.run_minute(0, PlayerMinute(swing_target=zombie.zombie_id))
        return gm, zombie, jacket

    def test_a_kill_leaves_a_corpse_with_the_zombies_clothes_and_weapon(self):
        gm, zombie, jacket = self.kill()
        self.assertNotIn(zombie.zombie_id, gm.world.zombies)
        body = gm.world.corpses["c1"]
        self.assertEqual(body.zone_id, "zone_street")
        self.assertEqual(body.gap, 1.0)
        self.assertEqual((body.female, body.outfit), (True, "police"))
        self.assertIs(body.contents[0], jacket)
        self.assertEqual(
            [e.item.id for e in body.contents], ["item_jacket_police", "item_hand_axe"]
        )
        self.assertEqual(body.contents[1].condition, 7)
        self.assertIs(body.attached, body.contents[1])
        self.assertFalse(body.skeleton or body.fake_dead or body.crawling)
        self.assertEqual(body.died_at, 0)
        self.assertEqual(gm.world.next_corpse_number, 2)

    def test_corpses_are_numbered_in_order_of_creation(self):
        gm = zombie_game()
        hold(gm, "item_crowbar")
        for _ in range(2):
            add_zombie(gm, gap=1, health=0.001)
        loop = ZombieLoop(gm, FixedRng(), SkillEngine())
        loop.run_minute(0, PlayerMinute(swing_target="z1"))
        loop.run_minute(1, PlayerMinute(swing_target="z2"))
        self.assertEqual(list(gm.world.corpses), ["c1", "c2"])

    def test_a_knife_that_stays_in_the_jaw_goes_into_the_corpse(self):
        rng = FixedRng(script=[0], by_size={10: 0})
        gm = zombie_game()
        hold(gm, "item_kitchen_knife")
        add_zombie(gm, gap=1, health=1000)
        ZombieLoop(gm, rng, SkillEngine()).run_minute(0, PlayerMinute(swing_target="z1"))
        body = gm.world.corpses["c1"]
        self.assertIn("item_kitchen_knife", [e.item.id for e in body.contents])
        ground = [e.item.id for e in gm.current_location.entities if isinstance(e, ItemEntity)]
        self.assertNotIn("item_kitchen_knife", ground)

    def test_a_close_kill_always_leaves_a_corpse(self):
        gm = zombie_game()
        hold(gm, "item_kitchen_knife")
        add_zombie(gm, gap=1, health=1000)
        ZombieLoop(gm, FixedRng(script=[0]), SkillEngine()).run_minute(
            0, PlayerMinute(swing_target="z1")
        )
        self.assertEqual(list(gm.world.corpses), ["c1"])


class RotAtDeathTests(unittest.TestCase):
    """Spec 14, Where corpses come from: the rot stage a kill is rolled with."""

    def stage(self, days: float, roll: int) -> int:
        return corpses.rot_stage_at_death(days, ScriptedRandom(randrange=[roll]))

    def test_the_first_twenty_days_are_always_stage_one(self):
        for days in (0, 10.9, 20):
            self.assertEqual(self.stage(days, 99), 1)

    def test_day_55_is_halfway_between_the_chances(self):
        # stage 1 chance 60, stage 2 chance 20
        self.assertEqual([self.stage(55, r) for r in (0, 59, 60, 79, 80, 99)], [1, 1, 2, 2, 3, 3])

    def test_from_day_90_the_chances_stop_moving(self):
        # stage 1 chance 20, stage 2 chance 30
        self.assertEqual([self.stage(100, r) for r in (0, 19, 20, 49, 50)], [1, 1, 2, 2, 3])

    def test_from_day_180_stage_one_is_gone(self):
        self.assertEqual([self.stage(180, r) for r in (0, 9, 10, 99)], [2, 2, 3, 3])

    def test_a_killed_corpse_takes_the_roll_on_days_since_the_outbreak(self):
        gm = zombie_game()
        zombie = add_zombie(gm, gap=1)
        gm.world.outbreak_started_at = 0
        body = corpses.kill_corpse(
            gm.world, zombie, 200 * 24 * HOUR, ScriptedRandom(randrange=[99])
        )
        self.assertEqual(body.rot_at_death, 3)
        self.assertEqual(body.died_at, 200 * 24 * HOUR)
        early = corpses.kill_corpse(gm.world, zombie, 24 * HOUR, ScriptedRandom(randrange=[99]))
        self.assertEqual(early.rot_at_death, 1)


class OutbreakCorpseTests(unittest.TestCase):
    """Spec 14, Where corpses come from: the bodies lying around when the outbreak starts."""

    def test_the_chunk_chance_is_two_thirds_of_a_tenth_of_the_per_chunk_count(self):
        self.assertAlmostEqual(corpses.chunk_chance(0.8091), 2 / 3 * 0.1 * 0.8091)
        self.assertAlmostEqual(corpses.chunk_chance(per_chunk(96)), 0.1538, places=3)

    def test_expected_corpses_per_zone_and_none_in_the_spawn_building(self):
        totals: dict[str, int] = {}
        runs = 300
        for seed in range(runs):
            gm = GameManager()
            corpses.scatter(gm.world, 0, random.Random(seed), per_chunk)
            for body in gm.world.corpses.values():
                totals[body.zone_id] = totals.get(body.zone_id, 0) + 1
        self.assertNotIn("zone_home", totals)
        self.assertAlmostEqual(totals["zone_building"] / runs, 0.16, delta=0.08)
        self.assertAlmostEqual(totals["zone_street"] / runs, 0.92, delta=0.2)
        self.assertAlmostEqual(totals["zone_neighborhood"] / runs, 1.66, delta=0.3)

    def test_a_zone_holds_at_most_one_corpse_per_chunk(self):
        gm = GameManager()
        zone = gm.world.locations["zone_neighborhood"]
        zone.zombie_intensity = 255
        corpses.scatter(gm.world, 0, random.Random(1), lambda intensity: 100.0)
        per_zone = [b.zone_id for b in gm.world.corpses.values()]
        self.assertEqual(per_zone.count("zone_neighborhood"), zone.chunks)

    def test_starting_the_outbreak_scatters_corpses_and_numbers_them(self):
        found = 0
        for seed in range(40):
            gm = GameManager()
            start_outbreak(gm.world, 0, "zone_home", random.Random(seed))
            ids = list(gm.world.corpses)
            self.assertEqual(ids, [f"c{i}" for i in range(1, len(ids) + 1)])
            self.assertEqual(gm.world.next_corpse_number, len(ids) + 1)
            found += len(ids)
        self.assertGreater(found, 40)

    def test_each_body_is_a_skeleton_one_time_in_fourteen(self):
        gm = GameManager()
        zone = gm.world.locations["zone_street"]
        rng = random.Random(12)
        bodies = [corpses.outbreak_corpse(gm.world, zone, 4400, rng) for _ in range(6000)]
        skeletons = [b for b in bodies if b.skeleton]
        self.assertAlmostEqual(len(skeletons) / 6000, 1 / 14, delta=0.012)
        self.assertTrue(all(not b.contents and not b.fake_dead for b in skeletons))
        self.assertTrue(all(b.died_at == 4400 for b in bodies))

    def test_one_in_fifteen_of_the_rest_is_fake_dead_and_one_in_five_of_those_crawls(self):
        gm = GameManager()
        zone = gm.world.locations["zone_street"]
        rng = random.Random(13)
        bodies = [corpses.outbreak_corpse(gm.world, zone, 0, rng) for _ in range(9000)]
        dressed = [b for b in bodies if not b.skeleton]
        fake = [b for b in dressed if b.fake_dead]
        self.assertAlmostEqual(len(fake) / len(dressed), 1 / 15, delta=0.012)
        self.assertAlmostEqual(sum(b.crawling for b in fake) / len(fake), 0.2, delta=0.08)
        self.assertFalse(any(b.crawling for b in dressed if not b.fake_dead))

    def test_a_dressed_body_has_an_outfit_a_fresh_rot_and_a_gap_inside_the_zone(self):
        gm = GameManager()
        zone = gm.world.locations["zone_street"]
        rng = random.Random(14)
        for _ in range(300):
            body = corpses.outbreak_corpse(gm.world, zone, 0, rng)
            self.assertEqual(body.zone_id, "zone_street")
            self.assertTrue(1 <= body.gap <= zone.size_tiles)
            self.assertEqual(body.rot_at_death, 1)
            if not body.skeleton:
                self.assertTrue(body.outfit)

    def test_ten_random_holes_land_on_the_outermost_layer_with_none_there(self):
        everything = frozenset(BodyPart)
        layers = {}
        for location in (BodyLocation.TSHIRT, BodyLocation.JACKET):
            item = ClothingItem(
                id=f"item_test_{location.value}",
                name="Test",
                description="",
                max_hit_points=10,
                tags=[],
                body_location=location,
                covers=everything,
                insulation=0,
                wind_resistance=0,
                water_resistance=0,
                weight=1,
            )
            layers[location] = ItemEntity(item=item)
        corpses.add_random_holes(layers, random.Random(2), 10)
        holes = sum(len(entity.holes) for entity in layers.values())
        self.assertEqual(holes, 10)
        self.assertGreaterEqual(
            len(layers[BodyLocation.JACKET].holes), len(layers[BodyLocation.TSHIRT].holes)
        )

    def test_a_part_with_no_clothing_over_it_takes_no_hole(self):
        shirt = ItemEntity(item=ITEMS["item_tshirt"])
        corpses.add_random_holes({BodyLocation.TSHIRT: shirt}, random.Random(3), 200)
        self.assertTrue(shirt.holes <= shirt.item.covers)  # type: ignore[union-attr]


class RotAndRemovalTests(unittest.TestCase):
    """Spec 14, Rot and removal."""

    def test_the_stage_climbs_every_72_hours_to_three(self):
        body = corpse()
        self.assertEqual(
            [corpses.rot_stage(body, hours * HOUR) for hours in (0, 71, 72, 143, 144, 215)],
            [1, 1, 2, 2, 3, 3],
        )

    def test_a_body_that_started_at_stage_two_reaches_three_after_72_hours(self):
        body = corpse(rot_at_death=2)
        self.assertEqual(
            [corpses.rot_stage(body, h * HOUR) for h in (0, 71, 72, 215)], [2, 2, 3, 3]
        )

    def test_the_stage_never_passes_three(self):
        self.assertEqual(corpses.rot_stage(corpse(rot_at_death=3), 200 * HOUR), 3)

    def test_the_rot_words(self):
        self.assertEqual(ROT_WORDS, {1: "fresh", 2: "decaying", 3: "rotten"})
        self.assertEqual(SKELETON_WORD, "bare bones")

    def test_at_216_hours_a_body_not_turned_to_bones_is_removed(self):
        world = GameManager().world
        world.corpses["c1"] = corpse(contents=[ItemEntity(item=ITEMS["item_tshirt"])])
        corpses.update(world, 215 * HOUR, ScriptedRandom(randrange=[0]))
        self.assertIn("c1", world.corpses)
        corpses.update(world, 216 * HOUR, ScriptedRandom(randrange=[1]))
        self.assertNotIn("c1", world.corpses)

    def test_one_in_seven_become_skeletons_and_are_removed_72_hours_later(self):
        world = GameManager().world
        world.corpses["c1"] = corpse(contents=[ItemEntity(item=ITEMS["item_tshirt"])])
        rolls = ScriptedRandom(randrange=[0])
        corpses.update(world, 216 * HOUR, rolls)
        body = world.corpses["c1"]
        self.assertTrue(body.skeleton)
        self.assertEqual(body.contents, [])
        corpses.update(world, 287 * HOUR, ScriptedRandom(randrange=[0]))
        self.assertIn("c1", world.corpses)
        corpses.update(world, 288 * HOUR, ScriptedRandom(randrange=[0]))
        self.assertNotIn("c1", world.corpses)

    def test_a_skeleton_made_at_the_outbreak_is_removed_at_288_hours_without_a_roll(self):
        world = GameManager().world
        world.corpses["c1"] = corpse(skeleton=True)
        corpses.update(world, 216 * HOUR, ScriptedRandom())
        self.assertIn("c1", world.corpses)
        corpses.update(world, 288 * HOUR, ScriptedRandom())
        self.assertNotIn("c1", world.corpses)

    def test_one_in_seven_over_many_bodies(self):
        world = GameManager().world
        for number in range(1, 2001):
            world.corpses[f"c{number}"] = corpse(corpse_id=f"c{number}")
        corpses.update(world, 216 * HOUR, random.Random(8))
        self.assertAlmostEqual(len(world.corpses) / 2000, 1 / 7, delta=0.02)
        self.assertTrue(all(b.skeleton for b in world.corpses.values()))

    def test_a_body_in_another_zone_rots_the_same_way(self):
        gm = zombie_game("zone_home")
        gm.world.last_redistribution_minute = 216 * HOUR
        gm.world.corpses["c1"] = corpse(zone_id="zone_neighborhood")
        loop = ZombieLoop(gm, ScriptedRandom(randrange=[1]), SkillEngine())
        loop.run_minute(216 * HOUR, PlayerMinute())
        self.assertNotIn("c1", gm.world.corpses)


def fake_dead_game(gap: float = 3.0, *, crawling: bool = False, died_at: int = 0):
    gm = zombie_game()
    body = corpse(gap=gap, fake_dead=True, crawling=crawling, died_at=died_at)
    body.contents = [
        ItemEntity(item=ITEMS["item_jacket_police"]),
        ItemEntity(item=ITEMS["item_hand_axe"], condition=6),
    ]
    body.attached = body.contents[1]
    body.female = True
    body.outfit = "police"
    gm.world.corpses["c1"] = body
    return gm, body


class RisingTests(unittest.TestCase):
    """Spec 14, Fake-dead corpses: when a body gets up."""

    def test_it_rises_when_the_gap_interval_touches_2_to_4_tiles(self):
        cases = {(3, 3): True, (2, 2): True, (4, 4): True, (6, 3): True, (1, 5): True, (5, 1): True}
        cases |= {(5, 5): False, (1, 1): False, (8, 5): False, (1.5, 1.9): False, (4.5, 9): False}
        for (before, after), expected in cases.items():
            with self.subTest(gap=(before, after)):
                body = corpse(fake_dead=True)
                self.assertEqual(corpses.should_rise(body, before, after, 30), expected)

    def test_it_waits_30_minutes_after_it_died(self):
        body = corpse(fake_dead=True, died_at=100)
        self.assertFalse(corpses.should_rise(body, 3, 3, 129))
        self.assertTrue(corpses.should_rise(body, 3, 3, 130))

    def test_a_skeleton_or_an_ordinary_body_never_rises(self):
        self.assertFalse(corpses.should_rise(corpse(fake_dead=True, skeleton=True), 3, 3, 99))
        self.assertFalse(corpses.should_rise(corpse(fake_dead=False), 3, 3, 99))


class RisingInTheLoopTests(unittest.TestCase):
    """Spec 14, Fake-dead corpses: step 3b and the zombie that takes its place."""

    def minute(self, gm, now, **kwargs):
        loop = ZombieLoop(gm, random.Random(3), SkillEngine())
        return loop.run_minute(now, PlayerMinute(**kwargs))

    def test_a_body_rises_after_30_minutes_and_not_before(self):
        gm, body = fake_dead_game()
        self.minute(gm, 29)
        self.assertIn("c1", gm.world.corpses)
        report = self.minute(gm, 30)
        self.assertNotIn("c1", gm.world.corpses)
        self.assertEqual(list(gm.world.zombies), ["z1"])
        self.assertIn("A body on the ground lurches to its feet.", report.facts)
        self.assertTrue(report.interrupted)

    def test_a_body_at_gap_one_the_whole_time_stays_down(self):
        gm, _ = fake_dead_game(gap=1.0)
        for now in range(30, 40):
            self.minute(gm, now)
        self.assertIn("c1", gm.world.corpses)
        self.assertEqual(gm.world.zombies, {})

    def test_a_body_in_another_zone_stays_down(self):
        gm, body = fake_dead_game()
        body.zone_id = "zone_neighborhood"
        self.minute(gm, 40)
        self.assertIn("c1", gm.world.corpses)

    def test_walking_up_to_it_crosses_the_ring_in_one_minute(self):
        gm, body = fake_dead_game(gap=8.0)
        self.minute(gm, 40, approach_target="c1")
        self.assertNotIn("c1", gm.world.corpses)
        self.assertEqual(gm.world.zombies["z1"].gap, 4.0)

    def test_a_body_not_being_approached_keeps_its_gap(self):
        gm, body = fake_dead_game(gap=9.0)
        self.minute(gm, 40)
        self.assertEqual(body.gap, 9.0)
        self.assertIn("c1", gm.world.corpses)

    def test_the_new_zombie_keeps_the_clothes_and_is_rolled_afresh(self):
        gm, body = fake_dead_game()
        self.minute(gm, 30)
        zombie = gm.world.zombies["z1"]
        self.assertTrue(zombie.was_fake_dead)
        self.assertTrue(zombie.female)
        self.assertEqual(zombie.outfit, "police")
        self.assertEqual([e.item.id for e in zombie.worn.values()], ["item_jacket_police"])
        assert zombie.attached is not None
        self.assertEqual((zombie.attached.item.id, zombie.attached.condition), ("item_hand_axe", 6))
        self.assertTrue(0.5 <= zombie.health < 3.8)
        self.assertEqual(zombie.zone_id, "zone_street")
        self.assertEqual(zombie.gap, 3.0)

    def test_it_starts_chasing_facing_the_player(self):
        gm, body = fake_dead_game()
        self.minute(gm, 30)
        zombie = gm.world.zombies["z1"]
        self.assertEqual(zombie.state.value, "chasing")
        self.assertEqual(zombie.facing_cos, 1.0)
        self.assertEqual(zombie.time_since_seen, 180.0)

    def test_a_crawling_body_rises_as_a_crawler(self):
        gm, body = fake_dead_game(crawling=True)
        report = self.minute(gm, 30)
        zombie = gm.world.zombies["z1"]
        self.assertTrue(zombie.crawling)
        self.assertFalse(zombie.lunger)
        self.assertTrue(0.3 <= zombie.speed_mod < 0.45)
        self.assertIn(
            "A body on the ground twitches and starts to drag itself across the floor.",
            report.facts,
        )

    def test_a_standing_body_rises_standing(self):
        gm, body = fake_dead_game(crawling=False)
        self.minute(gm, 30)
        self.assertFalse(gm.world.zombies["z1"].crawling)

    def test_the_rising_counts_as_newly_noticing_the_player(self):
        gm, body = fake_dead_game()
        report = self.minute(gm, 30)
        self.assertEqual(
            report.interruption_fact, "A zombie notices {name} and heads straight for {object}."
        )
        self.assertEqual(report.new_seen, 1)


if __name__ == "__main__":
    unittest.main()


class CorpseEntryGapTests(unittest.TestCase):
    """Spec 14, Corpses: the gap is rolled again on every entry into the zone."""

    def test_entering_the_zone_rolls_each_corpse_gap_in_one_to_the_zone_size(self):
        from managers.zombies.population import enter_zone

        gm = zombie_game("zone_street")
        size = gm.world.locations["zone_neighborhood"].size_tiles
        here = corpse(zone_id="zone_neighborhood", gap=999.0)
        elsewhere = corpse(corpse_id="c2", zone_id="zone_street", gap=999.0)
        gm.world.corpses["c1"], gm.world.corpses["c2"] = here, elsewhere
        enter_zone(gm.world, "zone_neighborhood", "zone_street", ScriptedRandom(randrange=[size]))
        self.assertEqual(here.gap, float(size))
        self.assertEqual(elsewhere.gap, 999.0)


class RisenBodyKeepsItsPocketsTests(unittest.TestCase):
    """Spec 14, Fake-dead corpses: the zombie takes the corpse's worn items and contents."""

    def test_a_risen_zombie_carries_the_items_that_were_neither_worn_nor_the_weapon(self):
        gm, body = fake_dead_game()
        hammer = ItemEntity(item=ITEMS["item_hammer"])
        body.contents.append(hammer)
        zombie = ZombieLoop(gm, random.Random(3), SkillEngine())
        zombie.run_minute(30, PlayerMinute())
        risen = gm.world.zombies["z1"]
        self.assertEqual(risen.carried, [hammer])
        self.assertEqual(len(risen.worn), 1)
        self.assertIsNotNone(risen.attached)

    def test_a_weapon_in_the_pockets_is_not_taken_for_the_attached_one(self):
        gm, body = fake_dead_game()
        pocket_hammer = ItemEntity(item=ITEMS["item_hammer"])
        body.contents.insert(0, pocket_hammer)
        zombie = ZombieLoop(gm, random.Random(3), SkillEngine())
        zombie.run_minute(30, PlayerMinute())
        risen = gm.world.zombies["z1"]
        assert risen.attached is not None
        self.assertEqual(risen.attached.item.id, "item_hand_axe")
        self.assertEqual(risen.carried, [pocket_hammer])

    def test_a_body_with_no_attached_weapon_rises_without_one(self):
        gm, body = fake_dead_game()
        body.attached = None
        zombie = ZombieLoop(gm, random.Random(3), SkillEngine())
        zombie.run_minute(30, PlayerMinute())
        risen = gm.world.zombies["z1"]
        self.assertIsNone(risen.attached)
        self.assertEqual([e.item.id for e in risen.carried], ["item_hand_axe"])

    def test_a_weapon_the_player_took_is_not_given_back(self):
        gm, body = fake_dead_game()
        assert body.attached is not None
        body.contents.remove(body.attached)
        zombie = ZombieLoop(gm, random.Random(3), SkillEngine())
        zombie.run_minute(30, PlayerMinute())
        self.assertIsNone(gm.world.zombies["z1"].attached)
