"""Spec 09, Population."""

import random
import unittest

from data.world.locations import build_starting_locations
from managers.game import GameManager
from managers.zombies.population import (
    kill_zombie,
    per_chunk,
    population_curve,
    redistribute,
    roll_zombie,
    start_outbreak,
    stochastic_round,
    zone_target,
)
from modules.entity.barrier import BarrierEntity, BarrierKind
from modules.entity.zombie import ZombieState


class PerChunkTests(unittest.TestCase):
    """Spec 09, Population: per-chunk zombies from a 0-255 intensity."""

    def test_per_chunk_for_listed_intensities(self):
        expected = {0: 0.06, 32: 0.8091, 64: 1.5584, 96: 2.3075, 255: 6.03}
        for intensity, value in expected.items():
            with self.subTest(intensity=intensity):
                self.assertAlmostEqual(per_chunk(intensity), value, places=3)


class CurveTests(unittest.TestCase):
    """Spec 09, Population: the curve rises from 1.0 to 1.5 over 28 days."""

    def test_curve_values(self):
        self.assertAlmostEqual(population_curve(0), 1.0)
        self.assertAlmostEqual(population_curve(14), 1.25)
        self.assertAlmostEqual(population_curve(28), 1.5)
        self.assertAlmostEqual(population_curve(90), 1.5)


class ZoneFieldTests(unittest.TestCase):
    """Spec 09, Zones: size, chunks and intensity per zone."""

    def test_zone_fields(self):
        zones = build_starting_locations()
        rows = {
            zone_id: (zone.size_tiles, zone.chunks, zone.zombie_intensity)
            for zone_id, zone in zones.items()
        }
        self.assertEqual(
            rows,
            {
                "zone_home": (8, 1, 0),
                "zone_building": (20, 3, 32),
                "zone_street": (40, 6, 96),
                "zone_bodega": (10, 1, 63),
                "zone_neighborhood": (80, 16, 64),
                "zone_flat_vacant": (8, 1, 0),
                "zone_flat_tenant": (8, 1, 64),
                "zone_pharmacy": (14, 2, 63),
                "zone_clinic": (20, 3, 48),
                "zone_supermarket": (30, 6, 63),
                "zone_hardware": (20, 3, 63),
            },
        )


class NewZoneTargetTests(unittest.TestCase):
    """Spec 25, The new zones: the outbreak target of each new zone."""

    def test_each_target_at_the_outbreak(self):
        zones = build_starting_locations()
        expected = {
            "zone_flat_vacant": 0.04,
            "zone_flat_tenant": 1.0,
            "zone_pharmacy": 2.0,
            "zone_clinic": 2.3,
            "zone_supermarket": 6.0,
            "zone_hardware": 3.0,
        }
        for zone_id, target in expected.items():
            with self.subTest(zone_id):
                self.assertAlmostEqual(zone_target(zones[zone_id], 0), target, delta=0.02)


if __name__ == "__main__":
    unittest.main()


