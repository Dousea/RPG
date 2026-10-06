"""Spec 09, A zombie: how one zombie is rolled."""

import random
import unittest

from managers.zombies import roll_zombie

ROLLS = 10000


class RollZombieTests(unittest.TestCase):
    """Spec 09, A zombie: health, speed, senses, memory and strength."""

    @classmethod
    def setUpClass(cls):
        rng = random.Random(1)
        cls.zombies = [roll_zombie(rng, f"z{i}", "zone_street") for i in range(ROLLS)]

    def test_health_range(self):
        healths = [z.health for z in self.zombies]
        self.assertGreaterEqual(min(healths), 0.5)
        self.assertLess(max(healths), 3.8)
        self.assertLess(min(healths), 0.6)
        self.assertGreater(max(healths), 3.7)

    def test_half_are_shamblers_and_a_sixth_lungers(self):
        shamblers = sum(1 for z in self.zombies if z.speed_type == 3)
        fast = sum(1 for z in self.zombies if z.speed_type == 2)
        lungers = sum(1 for z in self.zombies if z.lunger)
        self.assertEqual(shamblers + fast, ROLLS)
        self.assertAlmostEqual(shamblers / ROLLS, 0.5, delta=0.03)
        self.assertAlmostEqual(lungers / ROLLS, 1 / 6, delta=0.03)

    def test_no_sprinters(self):
        self.assertTrue(all(z.speed_type in (2, 3) for z in self.zombies))

    def test_speed_mod_ranges(self):
        for zombie in self.zombies:
            if zombie.lunger:
                self.assertGreaterEqual(zombie.speed_mod, 0.85)
                self.assertLess(zombie.speed_mod, 1.0)
            else:
                self.assertGreaterEqual(zombie.speed_mod, 0.55)
                self.assertLess(zombie.speed_mod, 0.70)

    def test_senses_memory_and_strength(self):
        self.assertTrue(all(z.sight in (2, 3) for z in self.zombies))
        self.assertTrue(all(z.hearing in (2, 3) for z in self.zombies))
        poor = sum(1 for z in self.zombies if z.sight == 3)
        self.assertAlmostEqual(poor / ROLLS, 0.5, delta=0.03)
        self.assertTrue(all(z.memory == 800 for z in self.zombies))
        self.assertTrue(all(z.strength == 3 for z in self.zombies))

    def test_new_zombie_has_not_seen_the_player(self):
        zombie = self.zombies[0]
        self.assertEqual(zombie.time_since_seen, 100000)
        self.assertEqual(zombie.state.value, "idle")


if __name__ == "__main__":
    unittest.main()
