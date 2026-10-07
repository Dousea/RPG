"""Spec 12, The body: parts, overall health and the two helpers that move it."""

import random
import unittest

from data.body.health import PARTS
from managers.body.health import (
    action_time_multiplier,
    add_general,
    land_wound,
    limp_factor,
    limp_value,
    next_pain,
    pain_target,
    part_pain,
    reduce_general,
)
from modules.body.parts import BodyPart, PartState, overall_health
from modules.body.stats import CharacterStat
from modules.entity.player import PlayerEntity


def make_player() -> PlayerEntity:
    return PlayerEntity(name="Orton", current_location_id="zone_home")


class PartTableTests(unittest.TestCase):
    """Spec 12, The body."""

    def test_seventeen_parts_with_the_specs_weights_bleeding_and_pain(self):
        expected = {
            BodyPart.HAND_L: (0.1, 0.2, 0.5),
            BodyPart.HAND_R: (0.1, 0.2, 0.5),
            BodyPart.FOREARM_L: (0.2, 0.3, 0.6),
            BodyPart.FOREARM_R: (0.2, 0.3, 0.6),
            BodyPart.UPPERARM_L: (0.3, 0.4, 0.6),
            BodyPart.UPPERARM_R: (0.3, 0.4, 0.6),
            BodyPart.TORSO_UPPER: (0.35, 0.5, 0.7),
            BodyPart.TORSO_LOWER: (0.4, 0.9, 0.78),
            BodyPart.HEAD: (0.6, 1.0, 0.8),
            BodyPart.NECK: (0.7, 1.5, 0.8),
            BodyPart.GROIN: (0.4, 0.5, 0.7),
            BodyPart.UPPERLEG_L: (0.3, 0.4, 0.7),
            BodyPart.UPPERLEG_R: (0.3, 0.4, 0.7),
            BodyPart.LOWERLEG_L: (0.2, 0.3, 0.6),
            BodyPart.LOWERLEG_R: (0.2, 0.3, 0.6),
            BodyPart.FOOT_L: (0.2, 0.2, 0.5),
            BodyPart.FOOT_R: (0.2, 0.2, 0.5),
        }
        self.assertEqual(len(PARTS), 17)
        for part, (weight, bleeding, pain) in expected.items():
            row = PARTS[part]
            self.assertEqual((row.weight, row.bleeding, row.pain), (weight, bleeding, pain), part)

    def test_a_fresh_player_has_every_part_whole(self):
        player = make_player()
        self.assertEqual(set(player.body), set(BodyPart))
        self.assertTrue(all(state.health == 100 for state in player.body.values()))
        self.assertEqual(player.hit_points, 100)


class OverallHealthTests(unittest.TestCase):
    """Spec 12, Overall health."""

    def test_ten_damage_on_a_hand_costs_one_health(self):
        player = make_player()
        player.body[BodyPart.HAND_L].health = 90
        self.assertAlmostEqual(overall_health(player.body), 99.0)

    def test_ten_damage_on_the_neck_costs_seven_health(self):
        player = make_player()
        player.body[BodyPart.NECK].health = 90
        self.assertAlmostEqual(overall_health(player.body), 93.0)

    def test_damage_is_capped_at_one_hundred(self):
        player = make_player()
        for state in player.body.values():
            state.health = 0
        self.assertEqual(overall_health(player.body), 0)

    def test_hit_points_is_a_read_only_view_of_the_derived_health(self):
        player = make_player()
        player.body[BodyPart.NECK].health = 0
        self.assertEqual(player.hit_points, 30)
        with self.assertRaises(AttributeError):
            player.hit_points = 5  # type: ignore[misc]

    def test_a_body_with_a_sliver_of_health_is_not_dead(self):
        player = make_player()
        player.body[BodyPart.HEAD].health = 0
        player.body[BodyPart.NECK].health = 43
        self.assertAlmostEqual(player.health, 0.1)
        self.assertEqual(player.hit_points, 1)


