"""GameEngine turn orchestration, with the LLM and the embedding model stubbed.

Two LLM calls per turn now, not one: the parser proposes actions (script via
`ScriptedLLM(actions=...)`), the engine validates and simulates them, and the
narrator describes what already happened (script via `ScriptedLLM(story=...)`).
"""

import json
import re
import unittest
from typing import cast
from unittest import mock

import adapters.engine as engine_module
import config
from adapters import llm
from adapters.engine import GameEngine
from adapters.llm import NARRATOR_SYSTEM_PROMPT, LLMError
from adapters.memory import DEFAULT_RECALL
from adapters.save import files
from data.memory import BUDGET_MARGIN_TOKENS
from data.presets import ORTON
from managers.context import NOTHING_DONE_FACT
from managers.game import MAX_RECENT_EVENTS
from modules.body import BodyLocation, BodyPart
from modules.entity.item import ItemEntity
from modules.entity.zombie import ZombieEntity, ZombieState
from tests.support import (
    FakeMemory,
    FakeStoryChecker,
    IsolatedSaveTestCase,
    ScriptedLLM,
    make_dying,
    npc_of,
)

MOVE_OUT_ACTIONS = "ACTIONS:\nMOVE_TO out\nADD_GOAL short_term Find a weapon"
MOVE_OUT_STORY = "STORY:\nYou walk out into the building.\n\nEVENT:\nOrton entered the building\n\nOPTIONS:\nNONE"


class EngineTestCase(IsolatedSaveTestCase):
    """Builds an engine whose slow edges are replaced."""

    def setUp(self):
        super().setUp()
        self.llm = ScriptedLLM(actions=MOVE_OUT_ACTIONS, story=MOVE_OUT_STORY)
        self._original_parser = engine_module.llm.query_parser
        self._original_narrator = engine_module.llm.query_narrator
        self._original_summary = engine_module.llm.query_summary
        engine_module.llm.query_parser = self.llm.query_parser
        engine_module.llm.query_narrator = self.llm.query_narrator
        engine_module.llm.query_summary = self.llm.query_summary
        self._original_memory = engine_module.SemanticMemory
        engine_module.SemanticMemory = FakeMemory
        self._original_storychecker = engine_module.StoryChecker
        engine_module.StoryChecker = FakeStoryChecker

        self.engine = GameEngine()
        self.engine.create_character(ORTON)

    def tearDown(self):
        engine_module.llm.query_parser = self._original_parser
        engine_module.llm.query_narrator = self._original_narrator
        engine_module.llm.query_summary = self._original_summary
        engine_module.SemanticMemory = self._original_memory
        engine_module.StoryChecker = self._original_storychecker
        super().tearDown()


