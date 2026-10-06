"""Persistence: full round trip, schema guarding, and tolerance of bad saves."""

import json
import unittest
from pathlib import Path

from adapters.save import codec, files
from data.items import ITEMS
from managers.game import GameManager
from modules.action.types import (
    AddGoalAction,
    AddRelationshipNoteAction,
    DiscoverFlagAction,
    Duration,
    MoveAction,
    NpcMoveAction,
    NpcStatusAction,
    SetFlagAction,
    StatusAddAction,
    TakeAction,
    UpdateInventoryAction,
    UpdateRelationshipAction,
    WaitAction,
)
from modules.body import BodyLocation, BodyPart
from modules.entity.item import ItemEntity
from modules.quest import QuestState, QuestStatus
from modules.stats import CharacterStat
from tests.support import IsolatedSaveTestCase, resolve_actions


def played_game() -> GameManager:
    """A game with something changed on every persisted axis."""
    gm = GameManager()
    resolve_actions(
        gm,
        MoveAction(destination="out"),
        MoveAction(destination="out"),
        TakeAction(item_name="Crowbar"),
        UpdateRelationshipAction(npc_name="Emma", axis="affection", amount=12),
        UpdateRelationshipAction(npc_name="Emma", axis="trust", amount=-2),
        AddRelationshipNoteAction(npc_name="Emma", note="Seemed shaken"),
        AddGoalAction(horizon="short_term", goal_text="Find a weapon"),
        AddGoalAction(horizon="long_term", goal_text="Leave the city"),
        SetFlagAction(flag_name="power_grid_stable", value=False),
        DiscoverFlagAction(flag_name="power_grid_stable"),
        WaitAction(duration=Duration(until_time_of_day="evening")),
        StatusAddAction(status="panic"),
        NpcMoveAction(npc_name="Emma", destination="Your Building"),
        NpcStatusAction(npc_name="Emma", operation="ADD", status="frightened"),
        UpdateInventoryAction(item_name="First Aid Kit", operation="ADD", value="1"),
    )
    # Health is retired as an LLM-declarable action (docs/01-engine-authority.md);
    # it only ever changes through combat or item effects. Set directly here
    # since this fixture is exercising persistence, not the action pipeline.
    gm.player.hit_points = 55
    gm.player.stats.set(CharacterStat.HUNGER, 0.7)
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
        files.save(self.original, self.save_path)
        loaded = files.load(self.save_path)
        self.assertIsNotNone(loaded)
        self.loaded = loaded

    def test_player_position_and_condition(self):
        self.assertEqual(self.loaded.player.current_location_id, "zone_street")
        self.assertEqual(self.loaded.player.hit_points, 55)
        self.assertEqual(self.loaded.player.stats.get(CharacterStat.HUNGER), 0.7)

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
        self.assertEqual(self.loaded.narrative.minutes, self.original.narrative.minutes)
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
        self.assertEqual(self.loaded.world.time, "06:00 PM")
        self.assertEqual(self.loaded.world.date, "2023-10-01")

    def test_a_save_with_a_stale_world_clock_is_corrected_on_load(self):
        data = codec.to_dict(self.original)
        data["world"]["time"] = "12:00 PM"
        data["world"]["date"] = "2023-10-01"
        data["narrative"]["minutes"] = 3 * 1440 + 600
        rebuilt = codec.from_dict(data)
        self.assertEqual(rebuilt.world.time, "06:00 PM")
        self.assertEqual(rebuilt.world.date, "2023-10-04")

    def test_memory_tiers(self):
        self.assertEqual(self.loaded.memory.full_event_log, self.original.memory.full_event_log)
        self.assertEqual(self.loaded.memory.recent_events, self.original.memory.recent_events)
        self.assertEqual(self.loaded.memory.summaries, self.original.memory.summaries)

    def test_the_loaded_game_is_still_playable(self):
        facts = resolve_actions(self.loaded, MoveAction(destination="in"))
        self.assertFalse(facts[0].startswith("Refused:"), facts[0])
        self.assertEqual(self.loaded.player.current_location_id, "zone_building")