class OutbreakFillTests(unittest.TestCase):
    """Spec 09, The outbreak and Population: every zone fills; zone_home starts empty."""

    def setUp(self):
        self.gm = GameManager()
        self.gm.player.current_location_id = "zone_street"
        self.rng = random.Random(3)

    def counts(self) -> dict[str, int]:
        result = {zone_id: 0 for zone_id in self.gm.world.locations}
        for zombie in self.gm.world.zombies.values():
            result[zombie.zone_id] += 1
        return result

    def test_no_zombies_before_the_outbreak(self):
        self.assertIsNone(self.gm.world.outbreak_started_at)
        self.assertEqual(self.gm.world.zombies, {})

    def test_start_outbreak_fills_every_zone_but_home(self):
        start_outbreak(self.gm.world, 100, "zone_street", self.rng)
        counts = self.counts()
        self.assertEqual(self.gm.world.outbreak_started_at, 100)
        self.assertEqual(counts["zone_home"], 0)
        self.assertIn(counts["zone_building"], (1, 2))
        self.assertEqual(counts["zone_street"], 9)
        self.assertIn(counts["zone_neighborhood"], (16, 17))

    def test_zombie_ids_count_up_from_z1(self):
        start_outbreak(self.gm.world, 0, "zone_street", self.rng)
        ids = list(self.gm.world.zombies)
        self.assertEqual(ids[:3], ["z1", "z2", "z3"])
        self.assertEqual(self.gm.world.next_zombie_number, len(ids) + 1)

    def test_zombies_in_the_players_zone_get_a_gap_inside_the_zone(self):
        start_outbreak(self.gm.world, 0, "zone_street", self.rng)
        for zombie in self.gm.world.zombies.values():
            if zombie.zone_id == "zone_street":
                self.assertGreaterEqual(zombie.gap, 1)
                self.assertLessEqual(zombie.gap, 40)
                self.assertGreaterEqual(zombie.facing_cos, -1)
                self.assertLessEqual(zombie.facing_cos, 1)

    def test_stochastic_rounding_averages_to_the_target(self):
        rng = random.Random(5)
        total = sum(stochastic_round(2.4, rng) for _ in range(10000))
        self.assertAlmostEqual(total / 10000, 2.4, delta=0.03)
        self.assertEqual({stochastic_round(2.4, rng) for _ in range(200)}, {2, 3})
        self.assertEqual(stochastic_round(3.0, rng), 3)

    def test_zone_target_follows_the_curve(self):
        zone = self.gm.world.locations["zone_street"]
        self.assertAlmostEqual(zone_target(zone, 0), 6 * 2.3075 * 0.65, places=2)
        self.assertAlmostEqual(zone_target(zone, 14), 6 * 2.3075 * 0.65 * 1.25, places=2)

    def test_zone_home_has_a_target_from_the_curve_after_the_outbreak(self):
        """Only the outbreak fill leaves the spawn building empty."""
        home = self.gm.world.locations["zone_home"]
        self.assertGreater(zone_target(home, 0), 0.03)
        self.assertLess(zone_target(home, 0), 0.07)


