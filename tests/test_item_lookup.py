"""carrying-and-loot: Naming an item: one lookup that asks "which one?" by the words that set items apart."""

import re
import unittest
from pathlib import Path

from data.items import ITEMS
from managers import naming
from managers.context import ContextBuilder
from managers.corpses.search import find_content
from managers.game import GameManager
from managers.validator import Accepted, ActionValidator, Rejected, ValidationResult
from managers.world.item_ids import stamp_world
from modules.action.parser import available_verbs
from modules.action.pins import Pinned
from modules.action.schema import build_plan_schema, parse_plan
from modules.action.types import EquipAction, PutAction, TakeAction
from modules.character.equipment import CharacterArmorSlot
from modules.entity.item import ItemEntity
from modules.resolution import HeldItem, Transfer
from tests.corpses.test_loot import with_body
from tests.test_plan_schema import branches, enum_of, fits

BAT = "item_baseball_bat"
KNIFE = "item_kitchen_knife"
SHIRT = "item_tshirt"
WIPES = "item_alcohol_wipes"


def thing(item_id: str, **fields) -> ItemEntity:
    return ItemEntity(item=ITEMS[item_id], **fields)


def broken_bat() -> ItemEntity:
    return thing(BAT, condition=0)


class LookupTests(unittest.TestCase):
    """carrying-and-loot: Naming an item: the lookup."""

    def test_the_deleted_method_has_no_callers(self):
        self.assertFalse(hasattr(GameManager, "_find_item_entity"))
        root = Path(__file__).resolve().parent.parent
        for folder in ("managers", "adapters", "modules", "data", "tests"):
            for path in (root / folder).rglob("*.py"):
                if path.name == "test_item_lookup.py":
                    continue
                self.assertNotIn("_find_item_entity", path.read_text(), path)

    def test_a_single_match_by_name_or_id_ignores_case_quotes_and_articles(self):
        knife = thing(KNIFE)
        for name in ("Kitchen Knife", "kitchen knife", "item_kitchen_knife", "the Kitchen Knife"):
            self.assertIs(naming.find_named([knife], name), knife, name)
        for name in ('"my kitchen knife."', "your kitchen knife"):
            self.assertIs(naming.find_named([knife], name), knife, name)
        self.assertIsNone(naming.find_named([knife], "hammer"))

    def test_the_words_are_the_condition_and_the_wetness(self):
        self.assertEqual(naming.describing_words(thing(SHIRT)), ("intact",))
        self.assertEqual(naming.describing_words(thing(SHIRT, wetness=50)), ("intact", "wet"))
        self.assertEqual(naming.describing_words(broken_bat()), ("broken",))

    def test_uses_left_set_items_apart_for_the_question(self):
        few, many = thing(WIPES, uses=3), thing(WIPES, uses=5)
        found = naming.find_named([few, many], "Alcohol Wipes")
        assert isinstance(found, list)
        self.assertEqual([id(e) for e in found], [id(few), id(many)])
        self.assertEqual(naming.describing_words(few), naming.describing_words(many))

    def test_equal_uses_left_give_the_first(self):
        first, second = thing(WIPES, uses=3), thing(WIPES, uses=3)
        self.assertIs(naming.find_named([first, second], "Alcohol Wipes"), first)

    def test_uses_candidates_carry_ids_and_the_question_has_no_number(self):
        few, many = thing(WIPES, uses=3), thing(WIPES, uses=5)
        few.instance_id, many.instance_id = "i1", "i2"
        candidates = naming.item_candidates([few, many])
        self.assertEqual([c.id for c in candidates], ["i1", "i2"])
        self.assertIn("3 left", candidates[0].description)
        self.assertIn("5 left", candidates[1].description)
        question = naming.which_one([few, many])
        self.assertIn("Alcohol Wipes", question)
        self.assertIsNone(re.search(r"\d", question))

    def test_identical_items_give_the_first(self):
        first, second = thing(KNIFE), thing(KNIFE)
        self.assertIs(naming.find_named([first, second], "Kitchen Knife"), first)

    def test_differing_items_give_the_candidates(self):
        bad, good = broken_bat(), thing(BAT)
        found = naming.find_named([bad, good], "Baseball Bat")
        assert isinstance(found, list)
        self.assertEqual([id(e) for e in found], [id(bad), id(good)])

    def test_a_word_before_or_after_the_name_picks_the_item_with_it(self):
        bad, good = broken_bat(), thing(BAT)
        for name in ("broken Baseball Bat", "Baseball Bat (broken)", "the broken baseball bat"):
            self.assertIs(naming.find_named([good, bad], name), bad, name)
        self.assertIs(naming.find_named([bad, good], "good Baseball Bat"), good)

    def test_a_word_no_item_has_matches_nothing(self):
        self.assertIsNone(naming.find_named([thing(BAT)], "broken Baseball Bat"))

    def test_the_first_of_several_is_taken_by_a_describing_caller(self):
        bad, good = broken_bat(), thing(BAT)
        self.assertIs(naming.first_named([bad, good], "Baseball Bat"), bad)

    def test_three_bats_get_three_labels_and_each_label_picks_its_bat(self):
        wet_good, good, wet_broken = (
            thing(BAT, wetness=50),
            thing(BAT),
            thing(BAT, condition=0, wetness=50),
        )
        bats = [wet_good, good, wet_broken]
        found = naming.find_named(bats, "Baseball Bat")
        assert isinstance(found, list)
        self.assertEqual(
            naming.qualified_names(found),
            ["good wet Baseball Bat", "good Baseball Bat", "broken Baseball Bat"],
        )
        self.assertIs(naming.find_named(bats, "good wet Baseball Bat"), wet_good)
        self.assertIs(naming.find_named(bats, "Baseball Bat (good, wet)"), wet_good)
        self.assertIs(naming.find_named(bats, "good Baseball Bat"), good)
        self.assertIs(naming.find_named(bats, "broken Baseball Bat"), wet_broken)

    def test_scene_names_are_distinct_and_offer_each_label(self):
        bats = [thing(BAT, wetness=50), thing(BAT), thing(BAT, condition=0, wetness=50)]
        self.assertEqual(
            naming.scene_names(bats),
            ("Baseball Bat", "good wet Baseball Bat", "good Baseball Bat", "broken Baseball Bat"),
        )

    def test_a_dry_and_a_wet_shirt_are_told_apart_by_the_wet_word(self):
        dry, wet = thing(SHIRT), thing(SHIRT, wetness=50)
        found = naming.find_named([dry, wet], "T-shirt")
        assert isinstance(found, list)
        self.assertEqual(naming.which_one(found), "Which one: intact T-shirt or wet T-shirt?")
        self.assertIs(naming.find_named([dry, wet], "wet T-shirt"), wet)
        self.assertIs(naming.find_named([dry, wet], "intact T-shirt"), dry)

    def test_a_body_exact_name_asks_and_a_contained_name_still_falls_back(self):
        gm, corpse = with_body(BAT, KNIFE)
        corpse.contents.append(broken_bat())
        found = find_content(corpse, "Baseball Bat")
        self.assertIsInstance(found, list)
        self.assertIs(find_content(corpse, "knife"), corpse.contents[1])


