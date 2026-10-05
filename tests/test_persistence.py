"""Persistence: full round trip, schema guarding, and tolerance of bad saves."""

import copy
import json
import unittest
from pathlib import Path

from adapters import persistence
from managers.game import GameManager
from modules.entity.item import ItemEntity
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

# A realistic v2 save, written by hand as main's v2 `to_dict` actually wrote
# it (see `git show 7668674:adapters/persistence.py`) -- not produced by
# calling today's `to_dict`, which now emits v3. Player and NPC still use
# room ids; quests still have `quest_storage_room` and predate the current
# roster; `narrative` has no `game_over`/`death_cause` at all.
#
# The crowbar appears twice on purpose: once as a hallway ground item (so the
# four-room ground-item test has its fourth name, and so migration must NOT
# duplicate zone_street's starting crowbar onto a world that already has
# one), and once in the player's own inventory (so quest_supply_run's
# `take:item_crowbar` is already satisfiable once seeded -- see
# test_supply_run_reconciles_against_migrated_state).
V2_SAVE = {
    "version": 2,
    "world": {
        "time": "07:00 PM",
        "date": "2023-10-03",
        "ground_items": {
            "location_id_hallway": [{"item_id": "item_crowbar", "hit_points": 50}],
            "location_id_office": [{"item_id": "item_canned_beans", "hit_points": 5}],
            "location_id_lobby": [{"item_id": "item_first_aid_kit", "hit_points": 20}],
            "location_id_storage": [{"item_id": "item_storage_key", "hit_points": 10}],
        },
    },
    "player": {
        "entity_id": "player",
        "name": "Orton",
        "current_location_id": "location_id_lobby",
        "hit_points": 80,
        "experience_points": 0,
        "level": 1,
        "max_inventory_size": 20,
        "hunger": 90,
        "thirst": 90,
        "morale": 90,
        "attributes": {},
        "inventory": [{"item_id": "item_crowbar", "hit_points": 50}],
        "equipment": {},
        "trait_ids": [],
        "perk_ids": [],
        "conditions": [],
    },
    "npcs": [
        {
            "npc_id": "npc_emma",
            "name": "Emma",
            "description": "A neighbour.",
            "current_location_id": "location_id_storage",
            "hit_points": 100,
            "age": 29,
            "faction": "neutral",
            "personality": [],
            "status": [],
            "notes": "",
            "romance_eligible": True,
            "conditions": [],
            "inventory": [],
            "base_max_hit_points": 100,
            "goals": [],
            "knowledge": [],
        }
    ],
    "relationships": {"affinities": {}, "trusts": {}, "reputations": {}},
    "narrative": {
        "day": 3,
        "time_of_day": "evening",
        "apocalypse_stage": "Normal",
        "goals": {"short_term": [], "long_term": []},
        "flags": {"PowerGrid": True},
        "discovered_flags": ["PowerGrid"],
        "player_status": [],
        "conditions": {"sleep": "Rested", "infection_risk": "No"},
        "pending_corrections": [],
    },
    "memory": {
        "recent_events": ["Orton entered the lobby."],
        "full_event_log": ["Orton entered the lobby."],
        "summaries": [],
    },
    "quests": {
        "quest_storage_room": {
            "title": "Find the Storage Key",
            "status": "active",
            "objectives": ["take:item_storage_key"],
            "objective_labels": {"take:item_storage_key": "Find the storage key"},
            "completed_objectives": ["take:item_storage_key"],
        },
        "quest_custom_errand": {
            "title": "Check the Office",
            "status": "active",
            "objectives": ["reach:location_id_office"],
            "objective_labels": {"reach:location_id_office": "Go check the office"},
            "completed_objectives": [],
        },
    },
}

# A v2 save with no items anywhere, to test in isolation that a zone v2
# didn't have gets its normal starting items -- V2_SAVE above can't be used
# for this, because its crowbar (already present in a room) must NOT be
# duplicated onto zone_street, which is the opposite behaviour.
V2_SAVE_NO_EXTRA_ITEMS = {
    "version": 2,
    "world": {"time": "12:00 PM", "date": "2023-10-01", "ground_items": {}},
    "player": {"name": "Orton", "current_location_id": "location_id_hallway"},
    "npcs": [],
    "relationships": {},
    "narrative": {"day": 1, "time_of_day": "morning"},
    "memory": {},
    "quests": {},
}


