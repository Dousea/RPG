"""The Flask routes, driven through Flask's real test client."""

import io
import json
import os
import unittest

import adapters.engine as engine_module
import app as app_module
from adapters.engine import GameEngine
from adapters.llm import LLMError
from data.character.presets import ORTON
from modules.body.stats import CharacterStat
from tests.support import FakeFactChecker, FakeMemory, IsolatedSaveTestCase, ScriptedLLM

ACTIONS = "ACTIONS:\nADD_GOAL short_term Find a weapon\nMOVE_TO out"
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
        self._original_factchecker = engine_module.FactChecker
        engine_module.FactChecker = FakeFactChecker

        engine = GameEngine()
        engine.create_character(ORTON)
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
        engine_module.FactChecker = self._original_factchecker
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
            b'id="turn-status"',
            b'id="turn-step"',
            b'id="turn-timer"',
            b'id="thoughts"',
            b'id="thoughts-text"',
            b'id="location-status"',
            b'id="inventory-list"',
            b'id="equipment-list"',
            b'id="npc-list"',
            b'id="goal-list"',
            b'id="quest-list"',
            b'id="trait-list"',
            b'id="save-button"',
            b'id="load-button"',
            b'id="load-input"',
            b'id="creation-screen"',
            b'id="creation-form"',
        ):
            self.assertIn(element_id, response.data)


class StatusEffectPayloadTests(RouteTestCase):
    """status-effects: What the narrator and the player see."""

    def test_play_carries_status_effects_and_no_hunger_or_thirst(self):
        stats = self.engine.game.player.stats
        stats.set(CharacterStat.HUNGER, 0.5)
        stats.set(CharacterStat.FATIGUE, 0.61)
        stats.set(CharacterStat.THIRST, 0.13)
        payload = self.client.post("/play", json={"input": "look"}).get_json()
        self.assertEqual(
            [(m["type"], m["name"]) for m in payload["effects"]][:3],
            [("hungry", "Very Hungry"), ("thirst", "Slightly Thirsty"), ("tired", "Drowsy")],
        )
        self.assertEqual(payload["effects"][0]["level"], 3)
        for gone in ("hunger", "thirst", "vitals"):
            self.assertNotIn(gone, payload)

    def test_play_carries_the_temperature_status_effects_and_no_core_temperature(self):
        """body-temperature: What the narrator and the player see."""
        stats = self.engine.game.player.stats
        stats.set(CharacterStat.TEMPERATURE, 21.0)
        stats.set(CharacterStat.WETNESS, 95)
        payload = self.client.post("/play", json={"input": "look"}).get_json()
        status_effects = {m["type"]: m for m in payload["effects"]}
        self.assertEqual(status_effects["hypothermia"]["level"], 4)
        self.assertIn("wet", status_effects)
        self.assertNotIn("temperature", payload)

    def test_state_lists_status_effects_highest_level_first(self):
        stats = self.engine.game.player.stats
        stats.set(CharacterStat.THIRST, 0.13)
        stats.set(CharacterStat.HUNGER, 0.5)
        levels = [m["level"] for m in self.client.get("/state").get_json()["effects"]]
        self.assertEqual(levels, sorted(levels, reverse=True))


class StateTests(RouteTestCase):
    def test_state_reports_the_starting_world(self):
        # Orton now starts alone in his apartment; move to the building to
        # exercise the NPC-presence check below.
        self.engine.game.player.current_location_id = "zone_building"
        payload = self.client.get("/state").get_json()
        self.assertEqual(payload["current_location"], "Your Building")
        self.assertEqual(payload["day"], 1)
        self.assertIn("Emma", payload["npcs_present"])
        self.assertEqual(payload["story_text"], "")

    def test_state_carries_the_last_story_after_a_turn(self):
        self.client.post("/play", json={"input": "go out"})
        payload = self.client.get("/state").get_json()
        self.assertEqual(payload["story_text"], "You walk out into the building.")
        self.assertEqual(payload["options"], [])

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


