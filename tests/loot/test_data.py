"""carrying-and-loot: Places and items: the new foods, drinks and weapons, and the item mapping."""

import random
import re
import unittest

from data.items import ITEMS
from data.loot.catalogue import LOOT_CATALOGUE
from data.loot.tables import BAG_TABLES, PROCEDURAL_TABLES, ROOM_TABLES
from data.world.locations import build_starting_locations
from managers.world.containers import container_weight, open_container
from modules.character.equipment import CharacterHoldableSlot
from modules.item import ConsumableItem, MeleeWeaponItem


def consumable(item_id: str) -> ConsumableItem:
    item = ITEMS[item_id]
    assert isinstance(item, ConsumableItem)
    return item


def weapon(item_id: str) -> MeleeWeaponItem:
    item = ITEMS[item_id]
    assert isinstance(item, MeleeWeaponItem)
    return item


class NewFoodTests(unittest.TestCase):
    """carrying-and-loot: New items: foods and drinks."""

    def check(self, item_id, hunger, thirst, unhappy, weight, stress=0.0):
        item = consumable(item_id)
        self.assertAlmostEqual(item.hunger_change, hunger)
        self.assertAlmostEqual(item.thirst_change, thirst)
        self.assertAlmostEqual(item.unhappy_change, unhappy)
        self.assertAlmostEqual(item.weight, weight)
        self.assertAlmostEqual(item.stress_change, stress)

    def test_canned_soup(self):
        self.check("item_canned_soup", -0.25, -0.04, 0, 0.8)

    def test_canned_tuna(self):
        self.check("item_canned_tuna", -0.18, 0, 0, 0.3)

    def test_canned_corn(self):
        self.check("item_canned_corn", -0.16, -0.04, 0, 0.8)

    def test_canned_peaches(self):
        self.check("item_canned_peaches", -0.15, 0, -10, 0.8)

    def test_canned_chili(self):
        self.check("item_canned_chili", -0.16, 0, 0, 0.8)

    def test_canned_sardines(self):
        self.check("item_canned_sardines", -0.14, 0, 0, 0.3)

    def test_crackers(self):
        self.check("item_crackers", -0.05, 0, 0, 0.1)

    def test_chocolate_bar(self):
        self.check("item_chocolate_bar", -0.20, 0, -10, 0.2)

    def test_crisps(self):
        self.check("item_crisps", -0.15, 0, -5, 0.2)

    def test_soda_can_full_weighs_point_six(self):
        self.check("item_soda_can", -0.036, -0.09, -3, 0.6)

    def test_juice_box_carries_the_fluids_stress(self):
        self.check("item_juice_box", -0.02, -0.06, -10, 0.3, stress=-0.04)

    def test_the_other_cans_get_one_row_each(self):
        rows = {
            "item_canned_bolognese": (-0.24, 0, 0),
            "item_canned_carrots": (-0.12, -0.04, 0),
            "item_canned_corned_beef": (-0.24, 0, 0),
            "item_canned_fruit_cocktail": (-0.15, 0, -10),
            "item_canned_fruit_beverage": (-0.15, -0.85, -10),
            "item_canned_condensed_milk": (-0.10, -0.10, 0),
            "item_canned_mushroom_soup": (-0.10, -0.04, 0),
            "item_canned_peas": (-0.16, -0.03, 0),
            "item_canned_pineapple": (-0.15, 0, -10),
            "item_canned_potatoes": (-0.18, -0.07, 0),
            "item_canned_tomatoes": (-0.12, -0.08, 0),
        }
        for item_id, (hunger, thirst, unhappy) in rows.items():
            with self.subTest(item_id):
                self.check(item_id, hunger, thirst, unhappy, 0.8)

    def test_every_catalogue_id_is_lowercase_snake_case(self):
        for item_id in ITEMS:
            self.assertRegex(item_id, r"^[a-z0-9_]+$")


class NewWeaponTests(unittest.TestCase):
    """carrying-and-loot: New items: weapons."""

    ROWS = {
        "item_rolling_pin": ("smallblunt", 1.5, 2, False),
        "item_meat_cleaver": ("axe", 1.0, 3, False),
        "item_screwdriver": ("smallblade", 0.5, 3, False),
        "item_wrench": ("smallblunt", 1.0, 4, False),
        "item_pipe_wrench": ("smallblunt", 1.5, 4, False),
        "item_tire_iron": ("smallblunt", 1.5, 4, False),
        "item_shovel": ("blunt", 2.0, 8, True),
        "item_sledgehammer": ("blunt", 6.0, 14, True),
    }

    def test_categories_weight_npc_damage_and_hands(self):
        for item_id, (category, weight_kg, damage, two_handed) in self.ROWS.items():
            with self.subTest(item_id):
                item = weapon(item_id)
                self.assertIn(category, item.categories)
                self.assertEqual(item.weight, weight_kg)
                self.assertEqual(item.damage, damage)
                self.assertEqual(item.is_two_handed, two_handed)

    def test_a_two_handed_weapon_fills_both_hands(self):
        slots = weapon("item_sledgehammer").slots
        self.assertEqual(
            set(slots), {CharacterHoldableSlot.RIGHT_HAND, CharacterHoldableSlot.LEFT_HAND}
        )

    def test_stats_come_from_the_script(self):
        sledge = weapon("item_sledgehammer")
        self.assertEqual((sledge.min_damage, sledge.max_damage), (2.0, 3.0))
        self.assertEqual(sledge.door_damage, 40)
        self.assertEqual(sledge.endurance_mod, 4.0)
        pin = weapon("item_rolling_pin")
        self.assertEqual((pin.condition_max, pin.condition_lower_chance), (8, 14))
        self.assertEqual(weapon("item_wrench").condition_max, 9)

    def test_a_tire_iron_pries_planks_off(self):
        self.assertIn("removes_barricade", weapon("item_tire_iron").tags)


