"""Story beats and derived statuses (llm-contract: Story beats and Derived statuses)."""

import random
import unittest
from unittest import mock

from data.items import ITEMS
from data.story.beats import (
    BROADCAST_LOOP_MINUTE,
    CORDON_MINUTE,
    EVACUATION_MINUTE,
    OUTBREAK_BEGINS_MINUTE,
    POWER_OUT_MINUTE,
    STORY_BEATS,
    WATER_OUT_MINUTE,
    Beat,
)
from managers.game import GameManager
from managers.simulation import SimulationCore
from managers.story.beats import holds
from modules.action.types import (
    AddGoalAction,
    Duration,
    MoveAction,
    SearchAction,
    SleepAction,
    TakeAction,
    TalkAction,
    WaitAction,
)
from modules.body.stats import CharacterStat
from modules.character.equipment import CharacterHoldableSlot
from modules.entity.item import ItemEntity
from modules.story.beats import (
    AddNpcStatus,
    AllOf,
    BeatFiredAgo,
    ClockAtOrPast,
    DiscoverFlag,
    FlagDiscovered,
    ItemHeld,
    MoveNpc,
    OutbreakStarted,
    PlayerInZone,
    RemoveNpcStatus,
    SetFlag,
    StartOutbreak,
)
from modules.story.quest import QuestStatus
from tests.support import adjust_regard, npc_of, simulate

SIRENS = "Sirens start up across the city and don't stop."


class OutbreakBeatTests(unittest.TestCase):
    """llm-contract: Story beats: the one starting beat."""

    def test_the_beat_is_the_outbreak_at_day_three_six_in_the_morning(self):
        beat = STORY_BEATS["outbreak_begins"]
        self.assertEqual(OUTBREAK_BEGINS_MINUTE, 2760)
        self.assertEqual(beat.when, ClockAtOrPast(2760))
        self.assertEqual(beat.effects, (StartOutbreak(),))
        self.assertEqual(beat.fact, SIRENS)
        self.assertTrue(beat.interrupts)

    def test_minute_2760_is_day_three_at_six(self):
        gm = GameManager()
        gm.advance_clock(2760)
        self.assertEqual(gm.narrative.day, 3)
        self.assertEqual((gm.narrative.hour, gm.narrative.minute), (6, 0))

    def test_it_fires_at_its_minute_in_the_middle_of_a_wait(self):
        gm = GameManager()
        gm.advance_clock(2733)
        facts = simulate(gm, WaitAction(duration=Duration(minutes=120)), rng=random.Random(1))
        self.assertEqual(gm.narrative.minutes, 2760)
        self.assertEqual(gm.world.outbreak_started_at, 2760)
        self.assertEqual(gm.world.fired_beats, {"outbreak_begins": 2760})
        self.assertIn(SIRENS, facts)
        self.assertEqual(facts[0], "Orton waits 27 minutes, then is interrupted.")
        self.assertNotIn("About 27 minutes pass.", facts)

    def test_a_wait_it_cuts_short_reports_the_time_actually_waited(self):
        gm = GameManager()
        gm.advance_clock(2733)
        facts = simulate(gm, WaitAction(duration=Duration(minutes=120)), rng=random.Random(1))
        self.assertEqual(facts[0], "Orton waits 27 minutes, then is interrupted.")
        self.assertNotIn("Orton waits 2 hours.", facts)

    def test_it_fires_exactly_once(self):
        gm = GameManager()
        gm.advance_clock(2750)
        simulate(gm, WaitAction(duration=Duration(minutes=60)), rng=random.Random(1))
        facts = simulate(gm, WaitAction(duration=Duration(minutes=60)), rng=random.Random(1))
        self.assertNotIn(SIRENS, facts)
        self.assertEqual(gm.world.outbreak_started_at, 2760)

    def test_it_populates_the_zones_but_not_the_apartment(self):
        gm = GameManager()
        gm.advance_clock(2755)
        simulate(gm, WaitAction(duration=Duration(minutes=30)), rng=random.Random(1))
        zones = [zombie.zone_id for zombie in gm.world.zombies.values()]
        self.assertGreater(len(zones), 20)
        self.assertNotIn("zone_home", zones)

    def test_it_interrupts_and_cancels_the_rest_of_the_plan(self):
        gm = GameManager()
        gm.advance_clock(2755)
        facts = simulate(
            gm,
            WaitAction(duration=Duration(minutes=30)),
            AddGoalAction(horizon="short_term", goal_text="Stay calm"),
            rng=random.Random(1),
        )
        self.assertEqual(gm.narrative.minutes, 2760)
        self.assertEqual(gm.narrative.goals["short_term"], [])
        self.assertIn("Orton never gets to: think about their goals.", facts)

    def test_it_wakes_a_sleeper_to_the_sirens(self):
        gm = GameManager()
        gm.advance_clock(2700)
        gm.player.stats.set(CharacterStat.FATIGUE, 0.9)
        facts = simulate(gm, SleepAction(duration=Duration(minutes=240)), rng=random.Random(1))
        self.assertEqual(gm.narrative.minutes, 2760)
        self.assertFalse(gm.player.asleep)
        self.assertIn(SIRENS, facts)
        self.assertIn("Orton is startled awake.", facts)
        self.assertEqual([z for z in gm.world.zombies.values() if z.zone_id == "zone_home"], [])

    def test_a_beat_fires_in_a_turn_that_starts_after_its_minute(self):
        gm = GameManager()
        gm.advance_clock(3000)
        facts = simulate(gm, AddGoalAction(horizon="short_term", goal_text="Rest"))
        self.assertEqual(gm.world.outbreak_started_at, 3000)
        self.assertIn(SIRENS, facts)


