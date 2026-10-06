"""The Flask routes, driven through Flask's real test client."""

import io
import json
import unittest

import adapters.engine as engine_module
import app as app_module
from adapters.engine import GameEngine
from adapters.llm import LLMError
from modules.stats import CharacterStat
from tests.support import FakeMemory, IsolatedSaveTestCase, ScriptedLLM

ACTIONS = "ACTIONS:\nMOVE_TO out\nADD_GOAL short_term Find a weapon"
STORY = "STORY:\nYou walk out into the building.\n\nEVENT:\nOrton entered the building"


class RouteTestCase(IsolatedSaveTestCase):
    def setUp(self):
        super().setUp()
        self.llm = ScriptedLLM(actions=ACTIONS, story=STORY)
        self._original_parser = engine_module.llm.query_parser
        self._original_narrator = engine_module.llm.query_narrator
        self._original_summary = engine_module.llm.query_summary
        engine_module.llm.query_parser = self.llm.query_parser
        engine_module.llm.query_narrator = self.llm.query_narrator
        engine_module.llm.query_summary = self.llm.query_summary
        self._original_memory = engine_module.SemanticMemory
        engine_module.SemanticMemory = FakeMemory

        engine = GameEngine()
        self._original_engine = app_module._engine
        app_module._engine = engine
        self.engine = engine

        app_module.app.config["TESTING"] = True
        self.client = app_module.app.test_client()

    def tearDown(self):
        app_module._engine = self._original_engine
        engine_module.llm.query_parser = self._original_parser
        engine_module.llm.query_narrator = self._original_narrator
        engine_module.llm.query_summary = self._original_summary
        engine_module.SemanticMemory = self._original_memory
        super().tearDown()


class IndexTests(RouteTestCase):
    def test_index_renders(self):
        response = self.client.get("/")
        self.assertEqual(response.status_code, 200)
        self.assertIn(b"Local LLM RPG", response.data)

    def test_index_markup_matches_the_ids_the_script_expects(self):
        response = self.client.get("/")
        for element_id in (
            b'id="story-display"',
            b'id="location-status"',
            b'id="vitals"',
            b'id="inventory-list"',
            b'id="equipment-list"',
            b'id="npc-list"',
            b'id="goal-list"',
            b'id="quest-list"',
            b'id="trait-list"',
            b'id="perk-list"',
            b'id="attribute-grid"',
            b'id="save-button"',
            b'id="load-button"',
            b'id="load-input"',
        ):
            self.assertIn(element_id, response.data)


class StatusEffectPayloadTests(RouteTestCase):
    """Spec 03, What the narrator and the player see."""

    def test_play_carries_status_effects_and_no_hunger_or_thirst(self):
        stats = self.engine.manager.player.stats
        stats.set(CharacterStat.HUNGER, 0.5)
        stats.set(CharacterStat.FATIGUE, 0.61)
        stats.set(CharacterStat.THIRST, 0.13)
        payload = self.client.post("/play", json={"input": "look"}).get_json()
        self.assertEqual(
            [(m["type"], m["name"]) for m in payload["effects"]][:3],
            [("hungry", "Very Hungry"), ("thirst", "Slightly Thirsty"), ("tired", "Drowsy")],
        )
        self.assertEqual(payload["effects"][0]["level"], 3)
        for gone in ("hunger", "thirst"):
            self.assertNotIn(gone, payload)
            self.assertNotIn(gone, payload["vitals"])

    def test_state_lists_status_effects_highest_level_first(self):
        stats = self.engine.manager.player.stats
        stats.set(CharacterStat.THIRST, 0.13)
        stats.set(CharacterStat.HUNGER, 0.5)
        levels = [m["level"] for m in self.client.get("/state").get_json()["effects"]]
        self.assertEqual(levels, sorted(levels, reverse=True))