class ItemMappingTests(unittest.TestCase):
    """carrying-and-loot: Item mapping."""

    def test_every_mapping_resolves_to_a_catalogue_id(self):
        for name, (item_id, _kind) in LOOT_CATALOGUE.items():
            with self.subTest(name):
                self.assertIn(item_id, ITEMS)

    def test_the_new_items_are_mapped(self):
        self.assertEqual(LOOT_CATALOGUE["tinned_soup"], ("item_canned_soup", "canned_food"))
        self.assertEqual(LOOT_CATALOGUE["tuna_tin"], ("item_canned_tuna", "canned_food"))
        for name in ("crisps", "crisps2", "crisps3", "crisps4"):
            self.assertEqual(LOOT_CATALOGUE[name], ("item_crisps", "canned_food"))
        self.assertEqual(LOOT_CATALOGUE["soda_can"], ("item_soda_can", "canned_food"))
        self.assertEqual(LOOT_CATALOGUE["sledgehammer"], ("item_sledgehammer", "weapon"))
        self.assertEqual(LOOT_CATALOGUE["tote_bags"], ("item_tote_bag", "container"))
        self.assertEqual(LOOT_CATALOGUE["garbagebag"], ("item_garbage_bag", "container"))

    def test_variants_with_other_values_stay_unmapped(self):
        for name in ("pop", "pop2", "pop3", "juice_box", "sledgehammer2", "shovel2"):
            self.assertNotIn(name, LOOT_CATALOGUE)

    def test_tables_name_only_mapped_items(self):
        tables = [*PROCEDURAL_TABLES.values(), *BAG_TABLES.values()]
        tables += [
            source.table
            for room in ROOM_TABLES.values()
            for source in room.values()
            if source.table is not None
        ]
        for table in tables:
            for name, _chance in (*table.items, *table.junk_items):
                self.assertIn(name, LOOT_CATALOGUE)

    def test_every_table_name_is_snake_case(self):
        for name in LOOT_CATALOGUE:
            self.assertTrue(re.fullmatch(r"[a-z0-9_]+", name), name)


class BindingTests(unittest.TestCase):
    """carrying-and-loot: The rooms: every container binds to a generated table."""

    SHOP_ZONES = ("zone_pharmacy", "zone_clinic", "zone_supermarket", "zone_hardware")

    def containers(self, zones):
        locations = build_starting_locations()
        for zone_id in zones:
            for room in locations[zone_id].rooms.values():
                yield from room.containers

    def test_every_source_resolves_to_a_generated_table(self):
        for container in self.containers(build_starting_locations()):
            if container.source is None:
                continue
            with self.subTest(container.container_id):
                room, kind = container.source
                source = ROOM_TABLES[room][kind]
                for entry in source.procedures:
                    self.assertIn(entry.table, PROCEDURAL_TABLES)

    def test_a_shop_container_is_built_only_if_a_table_can_drop_a_catalogue_item(self):
        for container in self.containers(self.SHOP_ZONES):
            if container.fixed:
                continue
            assert container.source is not None
            source = ROOM_TABLES[container.source[0]][container.source[1]]
            tables = [PROCEDURAL_TABLES[e.table] for e in source.procedures]
            if source.table is not None:
                tables.append(source.table)
            droppable = [name for t in tables for name, _ in (*t.items, *t.junk_items)]
            self.assertTrue(droppable, container.container_id)

    def test_every_generated_source_is_used_by_a_container(self):
        used = {
            c.source for c in self.containers(build_starting_locations()) if c.source is not None
        }
        for room, sources in ROOM_TABLES.items():
            for kind in sources:
                self.assertIn((room, kind), used)

    def test_opening_every_container_stays_within_its_capacity(self):
        for seed in range(5):
            locations = build_starting_locations()
            rng = random.Random(seed)
            for zone in locations.values():
                for room in zone.rooms.values():
                    for container in room.containers:
                        open_container(rng, room, container)
                        self.assertLessEqual(
                            container_weight(container), container.capacity + 0.01, container.name
                        )