STAGES = (
    ("evacuation_announced", "evacuation", EVACUATION_MINUTE, 4260),
    ("cordon", "cordon", CORDON_MINUTE, 7020),
    ("broadcast_loop", "broadcast_loop", BROADCAST_LOOP_MINUTE, 11760),
    ("power_out", "power_out", POWER_OUT_MINUTE, 19380),
    ("water_out", "water_out", WATER_OUT_MINUTE, 28920),
)


class StageBeatTests(unittest.TestCase):
    """world-lore: Stages."""

    def test_the_registry_holds_the_outbreak_the_stages_and_the_binder(self):
        self.assertEqual(
            list(STORY_BEATS),
            ["outbreak_begins", *(beat_id for beat_id, *_ in STAGES), "trial_files"],
        )

    def test_each_stage_is_a_quiet_clock_beat_that_sets_and_discovers_its_flag(self):
        for beat_id, flag, constant, minute in STAGES:
            with self.subTest(beat_id):
                beat = STORY_BEATS[beat_id]
                self.assertEqual(constant, minute)
                self.assertEqual(beat.when, ClockAtOrPast(minute))
                self.assertEqual(beat.effects, (SetFlag(flag), DiscoverFlag(flag)))
                self.assertFalse(beat.interrupts)

    def test_every_due_stage_fires_in_order_in_one_turn_without_interrupting(self):
        gm = GameManager()
        gm.advance_clock(WATER_OUT_MINUTE + 5)
        gm.world.outbreak_started_at = 0
        gm.world.fired_beats["outbreak_begins"] = 0
        facts = simulate(gm, AddGoalAction("short_term", "rest"), rng=random.Random(1))
        told = [STORY_BEATS[beat_id].fact for beat_id, *_ in STAGES]
        positions = [facts.index(fact) for fact in told]
        self.assertEqual(positions, sorted(positions))
        for _, flag, *_ in STAGES:
            self.assertIn(flag, gm.narrative.discovered_flags)
            self.assertIs(gm.narrative.flags[flag], True)
        self.assertFalse(any("interrupted" in fact for fact in facts))

    def test_a_stage_fires_at_its_own_minute_inside_a_wait(self):
        gm = GameManager()
        gm.advance_clock(EVACUATION_MINUTE - 5)
        simulate(gm, WaitAction(duration=Duration(minutes=30)), rng=random.Random(1))
        self.assertEqual(gm.world.fired_beats["evacuation_announced"], EVACUATION_MINUTE)
        self.assertNotIn("cordon", gm.world.fired_beats)


