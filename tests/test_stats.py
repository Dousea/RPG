"""Spec 02, Stats; Converting rates to game hours."""

import unittest

from data import survival
from modules import units
from modules.stats import CharacterStat, Stats

RANGES = {
    CharacterStat.HUNGER: (0, 1, 0),
    CharacterStat.THIRST: (0, 1, 0),
    CharacterStat.FATIGUE: (0, 1, 0),
    CharacterStat.ENDURANCE: (0, 1, 1),
    CharacterStat.STRESS: (0, 1, 0),
    CharacterStat.PANIC: (0, 100, 0),
    CharacterStat.IDLENESS: (0, 1, 0),
    CharacterStat.BOREDOM: (0, 100, 0),
    CharacterStat.UNHAPPINESS: (0, 100, 0),
    CharacterStat.PAIN: (0, 100, 0),
    CharacterStat.INTOXICATION: (0, 100, 0),
    CharacterStat.FOOD_SICKNESS: (0, 100, 0),
    CharacterStat.ZOMBIE_INFECTION: (0, 100, 0),
    CharacterStat.TEMPERATURE: (20, 40, 37),
    CharacterStat.WETNESS: (0, 100, 0),
    CharacterStat.SICKNESS: (0, 1, 0),
}


class StatTableTests(unittest.TestCase):
    """Spec 02, Stats."""

    def test_every_stat_has_the_spec_range_and_default(self):
        self.assertEqual(set(RANGES), set(CharacterStat))
        for stat, (low, high, default) in RANGES.items():
            self.assertEqual((stat.min, stat.max, stat.default), (low, high, default), stat)

    def test_fresh_stats_hold_the_defaults(self):
        stats = Stats()
        for stat, (_, _, default) in RANGES.items():
            self.assertEqual(stats.get(stat), default)

    def test_set_clamps_to_both_ends_for_every_stat(self):
        stats = Stats()
        for stat in CharacterStat:
            stats.set(stat, stat.max + 1000)
            self.assertEqual(stats.get(stat), stat.max)
            stats.set(stat, stat.min - 1000)
            self.assertEqual(stats.get(stat), stat.min)

    def test_add_and_remove_clamp(self):
        stats = Stats()
        stats.add(CharacterStat.HUNGER, 5)
        self.assertEqual(stats.get(CharacterStat.HUNGER), 1)
        stats.remove(CharacterStat.HUNGER, 0.25)
        self.assertAlmostEqual(stats.get(CharacterStat.HUNGER), 0.75)
        stats.remove(CharacterStat.HUNGER, 5)
        self.assertEqual(stats.get(CharacterStat.HUNGER), 0)

    def test_reset_one_and_all(self):
        stats = Stats()
        stats.set(CharacterStat.ENDURANCE, 0.2)
        stats.set(CharacterStat.PANIC, 40)
        stats.reset(CharacterStat.ENDURANCE)
        self.assertEqual(stats.get(CharacterStat.ENDURANCE), 1)
        self.assertEqual(stats.get(CharacterStat.PANIC), 40)
        stats.reset()
        self.assertEqual(stats.get(CharacterStat.PANIC), 0)

    def test_dict_round_trip_keeps_every_stat_exactly(self):
        stats = Stats()
        for index, stat in enumerate(CharacterStat):
            stats.set(stat, stat.min + (stat.max - stat.min) * (index + 1) / 20)
        loaded = Stats.from_dict(stats.to_dict())
        for stat in CharacterStat:
            self.assertEqual(loaded.get(stat), stats.get(stat))

    def test_unknown_names_are_dropped_and_values_clamped_on_load(self):
        loaded = Stats.from_dict({"hunger": 7, "mystery": 3})
        self.assertEqual(loaded.get(CharacterStat.HUNGER), 1)


class RateConversionTests(unittest.TestCase):
    """Spec 02, Converting rates to game hours."""

    def test_the_three_factors(self):
        self.assertEqual(units.per_hour_from_day_scaled(1), 3600)
        self.assertEqual(units.per_hour_from_frame(1), 10800)
        self.assertEqual(units.per_hour_from_real_frame(1), 6750)

    def test_constants_convert_to_the_per_hour_values(self):
        cases = {
            survival.HUNGER_INCREASE_per_hour: 0.03456,
            survival.HUNGER_INCREASE_WHEN_EXERCISE_per_hour: 0.06912,
            survival.HUNGER_INCREASE_WHILE_ASLEEP_per_hour: 0.0036,
            survival.THIRST_INCREASE_per_hour: 0.0288,
            survival.STRESS_DECREASE_per_hour: 0.108,
            survival.EXERCISE_ENDURANCE_DRAIN_per_hour: 0.2808,
            survival.IMOBILE_ENDURANCE_INCREASE_per_hour: 0.3348,
            survival.SLEEPING_ENDURANCE_REGEN_per_hour: 0.2232,
            survival.IDLE_INCREASE_per_hour: 1.8,
            survival.IDLE_DECREASE_per_hour: 21.6,
            survival.BOREDOM_DECREASE_per_hour: 41.58,
            survival.BOREDOM_INCREASE_per_hour: 10.8,
            survival.UNHAPPINESS_INCREASE_per_hour: 5.4,
            survival.PANIC_REDUCTION_per_hour: 405,
            survival.INTOXICATION_DECREASE_per_hour: 45.36,
            survival.FOOD_SICKNESS_DECREASE_per_hour: 16.2,
            survival.CORPSE_SICKNESS_per_hour: 1.134,
        }
        for actual, expected in cases.items():
            self.assertAlmostEqual(actual, expected, places=3)

    def test_walking_endurance_drain_is_a_real_frame_rate(self):
        self.assertAlmostEqual(survival.WALKING_ENDURANCE_DRAIN_per_hour, 0.0501, places=3)

    def test_health_loss_rates(self):
        self.assertAlmostEqual(survival.STARVING_HP_LOSS_per_hour, 3.564, places=3)
        self.assertAlmostEqual(survival.DYING_OF_THIRST_HP_LOSS_per_hour, 17.82, places=3)
        self.assertAlmostEqual(survival.FEVER_HP_LOSS_per_hour, 178.2, places=3)


if __name__ == "__main__":
    unittest.main()
