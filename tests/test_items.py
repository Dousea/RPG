"""Spec 11, Weapons and spec 12, Items: the catalogue's stats."""

import unittest

from data.items import ITEMS
from data.locations import build_starting_locations
from data.melee import BARE_HANDS
from modules.entity.item import ItemEntity
from modules.item import MedicalItem, MeleeWeaponItem


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


def medical(item_id: str) -> MedicalItem:
    item = ITEMS[item_id]
    assert isinstance(item, MedicalItem)
    return item


class MedicalCatalogueTests(unittest.TestCase):
    """Spec 12, Items."""

    def test_there_are_eleven_medical_items(self):
        self.assertEqual(sum(isinstance(item, MedicalItem) for item in ITEMS.values()), 11)

    def test_bandages(self):
        for item_id, power, alcoholic, dirty_version in (
            ("item_bandage", 4, False, "item_dirty_bandage"),
            ("item_sterilized_bandage", 4, True, "item_dirty_bandage"),
            ("item_adhesive_bandage", 1.5, False, None),
            ("item_ripped_sheets", 2, False, "item_dirty_ripped_sheets"),
            ("item_sterilized_ripped_sheets", 2, True, "item_dirty_ripped_sheets"),
        ):
            item = medical(item_id)
            self.assertEqual(item.bandage_power, power, item_id)
            self.assertEqual(item.alcoholic, alcoholic, item_id)
            self.assertEqual(item.dirty_version, dirty_version, item_id)
            self.assertFalse(item.dirty)
            self.assertFalse(item.reusable_bandage)

    def test_the_dirty_bandages_are_reusable(self):
        for item_id in ("item_dirty_bandage", "item_dirty_ripped_sheets"):
            item = medical(item_id)
            self.assertEqual(item.bandage_power, 0.5)
            self.assertTrue(item.dirty)
            self.assertTrue(item.reusable_bandage)
            self.assertIsNone(item.dirty_version)

    def test_alcohol_items(self):
        wipes = medical("item_alcohol_wipes")
        self.assertEqual((wipes.alcohol_power, wipes.uses), (4, 5))
        disinfectant = medical("item_disinfectant")
        self.assertEqual((disinfectant.alcohol_power, disinfectant.uses), (4, 3))

    def test_pills(self):
        painkillers = medical("item_painkillers")
        self.assertTrue(painkillers.painkiller)
        self.assertEqual(painkillers.uses, 10)
        antibiotics = medical("item_antibiotics")
        self.assertEqual(antibiotics.reduce_infection_power, 50)
        self.assertEqual(antibiotics.uses, 1)
        self.assertFalse(antibiotics.painkiller)

    def test_a_new_entity_starts_with_every_use_left(self):
        self.assertEqual(ItemEntity(item=medical("item_painkillers")).uses, 10)
        self.assertEqual(ItemEntity(item=medical("item_alcohol_wipes")).uses, 5)

    def test_the_first_aid_kit_and_its_direct_healing_are_gone(self):
        self.assertNotIn("item_first_aid_kit", ITEMS)

    def test_zone_building_holds_the_kits_fixed_contents(self):
        building = build_starting_locations()["zone_building"]
        names = sorted(
            entity.item.name for entity in building.entities if isinstance(entity, ItemEntity)
        )
        self.assertEqual(
            names,
            ["Adhesive Bandage", "Alcohol Wipes", "Bandage", "Bandage", "Painkillers"],
        )
