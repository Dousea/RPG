"""Spec 14, Searching and looting: SEARCH, TAKE ... from a corpse and the pocket tables."""

import random
import unittest
from unittest import mock

from data import traits as trait_k
from data import zombie_loot
from data.items import ITEMS
from data.loot_catalogue import LOOT_CATALOGUE, LOOT_KIND_MODIFIERS
from managers import loot
from managers.game import GameManager
from modules.action.parser import parse_action_line
from modules.action.types import SearchAction, TakeAction
from modules.body import BodyLocation
from modules.entity.corpse import CorpseEntity
from modules.entity.item import ItemEntity
from modules.stats import CharacterStat
from tests.support import ScriptedRandom, load_pack, simulate
from tests.test_simulation import zombie_game

NAME = "Orton"


def ids(entities) -> list[str]:
    return [e.item.id for e in entities]


def body(**fields) -> CorpseEntity:
    values = {
        "corpse_id": "c1",
        "zone_id": "zone_street",
        "gap": 1.0,
        "female": False,
        "outfit": "generic01",
        "died_at": 0,
        "rot_at_death": 1,
    }
    values.update(fields)
    return CorpseEntity(**values)


def with_body(*item_ids: str, **fields) -> tuple[GameManager, CorpseEntity]:
    gm = zombie_game()
    corpse = body(**fields)
    corpse.contents = [ItemEntity(item=ITEMS[item_id]) for item_id in item_ids]
    gm.world.corpses["c1"] = corpse
    return gm, corpse


def minutes_of(gm: GameManager, *actions, rng=None) -> tuple[int, list[str]]:
    before = gm.narrative.minutes
    facts = simulate(gm, *actions, rng=rng or random.Random(1))
    return gm.narrative.minutes - before, facts


class ParsingTests(unittest.TestCase):
    """Spec 14, Searching and looting: the verbs."""

    def test_search_takes_a_corpse(self):
        self.assertEqual(parse_action_line("SEARCH c3"), SearchAction(target_name="c3"))

    def test_take_gains_a_from_source(self):
        self.assertEqual(
            parse_action_line("TAKE jacket from c3"),
            TakeAction(item_name="jacket", from_name="c3"),
        )

    def test_a_plain_take_has_no_source(self):
        self.assertEqual(parse_action_line("TAKE Crowbar"), TakeAction(item_name="Crowbar"))

    def test_a_take_from_with_no_item_is_a_parse_failure(self):
        self.assertTrue(hasattr(parse_action_line("TAKE from c3"), "reason"))

    def test_search_needs_a_target(self):
        self.assertTrue(hasattr(parse_action_line("SEARCH"), "reason"))