class StateTests(RouteTestCase):
    def test_state_reports_the_starting_world(self):
        # Orton now starts alone in his apartment; move to the building to
        # exercise the NPC-presence check below.
        self.engine.manager.player.current_location_id = "zone_building"
        payload = self.client.get("/state").get_json()
        self.assertEqual(payload["current_location"], "Your Building")
        self.assertEqual(payload["day"], 1)
        self.assertIn("Emma", payload["npcs_present"])
        self.assertEqual(payload["story_text"], "")

    def test_inventory_is_a_list(self):
        # The frontend iterates this.
        payload = self.client.get("/state").get_json()
        self.assertIsInstance(payload["inventory"], list)


class PlayTests(RouteTestCase):
    def test_play_runs_a_turn(self):
        response = self.client.post("/play", json={"input": "go out"})
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["story_text"], "You walk out into the building.")
        self.assertEqual(payload["current_location"], "Your Building")
        self.assertIn("Find a weapon", payload["goals"]["short_term"])

    def test_player_input_reaches_the_prompt(self):
        self.client.post("/play", json={"input": "peer down the corridor"})
        self.assertIn("peer down the corridor", self.llm.prompts[-1])

    def test_state_reflects_the_turn_afterwards(self):
        self.client.post("/play", json={"input": "go out"})
        payload = self.client.get("/state").get_json()
        self.assertEqual(payload["current_location"], "Your Building")

    def test_missing_input_is_rejected(self):
        response = self.client.post("/play", json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    def test_blank_input_is_rejected(self):
        response = self.client.post("/play", json={"input": "   "})
        self.assertEqual(response.status_code, 400)

    def test_non_json_body_is_rejected_not_crashed(self):
        response = self.client.post("/play", data="not json", content_type="text/plain")
        self.assertEqual(response.status_code, 400)

    def test_llm_failure_returns_200_with_an_error_story(self):
        # The frontend shows story_text; a 500 would surface a less useful
        # message and lose the rest of the state payload.
        self.llm.error = LLMError("LM Studio is not running")
        response = self.client.post("/play", json={"input": "look"})
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertIn("LM Studio is not running", payload["story_text"])
        self.assertEqual(payload["current_location"], "Your Apartment")


class SaveLoadRouteTests(RouteTestCase):
    def test_export_downloads_a_save_file(self):
        response = self.client.get("/save/export")
        self.assertEqual(response.status_code, 200)
        self.assertIn("attachment", response.headers.get("Content-Disposition", ""))
        payload = response.get_json()
        self.assertEqual(payload["player"]["current_location_id"], "zone_home")

    def test_import_loads_an_exported_save(self):
        self.client.post("/play", json={"input": "go out"})
        exported = self.client.get("/save/export").get_json()
        exported["player"]["current_location_id"] = "zone_building"

        response = self.client.post(
            "/save/import",
            data={
                "save": (
                    io.BytesIO(json.dumps(exported).encode("utf-8")),
                    "orton-save.json",
                )
            },
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["current_location"], "Your Building")

    def test_import_rejects_a_non_json_file(self):
        response = self.client.post(
            "/save/import",
            data={"save": (io.BytesIO(b"not json"), "orton-save.json")},
            content_type="multipart/form-data",
        )
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    def test_import_without_a_file_is_rejected(self):
        response = self.client.post("/save/import", data={}, content_type="multipart/form-data")
        self.assertEqual(response.status_code, 400)


class ResetTests(RouteTestCase):
    def test_reset_starts_over(self):
        self.client.post("/play", json={"input": "go out"})
        response = self.client.post("/reset")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["message"], "Game has been reset.")
        self.assertEqual(payload["state"]["current_location"], "Your Apartment")
        self.assertEqual(payload["state"]["goals"]["short_term"], [])

    def test_state_after_reset_is_fresh(self):
        self.client.post("/play", json={"input": "go out"})
        self.client.post("/reset")
        payload = self.client.get("/state").get_json()
        self.assertEqual(payload["current_location"], "Your Apartment")


class LazyEngineTests(IsolatedSaveTestCase):
    def test_importing_app_does_not_build_an_engine(self):
        # Building one loads the save and can pull in the embedding model, which
        # must not happen at import time.
        self.assertIsNone(app_module._engine)


if __name__ == "__main__":
    unittest.main()
