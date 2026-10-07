"""Spec 14, Corpse sickness: standing among many bodies makes the player sick."""

import unittest

from data.character import traits as trait_k
from data.items import ITEMS
from managers.body.stats.drivers import StatContext, default_drivers
from managers.body.stats.engine import StatsEngine
from managers.corpses import sickness as corpse_sickness
from managers.game import GameManager
from modules.action.types import Duration, WaitAction
from modules.body.stats import CharacterStat
from modules.entity.corpse import CorpseEntity
from modules.entity.item import ItemEntity
from modules.entity.player import PlayerEntity
from modules.item import ClothingItem
from tests.support import simulate
from tests.test_simulation import zombie_game

S = CharacterStat


def player() -> PlayerEntity:
    return PlayerEntity(name="Orton", current_location_id="zone_home")


def hour(p: PlayerEntity, **ctx) -> None:
    StatsEngine(default_drivers()).advance(p, 60, StatContext(**ctx))


def add_bodies(gm: GameManager, zone_id: str, count: int, *, skeletons: int = 0) -> None:
    for number in range(count):
        corpse_id = f"c{len(gm.world.corpses) + 1}"
        gm.world.corpses[corpse_id] = CorpseEntity(
            corpse_id=corpse_id,
            zone_id=zone_id,
            gap=5.0,
            female=False,
            outfit="generic01",
            died_at=0,
            rot_at_death=1,
            skeleton=number < skeletons,
        )


class RateTests(unittest.TestCase):
    """Spec 14, Corpse sickness: the rate per game hour."""

    def gained(self, corpses: int, **ctx) -> float:
        p = player()
        p.stats.set(S.FOOD_SICKNESS, 10.0)
        hour(p, corpse_count=corpses, **ctx)
        return p.stats.get(S.FOOD_SICKNESS) - 10.0

    def test_five_corpses_or_fewer_make_no_one_sick(self):
        self.assertLessEqual(self.gained(5), 0)

    def test_the_sixth_corpse_adds_1_134_an_hour(self):
        self.assertAlmostEqual(self.gained(6), 1.134, places=3)

    def test_each_further_corpse_adds_another_1_134(self):
        self.assertAlmostEqual(self.gained(10), 5.67, places=3)

    def test_25_corpses_and_beyond_add_22_68_an_hour(self):
        self.assertAlmostEqual(self.gained(25), 22.68, places=3)
        self.assertAlmostEqual(self.gained(80), 22.68, places=3)

    def test_the_defence_cuts_the_rate_by_its_percent(self):
        self.assertAlmostEqual(self.gained(25, corpse_defence=25), 22.68 * 0.75, places=3)

    def test_resilient_cuts_a_quarter_and_prone_to_illness_adds_a_quarter(self):
        resilient = frozenset({trait_k.RESILIENT_ID})
        prone = frozenset({trait_k.PRONE_TO_ILLNESS_ID})
        self.assertAlmostEqual(self.gained(25, traits=resilient), 22.68 * 0.75, places=3)
        self.assertAlmostEqual(self.gained(25, traits=prone), 22.68 * 1.25, places=3)

    def test_the_decay_stops_while_the_rate_applies(self):
        p = player()
        p.stats.set(S.FOOD_SICKNESS, 50.0)
        hour(p, corpse_count=6)
        self.assertAlmostEqual(p.stats.get(S.FOOD_SICKNESS), 51.134, places=3)

    def test_the_decay_runs_when_there_is_no_rate(self):
        p = player()
        p.stats.set(S.FOOD_SICKNESS, 50.0)
        hour(p, corpse_count=5)
        self.assertAlmostEqual(p.stats.get(S.FOOD_SICKNESS), 50 - 16.2, places=3)

    def test_a_defence_of_100_lets_the_decay_run_again(self):
        p = player()
        p.stats.set(S.FOOD_SICKNESS, 50.0)
        hour(p, corpse_count=25, corpse_defence=100)
        self.assertAlmostEqual(p.stats.get(S.FOOD_SICKNESS), 50 - 16.2, places=3)

    def test_resilient_with_a_defence_of_100_still_decays(self):
        p = player()
        p.stats.set(S.FOOD_SICKNESS, 50.0)
        hour(p, corpse_count=25, corpse_defence=100, traits=frozenset({trait_k.RESILIENT_ID}))
        self.assertAlmostEqual(p.stats.get(S.FOOD_SICKNESS), 50 - 16.2, places=3)


