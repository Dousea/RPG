"""Spec 11, Weapons and spec 12, Items: the catalogue's stats."""

import unittest

from data.items import ITEMS
from data.locations import build_starting_locations
from data.melee import BARE_HANDS
from modules.entity.item import ItemEntity
from modules.item import MedicalItem, MeleeWeaponItem, StackItem


def weapon(item_id: str) -> MeleeWeaponItem:
    item = ITEMS[item_id]
    assert isinstance(item, MeleeWeaponItem)
    return item


def ground_ids(zone_id: str) -> list[str]:
    zone = build_starting_locations()[zone_id]
    return [e.item.id for e in zone.entities if isinstance(e, ItemEntity)]


class WeaponCatalogueTests(unittest.TestCase):
    """Spec 11, Weapons: the catalogue and its per-weapon fields."""

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

    def test_the_baseball_bat(self):
        bat = weapon("item_baseball_bat")
        self.assertEqual(bat.categories, ("blunt",))
        self.assertEqual((bat.min_damage, bat.max_damage), (0.8, 1.1))
        self.assertEqual(bat.max_range, 1.25)
        self.assertEqual((bat.critical_chance, bat.crit_dmg_multiplier), (40.0, 2.0))
        self.assertEqual(bat.max_hit_count, 2)
        self.assertTrue(bat.knockback_on_no_death)
        self.assertEqual((bat.condition_max, bat.condition_lower_chance), (15, 20))
        self.assertEqual(bat.weight, 2.0)
        self.assertEqual((bat.endurance_mod, bat.base_speed, bat.door_damage), (1.0, 1.0, 5))
        self.assertTrue(bat.is_two_handed)
        self.assertFalse(bat.is_stab)
        self.assertFalse(bat.no_maintenance_xp)
        self.assertEqual(bat.damage, 5)
        self.assertEqual(len(bat.slots), 2)
        self.assertIsNone(bat.sharpness)
        self.assertIsNone(bat.head_condition)
        self.assertIn("repairable_with_glue", bat.tags)
        self.assertIn("repairable_with_tape", bat.tags)

    def test_the_baseball_bat_starts_in_the_neighborhood(self):
        self.assertIn("item_baseball_bat", ground_ids("zone_neighborhood"))

    def test_the_frying_pan(self):
        pan = weapon("item_frying_pan")
        self.assertEqual(pan.categories, ("smallblunt",))
        self.assertEqual((pan.min_damage, pan.max_damage), (0.3, 0.5))
        self.assertEqual(pan.max_range, 1.1)
        self.assertEqual((pan.critical_chance, pan.crit_dmg_multiplier), (30.0, 2.0))
        self.assertEqual(pan.max_hit_count, 1)
        self.assertTrue(pan.knockback_on_no_death)
        self.assertEqual((pan.condition_max, pan.condition_lower_chance), (10, 12))
        self.assertEqual(pan.weight, 1.5)
        self.assertEqual((pan.endurance_mod, pan.base_speed, pan.door_damage), (1.3, 1.0, 3))
        self.assertFalse(pan.is_two_handed)
        self.assertFalse(pan.is_stab)
        self.assertTrue(pan.no_maintenance_xp)
        self.assertEqual(pan.damage, 2)
        self.assertEqual(len(pan.slots), 1)
        self.assertIsNone(pan.sharpness)
        self.assertIsNone(pan.head_condition)

    def test_the_frying_pan_starts_in_the_apartment(self):
        self.assertIn("item_frying_pan", ground_ids("zone_home"))

    def test_the_hand_axe(self):
        axe = weapon("item_hand_axe")
        self.assertEqual(axe.categories, ("axe",))
        self.assertEqual((axe.min_damage, axe.max_damage), (0.7, 1.5))
        self.assertEqual(axe.max_range, 1.1)
        self.assertEqual((axe.critical_chance, axe.crit_dmg_multiplier), (15.0, 5.0))
        self.assertEqual(axe.max_hit_count, 2)
        self.assertFalse(axe.knockback_on_no_death)
        self.assertEqual((axe.condition_max, axe.condition_lower_chance), (10, 15))
        self.assertEqual(axe.weight, 1.5)
        self.assertEqual((axe.endurance_mod, axe.base_speed, axe.door_damage), (1.0, 1.0, 20))
        self.assertFalse(axe.is_two_handed)
        self.assertFalse(axe.is_stab)
        self.assertFalse(axe.no_maintenance_xp)
        self.assertEqual(axe.damage, 6)
        self.assertEqual(len(axe.slots), 1)
        self.assertEqual(axe.sharpness, 1.0)
        self.assertEqual((axe.head_condition, axe.head_condition_max), (10, 10))
        self.assertEqual(axe.head_condition_lower_chance_multiplier, 1.5)
        for tag in ("sharpenable", "repairable_with_tape", "repairable_with_glue"):
            self.assertIn(tag, axe.tags)

    def test_the_hand_axe_is_in_the_basement_storage(self):
        self.assertIn("item_hand_axe", ground_ids("zone_building"))

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
        kit = [name for name in names if name not in {"Hammer", "Nails", "Plank", "Hand Axe"}]
        self.assertEqual(
            kit,
            ["Adhesive Bandage", "Alcohol Wipes", "Bandage", "Bandage", "Painkillers"],
        )


