"""Spec 08, Exercise: reps, regularity, stiffness, refusals and the starting regularity."""

import random
import unittest
from unittest import mock

from data import time_costs as time_cost_k
from data.character.exercises import EXERCISES
from data.items import ITEMS
from managers.character.exercise import (
    ExerciseEngine,
    rep_speed,
    reps_per_minute,
    starting_regularity,
)
from managers.character.skills import SkillEngine
from managers.game import GameManager
from managers.validator import Accepted, ActionValidator, Rejected
from modules.action.parser import parse_action_line
from modules.action.types import ExerciseAction
from modules.body.parts import BodyPart
from modules.body.stats import CharacterStat
from modules.character.skills import SkillState
from modules.entity.item import ItemEntity
from modules.entity.player import PlayerEntity
from modules.resolution import ExercisePlan, TimeSpan
from tests.support import simulate


def stiffness_of(player) -> dict[BodyPart, float]:
    return {part: state.stiffness for part, state in player.body.items() if state.stiffness}


def make_player(**kwargs) -> PlayerEntity:
    player = PlayerEntity(name="Orton", current_location_id="zone_home", **kwargs)
    SkillEngine().set_level(player, "fitness", 5)
    SkillEngine().set_level(player, "strength", 5)
    return player


class TimingTests(unittest.TestCase):
    """Spec 08, Timing."""

    def test_speed_at_fitness_five_is_a_tenth_below_one_over_one_point_one(self):
        self.assertAlmostEqual(rep_speed(5, 0), 0.9090909, places=6)

    def test_speed_below_point_eight_five_becomes_one(self):
        self.assertEqual(rep_speed(0, 0), 1.0)
        self.assertEqual(rep_speed(5, 2), 1.0)

    def test_speed_at_or_above_point_eight_five_is_kept(self):
        self.assertAlmostEqual(rep_speed(5, 1), 0.8590909, places=6)

    def test_speed_is_capped_at_one_and_a_half(self):
        self.assertEqual(rep_speed(10, 0), 1.5)

    def test_reps_per_minute_is_3_75_times_speed_over_the_period(self):
        self.assertAlmostEqual(reps_per_minute(EXERCISES["squats"], 5, 0), 1.1363636, places=6)
        self.assertAlmostEqual(reps_per_minute(EXERCISES["push_ups"], 5, 0), 2.6223776, places=6)
        self.assertAlmostEqual(reps_per_minute(EXERCISES["squats"], 0, 0), 1.25, places=6)
        self.assertAlmostEqual(reps_per_minute(EXERCISES["dumbbell_press"], 10, 0), 3.75, places=6)


class HeavyLoadRepTests(unittest.TestCase):
    """Spec 25, What Heavy Load does: a rep costs x(1 + level / 3) endurance, integer division."""

    def cost(self, *item_ids: str) -> float:
        player = make_player()
        player.skills["strength"] = SkillState(level=0)
        player.inventory.extend(ItemEntity(item=ITEMS[item_id]) for item_id in item_ids)
        before = player.stats.get(CharacterStat.ENDURANCE)
        ExerciseEngine(SkillEngine()).do_rep(player, EXERCISES["squats"], 0)
        return before - player.stats.get(CharacterStat.ENDURANCE)

    def test_levels_0_to_2_cost_the_same_and_3_and_4_cost_double(self):
        base = self.cost()
        self.assertGreater(base, 0)
        self.assertAlmostEqual(self.cost("item_barbell", "item_plank"), base * 2)  # level 3
        self.assertAlmostEqual(self.cost("item_barbell", "item_dumbbell"), base * 2)  # level 4
        self.assertAlmostEqual(self.cost("item_barbell", "item_hammer"), base)  # level 2 (7.5 / 6)