class CountTests(unittest.TestCase):
    """Spec 14, Corpse sickness: the count the player stands in."""

    def test_the_apartment_and_the_hallway_share_one_count(self):
        gm = GameManager()
        add_bodies(gm, "zone_home", 3)
        add_bodies(gm, "zone_building", 4)
        self.assertEqual(corpse_sickness.corpse_count(gm.world, "zone_home"), 7)
        self.assertEqual(corpse_sickness.corpse_count(gm.world, "zone_building"), 7)

    def test_a_zone_with_no_building_counts_only_its_own(self):
        gm = GameManager()
        add_bodies(gm, "zone_street", 2)
        add_bodies(gm, "zone_building", 5)
        self.assertEqual(corpse_sickness.corpse_count(gm.world, "zone_street"), 2)

    def test_the_corner_store_is_a_building_of_its_own(self):
        gm = GameManager()
        add_bodies(gm, "zone_bodega", 3)
        add_bodies(gm, "zone_building", 3)
        self.assertEqual(corpse_sickness.corpse_count(gm.world, "zone_bodega"), 3)

    def test_skeletons_count(self):
        gm = GameManager()
        add_bodies(gm, "zone_street", 4, skeletons=4)
        self.assertEqual(corpse_sickness.corpse_count(gm.world, "zone_street"), 4)

    def test_the_count_is_capped_at_25(self):
        gm = GameManager()
        add_bodies(gm, "zone_street", 40)
        self.assertEqual(corpse_sickness.corpse_count(gm.world, "zone_street"), 25)


class DefenceTests(unittest.TestCase):
    """Spec 14, Corpse sickness: the best defence among worn items."""

    def test_the_best_corpse_sickness_defence_of_the_worn_items(self):
        p = player()
        self.assertEqual(corpse_sickness.corpse_defence(p), 0)
        mask, shirt = ITEMS["item_dust_mask"], ITEMS["item_tshirt"]
        assert isinstance(mask, ClothingItem) and isinstance(shirt, ClothingItem)
        for item in (mask, shirt):
            p.worn[item.body_location] = ItemEntity(item=item)
        self.assertGreater(mask.corpse_sickness_defense, 0)
        self.assertEqual(corpse_sickness.corpse_defence(p), mask.corpse_sickness_defense)


class SmellTests(unittest.TestCase):
    """Spec 14, Corpse sickness: the fact when the count first passes five."""

    SMELL = "The smell of the dead hangs thick here."

    def wait(self, gm: GameManager) -> list[str]:
        return simulate(gm, WaitAction(duration=Duration(minutes=10)))

    def test_the_smell_is_reported_once_per_zone(self):
        gm = zombie_game("zone_street")
        add_bodies(gm, "zone_street", 6)
        first = self.wait(gm)
        second = self.wait(gm)
        self.assertEqual(first.count(self.SMELL), 1)
        self.assertNotIn(self.SMELL, second)
        self.assertEqual(gm.world.smell_zone_id, "zone_street")

    def test_five_bodies_have_no_smell(self):
        gm = zombie_game("zone_street")
        add_bodies(gm, "zone_street", 5)
        self.assertNotIn(self.SMELL, self.wait(gm))
        self.assertIsNone(gm.world.smell_zone_id)

    def test_it_is_reported_again_after_the_count_falls_and_rises(self):
        gm = zombie_game("zone_street")
        add_bodies(gm, "zone_street", 6)
        self.wait(gm)
        del gm.world.corpses["c6"]
        self.wait(gm)
        add_bodies(gm, "zone_street", 1)
        self.assertIn(self.SMELL, self.wait(gm))

    def test_an_hour_among_25_bodies_makes_the_player_sick(self):
        gm = zombie_game("zone_street")
        add_bodies(gm, "zone_street", 25)
        gm.player.stats.set(S.FOOD_SICKNESS, 0.0)
        simulate(gm, WaitAction(duration=Duration(minutes=60)))
        self.assertAlmostEqual(gm.player.stats.get(S.FOOD_SICKNESS), 22.68, delta=0.5)


if __name__ == "__main__":
    unittest.main()
