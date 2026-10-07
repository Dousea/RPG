"""body-temperature: Colds; Sneezes and coughs."""

import random
import unittest

from managers.body.cold import ColdDriver, catch_cold_delta, roll_sneeze, start_cold
from managers.body.stats.drivers import StatContext
from managers.body.stats.engine import StatsEngine
from managers.body.thermoregulator import NodeClothing
from modules.body.parts import BodyPart
from modules.body.stats import CharacterStat
from modules.body.thermal import ThermalState
from modules.entity.player import PlayerEntity

TORSO_25C = (8 / 13) ** 2 * 0.25 * 0.18 * 16
ALL_THREE_AT_20C = 0.25 * 0.18 * 16 + 0.25 * 0.02 * 8 + 0.25 * 0.08 * 4
RISE_PER_MIN = 0.003 * 180
FALL_PER_MIN = 0.175 * 112.5
COURSE_PER_MIN = 0.0112 * 180

PRONE_TO_ILLNESS_ID = "pronetoillness"  # character-creation: Traits with an effect now
RESILIENT_ID = "resilient"
OUTDOORSMAN_ID = "outdoorsman"


def chilled_state(skin_c=25.0, parts=(BodyPart.TORSO_UPPER,)) -> ThermalState:
    state = ThermalState()
    for part in parts:
        state.skin[part] = skin_c
    return state


def skin_for_torso_delta(delta: float) -> float:
    """The torso skin temperature whose cold-skin delta is `delta`."""
    x = delta / (0.25 * 0.18 * 16)
    return 20 + 13 * (1 - x**0.5)


class CatchColdDeltaTests(unittest.TestCase):
    """body-temperature: Colds: the catch-a-cold delta."""

    def test_a_cold_upper_torso_counts_sixteen_times(self):
        self.assertAlmostEqual(catch_cold_delta(chilled_state(), {}, 0), TORSO_25C)

    def test_skin_at_33_adds_nothing_and_just_under_33_does(self):
        self.assertEqual(catch_cold_delta(ThermalState(), {}, 0), 0.0)
        self.assertEqual(catch_cold_delta(chilled_state(35.0), {}, 0), 0.0)
        self.assertEqual(catch_cold_delta(chilled_state(33.0), {}, 0), 0.0)
        self.assertGreater(catch_cold_delta(chilled_state(32.9), {}, 0), 0.0)
        self.assertAlmostEqual(
            catch_cold_delta(chilled_state(32.9), {}, 0), (1 - 12.9 / 13) ** 2 * 0.25 * 0.18 * 16
        )

    def test_neck_counts_eight_times_and_head_four_times(self):
        neck = chilled_state(25.0, (BodyPart.NECK,))
        head = chilled_state(25.0, (BodyPart.HEAD,))
        self.assertAlmostEqual(catch_cold_delta(neck, {}, 0), (8 / 13) ** 2 * 0.25 * 0.02 * 8)
        self.assertAlmostEqual(catch_cold_delta(head, {}, 0), (8 / 13) ** 2 * 0.25 * 0.08 * 4)

    def test_other_nodes_count_once(self):
        state = chilled_state(25.0, (BodyPart.HAND_L,))
        self.assertAlmostEqual(catch_cold_delta(state, {}, 0), (8 / 13) ** 2 * 0.25 * 0.01)

    def test_wet_skin_multiplies_by_one_plus_its_wetness(self):
        self.assertAlmostEqual(catch_cold_delta(chilled_state(), {}, 0, 0.5), TORSO_25C * 1.5)

    def test_clothing_wetter_than_half_multiplies_further(self):
        wet = {BodyPart.TORSO_UPPER: NodeClothing(wetness=0.75)}
        self.assertAlmostEqual(catch_cold_delta(chilled_state(), wet, 0), TORSO_25C * 1.5)
        half = {BodyPart.TORSO_UPPER: NodeClothing(wetness=0.5)}
        self.assertAlmostEqual(catch_cold_delta(chilled_state(), half, 0), TORSO_25C)
        full = {BodyPart.TORSO_UPPER: NodeClothing(wetness=1.0)}
        self.assertAlmostEqual(catch_cold_delta(chilled_state(), full, 0, 1.0), TORSO_25C * 2 * 2)

    def test_hypothermia_above_level_1_multiplies_the_delta_by_the_level(self):
        self.assertAlmostEqual(catch_cold_delta(chilled_state(), {}, 1), TORSO_25C)
        self.assertAlmostEqual(catch_cold_delta(chilled_state(), {}, 2), TORSO_25C * 2)
        self.assertAlmostEqual(catch_cold_delta(chilled_state(), {}, 3), TORSO_25C * 3)


