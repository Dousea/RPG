"""Spec 25, Places and items: The new zones."""

import unittest

from data.world.barriers import build_starting_barriers
from data.world.locations import ZONE_EXIT_NOUNS, build_starting_locations
from managers.game import GameManager
from managers.world.locations import resolve_location
from modules.action.types import MoveAction
from modules.entity.barrier import BarrierEntity, BarrierKind

# zone id, name, parent, exit key, size_tiles, chunks, intensity
ZONES = (
    ("zone_flat_vacant", "The Vacant Flat", "zone_building", "vacant flat", 8, 1, 0),
    ("zone_flat_tenant", "The Tenant's Flat", "zone_building", "tenant flat", 8, 1, 64),
    ("zone_pharmacy", "The Pharmacy", "zone_neighborhood", "pharmacy", 14, 2, 63),
    ("zone_clinic", "The Clinic", "zone_neighborhood", "clinic", 20, 3, 48),
    ("zone_supermarket", "The Supermarket", "zone_neighborhood", "supermarket", 30, 6, 63),
    ("zone_hardware", "The Hardware Store", "zone_neighborhood", "hardware store", 20, 3, 63),
)
# barrier id, zone, kind, health, locked, key
BARRIERS = (
    ("door_flat_vacant", "zone_flat_vacant", BarrierKind.DOOR, 500, False),
    ("door_flat_tenant", "zone_flat_tenant", BarrierKind.DOOR, 500, True),
    ("window_pharmacy", "zone_pharmacy", BarrierKind.WINDOW, 50, True),
    ("door_clinic", "zone_clinic", BarrierKind.DOOR, 500, False),
    ("window_supermarket", "zone_supermarket", BarrierKind.WINDOW, 100, True),
    ("door_hardware", "zone_hardware", BarrierKind.DOOR, 500, True),
)


class ZoneFieldTests(unittest.TestCase):
    """Spec 25, The new zones: the table."""

    def setUp(self):
        self.locations = build_starting_locations()

    def test_each_zone_has_its_name_size_chunks_and_intensity(self):
        for zone_id, name, _parent, _key, size, chunks, intensity in ZONES:
            with self.subTest(zone_id):
                zone = self.locations[zone_id]
                self.assertEqual(zone.name, name)
                self.assertEqual(
                    (zone.size_tiles, zone.chunks, zone.zombie_intensity), (size, chunks, intensity)
                )
                self.assertTrue(zone.indoors)

    def test_the_parent_gains_the_exit_key_and_the_zone_goes_back_out(self):
        for zone_id, _name, parent, key, *_ in ZONES:
            with self.subTest(zone_id):
                self.assertEqual(self.locations[parent].connections[key], zone_id)
                self.assertEqual(self.locations[zone_id].connections, {"out": parent})

    def test_the_flats_are_on_floor_one_and_the_shops_on_floor_zero(self):
        self.assertEqual(self.locations["zone_flat_vacant"].floor, 1)
        self.assertEqual(self.locations["zone_flat_tenant"].floor, 1)
        for zone_id in ("zone_pharmacy", "zone_clinic", "zone_supermarket", "zone_hardware"):
            self.assertEqual(self.locations[zone_id].floor, 0)

    def test_each_zone_is_its_own_building(self):
        buildings = [self.locations[z[0]].building for z in ZONES]
        self.assertTrue(all(buildings))
        self.assertEqual(len(set(buildings)), 6)
        for other in ("apartment_block", "corner_store"):
            self.assertNotIn(other, buildings)

    def test_the_tenants_flat_sleeps_on_the_floor_with_a_bed_in_the_bedroom(self):
        flat = self.locations["zone_flat_tenant"]
        self.assertEqual(flat.bed_type, "floor")
        self.assertEqual(flat.bed_type_at("the bedroom"), "average_bed")
        self.assertEqual(flat.bed_type_at("the bed"), "average_bed")
        self.assertEqual(self.locations["zone_flat_vacant"].place_bed_types, {})

    def test_emmas_apartment_stays_an_alias_of_the_building(self):
        self.assertIn("emma's apartment", self.locations["zone_building"].aliases)


