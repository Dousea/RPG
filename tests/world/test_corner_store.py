"""The corner store and its shop-front window (doors: The shipped barriers; zombies: Zones)."""

import json
import os
import random
import tempfile
import unittest

from adapters.save import files
from data.world.barriers import WINDOW_HEALTH_SINGLE
from managers.game import GameManager
from managers.simulation import SimulationCore
from modules.action.types import AttackAction, MoveAction, OpenAction, SearchAction
from modules.entity.barrier import BarrierKind
from modules.entity.item import ItemEntity
from tests.support import ScriptedRandom, simulate, turn_of

STREET = "zone_street"
STORE = "zone_bodega"
WINDOW = "window_bodega"


def run(gm: GameManager, *actions) -> tuple[list[str], int]:
    before = gm.narrative.minutes
    facts = turn_of(SimulationCore(gm, rng=random.Random(1)), actions).facts
    return list(facts), gm.narrative.minutes - before


def on_the_street() -> GameManager:
    gm = GameManager()
    gm.player.current_location_id = STREET
    return gm


class CornerStoreZoneTests(unittest.TestCase):
    """zombies: Zones: the corner store row."""

    def test_the_store_is_an_indoor_one_chunk_zone_reached_only_from_the_street(self):
        store = GameManager().world.locations[STORE]
        self.assertEqual(store.name, "The Corner Store")
        self.assertTrue(store.indoors)
        self.assertEqual((store.size_tiles, store.chunks, store.zombie_intensity), (10, 1, 63))
        self.assertEqual(store.connections, {"out": STREET})
        self.assertEqual(store.building, "corner_store")
        self.assertEqual(GameManager().world.locations[STREET].connections["store"], STORE)

    def test_the_store_has_no_ground_stock_and_its_shelves_roll_the_shop_tables(self):
        """carrying-and-loot: The starting kit: the stand-in stock is gone."""
        gm = GameManager()
        store = gm.world.locations[STORE]
        self.assertEqual([e for e in store.entities if isinstance(e, ItemEntity)], [])
        gm.player.current_location_id = STORE
        gm.player.current_room = "shop_floor"
        simulate(gm, SearchAction(target_name="snack shelves"), rng=ScriptedRandom())
        shelves = store.rooms["shop_floor"].containers[2]
        self.assertEqual(shelves.name, "snack shelves")
        self.assertEqual(
            {e.item.id for e in shelves.contents}, {"item_water_bottle", "item_soda_can"}
        )

    def test_bodega_resolves_to_the_store_and_the_street_no_longer_claims_it(self):
        gm = GameManager()
        for phrase in ("bodega", "corner store", "the bodega", "the corner store"):
            found = gm.resolve_location(phrase)
            self.assertEqual(found and found.id, STORE, phrase)
        self.assertNotIn("bodega", gm.world.locations[STREET].aliases)
        self.assertNotIn("corner store", gm.world.locations[STREET].aliases)

    def test_outside_the_store_leaves_it_for_the_street(self):
        gm = GameManager()
        gm.player.current_location_id = STORE
        for phrase in (
            "outside the bodega",
            "out of the shop",
            "outside the store",
            "leave the corner store",
        ):
            found = gm.resolve_location(phrase)
            self.assertEqual(found and found.id, STREET, phrase)

    def test_outside_the_store_from_the_street_names_no_zone(self):
        gm = on_the_street()
        self.assertIsNone(gm.resolve_location("outside the bodega"))

    def test_a_shop_named_anywhere_is_not_the_store(self):
        for zone in (STREET, "zone_neighborhood"):
            gm = GameManager()
            gm.player.current_location_id = zone
            for phrase in ("the shop window", "a pet shop", "the gun shop"):
                found = gm.resolve_location(phrase)
                self.assertNotEqual(found and found.id, STORE, (zone, phrase))

    def test_the_shop_by_itself_asks_which_shop(self):
        for zone in (STREET, "zone_neighborhood"):
            gm = GameManager()
            gm.player.current_location_id = zone
            found = gm.resolve_places("the shop")
            assert isinstance(found, list)
            self.assertIn(STORE, [each.id for each in found])


