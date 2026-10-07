"""Action Validator: precondition checks only, no state mutation."""

import unittest

from data.items import ITEMS
from managers.game import GameManager
from managers.validator import Accepted, ActionValidator, Rejected, ValidationResult
from modules.action.types import (
    AttackAction,
    CloseAction,
    DropAction,
    Duration,
    MoveAction,
    OpenAction,
    PutAction,
    ShoveAction,
    SleepAction,
    TakeAction,
    TakeOffAction,
    UnequipAction,
    UseItemAction,
    WaitAction,
    WearAction,
)
from modules.body import BodyLocation
from modules.character.equipment import CharacterArmorSlot
from modules.entity.barrier import BarrierEntity, BarrierKind
from modules.entity.item import ItemEntity
from modules.entity.zombie import ZombieEntity, ZombieState
from modules.resolution import (
    HeldItem,
    MoveBlocked,
    MoveToSpot,
    MoveToZone,
    ShuffleInZone,
    TargetBarrier,
    TargetNpc,
    TimeSpan,
    Transfer,
)
from modules.stats import CharacterStat
from tests.support import load_pack


def _accepted(result: ValidationResult) -> Accepted:
    assert isinstance(result, Accepted), result
    return result


class ClockValidationTests(unittest.TestCase):
    """Spec 01, Actions and Edge cases."""

    def setUp(self):
        self.gm = GameManager()
        self.validator = ActionValidator(self.gm)

    def _wait(self, **kwargs):
        return self.validator.validate(WaitAction(duration=Duration(**kwargs)))

    def _resolved(self, **kwargs) -> TimeSpan:
        return _accepted(self._wait(**kwargs)).expect(TimeSpan)

    def test_a_span_resolves_to_its_minutes(self):
        self.assertEqual(self._resolved(minutes=90), TimeSpan(90, clamped=False))

    def test_until_a_time_of_day_from_the_start(self):
        self.assertEqual(self._resolved(until_time_of_day="night").minutes, 14 * 60)
        self.assertEqual(self._resolved(until_time_of_day="evening").minutes, 10 * 60)

    def test_until_the_current_band_start_waits_a_full_day(self):
        self.gm.narrative.minutes = 1440 - 480 + 7 * 60  # 07:00 on day 2
        self.assertEqual(self._resolved(until_time_of_day="morning").minutes, 23 * 60)

    def test_until_exactly_now_is_tomorrow_not_zero(self):
        self.assertEqual(self._resolved(until_minute_of_day=480), TimeSpan(1440, clamped=False))

    def test_until_a_past_clock_time_is_tomorrow(self):
        self.gm.narrative.minutes = 1440 - 480 + 8 * 60  # 08:00 on day 2
        self.assertEqual(self._resolved(until_minute_of_day=7 * 60).minutes, 23 * 60)

    def test_a_wait_over_24_hours_is_clamped(self):
        self.assertEqual(self._resolved(minutes=25 * 60), TimeSpan(1440, clamped=True))

    def test_a_sleep_is_capped_at_16_hours(self):
        result = self.validator.validate(SleepAction(duration=Duration(minutes=17 * 60)))
        assert isinstance(result, Accepted)
        self.assertEqual(result.resolved, TimeSpan(960, clamped=True))

    def test_an_open_sleep_by_day_runs_to_the_cap(self):
        result = self.validator.validate(SleepAction())
        assert isinstance(result, Accepted)
        self.assertEqual(result.expect(TimeSpan).minutes, 960)

    def test_an_unknown_time_of_day_is_rejected(self):
        self.assertIsInstance(self._wait(until_time_of_day="teatime"), Rejected)


class MovementValidationTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()
        self.validator = ActionValidator(self.gm)

    def test_adjacent_move_by_direction_is_accepted(self):
        result = _accepted(self.validator.validate(MoveAction(destination="out")))
        self.assertEqual(result.expect(MoveToZone).location.id, "zone_building")

    def test_adjacent_move_by_name_is_accepted(self):
        result = self.validator.validate(MoveAction(destination="Your Building"))
        self.assertIsInstance(result, Accepted)

    def test_non_adjacent_zone_is_reached_by_walking(self):
        # The Street is reachable from zone_home by walking the connection
        # graph through the building, though not directly adjacent.
        result = _accepted(self.validator.validate(MoveAction(destination="The Street")))
        self.assertEqual(result.expect(MoveToZone).location.id, "zone_street")

    def test_nonexistent_location_becomes_a_spot(self):
        # MOVE_TO never fails -- an unmatched name soft-lands as a free-text
        # spot in the current zone.
        result = _accepted(self.validator.validate(MoveAction(destination="Atlantis")))
        self.assertEqual(result.expect(MoveToSpot).place, "Atlantis")
        # State must not have moved -- validation never mutates.
        self.assertEqual(self.gm.player.current_location_id, "zone_home")

    def test_locked_door_blocks_movement_without_the_key(self):
        # A locked door soft-lands ("blocked") rather than rejecting the move.
        self.gm.player.current_location_id = "zone_building"
        self.gm.player.inventory.clear()

        result = _accepted(self.validator.validate(MoveAction(destination="in")))
        self.assertEqual(result.expect(MoveBlocked).location.id, "zone_building")

    def test_locked_door_opens_with_the_key_in_inventory(self):
        self.gm.player.current_location_id = "zone_building"

        result = _accepted(self.validator.validate(MoveAction(destination="in")))
        self.assertIsInstance(result.resolved, MoveToZone)

    def test_a_locked_door_needs_no_key_from_its_inside(self):
        self.gm.player.inventory.clear()

        result = _accepted(self.validator.validate(MoveAction(destination="out")))
        self.assertIsInstance(result.resolved, MoveToZone)

    def test_bare_direction_wins_over_a_colliding_alias(self):
        # BARE_DIRECTIONS is checked before resolve_location's whole-word
        # fallback, so a bare direction word is always a shuffle even if some
        # zone's alias list happens to contain it too (content bug, but the
        # validator must not let it silently turn a shuffle into a teleport).
        self.gm.current_location.aliases.append("north")
        result = _accepted(self.validator.validate(MoveAction(destination="north")))
        self.assertEqual(result.expect(ShuffleInZone).location.id, "zone_home")

    def test_validation_never_mutates(self):
        # The validator only decides what a move means; it never writes
        # state. A spot move resolved via the validator alone (SimulationCore
        # not invoked) must leave current_place untouched.
        result = _accepted(self.validator.validate(MoveAction(destination="the pharmacy")))
        self.assertEqual(result.expect(MoveToZone).place, "the pharmacy")
        self.assertEqual(self.gm.player.current_place, "")
        self.assertEqual(self.gm.player.current_location_id, "zone_home")


class ItemValidationTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()
        self.validator = ActionValidator(self.gm)

    def test_take_missing_item_is_rejected(self):
        result = self.validator.validate(TakeAction(item_name="Nonexistent"))
        self.assertIsInstance(result, Rejected)

    def test_take_present_item_is_accepted(self):
        self.gm.player.current_location_id = "zone_street"
        result = _accepted(self.validator.validate(TakeAction(item_name="Crowbar")))
        self.assertEqual(result.expect(Transfer).entities[0].item.name, "Crowbar")

    def test_take_rejected_past_fifty_kilos(self):
        self.gm.player.current_location_id = "zone_street"
        load_pack(self.gm.player, 49)
        result = self.validator.validate(TakeAction(item_name="Crowbar"))
        assert isinstance(result, Rejected)
        self.assertEqual(result.reason, "Orton can't carry any more.")

    def test_take_accepted_up_to_fifty_kilos(self):
        self.gm.player.current_location_id = "zone_street"
        load_pack(self.gm.player, 47.99)
        _accepted(self.validator.validate(TakeAction(item_name="Crowbar")))

    def test_drop_missing_item_is_rejected(self):
        result = self.validator.validate(DropAction(item_name="Crowbar"))
        self.assertIsInstance(result, Rejected)

    def test_use_item_requires_a_usable_item(self):
        from data.items import ITEMS
        from modules.entity.item import ItemEntity

        self.gm.player.inventory.append(ItemEntity(item=ITEMS["item_painkillers"]))
        result = self.validator.validate(UseItemAction(item_name="Painkillers"))
        self.assertIsInstance(result, Accepted)

    def test_use_item_rejects_non_usable_items(self):
        from data.items import ITEMS
        from modules.entity.item import ItemEntity

        self.gm.player.inventory.append(ItemEntity(item=ITEMS["item_crowbar"]))
        result = self.validator.validate(UseItemAction(item_name="Crowbar"))
        self.assertIsInstance(result, Rejected)

    def test_use_item_not_in_inventory_is_rejected(self):
        result = self.validator.validate(UseItemAction(item_name="Painkillers"))
        self.assertIsInstance(result, Rejected)


