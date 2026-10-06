"""Eating and drinking: consumable fields, status effect facts and alcohol."""

import unittest

from data.items import ITEMS
from managers.game import GameManager
from managers.simulation import SimulationCore
from modules.action.types import UseItemAction
from modules.character.equipment import CharacterHoldableSlot
from modules.entity.item import ItemEntity
from modules.item import ConsumableItem
from modules.stats import CharacterStat
from tests.support import simulate


def _food(name="Apple", **fields) -> ConsumableItem:
    return ConsumableItem(
        id=f"item_test_{name.lower()}",
        name=name,
        description="A test item.",
        max_hit_points=1,
        tags=["food", "consumable"],
        slots=[CharacterHoldableSlot.RIGHT_HAND],
        is_two_handed=False,
        modifiers=[],
        **fields,
    )


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
    """Spec 03, Item fields."""

    def test_the_shipped_foods_carry_the_food_fields(self):
        beans = _consumable("item_canned_beans")
        self.assertAlmostEqual(beans.hunger_change, -0.35)
        self.assertAlmostEqual(beans.thirst_change, -0.05)
        water = _consumable("item_water_bottle")
        self.assertAlmostEqual(water.thirst_change, -0.45)
        self.assertEqual(water.hunger_change, 0)
        granola = _consumable("item_granola_bar")
        self.assertAlmostEqual(granola.hunger_change, -0.20)
        self.assertAlmostEqual(granola.thirst_change, 0.05)
        noodles = _consumable("item_instant_noodles")
        self.assertAlmostEqual(noodles.hunger_change, -0.40)
        self.assertAlmostEqual(noodles.thirst_change, 0.10)

    def test_no_shipped_item_is_alcoholic_and_each_takes_five_minutes_to_eat(self):
        for item in ITEMS.values():
            if isinstance(item, ConsumableItem):
                self.assertFalse(item.alcoholic)
                self.assertFalse(item.low_alcohol)
                self.assertEqual(item.eat_minutes, 5)

    def test_the_canned_beans_carry_no_hp_modifier(self):
        self.assertEqual(_consumable("item_canned_beans").modifiers, [])


class ConsumingTests(unittest.TestCase):
    """Spec 03, Consuming."""

    def test_the_beans_no_longer_heal_directly(self):
        gm = GameManager()
        gm.player.hit_points = 50
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_canned_beans"]))
        simulate(gm, UseItemAction(item_name="Canned Beans"))
        self.assertEqual(gm.player.hit_points, 50)

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

    def test_bad_food_raises_unhappiness_and_clamps(self):
        gm, _ = _eat(_food(unhappy_change=30), unhappiness=90)
        self.assertGreater(gm.player.stats.get(CharacterStat.UNHAPPINESS), 99)

    def test_an_apple_adds_2080_to_the_timer(self):
        # The 5 minutes of eating then drain 900 (10800 per hour).
        gm, _ = _eat(_food(hunger_change=-0.16))
        self.assertAlmostEqual(gm.player.food_eaten_timer, 2080 - 900, delta=1)

    def test_cooked_food_doubles_the_timer(self):
        gm, _ = _eat(_food(hunger_change=-0.16, cooked=True))
        self.assertAlmostEqual(gm.player.food_eaten_timer, 4160 - 900, delta=1)

    def test_the_timer_caps_at_11000(self):
        gm = GameManager()
        gm.player.food_eaten_timer = 10500
        gm.player.inventory.append(ItemEntity(item=_food(hunger_change=-0.5)))
        simulate(gm, UseItemAction(item_name="Apple"))
        self.assertAlmostEqual(gm.player.food_eaten_timer, 11000 - 900, delta=1)

    def test_alcohol_is_applied_to_intoxication_and_clamps_at_the_stat_maximum(self):
        item = _food("Whisky", hunger_change=-0.01, alcoholic=True)
        gm, _ = _eat(item, hunger=0.9)
        self.assertGreater(gm.player.stats.get(CharacterStat.INTOXICATION), 95)

    def test_alcohol_amounts_before_the_clamp(self):
        from managers.stats.status_effects import alcohol_intoxication

        whole = _food("Whisky", hunger_change=-0.01, alcoholic=True)
        none = _food("Spirit", alcoholic=True)
        beer = _food("Beer", hunger_change=-0.01, alcoholic=True, low_alcohol=True)
        self.assertEqual(alcohol_intoxication(whole, 0.9), 1000)
        self.assertAlmostEqual(alcohol_intoxication(whole, 0.7), 880)
        self.assertEqual(alcohol_intoxication(whole, 0.2), 800)
        self.assertEqual(alcohol_intoxication(none, 0.9), 500)
        self.assertEqual(alcohol_intoxication(none, 0.2), 400)
        self.assertEqual(alcohol_intoxication(beer, 0.2), 200)

    def test_alcohol_hunger_bands_and_their_strict_cutoffs(self):
        from managers.stats.status_effects import alcohol_intoxication

        whole = _food("Whisky", hunger_change=-0.01, alcoholic=True)
        for hunger, expected in (
            (0.5, 800),
            (0.6, 800),
            (0.61, 880),
            (0.7, 880),
            (0.8, 880),
            (0.81, 1000),
        ):
            with self.subTest(hunger=hunger):
                self.assertAlmostEqual(alcohol_intoxication(whole, hunger), expected)

    def test_the_alcohol_band_uses_hunger_before_the_meal(self):
        from unittest import mock

        import managers.simulation as simulation

        item = _food("Whisky", hunger_change=-0.1, alcoholic=True)
        gm = GameManager()
        gm.player.stats.set(CharacterStat.HUNGER, 0.65)
        with mock.patch.object(
            simulation, "alcohol_intoxication", wraps=simulation.alcohol_intoxication
        ) as spy:
            SimulationCore(gm)._consume(item)
        self.assertAlmostEqual(spy.call_args.args[1], 0.65)
        self.assertAlmostEqual(simulation.alcohol_intoxication(item, 0.65), 880)

    def test_a_non_alcoholic_item_adds_no_intoxication(self):
        gm, _ = _eat(_food(hunger_change=-0.2))
        self.assertEqual(gm.player.stats.get(CharacterStat.INTOXICATION), 0)

    def test_a_food_item_costs_its_eat_minutes(self):
        for minutes in (5, 12):
            gm, facts = _eat(_food(hunger_change=-0.1, eat_minutes=minutes))
            self.assertEqual(gm.narrative.minutes, minutes)

    def test_eating_reports_the_status_effect_it_clears(self):
        gm, facts = _eat(_food(hunger_change=-0.5), hunger=0.5)
        self.assertIn("Orton is no longer Very Hungry.", facts[0])

    def test_water_is_a_drink_with_a_thirst_change_only(self):
        gm, _ = _eat(_food("Water", thirst_change=-0.5), thirst=0.8)
        self.assertAlmostEqual(gm.player.stats.get(CharacterStat.THIRST), 0.3, delta=0.01)
        self.assertEqual(gm.player.food_eaten_timer, 0)


if __name__ == "__main__":
    unittest.main()