class PlayStreamTests(RouteTestCase):
    """llm-contract: Streaming: /play/stream sends a turn's events as JSON lines, then the turn."""

    def events(self, player_input: str = "go out") -> list[dict]:
        response = self.client.post("/play/stream", json={"input": player_input})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.mimetype, "application/x-ndjson")
        return [json.loads(line) for line in response.get_data(as_text=True).splitlines()]

    def test_the_steps_come_before_the_finished_turn(self):
        events = self.events()
        steps = [event["step"] for event in events if event["type"] == "step"]
        # The scripted story has no OPTIONS section, so the follow-up asks for them.
        self.assertEqual(steps, ["parsing", "checking_plan", "narrating", "options", "saving"])
        self.assertEqual(events[-1]["type"], "done")

    def test_the_finished_turn_is_the_play_payload(self):
        turn = self.events()[-1]["turn"]
        self.assertEqual(turn["story_text"], "You walk out into the building.")
        self.assertEqual(turn["current_location"], "Your Building")

    def test_the_story_streams_before_the_turn_is_done(self):
        events = self.events()
        stories = [event["text"] for event in events if event["type"] == "story"]
        self.assertEqual(stories[-1], "You walk out into the building.")
        self.assertLess(
            max(i for i, event in enumerate(events) if event["type"] == "story"), len(events) - 1
        )

    def test_missing_input_is_rejected_before_streaming(self):
        response = self.client.post("/play/stream", json={})
        self.assertEqual(response.status_code, 400)
        self.assertIn("error", response.get_json())

    def test_no_game_is_rejected_before_streaming(self):
        self.engine.reset()
        response = self.client.post("/play/stream", json={"input": "look"})
        self.assertEqual(response.status_code, 409)
        self.assertTrue(response.get_json()["needs_creation"])

    def test_a_crashed_turn_ends_the_stream_with_an_error(self):
        def crash(player_input, on_event=None, mentions=()):
            raise RuntimeError("boom")

        self.engine.play = crash
        events = self.events()
        self.assertEqual(events[-1]["type"], "error")


class MentionRouteTests(RouteTestCase):
    """llm-contract: The `@` list in the payload, and the picks a turn request carries."""

    def test_state_lists_what_can_be_mentioned(self):
        payload = self.client.get("/state").get_json()
        kinds = {entry["kind"] for entry in payload["mentions"]}
        self.assertIn("zone", kinds)
        self.assertIn("room", kinds)
        self.assertEqual(
            set(payload["mentions"][0]), {"kind", "id", "name", "description", "label"}
        )

    def test_play_pins_the_ids_the_request_carries(self):
        self.llm.actions = "ACTIONS:\nMOVE_TO nowhere in particular"
        mark = "\ufffc"
        response = self.client.post(
            "/play", json={"input": f"go to {mark}", "mentions": ["zone_street"]}
        )
        self.assertEqual(response.get_json()["current_location"], "The Street")
        self.assertIn("go to [pinned: The Street]", self.llm.prompts[-1])

    def test_a_pick_out_of_reach_refuses_the_turn_with_no_parser_call(self):
        response = self.client.post("/play", json={"input": "hit \ufffc", "mentions": ["z99"]})
        self.assertIn("no longer within reach", response.get_json()["story_text"])
        self.assertEqual(self.llm.prompts, [])

    def test_the_stream_carries_the_picks_too(self):
        self.llm.actions = "ACTIONS:\nMOVE_TO nowhere in particular"
        response = self.client.post(
            "/play/stream", json={"input": "go to \ufffc", "mentions": ["zone_building"]}
        )
        done = json.loads(response.get_data(as_text=True).splitlines()[-1])
        self.assertEqual(done["turn"]["current_location"], "Your Building")

    def test_a_malformed_mentions_field_is_plain_prose(self):
        response = self.client.post("/play", json={"input": "look", "mentions": "z1"})
        self.assertEqual(response.status_code, 200)


