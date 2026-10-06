"""Spec 02, Stats; Converting rates to game hours."""

import unittest

from data import survival
from managers.stats.status_effects import (
    active_status_effects,
    bleeding_level,
    crit_penalty,
    damage_after_status_effects,
    defence_penalty,
    melee_status_effect_penalty,
    status_effect_level,
    status_effect_levels,
)
from modules import units
from modules.entity.player import PlayerEntity
from modules.stats import CharacterStat, Stats, StatusEffect

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
    CharacterStat.COLD_STRENGTH: (0, 100, 0),
    CharacterStat.WINDCHILL: (0, 100, 0),
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


class StatusEffectThresholdTests(unittest.TestCase):
    """Spec 03, Status effects."""

    ROWS = {
        StatusEffect.HUNGRY: (0.15, 0.25, 0.45, 0.70),
        StatusEffect.THIRST: (0.12, 0.25, 0.70, 0.84),
        StatusEffect.TIRED: (0.60, 0.70, 0.80, 0.90),
        StatusEffect.STRESS: (0.25, 0.50, 0.75, 0.90),
        StatusEffect.PANIC: (6, 30, 65, 80),
        StatusEffect.BORED: (25, 50, 75, 90),
        StatusEffect.UNHAPPY: (20, 45, 60, 80),
        StatusEffect.PAIN: (10, 20, 50, 75),
        StatusEffect.DRUNK: (10, 30, 50, 70),
        StatusEffect.SICK: (0.25, 0.50, 0.75, 0.90),
        StatusEffect.INJURED: (20, 40, 60, 75),
        StatusEffect.FOOD_EATEN: (0, 1600, 3200, 4800),
        StatusEffect.WET: (15, 40, 70, 90),
        StatusEffect.HAS_A_COLD: (20, 40, 60, 75),
        StatusEffect.HYPERTHERMIA: (37.5, 39, 40, 41),
        StatusEffect.WINDCHILL: (5, 10, 15, 20),
    }

    def test_each_column_is_strict_for_every_rising_status_effect(self):
        for status_effect, columns in self.ROWS.items():
            self.assertEqual(
                status_effect_level(status_effect, columns[0] - 0.01 if columns[0] else -1), 0
            )
            for level, column in enumerate(columns, start=1):
                with self.subTest(status_effect=status_effect, level=level):
                    self.assertEqual(status_effect_level(status_effect, column), level - 1)
                    self.assertEqual(status_effect_level(status_effect, column + 0.001), level)

    def test_endurance_is_inverted_and_inclusive(self):
        for level, column in enumerate((0.75, 0.50, 0.25, 0.10), start=1):
            with self.subTest(level=level):
                self.assertEqual(status_effect_level(StatusEffect.ENDURANCE, column), level)
                self.assertEqual(
                    status_effect_level(StatusEffect.ENDURANCE, column + 0.001), level - 1
                )

    def test_hunger_exactly_0_15_is_level_0_and_just_above_is_level_1(self):
        self.assertEqual(status_effect_level(StatusEffect.HUNGRY, 0.15), 0)
        self.assertEqual(status_effect_level(StatusEffect.HUNGRY, 0.1501), 1)

    def test_endurance_exactly_0_75_is_level_1(self):
        self.assertEqual(status_effect_level(StatusEffect.ENDURANCE, 0.75), 1)

    def test_food_eaten_timer_levels(self):
        self.assertEqual(status_effect_level(StatusEffect.FOOD_EATEN, 0), 0)
        self.assertEqual(status_effect_level(StatusEffect.FOOD_EATEN, 1), 1)
        self.assertEqual(status_effect_level(StatusEffect.FOOD_EATEN, 1601), 2)
        self.assertEqual(status_effect_level(StatusEffect.FOOD_EATEN, 3201), 3)
        self.assertEqual(status_effect_level(StatusEffect.FOOD_EATEN, 4801), 4)

    def test_bleeding_level_is_the_bleeding_parts_capped_at_four(self):
        self.assertEqual(bleeding_level(0, neck=False), 0)
        self.assertEqual(bleeding_level(3, neck=False), 3)
        self.assertEqual(bleeding_level(9, neck=False), 4)
        self.assertEqual(bleeding_level(1, neck=True), 4)

    def test_injured_reads_lost_hp_and_is_off_at_zero_hp(self):
        player = PlayerEntity(name="T", current_location_id="x")
        player.hit_points = 80
        self.assertEqual(
            dict((m, lv) for m, lv, _ in active_status_effects(player)).get(
                StatusEffect.INJURED, 0
            ),
            0,
        )
        player.hit_points = 79
        names = {m: n for m, _, n in active_status_effects(player)}
        self.assertEqual(names[StatusEffect.INJURED], "A Little Hurt")
        player.hit_points = 0
        self.assertNotIn(StatusEffect.INJURED, {m for m, _, _ in active_status_effects(player)})