class DoorKeyValidationTests(unittest.TestCase):
    """Door keys are engine-owned. A "door key" is any item id that is the
    `key_id` of a barrier anywhere in the world -- not hard-coded to
    item_apartment_key. Dropping or conjuring one could strand Orton outside
    his own apartment, since the door rebuilds LOCKED on every load."""

    def setUp(self):
        self.gm = GameManager()
        self.validator = ActionValidator(self.gm)

    def test_dropping_the_apartment_key_is_rejected(self):
        result = self.validator.validate(DropAction(item_name="Apartment Key"))
        self.assertIsInstance(result, Rejected)
        self.assertEqual(result.reason, "Orton keeps his keys on him.")
        # Still in inventory -- rejection must not have mutated anything.
        self.assertEqual([e.item.name for e in self.gm.player.inventory], ["Apartment Key"])

    def test_any_door_key_is_protected_not_just_the_apartment_one(self):
        # A second, test-local locked door with its own key -- the rule must
        # not be hard-coded to item_apartment_key.
        from data.items import ITEMS
        from modules.entity.item import ItemEntity

        self.gm.world.barriers["storage_door"] = BarrierEntity(
            barrier_id="storage_door",
            kind=BarrierKind.DOOR,
            zones=("zone_home", "zone_building"),
            inside_zone="zone_home",
            name="storage door",
            health=500,
            max_health=500,
            locked=True,
            key_id="item_storage_key",
        )
        self.gm.player.inventory.append(ItemEntity(item=ITEMS["item_storage_key"]))

        result = self.validator.validate(DropAction(item_name="Storage Room Key"))
        self.assertIsInstance(result, Rejected)
        self.assertEqual(result.reason, "Orton keeps his keys on him.")


class CombatValidationTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()
        # Orton now starts alone in his apartment; Emma starts in zone_building.
        self.gm.player.current_location_id = "zone_building"
        self.validator = ActionValidator(self.gm)

    def test_attack_present_npc_is_accepted(self):
        result = _accepted(self.validator.validate(AttackAction(target_name="Emma")))
        self.assertEqual(result.expect(TargetNpc).npc.npc_id, "npc_emma")

    def test_attack_absent_npc_is_rejected(self):
        # Jen is in zone_neighborhood, not zone_building -- Marcus moved
        # there too and would now be (wrongly) co-located with the player.
        result = self.validator.validate(AttackAction(target_name="Jen"))
        self.assertIsInstance(result, Rejected)

    def test_attack_downed_npc_is_rejected(self):
        emma = self.gm.resolve_npc("Emma")
        emma.hit_points = 0
        result = self.validator.validate(AttackAction(target_name="Emma"))
        self.assertIsInstance(result, Rejected)


class SleepRefusalTests(unittest.TestCase):
    """Spec 02, Waking."""

    def setUp(self):
        self.gm = GameManager()
        self.validator = ActionValidator(self.gm)

    def test_sleep_is_refused_at_panic_level_one(self):
        self.gm.player.stats.set(CharacterStat.PANIC, 7)
        result = self.validator.validate(SleepAction())
        assert isinstance(result, Rejected)
        self.assertIn("panicked", result.reason)

    def test_sleep_is_allowed_just_below_panic_level_one(self):
        self.gm.player.stats.set(CharacterStat.PANIC, 6)
        self.assertIsInstance(self.validator.validate(SleepAction()), Accepted)

    def test_sleep_is_refused_at_pain_level_two_unless_very_tired(self):
        self.gm.player.stats.set(CharacterStat.PAIN, 25)
        self.gm.player.stats.set(CharacterStat.FATIGUE, 0.85)
        self.assertIsInstance(self.validator.validate(SleepAction()), Rejected)
        self.gm.player.stats.set(CharacterStat.FATIGUE, 0.86)
        self.assertIsInstance(self.validator.validate(SleepAction()), Accepted)

    def test_open_sleep_runs_to_the_cap_by_day(self):
        result = self.validator.validate(SleepAction())
        assert isinstance(result, Accepted)
        self.assertEqual(result.expect(TimeSpan).minutes, 960)

    def test_open_sleep_at_night_runs_to_nine(self):
        self.gm.narrative.minutes = 14 * 60  # 22:00
        result = self.validator.validate(SleepAction())
        assert isinstance(result, Accepted)
        self.assertEqual(result.expect(TimeSpan).minutes, 11 * 60)


