"""Persistence: full round trip, schema guarding, and tolerance of bad saves."""

import json
import unittest
from pathlib import Path

from adapters import persistence
from managers.game import GameManager
from modules.quest import QuestState, QuestStatus
from tests.support import IsolatedSaveTestCase, resolve_actions
from modules.action import (
    AddGoalAction,
    AddRelationshipNoteAction,
    DiscoverFlagAction,
    MoveAction,
    NpcMoveAction,
    NpcStatusAction,
    SetFlagAction,
    StatusAddAction,
    TakeAction,
    TimeAdvanceAction,
    UpdateConditionAction,
    UpdateInventoryAction,
    UpdateRelationshipAction,
)


def played_game() -> GameManager:
    """A game with something changed on every persisted axis."""
    gm = GameManager()
    resolve_actions(
        gm,
        MoveAction(destination="north"),
        TakeAction(item_name="Crowbar"),
        UpdateConditionAction(field_name="hunger", raw_value="70"),
        UpdateConditionAction(field_name="sleep", raw_value="Exhausted"),
        UpdateRelationshipAction(npc_name="Emma", axis="affection", amount=12),
        UpdateRelationshipAction(npc_name="Emma", axis="trust", amount=-2),
        AddRelationshipNoteAction(npc_name="Emma", note="Seemed shaken"),
        AddGoalAction(horizon="short_term", goal_text="Find a weapon"),
        AddGoalAction(horizon="long_term", goal_text="Leave the city"),
        SetFlagAction(flag_name="power_grid_stable", value=False),
        DiscoverFlagAction(flag_name="power_grid_stable"),
        TimeAdvanceAction(time_of_day="evening"),
        StatusAddAction(status="panic"),
        NpcMoveAction(npc_name="Emma", destination="Lobby"),
        NpcStatusAction(npc_name="Emma", operation="ADD", status="frightened"),
        UpdateInventoryAction(item_name="First Aid Kit", operation="ADD", value="1"),
    )
    # Health is retired as an LLM-declarable action (docs/01-engine-authority.md);
    # it only ever changes through combat or item effects. Set directly here
    # since this fixture is exercising persistence, not the action pipeline.
    gm.player.hit_points = 55
    emma = gm.resolve_npc("Emma")
    emma.goals.append("find out who the new neighbor is")
    emma.knowledge.add("secret_bunker_location")
    gm.quests["find_the_bunker"] = QuestState(
        quest_id="find_the_bunker",
        title="Find the Bunker",
        status=QuestStatus.ACTIVE,
        objectives=["discover:bunker_location", "defeat:npc_marcus"],
        objective_labels={"discover:bunker_location": "Locate the bunker"},
        completed_objectives=["discover:bunker_location"],
    )
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

    def test_npc_goals_and_knowledge_round_trip(self):
        emma = self.loaded.resolve_npc("Emma")
        self.assertIn("find out who the new neighbor is", emma.goals)
        self.assertIn("secret_bunker_location", emma.knowledge)

    def test_quest_state_round_trips(self):
        quest = self.loaded.quests["find_the_bunker"]
        self.assertEqual(quest.title, "Find the Bunker")
        self.assertEqual(quest.status, QuestStatus.ACTIVE)
        self.assertEqual(quest.objectives, ["discover:bunker_location", "defeat:npc_marcus"])
        self.assertEqual(
            quest.objective_labels, {"discover:bunker_location": "Locate the bunker"}
        )
        self.assertEqual(quest.completed_objectives, ["discover:bunker_location"])

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
        self.assertIn("power_grid_stable", self.loaded.narrative.discovered_flags)
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
        facts = resolve_actions(self.loaded, MoveAction(destination="south"))
        self.assertFalse(facts[0].startswith("Refused:"), facts[0])
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

    def test_a_save_with_no_quests_seeds_the_starting_roster(self):
        # v2 already had a "quests" key before any quest content existed, so
        # an old save has it present but empty -- that must not leave a
        # loaded game with no quests forever, same as an empty "npcs" list
        # falls back to build_starting_npcs().
        persistence.save(GameManager(), self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["quests"] = {}
        self.write(data)
        loaded = persistence.load(self.save_path)
        self.assertTrue(loaded.quests)
        self.assertIn("quest_storage_room", loaded.quests)

    def test_seeded_quests_reconcile_against_what_the_save_already_achieved(self):
        # Objectives fire on the transition, not the condition. A save made
        # mid-playthrough already holds the key and stands in the storage
        # room, so seeding blind would leave both boxes unchecked forever --
        # the player would have to drop and retake a key already in hand.
        gm = GameManager()
        resolve_actions(
            gm, MoveAction(destination="north"), TakeAction(item_name="Storage Room Key")
        )
        gm.player.current_location_id = "location_id_storage"

        persistence.save(gm, self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["quests"] = {}
        self.write(data)

        quest = persistence.load(self.save_path).quests["quest_storage_room"]
        self.assertEqual(
            sorted(quest.completed_objectives),
            ["reach:location_id_storage", "take:item_storage_key"],
        )
        self.assertEqual(quest.status, QuestStatus.COMPLETED)

    def test_reconciliation_leaves_unachieved_objectives_open(self):
        persistence.save(GameManager(), self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["quests"] = {}
        self.write(data)

        quest = persistence.load(self.save_path).quests["quest_storage_room"]
        self.assertEqual(quest.completed_objectives, [])
        self.assertEqual(quest.status, QuestStatus.ACTIVE)

    def write(self, data: dict) -> None:
        with open(self.save_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)


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

    def test_a_v1_save_is_discarded_cleanly_not_crashed(self):
        # v1 predates NpcEntity.goals/.knowledge and discovered_flags -- the
        # existing "unreadable save -> fresh game" policy handles this with
        # no migration code, by design (adapters/persistence.py module doc).
        self.write({"version": 1, "player": {}, "narrative": {}})
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
