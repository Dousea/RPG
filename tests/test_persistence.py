"""Persistence: full round trip, schema guarding, and tolerance of bad saves."""

import json
import unittest
from pathlib import Path

from adapters import persistence
from managers.game import GameManager
from tests.support import IsolatedSaveTestCase


def played_game() -> GameManager:
    """A game with something changed on every persisted axis."""
    gm = GameManager()
    for action in (
        "MOVE_TO north",
        "TAKE Crowbar",
        "UPDATE_CONDITION health 55",
        "UPDATE_CONDITION hunger 70",
        "UPDATE_CONDITION sleep Exhausted",
        "UPDATE_RELATIONSHIP Emma affection +12",
        "UPDATE_RELATIONSHIP Emma trust -2",
        "ADD_RELATIONSHIP_NOTE Emma Seemed shaken",
        "ADD_GOAL short_term Find a weapon",
        "ADD_GOAL long_term Leave the city",
        "SET_FLAG power_grid_stable false",
        "TIME_ADVANCE evening",
        "STATUS_ADD panic",
        "NPC_MOVE Emma TO Lobby",
        "NPC_STATUS Emma ADD frightened",
        "UPDATE_INVENTORY First Aid Kit ADD 1",
    ):
        succeeded, message = gm.apply_action(action)
        assert succeeded, f"setup action {action!r} failed: {message}"
    gm.record_event("Orton entered the office.")
    gm.memory.summaries.append("The first day passed quietly.")
    gm.narrative.pending_corrections = ["TAKE Medkit -- No 'Medkit' here to take."]
    return gm


class RoundTripTests(IsolatedSaveTestCase):
    def setUp(self):
        super().setUp()
        self.original = played_game()
        persistence.save(self.original, self.save_path)
        loaded = persistence.load(self.save_path)
        self.assertIsNotNone(loaded)
        self.loaded = loaded

    def test_player_position_and_condition(self):
        self.assertEqual(self.loaded.player.current_location_id, "location_id_office")
        self.assertEqual(self.loaded.player.hit_points, 55)
        self.assertEqual(self.loaded.player.hunger, 70)

    def test_hit_points_are_not_reset_to_max_on_load(self):
        # __post_init__ fills hit_points to max, so the saved value has to be
        # applied after construction.
        self.assertNotEqual(self.loaded.player.hit_points, self.loaded.player.max_hit_points)

    def test_inventory_with_condition(self):
        self.assertEqual(
            sorted(e.item.id for e in self.loaded.player.inventory),
            sorted(e.item.id for e in self.original.player.inventory),
        )

    def test_ground_items_move_with_the_world(self):
        office = self.loaded.world.locations["location_id_office"]
        # The crowbar was picked up, so it is no longer on the office floor.
        self.assertNotIn("Crowbar", [e.item.name for e in office.entities])
        self.assertIn("Canned Beans", [e.item.name for e in office.entities])

    def test_traits_and_perks_resolve_by_id(self):
        self.assertEqual(
            [t.id for t in self.loaded.player.traits],
            [t.id for t in self.original.player.traits],
        )
        self.assertEqual(
            [p.id for p in self.loaded.player.perks],
            [p.id for p in self.original.player.perks],
        )

    def test_conditions(self):
        self.assertIn("panic", [c.value for c in self.loaded.player.conditions])
        self.assertEqual(self.loaded.narrative.conditions["sleep"], "Exhausted")

    def test_npc_state(self):
        emma = self.loaded.resolve_npc("Emma")
        self.assertEqual(emma.current_location_id, "location_id_lobby")
        self.assertIn("frightened", emma.status)
        self.assertIn("Seemed shaken", emma.notes)

    def test_relationships_keep_their_direction(self):
        manager = self.loaded.relationship_manager
        self.assertEqual(manager.get_affinity("npc_emma", "player"), 12)
        self.assertEqual(manager.get_trust("npc_emma", "player"), 3)
        # The reverse direction was never written and must stay empty.
        self.assertEqual(manager.get_affinity("player", "npc_emma"), 0)

    def test_narrative_state(self):
        self.assertEqual(self.loaded.narrative.day, self.original.narrative.day)
        self.assertEqual(self.loaded.narrative.time_of_day, "evening")
        self.assertIn("Find a weapon", self.loaded.narrative.goals["short_term"])
        self.assertIn("Leave the city", self.loaded.narrative.goals["long_term"])
        self.assertIs(self.loaded.narrative.flags["power_grid_stable"], False)
        self.assertEqual(
            self.loaded.narrative.pending_corrections,
            self.original.narrative.pending_corrections,
        )

    def test_world_clock_is_rebuilt_from_the_narrative_clock(self):
        # It is derived state, so a save written before it existed -- or one hand
        # edited -- still loads with the two in agreement.
        self.assertEqual(self.loaded.world.time, "07:00 PM")
        self.assertEqual(self.loaded.world.date, "2023-10-01")

    def test_a_save_with_a_stale_world_clock_is_corrected_on_load(self):
        data = persistence.to_dict(self.original)
        data["world"]["time"] = "12:00 PM"
        data["world"]["date"] = "2023-10-01"
        data["narrative"]["day"] = 4
        rebuilt = persistence.from_dict(data)
        self.assertEqual(rebuilt.world.time, "07:00 PM")
        self.assertEqual(rebuilt.world.date, "2023-10-04")

    def test_memory_tiers(self):
        self.assertEqual(
            self.loaded.memory.full_event_log, self.original.memory.full_event_log
        )
        self.assertEqual(self.loaded.memory.recent_events, self.original.memory.recent_events)
        self.assertEqual(self.loaded.memory.summaries, self.original.memory.summaries)

    def test_the_loaded_game_is_still_playable(self):
        succeeded, message = self.loaded.apply_action("MOVE_TO south")
        self.assertTrue(succeeded, message)
        self.assertEqual(self.loaded.player.current_location_id, "location_id_hallway")