class EachRepTests(unittest.TestCase):
    """Spec 08, Each rep."""

    def setUp(self):
        self.engine = ExerciseEngine(SkillEngine())

    def rep(self, player, exercise_id, now=0):
        return self.engine.do_rep(player, EXERCISES[exercise_id], now)

    def test_regularity_gains_point_oh_eight_at_fitness_five(self):
        player = make_player()
        self.rep(player, "squats")
        self.assertAlmostEqual(player.exercise.regularity["squats"], 0.08, places=6)

    def test_regularity_gain_shrinks_with_fitness(self):
        player = make_player()
        SkillEngine().set_level(player, "fitness", 10)
        self.rep(player, "squats")
        # 0.08 x ln 5 / ln 6
        self.assertAlmostEqual(player.exercise.regularity["squats"], 0.0718596, places=6)

    def test_regularity_is_capped_at_100(self):
        player = make_player()
        player.exercise.regularity["squats"] = 99.99
        self.rep(player, "squats")
        self.assertEqual(player.exercise.regularity["squats"], 100.0)

    def test_endurance_cost_of_a_light_rep(self):
        player = make_player()
        self.rep(player, "squats")
        self.assertAlmostEqual(player.stats.get(CharacterStat.ENDURANCE), 1 - 0.0149246, places=6)

    def test_a_heavy_rep_costs_thirty_percent_more_endurance(self):
        player = make_player()
        self.rep(player, "burpees")
        self.assertAlmostEqual(
            player.stats.get(CharacterStat.ENDURANCE), 1 - 0.0149246 * 1.3, places=5
        )

    def test_stiffness_is_added_to_the_trained_region_and_a_timer_starts(self):
        player = make_player()
        self.rep(player, "squats")
        self.assertAlmostEqual(player.exercise.future_stiffness["legs"], 0.3527059, places=6)
        self.assertEqual(player.exercise.region_timers["legs"], 72)
        self.assertNotIn("arms", player.exercise.future_stiffness)

    def test_a_running_timer_is_left_alone(self):
        player = make_player()
        player.exercise.region_timers["legs"] = 30
        self.rep(player, "squats")
        self.assertEqual(player.exercise.region_timers["legs"], 30)

    def test_a_finished_timer_starts_again(self):
        player = make_player()
        player.exercise.region_timers["legs"] = 0
        self.rep(player, "squats")
        self.assertEqual(player.exercise.region_timers["legs"], 72)

    def test_heavy_stiffness_is_thirty_percent_higher_in_each_region(self):
        player = make_player()
        self.rep(player, "burpees")
        expected = 0.5 * (120 - 0.08) / 170 * 1.3
        for region in ("legs", "arms", "chest"):
            self.assertAlmostEqual(player.exercise.future_stiffness[region], expected, places=4)

    def test_very_tired_doubles_stiffness_by_integer_division(self):
        for fatigue, factor in ((0.65, 1), (0.75, 1), (0.85, 2), (0.95, 2)):
            with self.subTest(fatigue=fatigue):
                player = make_player()
                player.stats.set(CharacterStat.FATIGUE, fatigue)
                self.rep(player, "squats")
                self.assertAlmostEqual(
                    player.exercise.future_stiffness["legs"], 0.3527059 * factor, places=6
                )

    def test_stiffness_is_capped_at_150(self):
        player = make_player()
        player.exercise.future_stiffness["legs"] = 149.9
        self.rep(player, "squats")
        self.assertEqual(player.exercise.future_stiffness["legs"], 150.0)

    def test_squats_give_four_fitness_xp(self):
        player = make_player()
        self.rep(player, "squats")
        self.assertEqual(player.skills["fitness"].xp - 37500, 4)
        self.assertEqual(player.skills["strength"].xp, 37500)

    def test_push_ups_give_four_strength_per_arms_and_two_per_chest(self):
        player = make_player()
        self.rep(player, "push_ups")
        self.assertEqual(player.skills["strength"].xp - 37500, 6)
        self.assertEqual(player.skills["fitness"].xp, 37500)

    def test_sit_ups_give_two_fitness_for_abs(self):
        player = make_player()
        self.rep(player, "sit_ups")
        self.assertEqual(player.skills["fitness"].xp - 37500, 2)

    def test_burpees_scale_each_award_by_the_xp_mod(self):
        player = make_player()
        self.rep(player, "burpees")
        self.assertAlmostEqual(player.skills["fitness"].xp - 37500, 3.2)
        self.assertAlmostEqual(player.skills["strength"].xp - 37500, 4.8)

    def test_dumbbell_press_gives_one_point_eight_times_four_strength(self):
        player = make_player()
        self.rep(player, "dumbbell_press")
        self.assertAlmostEqual(player.skills["strength"].xp - 37500, 7.2)

    def test_the_high_level_bonus_is_always_times_one(self):
        player = make_player()
        SkillEngine().set_level(player, "fitness", 9)
        self.rep(player, "squats")
        self.assertEqual(player.skills["fitness"].xp, 337500 + 4)

    def test_the_rep_records_when_the_exercise_was_done(self):
        player = make_player()
        self.rep(player, "squats", now=95)
        self.assertEqual(player.exercise.last_done_minute["squats"], 95)


def game_with(*item_ids: str) -> GameManager:
    gm = GameManager()
    for item_id in item_ids:
        gm.player.inventory.append(ItemEntity(item=ITEMS[item_id]))
    return gm