def chosen(result: ValidationResult) -> ItemEntity:
    """The one item an accepted hold, wear or similar action resolved to."""
    assert isinstance(result, Accepted), result
    return result.expect(HeldItem).entity


def taken(result: ValidationResult) -> ItemEntity:
    """The one item an accepted take resolved to."""
    assert isinstance(result, Accepted), result
    (entity,) = result.expect(Transfer).entities
    return entity


class WhichOneTests(unittest.TestCase):
    """carrying-and-loot: Naming an item: the which-one refusal."""

    def setUp(self):
        self.gm = GameManager()
        self.validator = ActionValidator(self.gm)

    def reason(self, action) -> str:
        result = self.validator.validate(action)
        assert isinstance(result, Rejected), result
        return result.reason

    def test_two_bats_carried_ask_which_one(self):
        self.gm.player.inventory.extend([broken_bat(), thing(BAT)])
        reason = self.reason(EquipAction(item_name="Baseball Bat"))
        self.assertEqual(reason, "Which one: broken Baseball Bat or good Baseball Bat?")
        self.assertIsNone(re.search(r"\d", reason))

    def test_a_qualified_name_picks_the_broken_one(self):
        bad = broken_bat()
        self.gm.player.inventory.extend([thing(BAT), bad])
        for name in ("broken Baseball Bat", "Baseball Bat (broken)"):
            result = self.validator.validate(EquipAction(item_name=name))
            self.assertIsInstance(result, Rejected)
            assert isinstance(result, Rejected)
            self.assertEqual(result.reason, "The Baseball Bat is broken.")

    def test_a_qualified_name_picks_the_good_one(self):
        good = thing(BAT)
        self.gm.player.inventory.extend([broken_bat(), good])
        for name in ("good Baseball Bat", "Baseball Bat (good)"):
            result = self.validator.validate(EquipAction(item_name=name))
            self.assertIs(chosen(result), good)

    def test_two_identical_knives_pick_the_first_without_a_question(self):
        first, second = thing(KNIFE), thing(KNIFE)
        self.gm.player.inventory.extend([first, second])
        result = self.validator.validate(EquipAction(item_name="Kitchen Knife"))
        self.assertIs(chosen(result), first)

    def test_a_wet_and_a_dry_shirt_ask_with_the_wetness_word(self):
        self.gm.player.inventory.extend([thing(SHIRT), thing(SHIRT, wetness=50)])
        reason = self.reason(EquipAction(item_name="T-shirt"))
        self.assertEqual(reason, "Which one: intact T-shirt or wet T-shirt?")

    def test_the_floor_asks(self):
        self.gm.current_location.entities.extend([broken_bat(), thing(BAT)])
        reason = self.reason(TakeAction(item_name="Baseball Bat"))
        self.assertEqual(reason, "Which one: broken Baseball Bat or good Baseball Bat?")
        picked = self.validator.validate(TakeAction(item_name="Baseball Bat (broken)"))
        self.assertTrue(taken(picked).broken)

    def test_a_bag_asks(self):
        bag = thing("item_duffel_bag")
        bag.contents.extend([broken_bat(), thing(BAT)])
        self.gm.player.equipment[CharacterArmorSlot.SHOULDERS] = bag
        action = TakeAction(item_name="Baseball Bat", from_name="Duffel Bag")
        self.assertEqual(
            self.reason(action), "Which one: broken Baseball Bat or good Baseball Bat?"
        )
        picked = self.validator.validate(
            TakeAction(item_name="broken Baseball Bat", from_name="Duffel Bag")
        )
        self.assertTrue(taken(picked).broken)

    def test_an_opened_container_asks(self):
        self.gm.player.current_location_id = "zone_home"
        self.gm.player.current_room = "kitchen"
        counter = self.gm.current_location.rooms["kitchen"].containers[0]
        counter.opened = True
        counter.contents[:] = [broken_bat(), thing(BAT)]
        action = TakeAction(item_name="Baseball Bat", from_name=counter.name)
        self.assertEqual(
            self.reason(action), "Which one: broken Baseball Bat or good Baseball Bat?"
        )
        picked = self.validator.validate(
            TakeAction(item_name="Baseball Bat (broken)", from_name=counter.name)
        )
        self.assertTrue(taken(picked).broken)

    def test_a_searched_body_asks(self):
        gm, corpse = with_body(BAT)
        corpse.contents.append(broken_bat())
        corpse.searched = True
        validator = ActionValidator(gm)
        action = TakeAction(item_name="Baseball Bat", from_name="c1")
        result = validator.validate(action)
        assert isinstance(result, Rejected)
        self.assertEqual(result.reason, "Which one: good Baseball Bat or broken Baseball Bat?")
        picked = validator.validate(TakeAction(item_name="broken Baseball Bat", from_name="c1"))
        self.assertTrue(taken(picked).broken)

    def test_a_pin_on_an_item_elsewhere_never_takes_the_bodys_copy(self):
        gm, corpse = with_body(BAT)
        corpse.searched = True
        stamp_world(gm.world, gm.player)
        elsewhere = Pinned("Baseball Bat", "item", "i999")
        result = ActionValidator(gm).validate(TakeAction(item_name=elsewhere, from_name="c1"))
        self.assertIsInstance(result, Rejected)
        own = Pinned("Baseball Bat", "item", corpse.contents[0].instance_id)
        result = ActionValidator(gm).validate(TakeAction(item_name=own, from_name="c1"))
        self.assertIs(taken(result), corpse.contents[0])

    def test_putting_a_carried_item_asks(self):
        self.gm.player.inventory.extend([thing("item_duffel_bag"), broken_bat(), thing(BAT)])
        reason = self.reason(PutAction(item_name="Baseball Bat", target_name="Duffel Bag"))
        self.assertEqual(reason, "Which one: broken Baseball Bat or good Baseball Bat?")