class PocketChanceTests(unittest.TestCase):
    """Spec 14, Zombie loot (p = chance x modifier / 100); spec 25, Rooms (a corpse container holds 12 kg)."""

    def test_the_chance_is_the_table_chance_times_the_modifier_over_a_hundred(self):
        cases = {
            (0.1, "medical"): 0.0006,
            (50, "container"): 0.30,
            (20, "literature"): 0.12,
            (10, "other"): 0.08,
            (10, "food"): 0.08,
            (10, "key"): 0.04,
            (10, "weapon"): 0.06,
        }
        for (chance, kind), expected in cases.items():
            with self.subTest(chance=chance, kind=kind):
                self.assertAlmostEqual(loot.drop_chance(chance, kind), expected)

    def test_the_modifiers_are_the_apocalypse_values(self):
        for kind, expected in {
            "other": 0.8,
            "food": 0.8,
            "key": 0.4,
            "medical": 0.6,
            "literature": 0.6,
            "container": 0.6,
            "weapon": 0.6,
            "media": 0.6,
            "clothing": 0.6,
        }.items():
            with self.subTest(kind=kind):
                self.assertEqual(LOOT_KIND_MODIFIERS[kind], expected)

    def test_the_roll_is_below_chance_x_100_x_modifier_out_of_ten_thousand(self):
        with mock.patch.dict(zombie_loot.DEFAULT_LOOT_TABLES, {"male": (("pills", 0.1),)}):
            found = [
                "item_painkillers"
                in ids(loot.roll_pockets(body(), ScriptedRandom(randrange=[roll])))
                for roll in (0, 5, 6, 9999)
            ]
        self.assertEqual(found, [True, True, False, False])

    def test_today_only_painkillers_drop_from_the_default_table_at_six_in_ten_thousand(self):
        rng = random.Random(15)
        draws = 200000
        hits = sum(
            1 for _ in range(draws) if "item_painkillers" in ids(loot.roll_pockets(body(), rng))
        )
        self.assertAlmostEqual(hits / draws, 0.0006, delta=0.0003)

    def test_a_body_holding_12_kg_has_no_room_for_pocket_items(self):
        full = body()
        full.contents = [ItemEntity(item=ITEMS["item_plank"]) for _ in range(4)]
        self.assertEqual(loot.roll_pockets(full, ScriptedRandom(randrange=[0])), [])

    def test_a_body_holding_9_kg_still_has_room_in_its_12_kg_container(self):
        loaded = body()
        loaded.contents = [ItemEntity(item=ITEMS["item_plank"]) for _ in range(3)]
        found = loot.roll_pockets(loaded, ScriptedRandom(randrange=[0]))
        self.assertIn("item_painkillers", [e.item.id for e in found])

    def test_a_female_body_rolls_the_female_table(self):
        with mock.patch.dict(
            zombie_loot.DEFAULT_LOOT_TABLES,
            {"female": (("kitchen_knife", 100.0),), "male": ()},
        ):
            self.assertEqual(
                loot.roll_pockets(body(female=True), ScriptedRandom(randrange=[0]))[0].item.id,
                "item_kitchen_knife",
            )
            self.assertEqual(
                loot.roll_pockets(body(female=False), ScriptedRandom(randrange=[0])), []
            )

    def test_an_outfit_table_is_rolled_before_the_default_table(self):
        order = loot.roll_pockets(
            body(outfit="construction_worker"), ScriptedRandom(randrange=[0, 0])
        )
        self.assertEqual(ids(order)[0], "item_nails")
        self.assertEqual(ids(order)[-1], "item_painkillers")

    def test_nails_come_at_twelve_percent_for_a_construction_worker(self):
        kind = LOOT_CATALOGUE["nails"][1]
        self.assertAlmostEqual(loot.drop_chance(20, kind), 0.12)

    def test_a_skeleton_gets_no_pocket_roll(self):
        class Boom(random.Random):
            def randrange(self, *args, **kwargs):
                raise AssertionError("a skeleton is not rolled")

        self.assertEqual(loot.roll_pockets(body(skeleton=True), Boom()), [])

    def test_an_item_outside_the_catalogue_is_skipped_without_a_roll(self):
        with mock.patch.dict(
            zombie_loot.DEFAULT_LOOT_TABLES,
            {"male": (("wallet_male", 50.0),)},
        ):
            self.assertEqual(loot.roll_pockets(body(), ScriptedRandom(randrange=[0])), [])