class ExerciseVerbTests(unittest.TestCase):
    """Spec 08, Exercise: the verb and its minutes."""

    def test_the_parser_reads_a_name_and_minutes(self):
        self.assertEqual(
            parse_action_line("EXERCISE push-ups 30"),
            ExerciseAction(exercise_name="push-ups", minutes=30),
        )
        self.assertEqual(
            parse_action_line("EXERCISE Barbell curls 20m"),
            ExerciseAction(exercise_name="Barbell curls", minutes=20),
        )
        self.assertEqual(
            parse_action_line("EXERCISE squats"),
            ExerciseAction(exercise_name="squats", minutes=None),
        )

    def test_the_parser_needs_an_exercise(self):
        self.assertNotIsInstance(parse_action_line("EXERCISE"), ExerciseAction)

    def validate(self, gm: GameManager, name: str, minutes: int | None = None):
        return ActionValidator(gm).validate(ExerciseAction(exercise_name=name, minutes=minutes))

    def test_the_default_is_ten_minutes(self):
        result = self.validate(game_with(), "Squats")
        assert isinstance(result, Accepted)
        self.assertEqual(result.resolved, ExercisePlan(EXERCISES["squats"], 10))

    def test_minutes_run_from_10_to_60_in_steps_of_10(self):
        for minutes in (10, 20, 30, 40, 50, 60):
            self.assertIsInstance(self.validate(game_with(), "squats", minutes), Accepted)
        for minutes in (0, 5, 15, 70, 120):
            self.assertIsInstance(self.validate(game_with(), "squats", minutes), Rejected)

    def test_an_unknown_exercise_is_refused(self):
        self.assertIsInstance(self.validate(game_with(), "juggling"), Rejected)

    def test_names_match_with_hyphens_and_spaces(self):
        for name in ("push-ups", "Push ups", "push_ups"):
            result = self.validate(game_with(), name)
            assert isinstance(result, Accepted)
            self.assertEqual(result.expect(ExercisePlan).exercise.id, "push_ups")

    def test_a_barbell_exercise_needs_the_barbell(self):
        self.assertIsInstance(self.validate(game_with(), "barbell curls"), Rejected)
        self.assertIsInstance(self.validate(game_with("item_barbell"), "barbell curls"), Accepted)
        self.assertIsInstance(self.validate(game_with("item_dumbbell"), "barbell curls"), Rejected)

    def test_dumbbell_exercises_need_the_dumbbell(self):
        self.assertIsInstance(self.validate(game_with(), "dumbbell press"), Rejected)
        self.assertIsInstance(self.validate(game_with("item_dumbbell"), "biceps curls"), Accepted)

    def test_refused_above_endurance_level_two(self):
        gm = game_with()
        gm.player.stats.set(CharacterStat.ENDURANCE, 0.25)
        self.assertIsInstance(self.validate(gm, "squats"), Rejected)

    def test_allowed_at_endurance_level_two(self):
        gm = game_with()
        gm.player.stats.set(CharacterStat.ENDURANCE, 0.30)
        self.assertIsInstance(self.validate(gm, "squats"), Accepted)

    def test_a_refusal_costs_no_time(self):
        gm = game_with()
        gm.player.stats.set(CharacterStat.ENDURANCE, 0.2)
        before = gm.narrative.minutes
        facts = simulate(gm, ExerciseAction(exercise_name="squats", minutes=30))
        self.assertTrue(facts[0].startswith("Refused:"))
        self.assertEqual(gm.narrative.minutes, before)


