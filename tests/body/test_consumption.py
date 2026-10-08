"""Eating and drinking: consumable fields, status effect facts and alcohol."""

import unittest

from data.items import ITEMS
from managers.body.stats.status_effects import alcohol_intoxication
from managers.game import GameManager
from managers.simulation import SimulationCore
from modules.action.types import UseItemAction
from modules.body.stats import CharacterStat
from modules.character.equipment import CharacterHoldableSlot
from modules.entity.item import ItemEntity
from modules.item import ConsumableItem
from tests.support import set_health, simulate


def _food(name="Apple", tags=None, **fields) -> ConsumableItem:
    return ConsumableItem(
        id=f"item_test_{name.lower()}",
        name=name,
        description="A test item.",
        max_hit_points=1,
        tags=tags or ["food", "consumable"],
        slots=[CharacterHoldableSlot.RIGHT_HAND],
        is_two_handed=False,
        modifiers=[],
        weight=0.1,
        **fields,
    )


def _beer() -> ConsumableItem:
    return _food("Beer", hunger_change=-0.03, alcohol=0.015, tags=["drink", "consumable"])


def _eat(item: ConsumableItem, **stats) -> tuple[GameManager, list[str]]:
    gm = GameManager()
    gm.player.inventory.clear()
    gm.player.inventory.append(ItemEntity(item=item))
    for stat, value in stats.items():
        gm.player.stats.set(CharacterStat[stat.upper()], value)
    return gm, simulate(gm, UseItemAction(item_name=item.name))


def _consumable(item_id: str) -> ConsumableItem:
    item = ITEMS[item_id]
    assert isinstance(item, ConsumableItem)
    return item


class ConsumableItemFieldTests(unittest.TestCase):
    """status-effects: Item fields."""

    def test_the_shipped_foods_carry_the_item_values(self):
        beans = _consumable("item_canned_beans")
        self.assertAlmostEqual(beans.hunger_change, -0.24)
        self.assertEqual(beans.thirst_change, 0)
        self.assertEqual(beans.unhappy_change, 10)
        water = _consumable("item_water_bottle")
        self.assertAlmostEqual(water.thirst_change, -0.50)
        self.assertEqual(water.hunger_change, 0)
        self.assertIn("litre", water.description)
        self.assertNotIn("Half", water.description)
        granola = _consumable("item_granola_bar")
        self.assertAlmostEqual(granola.hunger_change, -0.15)
        self.assertEqual(granola.thirst_change, 0)
        noodles = _consumable("item_instant_noodles")
        self.assertAlmostEqual(noodles.hunger_change, -0.10)
        self.assertAlmostEqual(noodles.thirst_change, 0.40)
        self.assertEqual(noodles.unhappy_change, 20)

    def test_no_shipped_item_is_alcoholic_and_each_takes_five_minutes_to_eat(self):
        for item in ITEMS.values():
            if isinstance(item, ConsumableItem):
                self.assertEqual(item.alcohol, 0)
                self.assertEqual(item.eat_minutes, 5)

    def test_the_canned_beans_carry_no_hp_modifier(self):
        self.assertEqual(_consumable("item_canned_beans").modifiers, [])


