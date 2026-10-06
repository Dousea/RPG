"""Spec 11, Weapons: the catalogue's stats."""

import unittest

from data.items import ITEMS
from data.melee import BARE_HANDS
from modules.entity.item import ItemEntity
from modules.item import MeleeWeaponItem


def weapon(item_id: str) -> MeleeWeaponItem:
    item = ITEMS[item_id]
    assert isinstance(item, MeleeWeaponItem)
    return item


class WeaponCatalogueTests(unittest.TestCase):
    """Spec 11, Weapons: the crowbar, the kitchen knife and bare hands."""

    def test_the_crowbar(self):
        crowbar = weapon("item_crowbar")
        self.assertEqual(crowbar.categories, ("blunt",))
        self.assertEqual((crowbar.min_damage, crowbar.max_damage), (0.6, 1.15))
        self.assertEqual(crowbar.max_range, 1.25)
        self.assertEqual((crowbar.critical_chance, crowbar.crit_dmg_multiplier), (20.0, 2.5))
        self.assertEqual(crowbar.max_hit_count, 3)
        self.assertTrue(crowbar.knockback_on_no_death)
        self.assertEqual((crowbar.condition_max, crowbar.condition_lower_chance), (15, 70))
        self.assertEqual(crowbar.weight, 2.0)
        self.assertEqual(crowbar.door_damage, 8)
        self.assertTrue(crowbar.is_two_handed)
        self.assertFalse(crowbar.is_stab)
        self.assertEqual(crowbar.damage, 5)

    def test_the_kitchen_knife(self):
        knife = weapon("item_kitchen_knife")
        self.assertEqual(knife.categories, ("smallblade",))
        self.assertTrue(knife.is_stab)
        self.assertEqual((knife.min_damage, knife.max_damage), (0.3, 0.7))
        self.assertEqual(knife.max_range, 0.9)
        self.assertEqual((knife.critical_chance, knife.crit_dmg_multiplier), (25.0, 4.0))
        self.assertEqual(knife.max_hit_count, 1)
        self.assertEqual((knife.condition_max, knife.condition_lower_chance), (10, 2))
        self.assertEqual(knife.weight, 0.7)
        self.assertEqual(knife.damage, 3)
        self.assertFalse(knife.is_two_handed)

    def test_bare_hands(self):
        self.assertEqual((BARE_HANDS.min_damage, BARE_HANDS.max_damage), (0.2, 0.4))
        self.assertEqual(BARE_HANDS.max_range, 1.1)
        self.assertEqual(BARE_HANDS.max_hit_count, 3)
        self.assertEqual(BARE_HANDS.endurance_mod, 1.7)
        self.assertEqual(BARE_HANDS.weight, 1.0)
        self.assertEqual(BARE_HANDS.base_speed, 0.9)
        self.assertEqual(BARE_HANDS.door_damage, 0)
        self.assertEqual(BARE_HANDS.categories, ())
        self.assertTrue(BARE_HANDS.knockback_on_no_death)
        self.assertTrue(BARE_HANDS.no_maintenance_xp)

    def test_the_kitchen_knife_starts_in_the_apartment(self):
        from data.locations import build_starting_locations

        zone = build_starting_locations()["zone_home"]
        names = [e.item.id for e in zone.entities if isinstance(e, ItemEntity)]
        self.assertIn("item_kitchen_knife", names)


if __name__ == "__main__":
    unittest.main()