class ReduceGeneralTests(unittest.TestCase):
    """Spec 12, Overall health: reduce_general."""

    def test_on_a_full_body_it_lowers_health_by_exactly_the_amount(self):
        player = make_player()
        reduce_general(player, 20)
        self.assertAlmostEqual(overall_health(player.body), 80.0)

    def test_each_part_loses_amount_over_seventeen_over_its_weight(self):
        player = make_player()
        reduce_general(player, 17)
        self.assertAlmostEqual(player.body[BodyPart.NECK].health, 100 - 1 / 0.7)
        self.assertAlmostEqual(player.body[BodyPart.HAND_L].health, 90.0)

    def test_a_part_at_zero_absorbs_nothing(self):
        player = make_player()
        player.body[BodyPart.NECK].health = 0
        reduce_general(player, 10)
        self.assertGreater(overall_health(player.body), 100 - 0.7 * 100 - 10)
        self.assertEqual(player.body[BodyPart.NECK].health, 0)

    def test_parts_never_go_below_zero(self):
        player = make_player()
        reduce_general(player, 5000)
        self.assertTrue(all(state.health == 0 for state in player.body.values()))

    def test_a_sleeper_at_ten_health_or_less_is_woken_first(self):
        player = make_player()
        player.asleep = True
        for state in player.body.values():
            state.health = 100 - 90 / 5.05
        reduce_general(player, 1)
        self.assertFalse(player.asleep)

    def test_a_sleeper_above_ten_health_stays_asleep(self):
        player = make_player()
        player.asleep = True
        reduce_general(player, 20)
        self.assertTrue(player.asleep)


class AddGeneralTests(unittest.TestCase):
    """Spec 12, Overall health: add_general."""

    def test_it_splits_evenly_over_the_parts_below_one_hundred(self):
        player = make_player()
        player.body[BodyPart.HEAD].health = 50
        player.body[BodyPart.NECK].health = 60
        add_general(player, 10)
        self.assertAlmostEqual(player.body[BodyPart.HEAD].health, 55)
        self.assertAlmostEqual(player.body[BodyPart.NECK].health, 65)
        self.assertEqual(player.body[BodyPart.HAND_L].health, 100)

    def test_each_part_is_capped_at_one_hundred(self):
        player = make_player()
        player.body[BodyPart.HEAD].health = 99
        player.body[BodyPart.NECK].health = 10
        add_general(player, 20)
        self.assertEqual(player.body[BodyPart.HEAD].health, 100)
        self.assertAlmostEqual(player.body[BodyPart.NECK].health, 20)

    def test_a_whole_body_gains_nothing(self):
        player = make_player()
        add_general(player, 20)
        self.assertEqual(overall_health(player.body), 100)


class PartStateTests(unittest.TestCase):
    """Spec 12, The body: bleeding and injured."""

    def test_a_part_bleeds_only_while_unbandaged(self):
        state = PartState(bleeding_time=3.0)
        self.assertTrue(state.bleeding)
        state.bandage = "item_bandage"
        self.assertFalse(state.bleeding)

    def test_injured_is_any_open_wound_time_or_bleeding(self):
        self.assertFalse(PartState().injured)
        self.assertTrue(PartState(scratch_time=1).injured)
        self.assertTrue(PartState(cut_time=1).injured)
        self.assertTrue(PartState(bite_time=1).injured)
        self.assertTrue(PartState(bleeding_time=1).injured)