class SceneChoicesTests(unittest.TestCase):
    """llm-contract: Scene filtering: a name held by items that differ is offered qualified."""

    def setUp(self):
        self.gm = GameManager()
        self.builder = ContextBuilder(self.gm)

    def test_differing_duplicates_are_offered_bare_and_qualified(self):
        self.gm.player.inventory.extend([broken_bat(), thing(BAT)])
        carried = self.builder.scene_choices().carried
        self.assertEqual(
            sorted(carried),
            ["Apartment Key", "Baseball Bat", "broken Baseball Bat", "good Baseball Bat"],
        )

    def test_unique_names_and_identical_duplicates_stay_bare(self):
        self.gm.player.inventory.extend([thing(KNIFE), thing(KNIFE), thing("item_crowbar")])
        self.assertEqual(
            self.builder.scene_choices().carried, ("Apartment Key", "Kitchen Knife", "Crowbar")
        )

    def test_a_wet_and_a_dry_shirt_are_offered_with_the_wetness_word(self):
        self.gm.player.inventory.extend([thing(SHIRT), thing(SHIRT, wetness=50)])
        carried = self.builder.scene_choices().carried
        self.assertIn("wet T-shirt", carried)
        self.assertIn("T-shirt", carried)

    def test_the_parser_prompt_shows_the_word_only_for_differing_duplicates(self):
        self.gm.player.inventory.extend([thing(KNIFE), thing(KNIFE), broken_bat(), thing(BAT)])
        inventory = self.builder.build_parser_prompt("look").split("[INVENTORY]\n")[1]
        inventory = inventory.split("\n\n[")[0]
        self.assertIn(" - Baseball Bat (broken)", inventory)
        self.assertIn(" - Baseball Bat (good)", inventory)
        self.assertIn(" - Kitchen Knife x2", inventory)

    def test_the_parser_prompt_shows_the_word_for_the_floor(self):
        self.gm.current_location.entities.extend([thing(SHIRT), thing(SHIRT, wetness=50)])
        prompt = self.builder.build_parser_prompt("look")
        here = prompt.split("[ITEMS HERE]\n")[1].split("\n\n[")[0]
        self.assertIn(" - T-shirt (intact)", here)
        self.assertIn(" - T-shirt (intact, wet)", here)


class QualifiedPlanTests(unittest.TestCase):
    """llm-contract: Plans: a qualified item name."""

    def test_the_schema_accepts_a_qualified_name_and_the_plan_reads_it(self):
        gm = GameManager()
        gm.player.inventory.extend([broken_bat(), thing(BAT)])
        builder = ContextBuilder(gm)
        schema = build_plan_schema(
            available_verbs(builder.scene_keys()), builder.scene_choices(), 5
        )
        equip = branches(schema)["EQUIP"]
        self.assertIn("broken Baseball Bat", enum_of(equip, "item"))
        entry = {"verb": "EQUIP", "item": "broken Baseball Bat"}
        self.assertTrue(fits(equip, entry))
        actions, failures = parse_plan({"actions": [entry]})
        self.assertEqual((actions, failures), ([EquipAction(item_name="broken Baseball Bat")], []))