class TurnTests(EngineTestCase):
    def test_turn_returns_story_and_applies_actions(self):
        result = self.engine.play("go out")
        self.assertEqual(result["story_text"], "You walk out into the building.")
        self.assertEqual(result["current_location"], "Your Building")
        self.assertIn("Find a weapon", result["goals"]["short_term"])

    def test_turn_records_the_event_in_both_tiers(self):
        self.engine.play("go out")
        memory = self.engine.game.memory
        self.assertTrue(memory.full_event_log[-1].startswith("Day 1, 08:00 AM, Your Apartment."))
        self.assertEqual(memory.recent_events[0], memory.full_event_log[-1])

    def test_turn_reindexes_memory(self):
        self.engine.play("go out")
        self.assertEqual(
            self.engine.memory.rebuilt_with[-1],
            self.engine.game.memory.full_event_log,
        )

    def test_the_parser_is_sent_this_scenes_schema(self):
        self.engine.play("go out")
        schema = self.llm.schemas[-1]
        assert schema is not None
        verbs = [
            b["properties"]["verb"]["const"]
            for b in schema["properties"]["actions"]["items"]["anyOf"]
        ]
        self.assertIn("MOVE_TO", verbs)
        self.assertNotIn("BANDAGE", verbs)

    def test_a_structured_reply_goes_through_the_same_validation(self):
        self.llm.structured = True
        self.llm.actions = json.dumps(
            {
                "actions": [
                    {"verb": "MOVE_TO", "destination": "out"},
                    {"verb": "ADD_GOAL", "horizon": "short_term", "text": "Find a weapon"},
                    {"verb": "TAKE", "item": "Nothing Like This"},
                ]
            }
        )
        result = self.engine.play("go out")
        self.assertEqual(result["current_location"], "Your Building")
        self.assertIn("Find a weapon", result["goals"]["short_term"])
        self.assertIn("Refused", self.llm.narrator_prompts[-1])

    def test_a_structured_reply_that_is_not_json_is_refused_and_the_turn_goes_on(self):
        self.llm.structured = True
        self.llm.actions = "{nope"
        result = self.engine.play("go out")
        self.assertEqual(result["story_text"], "You walk out into the building.")
        self.assertIn("Refused", self.llm.narrator_prompts[-1])

    def test_player_input_reaches_the_parser_prompt(self):
        self.engine.play("peer down the corridor")
        self.assertIn("peer down the corridor", self.llm.prompts[-1])

    def test_recalled_memories_reach_the_narrator_prompt(self):
        self.engine.game.memory.full_event_log.append("Orton heard sirens.")
        self.engine.memory.next_hits = [0]
        self.engine.play("what was that noise")
        self.assertIn("Orton heard sirens.", self.llm.narrator_prompts[-1])

    def test_out_of_range_recall_hits_are_ignored(self):
        # A stale index must not blow up the turn.
        self.engine.memory.next_hits = [99]
        result = self.engine.play("go out")
        self.assertEqual(result["current_location"], "Your Building")

    def test_deep_memory_skips_entries_already_in_recent_events(self):
        memory = self.engine.game.memory
        memory.full_event_log.extend(["Entry A.", "Entry B.", "Entry C.", "Entry D."])
        memory.recent_events[:] = ["Entry D."]
        cast(FakeMemory, self.engine.memory).next_hits = [3, 0, 1, 2]
        self.engine.play("what was that noise")
        prompt = self.llm.narrator_prompts[-1]
        deep = prompt.split("[DEEP MEMORY]")[1].split("[SUMMARY OF PAST EVENTS]")[0]
        self.assertEqual(prompt.count("Entry D."), 1)
        self.assertNotIn("Entry D.", deep)
        self.assertIn("Entry A.", deep)
        self.assertIn("Entry B.", deep)
        self.assertNotIn("Entry C.", deep)

    def test_deep_memory_searches_wider_than_it_recalls(self):
        self.engine.play("what was that noise")
        self.assertGreaterEqual(
            cast(FakeMemory, self.engine.memory).searched_k[-1], DEFAULT_RECALL + MAX_RECENT_EVENTS
        )

    def test_turn_persists(self):
        self.engine.play("go out")
        reloaded = files.load(self.save_path)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.player.current_location_id, "zone_building")
        self.assertIn("Find a weapon", reloaded.narrative.goals["short_term"])

    def test_snapshot_shape(self):
        result = self.engine.play("go out")
        self.assertIsInstance(result["inventory"], list)
        self.assertIsInstance(result["npcs_present"], list)
        self.assertIsInstance(result["goals"]["short_term"], list)
        self.assertEqual(result["day"], 1)
        self.assertIn("current_place", result)

    def test_snapshot_carries_threats_and_sneaking(self):
        state = self.engine.state()
        self.assertEqual(state["threats"], [])
        self.assertIs(state["sneaking"], False)
        manager = self.engine.game
        manager.world.outbreak_started_at = 0
        manager.player.sneaking = True
        manager.world.zombies["z1"] = ZombieEntity(
            zombie_id="z1",
            zone_id=manager.player.current_location_id,
            health=2.0,
            speed_type=3,
            speed_mod=0.6,
            lunger=False,
            strength=3,
            memory=800,
            sight=2,
            hearing=2,
            state=ZombieState.CHASING,
            gap=3.0,
        )
        state = self.engine.state()
        self.assertEqual(
            state["threats"],
            [{"id": "z1", "distance_word": "close", "state_word": "coming at you"}],
        )
        self.assertIs(state["sneaking"], True)

    def test_snapshot_carries_the_body_in_words_and_flags(self):
        """Spec 12, What the narrator and the player see."""
        self.assertEqual(self.engine.state()["body"], [])
        player = self.engine.game.player
        forearm = player.body[BodyPart.FOREARM_L]
        forearm.bite_time = 60.0
        forearm.bleeding_time = 10.0
        hand = player.body[BodyPart.HAND_R]
        hand.scratch_time = 6.0
        hand.infected_wound = True
        hand.zombie_infected = True
        player.zombie_infection_since = 0.0
        thigh = player.body[BodyPart.UPPERLEG_L]
        thigh.cut_time = 12.0
        thigh.bandage = "item_bandage"
        thigh.bandage_life = 0.0
        body = self.engine.state()["body"]
        self.assertEqual(
            body,
            [
                {
                    "part": "right hand",
                    "wounds": ["scratch"],
                    "bleeding": False,
                    "bandaged": False,
                    "dirty": False,
                    "infected": True,
                },
                {
                    "part": "left forearm",
                    "wounds": ["bite"],
                    "bleeding": True,
                    "bandaged": False,
                    "dirty": False,
                    "infected": False,
                },
                {
                    "part": "left thigh",
                    "wounds": ["laceration"],
                    "bleeding": False,
                    "bandaged": True,
                    "dirty": True,
                    "infected": False,
                },
            ],
        )

    def test_snapshot_body_never_carries_zombie_infection_or_a_number(self):
        player = self.engine.game.player
        player.body[BodyPart.HAND_R].scratch_time = 6.0
        player.body[BodyPart.HAND_R].zombie_infected = True
        player.zombie_infection_since = 0.0
        text = json.dumps(self.engine.state()["body"]).casefold()
        self.assertNotIn("zombie_infection", text)
        for entry in self.engine.state()["body"]:
            for value in entry.values():
                self.assertTrue(isinstance(value, bool | str | list), value)

    def test_snapshot_lists_worn_clothing_with_wetness_words(self):
        self.engine.game.player.worn[BodyLocation.PANTS].wetness = 90.0
        worn = self.engine.state()["worn"]
        self.assertEqual([entry["location"] for entry in worn][:2], ["base:sweater", "base:pants"])
        by_name = {entry["name"]: entry for entry in worn}
        self.assertEqual(
            by_name["Jeans"], {"location": "base:pants", "name": "Jeans", "wetness_word": "soaked"}
        )
        self.assertEqual(by_name["T-shirt"]["wetness_word"], "")

    def test_snapshot_equipment_holds_only_hands_and_shoulders(self):
        slots = [entry["slot"] for entry in self.engine.state()["equipment"]]
        self.assertEqual(slots, ["Right Hand", "Left Hand", "Shoulders"])

    def test_snapshot_carries_the_held_item_and_kills(self):
        from data.items import ITEMS
        from modules.character.equipment import CharacterHoldableSlot

        state = self.engine.state()
        self.assertIsNone(state["held"])
        self.assertEqual(state["zombie_kills"], 0)
        manager = self.engine.game
        crowbar = ItemEntity(item=ITEMS["item_crowbar"])
        crowbar.condition = 5
        manager.player.equipment[CharacterHoldableSlot.RIGHT_HAND] = crowbar
        manager.player.equipment[CharacterHoldableSlot.LEFT_HAND] = crowbar
        manager.player.zombie_kills = 3
        state = self.engine.state()
        self.assertEqual(state["held"], {"name": "Crowbar", "condition_word": "badly worn"})
        self.assertEqual(state["zombie_kills"], 3)
        right = next(e for e in state["equipment"] if e["slot"] == "Right Hand")
        self.assertEqual(right["condition"], "badly worn")

    def test_snapshot_has_game_over_false_by_default(self):
        result = self.engine.state()
        self.assertIs(result["game_over"], False)
        self.assertEqual(result["death_cause"], "")

    def test_narrator_options_reach_the_snapshot(self):
        self.llm.story = (
            "STORY:\nYou walk out.\n\nEVENT:\nOrton entered the building\n\n"
            "OPTIONS:\n- Check the mailboxes\n- Look out the window"
        )
        result = self.engine.play("go out")
        self.assertEqual(result["options"], ["Check the mailboxes", "Look out the window"])

    def test_no_options_offered_yields_an_empty_list(self):
        # MOVE_OUT_STORY offers OPTIONS: NONE.
        result = self.engine.play("go out")
        self.assertEqual(result["options"], [])

    def test_reset_and_state_snapshots_carry_no_stale_options(self):
        self.llm.story = (
            "STORY:\nYou walk out.\n\nEVENT:\nOrton entered the building\n\n"
            "OPTIONS:\n- Check the mailboxes"
        )
        self.engine.play("go out")
        self.assertEqual(self.engine.state()["options"], [])
        self.assertEqual(self.engine.reset()["options"], [])
        self.assertTrue(self.engine.reset()["needs_creation"])

    def test_npcs_present_tracks_the_player(self):
        # Orton now starts alone in his apartment; Emma starts in the building.
        self.engine.game.player.current_location_id = "zone_building"
        before = self.engine.state()
        self.assertIn("Emma", before["npcs_present"])  # in the building
        after = self.engine.play("go out")
        self.assertNotIn("Emma", after["npcs_present"])  # on the street

    def test_failed_actions_do_not_abort_the_turn(self):
        # MOVE_TO never fails, so TAKE Medkit stands in as the real refusal.
        self.llm.actions = "ACTIONS:\nTAKE Medkit\nADD_GOAL short_term Survive"
        self.llm.story = "STORY:\nYou try.\n\nEVENT:\nOrton tried"
        result = self.engine.play("go somewhere")
        self.assertEqual(result["story_text"], "You try.")
        # The bad action was refused, the good one still applied.
        self.assertEqual(result["current_location"], "Your Apartment")
        self.assertIn("Survive", result["goals"]["short_term"])

    def test_refused_actions_are_surfaced_to_the_narrator_the_same_turn(self):
        # Doc 01's inversion: a refusal is validated before any prose exists,
        # so the narrator sees it as an [OUTCOMES] fact this turn, not as a
        # next-turn [CONTINUITY] correction for damage already done.
        self.llm.actions = "ACTIONS:\nTAKE Medkit"
        self.llm.story = "STORY:\nYou reach for it.\n\nEVENT:\nOrton reached for something"
        self.engine.play("take the medkit")
        self.assertIn("[OUTCOMES]", self.llm.narrator_prompts[-1])
        self.assertIn("Refused:", self.llm.narrator_prompts[-1])
        self.assertIn("No 'Medkit' here to take.", self.llm.narrator_prompts[-1])
        # Nothing was deferred: pending_corrections/[CONTINUITY] stays empty.
        self.assertEqual(self.engine.game.narrative.pending_corrections, [])
        self.assertIn("(Nothing to correct)", self.llm.narrator_prompts[-1])

    def test_unparseable_action_lines_are_surfaced_but_do_not_abort_the_turn(self):
        self.llm.actions = "ACTIONS:\nFROBNICATE the widget\nADD_GOAL short_term Survive"
        result = self.engine.play("do something weird")
        self.assertIn("Survive", result["goals"]["short_term"])
        self.assertIn("Refused:", self.llm.narrator_prompts[-1])