def clinic_office_game() -> GameManager:
    gm = GameManager()
    gm.player.current_location_id = "zone_clinic"
    gm.player.current_room = "office"
    simulate(gm, SearchAction(target_name="filing cabinet"))
    return gm


TAKE_BINDER = TakeAction(item_name="Study Binder", from_name="filing cabinet")


class TrialFilesTests(unittest.TestCase):
    """world-lore: The binder."""

    def test_the_cabinet_holds_the_binder_alone(self):
        gm = clinic_office_game()
        office = gm.world.locations["zone_clinic"].rooms["office"]
        cabinet = next(c for c in office.containers if c.container_id == "clinic_filing_cabinet")
        self.assertEqual([e.item.id for e in cabinet.contents], ["item_study_binder"])
        self.assertTrue(cabinet.fixed)

    def test_taking_the_binder_fires_the_beat_and_discovers_the_truth(self):
        gm = clinic_office_game()
        facts = simulate(gm, TAKE_BINDER)
        self.assertIn(STORY_BEATS["trial_files"].fact, facts)
        self.assertIn("trial_truth", gm.narrative.discovered_flags)
        self.assertIn("trial_files", gm.world.fired_beats)
        self.assertFalse(STORY_BEATS["trial_files"].interrupts)

    def test_the_beat_is_quiet_until_the_binder_is_taken(self):
        gm = clinic_office_game()
        simulate(gm, AddGoalAction("short_term", "look around"))
        self.assertNotIn("trial_files", gm.world.fired_beats)

    def test_dropping_the_binder_later_undoes_nothing(self):
        gm = clinic_office_game()
        simulate(gm, TAKE_BINDER)
        gm.player.inventory.clear()
        self.assertFalse(holds(ItemHeld("item_study_binder"), gm))
        self.assertIn("trial_truth", gm.narrative.discovered_flags)


class ItemHeldTests(unittest.TestCase):
    """world-lore: The binder: `ItemHeld`."""

    def test_it_holds_for_the_pack_a_bag_the_hands_and_worn_things(self):
        binder = ITEMS["item_study_binder"]
        wanted = ItemHeld("item_study_binder")
        gm = GameManager()
        self.assertFalse(holds(wanted, gm))

        gm.player.inventory.append(ItemEntity(item=binder))
        self.assertTrue(holds(wanted, gm))

        gm.player.inventory.clear()
        bag = ItemEntity(item=ITEMS["item_paper_bag"])
        bag.contents.append(ItemEntity(item=binder))
        gm.player.inventory.append(bag)
        self.assertTrue(holds(wanted, gm))

        gm.player.inventory.clear()
        gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND] = ItemEntity(item=binder)
        self.assertTrue(holds(wanted, gm))

        gm.player.equipment.clear()
        jacket = ITEMS["item_black_jacket"]
        gm.player.worn.clear()
        self.assertFalse(holds(ItemHeld(jacket.id), gm))
        gm.player.worn[jacket.body_location] = ItemEntity(item=jacket)  # type: ignore[attr-defined]
        self.assertTrue(holds(ItemHeld(jacket.id), gm))

    def test_a_save_that_holds_the_binder_already_satisfies_the_beat(self):
        gm = GameManager()
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_study_binder"]))
        simulate(gm, AddGoalAction("short_term", "rest"))
        self.assertIn("trial_truth", gm.narrative.discovered_flags)