class SearchTests(unittest.TestCase):
    """Spec 14, `SEARCH <corpse>`."""

    def test_a_search_costs_a_minute_and_names_what_the_body_holds(self):
        gm, corpse = with_body("item_jacket_police", "item_kitchen_knife")
        minutes, facts = minutes_of(gm, SearchAction(target_name="c1"))
        self.assertEqual(minutes, 1)
        self.assertTrue(corpse.searched)
        self.assertIn(f"{NAME} goes through c1: a police jacket, a kitchen knife.", facts)

    def test_the_pockets_are_rolled_once_and_land_in_the_contents(self):
        gm, corpse = with_body("item_tshirt")
        minutes_of(gm, SearchAction(target_name="c1"), rng=ScriptedRandom(randrange=[0]))
        self.assertEqual(ids(corpse.contents)[0], "item_tshirt")
        self.assertEqual(ids(corpse.contents)[-1], "item_painkillers")

    def test_a_second_search_is_refused(self):
        gm, corpse = with_body("item_tshirt")
        minutes_of(gm, SearchAction(target_name="c1"))
        minutes, facts = minutes_of(gm, SearchAction(target_name="c1"))
        self.assertEqual(minutes, 0)
        self.assertIn(
            f"Refused: {NAME} can't search c1: {NAME} has already been through c1.", facts
        )

    def test_corpse_means_the_nearest(self):
        gm, near = with_body()
        far = body(corpse_id="c2", gap=6.0)
        gm.world.corpses["c2"] = far
        near.gap = 5.0
        minutes_of(gm, SearchAction(target_name="corpse"))
        self.assertTrue(far.searched is False and near.searched)

    def test_an_unknown_corpse_is_refused(self):
        gm, _ = with_body()
        minutes, facts = minutes_of(gm, SearchAction(target_name="c9"))
        self.assertEqual(minutes, 0)
        self.assertTrue(facts[0].startswith("Refused"))

    def test_a_sleeper_cannot_search(self):
        gm, corpse = with_body()
        gm.player.asleep = True
        minutes, facts = minutes_of(gm, SearchAction(target_name="c1"))
        self.assertEqual(minutes, 0)
        self.assertIn("asleep", facts[0])
        self.assertFalse(corpse.searched)

    def test_a_body_too_far_to_see_is_refused(self):
        gm, corpse = with_body(gap=60.0)
        minutes, facts = minutes_of(gm, SearchAction(target_name="c1"))
        self.assertEqual(minutes, 0)
        self.assertFalse(corpse.searched)

    def test_a_far_body_is_walked_up_to_first(self):
        gm, corpse = with_body(gap=9.0)
        minutes, facts = minutes_of(gm, SearchAction(target_name="c1"))
        self.assertEqual(minutes, 3)
        self.assertEqual(corpse.gap, 1.0)
        self.assertTrue(corpse.searched)

    def test_a_body_that_rises_on_the_way_is_gone_when_the_player_arrives(self):
        gm, corpse = with_body(gap=9.0, fake_dead=True, died_at=-200)
        minutes, facts = minutes_of(gm, SearchAction(target_name="c1"))
        self.assertNotIn("c1", gm.world.corpses)
        self.assertFalse(any("goes through" in fact for fact in facts))
        self.assertIn("A body on the ground lurches to its feet.", facts)

    def test_the_player_own_body_is_searched_already(self):
        gm, corpse = with_body(risen_from_player=True, searched=True)
        minutes, facts = minutes_of(gm, SearchAction(target_name="c1"))
        self.assertEqual(minutes, 0)


