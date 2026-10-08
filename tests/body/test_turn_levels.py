import unittest

from managers.game import GameManager
from modules.action.types import Duration, UseItemAction, WaitAction
from modules.body.stats import CharacterStat
from modules.entity.item import ItemEntity
from tests.body.test_consumption import _food
from tests.support import simulate


def _gm_with(*items) -> GameManager:
    gm = GameManager()
    gm.player.inventory.clear()
    for item in items:
        gm.player.inventory.append(ItemEntity(item=item))
    return gm


class TurnNetLevelTests(unittest.TestCase):
    """status-effects: Level changes are netted over the whole turn."""

    def test_two_actions_report_each_status_effect_once_at_its_final_level(self):
        first = _food("Chocolate", hunger_change=-0.1, boredom_change=30)
        second = _food("Soda", hunger_change=-0.2, boredom_change=-30)
        gm = _gm_with(first, second)
        gm.player.stats.set(CharacterStat.HUNGER, 0.5)
        facts = simulate(gm, UseItemAction(item_name="Chocolate"), UseItemAction(item_name="Soda"))
        self.assertEqual(facts.count("Orton is now Peckish."), 1)
        self.assertNotIn("Orton is now Hungry.", facts)
        self.assertFalse([f for f in facts if "Bored" in f])

    def test_a_status_effect_that_went_and_came_back_gives_no_fact(self):
        first = _food("Chocolate", boredom_change=30)
        second = _food("Soda", boredom_change=-30)
        gm = _gm_with(first, second)
        facts = simulate(gm, UseItemAction(item_name="Chocolate"), UseItemAction(item_name="Soda"))
        self.assertFalse([f for f in facts if "Bored" in f])

    def test_a_long_wait_still_reports_its_net_change(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.HUNGER, 0.149)
        facts = simulate(gm, WaitAction(duration=Duration(minutes=60)))
        self.assertEqual(facts.count("Orton is now Peckish."), 1)

    def test_the_net_facts_come_before_the_minutes_fact(self):
        gm = _gm_with(_food("Chocolate", hunger_change=-0.3))
        gm.player.stats.set(CharacterStat.HUNGER, 0.5)
        facts = simulate(gm, UseItemAction(item_name="Chocolate"))
        self.assertEqual(facts[-2:], ["Orton is now Peckish.", "About 5 minutes pass."])

    def test_other_facts_stay_where_they_happened(self):
        gm = _gm_with(_food("Chocolate", hunger_change=-0.3))
        gm.player.stats.set(CharacterStat.HUNGER, 0.5)
        facts = simulate(
            gm, UseItemAction(item_name="Chocolate"), UseItemAction(item_name="Nothing")
        )
        self.assertEqual(facts[0], "Use Chocolate: succeeded.")
        self.assertTrue(facts[1].startswith("Refused"))
        self.assertEqual(facts[2], "Orton is now Peckish.")


if __name__ == "__main__":
    unittest.main()