def cold_player(strength=0.0, **stats) -> PlayerEntity:
    player = PlayerEntity(name="Orton", current_location_id="zone_street")
    player.stats.set(CharacterStat.COLD_STRENGTH, strength)
    for stat, value in stats.items():
        player.stats.set(CharacterStat[stat], value)
    return player


def chill(player, skin=20.0):
    for part in (BodyPart.TORSO_UPPER, BodyPart.NECK, BodyPart.HEAD):
        player.thermal.skin[part] = skin


def run(player, minutes, rng=None, **ctx):
    engine = StatsEngine([ColdDriver(rng or random.Random(1))])
    return engine.advance(player, minutes, StatContext(**ctx))


class CatchCounterTests(unittest.TestCase):
    """body-temperature: Colds: catching."""

    def test_counter_rises_by_0_54_times_the_delta_per_minute(self):
        player = cold_player()
        chill(player)
        run(player, 6)
        self.assertAlmostEqual(player.thermal.catch_cold, RISE_PER_MIN * ALL_THREE_AT_20C * 6)

    def test_a_delta_of_0_15_raises_the_counter_and_0_05_lets_it_fall(self):
        raising = cold_player()
        raising.thermal.skin[BodyPart.TORSO_UPPER] = skin_for_torso_delta(0.15)
        run(raising, 1)
        self.assertAlmostEqual(raising.thermal.catch_cold, RISE_PER_MIN * 0.15)
        falling = cold_player()
        falling.thermal.skin[BodyPart.TORSO_UPPER] = skin_for_torso_delta(0.05)
        falling.thermal.catch_cold = 50.0
        run(falling, 1)
        self.assertAlmostEqual(falling.thermal.catch_cold, 50.0 - FALL_PER_MIN)

    def test_the_counter_falls_19_6875_per_minute_and_never_below_zero(self):
        self.assertAlmostEqual(FALL_PER_MIN, 19.6875)
        player = cold_player()
        player.thermal.catch_cold = 30.0
        run(player, 1)
        self.assertAlmostEqual(player.thermal.catch_cold, 10.3125)
        run(player, 5)
        self.assertEqual(player.thermal.catch_cold, 0.0)

    def test_the_counter_keeps_falling_during_a_cold_while_the_delta_is_low(self):
        player = cold_player(30.0)
        player.thermal.catch_cold = 30.0
        run(player, 1, indoors=True)
        self.assertAlmostEqual(player.thermal.catch_cold, 30.0 - FALL_PER_MIN)

    def test_the_counter_stands_still_while_a_cold_runs_and_the_delta_is_high(self):
        player = cold_player(30.0)
        chill(player)
        run(player, 5, indoors=False)
        self.assertEqual(player.thermal.catch_cold, 0.0)

    def test_a_cold_starts_at_strength_20_with_the_sneeze_timer_0(self):
        player = cold_player()
        player.thermal.sneeze_timer = 400.0
        player.thermal.catch_cold = 77.0
        start_cold(player.thermal, player.stats)
        self.assertEqual(player.stats.get(CharacterStat.COLD_STRENGTH), 20.0)
        self.assertEqual(player.thermal.catch_cold, 0.0)
        self.assertEqual(player.thermal.sneeze_timer, 0.0)

    def test_the_counter_reaching_100_starts_the_cold_inside_the_driver(self):
        player = cold_player()
        chill(player)
        player.thermal.catch_cold = 99.9
        run(player, 1, indoors=False)
        self.assertEqual(player.thermal.catch_cold, 0.0)
        self.assertGreater(player.stats.get(CharacterStat.COLD_STRENGTH), 19.0)
        self.assertLess(player.stats.get(CharacterStat.COLD_STRENGTH), 23.0)

    def test_the_counter_below_100_starts_nothing(self):
        player = cold_player()
        chill(player)
        player.thermal.catch_cold = 90.0
        run(player, 1, indoors=False)
        self.assertEqual(player.stats.get(CharacterStat.COLD_STRENGTH), 0.0)
        self.assertGreater(player.thermal.catch_cold, 90.0)

    def test_traits_scale_the_catch_rate(self):
        results = {}
        for trait in (None, PRONE_TO_ILLNESS_ID, RESILIENT_ID, OUTDOORSMAN_ID):
            player = cold_player()
            chill(player)
            run(player, 6, traits=frozenset({trait}) if trait else frozenset())
            results[trait] = player.thermal.catch_cold
        base = results[None]
        self.assertAlmostEqual(results[PRONE_TO_ILLNESS_ID], base * 1.7)
        self.assertAlmostEqual(results[RESILIENT_ID], base * 0.45)
        self.assertAlmostEqual(results[OUTDOORSMAN_ID], base * 0.25)

    def test_the_trait_multiplier_does_not_change_which_side_of_0_1_the_delta_falls_on(self):
        player = cold_player()
        player.thermal.skin[BodyPart.TORSO_UPPER] = skin_for_torso_delta(0.05)
        player.thermal.catch_cold = 50.0
        run(player, 1, traits=frozenset({PRONE_TO_ILLNESS_ID}))
        self.assertAlmostEqual(player.thermal.catch_cold, 50.0 - FALL_PER_MIN)

    def test_wet_skin_and_wet_clothes_raise_the_rate(self):
        dry = cold_player()
        wet = cold_player(WETNESS=50)
        for player in (dry, wet):
            chill(player)
            run(player, 1)
        self.assertAlmostEqual(wet.thermal.catch_cold, dry.thermal.catch_cold * 1.5)

    def test_hypothermia_level_multiplies_the_rate_above_level_1(self):
        base = cold_player()
        cold = cold_player(TEMPERATURE=32.0)
        for player in (base, cold):
            chill(player)
            run(player, 1)
        self.assertAlmostEqual(cold.thermal.catch_cold, base.thermal.catch_cold * 2)