class BeatEvaluationTests(unittest.TestCase):
    """llm-contract: Story beats: conditions, effects and when they are checked."""

    def test_each_condition_kind(self):
        gm = GameManager()
        self.assertFalse(holds(ClockAtOrPast(10), gm))
        gm.advance_clock(10)
        self.assertTrue(holds(ClockAtOrPast(10), gm))
        self.assertTrue(holds(PlayerInZone("zone_home"), gm))
        self.assertFalse(holds(PlayerInZone("zone_street"), gm))
        self.assertFalse(holds(FlagDiscovered("x"), gm))
        gm.narrative.discovered_flags.add("x")
        self.assertTrue(holds(FlagDiscovered("x"), gm))
        self.assertFalse(holds(OutbreakStarted(), gm))
        gm.world.outbreak_started_at = 0
        self.assertTrue(holds(OutbreakStarted(), gm))

    def test_beat_fired_ago_and_all_of(self):
        gm = GameManager()
        gm.advance_clock(100)
        gm.world.fired_beats["a"] = 40
        self.assertTrue(holds(BeatFiredAgo("a", 60), gm))
        self.assertFalse(holds(BeatFiredAgo("a", 61), gm))
        self.assertFalse(holds(BeatFiredAgo("b", 0), gm))
        both = AllOf((ClockAtOrPast(100), PlayerInZone("zone_home")))
        self.assertTrue(holds(both, gm))
        self.assertFalse(holds(AllOf((ClockAtOrPast(100), PlayerInZone("zone_street"))), gm))

    def test_each_effect(self):
        gm = GameManager()
        core = SimulationCore(gm, rng=random.Random(1))
        core.apply_story_effect(SetFlag("power_out"))
        self.assertIs(gm.narrative.flags["power_out"], True)
        core.apply_story_effect(DiscoverFlag("power_out"))
        self.assertIn("power_out", gm.narrative.discovered_flags)
        core.apply_story_effect(MoveNpc("npc_emma", "zone_street"))
        self.assertEqual(npc_of(gm, "Emma").current_location_id, "zone_street")
        core.apply_story_effect(AddNpcStatus("npc_emma", "frightened"))
        self.assertIn("frightened", npc_of(gm, "Emma").status)
        core.apply_story_effect(RemoveNpcStatus("npc_emma", "frightened"))
        self.assertNotIn("frightened", npc_of(gm, "Emma").status)
        core.apply_story_effect(StartOutbreak())
        self.assertEqual(gm.world.outbreak_started_at, gm.narrative.minutes)

    def test_a_beat_on_a_state_condition_fires_after_the_action_that_makes_it_true(self):
        beat = Beat(
            beat_id="street_noise",
            when=PlayerInZone("zone_building"),
            effects=(SetFlag("heard_noise"),),
            fact="A door slams somewhere above.",
            interrupts=False,
        )
        gm = GameManager()
        core = SimulationCore(gm, rng=random.Random(1), beats={"street_noise": beat})
        self.assertNotIn(
            "A door slams somewhere above.", core.resolve([AddGoalAction("short_term", "x")]).facts
        )
        facts = core.resolve([MoveAction(destination="out")]).facts
        self.assertIn("A door slams somewhere above.", facts)
        self.assertIs(gm.narrative.flags["heard_noise"], True)
        self.assertEqual(gm.world.fired_beats["street_noise"], gm.narrative.minutes)
        again = core.resolve([AddGoalAction("short_term", "y")]).facts
        self.assertNotIn("A door slams somewhere above.", again)

    def test_resolution_traces_the_action_the_beat_and_its_flag(self):
        beat = Beat("street_noise", PlayerInZone("zone_building"), (SetFlag("heard"),), "x", False)
        gm = GameManager()
        core = SimulationCore(gm, rng=random.Random(1), beats={"street_noise": beat})

        with self.assertLogs("managers.simulation", level="DEBUG") as logs:
            core.resolve([MoveAction(destination="out")])

        lines = [record.getMessage() for record in logs.records]
        self.assertTrue(any("MoveAction" in line and "minutes" in line for line in lines))
        self.assertTrue(any("street_noise" in line and "heard" in line for line in lines))
        self.assertTrue(any(line.startswith("Flag heard set") for line in lines))

    def test_a_beat_that_does_not_interrupt_lets_the_plan_run(self):
        beat = Beat("quiet", PlayerInZone("zone_home"), (), "Something stirs.", False)
        gm = GameManager()
        core = SimulationCore(gm, beats={"quiet": beat})
        facts = core.resolve(
            [AddGoalAction("short_term", "a"), AddGoalAction("short_term", "z")]
        ).facts
        self.assertIn("Something stirs.", facts)
        self.assertEqual(gm.narrative.goals["short_term"], ["a", "z"])

    def test_the_action_resolves_before_a_beat_due_in_its_minute(self):
        beat = Beat("due", ClockAtOrPast(1), (SetFlag("late"),), "It is late.", False)
        gm = GameManager()
        core = SimulationCore(gm, beats={"due": beat})
        facts = core.resolve(
            [AddGoalAction("short_term", "w"), AddGoalAction("short_term", "v")]
        ).facts
        self.assertEqual(gm.narrative.goals["short_term"], ["w", "v"])
        self.assertNotIn("It is late.", facts)
        facts = core.resolve([WaitAction(duration=Duration(minutes=3))]).facts
        self.assertIn("It is late.", facts)

    def test_beats_are_evaluated_by_the_registry_passed_in(self):
        with mock.patch("managers.simulation.STORY_BEATS", {}):
            gm = GameManager()
            gm.advance_clock(2800)
            simulate(gm, AddGoalAction("short_term", "q"))
            self.assertIsNone(gm.world.outbreak_started_at)


