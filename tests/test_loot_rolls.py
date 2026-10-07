"""Spec 25, Rooms and containers: the loot tables, the catalogue and how containers roll them."""

import math
import random
import re
import unittest
from unittest import mock

from data.items import ITEMS
from data.loot_catalogue import LOOT_CATALOGUE, LOOT_KIND_MODIFIERS
from data.loot_tables import (
    BAG_TABLES,
    PROCEDURAL_TABLES,
    ROOM_TABLES,
    ContainerSource,
    LootTable,
    ProcedureEntry,
)
from managers import containers
from modules.entity.item import ItemEntity
from modules.item import MeleeWeaponItem
from modules.room import ContainerEntity, RoomEntity
from tests.support import ScriptedRandom


class KindModifierTests(unittest.TestCase):
    """Spec 25, Filling a container: the modifier for each kind."""

    def test_food_and_other_are_point_eight_key_point_four_ranged_one_point_two(self):
        self.assertEqual(LOOT_KIND_MODIFIERS["food"], 0.8)
        self.assertEqual(LOOT_KIND_MODIFIERS["other"], 0.8)
        self.assertEqual(LOOT_KIND_MODIFIERS["key"], 0.4)
        self.assertEqual(LOOT_KIND_MODIFIERS["ranged_weapon"], 1.2)

    def test_every_other_kind_is_point_six(self):
        others = {
            kind: mod
            for kind, mod in LOOT_KIND_MODIFIERS.items()
            if kind not in ("food", "other", "key", "ranged_weapon")
        }
        self.assertEqual(
            sorted(others),
            sorted(
                [
                    "canned_food",
                    "medical",
                    "weapon",
                    "container",
                    "clothing",
                    "literature",
                    "tool",
                    "cookware",
                    "material",
                    "mechanics",
                    "farming",
                    "survival_gear",
                    "ammo",
                    "skill_book",
                    "recipe_resource",
                    "media",
                    "memento",
                ]
            ),
        )
        self.assertEqual(set(others.values()), {0.6})


class CatalogueTests(unittest.TestCase):
    """Spec 25, Item mapping."""

    def test_the_explicit_rows(self):
        rows = {
            "pills": ("item_painkillers", "medical"),
            "bandage": ("item_bandage", "medical"),
            "bandaid": ("item_adhesive_bandage", "medical"),
            "alcohol_wipes": ("item_alcohol_wipes", "medical"),
            "antibiotics": ("item_antibiotics", "medical"),
            "disinfectant": ("item_disinfectant", "medical"),
            "ripped_sheets": ("item_ripped_sheets", "other"),
            "ripped_sheets_dirty": ("item_dirty_ripped_sheets", "other"),
            "water_bottle": ("item_water_bottle", "other"),
            "granola_bar": ("item_granola_bar", "canned_food"),
            "tinned_beans": ("item_canned_beans", "canned_food"),
            "ramen": ("item_instant_noodles", "food"),
            "nails": ("item_nails", "material"),
            "dumb_bell": ("item_dumbbell", "weapon"),
            "bar_bell": ("item_barbell", "weapon"),
            "hammer": ("item_hammer", "weapon"),
            "pan": ("item_frying_pan", "weapon"),
        }
        for name, row in rows.items():
            with self.subTest(name=name):
                self.assertEqual(LOOT_CATALOGUE.get(name), row)

    def test_clothing_maps_to_its_own_id_with_the_clothing_kind(self):
        self.assertEqual(LOOT_CATALOGUE.get("socks_ankle"), ("item_socks_ankle", "clothing"))

    def test_every_row_names_a_real_item_and_a_known_kind(self):
        for name, (item_id, kind) in LOOT_CATALOGUE.items():
            with self.subTest(name=name):
                self.assertIn(item_id, ITEMS)
                self.assertIn(kind, LOOT_KIND_MODIFIERS)