class ExerciseRunTests(unittest.TestCase):
    """Spec 08, Stopping and refusing, and Each rep, through the simulation."""

    def run_exercise(self, gm: GameManager, name: str, minutes: int) -> list[str]:
        return simulate(gm, ExerciseAction(exercise_name=name, minutes=minutes))

    def test_a_full_session_costs_the_chosen_minutes(self):
        gm = game_with()
        before = gm.narrative.minutes
        facts = self.run_exercise(gm, "squats", 10)
        self.assertEqual(gm.narrative.minutes - before, 10)
        self.assertIn("You finish 10 minutes of squats.", facts)

    def test_reps_follow_the_rate_with_a_carried_remainder(self):
        gm = game_with()
        self.run_exercise(gm, "squats", 10)
        # 10 minutes x 1.1364 reps = 11.36 reps, so 11 whole reps at regularity 0.08 each
        self.assertAlmostEqual(gm.player.exercise.regularity["squats"], 11 * 0.08, places=4)

    def test_a_session_trains_fitness(self):
        gm = game_with()
        self.run_exercise(gm, "squats", 10)
        self.assertGreaterEqual(gm.player.skills["fitness"].xp, 37500 + 44)

    def test_the_session_is_remembered(self):
        gm = game_with()
        self.run_exercise(gm, "squats", 10)
        self.assertGreater(gm.player.exercise.last_done_minute["squats"], 0)

    def test_it_stops_early_once_endurance_goes_above_level_two(self):
        gm = game_with()
        gm.player.stats.set(CharacterStat.ENDURANCE, 0.3)
        before = gm.narrative.minutes
        facts = self.run_exercise(gm, "burpees", 60)
        spent = gm.narrative.minutes - before
        self.assertLess(spent, 60)
        self.assertGreater(spent, 0)
        self.assertEqual(facts[0], "You stop, too exhausted to go on.")
        self.assertRegex(facts[1], r"^\d+ reps in all\.$")
        self.assertLessEqual(gm.player.stats.get(CharacterStat.ENDURANCE), 0.25)

    def test_a_full_session_reports_the_reps_done(self):
        gm = game_with()
        facts = self.run_exercise(gm, "squats", 10)
        self.assertEqual(facts[:2], ["You finish 10 minutes of squats.", "11 reps in all."])

    def test_the_stats_advance_each_minute_while_exercising(self):
        gm = game_with()
        self.run_exercise(gm, "squats", 10)
        self.assertGreater(gm.player.stats.get(CharacterStat.THIRST), 0)

    def test_the_metabolic_target_is_fitness_or_fitness_heavy(self):
        from data.body.thermal import Metabolic
        from managers.simulation import SimulationCore

        core = SimulationCore(game_with())
        light = core._metabolic_target(ExerciseAction("squats", 10))  # pyright: ignore[reportPrivateUsage]
        heavy = core._metabolic_target(ExerciseAction("burpees", 10))  # pyright: ignore[reportPrivateUsage]
        self.assertEqual(light, Metabolic.FITNESS)
        self.assertEqual(heavy, Metabolic.FITNESS_HEAVY)


class OverTimeTests(unittest.TestCase):
    """Spec 08, Regularity and stiffness over time."""

    def setUp(self):
        self.engine = ExerciseEngine(SkillEngine())

    def test_stiffness_starts_draining_after_72_ticks(self):
        player = make_player()
        self.engine.do_rep(player, EXERCISES["squats"], 0)
        for _ in range(72):
            self.engine.tick(player, 0)
        self.assertEqual(player.exercise.region_timers["legs"], 0)
        self.assertEqual(stiffness_of(player), {})
        self.engine.tick(player, 0)
        self.assertAlmostEqual(player.body[BodyPart.UPPERLEG_L].stiffness, 2.5 * 0.3527059)
        self.assertEqual(player.exercise.future_stiffness.get("legs", 0), 0)

    def test_a_drain_moves_one_unit_into_every_part_of_the_region(self):
        player = make_player()
        player.exercise.future_stiffness["arms"] = 3.0
        player.exercise.region_timers["arms"] = 0
        self.engine.tick(player, 0)
        arms = (
            BodyPart.FOREARM_L,
            BodyPart.FOREARM_R,
            BodyPart.UPPERARM_L,
            BodyPart.UPPERARM_R,
        )
        self.assertEqual(set(stiffness_of(player)), set(arms))
        for part in arms:
            self.assertEqual(player.body[part].stiffness, 2.5)
        self.assertEqual(player.exercise.future_stiffness["arms"], 2.0)

    def test_the_regions_map_to_their_parts(self):
        for region, parts in (
            (
                "legs",
                {
                    BodyPart.UPPERLEG_L,
                    BodyPart.UPPERLEG_R,
                    BodyPart.LOWERLEG_L,
                    BodyPart.LOWERLEG_R,
                },
            ),
            ("chest", {BodyPart.TORSO_UPPER}),
            ("abs", {BodyPart.TORSO_LOWER}),
        ):
            player = make_player()
            player.exercise.future_stiffness[region] = 1.0
            player.exercise.region_timers[region] = 0
            self.engine.tick(player, 0)
            self.assertEqual(set(stiffness_of(player)), parts)

    def test_a_timer_still_running_holds_the_stiffness_back(self):
        player = make_player()
        player.exercise.future_stiffness["abs"] = 5.0
        player.exercise.region_timers["abs"] = 5
        self.engine.tick(player, 0)
        self.assertEqual(player.exercise.region_timers["abs"], 4)
        self.assertEqual(stiffness_of(player), {})

    def test_regularity_does_not_decay_within_24_hours(self):
        player = make_player()
        player.exercise.regularity["squats"] = 10.0
        player.exercise.last_done_minute["squats"] = 0
        self.engine.tick(player, 24 * 60 - 10)
        self.assertEqual(player.exercise.regularity["squats"], 10.0)

    def test_regularity_loses_point_oh_oh_two_per_tick_after_24_hours(self):
        player = make_player()
        player.exercise.regularity["squats"] = 10.0
        player.exercise.last_done_minute["squats"] = 0
        self.engine.tick(player, 24 * 60 + 10)
        self.assertAlmostEqual(player.exercise.regularity["squats"], 9.998)

    def test_regularity_never_goes_below_zero(self):
        player = make_player()
        player.exercise.regularity["squats"] = 0.001
        player.exercise.last_done_minute["squats"] = 0
        self.engine.tick(player, 24 * 60 + 10)
        self.assertEqual(player.exercise.regularity["squats"], 0.0)

    def test_an_exercise_never_done_keeps_its_starting_regularity(self):
        player = make_player()
        player.exercise.regularity["squats"] = 15.0
        self.engine.tick(player, 100 * 60)
        self.assertEqual(player.exercise.regularity["squats"], 15.0)