class DeathTests(EngineTestCase):
    def test_dead_game_makes_no_llm_calls(self):
        self.engine.game.narrative.game_over = True
        self.engine.game.narrative.death_cause = "Use Suspicious Vial: succeeded."
        result = self.engine.play("get up")
        self.assertEqual(self.llm.prompts, [])
        self.assertEqual(self.llm.narrator_prompts, [])
        self.assertIn("Use Suspicious Vial", result["story_text"])
        self.assertIn("new game", result["story_text"].lower())

    def test_reset_revives(self):
        self.engine.game.narrative.game_over = True
        self.engine.game.narrative.death_cause = "Orton starved."
        self.engine.reset()
        errors, result = self.engine.create_character(ORTON)
        self.assertEqual(errors, [])
        assert result is not None
        self.assertIs(result["game_over"], False)
        self.assertEqual(result["death_cause"], "")
        self.assertFalse(self.engine.game.narrative.game_over)
        # A revived game plays turns normally again.
        played = self.engine.play("go out")
        self.assertEqual(len(self.llm.prompts), 1)
        self.assertEqual(played["current_location"], "Your Building")


class SummarizationTests(EngineTestCase):
    def test_summary_is_produced_once_enough_events_accumulate(self):
        for i in range(9):
            self.engine.game.record_event(f"Event {i}")
        self.engine.play("go out")  # the tenth event
        self.assertEqual(self.engine.game.memory.summaries, ["A summary."])
        self.assertEqual(len(self.llm.summarized), 1)

    def test_no_summary_before_the_threshold(self):
        self.engine.play("go out")
        self.assertEqual(self.engine.game.memory.summaries, [])
        self.assertEqual(self.llm.summarized, [])


