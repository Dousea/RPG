"""GameEngine turn orchestration, with the LLM and the embedding model stubbed."""

import unittest

import adapters.engine as engine_module
from adapters import persistence
from adapters.engine import GameEngine
from adapters.llm import LLMError
from tests.support import FakeMemory, IsolatedSaveTestCase, ScriptedLLM

TURN = (
    "STORY:\nYou walk north into the office.\n\n"
    "EVENT:\nOrton entered the office\n\n"
    "ACTIONS:\nMOVE_TO north\nUPDATE_RELATIONSHIP Emma affection +12\n"
    "ADD_GOAL short_term Find a weapon"
)


class EngineTestCase(IsolatedSaveTestCase):
    """Builds an engine whose slow edges are replaced."""

    def setUp(self):
        super().setUp()
        self.llm = ScriptedLLM(response=TURN)
        self._original_gm = engine_module.llm.query_game_master
        self._original_summary = engine_module.llm.query_summary
        engine_module.llm.query_game_master = self.llm.query_game_master
        engine_module.llm.query_summary = self.llm.query_summary

        self.engine = GameEngine()
        self.engine.memory = FakeMemory()

    def tearDown(self):
        engine_module.llm.query_game_master = self._original_gm
        engine_module.llm.query_summary = self._original_summary
        super().tearDown()


class TurnTests(EngineTestCase):
    def test_turn_returns_story_and_applies_actions(self):
        result = self.engine.play("go north")
        self.assertEqual(result["story_text"], "You walk north into the office.")
        self.assertEqual(result["current_location"], "Office")
        self.assertIn("Find a weapon", result["goals"]["short_term"])

    def test_turn_records_the_event_in_both_tiers(self):
        self.engine.play("go north")
        memory = self.engine.manager.memory
        self.assertIn("Orton entered the office", memory.full_event_log)
        self.assertIn("Orton entered the office", memory.recent_events)

    def test_turn_reindexes_memory(self):
        self.engine.play("go north")
        self.assertEqual(
            self.engine.memory.rebuilt_with[-1],
            self.engine.manager.memory.full_event_log,
        )

    def test_recalled_memories_reach_the_prompt(self):
        self.engine.manager.memory.full_event_log.append("Orton heard sirens.")
        self.engine.memory.next_hits = [0]
        self.engine.play("what was that noise")
        self.assertIn("Orton heard sirens.", self.llm.prompts[-1])

    def test_out_of_range_recall_hits_are_ignored(self):
        # A stale index must not blow up the turn.
        self.engine.memory.next_hits = [99]
        result = self.engine.play("go north")
        self.assertEqual(result["current_location"], "Office")

    def test_turn_persists(self):
        self.engine.play("go north")
        reloaded = persistence.load(self.save_path)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.player.current_location_id, "location_id_office")
        self.assertIn("Find a weapon", reloaded.narrative.goals["short_term"])
        self.assertEqual(
            reloaded.relationship_manager.get_affinity("npc_emma", "player"), 12
        )

    def test_snapshot_shape(self):
        result = self.engine.play("go north")
        self.assertIsInstance(result["inventory"], list)
        self.assertIsInstance(result["npcs_present"], list)
        self.assertIsInstance(result["goals"]["short_term"], list)
        self.assertEqual(result["day"], 1)

    def test_npcs_present_tracks_the_player(self):
        before = self.engine.state()
        self.assertIn("Emma", before["npcs_present"])  # hallway
        after = self.engine.play("go north")
        self.assertNotIn("Emma", after["npcs_present"])  # office

    def test_failed_actions_do_not_abort_the_turn(self):
        self.llm.response = (
            "STORY:\nYou try.\n\nEVENT:\nOrton tried\n\n"
            "ACTIONS:\nMOVE_TO Atlantis\nADD_GOAL short_term Survive"
        )
        result = self.engine.play("go somewhere")
        self.assertEqual(result["story_text"], "You try.")
        # The bad action was skipped, the good one still applied.
        self.assertEqual(result["current_location"], "Hallway")
        self.assertIn("Survive", result["goals"]["short_term"])

    def test_refused_actions_are_fed_back_into_the_next_prompt(self):
        # Prose is written before the deltas are applied, so a refused delta
        # leaves the story describing something that never happened. The engine
        # cannot un-write it; it can tell the next turn to reconcile.
        self.llm.response = (
            "STORY:\nYou pocket the medkit.\n\nEVENT:\nOrton took a medkit\n\n"
            "ACTIONS:\nTAKE Medkit"
        )
        self.engine.play("take the medkit")
        self.assertEqual(len(self.engine.manager.narrative.pending_corrections), 1)
        self.assertIn("TAKE Medkit", self.engine.manager.narrative.pending_corrections[0])

        self.llm.response = TURN
        self.engine.play("go north")
        self.assertIn("[CONTINUITY]", self.llm.prompts[-1])
        self.assertIn("TAKE Medkit", self.llm.prompts[-1])
        # A clean turn clears them again.
        self.assertEqual(self.engine.manager.narrative.pending_corrections, [])