class StartingRegularityTests(unittest.TestCase):
    """Spec 08, Regularity and stiffness over time: starting regularity."""

    def test_most_occupations_start_at_zero_for_every_exercise(self):
        regularity = starting_regularity("unemployed", 123)
        self.assertEqual(set(regularity), set(EXERCISES))
        self.assertEqual(set(regularity.values()), {0.0})

    def test_ranges_by_occupation(self):
        for occupation, low, high in (
            ("fireofficer", 10, 19),
            ("fitnessinstructor", 40, 59),
            ("securityguard", 7, 11),
        ):
            for seed in range(30):
                for value in starting_regularity(occupation, seed).values():
                    self.assertTrue(low <= value <= high, (occupation, seed, value))

    def test_the_draw_is_stable_for_a_seed(self):
        self.assertEqual(
            starting_regularity("fireofficer", 77), starting_regularity("fireofficer", 77)
        )

    def test_the_draws_differ_between_seeds_and_between_exercises(self):
        draws = {
            tuple(starting_regularity("fitnessinstructor", seed).values()) for seed in range(10)
        }
        self.assertGreater(len(draws), 1)
        self.assertGreater(len(set(starting_regularity("fitnessinstructor", 5).values())), 1)

    def test_the_draw_is_one_randrange_per_exercise_in_table_order(self):
        rng = random.Random(9)
        expected = [float(rng.randrange(10, 20)) for _ in EXERCISES]
        self.assertEqual(list(starting_regularity("fireofficer", 9).values()), expected)

    def test_a_new_player_carries_the_draw_for_the_world_seed(self):
        from managers.character import creation
        from modules.character.appearance import Appearance
        from modules.character.build import CharacterBuild

        build = CharacterBuild(appearance=Appearance(forename="Sam"), occupation_id="fireofficer")
        player = creation.new_player(build, seed=7)
        self.assertEqual(player.exercise.regularity, starting_regularity("fireofficer", 7))
        self.assertTrue(all(10 <= v <= 19 for v in player.exercise.regularity.values()))

    def test_a_starting_game_uses_its_world_seed(self):
        gm = GameManager()
        self.assertEqual(
            gm.player.exercise.regularity,
            starting_regularity(gm.player.occupation_id, gm.world.seed),
        )


class ExerciseTimeCostTests(unittest.TestCase):
    """Spec 08, Exercise: the EXERCISE time cost row is the chosen or the run minutes."""

    def test_the_row_exists(self):
        self.assertIn(ExerciseAction, time_cost_k.TIME_COSTS)

    def test_the_row_gives_the_chosen_minutes(self):
        action = ExerciseAction(exercise_name="squats", minutes=30)
        self.assertEqual(
            time_cost_k.action_minutes(action, ExercisePlan(EXERCISES["squats"], 30)), 30
        )

    def test_the_row_gives_the_minutes_run_when_stopped_early(self):
        action = ExerciseAction(exercise_name="squats", minutes=60)
        self.assertEqual(time_cost_k.action_minutes(action, TimeSpan(7, False)), 7)

    def test_the_resolver_takes_its_minutes_from_the_row(self):
        gm = game_with()
        before = gm.narrative.minutes
        with mock.patch.dict(time_cost_k.TIME_COSTS, {ExerciseAction: 20}):
            simulate(gm, ExerciseAction(exercise_name="squats", minutes=10))
        self.assertEqual(gm.narrative.minutes - before, 20)


if __name__ == "__main__":
    unittest.main()