class FailureTests(EngineTestCase):
    def test_parser_failure_surfaces_as_story_text(self):
        self.llm.error = LLMError("LM Studio is not running")
        result = self.engine.play("look around")
        self.assertIn("LM Studio is not running", result["story_text"])

    def test_parser_failure_leaves_state_untouched(self):
        self.engine.play("go out")  # a good turn first
        log_before = list(self.engine.game.memory.full_event_log)

        self.llm.error = LLMError("connection refused")
        result = self.engine.play("go out")

        self.assertEqual(result["current_location"], "Your Building")
        self.assertEqual(self.engine.game.memory.full_event_log, log_before)
        reloaded = files.load(self.save_path)
        self.assertEqual(reloaded.memory.full_event_log, log_before)

    def test_narrator_failure_still_persists_the_engines_decision(self):
        # Movement was already decided by the engine before the narrator was
        # asked to describe it -- a rendering failure must not discard that.
        class FailingNarrator(ScriptedLLM):
            def query_narrator(self, prompt: str) -> str:
                self.narrator_prompts.append(prompt)
                raise LLMError("LM Studio dropped the connection")

        self.llm = FailingNarrator(actions=MOVE_OUT_ACTIONS)
        engine_module.llm.query_parser = self.llm.query_parser
        engine_module.llm.query_narrator = self.llm.query_narrator

        result = self.engine.play("go out")

        self.assertIn("LM Studio dropped the connection", result["story_text"])
        self.assertEqual(self.engine.game.player.current_location_id, "zone_building")
        reloaded = files.load(self.save_path)
        self.assertEqual(reloaded.player.current_location_id, "zone_building")

    def test_summarization_failure_does_not_lose_the_turn(self):
        def boom(text):
            raise LLMError("summarizer offline")

        engine_module.llm.query_summary = boom
        for i in range(9):
            self.engine.game.record_event(f"Event {i}")

        result = self.engine.play("go out")
        self.assertEqual(result["story_text"], "You walk out into the building.")
        self.assertEqual(self.engine.game.memory.summaries, [])
        self.assertTrue(self.engine.game.memory.full_event_log[-1].startswith("Day 1, 08:00 AM"))


class LifecycleTests(EngineTestCase):
    def test_engine_resumes_from_a_save(self):
        self.engine.play("go out")
        resumed = GameEngine()
        self.assertEqual(resumed.game.player.current_location_id, "zone_building")
        self.assertIn("Find a weapon", resumed.game.narrative.goals["short_term"])

    def test_reset_clears_everything(self):
        self.engine.play("go out")
        self.engine.reset()
        self.assertIsNone(self.engine.manager)
        _, result = self.engine.create_character(ORTON)
        assert result is not None
        self.assertEqual(result["current_location"], "Your Apartment")
        self.assertEqual(result["goals"]["short_term"], [])
        self.assertEqual(self.engine.game.memory.full_event_log, [])
        self.assertEqual(
            self.engine.game.relationship_manager.get_affinity("npc_emma", "player"), 0
        )

    def test_reset_deletes_the_save(self):
        self.engine.play("go out")
        self.engine.reset()
        self.assertIsNone(files.load(self.save_path))
        self.assertIsNone(GameEngine().manager)

    def test_creating_a_character_writes_a_fresh_save(self):
        self.engine.play("go out")
        self.engine.reset()
        self.engine.create_character(ORTON)
        reloaded = files.load(self.save_path)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.player.current_location_id, "zone_home")

    def test_reset_does_not_leak_previous_world_state(self):

        self.engine.play("go out")  # now in zone_building
        self.llm.actions = "ACTIONS:\nTAKE Painkillers"
        self.engine.play("take the painkillers")
        self.engine.reset()
        self.engine.create_character(ORTON)
        building = self.engine.game.world.locations["zone_building"]
        item_names = [e.item.name for e in building.entities if isinstance(e, ItemEntity)]
        self.assertIn("Painkillers", item_names)


