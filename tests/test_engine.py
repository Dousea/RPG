"""GameEngine turn orchestration, with the LLM and the embedding model stubbed.

Two LLM calls per turn now, not one: the parser proposes actions (script via
`ScriptedLLM(actions=...)`), the engine validates and simulates them, and the
narrator describes what already happened (script via `ScriptedLLM(story=...)`).
"""

import copy
import unittest

import adapters.engine as engine_module
from adapters import persistence
from adapters.engine import GameEngine
from adapters.llm import LLMError
from modules.entity.item import ItemEntity
from tests.support import FakeMemory, IsolatedSaveTestCase, ScriptedLLM
from tests.test_persistence import V2_SAVE
from tests.test_simulation import LETHAL_ITEM

MOVE_OUT_ACTIONS = "ACTIONS:\nMOVE_TO out\nUPDATE_RELATIONSHIP Emma affection +12\nADD_GOAL short_term Find a weapon"
MOVE_OUT_STORY = "STORY:\nYou walk out into the building.\n\nEVENT:\nOrton entered the building"


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

        self.engine = GameEngine()
        self.engine.memory = FakeMemory()

    def tearDown(self):
        engine_module.llm.query_parser = self._original_parser
        engine_module.llm.query_narrator = self._original_narrator
        engine_module.llm.query_summary = self._original_summary
        super().tearDown()


class TurnTests(EngineTestCase):
    def test_turn_returns_story_and_applies_actions(self):
        result = self.engine.play("go out")
        self.assertEqual(result["story_text"], "You walk out into the building.")
        self.assertEqual(result["current_location"], "Your Building")
        self.assertIn("Find a weapon", result["goals"]["short_term"])

    def test_turn_records_the_event_in_both_tiers(self):
        self.engine.play("go out")
        memory = self.engine.manager.memory
        self.assertIn("Orton entered the building", memory.full_event_log)
        self.assertIn("Orton entered the building", memory.recent_events)

    def test_turn_reindexes_memory(self):
        self.engine.play("go out")
        self.assertEqual(
            self.engine.memory.rebuilt_with[-1],
            self.engine.manager.memory.full_event_log,
        )

    def test_player_input_reaches_the_parser_prompt(self):
        self.engine.play("peer down the corridor")
        self.assertIn("peer down the corridor", self.llm.prompts[-1])

    def test_recalled_memories_reach_the_narrator_prompt(self):
        self.engine.manager.memory.full_event_log.append("Orton heard sirens.")
        self.engine.memory.next_hits = [0]
        self.engine.play("what was that noise")
        self.assertIn("Orton heard sirens.", self.llm.narrator_prompts[-1])

    def test_out_of_range_recall_hits_are_ignored(self):
        # A stale index must not blow up the turn.
        self.engine.memory.next_hits = [99]
        result = self.engine.play("go out")
        self.assertEqual(result["current_location"], "Your Building")

    def test_turn_persists(self):
        self.engine.play("go out")
        reloaded = persistence.load(self.save_path)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.player.current_location_id, "zone_building")
        self.assertIn("Find a weapon", reloaded.narrative.goals["short_term"])
        self.assertEqual(
            reloaded.relationship_manager.get_affinity("npc_emma", "player"), 12
        )

    def test_snapshot_shape(self):
        result = self.engine.play("go out")
        self.assertIsInstance(result["inventory"], list)
        self.assertIsInstance(result["npcs_present"], list)
        self.assertIsInstance(result["goals"]["short_term"], list)
        self.assertEqual(result["day"], 1)
        self.assertIn("current_place", result)

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
        # MOVE_OUT_STORY has no OPTIONS section at all.
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

    def test_npcs_present_tracks_the_player(self):
        # Orton now starts alone in his apartment; Emma starts in the building.
        self.engine.manager.player.current_location_id = "zone_building"
        before = self.engine.state()
        self.assertIn("Emma", before["npcs_present"])  # in the building
        after = self.engine.play("go out")
        self.assertNotIn("Emma", after["npcs_present"])  # on the street

    def test_failed_actions_do_not_abort_the_turn(self):
        # MOVE_TO Atlantis is no longer a failure (MOVE_TO never fails, Task
        # 2) -- TAKE Medkit is still a real refusal, and stands in for it here.
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
        self.assertEqual(self.engine.manager.narrative.pending_corrections, [])
        self.assertIn("(Nothing to correct)", self.llm.narrator_prompts[-1])

    def test_unparseable_action_lines_are_surfaced_but_do_not_abort_the_turn(self):
        self.llm.actions = "ACTIONS:\nFROBNICATE the widget\nADD_GOAL short_term Survive"
        result = self.engine.play("do something weird")
        self.assertIn("Survive", result["goals"]["short_term"])
        self.assertIn("Refused:", self.llm.narrator_prompts[-1])


class DeathTests(EngineTestCase):
    def test_dead_game_makes_no_llm_calls(self):
        self.engine.manager.narrative.game_over = True
        self.engine.manager.narrative.death_cause = "Use Suspicious Vial: succeeded."
        result = self.engine.play("get up")
        self.assertEqual(self.llm.prompts, [])
        self.assertEqual(self.llm.narrator_prompts, [])
        self.assertIn("Use Suspicious Vial", result["story_text"])
        self.assertIn("new game", result["story_text"].lower())

    def test_reset_revives(self):
        self.engine.manager.narrative.game_over = True
        self.engine.manager.narrative.death_cause = "Orton starved."
        result = self.engine.reset()
        self.assertIs(result["game_over"], False)
        self.assertEqual(result["death_cause"], "")
        self.assertFalse(self.engine.manager.narrative.game_over)
        # A revived game plays turns normally again.
        played = self.engine.play("go out")
        self.assertEqual(len(self.llm.prompts), 1)
        self.assertEqual(played["current_location"], "Your Building")