class BarrierTests(unittest.TestCase):
    """Spec 25, The new zones: one barrier per zone, joining it to its parent."""

    def setUp(self):
        self.barriers = build_starting_barriers()

    def test_each_zone_has_exactly_one_barrier_with_the_listed_state(self):
        for barrier_id, zone_id, kind, health, locked in BARRIERS:
            with self.subTest(barrier_id):
                barrier = self.barriers[barrier_id]
                self.assertEqual(barrier.kind, kind)
                self.assertEqual((barrier.health, barrier.max_health), (health, health))
                self.assertEqual(barrier.locked, locked)
                self.assertFalse(barrier.open)
                self.assertFalse(barrier.broken)
                self.assertEqual(barrier.inside_zone, zone_id)
                self.assertIsNone(barrier.key_id)
                touching = [b for b in self.barriers.values() if zone_id in b.zones]
                self.assertEqual(touching, [barrier])

    def test_a_barrier_joins_its_zone_to_the_parent(self):
        parents = {z[0]: z[2] for z in ZONES}
        for _barrier_id, zone_id, *_ in BARRIERS:
            barrier = next(b for b in self.barriers.values() if b.inside_zone == zone_id)
            self.assertEqual(set(barrier.zones), {zone_id, parents[zone_id]})

    def test_the_shipped_windows_are_the_shop_the_pharmacy_and_the_supermarket(self):
        windows = {b.barrier_id for b in self.barriers.values() if b.kind == BarrierKind.WINDOW}
        self.assertEqual(windows, {"window_bodega", "window_pharmacy", "window_supermarket"})

    def test_every_barrier_has_a_name_and_a_distinct_id(self):
        names = [b.name for b in self.barriers.values()]
        self.assertEqual(len(set(names)), len(names))
        for barrier in self.barriers.values():
            assert isinstance(barrier, BarrierEntity)
            self.assertTrue(barrier.name)


class AliasTests(unittest.TestCase):
    """Spec 25, The new zones: the pharmacy, supermarket and clinic aliases moved."""

    def setUp(self):
        self.gm = GameManager()
        self.locations = self.gm.world.locations

    def resolve(self, phrase, standing_in):
        found = resolve_location(phrase, self.locations[standing_in], self.locations)
        return found.id if found else None

    def test_the_old_neighborhood_aliases_moved_to_the_new_zones(self):
        neighborhood = self.locations["zone_neighborhood"].aliases
        for word in ("pharmacy", "drugstore", "supermarket", "grocery store", "clinic"):
            self.assertNotIn(word, neighborhood)
        for word in ("hospital", "coffee shop", "park", "shops"):
            self.assertIn(word, neighborhood)

    def test_each_phrase_resolves_to_its_zone_from_the_neighborhood(self):
        phrases = {
            "the pharmacy": "zone_pharmacy",
            "go to the drugstore": "zone_pharmacy",
            "the clinic": "zone_clinic",
            "the walk-in clinic": "zone_clinic",
            "the supermarket": "zone_supermarket",
            "the grocery store": "zone_supermarket",
            "the hardware store": "zone_hardware",
            "the tool store": "zone_hardware",
            "the coffee shop": "zone_neighborhood",
            "the hospital": "zone_neighborhood",
            "the park": "zone_neighborhood",
        }
        for phrase, zone_id in phrases.items():
            with self.subTest(phrase):
                self.assertEqual(self.resolve(phrase, "zone_neighborhood"), zone_id)

    def test_each_phrase_resolves_the_same_from_home(self):
        self.assertEqual(self.resolve("the pharmacy", "zone_home"), "zone_pharmacy")
        self.assertEqual(self.resolve("the supermarket", "zone_street"), "zone_supermarket")
        self.assertEqual(self.resolve("the hardware store", "zone_building"), "zone_hardware")

    def test_the_flats_resolve_from_the_building(self):
        self.assertEqual(self.resolve("vacant flat", "zone_building"), "zone_flat_vacant")
        self.assertEqual(self.resolve("the vacant flat", "zone_building"), "zone_flat_vacant")
        self.assertEqual(self.resolve("tenant flat", "zone_building"), "zone_flat_tenant")
        self.assertEqual(self.resolve("the tenant's flat", "zone_building"), "zone_flat_tenant")
        self.assertEqual(self.resolve("go to the tenant's flat", "zone_home"), "zone_flat_tenant")

    def test_the_old_zones_still_resolve_where_they_did(self):
        self.assertEqual(self.resolve("my flat", "zone_building"), "zone_home")
        self.assertEqual(self.resolve("the corner store", "zone_street"), "zone_bodega")
        self.assertEqual(self.resolve("the shop", "zone_neighborhood"), None)
        self.assertEqual(self.resolve("the store", "zone_neighborhood"), None)
        self.assertEqual(self.resolve("Emma's apartment", "zone_street"), "zone_building")

    def test_a_bare_generic_word_is_no_alias(self):
        generic = {
            "flat",
            "shop",
            "store",
            "door",
            "window",
            "room",
            "tenant",
            "vacant",
            "hardware",
        }
        for zone in self.locations.values():
            for alias in zone.aliases:
                self.assertNotIn(alias.casefold(), generic, zone.id)

    def test_no_two_zones_share_a_name_alias_or_exit_noun(self):
        owners: dict[str, str] = {}
        for zone in self.locations.values():
            texts = (
                zone.name.casefold().removeprefix("the "),
                *(a.casefold() for a in zone.aliases),
            )
            for text in texts:
                self.assertEqual(owners.setdefault(text, zone.id), zone.id, text)
        nouns: dict[str, str] = {}
        for zone_id, words in ZONE_EXIT_NOUNS.items():
            for word in words:
                self.assertNotIn(word, nouns, word)
                nouns[word] = zone_id

    def test_leaving_a_new_zone_goes_out_to_its_parent(self):
        for zone_id, _name, parent, key, *_ in ZONES:
            noun = key if zone_id != "zone_flat_tenant" else "tenant's flat"
            with self.subTest(zone_id):
                self.assertEqual(self.resolve(f"leave the {noun}", zone_id), parent)
                self.assertEqual(self.resolve("out", zone_id), parent)

    def test_naming_another_new_zone_in_an_exit_phrase_does_not_walk_out(self):
        self.assertIsNone(self.resolve("leave the pharmacy", "zone_clinic"))


