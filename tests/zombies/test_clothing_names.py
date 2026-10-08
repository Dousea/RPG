"""zombie-lifecycle: Clothing display names: the variant leads, overrides read naturally."""

import subprocess
import unittest

from data.items import ITEMS
from data.zombies import clothing_names as zombie_clothing_names
from data.zombies.clothing import ZOMBIE_CLOTHING
from modules.action.types import SearchAction
from modules.entity.item import ItemEntity
from tests.corpses.test_loot import body
from tests.support import simulate
from tests.test_simulation import zombie_game


class RuleTests(unittest.TestCase):
    """zombie-lifecycle: Clothing display names: the rule."""

    def test_variant_goes_before_the_noun(self):
        self.assertEqual(
            zombie_clothing_names.display_name("x", "Baseball Cap - Courier"),
            "Courier Baseball Cap",
        )
        self.assertEqual(zombie_clothing_names.display_name("x", "Jeans - Baggy"), "Baggy Jeans")

    def test_a_name_without_a_variant_is_kept(self):
        self.assertEqual(zombie_clothing_names.display_name("x", "Gold Ring"), "Gold Ring")

    def test_the_brief_example_cases(self):
        self.assertEqual(
            zombie_clothing_names.display_name("x", "Baseball Cap - State"), "State Baseball Cap"
        )
        self.assertEqual(zombie_clothing_names.display_name("x", "Bandana - Tied"), "Tied Bandana")


class OverrideTests(unittest.TestCase):
    """zombie-lifecycle: Clothing display names: the overrides."""

    def test_each_override_applies(self):
        for item_id, expected in zombie_clothing_names.OVERRIDES.items():
            with self.subTest(item_id):
                self.assertEqual(ITEMS[item_id].name, expected)
                self.assertEqual(
                    zombie_clothing_names.display_name(item_id, ZOMBIE_CLOTHING[item_id].name),
                    expected,
                )

    def test_known_overrides(self):
        names = {i: ITEMS[i].name for i in zombie_clothing_names.OVERRIDES}
        self.assertEqual(names["item_shirt_crop_top_tint"], "Crop Top")
        self.assertEqual(names["item_jacket_leather_biker_gang_a"], "Leather Jacket")
        self.assertEqual(names["item_earring_loop_small_gold_top"], "Small Looped Gold Earrings")
        self.assertEqual(names["item_tshirt_polo_striped_tint"], "Striped Polo Shirt")
        self.assertEqual(names["item_tshirt_polo_tint"], "Polo Shirt")

    def test_overrides_name_real_dash_items(self):
        for item_id in zombie_clothing_names.OVERRIDES:
            self.assertIn(" - ", ZOMBIE_CLOTHING[item_id].name)


class CatalogueTests(unittest.TestCase):
    """zombie-lifecycle: Clothing display names: where they apply."""

    def test_no_clothing_name_the_game_builds_has_a_dash(self):
        for item_id, item in ZOMBIE_CLOTHING.items():
            with self.subTest(item_id):
                self.assertNotIn(" - ", ITEMS[item_id].name)
                self.assertNotIn(" - ", ITEMS[item_id].description)
                self.assertEqual(ITEMS[item_id].id, item.id)

    def test_the_item_id_and_stats_are_unchanged(self):
        item = zombie_clothing_names.DISPLAY_CLOTHING["item_hat_baseball_cap_state"]
        self.assertIs(ITEMS[item.id], item)
        self.assertEqual(item.name, "State Baseball Cap")
        raw = ZOMBIE_CLOTHING["item_hat_baseball_cap_state"]
        self.assertEqual(item.insulation, raw.insulation)
        self.assertEqual(item.body_location, raw.body_location)

    def test_a_search_fact_uses_the_display_name(self):
        gm = zombie_game()
        corpse = body()
        corpse.contents = [ItemEntity(item=ITEMS["item_hat_baseball_cap_state"])]
        gm.world.corpses["c1"] = corpse
        facts = simulate(gm, SearchAction(target_name="c1"))
        self.assertTrue(any("state baseball cap" in f.lower() for f in facts), facts)
        self.assertFalse(any(" - " in f for f in facts))

    def test_the_generated_file_is_untouched(self):
        diff = subprocess.run(
            ["git", "diff", "--stat", "--", "data/zombies/clothing.py"],
            capture_output=True,
            text=True,
            check=True,
        )
        self.assertEqual(diff.stdout, "")


if __name__ == "__main__":
    unittest.main()