class TemperatureStatusEffectTests(unittest.TestCase):
    """Spec 06, Status effects added to 03."""

    def test_hypothermia_columns_are_strict_and_fall_with_the_core(self):
        for level, column in enumerate((36.5, 35, 30, 25), start=1):
            with self.subTest(level=level):
                self.assertEqual(status_effect_level(StatusEffect.HYPOTHERMIA, column), level - 1)
                self.assertEqual(
                    status_effect_level(StatusEffect.HYPOTHERMIA, column - 0.001), level
                )

    def _levels(self, core, intoxication):
        stats = Stats()
        stats.set(CharacterStat.TEMPERATURE, core)
        stats.set(CharacterStat.INTOXICATION, intoxication)
        return status_effect_levels(stats)[StatusEffect.HYPOTHERMIA]

    def test_intoxication_above_30_hides_hypothermia_level_1(self):
        self.assertEqual(self._levels(36.0, 30), 1)
        self.assertEqual(self._levels(36.0, 31), 0)

    def test_intoxication_above_70_hides_hypothermia_level_2(self):
        self.assertEqual(self._levels(34.0, 70), 2)
        self.assertEqual(self._levels(34.0, 71), 0)

    def test_deeper_hypothermia_is_never_hidden(self):
        self.assertEqual(self._levels(29.0, 100), 3)
        self.assertEqual(self._levels(24.0, 100), 4)

    def test_new_status_effects_read_their_stats(self):
        stats = Stats()
        stats.set(CharacterStat.WETNESS, 41)
        stats.set(CharacterStat.COLD_STRENGTH, 61)
        stats.set(CharacterStat.WINDCHILL, 16)
        stats.set(CharacterStat.TEMPERATURE, 39.5)
        levels = status_effect_levels(stats)
        self.assertEqual(levels[StatusEffect.WET], 2)
        self.assertEqual(levels[StatusEffect.HAS_A_COLD], 3)
        self.assertEqual(levels[StatusEffect.WINDCHILL], 3)
        self.assertEqual(levels[StatusEffect.HYPERTHERMIA], 2)


class StatusEffectEffectTests(unittest.TestCase):
    """Spec 03, What status effects do."""

    @staticmethod
    def _stats(panic_level: int, stress_level: int) -> Stats:
        stats = Stats()
        stats.set(CharacterStat.PANIC, {0: 0, 1: 7, 2: 31, 3: 66, 4: 81}[panic_level])
        stats.set(CharacterStat.STRESS, {0: 0, 1: 0.3, 2: 0.51, 3: 0.76, 4: 0.91}[stress_level])
        return stats

    def test_panic_2_and_stress_3_subtract_half_a_point(self):
        self.assertAlmostEqual(melee_status_effect_penalty(self._stats(2, 3)), 0.5)

    def test_panic_1_and_stress_1_change_nothing(self):
        self.assertEqual(melee_status_effect_penalty(self._stats(1, 1)), 0)

    def test_the_hit_never_goes_below_the_floor(self):
        self.assertEqual(damage_after_status_effects(0.2, self._stats(4, 4)), 0.1)
        self.assertAlmostEqual(damage_after_status_effects(1.0, self._stats(2, 3)), 0.5)

    def test_stress_2_alone_subtracts_0_2(self):
        self.assertAlmostEqual(melee_status_effect_penalty(self._stats(0, 2)), 0.2)

    def test_a_small_hit_is_reduced_not_raised_to_the_floor(self):
        self.assertAlmostEqual(damage_after_status_effects(0.55, self._stats(2, 3)), 0.05)

    def test_a_hit_the_penalty_drives_negative_becomes_0_1(self):
        self.assertAlmostEqual(damage_after_status_effects(0.45, self._stats(2, 3)), 0.1)

    def test_bleeding_level_is_reported_when_supplied(self):
        levels = status_effect_levels(Stats(), bleeding=2)
        self.assertEqual(levels[StatusEffect.BLEEDING], 2)
        self.assertEqual(status_effect_levels(Stats())[StatusEffect.BLEEDING], 0)

    def test_crit_penalty_per_level(self):
        self.assertAlmostEqual(crit_penalty(endurance=2, heavy_load=1, panic=3), 10 + 5 + 3.9)

    def test_defence_penalty_per_level(self):
        self.assertEqual(defence_penalty(endurance=2, tired=1, drunk=3), 4 + 3 + 6)


if __name__ == "__main__":
    unittest.main()