class ShopWindowTests(unittest.TestCase):
    """doors: The shipped barriers: the shop window."""

    def test_it_is_a_closed_locked_single_pane_window_between_street_and_store(self):
        barrier = GameManager().world.barriers[WINDOW]
        self.assertEqual(barrier.kind, BarrierKind.WINDOW)
        self.assertEqual(barrier.zones, (STREET, STORE))
        self.assertEqual(barrier.inside_zone, STORE)
        self.assertEqual((barrier.health, barrier.max_health), (WINDOW_HEALTH_SINGLE, 50))
        self.assertTrue(barrier.locked)
        self.assertFalse(barrier.open)
        self.assertIsNone(barrier.key_id)

    def test_open_from_the_street_is_refused(self):
        gm = on_the_street()
        gm.player.at_barrier = WINDOW
        facts, _ = run(gm, OpenAction(barrier_name="shop window"))
        self.assertFalse(gm.world.barriers[WINDOW].open)
        self.assertTrue(facts[0].startswith("Refused"), facts)

    def test_open_from_inside_opens_and_unlocks_it(self):
        gm = GameManager()
        gm.player.current_location_id = STORE
        gm.player.at_barrier = WINDOW
        run(gm, OpenAction(barrier_name="shop window"))
        barrier = gm.world.barriers[WINDOW]
        self.assertTrue(barrier.open)
        self.assertFalse(barrier.locked)

    def test_moving_to_the_store_from_the_street_stops_at_the_locked_window(self):
        gm = on_the_street()
        run(gm, MoveAction(destination="store"))
        self.assertEqual(gm.player.current_location_id, STREET)
        self.assertFalse(gm.world.barriers[WINDOW].open)

    def test_a_hit_from_the_street_smashes_it_and_the_climb_in_costs_a_minute_more(self):
        gm = on_the_street()
        gm.player.at_barrier = WINDOW
        facts, _ = run(gm, AttackAction(target_name="shop window"))
        self.assertTrue(gm.world.barriers[WINDOW].broken)
        self.assertTrue(any("Glass shatters" in fact for fact in facts), facts)
        _, minutes = run(gm, MoveAction(destination="store"))
        self.assertEqual(minutes, 2)
        self.assertEqual(gm.player.current_location_id, STORE)


class CornerStoreSaveTests(unittest.TestCase):
    """The save carries the new zone and barrier; older schemas are discarded."""

    def setUp(self):
        directory = tempfile.TemporaryDirectory()
        self.addCleanup(directory.cleanup)
        self.path = os.path.join(directory.name, "save.json")

    def test_the_smashed_window_and_the_store_round_trip(self):
        gm = on_the_street()
        gm.player.at_barrier = WINDOW
        run(gm, AttackAction(target_name="shop window"))
        files.save(gm, self.path)
        loaded = files.load(self.path)
        assert loaded is not None
        self.assertTrue(loaded.world.barriers[WINDOW].broken)
        self.assertEqual(loaded.world.locations[STORE].zombie_intensity, 63)
        self.assertEqual(loaded.world.locations[STORE].building, "corner_store")

    def test_a_v18_save_is_discarded(self):
        files.save(GameManager(), self.path)
        with open(self.path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["version"] = 18
        with open(self.path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        self.assertIsNone(files.load(self.path))


class BlockedMoveWordTests(unittest.TestCase):
    """doors: A blocked move names the barrier's kind."""

    def test_a_blocked_move_at_the_window_says_window(self):
        gm = on_the_street()
        facts, _ = run(gm, MoveAction(destination="The Corner Store"))
        self.assertIn("blocked -- the window to The Corner Store is locked", facts[0])

    def test_a_blocked_move_at_a_door_says_door(self):
        gm = GameManager()
        gm.player.inventory.clear()
        simulate(gm, MoveAction(destination="zone_street"))
        gm.world.barriers["door_apartment"].locked = True
        facts = simulate(gm, MoveAction(destination="Your Apartment"))
        self.assertIn("blocked -- the door to Your Apartment is locked", facts[0])