class ColdCourseTests(unittest.TestCase):
    """body-temperature: Colds: the course."""

    def test_indoors_rested_and_dry_the_cold_recovers_by_2_016_per_minute(self):
        player = cold_player(50.0)
        run(player, 5, indoors=True)
        self.assertAlmostEqual(player.stats.get(CharacterStat.COLD_STRENGTH), 50.0 - 5 * 2.016)

    def test_outdoors_the_cold_worsens_at_the_same_rate(self):
        player = cold_player(50.0)
        run(player, 5, indoors=False)
        self.assertAlmostEqual(player.stats.get(CharacterStat.COLD_STRENGTH), 50.0 + 5 * 2.016)

    def test_worsening_is_capped_at_100(self):
        player = cold_player(99.0)
        run(player, 5, indoors=False)
        self.assertEqual(player.stats.get(CharacterStat.COLD_STRENGTH), 100.0)

    def test_each_failed_condition_turns_recovery_into_worsening(self):
        cases = {
            "wet": {"WETNESS": 16},
            "hypothermic": {"TEMPERATURE": 36.0},
            "tired": {"FATIGUE": 0.51},
            "hungry": {"HUNGER": 0.26},
            "thirsty": {"THIRST": 0.26},
        }
        for name, stats in cases.items():
            with self.subTest(name):
                player = cold_player(50.0, **stats)
                run(player, 1, indoors=True)
                self.assertGreater(player.stats.get(CharacterStat.COLD_STRENGTH), 50.0)

    def test_the_limits_themselves_still_allow_recovery(self):
        player = cold_player(50.0, FATIGUE=0.5, HUNGER=0.25, THIRST=0.25, WETNESS=15)
        run(player, 1, indoors=True)
        self.assertLess(player.stats.get(CharacterStat.COLD_STRENGTH), 50.0)

    def test_cold_reduction_forces_recovery_twice_as_fast_and_drains_0_9_per_minute(self):
        player = cold_player(50.0)
        player.thermal.cold_reduction = 10.0
        run(player, 5, indoors=False)
        self.assertAlmostEqual(player.stats.get(CharacterStat.COLD_STRENGTH), 50.0 - 5 * 2 * 2.016)
        self.assertAlmostEqual(player.thermal.cold_reduction, 10.0 - 5 * 0.9)

    def test_the_cold_is_over_when_strength_goes_below_zero_and_the_counter_resets(self):
        player = cold_player(1.0)
        player.thermal.catch_cold = 40.0
        player.thermal.sneeze_timer = 300.0
        run(player, 1, indoors=True)
        self.assertEqual(player.stats.get(CharacterStat.COLD_STRENGTH), 0.0)
        self.assertEqual(player.thermal.sneeze_timer, 0.0)
        self.assertEqual(player.thermal.catch_cold, 0.0)

    def test_course_traits(self):
        def after(trait, indoors):
            player = cold_player(50.0)
            run(player, 1, indoors=indoors, traits=frozenset({trait}))
            return player.stats.get(CharacterStat.COLD_STRENGTH)

        self.assertAlmostEqual(after(PRONE_TO_ILLNESS_ID, True), 50.0 - 2.016 * 0.5)
        self.assertAlmostEqual(after(RESILIENT_ID, True), 50.0 - 2.016 * 1.5)
        self.assertAlmostEqual(after(PRONE_TO_ILLNESS_ID, False), 50.0 + 2.016 * 1.2)
        self.assertAlmostEqual(after(RESILIENT_ID, False), 50.0 + 2.016 * 0.8)
        self.assertAlmostEqual(after(OUTDOORSMAN_ID, True), 50.0 - 2.016)

    def test_a_cold_never_touches_the_sickness_stat(self):
        player = cold_player(50.0)
        run(player, 30, indoors=False)
        self.assertEqual(player.stats.get(CharacterStat.SICKNESS), 0.0)

    def test_without_a_wearer_the_driver_does_nothing(self):
        player = cold_player(50.0)
        ColdDriver().apply(player.stats, 1.0, StatContext())
        self.assertEqual(player.stats.get(CharacterStat.COLD_STRENGTH), 50.0)