class SaveFileTests(IsolatedSaveTestCase):
    def test_save_is_written_atomically(self):
        persistence.save(GameManager(), self.save_path)
        self.assertTrue(Path(self.save_path).exists())
        # The temp file used during the write must not be left behind.
        self.assertFalse(Path(f"{self.save_path}.tmp").exists())

    def test_default_path_follows_the_module_attribute(self):
        # Regression: the path was a default argument bound at import time, so
        # SAVE_FILE could not be redirected.
        persistence.save(GameManager())
        self.assertTrue(Path(self.save_path).exists())

    def test_save_is_json_serializable_end_to_end(self):
        persistence.save(played_game(), self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(data["version"], persistence.SCHEMA_VERSION)


class BadSaveTests(IsolatedSaveTestCase):
    def write(self, data: dict) -> None:
        with open(self.save_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)

    def test_missing_file_returns_none(self):
        self.assertIsNone(persistence.load(self.save_path))

    def test_schema_mismatch_is_refused(self):
        persistence.save(GameManager(), self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["version"] = persistence.SCHEMA_VERSION + 1
        self.write(data)
        self.assertIsNone(persistence.load(self.save_path))

    def test_corrupt_json_returns_none(self):
        with open(self.save_path, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        self.assertIsNone(persistence.load(self.save_path))

    def test_unknown_ids_are_dropped_not_fatal(self):
        persistence.save(played_game(), self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["player"]["inventory"].append({"item_id": "item_deleted", "hit_points": 1})
        data["player"]["trait_ids"].append("TraitID_Removed")
        data["player"]["conditions"].append("haunted")
        data["world"]["ground_items"]["location_id_atlantis"] = [
            {"item_id": "item_crowbar", "hit_points": 5}
        ]
        self.write(data)

        loaded = persistence.load(self.save_path)
        self.assertIsNotNone(loaded)
        self.assertNotIn("item_deleted", [e.item.id for e in loaded.player.inventory])
        self.assertNotIn("location_id_atlantis", loaded.world.locations)

    def test_unknown_player_location_falls_back(self):
        persistence.save(GameManager(), self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["player"]["current_location_id"] = "location_id_atlantis"
        self.write(data)

        loaded = persistence.load(self.save_path)
        self.assertIsNotNone(loaded)
        self.assertIn(loaded.player.current_location_id, loaded.world.locations)

    def test_save_with_no_npcs_falls_back_to_the_roster(self):
        persistence.save(GameManager(), self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["npcs"] = []
        self.write(data)

        loaded = persistence.load(self.save_path)
        self.assertIsNotNone(loaded)
        self.assertEqual(len(loaded.npcs), 3)


if __name__ == "__main__":
    unittest.main()