class BarrierItemTests(unittest.TestCase):
    """Spec 13, Items."""

    def test_the_hammer_has_its_catalogue_stats(self):
        hammer = ITEMS["item_hammer"]
        self.assertIsInstance(hammer, MeleeWeaponItem)
        assert isinstance(hammer, MeleeWeaponItem)
        self.assertEqual(hammer.categories, ("smallblunt",))
        self.assertEqual(hammer.door_damage, 9)
        self.assertEqual(hammer.condition_max, 10)
        self.assertEqual(hammer.condition_lower_chance, 30)
        self.assertFalse(hammer.is_two_handed)
        self.assertEqual((hammer.min_damage, hammer.max_damage), (0.5, 1.0))
        self.assertEqual((hammer.critical_chance, hammer.crit_dmg_multiplier), (20.0, 3.0))
        self.assertEqual((hammer.max_range, hammer.max_hit_count, hammer.weight), (1.1, 1, 1.5))
        self.assertIn("hammer", hammer.tags)
        self.assertIn("removes_barricade", hammer.tags)

    def test_the_plank_is_a_two_handed_club_with_door_damage_5(self):
        plank = ITEMS["item_plank"]
        assert isinstance(plank, MeleeWeaponItem)
        self.assertTrue(plank.is_two_handed)
        self.assertEqual(plank.categories, ("blunt",))
        self.assertEqual(
            (plank.door_damage, plank.condition_max, plank.condition_lower_chance), (5, 10, 2)
        )
        self.assertEqual((plank.min_damage, plank.max_damage), (0.4, 0.6))
        self.assertEqual((plank.max_range, plank.max_hit_count, plank.weight), (1.3, 2, 3.0))
        self.assertEqual((plank.critical_chance, plank.crit_dmg_multiplier), (30.0, 2.0))

    def test_nails_come_five_to_a_stack(self):
        nails = ITEMS["item_nails"]
        self.assertIsInstance(nails, StackItem)
        self.assertEqual(ItemEntity(item=nails).uses, 5)

    def test_the_crowbar_pries_planks_off(self):
        self.assertIn("removes_barricade", ITEMS["item_crowbar"].tags)

    def test_a_new_hammer_and_plank_are_at_full_condition(self):
        self.assertEqual(ItemEntity(item=ITEMS["item_hammer"]).condition, 10)
        self.assertEqual(ItemEntity(item=ITEMS["item_plank"]).condition, 10)

    def test_the_basement_storage_and_the_alley_hold_the_materials(self):
        zones = build_starting_locations()

        def names(zone_id: str) -> list[str]:
            return sorted(e.item.name for e in zones[zone_id].entities if isinstance(e, ItemEntity))

        building = names("zone_building")
        self.assertEqual(
            [n for n in building if n in {"Hammer", "Nails", "Plank"}],
            ["Hammer", "Nails", "Plank", "Plank"],
        )
        street = names("zone_street")
        self.assertEqual(street.count("Plank"), 2)
        self.assertIn("Crowbar", street)
