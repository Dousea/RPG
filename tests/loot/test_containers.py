"""carrying-and-loot: Verbs: SEARCH of a room or container, TAKE and PUT with containers."""

import random
import unittest

from data.items import ITEMS
from managers.game import GameManager
from managers.simulation import SimulationCore
from modules.action.types import MoveAction, PutAction, SearchAction, TakeAction
from modules.entity.corpse import CorpseEntity
from modules.entity.item import ItemEntity
from tests.support import ScriptedRandom, simulate

NAME = "Orton"


def named(gm: GameManager, zone_id: str, name: str):
    for room in gm.world.locations[zone_id].rooms.values():
        for container in room.containers:
            if container.name == name:
                return container
    raise AssertionError(name)


def ids_in(container) -> list[str]:
    return [e.item.id for e in container.contents]


def elapsed(gm: GameManager, *actions, rng=None) -> tuple[int, list[str]]:
    before = gm.narrative.minutes
    facts = simulate(gm, *actions, rng=rng or random.Random(5))
    return gm.narrative.minutes - before, facts


def refused(facts: list[str], reason: str) -> bool:
    """Whether the only fact is a refusal that ends with `reason`."""
    return len(facts) == 1 and facts[0].startswith("Refused: ") and facts[0].endswith(reason)


def in_room(room_id: str) -> GameManager:
    gm = GameManager()
    gm.player.current_room = room_id
    return gm


class SearchRoomTests(unittest.TestCase):
    """carrying-and-loot: `SEARCH <room>`: one minute for each unopened container, in layout order."""

    def test_a_room_of_three_unopened_containers_costs_three_minutes(self):
        gm = in_room("bedroom")
        minutes, facts = elapsed(gm, SearchAction(target_name="bedroom"))
        self.assertEqual(minutes, 3)
        opened = [c.opened for c in gm.world.locations["zone_home"].rooms["bedroom"].containers]
        self.assertEqual(opened, [True, True, True])
        order = [i for i, f in enumerate(facts) if "goes through the" in f]
        names = [
            facts[i].split("goes through the ")[1].split(":")[0].split(" and")[0] for i in order
        ]
        self.assertEqual(names, ["wardrobe", "dresser", "bedside table"])

    def test_searching_a_room_elsewhere_costs_a_minute_to_get_there_and_moves_the_player(self):
        gm = GameManager()
        minutes, _ = elapsed(gm, SearchAction(target_name="bathroom"))
        self.assertEqual(minutes, 1 + 2)
        self.assertEqual(gm.player.current_room, "bathroom")
        self.assertEqual(gm.player.current_place, "bathroom")

    def test_an_interruption_after_the_second_container_leaves_the_third_closed(self):
        gm = in_room("bedroom")
        core = SimulationCore(gm, rng=random.Random(5))
        original = core._spend
        calls: list[int] = []

        def spend(*args, **kwargs):
            result = original(*args, **kwargs)
            calls.append(1)
            if len(calls) == 2:
                core._interruption = "attacked"
            return result

        core._spend = spend  # type: ignore[method-assign]
        core.resolve([SearchAction(target_name="bedroom")])
        opened = [c.opened for c in gm.world.locations["zone_home"].rooms["bedroom"].containers]
        self.assertEqual(opened, [True, True, False])

    def test_a_room_already_gone_through_is_refused_without_time(self):
        gm = in_room("bedroom")
        elapsed(gm, SearchAction(target_name="bedroom"))
        minutes, facts = elapsed(gm, SearchAction(target_name="bedroom"))
        self.assertEqual(minutes, 0)
        self.assertTrue(refused(facts, f"{NAME} has already been through the bedroom."))

    def test_a_second_search_opens_only_what_is_still_closed(self):
        gm = in_room("bedroom")
        elapsed(gm, SearchAction(target_name="dresser"))
        minutes, _ = elapsed(gm, SearchAction(target_name="bedroom"))
        self.assertEqual(minutes, 2)

    def test_a_search_while_carrying_a_body_is_refused(self):
        gm = in_room("bedroom")
        gm.player.carrying_corpse = "c1"
        gm.world.corpses["c1"] = CorpseEntity(
            corpse_id="c1",
            zone_id="zone_home",
            gap=0.0,
            female=False,
            outfit="generic01",
            died_at=0,
            rot_at_death=1,
        )
        minutes, facts = elapsed(gm, SearchAction(target_name="bedroom"))
        self.assertEqual(minutes, 0)
        self.assertTrue(refused(facts, f"{NAME} is carrying a body."))

    def test_a_search_while_asleep_is_refused(self):
        gm = in_room("bedroom")
        gm.player.asleep = True
        minutes, facts = elapsed(gm, SearchAction(target_name="bedroom"))
        self.assertEqual(minutes, 0)
        self.assertTrue(facts)
        self.assertFalse(gm.world.locations["zone_home"].rooms["bedroom"].containers[1].opened)

    def test_a_name_that_is_no_room_or_container_is_refused(self):
        gm = GameManager()
        minutes, facts = elapsed(gm, SearchAction(target_name="garage"))
        self.assertEqual(minutes, 0)
        self.assertTrue(refused(facts, "There is no 'garage' to search here."))