class SneezeTests(unittest.TestCase):
    """body-temperature: Sneezes and coughs."""

    def test_no_sneeze_below_has_a_cold_level_2(self):
        player = cold_player(40.0)
        facts = run(player, 5, indoors=True)
        self.assertEqual(facts, [])
        player = cold_player(45.0)
        player.stats.set(CharacterStat.COLD_STRENGTH, 41.0)
        facts = run(player, 1, indoors=False)
        self.assertEqual(facts, ["Orton sneezes."])

    def test_the_timer_does_not_move_below_level_2(self):
        player = cold_player(30.0)
        player.thermal.sneeze_timer = 300.0
        run(player, 3, indoors=False)
        self.assertEqual(player.thermal.sneeze_timer, 300.0)

    def test_level_2_always_sneezes(self):
        for seed in range(50):
            sneeze, _ = roll_sneeze(2, random.Random(seed))
            self.assertTrue(sneeze)

    def test_levels_3_and_4_sneeze_about_49_in_100(self):
        for level in (3, 4):
            rng = random.Random(7)
            sneezes = sum(roll_sneeze(level, rng)[0] for _ in range(20000))
            self.assertAlmostEqual(sneezes / 20000, 0.49, delta=0.02)

    def test_the_coin_is_a_roll_above_50(self):
        class Fixed(random.Random):
            def __init__(self, values):
                super().__init__(0)
                self.values = list(values)

            def randrange(self, start, stop=None, step=1):
                return self.values.pop(0)

        self.assertTrue(roll_sneeze(3, Fixed([51, 0]))[0])
        self.assertFalse(roll_sneeze(3, Fixed([50, 0]))[0])
        self.assertTrue(roll_sneeze(4, Fixed([99, 0]))[0])
        self.assertFalse(roll_sneeze(4, Fixed([0, 0]))[0])

    def test_timer_ranges_by_level(self):
        for level, (low, high) in {2: (600, 800), 3: (300, 600), 4: (200, 300)}.items():
            draws = [roll_sneeze(level, random.Random(seed))[1] for seed in range(300)]
            self.assertGreaterEqual(min(draws), low)
            self.assertLess(max(draws), high)
            self.assertGreater(max(draws) - min(draws), (high - low) * 0.8)

    def test_the_timer_is_min_plus_the_draw(self):
        class Fixed(random.Random):
            def randrange(self, start, stop=None, step=1):
                return 5 if stop is None else 0

        self.assertEqual(roll_sneeze(2, Fixed(0))[1], 605)
        self.assertEqual(roll_sneeze(3, Fixed(0))[1], 305)
        self.assertEqual(roll_sneeze(4, Fixed(0))[1], 205)

    def test_a_trigger_is_a_fact_and_the_timer_is_reset_less_the_frames_left(self):
        player = cold_player(50.0)
        player.thermal.sneeze_timer = 12.5
        facts = run(player, 1, indoors=False)
        self.assertEqual(facts, ["Orton sneezes."])
        _, timer = roll_sneeze(2, random.Random(1))
        self.assertAlmostEqual(player.thermal.sneeze_timer, timer - 100.0)

    def test_the_timer_drops_112_5_frames_per_minute(self):
        player = cold_player(50.0)
        player.thermal.sneeze_timer = 300.0
        run(player, 2, indoors=False)
        self.assertAlmostEqual(player.thermal.sneeze_timer, 300.0 - 225.0)

    def test_a_cough_has_its_own_fact(self):
        player = cold_player(65.0)
        found = set()
        for seed in range(30):
            player.thermal.sneeze_timer = 0.0
            found.update(run(player, 1, rng=random.Random(seed), indoors=False))
        self.assertTrue({"Orton sneezes.", "Orton coughs."} <= found)

    def test_active_frames_are_set_to_25_less_the_frames_left(self):
        player = cold_player(50.0)
        player.thermal.sneeze_timer = 100.0
        run(player, 1, indoors=False)
        self.assertEqual(player.thermal.sneeze_active, 12.5)
        player.thermal.sneeze_active = 0.0
        player.thermal.sneeze_timer = 107.5
        run(player, 1, indoors=False)
        self.assertEqual(player.thermal.sneeze_active, 20.0)

    def test_the_active_counter_runs_down_each_minute(self):
        player = cold_player(30.0)
        player.thermal.sneeze_active = 200.0
        run(player, 1, indoors=False)
        self.assertEqual(player.thermal.sneeze_active, 87.5)

    def test_noise_constants(self):
        from data.body.thermal import COUGH_NOISE, SNEEZE_NOISE, SNEEZE_OR_COUGH_ACTIVE_FRAMES

        self.assertEqual(SNEEZE_NOISE, (20, 25))
        self.assertEqual(COUGH_NOISE, (35, 40))
        self.assertEqual(SNEEZE_OR_COUGH_ACTIVE_FRAMES, 25)

    def test_each_trigger_is_reported_once_across_chunks(self):
        from unittest import mock

        from managers.body import cold

        player = cold_player(50.0)
        engine = StatsEngine([ColdDriver(random.Random(3))])
        with mock.patch.object(cold, "roll_sneeze", wraps=cold.roll_sneeze) as rolled:
            facts = engine.advance(player, 25, StatContext(indoors=False))
        reports = [f for f in facts if f in ("Orton sneezes.", "Orton coughs.")]
        self.assertEqual(len(reports), rolled.call_count)
        self.assertGreaterEqual(rolled.call_count, 3)


if __name__ == "__main__":
    unittest.main()