def played_game() -> GameManager:
    """A game with something changed on every persisted axis."""
    gm = GameManager()
    resolve_actions(
        gm,
        MoveAction(destination="out"),
        MoveAction(destination="out"),
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
        NpcMoveAction(npc_name="Emma", destination="Your Building"),
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
        self.assertEqual(self.loaded.player.current_location_id, "zone_street")
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
        street = self.loaded.world.locations["zone_street"]
        home = self.loaded.world.locations["zone_home"]
        # The crowbar was picked up, so it is no longer on the street.
        self.assertNotIn("Crowbar", [e.item.name for e in street.entities])
        # The canned beans were never touched.
        self.assertIn("Canned Beans", [e.item.name for e in home.entities])

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
        self.assertEqual(emma.current_location_id, "zone_building")
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
        self.assertEqual(quest.objective_labels, {"discover:bunker_location": "Locate the bunker"})
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
        self.assertEqual(self.loaded.memory.full_event_log, self.original.memory.full_event_log)
        self.assertEqual(self.loaded.memory.recent_events, self.original.memory.recent_events)
        self.assertEqual(self.loaded.memory.summaries, self.original.memory.summaries)

    def test_the_loaded_game_is_still_playable(self):
        facts = resolve_actions(self.loaded, MoveAction(destination="in"))
        self.assertFalse(facts[0].startswith("Refused:"), facts[0])
        self.assertEqual(self.loaded.player.current_location_id, "zone_building")


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
        self.assertIn("quest_supply_run", loaded.quests)

    def test_seeded_quests_reconcile_against_what_the_save_already_achieved(self):
        # Objectives fire on the transition, not the condition. A save made
        # mid-playthrough already holds the crowbar and stands in the
        # neighborhood, so seeding blind would leave both boxes unchecked
        # forever -- the player would have to drop the crowbar and walk back.
        gm = GameManager()
        resolve_actions(
            gm,
            MoveAction(destination="out"),  # zone_home -> zone_building
            MoveAction(destination="out"),  # zone_building -> zone_street
            TakeAction(item_name="Crowbar"),
            MoveAction(destination="out"),  # zone_street -> zone_neighborhood
        )

        persistence.save(gm, self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["quests"] = {}
        self.write(data)

        quest = persistence.load(self.save_path).quests["quest_supply_run"]
        self.assertEqual(
            sorted(quest.completed_objectives),
            ["reach:zone_neighborhood", "take:item_crowbar"],
        )
        self.assertEqual(quest.status, QuestStatus.COMPLETED)

    def test_reconciliation_leaves_unachieved_objectives_open(self):
        persistence.save(GameManager(), self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["quests"] = {}
        self.write(data)

        quest = persistence.load(self.save_path).quests["quest_supply_run"]
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


class V3FieldsRoundTripTests(IsolatedSaveTestCase):
    """`current_place` and death state, added to the save format in v3."""

    def test_current_place_round_trips(self):
        gm = GameManager()
        # zone_home is the starting zone, so "the kitchen" (one of its
        # aliases) resolves as a spot inside it, not a zone change.
        resolve_actions(gm, MoveAction(destination="the kitchen"))
        self.assertEqual(gm.player.current_place, "the kitchen")

        persistence.save(gm, self.save_path)
        loaded = persistence.load(self.save_path)
        self.assertEqual(loaded.player.current_place, "the kitchen")

    def test_death_state_round_trips(self):
        gm = GameManager()
        gm.narrative.game_over = True
        gm.narrative.death_cause = "Orton bled out from a knife wound."

        persistence.save(gm, self.save_path)
        loaded = persistence.load(self.save_path)
        self.assertTrue(loaded.narrative.game_over)
        self.assertEqual(loaded.narrative.death_cause, "Orton bled out from a knife wound.")


class MigrationTests(IsolatedSaveTestCase):
    """v2 saves name main's four rooms that preceded zones."""

    def write(self, data: dict) -> None:
        with open(self.save_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)

    def setUp(self):
        super().setUp()
        self.write(V2_SAVE)

    def test_a_v2_save_loads_instead_of_being_discarded(self):
        # The version gate discards a mismatch outright, which would have
        # thrown away a real game over what is only a content change.
        loaded = persistence.load(self.save_path)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.player.current_location_id, "zone_building")
        self.assertEqual(loaded.player.current_place, "the lobby")
        self.assertEqual(loaded.narrative.day, 3)
        self.assertEqual(loaded.memory.full_event_log, ["Orton entered the lobby."])

    def test_ground_items_from_all_rooms_accumulate(self):
        # Four room keys fold onto one zone, so items must accumulate; a
        # plain rebuild would keep only whichever room was written last.
        loaded = persistence.load(self.save_path)
        names = sorted(
            entity.item.name
            for entity in loaded.world.locations["zone_building"].entities
            if isinstance(entity, ItemEntity)
        )
        self.assertEqual(names, ["Canned Beans", "Crowbar", "First Aid Kit", "Storage Room Key"])

    def test_npcs_are_remapped_too(self):
        loaded = persistence.load(self.save_path)
        self.assertEqual(loaded.resolve_npc("Emma").current_location_id, "zone_building")

    def test_storage_quest_is_replaced_by_the_supply_run(self):
        loaded = persistence.load(self.save_path)
        self.assertNotIn("quest_storage_room", loaded.quests)
        self.assertIn("quest_supply_run", loaded.quests)

    def test_reach_keys_are_remapped(self):
        loaded = persistence.load(self.save_path)
        quest = loaded.quests["quest_custom_errand"]
        self.assertIn("reach:zone_building", quest.objectives)
        self.assertIn("reach:zone_building", quest.objective_labels)

    def test_a_migrated_game_is_playable(self):
        loaded = persistence.load(self.save_path)
        self.assertIn("[SCENE]", loaded.build_narrator_prompt("look around"))
        facts = resolve_actions(loaded, MoveAction(destination="The Street"))
        self.assertFalse(facts[0].startswith("Refused:"), facts[0])

        # The migrated player can also walk home -- the apartment key must
        # have been granted, or he'd be locked out of his own home forever.
        home = persistence.load(self.save_path)
        facts = resolve_actions(home, MoveAction(destination="Your Apartment"))
        self.assertFalse(facts[0].startswith("Refused:"), facts[0])
        self.assertEqual(home.player.current_location_id, "zone_home")

    def test_a_v1_save_is_discarded(self):
        self.write({"version": 1, "player": {}, "narrative": {}})
        self.assertIsNone(persistence.load(self.save_path))

    def test_import_route_migrates_a_v2_upload(self):
        # GameEngine.import_save calls from_saved_data directly, so the
        # /save/import route gets migration for free -- covered end-to-end
        # in tests/test_engine.py's test_import_route_migrates_a_v2_upload.
        loaded = persistence.from_saved_data(copy.deepcopy(V2_SAVE))
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.player.current_location_id, "zone_building")

    def test_flag_keys_are_normalized_on_migration(self):
        # Task 3 made SET_FLAG/DISCOVER_FLAG normalize flag names, so a v2
        # save's "PowerGrid" would otherwise sit beside a new "powergrid".
        loaded = persistence.load(self.save_path)
        self.assertEqual(loaded.narrative.flags.get("powergrid"), True)
        self.assertIn("powergrid", loaded.narrative.discovered_flags)

    def test_migration_does_not_mutate_its_input(self):
        before = copy.deepcopy(V2_SAVE)
        persistence.migrate_v2_to_v3(V2_SAVE)
        self.assertEqual(V2_SAVE, before)

    def test_new_zones_get_their_starting_items(self):
        self.write(V2_SAVE_NO_EXTRA_ITEMS)
        loaded = persistence.load(self.save_path)
        street_names = {
            e.item.name
            for e in loaded.world.locations["zone_street"].entities
            if isinstance(e, ItemEntity)
        }
        home_names = {
            e.item.name
            for e in loaded.world.locations["zone_home"].entities
            if isinstance(e, ItemEntity)
        }
        self.assertIn("Crowbar", street_names)
        self.assertIn("Canned Beans", home_names)
        self.assertIn("Water Bottle", home_names)

    def test_items_already_in_the_save_are_not_duplicated(self):
        loaded = persistence.load(self.save_path)
        street = loaded.world.locations["zone_street"]
        self.assertNotIn(
            "Crowbar", [e.item.name for e in street.entities if isinstance(e, ItemEntity)]
        )
        crowbar_count = sum(
            1
            for location in loaded.world.locations.values()
            for e in location.entities
            if isinstance(e, ItemEntity) and e.item.id == "item_crowbar"
        )
        self.assertEqual(crowbar_count, 1)

    def test_migrated_player_is_given_the_apartment_key(self):
        loaded = persistence.load(self.save_path)
        self.assertIn("item_apartment_key", [e.item.id for e in loaded.player.inventory])

    def test_key_is_not_duplicated_if_already_held(self):
        save_with_key = copy.deepcopy(V2_SAVE)
        save_with_key["player"]["inventory"].append(
            {"item_id": "item_apartment_key", "hit_points": 10}
        )
        self.write(save_with_key)

        loaded = persistence.load(self.save_path)
        keys = [e for e in loaded.player.inventory if e.item.id == "item_apartment_key"]
        self.assertEqual(len(keys), 1)

    def test_supply_run_reconciles_against_migrated_state(self):
        loaded = persistence.load(self.save_path)
        quest = loaded.quests["quest_supply_run"]
        self.assertIn("take:item_crowbar", quest.completed_objectives)

    def test_v3_zone_ids_are_derived_from_the_world_not_hard_coded(self):
        # FW7: `_V3_ZONE_IDS` must come from `build_starting_locations()`
        # rather than a literal set that would silently go stale if a zone
        # were added, renamed, or removed.
        from data.locations import build_starting_locations

        self.assertEqual(persistence._V3_ZONE_IDS, frozenset(build_starting_locations().keys()))


class MigrationHardeningTests(unittest.TestCase):
    """Fix round 1 (task-5-fix-round-1.md, F1-F9): malformed saves must
    degrade to loading, or a clean None, but never raise -- and a few
    migration correctness bugs the review found along the way."""

    # F1: five malformed v2 saves that used to raise uncaught inside
    # GameEngine.__init__/the /save/import route. Each is a mutation of the
    # V2_SAVE fixture; every one of them now loads cleanly rather than just
    # "doesn't crash", because the individual migration helpers were made
    # tolerant (see F2/F3 below), not only wrapped in a wider try/except.
    def test_malformed_v2_fields_degrade_to_loading_not_crash(self):
        cases = {
            "ground_items entry is null": lambda d: d["world"]["ground_items"].update(
                {"location_id_office": None}
            ),
            "a quest's objectives is null": lambda d: d.update(
                {"quests": {"q": {"objectives": None}}}
            ),
            "a quest's objective_labels is null": lambda d: d["quests"][
                "quest_custom_errand"
            ].update({"objective_labels": None}),
            "a discovered flag is not a string": lambda d: d["narrative"].update(
                {"discovered_flags": [5]}
            ),
            "flags is a list, not a dict": lambda d: d["narrative"].update({"flags": []}),
        }
        for description, mutate in cases.items():
            with self.subTest(description):
                data = copy.deepcopy(V2_SAVE)
                mutate(data)
                result = persistence.from_saved_data(data)  # must not raise
                self.assertIsInstance(result, GameManager)

    # F2: a non-dict "quests" (v2 or v3) must be treated as empty -- seed
    # and reconcile the whole roster, same as a missing key.
    def test_null_quests_seeds_the_roster(self):
        data = copy.deepcopy(V2_SAVE)
        data["quests"] = None
        loaded = persistence.from_saved_data(data)
        self.assertIsNotNone(loaded)
        for quest_id in ("quest_supply_run", "quest_marcus_trust", "quest_understand_the_crisis"):
            self.assertIn(quest_id, loaded.quests)

    def test_quests_as_a_list_seeds_the_roster(self):
        data = copy.deepcopy(V2_SAVE)
        data["quests"] = []
        loaded = persistence.from_saved_data(data)
        self.assertIsNotNone(loaded)
        for quest_id in ("quest_supply_run", "quest_marcus_trust", "quest_understand_the_crisis"):
            self.assertIn(quest_id, loaded.quests)

    # F3: player.inventory: null must not crash the apartment-key grant.
    def test_null_player_inventory_still_grants_the_apartment_key(self):
        data = copy.deepcopy(V2_SAVE)
        data["player"]["inventory"] = None
        loaded = persistence.from_saved_data(data)
        self.assertIsNotNone(loaded)
        self.assertIn("item_apartment_key", [e.item.id for e in loaded.player.inventory])

    # F4: remapping can collapse two reach objectives onto one already-done
    # zone; the quest must not be left ACTIVE forever.
    def test_deduplicated_reach_objectives_completes_the_quest(self):
        data = copy.deepcopy(V2_SAVE)
        data["quests"] = {
            "quest_two_room_errand": {
                "title": "Check Both Rooms",
                "status": "active",
                "objectives": ["reach:location_id_office", "reach:location_id_lobby"],
                "objective_labels": {
                    "reach:location_id_office": "Check the office",
                    "reach:location_id_lobby": "Check the lobby",
                },
                "completed_objectives": ["reach:location_id_office"],
            }
        }
        loaded = persistence.from_saved_data(data)
        self.assertIsNotNone(loaded)
        quest = loaded.quests["quest_two_room_errand"]
        self.assertEqual(quest.objectives, ["reach:zone_building"])
        self.assertEqual(quest.status, QuestStatus.COMPLETED)

    # F5: an item under a location id that won't survive migration (not a
    # v2 room, not already a v3 zone) must not suppress a new zone's own
    # starting copy of it -- the original is dropped by from_dict either way.
    def test_item_under_an_unmapped_location_does_not_suppress_a_new_zones_item(self):
        data = copy.deepcopy(V2_SAVE_NO_EXTRA_ITEMS)
        data["world"]["ground_items"] = {
            "location_id_attic": [{"item_id": "item_crowbar", "hit_points": 50}]
        }
        loaded = persistence.from_saved_data(data)
        self.assertIsNotNone(loaded)
        street_names = [
            e.item.name
            for e in loaded.world.locations["zone_street"].entities
            if isinstance(e, ItemEntity)
        ]
        self.assertIn("Crowbar", street_names)
        crowbar_count = sum(
            1
            for location in loaded.world.locations.values()
            for e in location.entities
            if isinstance(e, ItemEntity) and e.item.id == "item_crowbar"
        )
        self.assertEqual(crowbar_count, 1)

    # F6: current_place must only be overwritten from a v2 room id; a
    # non-room current_location_id keeps whatever current_place it already had.
    def test_current_place_is_kept_for_a_non_room_location(self):
        data = copy.deepcopy(V2_SAVE)
        data["player"]["current_location_id"] = "zone_street"
        data["player"]["current_place"] = "by the bus stop"
        loaded = persistence.from_saved_data(data)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.player.current_location_id, "zone_street")
        self.assertEqual(loaded.player.current_place, "by the bus stop")

    # F7: bool()/str() are the wrong coercions for hand-edited values.
    def test_game_over_string_false_is_not_true(self):
        data = persistence.to_dict(GameManager())
        data["narrative"]["game_over"] = "false"
        loaded = persistence.from_saved_data(data)
        self.assertIsNotNone(loaded)
        self.assertFalse(loaded.narrative.game_over)

    def test_null_death_cause_becomes_empty_string(self):
        data = persistence.to_dict(GameManager())
        data["narrative"]["death_cause"] = None
        loaded = persistence.from_saved_data(data)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.narrative.death_cause, "")

    def test_null_current_place_becomes_empty_string(self):
        data = persistence.to_dict(GameManager())
        data["player"]["current_place"] = None
        loaded = persistence.from_saved_data(data)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.player.current_place, "")


if __name__ == "__main__":
    unittest.main()