class SearchContainerTests(unittest.TestCase):
    """carrying-and-loot: `SEARCH <container>`: opens and fills it; a reopened one is never refilled."""

    def test_opening_a_container_costs_one_minute_and_fills_it_from_its_table(self):
        gm = in_room("kitchen")
        minutes, _ = elapsed(
            gm, SearchAction(target_name="kitchen cupboards"), rng=ScriptedRandom()
        )
        self.assertEqual(minutes, 1)
        cupboards = named(gm, "zone_home", "kitchen cupboards")
        self.assertTrue(cupboards.opened)
        self.assertGreater(len(cupboards.contents), 0)

    def test_a_container_elsewhere_costs_a_minute_to_get_to_its_room(self):
        gm = GameManager()
        minutes, _ = elapsed(gm, SearchAction(target_name="medicine cabinet"))
        self.assertEqual(minutes, 2)
        self.assertEqual(gm.player.current_room, "bathroom")

    def test_a_bare_kind_word_finds_the_one_in_the_room(self):
        gm = in_room("bathroom")
        elapsed(gm, SearchAction(target_name="counter"))
        self.assertTrue(named(gm, "zone_home", "bathroom counter").opened)
        self.assertFalse(named(gm, "zone_home", "kitchen counter").opened)

    def test_an_ambiguous_bare_word_is_refused_and_lists_the_choices(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_bodega"
        gm.player.current_room = "shop_floor"
        minutes, facts = elapsed(gm, SearchAction(target_name="shelves"))
        self.assertEqual(minutes, 0)
        self.assertTrue(refused(facts, "Which one: snack shelves or drinks shelves?"))

    def test_a_container_already_gone_through_is_refused(self):
        gm = in_room("kitchen")
        elapsed(gm, SearchAction(target_name="fridge"))
        minutes, facts = elapsed(gm, SearchAction(target_name="fridge"))
        self.assertEqual(minutes, 0)
        self.assertTrue(refused(facts, f"{NAME} has already been through the fridge."))

    def test_a_reopened_container_is_never_refilled(self):
        gm = in_room("kitchen")
        counter = named(gm, "zone_home", "kitchen cupboards")
        counter.opened = True
        elapsed(gm, SearchAction(target_name="kitchen cupboards"))
        self.assertEqual(counter.contents, [])

    def test_a_fixed_container_opens_without_rolling_and_names_what_it_holds(self):
        gm = in_room("kitchen")
        rng = ScriptedRandom(randrange=[0] * 20)
        minutes, facts = elapsed(gm, SearchAction(target_name="kitchen counter"), rng=rng)
        self.assertEqual(minutes, 1)
        self.assertEqual(rng._ints, [0] * 20)
        counter = named(gm, "zone_home", "kitchen counter")
        self.assertEqual(len(counter.contents), 4)
        self.assertIn(
            f"{NAME} goes through the kitchen counter: canned beans, a water bottle, "
            "a kitchen knife and a frying pan.",
            facts,
        )

    def test_equal_items_are_counted_in_the_fact(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        gm.player.current_room = "basement"
        _, facts = elapsed(gm, SearchAction(target_name="storage shelves"))
        self.assertIn(
            f"{NAME} goes through the storage shelves: a hammer, nails, two planks and a hand axe.",
            facts,
        )

    def test_an_empty_container_finds_nothing(self):
        gm = in_room("kitchen")
        with_fill = named(gm, "zone_home", "freezer")
        with_fill.source = None
        _, facts = elapsed(gm, SearchAction(target_name="freezer"))
        self.assertIn(f"{NAME} goes through the freezer and finds nothing.", facts)

    def test_the_search_does_not_put_the_items_in_the_pack(self):
        gm = in_room("kitchen")
        elapsed(gm, SearchAction(target_name="kitchen counter"))
        self.assertEqual([e.item.id for e in gm.player.inventory], ["item_apartment_key"])


class TakeFromContainerTests(unittest.TestCase):
    """carrying-and-loot: `TAKE <item> from <container>`."""

    def opened_kitchen(self):
        gm = in_room("kitchen")
        elapsed(gm, SearchAction(target_name="kitchen counter"))
        return gm, named(gm, "zone_home", "kitchen counter")

    def test_take_moves_the_item_into_the_pack(self):
        gm, counter = self.opened_kitchen()
        minutes, facts = elapsed(
            gm, TakeAction(item_name="Water Bottle", from_name="kitchen counter")
        )
        self.assertGreaterEqual(minutes, 1)
        self.assertIn("item_water_bottle", [e.item.id for e in gm.player.inventory])
        self.assertNotIn("item_water_bottle", ids_in(counter))
        self.assertIn(f"{NAME} takes the water bottle out of the kitchen counter.", facts)

    def test_a_bare_kind_word_names_the_source(self):
        gm, counter = self.opened_kitchen()
        elapsed(gm, TakeAction(item_name="Water Bottle", from_name="counter"))
        self.assertNotIn("item_water_bottle", ids_in(counter))

    def test_take_all_takes_everything_in_one_action(self):
        gm, counter = self.opened_kitchen()
        _, facts = elapsed(
            gm, TakeAction(item_name="all", from_name="kitchen counter", all_items=True)
        )
        self.assertEqual(counter.contents, [])
        self.assertEqual(len(gm.player.inventory), 5)
        self.assertTrue(any("takes" in f and "kitchen counter" in f for f in facts), facts)

    def test_a_container_not_gone_through_is_refused(self):
        gm = in_room("kitchen")
        minutes, facts = elapsed(
            gm, TakeAction(item_name="Water Bottle", from_name="kitchen counter")
        )
        self.assertEqual(minutes, 0)
        self.assertTrue(refused(facts, "The kitchen counter hasn't been gone through."))

    def test_an_item_that_is_not_there_is_refused(self):
        gm, _ = self.opened_kitchen()
        minutes, facts = elapsed(gm, TakeAction(item_name="Crowbar", from_name="kitchen counter"))
        self.assertEqual(minutes, 0)
        self.assertTrue(refused(facts, "The kitchen counter holds no 'Crowbar'."))

    def test_a_container_in_another_room_is_refused(self):
        gm, _ = self.opened_kitchen()
        gm.player.current_room = "bedroom"
        minutes, facts = elapsed(
            gm, TakeAction(item_name="Water Bottle", from_name="kitchen counter")
        )
        self.assertEqual(minutes, 0)
        self.assertTrue(refused(facts, "The kitchen counter is in the kitchen, not here."))

    def test_past_the_main_inventory_limit_is_refused(self):
        gm, counter = self.opened_kitchen()
        counter.contents.append(ItemEntity(item=ITEMS["item_plank"]))
        from tests.support import load_pack

        load_pack(gm.player, 49.0)
        minutes, facts = elapsed(gm, TakeAction(item_name="Plank", from_name="kitchen counter"))
        self.assertEqual(minutes, 0)
        self.assertTrue(refused(facts, f"{NAME} can't carry any more."))

    def test_a_take_from_a_bag_still_works(self):
        gm = GameManager()
        bag = ItemEntity(item=ITEMS["item_toolbox"])
        bag.contents.append(ItemEntity(item=ITEMS["item_hammer"]))
        gm.player.inventory.append(bag)
        elapsed(gm, TakeAction(item_name="Hammer", from_name="Toolbox"))
        self.assertEqual(bag.contents, [])


class PutInContainerTests(unittest.TestCase):
    """carrying-and-loot: `PUT <item> in <container>`."""

    def test_put_moves_a_carried_item_into_an_opened_container(self):
        gm = in_room("kitchen")
        elapsed(gm, SearchAction(target_name="kitchen counter"))
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_hammer"]))
        minutes, facts = elapsed(gm, PutAction(item_name="Hammer", target_name="kitchen counter"))
        self.assertGreaterEqual(minutes, 1)
        counter = named(gm, "zone_home", "kitchen counter")
        self.assertIn("item_hammer", ids_in(counter))
        self.assertNotIn("item_hammer", [e.item.id for e in gm.player.inventory])
        self.assertIn(f"{NAME} puts the hammer in the kitchen counter.", facts)

    def test_a_fixed_container_keeps_what_the_player_leaves_in_it(self):
        gm = in_room("kitchen")
        elapsed(gm, SearchAction(target_name="kitchen counter"))
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_hammer"]))
        elapsed(gm, PutAction(item_name="Hammer", target_name="kitchen counter"))
        self.assertEqual(len(named(gm, "zone_home", "kitchen counter").contents), 5)

    def test_a_container_not_gone_through_is_refused(self):
        gm = in_room("kitchen")
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_hammer"]))
        minutes, facts = elapsed(gm, PutAction(item_name="Hammer", target_name="kitchen counter"))
        self.assertEqual(minutes, 0)
        self.assertTrue(refused(facts, "The kitchen counter hasn't been gone through."))

    def test_a_container_past_its_capacity_is_full(self):
        gm = in_room("kitchen")
        elapsed(gm, SearchAction(target_name="freezer"))
        freezer = named(gm, "zone_home", "freezer")
        freezer.contents = [ItemEntity(item=ITEMS["item_plank"]) for _ in range(5)]
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_hammer"]))
        minutes, facts = elapsed(gm, PutAction(item_name="Hammer", target_name="freezer"))
        self.assertEqual(minutes, 0)
        self.assertTrue(refused(facts, "The freezer is full."))

    def test_a_carried_bag_target_still_works(self):
        gm = GameManager()
        bag = ItemEntity(item=ITEMS["item_toolbox"])
        gm.player.inventory.extend([bag, ItemEntity(item=ITEMS["item_hammer"])])
        elapsed(gm, PutAction(item_name="Hammer", target_name="Toolbox"))
        self.assertEqual(ids_in(bag), ["item_hammer"])

    def test_a_target_that_is_nothing_is_refused(self):
        gm = in_room("kitchen")
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_hammer"]))
        minutes, facts = elapsed(gm, PutAction(item_name="Hammer", target_name="skip"))
        self.assertEqual(minutes, 0)
        self.assertTrue(refused(facts, f"{NAME} has no 'skip' to put things in."))


class MoveThenSearchTests(unittest.TestCase):
    """carrying-and-loot: a room move and a container search work together."""

    def test_moving_to_the_kitchen_then_searching_the_counter_costs_two_minutes(self):
        gm = GameManager()
        minutes, _ = elapsed(
            gm, MoveAction(destination="kitchen"), SearchAction(target_name="kitchen counter")
        )
        self.assertEqual(minutes, 2)