class WearValidationTests(unittest.TestCase):
    """Spec 05, Actions: WEAR and TAKE_OFF."""

    def setUp(self):
        self.gm = GameManager()
        self.gm.player.worn.clear()
        self.gm.player.inventory.clear()
        self.validator = ActionValidator(self.gm)

    def _carry(self, item_id: str) -> ItemEntity:
        entity = ItemEntity(item=ITEMS[item_id])
        self.gm.player.inventory.append(entity)
        return entity

    def _wear(self, item_id: str) -> ItemEntity:
        entity = ItemEntity(item=ITEMS[item_id])
        self.gm.player.worn[entity.item.body_location] = entity  # type: ignore[attr-defined]
        return entity

    def test_wear_accepts_a_carried_garment(self):
        entity = self._carry("item_tshirt")
        result = _accepted(self.validator.validate(WearAction(item_name="T-shirt")))
        self.assertIs(result.expect(HeldItem).entity, entity)

    def test_wear_refuses_what_is_not_carried(self):
        result = self.validator.validate(WearAction(item_name="T-shirt"))
        self.assertIsInstance(result, Rejected)

    def test_wear_refuses_a_non_garment(self):
        self._carry("item_crowbar")
        result = self.validator.validate(WearAction(item_name="Crowbar"))
        assert isinstance(result, Rejected)
        self.assertIn("cannot be worn", result.reason)

    def test_wear_refuses_an_occupied_location_naming_the_item(self):
        self._wear("item_tshirt")
        self._carry("item_tshirt")
        result = self.validator.validate(WearAction(item_name="T-shirt"))
        assert isinstance(result, Rejected)
        self.assertEqual(result.reason, "Orton is already wearing a T-shirt there.")

    def test_plural_garments_take_no_article(self):
        self._wear("item_jeans")
        self._carry("item_jeans")
        result = self.validator.validate(WearAction(item_name="Jeans"))
        assert isinstance(result, Rejected)
        self.assertEqual(result.reason, "Orton is already wearing Jeans there.")

    def test_wear_refuses_an_excluded_location_naming_the_blocker(self):
        self.gm.player.worn[BodyLocation.FULLSUIT] = ItemEntity(item=ITEMS["item_black_jacket"])
        self._carry("item_black_jacket")
        result = self.validator.validate(WearAction(item_name="Black jacket"))
        assert isinstance(result, Rejected)
        self.assertIn("Black jacket", result.reason)

    def test_take_off_accepts_a_worn_item(self):
        entity = self._wear("item_jeans")
        result = _accepted(self.validator.validate(TakeOffAction(item_name="Jeans")))
        self.assertIs(result.expect(HeldItem).entity, entity)

    def test_take_off_refuses_what_is_not_worn(self):
        self._carry("item_jeans")
        result = self.validator.validate(TakeOffAction(item_name="Jeans"))
        self.assertIsInstance(result, Rejected)

    def test_take_off_refuses_past_fifty_kilos(self):
        self._wear("item_jeans")
        load_pack(self.gm.player, 49.5)
        result = self.validator.validate(TakeOffAction(item_name="Jeans"))
        assert isinstance(result, Rejected)
        self.assertEqual(result.reason, "Orton can't carry any more.")