class SummarizationTests(EngineTestCase):
    def test_summary_is_produced_once_enough_events_accumulate(self):
        for i in range(9):
            self.engine.manager.record_event(f"Event {i}")
        self.engine.play("go out")  # the tenth event
        self.assertEqual(self.engine.manager.memory.summaries, ["A summary."])
        self.assertEqual(len(self.llm.summarized), 1)

    def test_no_summary_before_the_threshold(self):
        self.engine.play("go out")
        self.assertEqual(self.engine.manager.memory.summaries, [])
        self.assertEqual(self.llm.summarized, [])


class FailureTests(EngineTestCase):
    def test_parser_failure_surfaces_as_story_text(self):
        self.llm.error = LLMError("LM Studio is not running")
        result = self.engine.play("look around")
        self.assertIn("LM Studio is not running", result["story_text"])

    def test_parser_failure_leaves_state_untouched(self):
        self.engine.play("go out")  # a good turn first
        log_before = list(self.engine.manager.memory.full_event_log)

        self.llm.error = LLMError("connection refused")
        result = self.engine.play("go out")

        self.assertEqual(result["current_location"], "Your Building")
        self.assertEqual(self.engine.manager.memory.full_event_log, log_before)
        reloaded = persistence.load(self.save_path)
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
        self.assertEqual(self.engine.manager.player.current_location_id, "zone_building")
        reloaded = persistence.load(self.save_path)
        self.assertEqual(reloaded.player.current_location_id, "zone_building")

    def test_summarization_failure_does_not_lose_the_turn(self):
        def boom(text):
            raise LLMError("summarizer offline")

        engine_module.llm.query_summary = boom
        for i in range(9):
            self.engine.manager.record_event(f"Event {i}")

        result = self.engine.play("go out")
        self.assertEqual(result["story_text"], "You walk out into the building.")
        self.assertEqual(self.engine.manager.memory.summaries, [])
        self.assertIn("Orton entered the building", self.engine.manager.memory.full_event_log)


class LifecycleTests(EngineTestCase):
    def test_engine_resumes_from_a_save(self):
        self.engine.play("go out")
        resumed = GameEngine()
        self.assertEqual(resumed.manager.player.current_location_id, "zone_building")
        self.assertIn("Find a weapon", resumed.manager.narrative.goals["short_term"])

    def test_reset_clears_everything(self):
        self.engine.play("go out")
        result = self.engine.reset()
        self.assertEqual(result["current_location"], "Your Apartment")
        self.assertEqual(result["goals"]["short_term"], [])
        self.assertEqual(self.engine.manager.memory.full_event_log, [])
        self.assertEqual(
            self.engine.manager.relationship_manager.get_affinity("npc_emma", "player"), 0
        )

    def test_reset_writes_a_fresh_save(self):
        self.engine.play("go out")
        self.engine.reset()
        reloaded = persistence.load(self.save_path)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.player.current_location_id, "zone_home")

    def test_reset_does_not_leak_previous_world_state(self):
        from modules.entity.item import ItemEntity

        self.engine.play("go out")  # now in zone_building
        self.llm.actions = "ACTIONS:\nTAKE First Aid Kit"
        self.engine.play("take the first aid kit")
        self.engine.reset()
        building = self.engine.manager.world.locations["zone_building"]
        item_names = [
            e.item.name for e in building.entities if isinstance(e, ItemEntity)
        ]
        self.assertIn("First Aid Kit", item_names)


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
        self.assertEqual(self.engine.manager.player.current_location_id, "zone_home")

    def test_import_persists_the_uploaded_save(self):
        self.engine.play("go out")  # now in the building
        exported = self.engine.export_save()

        self.engine.reset()  # back home; save file now says zone_home
        self.engine.import_save(exported)  # re-import the building save

        reloaded = persistence.load(self.save_path)
        self.assertEqual(reloaded.player.current_location_id, "zone_building")

    def test_import_route_migrates_a_v2_upload(self):
        # GameEngine.import_save calls persistence.from_saved_data directly,
        # so the /save/import route gets v2 -> v3 migration for free.
        result = self.engine.import_save(copy.deepcopy(V2_SAVE))
        self.assertIsNotNone(result)
        self.assertEqual(result["current_location"], "Your Building")
        self.assertEqual(result["current_place"], "the lobby")


class DeathPersistenceTests(EngineTestCase):
    """Task 4 added game_over/death_cause but left persisting them to us."""

    def test_death_survives_a_reload_through_the_engine(self):
        self.engine.manager.player.inventory.append(ItemEntity(item=LETHAL_ITEM))
        self.llm.actions = "ACTIONS:\nUSE_ITEM Suspicious Vial"

        self.engine.play("drink the vial")
        self.assertTrue(self.engine.manager.narrative.game_over)
        original_cause = self.engine.manager.narrative.death_cause
        self.assertTrue(original_cause)

        prompts_before = len(self.llm.prompts)
        narrator_prompts_before = len(self.llm.narrator_prompts)

        # A fresh engine, reading the same (redirected) save file, must come
        # back up already dead -- not resurrect Orton for one more turn.
        reloaded = GameEngine()
        reloaded.memory = FakeMemory()
        self.assertTrue(reloaded.manager.narrative.game_over)
        self.assertEqual(reloaded.manager.narrative.death_cause, original_cause)

        result = reloaded.play("try again")
        self.assertIn("Orton is dead", result["story_text"])
        # No parser/narrator call for a turn that can't happen anymore.
        self.assertEqual(len(self.llm.prompts), prompts_before)
        self.assertEqual(len(self.llm.narrator_prompts), narrator_prompts_before)


if __name__ == "__main__":
    unittest.main()