class SaveLoadTests(EngineTestCase):
    def test_export_round_trips_through_import(self):
        self.engine.play("go out")
        exported = self.engine.export_save()

        other = GameEngine()
        other.memory = FakeMemory()
        result = other.import_save(exported)

        self.assertIsNotNone(result)
        self.assertEqual(result["current_location"], "Your Building")
        self.assertIn("Find a weapon", result["goals"]["short_term"])

    def test_import_rejects_a_bad_version(self):
        exported = self.engine.export_save()
        exported["version"] = 999
        self.assertIsNone(self.engine.import_save(exported))
        # The live game must be untouched by a rejected upload.
        self.assertEqual(self.engine.game.player.current_location_id, "zone_home")

    def test_import_persists_the_uploaded_save(self):
        self.engine.play("go out")  # now in the building
        exported = self.engine.export_save()

        self.engine.reset()  # back home; save file now says zone_home
        self.engine.import_save(exported)  # re-import the building save

        reloaded = files.load(self.save_path)
        self.assertEqual(reloaded.player.current_location_id, "zone_building")


class DeathPersistenceTests(EngineTestCase):
    """game_over/death_cause survive a save and reload through the engine."""

    def test_death_survives_a_reload_through_the_engine(self):
        make_dying(self.engine.game.player)
        self.llm.actions = "ACTIONS:\nWAIT 10m"

        self.engine.play("wait here")
        self.assertTrue(self.engine.game.narrative.game_over)
        original_cause = self.engine.game.narrative.death_cause
        self.assertTrue(original_cause)

        prompts_before = len(self.llm.prompts)
        narrator_prompts_before = len(self.llm.narrator_prompts)

        # A fresh engine, reading the same (redirected) save file, must come
        # back up already dead -- not resurrect Orton for one more turn.
        reloaded = GameEngine()
        reloaded.memory = FakeMemory()
        self.assertTrue(reloaded.game.narrative.game_over)
        self.assertEqual(reloaded.game.narrative.death_cause, original_cause)

        result = reloaded.play("try again")
        self.assertIn("Orton is dead", result["story_text"])
        # No parser/narrator call for a turn that can't happen anymore.
        self.assertEqual(len(self.llm.prompts), prompts_before)
        self.assertEqual(len(self.llm.narrator_prompts), narrator_prompts_before)


if __name__ == "__main__":
    unittest.main()


class MemoryFactsTests(EngineTestCase):
    """Spec 10, Memory and Plans."""

    def test_each_event_log_entry_is_stamp_attempt_then_the_turns_facts(self):
        self.engine.play("go out")
        entry = self.engine.game.memory.full_event_log[-1]
        self.assertTrue(
            entry.startswith('Day 1, 08:00 AM, Your Apartment. Orton tries: "go out" '), entry
        )
        self.assertTrue(entry.endswith("About 10 minutes pass."), entry)
        self.assertNotIn("Orton entered the building", entry)
        self.assertIn("Move to Your Building", entry)
        self.assertIn("Find a weapon", entry)

    def test_the_recent_buffer_carries_the_same_entry(self):
        self.engine.play("go out")
        memory = self.engine.game.memory
        self.assertEqual(memory.recent_events[0], memory.full_event_log[-1])

    def test_refused_lines_are_facts_in_the_entry(self):
        self.llm.actions = "ACTIONS:\nFROBNICATE the widget"
        self.engine.play("do something weird")
        entry = self.engine.game.memory.full_event_log[-1]
        self.assertIn("Refused:", entry)
        self.assertNotIn("the widget", entry)

    def test_the_entry_names_no_zombie_id(self):
        self.llm.actions = "ACTIONS:\nATTACK z7"
        self.engine.play("attack it")
        entry = self.engine.game.memory.full_event_log[-1]
        self.assertIn("the zombie", entry)
        self.assertNotRegex(entry, r"\bz\d+\b")

    def test_a_turn_of_only_refused_lines_costs_no_time(self):
        self.llm.actions = "ACTIONS:\nFROBNICATE the widget"
        self.engine.play("do something weird")
        self.assertEqual(self.engine.game.narrative.minutes, 0)

    def test_a_none_turn_costs_one_minute(self):
        self.llm.actions = "ACTIONS:\nNONE"
        self.engine.play("look around")
        self.assertEqual(self.engine.game.narrative.minutes, 1)
        self.assertTrue(
            self.engine.game.memory.full_event_log[-1].endswith(
                'Orton tries: "look around" About 1 minute passes.'
            )
        )

    def test_a_none_turn_tells_the_narrator_nothing_typed_happens(self):
        self.llm.actions = "ACTIONS:\nNONE"
        self.engine.play("lock the door")
        self.assertIn(
            f" - {NOTHING_DONE_FACT.format(name='Orton')}\n - About 1 minute passes.",
            self.llm.narrator_prompts[-1],
        )

    def test_the_nothing_done_fact_stays_out_of_memory(self):
        self.llm.actions = "ACTIONS:\nNONE"
        self.engine.play("lock the door")
        self.assertNotIn("[SCENE]", self.engine.game.memory.full_event_log[-1])

    def test_a_turn_with_an_action_or_a_refused_line_has_no_nothing_done_fact(self):
        for actions in ("ACTIONS:\nWAIT 10m", "ACTIONS:\nFROBNICATE the widget"):
            self.llm.actions = actions
            self.engine.play("do it")
            self.assertNotIn("Nothing else in [SCENE]", self.llm.narrator_prompts[-1])

    def test_the_narrator_failure_records_the_same_entry(self):
        self.engine.play("go out")
        narrated = self.engine.game.memory.full_event_log[-1]
        self.engine.reset()
        self.engine.create_character(ORTON)

        def failing(prompt: str) -> str:
            raise LLMError("narrator offline")

        engine_module.llm.query_narrator = failing
        self.engine.play("go out")
        self.assertEqual(self.engine.game.memory.full_event_log[-1], narrated)

    def test_the_entry_holds_no_narrator_text(self):
        self.llm.story = "STORY:\nYou kill it dead.\n\nEVENT:\nOrton killed a zombie"
        self.engine.play("go out")
        entry = self.engine.game.memory.full_event_log[-1]
        self.assertNotIn("kill it dead", entry)
        self.assertNotIn("killed a zombie", entry)

    def test_the_narrator_failure_entry_names_no_zombie_id(self):
        self.llm.actions = "ACTIONS:\nATTACK z7"

        def failing(prompt: str) -> str:
            raise LLMError("narrator offline")

        engine_module.llm.query_narrator = failing
        self.engine.play("attack it")
        self.assertNotRegex(self.engine.game.memory.full_event_log[-1], r"\bz\d+\b")