class TableShapeTests(unittest.TestCase):
    """Spec 25, Testing: every source resolves to a generated table and every id is snake_case."""

    def test_the_tables_exist(self):
        self.assertGreater(len(PROCEDURAL_TABLES), 0)
        self.assertGreater(len(ROOM_TABLES), 0)

    def test_every_procedure_names_a_generated_table(self):
        for room, types in ROOM_TABLES.items():
            for ctype, source in types.items():
                for entry in source.procedures:
                    with self.subTest(source=f"{room}.{ctype}", table=entry.table):
                        self.assertIn(entry.table, PROCEDURAL_TABLES)

    def test_every_id_is_lowercase_snake_case(self):
        names = [*PROCEDURAL_TABLES, *BAG_TABLES, *ROOM_TABLES]
        names += [c for types in ROOM_TABLES.values() for c in types]
        for name in names:
            with self.subTest(name=name):
                self.assertRegex(name, r"^[a-z0-9_]+$")

    def test_every_item_in_a_table_is_a_catalogue_name(self):
        tables = [*PROCEDURAL_TABLES.values(), *BAG_TABLES.values()]
        tables += [s.table for t in ROOM_TABLES.values() for s in t.values() if s.table]
        for table in tables:
            for name, chance in [*table.items, *table.junk_items]:
                with self.subTest(name=name):
                    self.assertIn(name, LOOT_CATALOGUE)
                    self.assertGreater(chance, 0)
                    self.assertTrue(re.fullmatch(r"[a-z0-9_]+", name))

    def test_the_kitchen_cupboards_force_dishes_and_cap_canned_food_at_two(self):
        cupboards = ROOM_TABLES["kitchen"]["overhead"].procedures
        self.assertEqual(
            [p for p in cupboards if p.table in ("kitchen_dishes", "kitchen_canned_food")],
            [
                ProcedureEntry("kitchen_canned_food", 0, 2, 100),
                ProcedureEntry("kitchen_dishes", 1, 1, 100),
            ],
        )

    def test_the_corner_store_tables_are_shop_tables_and_the_kitchen_ones_are_not(self):
        self.assertTrue(PROCEDURAL_TABLES["store_shelf_snacks"].shop)
        self.assertTrue(PROCEDURAL_TABLES["store_counter_bags"].shop)
        self.assertFalse(PROCEDURAL_TABLES["kitchen_canned_food"].shop)

    def test_the_corner_store_fridge_forces_all_four_of_its_tables(self):
        fridge = ROOM_TABLES["cornerstore"]["fridge"].procedures
        self.assertEqual([p.min_picks for p in fridge], [1, 1, 1, 1])
        self.assertEqual([p.weight for p in fridge], [40, 100, 100, 60])

    def test_the_kitchen_counter_picks_among_eight_tables_each_used_once(self):
        counter = ROOM_TABLES["kitchen"]["counter"].procedures
        self.assertEqual(
            [(p.max_picks, p.weight) for p in counter],
            [(1, 40), (1, 40), (1, 80), (1, 100), (1, 80), (1, 100), (1, 80), (1, 20)],
        )

    def test_the_kitchen_canned_food_table_rolls_twice_and_holds_beans(self):
        table = PROCEDURAL_TABLES["kitchen_canned_food"]
        self.assertEqual(table.rolls, 2)
        self.assertIn("tinned_beans", [name for name, _ in table.items])

    def test_a_bag_that_can_spawn_has_its_own_table(self):
        toolbox = BAG_TABLES["toolbox"]
        self.assertEqual(toolbox.rolls, 1)
        self.assertIn("hammer", [name for name, _ in toolbox.items])


def table(*items: tuple[str, float], rolls: int = 1, junk=(), shop: bool = False) -> LootTable:
    return LootTable(rolls, tuple(items), 1, tuple(junk), shop)


def spawn_rate(entry: tuple[str, float], draws: int, *, junk: bool = False) -> float:
    """The share of `draws` fresh rolls, seeded, that spawn the entry."""
    rng = random.Random(2025)
    lone = table(entry) if not junk else table(junk=(entry,))
    hits = sum(bool(containers.roll_table(rng, lone, capacity=1000.0)) for _ in range(draws))
    return hits / draws