class RedistributionTests(unittest.TestCase):
    """Spec 09, Population: every 12 hours idle zombies move one hop toward targets."""

    def setUp(self):
        self.gm = GameManager()
        self.world = self.gm.world
        self.rng = random.Random(9)
        self.world.outbreak_started_at = 0
        self.world.last_redistribution_minute = 0
        for barrier in self.world.barriers.values():
            barrier.open = True

    def add(self, zone_id: str, count: int):
        for _ in range(count):
            number = self.world.next_zombie_number
            self.world.next_zombie_number += 1
            zombie_id = f"z{number}"
            self.world.zombies[zombie_id] = roll_zombie(self.rng, zombie_id, zone_id)

    def counts(self) -> dict[str, int]:
        result = {zone_id: 0 for zone_id in self.world.locations}
        for zombie in self.world.zombies.values():
            result[zombie.zone_id] += 1
        return result

    def test_surplus_idle_zombies_move_one_hop_to_a_zone_below_target(self):
        self.add("zone_street", 20)
        redistribute(self.world, 720, "zone_home", self.rng)
        counts = self.counts()
        self.assertLessEqual(counts["zone_street"], 9 + 1)
        self.assertGreater(counts["zone_building"], 0)
        self.assertGreater(counts["zone_neighborhood"], 0)
        self.assertEqual(counts["zone_home"], 0)

    def test_zombies_move_only_one_hop(self):
        self.add("zone_neighborhood", 40)
        redistribute(self.world, 720, "zone_home", self.rng)
        movers = {
            z.zombie_id: z.zone_id
            for z in self.world.zombies.values()
            if int(z.zombie_id[1:]) <= 40
        }
        self.assertEqual(
            set(movers.values()),
            {
                "zone_neighborhood",
                "zone_street",
                "zone_pharmacy",
                "zone_clinic",
                "zone_supermarket",
                "zone_hardware",
            },
        )
        self.assertEqual(self.counts()["zone_street"], 9)

    def test_busy_zombies_stay_put(self):
        self.add("zone_street", 20)
        for zombie in self.world.zombies.values():
            zombie.state = ZombieState.CHASING
        redistribute(self.world, 720, "zone_home", self.rng)
        self.assertEqual(
            {z.zone_id for z in self.world.zombies.values() if z.state == ZombieState.CHASING},
            {"zone_street"},
        )

    def test_zones_below_target_gain_new_zombies(self):
        redistribute(self.world, 720, "zone_home", self.rng)
        counts = self.counts()
        self.assertIn(counts["zone_building"], (1, 2))
        self.assertEqual(counts["zone_street"], 9)
        self.assertEqual(counts["zone_home"], 0)

    def test_the_curve_adds_zombies_over_time(self):
        redistribute(self.world, 14 * 1440, "zone_home", self.rng)
        self.assertGreaterEqual(self.counts()["zone_street"], 11)

    def test_a_closed_door_stops_movement_and_new_zombies(self):
        for barrier_id in ("door_lobby", "door_apartment", "door_flat_vacant", "door_flat_tenant"):
            self.world.barriers[barrier_id].open = False
        self.add("zone_street", 20)
        redistribute(self.world, 720, "zone_home", self.rng)
        self.assertEqual(self.counts()["zone_building"], 0)

    def test_a_zone_whose_connections_are_all_blocked_gains_nothing(self):
        self.world.barriers["gate"] = BarrierEntity(
            barrier_id="gate",
            kind=BarrierKind.DOOR,
            zones=("zone_street", "zone_neighborhood"),
            inside_zone="zone_street",
            name="gate",
            health=500,
            max_health=500,
        )
        for barrier_id in (
            "door_clinic",
            "door_hardware",
            "window_pharmacy",
            "window_supermarket",
        ):
            self.world.barriers[barrier_id].open = False
        redistribute(self.world, 720, "zone_home", self.rng)
        self.assertEqual(self.counts()["zone_neighborhood"], 0)

    def test_a_zombie_arriving_in_the_players_zone_gets_a_gap(self):
        self.add("zone_neighborhood", 40)
        redistribute(self.world, 720, "zone_street", self.rng)
        for zombie in self.world.zombies.values():
            if zombie.zone_id == "zone_street":
                self.assertGreaterEqual(zombie.gap, 1)
                self.assertLessEqual(zombie.gap, 40)

    def test_same_seed_gives_the_same_result(self):
        def run() -> dict[str, str]:
            world = GameManager().world
            rng = random.Random(4)
            start_outbreak(world, 0, "zone_home", rng)
            redistribute(world, 720, "zone_home", rng)
            return {z.zombie_id: z.zone_id for z in world.zombies.values()}

        self.assertEqual(run(), run())


class NoRespawnTests(unittest.TestCase):
    """Spec 09, Population: a killed zombie is gone for good."""

    def test_killing_a_zombie_leaves_its_zone_one_short(self):
        gm = GameManager()
        rng = random.Random(0)
        start_outbreak(gm.world, 0, "zone_home", rng)
        street = [z for z in gm.world.zombies.values() if z.zone_id == "zone_street"]
        self.assertEqual(len(street), 9)
        kill_zombie(gm.world, street[0].zombie_id)
        redistribute(gm.world, 720, "zone_home", rng)
        self.assertEqual(
            len([z for z in gm.world.zombies.values() if z.zone_id == "zone_street"]), 8
        )
        self.assertNotIn(street[0].zombie_id, gm.world.zombies)

    def test_a_kill_is_counted_against_the_zone(self):
        gm = GameManager()
        start_outbreak(gm.world, 0, "zone_home", random.Random(0))
        zombie = next(iter(gm.world.zombies.values()))
        kill_zombie(gm.world, zombie.zombie_id)
        self.assertEqual(gm.world.zombie_kills, {zombie.zone_id: 1})


class RedistributionHomeTests(unittest.TestCase):
    """Spec 09, Population: the spawn building is cleared only at the outbreak."""

    def test_redistribution_can_put_zombies_in_zone_home(self):
        found = False
        for seed in range(400):
            world = GameManager().world
            world.outbreak_started_at = 0
            world.last_redistribution_minute = 0
            for barrier in world.barriers.values():
                barrier.open = True
            redistribute(world, 720, "zone_street", random.Random(seed))
            if any(z.zone_id == "zone_home" for z in world.zombies.values()):
                found = True
                break
        self.assertTrue(found)
