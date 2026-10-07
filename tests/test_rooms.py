"""Spec 25, Rooms and containers: the room layouts, the starting kit and moving between rooms."""

import random
import unittest

from data.items import ITEMS
from managers.game import GameManager
from managers.rooms import resolve_container, resolve_room
from modules.action.types import MoveAction
from modules.entity.item import ItemEntity
from modules.room import ContainerEntity
from tests.support import simulate


def room_id(zone, name: str) -> str | None:
    room = resolve_room(zone, name)
    return room.room_id if room is not None else None


def container_id(found) -> str | None:
    return found.container_id if isinstance(found, ContainerEntity) else None


def ids_in(container) -> list[str]:
    return [e.item.id for e in container.contents]


def ground_ids(gm: GameManager, zone_id: str) -> list[str]:
    return [e.item.id for e in gm.world.locations[zone_id].entities if isinstance(e, ItemEntity)]


class LayoutTests(unittest.TestCase):
    """Spec 25, The rooms."""

    def setUp(self):
        self.gm = GameManager()
        self.home = self.gm.world.locations["zone_home"]
        self.building = self.gm.world.locations["zone_building"]
        self.store = self.gm.world.locations["zone_bodega"]

    def test_the_apartment_has_four_rooms_with_their_containers_in_layout_order(self):
        self.assertEqual(
            {rid: [c.name for c in room.containers] for rid, room in self.home.rooms.items()},
            {
                "kitchen": ["kitchen counter", "kitchen cupboards", "fridge", "freezer"],
                "bedroom": ["wardrobe", "dresser", "bedside table"],
                "bathroom": ["medicine cabinet", "bathroom counter"],
                "living_room": ["side table", "living room shelves"],
            },
        )

    def test_the_building_has_a_hallway_a_laundry_room_and_a_basement(self):
        self.assertEqual(
            {rid: [c.name for c in room.containers] for rid, room in self.building.rooms.items()},
            {
                "hallway": ["first-aid cabinet"],
                "laundry_room": ["laundry counter"],
                "basement": ["storage shelves", "tool cabinet"],
            },
        )

    def test_the_corner_store_has_a_shop_floor_and_a_storeroom(self):
        self.assertEqual(
            {rid: [c.name for c in room.containers] for rid, room in self.store.rooms.items()},
            {
                "shop_floor": ["till counter", "store fridge", "snack shelves", "drinks shelves"],
                "storeroom": ["stock crates"],
            },
        )

    def test_the_freezer_holds_15_kg_and_every_other_container_50(self):
        capacities = {
            c.name: c.capacity
            for zone in (self.home, self.building, self.store)
            for room in zone.rooms.values()
            for c in room.containers
        }
        self.assertEqual(capacities.pop("freezer"), 15)
        self.assertEqual(set(capacities.values()), {50})

    def test_the_streets_and_the_neighbourhood_have_no_rooms(self):
        for zone_id in ("zone_street", "zone_neighborhood"):
            self.assertEqual(self.gm.world.locations[zone_id].rooms, {})

    def test_container_names_are_unique_in_a_zone(self):
        for zone in (self.home, self.building, self.store):
            names = [c.name for room in zone.rooms.values() for c in room.containers]
            self.assertEqual(len(names), len(set(names)))

    def test_every_source_has_a_generated_table(self):
        from data.loot_tables import ROOM_TABLES

        for zone in (self.home, self.building, self.store):
            for room in zone.rooms.values():
                for c in room.containers:
                    if c.source is not None:
                        self.assertIn(c.source[1], ROOM_TABLES[c.source[0]], c.name)

    def test_the_player_starts_in_the_living_room(self):
        self.assertEqual(self.gm.player.current_room, "living_room")
        self.assertEqual(self.home.entry_room, "living_room")