class SummarizationTests(EngineTestCase):
    def test_summary_is_produced_once_enough_events_accumulate(self):
        for i in range(9):
            self.engine.manager.record_event(f"Event {i}")
        self.engine.play("go north")  # the tenth event
        self.assertEqual(self.engine.manager.memory.summaries, ["A summary."])
        self.assertEqual(len(self.llm.summarized), 1)

    def test_no_summary_before_the_threshold(self):
        self.engine.play("go north")
        self.assertEqual(self.engine.manager.memory.summaries, [])
        self.assertEqual(self.llm.summarized, [])


class FailureTests(EngineTestCase):
    def test_llm_failure_surfaces_as_story_text(self):
        self.llm.error = LLMError("LM Studio is not running")
        result = self.engine.play("look around")
        self.assertIn("LM Studio is not running", result["story_text"])

    def test_llm_failure_leaves_state_untouched(self):
        self.engine.play("go north")  # a good turn first
        log_before = list(self.engine.manager.memory.full_event_log)

        self.llm.error = LLMError("connection refused")
        result = self.engine.play("go south")

        self.assertEqual(result["current_location"], "Office")
        self.assertEqual(self.engine.manager.memory.full_event_log, log_before)
        reloaded = persistence.load(self.save_path)
        self.assertEqual(reloaded.memory.full_event_log, log_before)

    def test_summarization_failure_does_not_lose_the_turn(self):
        def boom(text):
            raise LLMError("summarizer offline")

        engine_module.llm.query_summary = boom
        for i in range(9):
            self.engine.manager.record_event(f"Event {i}")

        result = self.engine.play("go north")
        self.assertEqual(result["story_text"], "You walk north into the office.")
        self.assertEqual(self.engine.manager.memory.summaries, [])
        self.assertIn("Orton entered the office", self.engine.manager.memory.full_event_log)


class LifecycleTests(EngineTestCase):
    def test_engine_resumes_from_a_save(self):
        self.engine.play("go north")
        resumed = GameEngine()
        self.assertEqual(resumed.manager.player.current_location_id, "location_id_office")
        self.assertIn("Find a weapon", resumed.manager.narrative.goals["short_term"])

    def test_reset_clears_everything(self):
        self.engine.play("go north")
        result = self.engine.reset()
        self.assertEqual(result["current_location"], "Hallway")
        self.assertEqual(result["goals"]["short_term"], [])
        self.assertEqual(self.engine.manager.memory.full_event_log, [])
        self.assertEqual(
            self.engine.manager.relationship_manager.get_affinity("npc_emma", "player"), 0
        )

    def test_reset_writes_a_fresh_save(self):
        self.engine.play("go north")
        self.engine.reset()
        reloaded = persistence.load(self.save_path)
        self.assertIsNotNone(reloaded)
        self.assertEqual(reloaded.player.current_location_id, "location_id_hallway")

    def test_reset_does_not_leak_previous_world_state(self):
        self.engine.play("go north")
        self.engine.manager.apply_action("TAKE Crowbar")
        self.engine.reset()
        office = self.engine.manager.world.locations["location_id_office"]
        self.assertIn("Crowbar", [e.item.name for e in office.entities])


if __name__ == "__main__":
    unittest.main()