class DerivedStatusTests(unittest.TestCase):
    """llm-contract: Derived statuses."""

    def test_trusts_player_appears_at_solid_trust_and_completes_the_quest(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        adjust_regard(gm, "npc_marcus", trust=35)
        facts = simulate(gm, TalkAction(npc_name="Marcus", approach="confide"))
        self.assertIn("trusts_player", npc_of(gm, "Marcus").status)
        self.assertEqual(gm.quests["quest_marcus_trust"].status, QuestStatus.COMPLETED)
        self.assertIn("Marcus's trust in Orton is now solid.", facts)
        self.assertIn('Quest "Earn the Super\'s Trust" completed.', " ".join(facts))

    def test_it_is_absent_below_solid(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        adjust_regard(gm, "npc_marcus", trust=30)
        simulate(gm, TalkAction(npc_name="Marcus", approach="confide"))
        self.assertNotIn("trusts_player", npc_of(gm, "Marcus").status)

    def test_it_disappears_when_trust_falls_but_the_quest_stays_complete(self):
        gm = GameManager()
        adjust_regard(gm, "npc_marcus", trust=37)
        simulate(gm, AddGoalAction("short_term", "a"))
        self.assertIn("trusts_player", npc_of(gm, "Marcus").status)
        adjust_regard(gm, "npc_marcus", trust=-20)
        simulate(gm, AddGoalAction("short_term", "b"))
        self.assertNotIn("trusts_player", npc_of(gm, "Marcus").status)
        self.assertEqual(gm.quests["quest_marcus_trust"].status, QuestStatus.COMPLETED)

    def test_unwavering_trust_counts_too(self):
        gm = GameManager()
        adjust_regard(gm, "npc_emma", trust=80)
        simulate(gm, AddGoalAction("short_term", "a"))
        self.assertIn("trusts_player", npc_of(gm, "Emma").status)

    def test_the_descriptive_statuses_are_left_alone(self):
        gm = GameManager()
        adjust_regard(gm, "npc_emma", trust=80)
        simulate(gm, AddGoalAction("short_term", "a"))
        self.assertIn("friendly", npc_of(gm, "Emma").status)