class StartingKitTests(unittest.TestCase):
    """Spec 25, The starting kit."""

    def setUp(self):
        self.gm = GameManager()

    def container(self, zone_id: str, name: str):
        for room in self.gm.world.locations[zone_id].rooms.values():
            for c in room.containers:
                if c.name == name:
                    return c
        raise AssertionError(name)

    def test_the_hallway_first_aid_cabinet_holds_the_kit(self):
        cabinet = self.container("zone_building", "first-aid cabinet")
        self.assertEqual(
            sorted(ids_in(cabinet)),
            sorted(
                [
                    "item_bandage",
                    "item_bandage",
                    "item_adhesive_bandage",
                    "item_alcohol_wipes",
                    "item_painkillers",
                ]
            ),
        )
        self.assertTrue(cabinet.fixed)
        self.assertFalse(cabinet.opened)

    def test_the_basement_storage_shelves_hold_the_materials(self):
        shelves = self.container("zone_building", "storage shelves")
        self.assertEqual(
            sorted(ids_in(shelves)),
            sorted(["item_hammer", "item_nails", "item_plank", "item_plank", "item_hand_axe"]),
        )
        self.assertTrue(shelves.fixed)

    def test_the_kitchen_counter_holds_the_food_knife_and_pan(self):
        counter = self.container("zone_home", "kitchen counter")
        self.assertEqual(
            sorted(ids_in(counter)),
            sorted(
                ["item_canned_beans", "item_water_bottle", "item_kitchen_knife", "item_frying_pan"]
            ),
        )
        self.assertTrue(counter.fixed)

    def test_the_wardrobe_holds_the_jacket_and_the_schoolbag(self):
        wardrobe = self.container("zone_home", "wardrobe")
        self.assertEqual(sorted(ids_in(wardrobe)), ["item_black_jacket", "item_schoolbag"])
        self.assertTrue(wardrobe.fixed)

    def test_no_ground_item_is_left_in_the_apartment_the_building_or_the_store(self):
        for zone_id in ("zone_home", "zone_building", "zone_bodega"):
            self.assertEqual(ground_ids(self.gm, zone_id), [], zone_id)

    def test_the_street_and_the_park_ground_items_stay(self):
        self.assertEqual(
            sorted(ground_ids(self.gm, "zone_street")),
            ["item_crowbar", "item_plank", "item_plank"],
        )
        self.assertEqual(ground_ids(self.gm, "zone_neighborhood"), ["item_baseball_bat"])

    def test_the_store_rolls_the_shop_tables_and_holds_no_fixed_stock(self):
        store = self.gm.world.locations["zone_bodega"]
        for room in store.rooms.values():
            for c in room.containers:
                self.assertFalse(c.fixed, c.name)
                self.assertEqual(c.contents, [], c.name)

    def test_a_new_game_does_not_share_containers_with_the_last_one(self):
        self.container("zone_home", "wardrobe").contents.clear()
        again = GameManager()
        wardrobe = [
            c
            for room in again.world.locations["zone_home"].rooms.values()
            for c in room.containers
            if c.name == "wardrobe"
        ][0]
        self.assertEqual(len(wardrobe.contents), 2)

    def test_the_catalogue_has_every_fixed_item(self):
        for zone in self.gm.world.locations.values():
            for room in zone.rooms.values():
                for c in room.containers:
                    for entity in c.contents:
                        self.assertIs(ITEMS[entity.item.id], entity.item)