class TakeFromTests(unittest.TestCase):
    """Spec 14, `TAKE <item> from <corpse>`."""

    def searched(self, *item_ids: str) -> tuple[GameManager, CorpseEntity]:
        gm, corpse = with_body(*item_ids, searched=True)
        gm.player.stats.set(CharacterStat.UNHAPPINESS, 0.0)
        return gm, corpse

    def test_the_item_moves_to_the_inventory_and_costs_a_minute(self):
        gm, corpse = self.searched("item_jacket_police", "item_kitchen_knife")
        minutes, facts = minutes_of(gm, TakeAction(item_name="police jacket", from_name="c1"))
        self.assertEqual(minutes, 1)
        self.assertEqual([e.item.id for e in corpse.contents], ["item_kitchen_knife"])
        self.assertEqual(gm.player.inventory[-1].item.id, "item_jacket_police")
        self.assertIn(f"{NAME} takes the dead man's police jacket.", facts)

    def test_the_fact_names_the_dead_woman_for_a_female_body(self):
        gm, corpse = self.searched("item_jacket_police")
        corpse.female = True
        _, facts = minutes_of(gm, TakeAction(item_name="jacket", from_name="c1"))
        self.assertIn(f"{NAME} takes the dead woman's police jacket.", facts)

    def test_clothing_keeps_its_holes_and_is_not_worn(self):
        gm, corpse = self.searched("item_jacket_police")
        corpse.contents[0].holes = set(list(corpse.contents[0].item.covers)[:2])  # type: ignore[union-attr]
        holes = set(corpse.contents[0].holes)
        minutes_of(gm, TakeAction(item_name="jacket", from_name="c1"))
        self.assertEqual(gm.player.inventory[-1].holes, holes)
        self.assertNotIn(BodyLocation.JACKET, gm.player.worn)

    def test_an_unsearched_body_is_refused(self):
        gm, corpse = with_body("item_jacket_police")
        minutes, facts = minutes_of(gm, TakeAction(item_name="jacket", from_name="c1"))
        self.assertEqual(minutes, 0)
        self.assertTrue(facts[0].startswith("Refused"))
        self.assertIn(f"{NAME} hasn't been through c1 yet.", facts[0])
        self.assertEqual(len(corpse.contents), 1)

    def test_an_item_the_body_does_not_hold_is_refused(self):
        gm, _ = self.searched("item_jacket_police")
        minutes, facts = minutes_of(gm, TakeAction(item_name="hammer", from_name="c1"))
        self.assertEqual(minutes, 0)
        self.assertTrue(facts[0].startswith("Refused"))

    def test_a_full_inventory_is_refused(self):
        gm, corpse = self.searched("item_jacket_police")
        load_pack(gm.player, 49.5)
        minutes, facts = minutes_of(gm, TakeAction(item_name="jacket", from_name="c1"))
        self.assertEqual(minutes, 0)
        self.assertIn("can't carry any more", facts[0])
        self.assertEqual(len(corpse.contents), 1)

    def test_a_sleeper_cannot_take(self):
        gm, _ = self.searched("item_jacket_police")
        gm.player.asleep = True
        minutes, _ = minutes_of(gm, TakeAction(item_name="jacket", from_name="c1"))
        self.assertEqual(minutes, 0)

    def unhappiness_gain(self, *traits: str) -> float:
        gm, _ = self.searched("item_jacket_police")
        control = zombie_game()
        control.current_location.entities.append(ItemEntity(item=ITEMS["item_hammer"]))
        for game in (gm, control):
            game.player.traits.extend(traits)
            game.player.stats.set(CharacterStat.UNHAPPINESS, 0.0)
        minutes_of(gm, TakeAction(item_name="jacket", from_name="c1"))
        minutes_of(control, TakeAction(item_name="hammer"))
        return gm.player.stats.get(CharacterStat.UNHAPPINESS) - control.player.stats.get(
            CharacterStat.UNHAPPINESS
        )

    def test_each_item_taken_adds_one_point_eight_unhappiness(self):
        self.assertAlmostEqual(self.unhappiness_gain(), 1.8)

    def test_cowardly_doubles_it_brave_halves_it_and_desensitized_removes_it(self):
        self.assertAlmostEqual(self.unhappiness_gain(trait_k.COWARDLY_ID), 3.6)
        self.assertAlmostEqual(self.unhappiness_gain(trait_k.BRAVE_ID), 0.9)
        self.assertAlmostEqual(self.unhappiness_gain(trait_k.DESENSITIZED_ID), 0.0)

    def test_searching_adds_no_unhappiness(self):
        gm, corpse = with_body("item_jacket_police")
        control = zombie_game()
        control.current_location.entities.append(ItemEntity(item=ITEMS["item_hammer"]))
        for game in (gm, control):
            game.player.stats.set(CharacterStat.UNHAPPINESS, 0.0)
        minutes_of(gm, SearchAction(target_name="c1"))
        minutes_of(control, TakeAction(item_name="hammer"))
        self.assertAlmostEqual(
            gm.player.stats.get(CharacterStat.UNHAPPINESS),
            control.player.stats.get(CharacterStat.UNHAPPINESS),
        )


if __name__ == "__main__":
    unittest.main()