class PlanRouteTests(RouteTestCase):
    """llm-contract: The plan screen over HTTP: a plan with an open choice is sent, answered by Go or dropped by Cancel."""

    def ask(self):
        self.llm.actions = "ACTIONS:\nMOVE_TO the apartment"
        response = self.client.post("/play/stream", json={"input": "go to the apartment"})
        return json.loads(response.get_data(as_text=True).splitlines()[-1])["turn"]

    def test_the_turn_carries_the_plan_and_state_shows_it_again(self):
        turn = self.ask()
        self.assertEqual(len(turn["plan"]["choices"][0]["candidates"]), 4)
        self.assertEqual(self.client.get("/state").get_json()["plan"], turn["plan"])

    def test_go_streams_the_run_of_the_kept_plan(self):
        self.ask()
        response = self.client.post("/plan/go/stream", json={"choices": ["zone_home"]})
        events = [json.loads(line) for line in response.get_data(as_text=True).splitlines()]
        self.assertEqual(events[-1]["type"], "done")
        self.assertIsNone(events[-1]["turn"]["plan"])
        self.assertEqual(events[-1]["turn"]["story_text"], "You walk out into the building.")
        self.assertEqual(len(self.llm.prompts), 1)

    def test_cancel_drops_the_plan(self):
        self.ask()
        self.assertIsNone(self.client.post("/plan/cancel").get_json()["plan"])
        self.assertIsNone(self.client.get("/state").get_json()["plan"])

    def test_go_with_no_game_is_rejected(self):
        self.engine.reset()
        response = self.client.post("/plan/go/stream", json={"choices": []})
        self.assertEqual(response.status_code, 409)


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
        self.assertEqual(payload["story_text"], "You walk out into the building.")

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
    def test_reset_deletes_the_save_and_leaves_no_game(self):
        """character-creation: Flow and routes."""
        self.client.post("/play", json={"input": "go out"})
        response = self.client.post("/reset")
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertEqual(payload["message"], "Game has been reset.")
        self.assertTrue(payload["state"]["needs_creation"])
        self.assertFalse(os.path.exists(self.save_path))

    def test_state_after_reset_asks_for_creation_and_play_is_refused(self):
        self.client.post("/reset")
        self.assertTrue(self.client.get("/state").get_json()["needs_creation"])
        self.assertEqual(self.client.post("/play", json={"input": "go out"}).status_code, 409)
        self.assertEqual(self.client.get("/save/export").status_code, 409)


class CreationRouteTests(RouteTestCase):
    """character-creation: Flow and routes."""

    VALID = {
        "appearance": {
            "forename": "Mara",
            "surname": "Quinn",
            "gender": "female",
            "skin_tone": 3,
            "hair_style": "long",
            "hair_colour": "black",
            "beard_style": "",
            "backstory": "Night shift nurse.",
        },
        "occupation_id": "nurse",
        "job_title": "",
        "traits": ["brave", "hemophobic"],
        "outfit": ["item_tshirt", "item_jeans", "item_trainers"],
    }

    def setUp(self):
        super().setUp()
        self.client.post("/reset")

    def test_get_creation_has_the_screen_data(self):
        payload = self.client.get("/creation").get_json()
        self.assertEqual(len(payload["occupations"]), 25)
        good, bad = payload["traits"]["good"], payload["traits"]["bad"]
        self.assertTrue(all(t["cost"] > 0 for t in good))
        self.assertTrue(all(t["cost"] < 0 for t in bad))
        self.assertIn("strong", [t["id"] for t in good])
        by_id = {t["id"]: t for t in good + bad}
        self.assertEqual(
            by_id["brave"]["excludes"],
            ["agoraphobic", "claustrophobic", "cowardly", "desensitized"],
        )
        self.assertEqual(payload["base_skills"], {"fitness": 5, "strength": 5})
        self.assertEqual(payload["appearance"]["skin_tones"]["1"], "pale")
        self.assertIn("male", payload["outfits"]["default"])
        self.assertEqual(payload["presets"]["orton"]["points_left"], 7)
        self.assertEqual(payload["presets"]["orton"]["appearance"]["forename"], "Orton")

    def test_an_invalid_build_starts_no_game(self):
        bad = {**self.VALID, "occupation_id": "veteran", "traits": ["brave"]}
        response = self.client.post("/creation", json=bad)
        self.assertEqual(response.status_code, 400)
        self.assertTrue(response.get_json()["errors"])
        self.assertFalse(self.engine.has_game)
        self.assertFalse(os.path.exists(self.save_path))
        self.assertTrue(self.client.get("/state").get_json()["needs_creation"])

    def test_a_malformed_body_is_refused(self):
        for body in ({}, {"appearance": 3}, {**self.VALID, "traits": "brave"}):
            response = self.client.post("/creation", json=body)
            self.assertEqual(response.status_code, 400)
        self.assertFalse(self.engine.has_game)

    def test_a_valid_build_starts_day_one_at_eight_with_the_chosen_outfit(self):
        response = self.client.post("/creation", json=self.VALID)
        self.assertEqual(response.status_code, 200)
        payload = response.get_json()
        self.assertFalse(payload["needs_creation"])
        self.assertEqual(payload["day"], 1)
        manager = self.engine.game
        self.assertEqual(
            (manager.narrative.day, manager.narrative.hour, manager.narrative.minute), (1, 8, 0)
        )
        self.assertEqual(manager.world.time, "08:00 AM")
        self.assertEqual(
            sorted(e.item.id for e in manager.player.worn.values()),
            ["item_jeans", "item_trainers", "item_tshirt"],
        )
        self.assertEqual(
            payload["character"],
            {
                "name": "Mara Quinn",
                "occupation": "Nurse",
                "traits": ["Night Owl", "Brave", "Fear of Blood", "Fit"],
            },
        )
        self.assertTrue(os.path.exists(self.save_path))
        self.assertEqual(self.client.post("/play", json={"input": "go out"}).status_code, 200)

    def test_the_preset_posts_back_as_a_valid_build(self):
        preset = self.client.get("/creation").get_json()["presets"]["orton"]
        response = self.client.post("/creation", json=preset)
        self.assertEqual(response.status_code, 200, response.get_json())
        self.assertEqual(response.get_json()["character"]["occupation"], "Software Developer")