class RefusalWordingTests(EngineTestCase):
    """Spec 10, Failures."""

    def _refusals(self) -> list[str]:
        prompt = self.llm.narrator_prompts[-1]
        return [line for line in prompt.splitlines() if "Refused" in line and "[" not in line]

    def test_a_malformed_line_is_refused_in_words_without_the_raw_line(self):
        self.llm.actions = 'ACTIONS:\nTALK Emma "Emma, I need help"'
        self.engine.play("talk")
        refusals = [line for line in self._refusals() if "tried to talk" in line]
        self.assertEqual(len(refusals), 1, self._refusals())
        self.assertNotIn("TALK", refusals[0])
        self.assertNotIn("Emma, I need help", refusals[0])

    def test_an_unknown_verb_is_refused_in_words_without_the_raw_line(self):
        self.llm.actions = "ACTIONS:\nFROBNICATE the widget"
        self.engine.play("do something weird")
        self.assertFalse(any("the widget" in line for line in self._refusals()))

    def test_every_parse_failure_path_is_refused_in_plain_words(self):
        scripts = {
            "bad talk": (False, 'ACTIONS:\nTALK Emma "Emma, I need help"'),
            "bad wait": (False, "ACTIONS:\nWAIT soon"),
            "unknown verb": (False, "ACTIONS:\nFROBNICATE the widget"),
            "removed verb": (False, "ACTIONS:\nCRAFT a spear"),
            "not json": (True, "not json at all"),
            "malformed plan": (True, '{"steps": 3}'),
            "unknown structured verb": (True, '{"actions": [{"verb": "FROB"}]}'),
        }
        for label, (structured, reply) in scripts.items():
            with self.subTest(label):
                self.llm.structured = structured
                self.llm.actions = reply
                self.engine.play("do something")
                refusals = re.findall(r"Refused:[^.]*\.", self.llm.narrator_prompts[-1])
                self.assertTrue(refusals, label)
                for line in refusals:
                    self.assertNotRegex(line, r"\d", line)
                    self.assertNotRegex(line, r"(?<!\w)'|'(?!\w)|[\"{}\[\]]", line)
                    self.assertNotIn("one of", line)
                    self.assertFalse(line.removeprefix("Refused:").count(":"), line)
                    self.assertNotRegex(line, r"\b[A-Z]{2,}\b", line)

    def test_a_known_verb_that_failed_to_parse_is_named_in_lower_case(self):
        self.llm.actions = "ACTIONS:\nWAIT soon"
        self.engine.play("wait")
        refusals = [line for line in self._refusals() if "tried to wait" in line]
        self.assertEqual(len(refusals), 1, self._refusals())

    def test_a_known_structured_verb_with_a_bad_field_is_named(self):
        self.llm.structured = True
        self.llm.actions = (
            '{"actions": [{"verb": "EXERCISE", "exercise": "pushups", "minutes": "ten"}]}'
        )
        self.engine.play("exercise")
        refusals = [line for line in self._refusals() if "tried to exercise" in line]
        self.assertEqual(len(refusals), 1, self._refusals())


class PayloadTests(EngineTestCase):
    """Spec 10, What the player sees."""

    def test_outbreak_day_is_none_before_the_outbreak(self):
        state = self.engine.state()
        self.assertIsNone(state["outbreak_day"])
        self.assertNotIn("apocalypse_stage", state)

    def test_outbreak_day_counts_from_one(self):
        manager = self.engine.game
        manager.advance_clock(2760)
        manager.world.outbreak_started_at = 2760
        self.assertEqual(self.engine.state()["outbreak_day"], 1)
        manager.advance_clock(1440)
        self.assertEqual(self.engine.state()["outbreak_day"], 2)

    def test_each_npc_carries_following(self):
        manager = self.engine.game
        manager.player.current_location_id = "zone_building"
        npc_of(manager, "Emma").following = True
        by_name = {npc["name"]: npc for npc in self.engine.state()["npcs"]}
        self.assertIs(by_name["Emma"]["following"], True)
        self.assertIs(by_name["Marcus"]["following"], False)

    def test_the_payload_drops_the_player_status_list(self):
        self.assertNotIn("status_effects", self.engine.state())