class CarryRefusalTests(unittest.TestCase):
    """Spec 25, Verbs: the refusals of TAKE, PUT, DROP and EQUIP."""

    def setUp(self):
        self.gm = GameManager()
        self.validator = ActionValidator(self.gm)

    def give(self, *item_ids: str) -> list[ItemEntity]:
        made = [ItemEntity(item=ITEMS[item_id]) for item_id in item_ids]
        self.gm.player.inventory.extend(made)
        return made

    def reason(self, action) -> str:
        result = self.validator.validate(action)
        assert isinstance(result, Rejected), result
        return result.reason

    def test_take_from_a_bag_that_is_not_carried(self):
        self.assertIn(
            "schoolbag", self.reason(TakeAction(item_name="Hammer", from_name="schoolbag"))
        )

    def test_take_an_item_the_bag_does_not_hold(self):
        self.give("item_schoolbag")
        self.assertEqual(
            self.reason(TakeAction(item_name="Hammer", from_name="Schoolbag")),
            "The Schoolbag holds no 'Hammer'.",
        )

    def test_take_from_a_bag_past_fifty_kilos(self):
        (bag,) = self.give("item_duffel_bag")
        self.gm.player.inventory.remove(bag)
        self.gm.player.equipment[CharacterArmorSlot.SHOULDERS] = bag
        bag.contents.append(ItemEntity(item=ITEMS["item_plank"]))
        load_pack(self.gm.player, 48.5)
        self.assertEqual(
            self.reason(TakeAction(item_name="Plank", from_name="Duffel Bag")),
            "Orton can't carry any more.",
        )

    def test_the_fifty_kilo_limit_allows_exactly_fifty(self):
        load_pack(self.gm.player, 47.0)
        self.gm.current_location.entities.append(ItemEntity(item=ITEMS["item_plank"]))
        result = self.validator.validate(TakeAction(item_name="Plank"))
        self.assertIsInstance(result, Accepted)

    def test_a_hundredth_of_a_kilo_over_fifty_is_refused(self):
        load_pack(self.gm.player, 47.01)
        self.gm.current_location.entities.append(ItemEntity(item=ITEMS["item_plank"]))
        self.assertEqual(self.reason(TakeAction(item_name="Plank")), "Orton can't carry any more.")

    def test_take_all_from_an_empty_bag(self):
        self.give("item_schoolbag")
        self.assertEqual(
            self.reason(TakeAction(item_name="all", from_name="Schoolbag", all_items=True)),
            "There is nothing in the Schoolbag to take.",
        )

    def test_take_all_past_fifty_kilos_refuses_the_lot(self):
        load_pack(self.gm.player, 45)
        self.assertEqual(
            self.reason(TakeAction(item_name="all", all_items=True)), "Orton can't carry any more."
        )

    def test_a_sleeper_cannot_take_put_or_drop(self):
        self.give("item_schoolbag", "item_canned_beans")
        self.gm.player.asleep = True
        for action in (
            TakeAction(item_name="Canned Beans", from_name="Schoolbag"),
            PutAction(item_name="Canned Beans", target_name="Schoolbag"),
            DropAction(item_name="Canned Beans"),
        ):
            self.assertEqual(self.reason(action), "Orton is asleep.")

    def test_put_an_item_not_carried(self):
        self.give("item_schoolbag")
        self.assertIn("Hammer", self.reason(PutAction(item_name="Hammer", target_name="Schoolbag")))

    def test_put_into_a_bag_not_carried(self):
        self.give("item_hammer")
        self.assertIn("Toolbox", self.reason(PutAction(item_name="Hammer", target_name="Toolbox")))

    def test_put_past_the_bags_capacity(self):
        bag, _ = self.give("item_paper_bag", "item_plank")
        self.assertEqual(
            self.reason(PutAction(item_name="Plank", target_name="Paper Bag")),
            "The Paper Bag is full.",
        )
        self.assertEqual(bag.contents, [])

    def test_put_an_item_over_the_max_size(self):
        self.give("item_toolbox", "item_plank")
        self.assertEqual(
            self.reason(PutAction(item_name="Plank", target_name="Toolbox")), "The Toolbox is full."
        )

    def test_put_a_bag_into_itself(self):
        self.give("item_schoolbag")
        self.assertEqual(
            self.reason(PutAction(item_name="Schoolbag", target_name="Schoolbag")),
            "A bag can't go into itself.",
        )

    def test_put_a_bag_into_a_bag_it_holds(self):
        outer, inner = self.give("item_duffel_bag", "item_schoolbag")
        outer.contents.append(inner)
        self.gm.player.inventory.remove(inner)
        self.assertEqual(
            self.reason(PutAction(item_name="Duffel Bag", target_name="Schoolbag")),
            "A bag can't go into itself.",
        )

    def test_put_a_bag_into_a_bag_counts_the_whole_weight(self):
        small, big = self.give("item_paper_bag", "item_duffel_bag")
        big.contents.append(ItemEntity(item=ITEMS["item_dumbbell"]))
        self.assertEqual(
            self.reason(PutAction(item_name="Duffel Bag", target_name="Paper Bag")),
            "The Paper Bag is full.",
        )
        self.assertEqual(small.contents, [])

    def test_unequip_past_fifty_kilos(self):
        (bag,) = self.give("item_schoolbag")
        self.gm.player.inventory.remove(bag)
        self.gm.player.equipment[CharacterArmorSlot.SHOULDERS] = bag
        bag.contents.append(ItemEntity(item=ITEMS["item_dumbbell"]))
        load_pack(self.gm.player, 46)
        self.assertEqual(
            self.reason(UnequipAction(item_name="Schoolbag")), "Orton can't carry any more."
        )


if __name__ == "__main__":
    unittest.main()


