"""carrying-and-loot: Instance ids: every item has its own, numbered from a counter in the world."""

import json
import unittest

from adapters.save import codec, files
from data.items import ITEMS
from managers.game import GameManager
from managers.world import item_ids
from modules.body.parts import BodyLocation
from modules.entity.item import ItemEntity
from tests.support import IsolatedSaveTestCase
from tests.test_simulation import add_zombie, zombie_game


def ids_of(gm: GameManager) -> list[tuple[str, str]]:
    return [
        (e.item.id, e.instance_id)
        for e in item_ids.every_item(gm.world, gm.player, gm.npcs.values())
    ]


class StampTests(unittest.TestCase):
    def test_every_item_of_a_new_game_has_a_unique_id(self):
        gm = GameManager()
        found = [instance for _, instance in ids_of(gm)]
        self.assertTrue(found)
        self.assertNotIn("", found)
        self.assertEqual(len(found), len(set(found)))
        self.assertEqual(gm.world.next_item_number, len(found) + 1)

    def test_a_new_game_numbers_its_items_the_same_way_each_time(self):
        self.assertEqual(ids_of(GameManager()), ids_of(GameManager()))

    def test_a_bags_contents_and_a_zombies_clothes_are_stamped(self):
        gm = GameManager()
        bag = ItemEntity(item=ITEMS["item_schoolbag"])
        bag.contents.append(ItemEntity(item=ITEMS["item_canned_beans"]))
        gm.player.inventory.append(bag)
        item_ids.stamp_world(gm.world, gm.player, gm.npcs.values())
        self.assertNotEqual(bag.instance_id, "")
        self.assertNotEqual(bag.contents[0].instance_id, "")

    def test_a_stamped_item_keeps_its_id_and_a_new_one_takes_the_next_number(self):
        gm = GameManager()
        first = gm.player.inventory[0]
        before = first.instance_id
        extra = ItemEntity(item=ITEMS["item_canned_beans"])
        gm.player.inventory.append(extra)
        item_ids.stamp_world(gm.world, gm.player, gm.npcs.values())
        self.assertEqual(first.instance_id, before)
        self.assertEqual(extra.instance_id, f"i{gm.world.next_item_number - 1}")

    def test_a_zombies_clothes_are_stamped(self):
        gm = zombie_game()
        zombie = add_zombie(gm, gap=3)
        shirt = ItemEntity(item=ITEMS["item_tshirt"])
        zombie.worn = {BodyLocation.TSHIRT: shirt}
        item_ids.stamp_world(gm.world, gm.player, gm.npcs.values())
        self.assertNotEqual(shirt.instance_id, "")


class SaveTests(IsolatedSaveTestCase):
    def test_ids_and_the_counter_survive_a_save_and_load(self):
        gm = GameManager()
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_canned_beans"]))
        files.save(gm, self.save_path)
        loaded = files.load(self.save_path)
        assert loaded is not None
        self.assertEqual(ids_of(loaded), ids_of(gm))
        self.assertEqual(loaded.world.next_item_number, gm.world.next_item_number)

    def test_a_save_made_before_ids_is_discarded(self):
        files.save(GameManager(), self.save_path)
        with open(self.save_path, encoding="utf-8") as handle:
            data = json.load(handle)
        data["version"] = codec.SCHEMA_VERSION - 1
        with open(self.save_path, "w", encoding="utf-8") as handle:
            json.dump(data, handle)
        self.assertIsNone(files.load(self.save_path))
