"""GameEngine turn orchestration, with the LLM and the embedding model stubbed.

Two LLM calls per turn now, not one: the parser proposes actions (script via
`ScriptedLLM(actions=...)`), the engine validates and simulates them, and the
narrator describes what already happened (script via `ScriptedLLM(story=...)`).
"""

import unittest

import adapters.engine as engine_module
from adapters import persistence
from adapters.engine import GameEngine
from adapters.llm import LLMError
from tests.support import FakeMemory, IsolatedSaveTestCase, ScriptedLLM

MOVE_NORTH_ACTIONS = "ACTIONS:\nMOVE_TO north\nUPDATE_RELATIONSHIP Emma affection +12\nADD_GOAL short_term Find a weapon"
MOVE_NORTH_STORY = "STORY:\nYou walk north into the office.\n\nEVENT:\nOrton entered the office"


class EngineTestCase(IsolatedSaveTestCase):
    """Builds an engine whose slow edges are replaced."""

    def setUp(self):
        super().setUp()
        self.llm = ScriptedLLM(actions=MOVE_NORTH_ACTIONS, story=MOVE_NORTH_STORY)
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
        self.llm.actions = "ACTIONS:\nMOVE_TO Atlantis\nADD_GOAL short_term Survive"
        self.llm.story = "STORY:\nYou try.\n\nEVENT:\nOrton tried"
        result = self.engine.play("go somewhere")
        self.assertEqual(result["story_text"], "You try.")
        # The bad action was refused, the good one still applied.
        self.assertEqual(result["current_location"], "Hallway")
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
    def test_parser_failure_surfaces_as_story_text(self):
        self.llm.error = LLMError("LM Studio is not running")
        result = self.engine.play("look around")
        self.assertIn("LM Studio is not running", result["story_text"])

    def test_parser_failure_leaves_state_untouched(self):
        self.engine.play("go north")  # a good turn first
        log_before = list(self.engine.manager.memory.full_event_log)

        self.llm.error = LLMError("connection refused")
        result = self.engine.play("go south")

        self.assertEqual(result["current_location"], "Office")
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

        self.llm = FailingNarrator(actions=MOVE_NORTH_ACTIONS)
        engine_module.llm.query_parser = self.llm.query_parser
        engine_module.llm.query_narrator = self.llm.query_narrator

        result = self.engine.play("go north")

        self.assertIn("LM Studio dropped the connection", result["story_text"])
        self.assertEqual(self.engine.manager.player.current_location_id, "location_id_office")
        reloaded = persistence.load(self.save_path)
        self.assertEqual(reloaded.player.current_location_id, "location_id_office")

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
        self.llm.actions = "ACTIONS:\nTAKE Crowbar"
        self.engine.play("take the crowbar")
        self.engine.reset()
        office = self.engine.manager.world.locations["location_id_office"]
        self.assertIn("Crowbar", [e.item.name for e in office.entities])


if __name__ == "__main__":
    unittest.main()