class ConsumingTests(unittest.TestCase):
    """status-effects: Consuming."""

    def test_the_beans_no_longer_heal_directly(self):
        gm = GameManager()
        set_health(gm.player, 50)
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_canned_beans"]))
        simulate(gm, UseItemAction(item_name="Canned Beans"))
        self.assertLess(gm.player.health, 60)

    def test_each_field_applies_once(self):
        item = _food(
            hunger_change=-0.2,
            thirst_change=-0.1,
            unhappy_change=-5,
            boredom_change=-10,
            stress_change=-0.05,
        )
        gm = GameManager()
        stats = gm.player.stats
        for stat, value in (
            (CharacterStat.HUNGER, 0.5),
            (CharacterStat.THIRST, 0.5),
            (CharacterStat.UNHAPPINESS, 20),
            (CharacterStat.BOREDOM, 30),
            (CharacterStat.STRESS, 0.5),
        ):
            stats.set(stat, value)
        SimulationCore(gm)._consume(item)
        self.assertAlmostEqual(stats.get(CharacterStat.HUNGER), 0.3)
        self.assertAlmostEqual(stats.get(CharacterStat.THIRST), 0.4)
        self.assertAlmostEqual(stats.get(CharacterStat.UNHAPPINESS), 15)
        self.assertAlmostEqual(stats.get(CharacterStat.BOREDOM), 20)
        self.assertAlmostEqual(stats.get(CharacterStat.STRESS), 0.45)

    def test_a_meal_reports_well_fed_once(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.HUNGER, 0.2)
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_canned_beans"]))
        facts = simulate(gm, UseItemAction(item_name="Canned Beans"))
        self.assertEqual(" ".join(facts).count("Well Fed"), 1, facts)

    def test_bad_food_raises_unhappiness_and_clamps(self):
        gm, _ = _eat(_food(unhappy_change=30), unhappiness=90)
        self.assertGreater(gm.player.stats.get(CharacterStat.UNHAPPINESS), 99)

    def test_an_apple_that_empties_hunger_adds_2080_to_the_timer(self):
        # The 5 minutes of eating then drain 900 (10800 per hour).
        gm, _ = _eat(_food(hunger_change=-0.16), hunger=0.16)
        self.assertAlmostEqual(gm.player.food_eaten_timer, 2080 - 900, delta=1)

    def test_an_apple_at_hunger_point_five_leaves_the_timer_alone(self):
        gm, _ = _eat(_food(hunger_change=-0.16), hunger=0.5)
        self.assertAlmostEqual(gm.player.stats.get(CharacterStat.HUNGER), 0.34, delta=0.01)
        self.assertEqual(gm.player.food_eaten_timer, 0)

    def test_a_meal_leaving_hunger_just_above_zero_leaves_the_timer_alone(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.HUNGER, 0.21)
        SimulationCore(gm)._consume(_food(hunger_change=-0.16))
        self.assertAlmostEqual(gm.player.stats.get(CharacterStat.HUNGER), 0.05)
        self.assertEqual(gm.player.food_eaten_timer, 0)

    def test_a_full_strength_drink_adds_400_intoxication(self):
        spirit = _food("Spirit", alcohol=1.0, tags=["drink", "consumable"])
        self.assertAlmostEqual(alcohol_intoxication(spirit, 0.4), 400)

    def test_beans_at_hunger_point_two_store_zero_and_add_3120(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.HUNGER, 0.2)
        gm.player.stats.set(CharacterStat.UNHAPPINESS, 0)
        SimulationCore(gm)._consume(_consumable("item_canned_beans"))
        self.assertEqual(gm.player.stats.get(CharacterStat.HUNGER), 0)
        self.assertEqual(gm.player.stats.get(CharacterStat.UNHAPPINESS), 10)
        self.assertAlmostEqual(gm.player.food_eaten_timer, 3120)

    def test_beans_at_hunger_point_five_add_nothing(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.HUNGER, 0.5)
        SimulationCore(gm)._consume(_consumable("item_canned_beans"))
        self.assertAlmostEqual(gm.player.stats.get(CharacterStat.HUNGER), 0.26)
        self.assertEqual(gm.player.food_eaten_timer, 0)

    def test_granola_and_noodles_values_apply(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.HUNGER, 0.5)
        gm.player.stats.set(CharacterStat.THIRST, 0.2)
        SimulationCore(gm)._consume(_consumable("item_granola_bar"))
        self.assertAlmostEqual(gm.player.stats.get(CharacterStat.HUNGER), 0.35)
        self.assertAlmostEqual(gm.player.stats.get(CharacterStat.THIRST), 0.2)
        SimulationCore(gm)._consume(_consumable("item_instant_noodles"))
        self.assertAlmostEqual(gm.player.stats.get(CharacterStat.HUNGER), 0.25)
        self.assertAlmostEqual(gm.player.stats.get(CharacterStat.THIRST), 0.6)
        self.assertAlmostEqual(gm.player.stats.get(CharacterStat.UNHAPPINESS), 20)

    def test_the_water_bottle_changes_thirst_by_half(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.THIRST, 0.8)
        SimulationCore(gm)._consume(_consumable("item_water_bottle"))
        self.assertAlmostEqual(gm.player.stats.get(CharacterStat.THIRST), 0.3)

    def test_cooked_food_doubles_the_timer(self):
        gm, _ = _eat(_food(hunger_change=-0.16, cooked=True), hunger=0.16)
        self.assertAlmostEqual(gm.player.food_eaten_timer, 4160 - 900, delta=1)

    def test_the_timer_caps_at_11000(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.HUNGER, 0.4)
        gm.player.food_eaten_timer = 10500
        gm.player.inventory.append(ItemEntity(item=_food(hunger_change=-0.5)))
        simulate(gm, UseItemAction(item_name="Apple"))
        self.assertAlmostEqual(gm.player.food_eaten_timer, 11000 - 900, delta=1)

    def test_a_drink_adds_its_hunger_share_every_time_and_uncapped(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.HUNGER, 0.5)
        gm.player.food_eaten_timer = 20000
        broth = _food("Broth", hunger_change=-0.1, tags=["drink", "consumable"])
        SimulationCore(gm)._consume(broth)
        self.assertAlmostEqual(gm.player.food_eaten_timer, 21300)

    def test_alcohol_reads_hunger_after_the_drink_with_the_swapped_bands(self):
        for before, expected in ((0.53, 6.0), (0.73, 7.5), (0.93, 6.6)):
            with self.subTest(hunger_before=before):
                gm = GameManager()
                gm.player.stats.set(CharacterStat.HUNGER, before)
                SimulationCore(gm)._consume(_beer())
                self.assertAlmostEqual(gm.player.stats.get(CharacterStat.INTOXICATION), expected)

    def test_alcohol_band_edges_are_strict(self):
        for after, expected in ((0.6, 6.0), (0.61, 7.5), (0.8, 7.5), (0.81, 6.6)):
            with self.subTest(hunger_after=after):
                gm = GameManager()
                gm.player.stats.set(CharacterStat.HUNGER, after + 0.03)
                SimulationCore(gm)._consume(_beer())
                self.assertAlmostEqual(gm.player.stats.get(CharacterStat.INTOXICATION), expected)

    def test_a_litre_of_strong_spirit_clamps_intoxication_to_100(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.HUNGER, 0.5)
        spirit = _food("Spirit", hunger_change=-0.2, alcohol=0.4, tags=["drink", "consumable"])
        SimulationCore(gm)._consume(spirit)
        self.assertEqual(gm.player.stats.get(CharacterStat.INTOXICATION), 100)

    def test_a_non_alcoholic_item_adds_no_intoxication(self):
        gm, _ = _eat(_food(hunger_change=-0.2))
        self.assertEqual(gm.player.stats.get(CharacterStat.INTOXICATION), 0)

    def test_a_food_item_costs_its_eat_minutes(self):
        for minutes in (5, 12):
            gm, facts = _eat(_food(hunger_change=-0.1, eat_minutes=minutes))
            self.assertEqual(gm.narrative.minutes, minutes)

    def test_eating_reports_the_status_effect_it_clears(self):
        gm, facts = _eat(_food(hunger_change=-0.5), hunger=0.5)
        self.assertIn("Orton is no longer Very Hungry.", facts)

    def test_water_is_a_drink_with_a_thirst_change_only(self):
        gm, _ = _eat(_food("Water", thirst_change=-0.5), thirst=0.8)
        self.assertAlmostEqual(gm.player.stats.get(CharacterStat.THIRST), 0.3, delta=0.01)
        self.assertEqual(gm.player.food_eaten_timer, 0)


if __name__ == "__main__":
    unittest.main()