class WoundLandingTests(unittest.TestCase):
    """Spec 12, Wounds."""

    def land(self, kind, part, *, traits=(), seed=0, damage=5.0, zombie_infected=False):
        player = make_player()
        player.traits = list(traits)
        land_wound(player, kind, part, damage, zombie_infected, random.Random(seed))
        return player, player.body[part]

    def test_the_damage_goes_into_the_part_and_is_clamped_at_zero(self):
        player, state = self.land("scratch", BodyPart.HAND_L, damage=10.0)
        self.assertEqual(state.health, 90.0)
        self.assertAlmostEqual(player.health, 99.0)
        _, state = self.land("bite", BodyPart.HAND_L, damage=500.0)
        self.assertEqual(state.health, 0.0)

    def test_scratch_time_is_between_7_and_15(self):
        for seed in range(200):
            _, state = self.land("scratch", BodyPart.HAND_L, seed=seed)
            self.assertTrue(7 <= state.scratch_time <= 15, state.scratch_time)

    def test_laceration_time_is_between_10_and_20(self):
        for seed in range(200):
            _, state = self.land("laceration", BodyPart.HAND_L, seed=seed)
            self.assertTrue(10 <= state.cut_time <= 20, state.cut_time)

    def test_bite_time_is_between_50_and_80(self):
        for seed in range(200):
            _, state = self.land("bite", BodyPart.HAND_L, seed=seed)
            self.assertTrue(50 <= state.bite_time <= 80, state.bite_time)

    def test_fast_healer_shortens_every_wound_time(self):
        for seed in range(200):
            _, scratch = self.land("scratch", BodyPart.HAND_L, traits=["fasthealer"], seed=seed)
            _, cut = self.land("laceration", BodyPart.HAND_L, traits=["fasthealer"], seed=seed)
            _, bite = self.land("bite", BodyPart.HAND_L, traits=["fasthealer"], seed=seed)
            self.assertTrue(4 <= scratch.scratch_time <= 10)
            self.assertTrue(5 <= cut.cut_time <= 10)
            self.assertTrue(30 <= bite.bite_time <= 50)

    def test_slow_healer_lengthens_every_wound_time(self):
        for seed in range(200):
            _, scratch = self.land("scratch", BodyPart.HAND_L, traits=["slowhealer"], seed=seed)
            _, cut = self.land("laceration", BodyPart.HAND_L, traits=["slowhealer"], seed=seed)
            _, bite = self.land("bite", BodyPart.HAND_L, traits=["slowhealer"], seed=seed)
            self.assertTrue(15 <= scratch.scratch_time <= 25)
            self.assertTrue(20 <= cut.cut_time <= 30)
            self.assertTrue(80 <= bite.bite_time <= 150)

    def test_a_forearm_laceration_bleeds_for_2_1_to_6_units(self):
        for seed in range(300):
            _, state = self.land("laceration", BodyPart.FOREARM_L, seed=seed)
            self.assertTrue(2.1 <= state.bleeding_time <= 6.0, state.bleeding_time)

    def test_a_neck_bite_bleeds_for_11_to_22_units(self):
        for seed in range(300):
            _, state = self.land("bite", BodyPart.NECK, seed=seed)
            self.assertTrue(11.25 <= state.bleeding_time <= 22.5, state.bleeding_time)

    def test_a_scratch_alone_sets_no_bleeding(self):
        for seed in range(50):
            _, state = self.land("scratch", BodyPart.FOREARM_L, seed=seed)
            self.assertEqual(state.bleeding_time, 0.0)

    def test_a_laceration_over_an_open_scratch_bleeds_from_both(self):
        player = make_player()
        state = player.body[BodyPart.TORSO_LOWER]
        land_wound(player, "scratch", BodyPart.TORSO_LOWER, 1.0, False, random.Random(1))
        scratch = state.scratch_time
        land_wound(player, "laceration", BodyPart.TORSO_LOWER, 1.0, False, random.Random(2))
        low = (0.3 * scratch + 0.7 * state.cut_time) * 0.9
        high = (0.6 * scratch + 1.0 * state.cut_time) * 0.9
        self.assertTrue(low <= state.bleeding_time <= high)

    def test_a_new_wound_takes_the_bandage_off(self):
        player = make_player()
        state = player.body[BodyPart.HAND_L]
        state.bandage = "item_bandage"
        state.bandage_life = 4.0
        state.bandage_alcoholic = True
        land_wound(player, "scratch", BodyPart.HAND_L, 1.0, False, random.Random(1))
        self.assertIsNone(state.bandage)
        self.assertEqual(state.bandage_life, 0.0)
        self.assertFalse(state.bandage_alcoholic)

    def test_a_second_wound_of_the_same_kind_replaces_the_first_time(self):
        player = make_player()
        land_wound(player, "scratch", BodyPart.HAND_L, 1.0, False, random.Random(1))
        first = player.body[BodyPart.HAND_L].scratch_time
        land_wound(player, "scratch", BodyPart.HAND_L, 1.0, False, random.Random(2))
        self.assertNotEqual(player.body[BodyPart.HAND_L].scratch_time, first)
        self.assertTrue(7 <= player.body[BodyPart.HAND_L].scratch_time <= 15)

    def test_a_bite_infects_the_wound_and_a_scratch_does_not(self):
        _, bite = self.land("bite", BodyPart.HAND_L)
        _, scratch = self.land("scratch", BodyPart.HAND_L)
        self.assertTrue(bite.infected_wound)
        self.assertFalse(scratch.infected_wound)

    def test_a_zombie_infection_wound_marks_the_part(self):
        _, state = self.land("scratch", BodyPart.HAND_L, zombie_infected=True)
        self.assertTrue(state.zombie_infected)
        _, state = self.land("scratch", BodyPart.HAND_L, zombie_infected=False)
        self.assertFalse(state.zombie_infected)