class NarratorBudgetTests(EngineTestCase):
    """Spec 10, Token budget: the narrator prompt's character budget."""

    def tearDown(self):
        llm.reset_chars_per_token()
        super().tearDown()

    def test_the_budget_is_the_context_less_reply_and_margin_in_characters(self):
        llm.reset_chars_per_token()
        with (
            mock.patch.dict(
                config.llm._values, {"context_tokens": 3000, "narrator_max_tokens": 500}
            ),
            mock.patch.object(
                engine_module.ContextBuilder,
                "build_narrator_prompt",
                autospec=True,
                return_value="prompt",
            ) as build,
        ):
            self.engine.play("go out")
        expected = int((3000 - 500 - BUDGET_MARGIN_TOKENS) * 3.5) - len(NARRATOR_SYSTEM_PROMPT)
        self.assertEqual(build.call_args.kwargs["max_chars"], expected)

    def test_the_budget_follows_the_measured_ratio(self):
        with (
            mock.patch.object(llm, "chars_per_token", return_value=2.0),
            mock.patch.object(
                engine_module.ContextBuilder,
                "build_narrator_prompt",
                autospec=True,
                return_value="prompt",
            ) as build,
        ):
            self.engine.play("go out")
        expected = int((8192 - 800 - BUDGET_MARGIN_TOKENS) * 2.0) - len(NARRATOR_SYSTEM_PROMPT)
        self.assertEqual(build.call_args.kwargs["max_chars"], expected)


class SequencedNarrator(ScriptedLLM):
    """Answers each narrator call with the next scripted reply; an LLMError instance is raised."""

    def __init__(self, replies: list[str | LLMError], **kwargs):
        super().__init__(**kwargs)
        self.replies = replies

    def query_narrator(self, prompt: str) -> str:
        self.narrator_prompts.append(prompt)
        reply = self.replies.pop(0)
        if isinstance(reply, LLMError):
            raise reply
        return reply


class FactCheckRetryTests(EngineTestCase):
    """Spec 10, The fact check: one retry when the story conflicts with the engine's state."""

    FIRST = "STORY:\nFirst story.\n\nOPTIONS:\n1. Go on\n2. Wait"
    SECOND = "STORY:\nSecond story.\n\nOPTIONS:\n1. Rest\n2. Hide"
    FACTS = ["z1 staggers back but stays on its feet.", "You are winded."]
    CORRECTION = "The zombie is still alive at the end of this turn."

    def script(self, replies: list[str | LLMError], *results: list[str]) -> FakeStoryChecker:
        self.llm = SequencedNarrator(replies, actions=MOVE_OUT_ACTIONS)
        engine_module.llm.query_parser = self.llm.query_parser
        engine_module.llm.query_narrator = self.llm.query_narrator
        checker = cast(FakeStoryChecker, self.engine.factcheck)
        checker.results = [list(result) for result in results]
        return checker

    def setUp(self):
        super().setUp()
        patcher = mock.patch.object(
            engine_module.SimulationCore, "resolve", return_value=list(self.FACTS)
        )
        patcher.start()
        self.addCleanup(patcher.stop)
        self.engine.game.world.zombies["z1"] = ZombieEntity(
            zombie_id="z1",
            zone_id=self.engine.game.player.current_location_id,
            health=2.0,
            speed_type=3,
            speed_mod=0.6,
            lunger=False,
            strength=3,
            memory=800,
            sight=2,
            hearing=2,
            state=ZombieState.CHASING,
            gap=3.0,
        )

    def test_the_checker_gets_the_story_and_the_alive_question(self):
        checker = self.script([self.FIRST])
        self.engine.play("go out")
        ((story, questions),) = checker.calls
        self.assertEqual(story, "First story.")
        self.assertEqual([q.correction for q in questions], [self.CORRECTION])

    def test_a_killed_zombie_hands_the_checker_the_dead_question(self):
        checker = self.script([self.FIRST])
        del self.engine.game.world.zombies["z1"]
        self.engine.play("go out")
        ((_, questions),) = checker.calls
        self.assertEqual(
            [q.correction for q in questions], ["The zombie is dead at the end of this turn."]
        )

    def test_a_clean_story_is_not_retried(self):
        checker = self.script([self.FIRST], [])
        result = self.engine.play("go out")
        self.assertEqual(len(self.llm.narrator_prompts), 1)
        self.assertEqual(len(checker.calls), 1)
        self.assertEqual(result["story_text"], "First story.")

    def test_the_retry_prompt_carries_a_correction_with_the_correction_facts(self):
        checker = self.script([self.FIRST, self.SECOND], [self.CORRECTION], [])
        self.engine.play("go out")
        first, retry = self.llm.narrator_prompts
        self.assertNotIn("[CORRECTION]", first)
        correction = retry[retry.index("[CORRECTION]") :]
        self.assertEqual(
            correction,
            "[CORRECTION]\nYour last story got these facts wrong. Write the story again so it "
            "agrees with them and with every outcome:\n" + self.CORRECTION + "\n",
        )
        self.assertEqual([call[0] for call in checker.calls], ["First story.", "Second story."])

    def test_a_retry_with_fewer_conflicts_is_used(self):
        self.script([self.FIRST, self.SECOND], ["a fact"], [])
        result = self.engine.play("go out")
        self.assertEqual(result["story_text"], "Second story.")
        self.assertEqual(result["options"], ["1. Rest", "2. Hide"])
        self.assertEqual(self.engine.game.memory.last_story, "Second story.")

    def test_a_retry_with_equal_conflicts_is_used(self):
        self.script([self.FIRST, self.SECOND], ["a fact"], ["a fact"])
        result = self.engine.play("go out")
        self.assertEqual(result["story_text"], "Second story.")

    def test_a_worse_retry_is_dropped_for_the_first_story(self):
        self.script([self.FIRST, self.SECOND], ["a fact"], ["a fact", "another"])
        result = self.engine.play("go out")
        self.assertEqual(result["story_text"], "First story.")
        self.assertEqual(result["options"], ["1. Go on", "2. Wait"])
        self.assertEqual(self.engine.game.memory.last_story, "First story.")

    def test_a_retry_error_keeps_the_first_story(self):
        self.script([self.FIRST, LLMError("dropped")], ["a fact"])
        result = self.engine.play("go out")
        self.assertEqual(result["story_text"], "First story.")
        self.assertEqual(len(self.llm.narrator_prompts), 2)

    def test_a_retry_with_a_blank_story_keeps_the_first_story(self):
        self.script([self.FIRST, "STORY:\n\nOPTIONS:\n1. Rest"], ["a fact"], [])
        result = self.engine.play("go out")
        self.assertEqual(result["story_text"], "First story.")

    def test_there_is_never_a_second_retry(self):
        self.script([self.FIRST, self.SECOND], ["a fact"], ["a fact"], ["a fact"])
        self.engine.play("go out")
        self.assertEqual(len(self.llm.narrator_prompts), 2)

    def test_the_retry_prompt_is_rebuilt_inside_the_budget_less_the_block(self):
        self.script([self.FIRST, self.SECOND], ["a fact"], [])
        with mock.patch.object(
            engine_module.ContextBuilder,
            "build_narrator_prompt",
            autospec=True,
            return_value="prompt",
        ) as build:
            self.engine.play("go out")
        first, retry = build.call_args_list
        block = self.llm.narrator_prompts[1][len("prompt") :]
        self.assertEqual(retry.kwargs["max_chars"], first.kwargs["max_chars"] - len(block))

    def test_a_turn_without_questions_is_not_checked(self):
        checker = self.script([self.FIRST])
        with mock.patch.object(
            engine_module.SimulationCore, "resolve", return_value=["You are winded."]
        ):
            self.engine.play("go out")
        self.assertEqual(checker.calls, [])