class LazyEngineTests(IsolatedSaveTestCase):
    def test_importing_app_does_not_build_an_engine(self):
        # Building one loads the save and can pull in the embedding model, which
        # must not happen at import time.
        self.assertIsNone(app_module._engine)


if __name__ == "__main__":
    unittest.main()


class WeatherPayloadTests(RouteTestCase):
    """weather: What the narrator and the player see."""

    def test_state_carries_weather_summary_temperature_and_shelter(self):
        weather = self.client.get("/state").get_json()["weather"]
        self.assertEqual(set(weather), {"summary", "temperature_c", "sheltered"})
        self.assertIsInstance(weather["summary"], str)
        self.assertIsInstance(weather["temperature_c"], int)
        self.assertTrue(weather["sheltered"])

    def test_temperature_is_the_rounded_outdoor_sample(self):
        manager = self.engine.game
        expected = round(manager.climate.sample(manager.narrative.minutes).air_temperature)
        weather = self.client.get("/state").get_json()["weather"]
        self.assertEqual(weather["temperature_c"], expected)


class SkillsPayloadTests(RouteTestCase):
    """skills: What the narrator and the player see: the skills payload."""

    def payload(self) -> dict:
        return self.client.post("/play", json={"input": "look"}).get_json()

    def test_play_replaces_level_and_experience_with_skills(self):
        payload = self.payload()
        self.assertNotIn("level", payload)
        self.assertNotIn("experience_points", payload)
        self.assertEqual(len(payload["skills"]), 35)

    def test_each_entry_has_id_name_category_level_and_progress(self):
        entry = {s["id"]: s for s in self.payload()["skills"]}["fitness"]
        self.assertEqual(
            entry,
            {
                "id": "fitness",
                "name": "Fitness",
                "category": "physical",
                "level": 5,
                "progress": 0.0,
            },
        )

    def test_progress_is_the_share_of_the_way_to_the_next_level(self):
        skills = self.engine.game.player.skills
        skills["axe"].level = 1
        skills["axe"].xp = 75 + 37.5
        entry = {s["id"]: s for s in self.payload()["skills"]}["axe"]
        self.assertEqual(entry["level"], 1)
        self.assertAlmostEqual(entry["progress"], 0.25)

    def test_level_ten_reads_as_full(self):
        skills = self.engine.game.player.skills
        skills["axe"].level = 10
        skills["axe"].xp = 32775
        entry = {s["id"]: s for s in self.payload()["skills"]}["axe"]
        self.assertEqual(entry["progress"], 1.0)

    def test_the_page_renders_skills_and_drops_the_old_rows(self):
        page = self.client.get("/").data
        self.assertIn(b"skill-list", page)
        self.assertNotIn(b"data.experience_points", page)