class PartPainTests(unittest.TestCase):
    """Spec 12, Pain from each part."""

    def test_a_bandaged_bite_is_thirty_over_one_and_a_half(self):
        state = PartState(bite_time=60.0, bandage="item_bandage")
        self.assertAlmostEqual(part_pain(state), 20.0)

    def test_an_unbandaged_bite_is_fifty(self):
        self.assertAlmostEqual(part_pain(PartState(bite_time=60.0)), 50.0)

    def test_a_bandaged_forearm_bite_gives_pain_twelve_and_unbandaged_thirty(self):
        player = make_player()
        player.body[BodyPart.FOREARM_L] = PartState(bite_time=60.0, bandage="item_bandage")
        self.assertAlmostEqual(pain_target(player), 12.0)
        player.body[BodyPart.FOREARM_L] = PartState(bite_time=60.0)
        self.assertAlmostEqual(pain_target(player), 30.0)

    def test_a_scratch_and_a_cut_scale_with_their_time(self):
        self.assertAlmostEqual(part_pain(PartState(scratch_time=10.0)), 17.0)
        self.assertAlmostEqual(part_pain(PartState(cut_time=10.0)), 25.0)

    def test_a_bandage_divides_the_wound_pain_by_one_and_a_half(self):
        state = PartState(scratch_time=15.0, cut_time=6.0, bandage="item_bandage")
        self.assertAlmostEqual(part_pain(state), (1.7 * 15 + 2.5 * 6) / 1.5)

    def test_wound_infection_adds_after_the_bandage_division(self):
        state = PartState(scratch_time=15.0, bandage="item_bandage", wound_infection=3.0)
        self.assertAlmostEqual(part_pain(state), 1.7 * 15 / 1.5 + 3.0)

    def test_a_negative_wound_infection_adds_nothing(self):
        self.assertAlmostEqual(part_pain(PartState(wound_infection=-1.5)), 0.0)

    def test_extra_pain_and_stiffness_add_on_top(self):
        state = PartState(extra_pain=10.0, stiffness=7.0)
        self.assertAlmostEqual(part_pain(state), 10.0 + 7.0 / 3.5)

    def test_the_target_weights_each_part_by_its_pain_multiplier(self):
        player = make_player()
        player.body[BodyPart.HAND_L].extra_pain = 10.0
        player.body[BodyPart.NECK].extra_pain = 10.0
        self.assertAlmostEqual(pain_target(player), 10 * 0.5 + 10 * 0.8)


class PainStatTests(unittest.TestCase):
    """Spec 12, The pain stat."""

    def test_a_rising_target_closes_about_a_fifth_of_the_gap_in_a_minute(self):
        self.assertAlmostEqual(next_pain(0.0, 100.0), 100 - 100 * 0.7985)
        self.assertAlmostEqual(next_pain(40.0, 100.0), 100 - 60 * 0.7985)

    def test_a_lower_target_applies_at_once(self):
        self.assertEqual(next_pain(80.0, 30.0), 30.0)
        self.assertEqual(next_pain(30.0, 30.0), 30.0)

    def test_pain_reaches_most_of_its_target_in_about_four_minutes(self):
        pain = 0.0
        for _ in range(4):
            pain = next_pain(pain, 50.0)
        self.assertGreater(pain, 50 * 0.58)