class RollChanceTests(unittest.TestCase):
    """Spec 25, Filling a container: spawn if randrange(10000) < chance x 100 x modifier."""

    def assert_rate(self, observed: float, expected: float, draws: int) -> None:
        sigma = math.sqrt(expected * (1 - expected) / draws)
        self.assertLessEqual(abs(observed - expected), 3 * sigma)

    def test_chance_20_in_a_medical_kind_drops_at_0_12(self):
        observed = spawn_rate(("pills", 20.0), 20000)
        self.assert_rate(observed, 0.12, 20000)

    def test_chance_4_in_a_food_kind_drops_at_0_032(self):
        observed = spawn_rate(("ramen", 4.0), 40000)
        self.assert_rate(observed, 0.032, 40000)

    def test_chance_0_1_in_a_weapon_kind_drops_at_0_06_percent(self):
        observed = spawn_rate(("hammer", 0.1), 400000)
        self.assert_rate(observed, 0.0006, 400000)

    def test_a_junk_entry_uses_the_junk_multiplier_and_modifier_one(self):
        observed = spawn_rate(("pills", 10.0), 20000, junk=True)
        self.assert_rate(observed, 0.14, 20000)

    def test_the_roll_is_below_value_so_the_edge_does_not_spawn(self):
        one_in_ten = table(("pills", 10.0))
        below = ScriptedRandom(randrange=[599])
        edge = ScriptedRandom(randrange=[600])
        self.assertEqual(len(containers.roll_table(below, one_in_ten, capacity=50.0)), 1)
        self.assertEqual(len(containers.roll_table(edge, one_in_ten, capacity=50.0)), 0)

    def test_every_pass_rolls_every_entry_in_order(self):
        two_passes = table(("water_bottle", 100.0), ("granola_bar", 100.0), rolls=2)
        found = containers.roll_table(ScriptedRandom(), two_passes, capacity=50.0)
        self.assertEqual(
            [e.item.id for e in found],
            ["item_water_bottle", "item_granola_bar", "item_water_bottle", "item_granola_bar"],
        )


def room_of(*entries: ProcedureEntry) -> tuple[RoomEntity, tuple[ProcedureEntry, ...]]:
    return RoomEntity(room_id="r", name="r", kind="kitchen"), entries


class ProceduralPickTests(unittest.TestCase):
    """Spec 25, The procedural pick."""

    def test_weights_40_and_100_pick_the_first_with_probability_41_over_140(self):
        room, entries = room_of(ProcedureEntry("a", 0, 99, 40), ProcedureEntry("b", 0, 99, 100))
        rng = random.Random(7)
        draws = 40000
        first = 0
        for _ in range(draws):
            room.proc_spawned.clear()
            picked = containers.pick_procedural(rng, room, entries)
            first += picked is not None and picked.table == "a"
        expected = 41 / 140
        self.assertLessEqual(
            abs(first / draws - expected), 3 * math.sqrt(expected * (1 - expected) / draws)
        )

    def test_the_boundaries_of_the_walk(self):
        room, entries = room_of(ProcedureEntry("a", 0, 99, 40), ProcedureEntry("b", 0, 99, 100))
        at_40 = containers.pick_procedural(ScriptedRandom(randrange=[40]), room, entries)
        room.proc_spawned.clear()
        at_41 = containers.pick_procedural(ScriptedRandom(randrange=[41]), room, entries)
        assert at_40 is not None and at_41 is not None
        self.assertEqual((at_40.table, at_41.table), ("a", "b"))

    def test_a_forced_table_not_yet_used_in_the_room_is_picked_first(self):
        room, entries = room_of(
            ProcedureEntry("plain", 0, 99, 1000), ProcedureEntry("forced", 1, 1, 1)
        )
        for seed in range(50):
            room.proc_spawned.clear()
            picked = containers.pick_procedural(random.Random(seed), room, entries)
            assert picked is not None
            self.assertEqual(picked.table, "forced")
        self.assertEqual(room.proc_spawned, {"forced": 1})

    def test_once_the_forced_table_is_used_the_others_are_open(self):
        room, entries = room_of(
            ProcedureEntry("plain", 0, 99, 1000), ProcedureEntry("forced", 1, 1, 1)
        )
        room.proc_spawned["forced"] = 1
        picked = containers.pick_procedural(random.Random(1), room, entries)
        assert picked is not None
        self.assertEqual(picked.table, "plain")

    def test_a_table_with_max_1_is_not_picked_twice_in_a_room(self):
        room, entries = room_of(
            ProcedureEntry("once", 0, 1, 100), ProcedureEntry("other", 0, 99, 1)
        )
        rng = random.Random(3)
        picks = [containers.pick_procedural(rng, room, entries) for _ in range(40)]
        names = [p.table for p in picks if p is not None]
        self.assertEqual(names.count("once"), 1)

    def test_no_table_left_means_no_pick(self):
        room, entries = room_of(ProcedureEntry("once", 0, 1, 100))
        room.proc_spawned["once"] = 1
        self.assertIsNone(containers.pick_procedural(random.Random(1), room, entries))

    def test_a_weight_of_0_counts_as_1_in_the_data_so_every_generated_weight_is_positive(self):
        for types in ROOM_TABLES.values():
            for source in types.values():
                for entry in source.procedures:
                    self.assertGreater(entry.weight, 0)