class StatsSaveTests(IsolatedSaveTestCase):
    """Spec 02, Stats (saves)."""

    def test_a_v5_round_trip_keeps_stats_and_asleep_exactly(self):
        gm = GameManager()
        for index, stat in enumerate(CharacterStat):
            gm.player.stats.set(stat, stat.min + (stat.max - stat.min) * (index + 1) / 37)
        gm.player.asleep = True
        gm.player.fractional_hp_loss = 0.25
        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        assert loaded is not None
        for stat in CharacterStat:
            self.assertEqual(loaded.player.stats.get(stat), gm.player.stats.get(stat))
        self.assertTrue(loaded.player.asleep)
        self.assertEqual(loaded.player.fractional_hp_loss, 0.25)

    def test_the_old_survival_fields_are_not_saved(self):
        files.save(GameManager(), self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            player = json.load(handle)["player"]
        for gone in ("hunger", "thirst", "morale"):
            self.assertNotIn(gone, player)


class WellFedSaveTests(IsolatedSaveTestCase):
    """Spec 03, Consuming (saves)."""

    def test_the_well_fed_timer_round_trips(self):
        gm = GameManager()
        gm.player.food_eaten_timer = 4321.5
        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        assert loaded is not None
        self.assertEqual(loaded.player.food_eaten_timer, 4321.5)

    def test_a_v5_save_is_discarded(self):
        files.save(GameManager(), self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["version"] = 5
        with open(self.save_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        self.assertIsNone(files.load(self.save_path))


class ClockSaveTests(IsolatedSaveTestCase):
    """Spec 01, Saves."""

    def test_schema_version_is_9(self):
        self.assertEqual(codec.SCHEMA_VERSION, 9)

    def test_a_v4_round_trip_keeps_minutes_and_drops_derived_fields(self):
        gm = GameManager()
        gm.narrative.minutes = 2 * 1440 + 95
        files.save(gm, self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            narrative = json.load(handle)["narrative"]
        self.assertEqual(narrative["minutes"], 2 * 1440 + 95)
        self.assertNotIn("day", narrative)
        self.assertNotIn("time_of_day", narrative)
        loaded = files.load(self.save_path)
        assert loaded is not None
        self.assertEqual(loaded.narrative.minutes, 2 * 1440 + 95)
        self.assertEqual(loaded.narrative.day, 3)


class ThermalSaveTests(IsolatedSaveTestCase):
    """Spec 06, Saves."""

    def _round_trip(self, gm):
        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        assert loaded is not None
        return loaded

    def test_thermal_state_round_trips_exactly(self):
        gm = GameManager()
        thermal = gm.player.thermal
        thermal.skin[BodyPart.HEAD] = 28.25
        thermal.node_temp[BodyPart.HAND_L] = 30.5
        thermal.primary[BodyPart.FOOT_L] = -0.5
        thermal.secondary[BodyPart.NECK] = 0.25
        thermal.metabolic_rate = 2.5
        thermal.primary_total = -0.4
        thermal.secondary_total = 0.3
        thermal.energy_mult = 1.1
        thermal.fluids_mult = 1.2
        thermal.fatigue_mult = 1.3
        thermal.core_cache = 36.25
        thermal.cache_counter = 55.5
        thermal.catch_cold = 41.5
        thermal.cold_reduction = 3.0
        thermal.sneeze_timer = 317.5
        thermal.sneeze_active = 12.5
        thermal.thermal_damage = 0.4
        thermal.thermal_duration = 33.5
        thermal.tick_frames = 1.0
        gm.player.stats.set(CharacterStat.TEMPERATURE, 35.5)
        gm.player.stats.set(CharacterStat.COLD_STRENGTH, 44.0)
        loaded = self._round_trip(gm).player
        self.assertEqual(loaded.thermal.to_dict(), thermal.to_dict())
        self.assertEqual(loaded.stats.get(CharacterStat.TEMPERATURE), 35.5)
        self.assertEqual(loaded.stats.get(CharacterStat.COLD_STRENGTH), 44.0)

    def test_power_state_round_trips(self):
        gm = GameManager()
        gm.world.power_on = False
        self.assertFalse(self._round_trip(gm).world.power_on)

    def test_a_save_without_thermal_data_loads_a_fresh_body(self):
        gm = GameManager()
        files.save(gm, self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        del data["player"]["thermal"]
        del data["world"]["power_on"]
        loaded = codec.from_dict(data)
        self.assertEqual(loaded.player.thermal.skin[BodyPart.HEAD], 33.0)
        self.assertTrue(loaded.world.power_on)

    def test_an_unknown_body_part_in_the_thermal_state_is_dropped(self):
        gm = GameManager()
        data = codec.to_dict(gm)
        data["player"]["thermal"]["skin"]["tail"] = 20.0
        loaded = codec.from_dict(data)
        self.assertEqual(len(loaded.player.thermal.skin), len(BodyPart))


class ClothingSaveTests(IsolatedSaveTestCase):
    """Spec 05, Saves."""

    def test_worn_items_and_wetness_round_trip(self):
        gm = GameManager()
        gm.player.worn[BodyLocation.TSHIRT].wetness = 37.5
        gm.player.worn[BodyLocation.SHOES].hit_points = 10
        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        assert loaded is not None
        worn = loaded.player.worn
        self.assertEqual(set(worn), set(gm.player.worn))
        self.assertEqual(worn[BodyLocation.TSHIRT].item.id, "item_tshirt")
        self.assertEqual(worn[BodyLocation.TSHIRT].wetness, 37.5)
        self.assertEqual(worn[BodyLocation.SHOES].hit_points, 10)

    def test_carried_wet_clothes_keep_their_wetness(self):
        gm = GameManager()
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_black_jacket"], wetness=80.0))
        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        assert loaded is not None
        self.assertEqual(loaded.player.inventory[-1].wetness, 80.0)

    def test_wetness_cap_is_100_and_round_trips_exactly(self):
        from data.items import WETNESS_MAX

        self.assertEqual(WETNESS_MAX, 100)
        gm = GameManager()
        gm.player.worn[BodyLocation.TSHIRT].wetness = 100.0
        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        assert loaded is not None
        self.assertEqual(loaded.player.worn[BodyLocation.TSHIRT].wetness, 100.0)

    def test_wetness_above_the_cap_clamps_on_load(self):
        data = codec.to_dict(GameManager())
        data["player"]["worn"]["base:tshirt"]["wetness"] = 150
        data["player"]["worn"]["base:shoes"]["wetness"] = -5
        loaded = codec.from_dict(data)
        self.assertEqual(loaded.player.worn[BodyLocation.TSHIRT].wetness, 100.0)
        self.assertEqual(loaded.player.worn[BodyLocation.SHOES].wetness, 0.0)

    def test_holes_round_trip(self):
        gm = GameManager()
        gm.player.worn[BodyLocation.TSHIRT].holes = {BodyPart.TORSO_UPPER}
        loaded = codec.from_dict(codec.to_dict(gm))
        self.assertEqual(loaded.player.worn[BodyLocation.TSHIRT].holes, {BodyPart.TORSO_UPPER})

    def test_an_unknown_worn_location_is_dropped(self):
        gm = GameManager()
        data = codec.to_dict(gm)
        data["player"]["worn"]["base:nonsense"] = {"item_id": "item_tshirt", "hit_points": 1}
        loaded = codec.from_dict(data)
        self.assertEqual(set(loaded.player.worn), set(gm.player.worn))

    def test_a_worn_item_at_the_wrong_location_is_dropped(self):
        gm = GameManager()
        data = codec.to_dict(gm)
        data["player"]["worn"] = {"base:shoes": {"item_id": "item_tshirt", "hit_points": 1}}
        loaded = codec.from_dict(data)
        self.assertEqual(loaded.player.worn, {})


class WeatherSaveTests(IsolatedSaveTestCase):
    """Spec 04, Saves."""

    def _stormy_game(self) -> GameManager:
        gm = GameManager()
        gm.world.seed = 4242
        gm.climate = type(gm.climate)(4242, gm.climate.start_date, gm.climate.start_minute_of_day)
        gm.narrative.minutes = 100 * 60
        gm.climate.advance_to(gm.narrative.minutes)
        gm.climate.start_period(99, 0.9)
        return gm

    def test_the_save_holds_the_seed_front_and_period(self):
        gm = self._stormy_game()
        files.save(gm, self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(data["world"]["seed"], 4242)
        self.assertEqual(set(data["weather"]), {"front", "period"})
        self.assertEqual(len(data["weather"]["period"]["stages"]), 5)

    def test_a_round_trip_gives_identical_weather_for_48_hours(self):
        gm = self._stormy_game()
        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        assert loaded is not None
        start = gm.narrative.minutes
        for hour in range(1, 49):
            minutes = start + hour * 60
            gm.climate.advance_to(minutes)
            loaded.climate.advance_to(minutes)
            self.assertEqual(gm.climate.sample(minutes), loaded.climate.sample(minutes))
            self.assertEqual(gm.climate.sample(minutes + 30), loaded.climate.sample(minutes + 30))
        self.assertEqual(gm.climate.front, loaded.climate.front)
        self.assertEqual(gm.climate.period, loaded.climate.period)

    def _saved_weather(self, gm):
        files.save(gm, self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            return json.load(handle)

    def _load_with_weather(self, mutate):
        gm = self._stormy_game()
        data = self._saved_weather(gm)
        mutate(data["weather"])
        restored = codec.from_dict(data)
        return gm, restored

    def test_a_non_default_front_round_trips(self):
        from modules.weather import AirFront

        gm = self._stormy_game()
        gm.climate.front = AirFront(positive=True, strength=0.7, start_hour=5)
        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        assert loaded is not None
        self.assertEqual(loaded.climate.front, AirFront(True, 0.7, 5))
        self.assertEqual(loaded.climate.last_hour, 100)

    def test_a_period_with_a_bad_start_hour_is_dropped(self):
        _, loaded = self._load_with_weather(lambda w: w["period"].update(start_hour="abc"))
        self.assertIsNone(loaded.climate.period)

    def test_a_period_with_a_bad_stage_value_is_dropped(self):
        _, loaded = self._load_with_weather(
            lambda w: w["period"]["stages"][1].update(precipitation="lots")
        )
        self.assertIsNone(loaded.climate.period)

    def test_a_period_with_an_unknown_stage_is_dropped(self):
        _, loaded = self._load_with_weather(
            lambda w: w["period"]["stages"][0].update(name="hailstorm")
        )
        self.assertIsNone(loaded.climate.period)
        from managers.climate import describe_weather

        minutes = loaded.narrative.minutes
        describe_weather(loaded.climate.sample(minutes), True)

    def test_a_bad_front_falls_back_to_the_air_mass(self):
        _, loaded = self._load_with_weather(lambda w: w["front"].update(strength="x"))
        self.assertEqual(loaded.climate.front.strength, 0.0)

    def test_a_save_without_a_period_round_trips(self):
        gm = GameManager()
        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        assert loaded is not None
        self.assertIsNone(loaded.climate.period)
        self.assertEqual(loaded.world.seed, gm.world.seed)


class SaveFileTests(IsolatedSaveTestCase):
    def test_save_is_written_atomically(self):
        files.save(GameManager(), self.save_path)
        self.assertTrue(Path(self.save_path).exists())
        # The temp file used during the write must not be left behind.
        self.assertFalse(Path(f"{self.save_path}.tmp").exists())

    def test_default_path_follows_the_module_attribute(self):
        # Regression: the path was a default argument bound at import time, so
        # SAVE_FILE could not be redirected.
        files.save(GameManager())
        self.assertTrue(Path(self.save_path).exists())

    def test_save_is_json_serializable_end_to_end(self):
        files.save(played_game(), self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        self.assertEqual(data["version"], codec.SCHEMA_VERSION)

    def test_a_save_with_no_quests_seeds_the_starting_roster(self):
        # v2 already had a "quests" key before any quest content existed, so
        # an old save has it present but empty -- that must not leave a
        # loaded game with no quests forever, same as an empty "npcs" list
        # falls back to build_starting_npcs().
        files.save(GameManager(), self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["quests"] = {}
        self.write(data)
        loaded = files.load(self.save_path)
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

        files.save(gm, self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["quests"] = {}
        self.write(data)

        loaded = files.load(self.save_path)
        assert loaded is not None
        quest = loaded.quests["quest_supply_run"]
        self.assertEqual(
            sorted(quest.completed_objectives),
            ["reach:zone_neighborhood", "take:item_crowbar"],
        )
        self.assertEqual(quest.status, QuestStatus.COMPLETED)

    def test_reconciliation_leaves_unachieved_objectives_open(self):
        files.save(GameManager(), self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["quests"] = {}
        self.write(data)

        loaded = files.load(self.save_path)
        assert loaded is not None
        quest = loaded.quests["quest_supply_run"]
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
        self.assertIsNone(files.load(self.save_path))

    def test_schema_mismatch_is_refused(self):
        files.save(GameManager(), self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["version"] = codec.SCHEMA_VERSION + 1
        self.write(data)
        self.assertIsNone(files.load(self.save_path))

    def test_a_v4_save_is_discarded_and_a_new_game_starts(self):
        files.save(GameManager(), self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["version"] = 4
        self.write(data)
        self.assertIsNone(files.load(self.save_path))

    def test_a_v3_save_is_discarded_and_a_new_game_starts(self):
        files.save(GameManager(), self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["version"] = 3
        self.write(data)
        self.assertIsNone(files.load(self.save_path))

    def test_a_v1_save_is_discarded_cleanly_not_crashed(self):
        # v1 predates NpcEntity.goals/.knowledge and discovered_flags -- the
        # existing "unreadable save -> fresh game" policy handles this with
        # no migration code, by design (adapters/save/files.py module doc).
        self.write({"version": 1, "player": {}, "narrative": {}})
        self.assertIsNone(files.load(self.save_path))

    def test_corrupt_json_returns_none(self):
        with open(self.save_path, "w", encoding="utf-8") as handle:
            handle.write("{not json")
        self.assertIsNone(files.load(self.save_path))

    def test_unknown_ids_are_dropped_not_fatal(self):
        files.save(played_game(), self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["player"]["inventory"].append({"item_id": "item_deleted", "hit_points": 1})
        data["player"]["trait_ids"].append("TraitID_Removed")
        data["player"]["conditions"].append("haunted")
        data["world"]["ground_items"]["location_id_atlantis"] = [
            {"item_id": "item_crowbar", "hit_points": 5}
        ]
        self.write(data)

        loaded = files.load(self.save_path)
        self.assertIsNotNone(loaded)
        self.assertNotIn("item_deleted", [e.item.id for e in loaded.player.inventory])
        self.assertNotIn("location_id_atlantis", loaded.world.locations)

    def test_unknown_player_location_falls_back(self):
        files.save(GameManager(), self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["player"]["current_location_id"] = "location_id_atlantis"
        self.write(data)

        loaded = files.load(self.save_path)
        self.assertIsNotNone(loaded)
        self.assertIn(loaded.player.current_location_id, loaded.world.locations)

    def test_save_with_no_npcs_falls_back_to_the_roster(self):
        files.save(GameManager(), self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["npcs"] = []
        self.write(data)

        loaded = files.load(self.save_path)
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

        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        self.assertEqual(loaded.player.current_place, "the kitchen")

    def test_death_state_round_trips(self):
        gm = GameManager()
        gm.narrative.game_over = True
        gm.narrative.death_cause = "Orton bled out from a knife wound."

        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        self.assertTrue(loaded.narrative.game_over)
        self.assertEqual(loaded.narrative.death_cause, "Orton bled out from a knife wound.")


class HandEditedFieldTests(unittest.TestCase):
    """Hand-edited values of the wrong type load as safe defaults."""

    def test_game_over_string_false_is_not_true(self):
        data = codec.to_dict(GameManager())
        data["narrative"]["game_over"] = "false"
        loaded = files.from_saved_data(data)
        self.assertIsNotNone(loaded)
        self.assertFalse(loaded.narrative.game_over)

    def test_null_death_cause_becomes_empty_string(self):
        data = codec.to_dict(GameManager())
        data["narrative"]["death_cause"] = None
        loaded = files.from_saved_data(data)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.narrative.death_cause, "")

    def test_null_current_place_becomes_empty_string(self):
        data = codec.to_dict(GameManager())
        data["player"]["current_place"] = None
        loaded = files.from_saved_data(data)
        self.assertIsNotNone(loaded)
        self.assertEqual(loaded.player.current_place, "")


if __name__ == "__main__":
    unittest.main()