class BarrierValidationTests(unittest.TestCase):
    """Spec 13, Opening and closing."""

    def setUp(self):
        self.gm = GameManager()
        self.validator = ActionValidator(self.gm)

    def refusal(self, action) -> str:
        result = self.validator.validate(action)
        self.assertIsInstance(result, Rejected)
        assert isinstance(result, Rejected)
        return result.reason

    def test_open_refuses_a_barricaded_door(self):
        self.gm.world.barriers["door_apartment"].barricades["zone_home"] = [1000]
        self.assertEqual(
            self.refusal(OpenAction(barrier_name="apartment door")),
            "The apartment door is barricaded.",
        )

    def test_open_refuses_a_door_barricaded_on_the_far_side(self):
        self.gm.world.barriers["door_apartment"].barricades["zone_building"] = [1000]
        self.assertIn("barricaded", self.refusal(OpenAction(barrier_name="apartment door")))

    def test_open_refuses_a_broken_door(self):
        self.gm.world.barriers["door_apartment"].broken = True
        self.assertIn("no door left", self.refusal(OpenAction(barrier_name="apartment door")))

    def test_close_refuses_a_broken_door_and_a_closed_one(self):
        self.assertIn("already closed", self.refusal(CloseAction(barrier_name="apartment door")))
        self.gm.world.barriers["door_apartment"].broken = True
        self.assertEqual(
            self.refusal(CloseAction(barrier_name="apartment door")),
            "There's no door left to close.",
        )

    def test_open_refuses_a_locked_door_from_outside_without_the_key(self):
        self.gm.player.current_location_id = "zone_building"
        self.gm.player.inventory.clear()
        self.assertEqual(self.refusal(OpenAction(barrier_name="apartment door")), "It's locked.")

    def test_open_accepts_the_locked_door_from_outside_with_the_key(self):
        self.gm.player.current_location_id = "zone_building"
        result = self.validator.validate(OpenAction(barrier_name="apartment door"))
        self.assertIsInstance(result, Accepted)

    def test_open_accepts_it_from_inside_without_the_key(self):
        self.gm.player.inventory.clear()
        result = self.validator.validate(OpenAction(barrier_name="apartment door"))
        assert isinstance(result, Accepted)
        self.assertTrue(result.expect(TargetBarrier).walk)

    def test_a_barrier_of_another_zone_is_refused(self):
        self.assertEqual(
            self.refusal(OpenAction(barrier_name="lobby door")), "There's no door here."
        )

    def test_aliases_and_articles_find_the_door(self):
        for name in ("the front door", "my door", "door", "apartment door", "door_apartment"):
            with self.subTest(name=name):
                self.assertIsInstance(
                    self.validator.validate(OpenAction(barrier_name=name)), Accepted
                )

    def test_a_zombie_behind_a_door_cannot_be_attacked(self):
        self.gm.world.outbreak_started_at = 0
        self.gm.world.barriers["door_apartment"].open = False
        self.gm.world.zombies["z1"] = ZombieEntity(
            zombie_id="z1",
            zone_id="zone_building",
            health=2.0,
            speed_type=3,
            speed_mod=0.6,
            lunger=False,
            strength=3,
            memory=800,
            sight=2,
            hearing=2,
            state=ZombieState.THUMPING,
            gap=5,
            thump_barrier="door_apartment",
            thump_rate=1.5,
        )
        self.assertEqual(
            self.refusal(AttackAction(target_name="z1")), "It's on the other side of the door."
        )
        self.assertEqual(
            self.refusal(ShoveAction(target_name="z1")), "It's on the other side of the door."
        )

    def test_attack_door_is_accepted_and_names_the_barrier(self):
        result = self.validator.validate(AttackAction(target_name="apartment door"))
        assert isinstance(result, Accepted)
        self.assertEqual(result.expect(TargetBarrier).barrier.barrier_id, "door_apartment")

    def test_move_to_stops_at_a_barricade_on_either_side(self):
        door = self.gm.world.barriers["door_apartment"]
        for side in ("zone_home", "zone_building"):
            with self.subTest(side=side):
                door.barricades["zone_home"] = []
                door.barricades["zone_building"] = []
                door.barricades[side] = [1000]
                result = self.validator.validate(MoveAction(destination="out"))
                assert isinstance(result, Accepted)
                blocked = result.expect(MoveBlocked)
                self.assertEqual(blocked.place, "at the barricaded door")
                self.assertEqual(blocked.barrier, door)

    def test_move_to_passes_an_open_barricade_free_door(self):
        self.gm.world.barriers["door_apartment"].open = True
        result = self.validator.validate(MoveAction(destination="out"))
        assert isinstance(result, Accepted)
        self.assertIsInstance(result.resolved, MoveToZone)