class CapacityCutoffTests(unittest.TestCase):
    """Spec 25, The capacity cutoff."""

    def test_when_an_item_does_not_fit_the_rest_of_the_rolls_stop(self):
        heavy_then_light = table(
            ("hammer", 100.0), ("hammer", 100.0), ("water_bottle", 100.0), rolls=2
        )
        found = containers.roll_table(ScriptedRandom(), heavy_then_light, capacity=2.0)
        self.assertEqual([e.item.id for e in found], ["item_hammer"])

    def test_an_item_that_brings_the_container_to_exactly_its_capacity_goes_in(self):
        two_hammers = table(("hammer", 100.0), rolls=2)
        found = containers.roll_table(ScriptedRandom(), two_hammers, capacity=3.0)
        self.assertEqual(len(found), 2)

    def test_an_item_a_hundredth_of_a_kilo_over_the_capacity_is_cut_off(self):
        two_hammers = table(("hammer", 100.0), rolls=2)
        found = containers.roll_table(ScriptedRandom(), two_hammers, capacity=2.99)
        self.assertEqual(len(found), 1)

    def test_a_full_junk_list_stops_only_the_junk_and_the_main_list_still_runs(self):
        both = table(
            ("granola_bar", 100.0),
            junk=(("hammer", 100.0), ("hammer", 100.0), ("hammer", 100.0)),
        )
        found = containers.roll_table(ScriptedRandom(), both, capacity=2.0)
        self.assertEqual([e.item.id for e in found], ["item_hammer", "item_granola_bar"])

    def test_weight_already_in_the_container_counts(self):
        found = containers.roll_table(
            ScriptedRandom(), table(("hammer", 100.0)), capacity=2.0, held=1.0
        )
        self.assertEqual(found, [])

    def test_unmapped_entries_are_skipped_without_a_roll(self):
        entries = table(("not_in_the_catalogue", 100.0), ("water_bottle", 100.0))
        found = containers.roll_table(ScriptedRandom(randrange=[9999, 0]), entries, capacity=50.0)
        self.assertEqual(found, [])


class AfterSpawnTests(unittest.TestCase):
    """Spec 25, Filling a container: step 4, random condition, uses and filled bags."""

    def test_a_weapon_outside_a_shop_may_spawn_worn(self):
        rng = ScriptedRandom(randrange=[0, 39, 3])
        (hammer,) = containers.roll_table(rng, table(("hammer", 100.0)), capacity=50.0)
        self.assertEqual(hammer.condition, 3)

    def test_a_random_condition_is_at_least_1(self):
        rng = ScriptedRandom(randrange=[0, 0, 0])
        (hammer,) = containers.roll_table(rng, table(("hammer", 100.0)), capacity=50.0)
        self.assertEqual(hammer.condition, 1)

    def test_a_percent_draw_of_40_leaves_the_condition_full(self):
        rng = ScriptedRandom(randrange=[0, 40, 3])
        (hammer,) = containers.roll_table(rng, table(("hammer", 100.0)), capacity=50.0)
        item = hammer.item
        assert isinstance(item, MeleeWeaponItem)
        self.assertEqual(hammer.condition, item.condition_max)

    def test_a_shop_table_never_randomises(self):
        rng = ScriptedRandom(randrange=[0, 0, 3])
        (hammer,) = containers.roll_table(rng, table(("hammer", 100.0), shop=True), capacity=50.0)
        self.assertEqual(hammer.condition, 10)

    def test_a_multi_use_item_may_spawn_part_used(self):
        rng = ScriptedRandom(randrange=[0, 39, 4])
        (pills,) = containers.roll_table(rng, table(("pills", 100.0)), capacity=50.0)
        self.assertEqual(pills.uses, 4)

    def test_a_single_use_item_draws_nothing_more(self):
        rng = ScriptedRandom(randrange=[0, 0, 0])
        (bandage,) = containers.roll_table(rng, table(("bandage", 100.0)), capacity=50.0)
        self.assertEqual(bandage.uses, 1)

    def test_a_bag_spawns_filled_from_its_own_table(self):
        bag_tables = {"toolbox": table(("hammer", 100.0))}
        (box,) = containers.roll_table(
            ScriptedRandom(), table(("toolbox", 100.0)), capacity=50.0, bag_tables=bag_tables
        )
        self.assertEqual([e.item.id for e in box.contents], ["item_hammer"])

    def test_a_bag_in_a_shop_container_is_empty(self):
        bag_tables = {"toolbox": table(("hammer", 100.0))}
        (box,) = containers.roll_table(
            ScriptedRandom(),
            table(("toolbox", 100.0), shop=True),
            capacity=50.0,
            bag_tables=bag_tables,
        )
        self.assertEqual(box.contents, [])

    def test_a_bags_fill_stops_at_the_bags_own_capacity(self):
        stock = (
            ("plank", 100.0),
            ("hammer", 100.0),
            ("hammer", 100.0),
            ("hammer", 100.0),
            ("hammer", 100.0),
        )
        (box,) = containers.roll_table(
            ScriptedRandom(),
            table(("toolbox", 100.0)),
            capacity=50.0,
            bag_tables={"toolbox": table(*stock)},
        )
        self.assertEqual(
            [e.item.id for e in box.contents],
            ["item_plank", "item_hammer", "item_hammer", "item_hammer"],
        )