class MissingOptionsTests(EngineTestCase):
    """A reply with no OPTIONS section gets one follow-up call asking for the options alone."""

    NO_OPTIONS = "STORY:\nYou walk out."
    OPTIONS_ONLY = "OPTIONS:\n- Check the mailboxes\n- Knock on a door"

    def script(self, replies: list[str | LLMError]) -> None:
        self.llm = SequencedNarrator(replies, actions=MOVE_OUT_ACTIONS)
        engine_module.llm.query_parser = self.llm.query_parser
        engine_module.llm.query_narrator = self.llm.query_narrator

    def test_the_follow_up_options_join_the_first_story(self):
        self.script([self.NO_OPTIONS, self.OPTIONS_ONLY])
        result = self.engine.play("go out")
        self.assertEqual(result["story_text"], "You walk out.")
        self.assertEqual(result["options"], ["Check the mailboxes", "Knock on a door"])
        self.assertEqual(self.engine.game.memory.last_story, "You walk out.")

    def test_the_follow_up_prompt_shows_the_story_and_asks_for_options_only(self):
        self.script([self.NO_OPTIONS, self.OPTIONS_ONLY])
        self.engine.play("go out")
        first, follow_up = self.llm.narrator_prompts
        block = follow_up[follow_up.index("[STORY WRITTEN]") :]
        self.assertEqual(
            block,
            "[STORY WRITTEN]\nYou already wrote this turn's story, below. Reply with only "
            "its OPTIONS section.\nYou walk out.\n",
        )
        self.assertNotIn("[STORY WRITTEN]", first)

    def test_options_none_is_not_followed_up(self):
        self.script(["STORY:\nYou wait.\n\nOPTIONS:\nNONE"])
        result = self.engine.play("go out")
        self.assertEqual(result["options"], [])
        self.assertEqual(len(self.llm.narrator_prompts), 1)

    def test_a_turn_that_ends_the_game_is_not_followed_up(self):
        self.script([self.NO_OPTIONS])
        make_dying(self.engine.game.player)
        self.llm.actions = "ACTIONS:\nWAIT 10m"
        self.engine.play("wait here")
        self.assertTrue(self.engine.game.narrative.game_over)
        self.assertEqual(len(self.llm.narrator_prompts), 1)

    def test_a_follow_up_error_leaves_no_options(self):
        self.script([self.NO_OPTIONS, LLMError("dropped")])
        result = self.engine.play("go out")
        self.assertEqual(result["story_text"], "You walk out.")
        self.assertEqual(result["options"], [])

    def test_a_follow_up_with_no_options_is_not_repeated(self):
        self.script([self.NO_OPTIONS, "Nothing useful."])
        result = self.engine.play("go out")
        self.assertEqual(result["options"], [])
        self.assertEqual(len(self.llm.narrator_prompts), 2)

    def test_the_follow_up_prompt_is_rebuilt_inside_the_budget_less_the_block(self):
        self.script([self.NO_OPTIONS, self.OPTIONS_ONLY])
        with mock.patch.object(
            engine_module.ContextBuilder,
            "build_narrator_prompt",
            autospec=True,
            return_value="prompt",
        ) as build:
            self.engine.play("go out")
        first, follow_up = build.call_args_list
        block = self.llm.narrator_prompts[1][len("prompt") :]
        self.assertEqual(follow_up.kwargs["max_chars"], first.kwargs["max_chars"] - len(block))