class ResolveTests(unittest.TestCase):
    """Spec 25, Names: names resolve inside the current zone; a bare kind word needs exactly one in the room."""

    def setUp(self):
        self.gm = GameManager()
        self.home = self.gm.world.locations["zone_home"]

    def test_a_room_resolves_by_name_or_alias(self):
        self.assertEqual(room_id(self.home, "the kitchen"), "kitchen")
        self.assertEqual(room_id(self.home, "Lounge"), "living_room")
        self.assertIsNone(resolve_room(self.home, "room"))
        self.assertIsNone(resolve_room(self.home, "garage"))

    def test_a_container_resolves_by_its_full_name_from_any_room(self):
        found = resolve_container(self.home, "living_room", "bathroom counter")
        self.assertEqual(container_id(found), "bathroom_counter")

    def test_a_bare_kind_word_resolves_when_the_room_has_one(self):
        found = resolve_container(self.home, "kitchen", "counter")
        self.assertEqual(container_id(found), "kitchen_counter")
        found = resolve_container(self.home, "bathroom", "the counter")
        self.assertEqual(container_id(found), "bathroom_counter")

    def test_a_bare_word_the_room_does_not_have_is_not_a_container(self):
        self.assertIsNone(resolve_container(self.home, "bedroom", "counter"))

    def test_generic_words_are_never_aliases(self):
        for word in ("box", "thing", "room", "container"):
            self.assertIsNone(resolve_container(self.home, "kitchen", word), word)

    def test_an_ambiguous_bare_word_lists_the_choices(self):
        store = self.gm.world.locations["zone_bodega"]
        found = resolve_container(store, "shop_floor", "shelves")
        assert isinstance(found, list)
        self.assertEqual([c.name for c in found], ["snack shelves", "drinks shelves"])


class MoveBetweenRoomsTests(unittest.TestCase):
    """Spec 25, Verbs: MOVE_TO a room."""

    def setUp(self):
        self.gm = GameManager()
        self.name = self.gm.player.appearance.forename

    def test_a_move_between_rooms_costs_one_minute_and_sets_the_room_and_place(self):
        before = self.gm.narrative.minutes
        facts = simulate(self.gm, MoveAction(destination="the bedroom"))
        self.assertEqual(self.gm.narrative.minutes - before, 1)
        self.assertEqual(self.gm.player.current_room, "bedroom")
        self.assertEqual(self.gm.player.current_place, "bedroom")
        self.assertEqual(self.gm.player.current_location_id, "zone_home")
        self.assertTrue(any("bedroom" in f for f in facts), facts)

    def test_the_bedroom_still_finds_the_bed_by_its_place_words(self):
        simulate(self.gm, MoveAction(destination="bedroom"))
        home = self.gm.world.locations["zone_home"]
        self.assertEqual(home.bed_type_at(self.gm.player.current_place), "average_bed")

    def test_moving_to_the_room_the_player_is_in_is_refused_without_time(self):
        before = self.gm.narrative.minutes
        facts = simulate(self.gm, MoveAction(destination="living room"))
        self.assertEqual(self.gm.narrative.minutes, before)
        self.assertEqual(self.gm.player.current_room, "living_room")
        self.assertTrue(any("already in the living room" in f for f in facts), facts)

    def test_a_name_that_is_no_room_falls_to_the_zone_and_spot_rules(self):
        simulate(self.gm, MoveAction(destination="the window"))
        self.assertEqual(self.gm.player.current_place, "the window")
        self.assertEqual(self.gm.player.current_room, "living_room")

    def test_a_room_name_wins_over_a_zone_alias_in_the_current_zone(self):
        self.gm.player.current_location_id = "zone_building"
        self.gm.player.current_room = "hallway"
        simulate(self.gm, MoveAction(destination="basement"))
        self.assertEqual(self.gm.player.current_location_id, "zone_building")
        self.assertEqual(self.gm.player.current_room, "basement")

    def test_leaving_a_zone_enters_the_next_zones_entry_room(self):
        simulate(self.gm, MoveAction(destination="out"), rng=random.Random(1))
        self.assertEqual(self.gm.player.current_location_id, "zone_building")
        self.assertEqual(self.gm.player.current_room, "hallway")
        simulate(self.gm, MoveAction(destination="out"), rng=random.Random(1))
        self.assertEqual(self.gm.player.current_location_id, "zone_street")
        self.assertIsNone(self.gm.player.current_room)