class LimpTests(unittest.TestCase):
    """Spec 12, The limp."""

    def test_a_whole_body_does_not_limp(self):
        player = make_player()
        self.assertEqual(limp_value(player), 0.0)
        self.assertEqual(limp_factor(player), 1.0)

    def test_a_shin_laceration_is_about_point_two_seven_and_slows_to_point_eight_two(self):
        player = make_player()
        player.body[BodyPart.LOWERLEG_L].cut_time = 15.0
        self.assertAlmostEqual(limp_value(player), 15 / 55)
        self.assertAlmostEqual(limp_factor(player), 1 - (15 / 55) / 1.5)
        self.assertAlmostEqual(limp_factor(player), 0.82, delta=0.005)

    def test_a_bitten_thigh_drops_the_pace_to_a_quarter(self):
        player = make_player()
        player.body[BodyPart.UPPERLEG_L].bite_time = 65.0
        self.assertAlmostEqual(limp_value(player), 65 / 20)
        self.assertEqual(limp_factor(player), 0.25)

    def test_a_scratch_counts_only_above_two_units(self):
        player = make_player()
        player.body[BodyPart.LOWERLEG_L].scratch_time = 2.0
        self.assertEqual(limp_value(player), 0.0)
        player.body[BodyPart.LOWERLEG_L].scratch_time = 9.0
        self.assertAlmostEqual(limp_value(player), 9 / 45)

    def test_a_cut_counts_only_above_five_units(self):
        player = make_player()
        player.body[BodyPart.LOWERLEG_L].cut_time = 5.0
        self.assertEqual(limp_value(player), 0.0)

    def test_the_feet_use_their_own_divisors(self):
        player = make_player()
        player.body[BodyPart.FOOT_L].scratch_time = 7.0
        player.body[BodyPart.FOOT_R].cut_time = 9.0
        self.assertAlmostEqual(limp_value(player), 7 / 35 + 9 / 45)

    def test_a_bitten_foot_adds_one_and_a_bandage_takes_it_to_point_seven(self):
        player = make_player()
        player.body[BodyPart.FOOT_L].bite_time = 40.0
        self.assertAlmostEqual(limp_value(player), 1 + 40 / 20)
        player.body[BodyPart.FOOT_L].bandage = "item_bandage"
        self.assertAlmostEqual(limp_value(player), 0.7 + (40 / 20) / 2)

    def test_a_bandage_halves_the_wound_term(self):
        player = make_player()
        player.body[BodyPart.LOWERLEG_L].cut_time = 15.0
        player.body[BodyPart.LOWERLEG_L].bandage = "item_bandage"
        self.assertAlmostEqual(limp_value(player), 15 / 55 / 2)

    def test_a_small_value_under_the_threshold_does_not_slow_the_player(self):
        player = make_player()
        player.body[BodyPart.LOWERLEG_L].scratch_time = 4.0
        self.assertLess(limp_value(player), 0.1)
        self.assertEqual(limp_factor(player), 1.0)

    def test_parts_outside_the_legs_do_not_limp(self):
        player = make_player()
        player.body[BodyPart.FOREARM_L].bite_time = 65.0
        player.body[BodyPart.TORSO_LOWER].cut_time = 65.0
        self.assertEqual(limp_value(player), 0.0)


class ActionTimeMultiplierTests(unittest.TestCase):
    """Spec 12, What pain does."""

    def test_a_calm_sober_pain_free_player_has_no_slowdown(self):
        self.assertEqual(action_time_multiplier(make_player()), 1.0)

    def test_unhappy_two_drunk_one_and_thirty_hand_pain(self):
        player = make_player()
        player.stats.set(CharacterStat.UNHAPPINESS, 50)
        player.stats.set(CharacterStat.INTOXICATION, 15)
        player.body[BodyPart.HAND_L].extra_pain = 30.0
        self.assertAlmostEqual(action_time_multiplier(player), 1.5 * 1.25 * 1.1)

    def test_hand_pain_sums_both_hands_and_forearms_without_the_pain_multiplier(self):
        player = make_player()
        player.body[BodyPart.HAND_L].extra_pain = 60.0
        player.body[BodyPart.FOREARM_R].extra_pain = 30.0
        player.body[BodyPart.UPPERARM_L].extra_pain = 300.0
        self.assertAlmostEqual(action_time_multiplier(player), 1 + 90 / 300)

    def test_warm_skin_adds_nothing_and_cold_skin_adds_under_a_percent(self):
        player = make_player()
        warm = action_time_multiplier(player)
        for part in (
            BodyPart.HAND_L,
            BodyPart.HAND_R,
            BodyPart.FOREARM_L,
            BodyPart.FOREARM_R,
            BodyPart.UPPERARM_L,
            BodyPart.UPPERARM_R,
        ):
            player.thermal.skin[part] = 20.0
        cold = action_time_multiplier(player)
        self.assertEqual(warm, 1.0)
        self.assertGreater(cold, 1.0)
        self.assertLess(cold, 1.007)


if __name__ == "__main__":
    unittest.main()