def container_of(source: tuple[str, str] | None, *, capacity: float = 50.0, fixed: bool = False):
    return ContainerEntity(
        container_id="c", name="c", kind="counter", capacity=capacity, source=source, fixed=fixed
    )


class OpenContainerTests(unittest.TestCase):
    """Spec 25, Filling a container: fills when first opened, never refills."""

    def test_opening_fills_from_the_sources_table_and_marks_it_opened(self):
        room = RoomEntity(room_id="k", name="k", kind="kitchen")
        box = container_of(("kitchen", "freezer"))
        with mock.patch.dict(
            PROCEDURAL_TABLES, {"freezer_generic": table(("water_bottle", 100.0))}
        ):
            containers.open_container(ScriptedRandom(), room, box)
        self.assertTrue(box.opened)
        self.assertEqual([e.item.id for e in box.contents], ["item_water_bottle"])
        self.assertEqual(room.proc_spawned, {"freezer_generic": 1})

    def test_a_reopened_container_is_never_refilled(self):
        room = RoomEntity(room_id="k", name="k", kind="kitchen")
        box = container_of(("kitchen", "freezer"))
        box.opened = True
        rng = mock.Mock(spec=random.Random)
        containers.open_container(rng, room, box)
        self.assertEqual(box.contents, [])
        self.assertEqual(rng.mock_calls, [])

    def test_fixed_contents_are_never_rolled(self):
        room = RoomEntity(room_id="h", name="h", kind="hall")
        box = container_of(None, fixed=True)
        box.contents.append(ItemEntity(item=ITEMS["item_bandage"]))
        rng = mock.Mock(spec=random.Random)
        containers.open_container(rng, room, box)
        self.assertTrue(box.opened)
        self.assertEqual([e.item.id for e in box.contents], ["item_bandage"])
        self.assertEqual(rng.mock_calls, [])

    def test_the_fill_stops_at_the_containers_capacity(self):
        room = RoomEntity(room_id="k", name="k", kind="kitchen")
        box = container_of(("kitchen", "freezer"), capacity=1.0)
        with mock.patch.dict(
            PROCEDURAL_TABLES,
            {"freezer_generic": table(("water_bottle", 100.0), ("granola_bar", 100.0))},
        ):
            containers.open_container(ScriptedRandom(), room, box)
        self.assertEqual(box.contents, [])

    def test_a_source_with_its_own_table_rolls_it_without_a_pick(self):
        room = RoomEntity(room_id="k", name="k", kind="kitchen")
        box = container_of(("test", "box"))
        own = ContainerSource((), table(("water_bottle", 100.0)))
        with mock.patch.dict(ROOM_TABLES, {"test": {"box": own}}):
            containers.open_container(ScriptedRandom(), room, box)
        self.assertEqual([e.item.id for e in box.contents], ["item_water_bottle"])
        self.assertEqual(room.proc_spawned, {})

    def test_every_real_source_opens_without_error_over_many_seeds(self):
        for room_id, types in ROOM_TABLES.items():
            for container_type in types:
                for seed in range(20):
                    room = RoomEntity(room_id="r", name="r", kind=room_id)
                    box = container_of((room_id, container_type), capacity=50.0)
                    containers.open_container(random.Random(seed), room, box)
                    self.assertTrue(box.opened)
