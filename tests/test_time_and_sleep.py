"""Time costs, the clock, stats over a turn, sleep and stat deaths."""

import random
import unittest
from unittest.mock import patch

from data.items import ITEMS
from managers.game import GameManager
from managers.simulation import SimulationCore
from managers.zombies import MinuteReport
from modules.action.types import (
    AddGoalAction,
    AddRelationshipNoteAction,
    AttackAction,
    DropAction,
    Duration,
    MoveAction,
    SleepAction,
    StanceAction,
    TakeAction,
    UseItemAction,
    WaitAction,
)
from modules.entity.item import ItemEntity
from modules.stats import CharacterStat
from tests.support import make_dying, simulate


def _spent(gm: GameManager, *actions) -> int:
    before = gm.narrative.minutes
    simulate(gm, *actions)
    return gm.narrative.minutes - before


class TimeCostTests(unittest.TestCase):
    """Spec 01, Time costs."""

    def test_a_swing_costs_one_minute(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        self.assertEqual(_spent(gm, AttackAction(target_name="Emma")), 1)

    def test_take_and_drop_cost_one_minute(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_street"
        self.assertEqual(_spent(gm, TakeAction(item_name="Crowbar")), 1)
        self.assertEqual(_spent(gm, DropAction(item_name="Crowbar")), 1)

    def test_using_a_non_food_item_costs_one_minute(self):
        gm = GameManager()
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_painkillers"]))
        self.assertEqual(_spent(gm, UseItemAction(item_name="Painkillers")), 1)

    def test_eating_costs_the_default_five_minutes(self):
        gm = GameManager()
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_canned_beans"]))
        self.assertEqual(_spent(gm, UseItemAction(item_name="Canned Beans")), 5)

    def test_the_action_time_multiplier_scales_only_the_timed_verbs(self):
        def spent_with_double(gm: GameManager, action) -> int:
            core = SimulationCore(gm)
            core._action_time_multiplier = lambda: 2.0  # pyright: ignore[reportPrivateUsage]
            before = gm.narrative.minutes
            core.resolve([action])
            return gm.narrative.minutes - before

        gm = GameManager()
        gm.player.current_location_id = "zone_street"
        self.assertEqual(spent_with_double(gm, TakeAction(item_name="Crowbar")), 2)
        self.assertEqual(spent_with_double(gm, DropAction(item_name="Crowbar")), 2)
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_canned_beans"]))
        self.assertEqual(spent_with_double(gm, UseItemAction(item_name="Canned Beans")), 10)
        self.assertEqual(spent_with_double(gm, WaitAction(duration=Duration(minutes=7))), 7)
        self.assertEqual(spent_with_double(gm, MoveAction(destination="zone_building")), 10)
        gm.player.current_location_id = "zone_building"
        self.assertEqual(spent_with_double(gm, AttackAction(target_name="Emma")), 1)

    def test_a_zone_hop_costs_ten_minutes_per_hop(self):
        gm = GameManager()
        self.assertEqual(_spent(gm, MoveAction(destination="out")), 10)
        self.assertEqual(_spent(gm, MoveAction(destination="zone_street")), 10)

    def test_a_walk_over_several_hops_costs_ten_per_hop(self):
        gm = GameManager()
        self.assertEqual(_spent(gm, MoveAction(destination="zone_street")), 20)
        self.assertEqual(_spent(gm, MoveAction(destination="The Neighborhood")), 10)

    def test_a_move_within_a_zone_costs_one_minute(self):
        gm = GameManager()
        self.assertEqual(_spent(gm, MoveAction(destination="the kitchen")), 1)
        self.assertEqual(_spent(gm, MoveAction(destination="north")), 1)

    def test_a_locked_door_stop_costs_the_walk_to_it(self):
        gm = GameManager()
        simulate(gm, MoveAction(destination="out"))
        gm.player.inventory.clear()
        self.assertEqual(_spent(gm, MoveAction(destination="Your Apartment")), 1)

    def test_zero_minute_verbs_cost_nothing(self):
        gm = GameManager()
        spent = _spent(
            gm,
            AddGoalAction(horizon="short_term", goal_text="Find water"),
            AddRelationshipNoteAction(npc_name="Emma", note="kind"),
            StanceAction(sneaking=True),
        )
        self.assertEqual(spent, 0)

    def test_a_refused_action_costs_nothing(self):
        gm = GameManager()
        facts = simulate(gm, TakeAction(item_name="Unicorn"))
        self.assertTrue(facts[0].startswith("Refused:"))
        self.assertEqual(gm.narrative.minutes, 0)
        self.assertEqual(len(facts), 1)

    def test_a_none_turn_costs_one_minute(self):
        gm = GameManager()
        facts = simulate(gm)
        self.assertEqual(gm.narrative.minutes, 1)
        self.assertEqual(facts, ["About 1 minute passes."])

    def test_world_clock_follows_each_action(self):
        gm = GameManager()
        simulate(gm, WaitAction(duration=Duration(minutes=75)))
        self.assertEqual(gm.world.time, "09:15 AM")

    def test_the_turn_fact_reports_the_summed_minutes(self):
        gm = GameManager()
        facts = simulate(
            gm,
            MoveAction(destination="out"),
            WaitAction(duration=Duration(minutes=30)),
        )
        self.assertEqual(gm.narrative.minutes, 40)
        self.assertEqual(facts[-1], "About 40 minutes pass.")
        self.assertEqual(len(facts), 3)

    def test_a_turn_over_an_hour_gives_its_total_in_hours_and_minutes(self):
        gm = GameManager()
        facts = simulate(
            gm,
            MoveAction(destination="out"),
            WaitAction(duration=Duration(minutes=120)),
        )
        self.assertEqual(facts[-1], "About 2 hours 10 minutes pass.")

    def test_a_lone_wait_states_its_time_once(self):
        gm = GameManager()
        facts = simulate(gm, WaitAction(duration=Duration(minutes=90)))
        self.assertEqual(facts, ["Orton waits 1 hour 30 minutes."])

    def test_a_lone_sleep_states_its_time_once(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.FATIGUE, 0.9)
        facts = simulate(gm, SleepAction(duration=Duration(minutes=60)))
        self.assertEqual(facts[0], "Orton sleeps 1 hour.")
        self.assertFalse([f for f in facts if f.startswith("About ")], facts)

    def test_the_minutes_fact_is_absent_when_nothing_took_time(self):
        gm = GameManager()
        facts = simulate(gm, AddGoalAction(horizon="short_term", goal_text="Find water"))
        self.assertFalse(any("pass" in fact for fact in facts))

    def test_the_stat_engine_receives_each_actions_minutes(self):
        gm = GameManager()
        core = SimulationCore(gm)
        handed: list[int] = []
        advance = core.stats_engine.advance

        def spy(player, minutes, ctx, weather_for_chunk=None):
            handed.append(minutes)
            return advance(player, minutes, ctx, weather_for_chunk)

        core.stats_engine.advance = spy
        core.resolve([MoveAction(destination="out"), WaitAction(duration=Duration(minutes=5))])
        self.assertEqual(handed, [10, 5])


class ClockEdgeCaseTests(unittest.TestCase):
    """Spec 01, Edge cases."""

    def test_wait_until_night_from_0800_lands_on_2200(self):
        gm = GameManager()
        simulate(gm, WaitAction(duration=Duration(until_time_of_day="night")))
        self.assertEqual((gm.narrative.day, gm.narrative.hour, gm.narrative.minute), (1, 22, 0))

    def test_wait_until_morning_at_0700_lands_on_0600_next_day(self):
        gm = GameManager()
        gm.advance_clock(1440 - 480 + 7 * 60)  # 07:00 on day 2
        simulate(gm, WaitAction(duration=Duration(until_time_of_day="morning")))
        self.assertEqual((gm.narrative.day, gm.narrative.hour, gm.narrative.minute), (3, 6, 0))

    def test_wait_until_morning_while_in_the_morning_never_waits_zero(self):
        gm = GameManager()
        self.assertEqual(
            _spent(gm, WaitAction(duration=Duration(until_time_of_day="morning"))), 22 * 60
        )

    def test_wait_until_a_clock_time_already_past_is_tomorrow(self):
        gm = GameManager()
        simulate(gm, WaitAction(duration=Duration(until_minute_of_day=7 * 60)))
        self.assertEqual((gm.narrative.day, gm.narrative.hour), (2, 7))

    def test_a_wait_over_24_hours_is_clamped_and_says_so(self):
        gm = GameManager()
        facts = simulate(gm, WaitAction(duration=Duration(minutes=30 * 60)))
        self.assertEqual(gm.narrative.minutes, 1440)
        self.assertEqual(facts[0], "Orton waits 24 hours, the most he can at once.")

    def test_a_sleep_over_16_hours_is_clamped_and_says_so(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.FATIGUE, 1)
        facts = simulate(gm, SleepAction(duration=Duration(minutes=20 * 60)))
        self.assertEqual(gm.narrative.minutes, 960)
        self.assertEqual(facts[0], "Orton sleeps 16 hours, the most he can at once.")

    def test_a_short_sleep_runs_its_duration(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.FATIGUE, 1)
        simulate(gm, SleepAction(duration=Duration(minutes=90)))
        self.assertEqual(gm.narrative.minutes, 90)


class StatTurnTests(unittest.TestCase):
    """Spec 02, Turn flow."""

    def test_a_wait_moves_the_stats_and_reports_a_threshold_crossing(self):
        gm = GameManager()
        facts = simulate(gm, WaitAction(duration=Duration(minutes=5 * 60)))
        self.assertIn("Orton is now Peckish.", facts)
        self.assertGreater(gm.player.stats.get(CharacterStat.HUNGER), 0.15)

    def test_stat_facts_come_before_the_time_fact(self):
        gm = GameManager()
        facts = simulate(
            gm, MoveAction(destination="out"), WaitAction(duration=Duration(minutes=5 * 60))
        )
        self.assertTrue(facts[-1].startswith("About"))
        self.assertLess(facts.index("Orton is now Peckish."), len(facts) - 1)

    def test_a_long_wait_reports_each_status_effect_once_at_its_final_level(self):
        gm = GameManager()
        facts = simulate(gm, WaitAction(duration=Duration(minutes=10 * 60)))
        bored = [fact for fact in facts if "Bored" in fact]
        self.assertEqual(bored, ["Orton is now Extremely Bored."])
        hungry = [
            fact for fact in facts if fact in ("Orton is now Peckish.", "Orton is now Hungry.")
        ]
        self.assertEqual(hungry, ["Orton is now Hungry."])

    def test_a_refused_action_advances_no_stats(self):
        gm = GameManager()
        facts = SimulationCore(gm).resolve([TakeAction(item_name="Unicorn")])
        self.assertTrue(facts[0].startswith("Refused:"))
        self.assertEqual(gm.player.stats.get(CharacterStat.HUNGER), 0)

    def test_combat_minutes_are_exercise(self):
        gm = GameManager()
        simulate(gm, MoveAction(destination="out"), MoveAction(destination="out"))
        endurance_before = gm.player.stats.get(CharacterStat.ENDURANCE)
        self.assertEqual(endurance_before, 1)
        core = SimulationCore(gm)
        context = core._stat_context(AttackAction(target_name="Emma"))  # pyright: ignore[reportPrivateUsage]
        self.assertTrue(context.exercising)


class SleepSpanTests(unittest.TestCase):
    """Spec 02, Waking."""

    def test_sleep_ends_when_fatigue_reaches_zero_after_an_hour(self):
        gm = GameManager()
        gm.player.current_place = "the bedroom"
        gm.player.stats.set(CharacterStat.FATIGUE, 0.2)
        facts = simulate(gm, SleepAction())
        self.assertIn("Orton wakes fully rested.", facts)
        self.assertEqual(gm.player.stats.get(CharacterStat.FATIGUE), 0)
        self.assertGreaterEqual(gm.narrative.minutes, 60)
        self.assertLess(gm.narrative.minutes, 6 * 60)
        self.assertFalse(gm.player.asleep)

    def test_a_rested_sleeper_still_sleeps_the_first_hour(self):
        gm = GameManager()
        simulate(gm, SleepAction())
        self.assertEqual(gm.narrative.minutes, 60)

    def test_a_timed_sleep_stops_when_the_time_is_up(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.FATIGUE, 1)
        facts = simulate(gm, SleepAction(duration=Duration(minutes=120)))
        self.assertEqual(gm.narrative.minutes, 120)
        self.assertEqual(facts[0], "Orton sleeps 2 hours.")

    def test_open_sleep_at_night_wakes_at_nine(self):
        gm = GameManager()
        gm.advance_clock(14 * 60)  # 22:00
        gm.player.stats.set(CharacterStat.FATIGUE, 1)
        simulate(gm, SleepAction())
        self.assertEqual((gm.narrative.hour, gm.narrative.minute), (9, 0))

    def test_the_bedroom_bed_beats_the_floor(self):
        floor, bed = GameManager(), GameManager()
        bed.player.current_place = "the bedroom"
        for gm in (floor, bed):
            gm.player.stats.set(CharacterStat.FATIGUE, 0.8)
            simulate(gm, SleepAction(duration=Duration(minutes=120)))
        self.assertLess(
            bed.player.stats.get(CharacterStat.FATIGUE),
            floor.player.stats.get(CharacterStat.FATIGUE),
        )
        self.assertAlmostEqual(bed.player.stats.get(CharacterStat.FATIGUE), 0.8 - 0.28, delta=0.01)

    def test_a_zombie_wakes_the_sleeper_and_raises_panic_by_30_to_60(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.FATIGUE, 1)
        core = SimulationCore(gm, rng=random.Random(7))
        calls = {"n": 0}

        def zombie_on_minute_thirty(*args: object) -> MinuteReport:
            calls["n"] += 1
            return MinuteReport(new_seen=1 if calls["n"] == 30 else 0)

        with patch.object(core._loop, "run_minute", zombie_on_minute_thirty):  # pyright: ignore[reportPrivateUsage]
            facts = core.resolve([SleepAction()])
        self.assertIn("A zombie wakes Orton in a panic.", facts)
        self.assertEqual(gm.narrative.minutes, 30)
        self.assertFalse(gm.player.asleep)
        panic = gm.player.stats.get(CharacterStat.PANIC)
        # The sighting's panic decays away within the chunk; the draw is what is left.
        self.assertAlmostEqual(panic, random.Random(7).uniform(30, 60))
        self.assertGreaterEqual(panic, 30)
        self.assertLessEqual(panic, 60)

    def test_the_interruption_panic_is_drawn_from_the_injected_rng(self):
        outcomes = []
        for seed in (1, 2):
            gm = GameManager()
            gm.player.stats.set(CharacterStat.FATIGUE, 1)
            core = SimulationCore(gm, rng=random.Random(seed))
            with patch.object(core._loop, "run_minute", lambda *args: MinuteReport(new_seen=1)):  # pyright: ignore[reportPrivateUsage]
                core.resolve([SleepAction()])
            outcomes.append(gm.player.stats.get(CharacterStat.PANIC))
        self.assertNotEqual(outcomes[0], outcomes[1])
        for panic in outcomes:
            self.assertGreaterEqual(panic, 30)
            self.assertLessEqual(panic, 60)

    def test_starving_wakes_a_sleeper(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.FATIGUE, 1)
        gm.player.stats.set(CharacterStat.HUNGER, 0.699)
        gm.player.stats.set(CharacterStat.THIRST, 0)
        facts = simulate(gm, SleepAction(duration=Duration(minutes=6 * 60)))
        self.assertIn("Hunger wakes Orton.", facts)
        self.assertLess(gm.narrative.minutes, 6 * 60)

    def test_dying_of_thirst_wakes_a_sleeper_before_it_can_kill(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.FATIGUE, 1)
        gm.player.stats.set(CharacterStat.THIRST, 0.9)
        facts = simulate(gm, SleepAction(duration=Duration(minutes=16 * 60)))
        self.assertIn("Thirst wakes Orton.", facts)
        self.assertFalse(gm.narrative.game_over)
        self.assertGreater(gm.player.hit_points, 0)


class StatDeathTests(unittest.TestCase):
    """Spec 02, Edge cases; spec 12, Death."""

    def test_death_by_thirst_ends_the_game_with_the_cause(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.THIRST, 0.9)
        facts: list[str] = []
        for _ in range(60):
            facts.extend(simulate(gm, WaitAction(duration=Duration(minutes=12 * 60))))
            if gm.narrative.game_over:
                break
        self.assertTrue(gm.narrative.game_over)
        self.assertEqual(gm.narrative.death_cause, "Orton died of thirst.")
        self.assertTrue(any("Orton has died" in fact for fact in facts))
        self.assertEqual(gm.player.hit_points, 0)

    def test_the_wait_stops_each_time_the_injured_level_rises(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.THIRST, 0.9)
        facts = simulate(gm, WaitAction(duration=Duration(minutes=12 * 60)))
        self.assertIn("Orton is getting weaker.", facts)
        self.assertFalse(gm.narrative.game_over)
        self.assertLess(gm.narrative.minutes, 60 * 3)

    def test_the_clock_stops_at_the_minute_orton_died(self):
        gm = GameManager()
        make_dying(gm.player)
        simulate(gm, WaitAction(duration=Duration(minutes=12 * 60)))
        self.assertLess(gm.narrative.minutes, 10)

    def test_later_actions_in_the_turn_are_refused(self):
        gm = GameManager()
        make_dying(gm.player)
        facts = simulate(
            gm,
            WaitAction(duration=Duration(minutes=12 * 60)),
            WaitAction(duration=Duration(minutes=5)),
        )
        self.assertTrue(any(f.startswith("Refused:") and "dead" in f for f in facts))

    def test_death_while_asleep_is_not_possible_by_a_single_sleep_from_fine_health(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.FATIGUE, 1)
        simulate(gm, SleepAction(duration=Duration(minutes=16 * 60)))
        self.assertFalse(gm.narrative.game_over)


if __name__ == "__main__":
    unittest.main()