def layout(zone):
    return {rid: [c.name for c in room.containers] for rid, room in zone.rooms.items()}


APARTMENT_ROOMS = {
    "kitchen": ["kitchen counter", "kitchen cupboards", "fridge", "freezer"],
    "bedroom": ["wardrobe", "dresser", "bedside table"],
    "bathroom": ["medicine cabinet", "bathroom counter"],
    "living_room": ["side table", "living room shelves"],
}
ROOMS = {
    "zone_flat_vacant": {
        "kitchen": ["kitchen counter", "kitchen cupboards"],
        "bedroom": ["wardrobe"],
        "bathroom": ["medicine cabinet"],
        "living_room": [],
    },
    "zone_flat_tenant": APARTMENT_ROOMS,
    "zone_pharmacy": {
        "shop_floor": ["pharmacy counter", "left shelves", "right shelves", "shop fridge"],
        "back_room": ["dispensing counter", "medicine fridge", "supply crates"],
    },
    "zone_clinic": {
        "exam_room": ["exam counter", "exam desk", "side table"],
        "office": ["office desk", "office counter"],
        "supply_room": [
            "supply counter",
            "supply shelves",
            "supply fridge",
            "supply crates",
            "supply desk",
        ],
    },
    "zone_supermarket": {
        "aisles": [
            "checkout counter",
            "first aisle shelves",
            "second aisle shelves",
            "third aisle shelves",
            "fourth aisle shelves",
            "drinks fridge",
        ],
        "stockroom": ["stockroom fridge", "first stock crates", "second stock crates"],
    },
    "zone_hardware": {
        "shop_floor": [
            "tool counter",
            "first shelves",
            "second shelves",
            "third shelves",
            "shop crates",
        ],
        "storeroom": ["first storeroom crates", "second storeroom crates"],
    },
}
ENTRY = {
    "zone_flat_vacant": "living_room",
    "zone_flat_tenant": "living_room",
    "zone_pharmacy": "shop_floor",
    "zone_clinic": "exam_room",
    "zone_supermarket": "aisles",
    "zone_hardware": "shop_floor",
}


class RoomLayoutTests(unittest.TestCase):
    """Spec 25, The rooms: the layout of each new zone and its entry room."""

    def setUp(self):
        self.locations = build_starting_locations()

    def test_each_zone_has_its_rooms_and_containers_in_layout_order(self):
        for zone_id, rooms in ROOMS.items():
            with self.subTest(zone_id):
                self.assertEqual(layout(self.locations[zone_id]), rooms)

    def test_each_zone_has_its_entry_room(self):
        for zone_id, room_id in ENTRY.items():
            with self.subTest(zone_id):
                self.assertEqual(self.locations[zone_id].entry_room, room_id)
                self.assertIn(room_id, self.locations[zone_id].rooms)

    def test_a_container_name_is_unique_in_its_zone_and_an_id_unique_in_the_world(self):
        ids = []
        for zone in self.locations.values():
            names = [c.name for room in zone.rooms.values() for c in room.containers]
            self.assertEqual(len(names), len(set(names)), zone.id)
            ids += [c.container_id for room in zone.rooms.values() for c in room.containers]
        self.assertEqual(len(ids), len(set(ids)))

    def test_the_tenants_flat_is_stocked_from_tables_and_the_freezer_holds_15_kg(self):
        flat = self.locations["zone_flat_tenant"]
        for room in flat.rooms.values():
            for container in room.containers:
                self.assertFalse(container.fixed, container.name)
                self.assertIsNotNone(container.source, container.name)
        self.assertEqual(flat.rooms["kitchen"].containers[3].capacity, 15)
        self.assertEqual(flat.rooms["kitchen"].containers[0].source, ("kitchen", "counter"))

    def test_a_player_who_enters_a_zone_is_in_its_entry_room(self):
        from tests.support import simulate

        for zone_id, room_id in ENTRY.items():
            with self.subTest(zone_id):
                gm = GameManager()
                gm.player.current_location_id = self.locations[zone_id].connections["out"]
                for barrier in gm.world.barriers.values():
                    barrier.open = True
                simulate(gm, MoveAction(destination=zone_id))
                self.assertEqual(gm.player.current_location_id, zone_id)
                self.assertEqual(gm.player.current_room, room_id)


if __name__ == "__main__":
    unittest.main()
