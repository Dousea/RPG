"""Persistence: full round trip, schema guarding, and tolerance of bad saves."""

import json
import random
import unittest
from pathlib import Path

from adapters.save import codec, files
from data.items import ITEMS
from managers.game import GameManager
from managers.simulation import SimulationCore
from modules.action.types import (
    AddGoalAction,
    AddRelationshipNoteAction,
    Duration,
    MoveAction,
    TakeAction,
    WaitAction,
)
from modules.body.parts import BodyLocation, BodyPart
from modules.body.stats import CharacterStat
from modules.character.equipment import CharacterArmorSlot
from modules.character.state import CharacterCondition
from modules.entity.corpse import CorpseEntity
from modules.entity.item import ItemEntity
from modules.entity.zombie import AttackSide, ZombieEntity, ZombieState
from modules.story.quest import QuestState, QuestStatus
from modules.world.room import ContainerEntity, RoomEntity
from tests.support import (
    IsolatedSaveTestCase,
    adjust_regard,
    npc_of,
    resolve_actions,
    set_health,
    simulate,
)


def played_game() -> GameManager:
    """A game with something changed on every persisted axis."""
    gm = GameManager()
    resolve_actions(
        gm,
        AddGoalAction(horizon="short_term", goal_text="Find a weapon"),
        MoveAction(destination="out"),
    )
    resolve_actions(gm, MoveAction(destination="out"))
    resolve_actions(
        gm,
        TakeAction(item_name="Crowbar"),
        AddRelationshipNoteAction(npc_name="Emma", note="Seemed shaken"),
    )
    resolve_actions(
        gm,
        AddGoalAction(horizon="long_term", goal_text="Leave the city"),
        WaitAction(duration=Duration(until_time_of_day="evening")),
    )
    adjust_regard(gm, "npc_emma", affection=12, trust=-2)
    gm.narrative.flags["power_grid_stable"] = False
    SimulationCore(gm).discover_flag("power_grid_stable")
    gm.player.conditions.append(CharacterCondition.PANIC)
    npc_of(gm, "Emma").status.append("frightened")
    # Health is retired as an LLM-declarable action (docs/architecture/engine-authority.md);
    # it only ever changes through combat or item effects. Set directly here
    # since this fixture is exercising persistence, not the action pipeline.
    set_health(gm.player, 55)
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

    def test_derived_health_is_not_reset_to_max_on_load(self):
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
        street_names = [e.item.name for e in street.entities if isinstance(e, ItemEntity)]
        self.assertNotIn("Crowbar", street_names)
        # The alley planks were never touched.
        self.assertIn("Plank", street_names)
        self.assertEqual(home.entities, [])

    def test_character_fields_round_trip(self):
        """character-creation: Saves."""
        assert self.loaded is not None
        original, loaded = self.original.player, self.loaded.player
        self.assertEqual(loaded.traits, original.traits)
        self.assertEqual(loaded.appearance, original.appearance)
        self.assertEqual(loaded.occupation_id, "unemployed")
        self.assertEqual(loaded.job_title, "Software Developer")
        self.assertEqual(loaded.skills, original.skills)
        self.assertEqual(loaded.skill_boosts, original.skill_boosts)
        self.assertEqual(loaded.skills["fitness"].level, 5)
        self.assertEqual(loaded.skills["fitness"].xp, 37500)

    def test_skill_timers_and_exercise_state_round_trip(self):
        """skills: Saves."""
        assert self.loaded is not None
        player = self.original.player
        player.loss_timers = {"fitness": 1234.0, "strength": -49000.0}
        player.loss_timer_steps = {"fitness": 1, "strength": -41}
        player.exercise.regularity = {"squats": 12.5}
        player.exercise.last_done_minute = {"squats": 90}
        player.exercise.future_stiffness = {"legs": 3.5}
        player.exercise.region_timers = {"legs": 60}
        restored = codec.from_dict(codec.to_dict(self.original)).player
        self.assertEqual(restored.loss_timers, player.loss_timers)
        self.assertEqual(restored.loss_timer_steps, player.loss_timer_steps)
        self.assertEqual(restored.exercise, player.exercise)

    def test_a_created_character_round_trips(self):
        from managers.character import creation

        build = creation.randomize(random.Random(3))
        gm = GameManager(player=creation.new_player(build))
        loaded = codec.from_dict(codec.to_dict(gm))
        self.assertEqual(loaded.player.appearance, build.appearance)
        self.assertEqual(loaded.player.traits, gm.player.traits)
        self.assertEqual(loaded.player.name, build.appearance.full_name)
        self.assertEqual(
            sorted(e.item.id for e in loaded.player.worn.values()), sorted(build.outfit)
        )

    def test_unknown_trait_ids_are_dropped_on_load(self):
        data = codec.to_dict(GameManager())
        data["player"]["trait_ids"] = ["strong", "nosuchtrait"]
        loaded = codec.from_dict(data)
        assert loaded is not None
        self.assertEqual(loaded.player.traits, ["strong"])

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
    """survival-stats: Stats (saves)."""

    def test_a_v5_round_trip_keeps_stats_and_asleep_exactly(self):
        gm = GameManager()
        for index, stat in enumerate(CharacterStat):
            gm.player.stats.set(stat, stat.min + (stat.max - stat.min) * (index + 1) / 37)
        gm.player.asleep = True
        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        assert loaded is not None
        for stat in CharacterStat:
            self.assertEqual(loaded.player.stats.get(stat), gm.player.stats.get(stat))
        self.assertTrue(loaded.player.asleep)

    def test_the_old_survival_fields_are_not_saved(self):
        files.save(GameManager(), self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            player = json.load(handle)["player"]
        for gone in ("hunger", "thirst", "morale"):
            self.assertNotIn(gone, player)


class WellFedSaveTests(IsolatedSaveTestCase):
    """status-effects: Consuming (saves)."""

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


class RoomSaveTests(IsolatedSaveTestCase):
    """carrying-and-loot: Saves: each container's opened flag and contents, each room's proc_spawned, current_room."""

    def test_a_bags_pending_roll_round_trips(self):
        for pending in (True, False):
            bag = ItemEntity(item=ITEMS["item_schoolbag"], loot_pending=pending)
            loaded = codec._item_entity_from_dict(codec._item_entity_to_dict(bag))
            assert loaded is not None
            self.assertEqual(loaded.loot_pending, pending)

    def test_rooms_containers_and_the_current_room_round_trip(self):
        gm = GameManager()
        counter = ContainerEntity(
            container_id="test_counter",
            name="test counter",
            kind="counter",
            capacity=50,
            aliases=["worktop"],
            source=("kitchen", "counter"),
            opened=True,
        )
        counter.contents.append(ItemEntity(item=ITEMS["item_canned_beans"]))
        shelf = ContainerEntity(
            container_id="test_shelf",
            name="test shelf",
            kind="shelves",
            capacity=15,
            fixed=True,
        )
        room = RoomEntity(
            room_id="test_room",
            name="test room",
            kind="kitchen",
            aliases=["galley"],
            containers=[counter, shelf],
            proc_spawned={"kitchen_dishes": 1},
        )
        zone = gm.world.locations["zone_home"]
        zone.rooms = {"test_room": room}
        zone.entry_room = "test_room"
        gm.player.current_room = "test_room"
        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        assert loaded is not None
        got = loaded.world.locations["zone_home"]
        self.assertEqual(got.entry_room, "test_room")
        self.assertEqual(loaded.player.current_room, "test_room")
        back = got.rooms["test_room"]
        self.assertEqual((back.name, back.kind, back.aliases), ("test room", "kitchen", ["galley"]))
        self.assertEqual(back.proc_spawned, {"kitchen_dishes": 1})
        first, second = back.containers
        self.assertEqual(
            (first.container_id, first.capacity, first.source),
            ("test_counter", 50, ("kitchen", "counter")),
        )
        self.assertTrue(first.opened)
        self.assertEqual([e.item.id for e in first.contents], ["item_canned_beans"])
        self.assertEqual((second.opened, second.fixed, second.source), (False, True, None))


class NewZoneSaveTests(IsolatedSaveTestCase):
    """carrying-and-loot: Saves: the six zones, their rooms and their barriers survive a round trip."""

    def test_an_opened_clinic_container_and_a_broken_in_window_round_trip(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_clinic"
        gm.player.current_room = "exam_room"
        clinic = gm.world.locations["zone_clinic"]
        counter = clinic.rooms["exam_room"].containers[0]
        counter.opened = True
        counter.contents.append(ItemEntity(item=ITEMS["item_bandage"]))
        clinic.rooms["exam_room"].proc_spawned = {"medical_clinic_drugs": 1}
        gm.world.barriers["window_pharmacy"].broken = True
        gm.world.barriers["door_flat_tenant"].locked = False
        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        assert loaded is not None
        self.assertEqual(loaded.player.current_location_id, "zone_clinic")
        self.assertEqual(loaded.player.current_room, "exam_room")
        got = loaded.world.locations["zone_clinic"].rooms["exam_room"]
        self.assertTrue(got.containers[0].opened)
        self.assertEqual([e.item.id for e in got.containers[0].contents], ["item_bandage"])
        self.assertEqual(got.proc_spawned, {"medical_clinic_drugs": 1})
        self.assertTrue(loaded.world.barriers["window_pharmacy"].broken)
        self.assertFalse(loaded.world.barriers["door_flat_tenant"].locked)
        self.assertEqual(
            loaded.world.locations["zone_neighborhood"].connections["clinic"], "zone_clinic"
        )

    def test_a_schema_23_save_is_refused(self):
        files.save(GameManager(), self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["version"] = 23
        with open(self.save_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        self.assertIsNone(files.load(self.save_path))


class ClockSaveTests(IsolatedSaveTestCase):
    """clock: Saves."""

    def test_schema_version_is_24(self):
        self.assertEqual(codec.SCHEMA_VERSION, 24)

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
    """body-temperature: Saves."""

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
    """clothing: Saves."""

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
    """weather: Saves."""

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
        from modules.world.weather import AirFront

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
        from managers.world.climate import describe_weather

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
        resolve_actions(gm, MoveAction(destination="out"))  # zone_home -> zone_building
        resolve_actions(gm, MoveAction(destination="out"))  # zone_building -> zone_street
        resolve_actions(gm, TakeAction(item_name="Crowbar"))
        resolve_actions(gm, MoveAction(destination="out"))  # zone_street -> zone_neighborhood

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
        # zone_home is the starting zone and "the window" is no room of it, so it
        # stays a spot inside the zone.
        resolve_actions(gm, MoveAction(destination="the window"))
        self.assertEqual(gm.player.current_place, "the window")

        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        self.assertEqual(loaded.player.current_place, "the window")

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


class ZombieSaveTests(IsolatedSaveTestCase):
    """zombies: Saves: the outbreak time, zombies, next id, redistribution time and sneaking."""

    def test_zombies_the_outbreak_and_sneaking_round_trip(self):
        gm = GameManager()
        gm.world.outbreak_started_at = 4300
        gm.world.last_redistribution_minute = 5020
        gm.world.next_zombie_number = 8
        gm.world.zombie_kills = {"zone_street": 3}
        gm.player.sneaking = True
        gm.world.zombies["z7"] = ZombieEntity(
            zombie_id="z7",
            zone_id="zone_street",
            health=2.25,
            speed_type=2,
            speed_mod=0.9,
            lunger=True,
            strength=3,
            memory=800,
            sight=3,
            hearing=2,
            state=ZombieState.ATTACKING,
            gap=1.0,
            facing_cos=0.5,
            time_since_seen=360.0,
            has_chased=True,
            bonus_spot_time=540.0,
            side=AttackSide.BEHIND,
            sound_gap=12.5,
        )
        loaded = codec.from_dict(codec.to_dict(gm))
        self.assertEqual(loaded.world.outbreak_started_at, 4300)
        self.assertEqual(loaded.world.last_redistribution_minute, 5020)
        self.assertEqual(loaded.world.next_zombie_number, 8)
        self.assertEqual(loaded.world.zombie_kills, {"zone_street": 3})
        self.assertTrue(loaded.player.sneaking)
        self.assertEqual(loaded.world.zombies, gm.world.zombies)

    def test_a_game_before_the_outbreak_has_no_zombies(self):
        loaded = codec.from_dict(codec.to_dict(GameManager()))
        self.assertIsNone(loaded.world.outbreak_started_at)
        self.assertEqual(loaded.world.zombies, {})
        self.assertFalse(loaded.player.sneaking)

    def test_a_zombie_in_an_unknown_zone_is_dropped(self):
        gm = GameManager()
        gm.world.zombies["z1"] = ZombieEntity(
            zombie_id="z1",
            zone_id="zone_street",
            health=1.0,
            speed_type=3,
            speed_mod=0.6,
            lunger=False,
            strength=3,
            memory=800,
            sight=2,
            hearing=2,
        )
        data = codec.to_dict(gm)
        data["world"]["zombies"][0]["zone_id"] = "zone_moon"
        loaded = codec.from_dict(data)
        self.assertEqual(loaded.world.zombies, {})


class LifecycleSaveTests(IsolatedSaveTestCase):
    """zombie-lifecycle: Saves: corpses, the smell zone, crawler flags, outfits and worn items."""

    def dressed_zombie(self) -> ZombieEntity:
        jacket = ItemEntity(item=ITEMS["item_black_jacket"])
        jacket.holes.add(BodyPart.TORSO_UPPER)
        return ZombieEntity(
            zombie_id="z4",
            zone_id="zone_street",
            health=1.5,
            speed_type=3,
            speed_mod=0.35,
            lunger=False,
            strength=3,
            memory=800,
            sight=2,
            hearing=2,
            female=True,
            outfit="police",
            worn={BodyLocation.JACKET: jacket},
            attached=ItemEntity(item=ITEMS["item_kitchen_knife"], condition=7),
            crawling=True,
            become_crawler=True,
            was_fake_dead=True,
            risen_from_player=True,
        )

    def test_a_zombie_keeps_its_outfit_worn_items_and_flags(self):
        gm = GameManager()
        gm.world.zombies["z4"] = self.dressed_zombie()
        loaded = codec.from_dict(codec.to_dict(gm))
        zombie = loaded.world.zombies["z4"]
        self.assertEqual(loaded.world.zombies, gm.world.zombies)
        self.assertTrue(zombie.female)
        self.assertEqual(zombie.outfit, "police")
        self.assertEqual(zombie.worn[BodyLocation.JACKET].holes, {BodyPart.TORSO_UPPER})
        assert zombie.attached is not None
        self.assertEqual(zombie.attached.condition, 7)
        self.assertTrue(zombie.crawling and zombie.become_crawler)
        self.assertTrue(zombie.was_fake_dead and zombie.risen_from_player)

    def test_corpses_the_next_number_and_the_smell_zone_round_trip(self):
        gm = GameManager()
        gm.world.corpses["c2"] = CorpseEntity(
            corpse_id="c2",
            zone_id="zone_street",
            gap=6.0,
            female=False,
            outfit="biker",
            died_at=4400,
            rot_at_death=2,
            skeleton=False,
            contents=[ItemEntity(item=ITEMS["item_crowbar"], condition=9)],
            searched=True,
            fake_dead=True,
            crawling=True,
            risen_from_player=False,
        )
        gm.world.next_corpse_number = 3
        gm.world.smell_zone_id = "zone_street"
        loaded = codec.from_dict(codec.to_dict(gm))
        self.assertEqual(loaded.world.corpses, gm.world.corpses)
        self.assertEqual(loaded.world.next_corpse_number, 3)
        self.assertEqual(loaded.world.smell_zone_id, "zone_street")

    def test_which_item_is_the_attached_weapon_survives_a_save(self):
        gm = GameManager()
        contents = [
            ItemEntity(item=ITEMS["item_hammer"]),
            ItemEntity(item=ITEMS["item_hand_axe"], condition=5),
        ]
        gm.world.corpses["c2"] = CorpseEntity(
            corpse_id="c2",
            zone_id="zone_street",
            gap=6.0,
            female=False,
            outfit="biker",
            died_at=4400,
            rot_at_death=2,
            contents=contents,
            attached=contents[1],
        )
        loaded = codec.from_dict(codec.to_dict(gm)).world.corpses["c2"]
        self.assertIs(loaded.attached, loaded.contents[1])
        assert loaded.attached is not None
        self.assertEqual(loaded.attached.item.id, "item_hand_axe")

    def test_a_corpse_in_an_unknown_zone_is_dropped(self):
        gm = GameManager()
        gm.world.corpses["c1"] = CorpseEntity(
            corpse_id="c1",
            zone_id="zone_street",
            gap=2.0,
            female=True,
            outfit="young",
            died_at=0,
            rot_at_death=1,
        )
        data = codec.to_dict(gm)
        data["world"]["corpses"][0]["zone_id"] = "zone_moon"
        self.assertEqual(codec.from_dict(data).world.corpses, {})


class SocialSaveTests(IsolatedSaveTestCase):
    """llm-contract: Saves."""

    def played(self) -> GameManager:
        gm = GameManager()
        npc_of(gm, "Emma").following = True
        log = gm.narrative.social_log
        log.day = 2
        log.record_use("npc_emma", "chat")
        log.record_use("npc_emma", "chat")
        log.record_use("npc_emma", "give")
        log.refuse("npc_emma", "follow", 95)
        log.told_topics.add("outbreak_news")
        gm.world.fired_beats["outbreak_begins"] = 2760
        return gm

    def reload(self, gm: GameManager) -> GameManager:
        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        assert loaded is not None
        return loaded

    def test_following_round_trips(self):
        loaded = self.reload(self.played())
        self.assertIs(npc_of(loaded, "Emma").following, True)
        self.assertIs(npc_of(loaded, "Marcus").following, False)

    def test_the_social_log_round_trips(self):
        loaded = self.reload(self.played())
        log = loaded.narrative.social_log
        self.assertEqual(log.day, 2)
        self.assertEqual(log.counts, {"npc_emma|chat": 2, "npc_emma|give": 1})
        self.assertEqual(log.refusals, {"npc_emma|follow": 95})
        self.assertEqual(log.told_topics, {"outbreak_news"})

    def test_fired_beats_round_trip(self):
        loaded = self.reload(self.played())
        self.assertEqual(loaded.world.fired_beats, {"outbreak_begins": 2760})

    def test_the_social_log_is_saved_with_narrative_as_keyed_json(self):
        data = codec.to_dict(self.played())
        self.assertEqual(
            data["narrative"]["social_log"],
            {
                "day": 2,
                "counts": {"npc_emma|chat": 2, "npc_emma|give": 1},
                "refusals": {"npc_emma|follow": 95},
                "told_topics": ["outbreak_news"],
            },
        )

    def test_the_dropped_narrative_fields_are_not_saved(self):
        narrative = codec.to_dict(GameManager())["narrative"]
        for dropped in ("player_status", "apocalypse_stage", "conditions"):
            self.assertNotIn(dropped, narrative)

    def test_a_fired_beat_stays_fired_after_a_reload(self):
        gm = GameManager()
        gm.advance_clock(2750)
        simulate(gm, WaitAction(duration=Duration(minutes=30)), rng=random.Random(1))
        loaded = self.reload(gm)
        self.assertEqual(loaded.world.outbreak_started_at, 2760)
        simulate(loaded, WaitAction(duration=Duration(minutes=30)), rng=random.Random(1))
        self.assertEqual(loaded.world.outbreak_started_at, 2760)
        self.assertEqual(loaded.world.fired_beats, {"outbreak_begins": 2760})

    def test_a_garbled_social_log_loads_empty(self):
        data = codec.to_dict(GameManager())
        data["narrative"]["social_log"] = {"counts": "nope", "refusals": 3, "told_topics": 7}
        loaded = codec.from_dict(data)
        log = loaded.narrative.social_log
        self.assertEqual((log.counts, log.refusals, log.told_topics), ({}, {}, set()))


class MeleeSaveTests(IsolatedSaveTestCase):
    """melee: Saves: weapon condition, hits_taken, down_until and zombie_kills."""

    def test_weapon_condition_zombie_hits_and_kills_round_trip(self):
        gm = GameManager()
        crowbar = ItemEntity(item=ITEMS["item_crowbar"])
        crowbar.condition = 7
        gm.player.inventory.append(crowbar)
        broken = ItemEntity(item=ITEMS["item_kitchen_knife"])
        broken.condition = 0
        gm.player.inventory.append(broken)
        gm.player.zombie_kills = 4
        gm.world.zombies["z1"] = ZombieEntity(
            zombie_id="z1",
            zone_id="zone_street",
            health=1.0,
            speed_type=3,
            speed_mod=0.6,
            lunger=False,
            strength=3,
            memory=800,
            sight=2,
            hearing=2,
            hits_taken=3,
            down_until=1234,
        )
        loaded = codec.from_dict(codec.to_dict(gm))
        conditions = {e.item.id: e.condition for e in loaded.player.inventory}
        self.assertEqual(conditions["item_crowbar"], 7)
        self.assertEqual(conditions["item_kitchen_knife"], 0)
        self.assertTrue(
            next(e for e in loaded.player.inventory if e.item.id == "item_kitchen_knife").broken
        )
        self.assertEqual(loaded.player.zombie_kills, 4)
        self.assertEqual(loaded.world.zombies["z1"].hits_taken, 3)
        self.assertEqual(loaded.world.zombies["z1"].down_until, 1234)

    def test_a_new_weapon_starts_at_full_condition(self):
        self.assertEqual(ItemEntity(item=ITEMS["item_crowbar"]).condition, 15)
        self.assertEqual(ItemEntity(item=ITEMS["item_kitchen_knife"]).condition, 10)


class BodySaveTests(IsolatedSaveTestCase):
    """health: Saves."""

    def test_the_body_zombie_infection_fields_pain_effect_and_antibiotics_round_trip(self):
        gm = GameManager()
        player = gm.player
        part = player.body[BodyPart.FOREARM_L]
        part.health = 61.5
        part.scratch_time = 3.25
        part.cut_time = 9.5
        part.bite_time = 40.0
        part.bleeding_time = 2.75
        part.bandage = "item_bandage"
        part.bandage_life = 3.5
        part.bandage_alcoholic = True
        part.bandage_xp_ready = False
        part.zombie_infected = True
        part.infected_wound = True
        part.wound_infection = 4.5
        part.alcohol = 1.5
        part.extra_pain = 20.0
        part.stiffness = 7.0
        player.zombie_infection_since = 12.5
        player.zombie_infection_hours = 60.0
        player.pain_effect_minutes = 30.0
        player.reduce_infection_power = 44.0
        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        assert loaded is not None
        self.assertEqual(loaded.player.body, player.body)
        self.assertEqual(loaded.player.zombie_infection_since, 12.5)
        self.assertEqual(loaded.player.zombie_infection_hours, 60.0)
        self.assertEqual(loaded.player.pain_effect_minutes, 30.0)
        self.assertEqual(loaded.player.reduce_infection_power, 44.0)

    def test_an_uninfected_player_keeps_zombie_infection_since_unset(self):
        files.save(GameManager(), self.save_path)
        loaded = files.load(self.save_path)
        assert loaded is not None
        self.assertIsNone(loaded.player.zombie_infection_since)

    def test_a_medical_items_uses_round_trip(self):
        gm = GameManager()
        pills = ItemEntity(item=ITEMS["item_painkillers"])
        pills.uses = 7
        gm.player.inventory.append(pills)
        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        assert loaded is not None
        saved = [e for e in loaded.player.inventory if e.item.id == "item_painkillers"]
        self.assertEqual([e.uses for e in saved], [7])

    def test_player_hit_points_and_fractional_loss_are_no_longer_saved(self):
        data = codec.to_dict(GameManager())
        self.assertNotIn("hit_points", data["player"])
        self.assertNotIn("fractional_hp_loss", data["player"])

    def test_stiffness_lives_on_the_part(self):
        gm = GameManager()
        gm.player.body[BodyPart.UPPERLEG_L].stiffness = 5.0
        loaded = codec.from_dict(codec.to_dict(gm))
        self.assertEqual(loaded.player.body[BodyPart.UPPERLEG_L].stiffness, 5.0)

    def test_an_unknown_part_in_the_body_is_dropped(self):
        data = codec.to_dict(GameManager())
        data["player"]["body"]["tail"] = {"health": 3}
        loaded = codec.from_dict(data)
        self.assertEqual(set(loaded.player.body), set(BodyPart))


class BarrierSaveTests(IsolatedSaveTestCase):
    """doors: Saves."""

    def test_barriers_plank_healths_and_the_players_barrier_round_trip(self):
        gm = GameManager()
        door = gm.world.barriers["door_apartment"]
        door.open = True
        door.locked = False
        door.health = 321
        door.barricades["zone_home"] = [1000, 640]
        door.barricades["zone_building"] = [88]
        lobby = gm.world.barriers["door_lobby"]
        lobby.broken = True
        gm.player.at_barrier = "door_apartment"
        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        assert loaded is not None
        self.assertEqual(loaded.world.barriers, gm.world.barriers)
        self.assertEqual(loaded.player.at_barrier, "door_apartment")
        self.assertEqual(
            loaded.world.barriers["door_apartment"].barricades["zone_home"], [1000, 640]
        )

    def test_a_barrier_missing_from_a_save_is_rebuilt_from_the_data(self):
        gm = GameManager()
        data = codec.to_dict(gm)
        del data["world"]["barriers"]
        loaded = codec.from_dict(data)
        self.assertEqual(
            set(loaded.world.barriers),
            {
                "door_apartment",
                "door_lobby",
                "window_bodega",
                "door_flat_vacant",
                "door_flat_tenant",
                "window_pharmacy",
                "door_clinic",
                "window_supermarket",
                "door_hardware",
            },
        )

    def test_thumping_fields_round_trip(self):
        gm = GameManager()
        zombie = ZombieEntity(
            zombie_id="z1",
            zone_id="zone_building",
            health=2.0,
            speed_type=3,
            speed_mod=0.6,
            lunger=False,
            strength=3,
            memory=800,
            sight=2,
            hearing=2,
            state=ZombieState.THUMPING,
            thump_barrier="door_apartment",
            thump_rate=1.40625,
            thump_carry=0.25,
            thump_cooldown=2,
            was_chasing=True,
        )
        gm.world.zombies["z1"] = zombie
        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        assert loaded is not None
        self.assertEqual(loaded.world.zombies["z1"], zombie)

    def test_the_nails_uses_and_the_building_round_trip(self):
        gm = GameManager()
        nails = ItemEntity(item=ITEMS["item_nails"])
        nails.uses = 3
        gm.player.inventory.append(nails)
        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        assert loaded is not None
        saved = [e for e in loaded.player.inventory if e.item.id == "item_nails"]
        self.assertEqual([e.uses for e in saved], [3])
        self.assertEqual(loaded.world.locations["zone_building"].building, "apartment_block")


class CarrySaveTests(IsolatedSaveTestCase):
    """carrying-and-loot: Saves: nested contents, the held and worn bags and a carried body."""

    def test_a_bag_with_a_bag_in_it_round_trips(self):
        gm = GameManager()
        outer = ItemEntity(item=ITEMS["item_duffel_bag"])
        inner = ItemEntity(item=ITEMS["item_toolbox"])
        inner.contents.append(ItemEntity(item=ITEMS["item_hammer"]))
        outer.contents.append(inner)
        outer.contents.append(ItemEntity(item=ITEMS["item_canned_beans"]))
        gm.player.inventory.append(outer)
        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        assert loaded is not None
        bag = loaded.player.inventory[-1]
        self.assertEqual(bag.item.id, "item_duffel_bag")
        self.assertEqual([e.item.id for e in bag.contents], ["item_toolbox", "item_canned_beans"])
        self.assertEqual([e.item.id for e in bag.contents[0].contents], ["item_hammer"])

    def test_the_shoulder_bag_and_a_worn_bag_round_trip(self):
        gm = GameManager()
        back = ItemEntity(item=ITEMS["item_schoolbag"])
        back.contents.append(ItemEntity(item=ITEMS["item_bandage"]))
        gm.player.equipment[CharacterArmorSlot.SHOULDERS] = back
        gm.player.worn[BodyLocation.SATCHEL] = ItemEntity(item=ITEMS["item_satchel"])
        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        assert loaded is not None
        shoulders = loaded.player.equipment[CharacterArmorSlot.SHOULDERS]
        assert shoulders is not None
        self.assertEqual([e.item.id for e in shoulders.contents], ["item_bandage"])
        self.assertEqual(loaded.player.worn[BodyLocation.SATCHEL].item.id, "item_satchel")

    def test_a_carried_body_round_trips(self):
        gm = GameManager()
        gm.player.carrying_corpse = "c4"
        gm.player.carrying_skeleton = True
        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        assert loaded is not None
        self.assertEqual(loaded.player.carrying_corpse, "c4")
        self.assertTrue(loaded.player.carrying_skeleton)
