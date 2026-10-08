"""carrying-and-loot: Carrying: capacity, weight and Heavy Load."""

import random
import unittest
from unittest import mock

from data.body.status_effects import STATUS_EFFECT_THRESHOLDS
from data.items import ITEMS
from managers import carry
from managers.body.health import BodyEngine
from managers.body.stats.drivers import EnduranceDriver, StatContext
from managers.body.stats.status_effects import player_status_effect_levels
from managers.game import GameManager
from managers.simulation import SimulationCore
from modules import units
from modules.action.parser import VERBS, ParseFailure, parse_action_line
from modules.action.types import (
    CarryAction,
    DropAction,
    Duration,
    EquipAction,
    MoveAction,
    PutAction,
    TakeAction,
    TakeOffAction,
    UnequipAction,
    UseItemAction,
    WaitAction,
    WearAction,
)
from modules.body.parts import BodyLocation
from modules.body.stats import CharacterStat, Stats, StatusEffect
from modules.character.equipment import CharacterArmorSlot, CharacterHoldableSlot
from modules.character.skills import SkillState
from modules.entity.corpse import CorpseEntity
from modules.entity.item import ItemEntity
from modules.entity.player import PlayerEntity
from modules.item import ContainerItem, HoldableItem
from tests.support import ScriptedRandom, set_health, simulate


def player(strength: int = 5, traits: tuple[str, ...] = ()) -> PlayerEntity:
    who = PlayerEntity(name="Test", current_location_id="zone_home")
    who.skills["strength"] = SkillState(level=strength)
    who.traits = list(traits)
    return who


def entity(item_id: str, **fields) -> ItemEntity:
    return ItemEntity(item=ITEMS[item_id], **fields)


NO_EFFECTS: dict[StatusEffect, int] = {}


class CapacityTests(unittest.TestCase):
    """carrying-and-loot: Capacity."""

    def test_strength_zero_to_ten(self):
        got = [carry.max_weight(level, (), NO_EFFECTS) for level in range(11)]
        self.assertEqual(got, [6, 7, 8, 9, 11, 12, 14, 15, 16, 18, 20])

    def test_strong_at_strength_nine_is_27(self):
        self.assertEqual(carry.max_weight(9, ("strong",), NO_EFFECTS), 27)

    def test_the_other_trait_multipliers(self):
        self.assertEqual(carry.max_weight(9, ("stout",), NO_EFFECTS), int(18 * 1.25))
        self.assertEqual(carry.max_weight(9, ("feeble",), NO_EFFECTS), int(18 * 0.9))
        self.assertEqual(carry.max_weight(9, ("weak",), NO_EFFECTS), int(18 * 0.75))

    def test_hungry_level_three_at_strength_five_is_10(self):
        self.assertEqual(carry.max_weight(5, (), {StatusEffect.HUNGRY: 3}), 10)

    def test_the_reducer_table(self):
        cases = {
            StatusEffect.HUNGRY: [0, 1, 2, 2],
            StatusEffect.THIRST: [0, 1, 2, 2],
            StatusEffect.SICK: [0, 1, 2, 3],
            StatusEffect.BLEEDING: [0, 1, 1, 1],
            StatusEffect.INJURED: [0, 1, 2, 3],
        }
        for effect, losses in cases.items():
            got = [20 - carry.max_weight(10, (), {effect: level}) for level in (1, 2, 3, 4)]
            self.assertEqual(got, losses, effect)

    def test_the_reducers_add_up(self):
        levels = {StatusEffect.HUNGRY: 4, StatusEffect.SICK: 4, StatusEffect.INJURED: 4}
        self.assertEqual(carry.max_weight(10, (), levels), 20 - 2 - 3 - 3)

    def test_a_negative_result_is_zero(self):
        levels = {StatusEffect.HUNGRY: 4, StatusEffect.INJURED: 4}
        self.assertEqual(carry.max_weight(0, (), levels), 1)
        levels.update({StatusEffect.SICK: 4, StatusEffect.THIRST: 4})
        self.assertEqual(carry.max_weight(0, (), levels), 0)

    def test_the_player_capacity_reads_strength_and_traits(self):
        self.assertEqual(carry.player_max_weight(player(9, ("strong",)), NO_EFFECTS), 27)


class WeightTests(unittest.TestCase):
    """carrying-and-loot: Weight."""

    def test_a_can_in_the_pack_weighs_0_8(self):
        who = player()
        who.inventory.append(entity("item_canned_beans"))
        self.assertAlmostEqual(carry.carried_weight(who), 0.8)

    def test_a_can_in_a_hand_weighs_0_24(self):
        who = player()
        who.equipment[CharacterHoldableSlot.RIGHT_HAND] = entity("item_canned_beans")
        self.assertAlmostEqual(carry.carried_weight(who), 0.24)

    def test_a_worn_garment_weighs_0_3_of_its_weight(self):
        who = player()
        who.worn[ITEMS["item_black_jacket"].body_location] = entity("item_black_jacket")  # type: ignore[attr-defined]
        self.assertAlmostEqual(carry.carried_weight(who), 0.6)

    def test_a_two_handed_item_counts_once(self):
        who = player()
        bat = entity("item_baseball_bat")
        who.equipment[CharacterHoldableSlot.RIGHT_HAND] = bat
        who.equipment[CharacterHoldableSlot.LEFT_HAND] = bat
        self.assertAlmostEqual(carry.carried_weight(who), 0.6)

    def test_a_worn_bag_with_ten_kilos_weighs_3_3(self):
        who = player()
        bag = entity("item_schoolbag")
        bag.contents = [entity("item_dumbbell"), entity("item_dumbbell")]
        who.equipment[CharacterArmorSlot.SHOULDERS] = bag
        self.assertAlmostEqual(carry.carried_weight(who), 3.3)

    def test_the_same_bag_unworn_weighs_11(self):
        who = player()
        bag = entity("item_schoolbag")
        bag.contents = [entity("item_dumbbell"), entity("item_dumbbell")]
        who.inventory.append(bag)
        self.assertAlmostEqual(carry.carried_weight(who), 11.0)

    def test_a_bag_in_a_worn_bag_counts_in_full_inside_one_reduction(self):
        who = player()
        outer = entity("item_schoolbag")
        inner = entity("item_toolbox")
        inner.contents = [entity("item_hammer")]
        outer.contents = [inner]
        who.equipment[CharacterArmorSlot.SHOULDERS] = outer
        self.assertAlmostEqual(carry.carried_weight(who), 0.3 + (2.0 + 1.5) * 0.3)

    def test_a_carried_body_weighs_6_and_a_skeleton_2_1(self):
        who = player()
        who.carrying_corpse = "c1"
        self.assertAlmostEqual(carry.carried_weight(who), 6.0)
        who.carrying_skeleton = True
        self.assertAlmostEqual(carry.carried_weight(who), 2.1)

    def test_a_weight_is_rounded_to_a_hundredth(self):
        self.assertEqual(carry.rounded(0.1 + 0.2), 0.3)


class HeavyLoadTests(unittest.TestCase):
    """carrying-and-loot: Heavy Load."""

    def test_capacity_12_edges(self):
        got = [carry.heavy_load_level(weight, 12) for weight in (0, 12, 12.5, 15, 18, 21)]
        self.assertEqual(got, [0, 0, 1, 2, 3, 4])

    def test_the_levels_start_at_or_above_except_the_first(self):
        self.assertEqual(carry.heavy_load_level(12.01, 12), 1)
        self.assertEqual(carry.heavy_load_level(14.99, 12), 1)
        self.assertEqual(carry.heavy_load_level(17.99, 12), 2)
        self.assertEqual(carry.heavy_load_level(20.99, 12), 3)

    def test_capacity_zero_with_anything_is_level_four(self):
        self.assertEqual(carry.heavy_load_level(0.05, 0), 4)
        self.assertEqual(carry.heavy_load_level(0, 0), 0)

    def test_the_status_effect_row(self):
        row = STATUS_EFFECT_THRESHOLDS[StatusEffect.HEAVY_LOAD]
        self.assertEqual(row.thresholds, (1.0, 1.25, 1.5, 1.75))
        self.assertEqual(
            row.names, ("Weighed Down", "Overloaded", "Very Overloaded", "Extremely Overloaded")
        )

    def test_the_player_levels_carry_heavy_load(self):
        who = player(0)
        self.assertEqual(player_status_effect_levels(who)[StatusEffect.HEAVY_LOAD], 0)
        who.inventory.extend([entity("item_barbell"), entity("item_barbell")])
        self.assertEqual(carry.player_max_weight(who, player_status_effect_levels(who)), 6)
        self.assertEqual(player_status_effect_levels(who)[StatusEffect.HEAVY_LOAD], 4)

    def test_it_moves_the_moment_an_item_moves(self):
        who = player(5)
        who.inventory.append(entity("item_barbell"))
        self.assertEqual(player_status_effect_levels(who)[StatusEffect.HEAVY_LOAD], 0)
        who.inventory.append(entity("item_dumbbell"))
        self.assertEqual(player_status_effect_levels(who)[StatusEffect.HEAVY_LOAD], 0)
        who.inventory.append(entity("item_hammer"))
        self.assertEqual(player_status_effect_levels(who)[StatusEffect.HEAVY_LOAD], 1)

    def test_it_is_zero_at_zero_health(self):
        who = player(0)
        who.inventory.extend([entity("item_barbell"), entity("item_barbell")])
        set_health(who, 0)
        self.assertEqual(player_status_effect_levels(who)[StatusEffect.HEAVY_LOAD], 0)


def loaded(strength: int, *item_ids: str, traits: tuple[str, ...] = ()) -> PlayerEntity:
    """A player with `item_ids` loose in the pack."""
    who = player(strength, traits)
    who.inventory.extend(entity(item_id) for item_id in item_ids)
    return who


LEVEL_3 = ("item_barbell", "item_plank")  # 9 kg against a capacity of 6
LEVEL_4 = ("item_barbell", "item_dumbbell")  # 11 kg against a capacity of 6
LEVEL_2 = ("item_barbell", "item_plank")  # 9 kg against a capacity of 7 (Strength 1)


def endurance_after(who_ctx: StatContext, start: float, minutes: float = 1.0) -> float:
    stats = Stats()
    stats.set(CharacterStat.ENDURANCE, start)
    EnduranceDriver().apply(stats, minutes / 60, who_ctx)
    return stats.get(CharacterStat.ENDURANCE)


class HeavyLoadEnduranceTests(unittest.TestCase):
    """carrying-and-loot: What Heavy Load does: the endurance terms."""

    def test_the_exercising_drain_is_1_9_times_at_level_2(self):
        plain = 0.8 - endurance_after(StatContext(exercising=True), 0.8, 60)
        heavy = 0.8 - endurance_after(StatContext(exercising=True, heavy_load=2), 0.8, 60)
        self.assertAlmostEqual(plain, 0.2808, places=4)
        self.assertAlmostEqual(heavy, 0.2808 * 1.9, places=4)

    def test_the_exercising_multipliers_by_level(self):
        for level, mult in enumerate((1, 1.5, 1.9, 2.3, 2.8)):
            drop = 0.9 - endurance_after(StatContext(exercising=True, heavy_load=level), 0.9, 60)
            self.assertAlmostEqual(drop, 0.2808 * mult, places=4, msg=str(level))

    def test_walking_at_level_3_drains_0_01307_a_minute(self):
        drop = 0.9 - endurance_after(StatContext(walking=True, heavy_load=3), 0.9)
        self.assertAlmostEqual(drop, 0.01307, places=5)

    def test_walking_at_level_4_drains_0_01582_a_minute(self):
        drop = 0.9 - endurance_after(StatContext(walking=True, heavy_load=4), 0.9)
        self.assertAlmostEqual(drop, 0.01582, places=5)

    def test_sneaking_under_load_drains_half_as_much_again(self):
        ctx = StatContext(walking=True, sneaking=True, heavy_load=3)
        self.assertAlmostEqual(0.9 - endurance_after(ctx, 0.9), 0.01307 * 1.5, places=5)

    def test_the_walking_drain_traits(self):
        overweight = StatContext(walking=True, heavy_load=3, traits=frozenset({"overweight"}))
        athletic = StatContext(walking=True, heavy_load=3, traits=frozenset({"athletic"}))
        asthmatic = StatContext(walking=True, heavy_load=3, traits=frozenset({"asthmatic"}))
        self.assertAlmostEqual(0.9 - endurance_after(overweight, 0.9), 0.01307 * 2.9 / 1.4, 5)
        self.assertAlmostEqual(0.9 - endurance_after(athletic, 0.9), 0.01307 * 0.8 / 1.4, 5)
        self.assertAlmostEqual(0.9 - endurance_after(asthmatic, 0.9), 0.01307 / 0.7, 5)

    def test_standing_regeneration_stops_above_level_1(self):
        for level in (2, 3, 4):
            self.assertEqual(endurance_after(StatContext(heavy_load=level), 0.5, 60), 0.5, level)
        for level in (0, 1):
            self.assertGreater(endurance_after(StatContext(heavy_load=level), 0.5, 60), 0.5, level)

    def test_walking_regeneration_stops_above_level_1(self):
        self.assertEqual(endurance_after(StatContext(walking=True, heavy_load=2), 0.9, 60), 0.9)
        self.assertGreater(endurance_after(StatContext(walking=True, heavy_load=1), 0.9, 60), 0.9)

    def test_moving_a_body_drains_2_457_an_hour(self):
        ctx = StatContext(walking=True, exercising=True, carrying_corpse=True)
        self.assertAlmostEqual((0.9 - endurance_after(ctx, 0.9, 1)) * 60, 2.457, places=3)


class OverloadLossTests(unittest.TestCase):
    """carrying-and-loot: What Heavy Load does: the overload loss."""

    def lose(self, who: PlayerEntity, *, resting: bool = False) -> float:
        before = who.health
        BodyEngine(random.Random(1)).overload(who, resting=resting)
        return before - who.health

    def test_level_3_costs_1_485_hp_a_minute(self):
        who = loaded(0, *LEVEL_3)
        set_health(who, 90)
        self.assertAlmostEqual(self.lose(who), 1.485, places=3)

    def test_level_4_costs_2_97_hp_a_minute(self):
        who = loaded(0, *LEVEL_4)
        set_health(who, 90)
        self.assertAlmostEqual(self.lose(who), 2.97, places=3)

    def test_level_2_costs_nothing(self):
        who = loaded(1, *LEVEL_2)
        set_health(who, 90)
        self.assertEqual(player_status_effect_levels(who)[StatusEffect.HEAVY_LOAD], 2)
        self.assertEqual(self.lose(who), 0)

    def test_nothing_at_or_below_75_hp(self):
        who = loaded(0, *LEVEL_4)
        set_health(who, 75)
        self.assertEqual(self.lose(who), 0)
        set_health(who, 60)
        self.assertEqual(self.lose(who), 0)

    def test_the_loss_stops_at_75_hp(self):
        who = loaded(0, *LEVEL_4)
        set_health(who, 76)
        self.lose(who)
        self.assertAlmostEqual(who.health, 75, places=3)

    def test_resting_and_sleeping_cost_nothing(self):
        who = loaded(0, *LEVEL_4)
        set_health(who, 90)
        self.assertEqual(self.lose(who, resting=True), 0)
        who.asleep = True
        self.assertEqual(self.lose(who), 0)

    def test_a_minute_of_walking_applies_it_and_a_minute_of_waiting_does_not(self):
        moving = bare_game(0, *LEVEL_4)
        set_health(moving.player, 90)
        simulate(moving, MoveAction(destination="the kitchen"))
        self.assertLess(moving.player.health, 88)
        waiting = bare_game(0, *LEVEL_4)
        set_health(waiting.player, 90)
        simulate(waiting, WaitAction(duration=Duration(minutes=1)))
        self.assertGreaterEqual(waiting.player.health, 90)


def bare_game(strength: int, *item_ids: str) -> GameManager:
    gm = GameManager()
    gm.player.worn.clear()
    gm.player.inventory = [entity(item_id) for item_id in item_ids]
    gm.player.skills["strength"] = SkillState(level=strength)
    return gm


class StatContextTests(unittest.TestCase):
    """carrying-and-loot: What Heavy Load does: the context the drivers read."""

    def test_the_context_has_the_ratio_and_the_level(self):
        gm = bare_game(0, "item_barbell", "item_dumbbell")
        ctx = SimulationCore(gm)._stat_context(None)
        self.assertAlmostEqual(ctx.carry_ratio, 11 / 6)
        self.assertEqual(ctx.heavy_load, 4)
        self.assertFalse(ctx.carrying_corpse)

    def test_an_empty_pack_has_ratio_zero(self):
        ctx = SimulationCore(bare_game(5))._stat_context(None)
        self.assertEqual((ctx.carry_ratio, ctx.heavy_load), (0.0, 0))

    def test_moving_a_body_counts_as_exercising(self):
        gm = bare_game(5)
        gm.player.carrying_corpse = "c1"
        core = SimulationCore(gm)
        moving = core._stat_context(MoveAction(destination="out"))
        self.assertTrue(moving.exercising)
        self.assertTrue(moving.carrying_corpse)
        self.assertFalse(core._stat_context(WaitAction(duration=Duration(minutes=5))).exercising)


class ParsingTests(unittest.TestCase):
    """carrying-and-loot: Verbs: the lines the parser reads."""

    def test_put_takes_an_item_and_a_bag(self):
        self.assertEqual(
            parse_action_line("PUT hammer in toolbox"),
            PutAction(item_name="hammer", target_name="toolbox"),
        )
        self.assertEqual(
            parse_action_line("PUT the canned beans into the schoolbag"),
            PutAction(item_name="the canned beans", target_name="the schoolbag"),
        )

    def test_put_without_a_target_is_refused(self):
        self.assertIsInstance(parse_action_line("PUT hammer"), ParseFailure)
        self.assertIsInstance(parse_action_line("PUT"), ParseFailure)

    def test_take_all_from_a_source(self):
        self.assertEqual(
            parse_action_line("TAKE all from schoolbag"),
            TakeAction(item_name="all", from_name="schoolbag", all_items=True),
        )

    def test_take_all_with_no_source_is_the_ground(self):
        self.assertEqual(parse_action_line("TAKE all"), TakeAction(item_name="all", all_items=True))

    def test_an_item_called_all_something_is_still_an_item(self):
        self.assertEqual(parse_action_line("TAKE allen key"), TakeAction(item_name="allen key"))

    def test_carry_names_a_corpse(self):
        self.assertEqual(parse_action_line("CARRY c3"), CarryAction(corpse_name="c3"))
        self.assertIsInstance(parse_action_line("CARRY"), ParseFailure)

    def test_drop_corpse(self):
        self.assertEqual(
            parse_action_line("DROP corpse"), DropAction(item_name="corpse", corpse=True)
        )
        self.assertEqual(
            parse_action_line("DROP the body"), DropAction(item_name="the body", corpse=True)
        )
        self.assertEqual(parse_action_line("DROP hammer"), DropAction(item_name="hammer"))

    def test_the_verbs_are_registered(self):
        self.assertEqual(VERBS["PUT"].minutes, 1)
        self.assertEqual(VERBS["CARRY"].minutes, 1)


class TransferFramesTests(unittest.TestCase):
    """carrying-and-loot: Moving things: frames per item."""

    def frames(self, item_id, source, target, **kw):
        return carry.transfer_frames(entity(item_id), source, target, **kw)

    def test_a_small_can_from_a_world_container_is_40_frames_and_a_minute(self):
        frames = self.frames("item_canned_beans", carry.Place.WORLD, carry.Place.PACK)
        self.assertAlmostEqual(frames, 40)
        self.assertEqual(units.minutes_from_timed_action_frames(frames), 1)

    def test_twelve_cans_taken_at_once_are_480_frames_and_three_minutes(self):
        frames = sum(
            self.frames("item_canned_beans", carry.Place.WORLD, carry.Place.PACK) for _ in range(12)
        )
        self.assertAlmostEqual(frames, 480)
        self.assertEqual(units.minutes_from_timed_action_frames(frames), 3)

    def test_a_plank_into_a_bag_at_90_percent_is_324_frames_and_two_minutes(self):
        bag = entity("item_garbage_bag")  # capacity 20
        bag.contents = [entity("item_barbell") for _ in range(3)]  # 18 kg: 90 percent
        frames = carry.transfer_frames(
            entity("item_plank"), carry.Place.PACK, carry.Place.BAG, bag=bag
        )
        self.assertAlmostEqual(frames, 324)
        self.assertEqual(units.minutes_from_timed_action_frames(frames), 2)

    def test_an_emptier_bag_counts_as_at_least_40_percent_full(self):
        frames = self.frames(
            "item_plank", carry.Place.PACK, carry.Place.BAG, bag=entity("item_duffel_bag")
        )
        self.assertAlmostEqual(frames, 120 * 3 * 0.4)

    def test_a_heavy_item_counts_as_3_kilos(self):
        self.assertAlmostEqual(
            self.frames("item_barbell", carry.Place.WORLD, carry.Place.PACK), 150
        )

    def test_dropping_on_the_floor_is_a_tenth(self):
        self.assertAlmostEqual(
            self.frames("item_canned_beans", carry.Place.PACK, carry.Place.FLOOR), 4
        )

    def test_the_floor_and_a_corpse_count_as_the_world(self):
        self.assertAlmostEqual(
            self.frames("item_canned_beans", carry.Place.FLOOR, carry.Place.PACK), 40
        )

    def test_anything_out_of_a_carried_bag_is_120_a_kilo(self):
        for target in (carry.Place.PACK, carry.Place.FLOOR, carry.Place.WORLD, carry.Place.BAG):
            self.assertAlmostEqual(self.frames("item_canned_beans", carry.Place.BAG, target), 96)

    def test_dextrous_halves_and_all_thumbs_doubles(self):
        base = self.frames("item_canned_beans", carry.Place.WORLD, carry.Place.PACK)
        dextrous = self.frames(
            "item_canned_beans", carry.Place.WORLD, carry.Place.PACK, traits=("dextrous",)
        )
        clumsy = self.frames(
            "item_canned_beans", carry.Place.WORLD, carry.Place.PACK, traits=("allthumbs",)
        )
        self.assertAlmostEqual(dextrous, base / 2)
        self.assertAlmostEqual(clumsy, base * 2)


def home() -> GameManager:
    """A new game with nothing worn, in the apartment, and the pack holding the key only."""
    gm = GameManager()
    gm.player.worn.clear()
    return gm


def home_with_things_on_the_floor() -> GameManager:
    """The apartment with the old floor stock: beans, a bottle, a jacket, a knife, a pan, a schoolbag."""
    gm = home()
    for item_id in (
        "item_canned_beans",
        "item_water_bottle",
        "item_black_jacket",
        "item_kitchen_knife",
        "item_frying_pan",
        "item_schoolbag",
    ):
        gm.current_location.entities.append(ItemEntity(item=ITEMS[item_id]))
    return gm


def give(gm: GameManager, *item_ids: str) -> list[ItemEntity]:
    made = [entity(item_id) for item_id in item_ids]
    gm.player.inventory.extend(made)
    return made


def minutes_of(gm: GameManager, *actions) -> tuple[int, list[str]]:
    before = gm.narrative.minutes
    facts = simulate(gm, *actions)
    return gm.narrative.minutes - before, facts


class BagVerbTests(unittest.TestCase):
    """carrying-and-loot: Bags: EQUIP, UNEQUIP, WEAR and TAKE_OFF on a bag."""

    def test_a_back_bag_goes_on_the_shoulders(self):
        gm = home()
        (bag,) = give(gm, "item_schoolbag")
        minutes, facts = minutes_of(gm, EquipAction(item_name="Schoolbag"))
        self.assertIs(gm.player.equipment[CharacterArmorSlot.SHOULDERS], bag)
        self.assertNotIn(bag, gm.player.inventory)
        self.assertEqual(minutes, 1)
        self.assertEqual(facts[0], "Orton sets the schoolbag on his back.")

    def test_a_second_back_bag_goes_in_the_left_hand(self):
        gm = home()
        first, second = give(gm, "item_schoolbag", "item_duffel_bag")
        simulate(gm, EquipAction(item_name="Schoolbag"), EquipAction(item_name="Duffel Bag"))
        self.assertIs(gm.player.equipment[CharacterArmorSlot.SHOULDERS], first)
        self.assertIs(gm.player.equipment[CharacterHoldableSlot.LEFT_HAND], second)
        self.assertIsNone(gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND])

    def test_a_third_bag_is_refused(self):
        gm = home()
        give(gm, "item_schoolbag", "item_duffel_bag", "item_hiking_bag")
        simulate(gm, EquipAction(item_name="Schoolbag"), EquipAction(item_name="Duffel Bag"))
        minutes, facts = minutes_of(gm, EquipAction(item_name="Hiking Bag"))
        self.assertEqual(minutes, 0)
        self.assertEqual(
            facts[0],
            "Refused: Orton can't take the Hiking Bag in hand: Orton's hands and back are full.",
        )

    def test_a_hand_bag_takes_the_left_hand_and_leaves_the_right(self):
        gm = home()
        (box,) = give(gm, "item_toolbox")
        simulate(gm, EquipAction(item_name="Toolbox"))
        self.assertIs(gm.player.equipment[CharacterHoldableSlot.LEFT_HAND], box)
        self.assertIsNone(gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND])
        give(gm, "item_hammer")
        simulate(gm, EquipAction(item_name="Hammer"))
        self.assertIsNotNone(gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND])

    def test_a_held_bag_blocks_a_two_handed_weapon(self):
        gm = home()
        give(gm, "item_toolbox", "item_baseball_bat")
        simulate(gm, EquipAction(item_name="Toolbox"))
        _, facts = minutes_of(gm, EquipAction(item_name="Baseball Bat"))
        self.assertTrue(facts[0].startswith("Refused"))

    def test_a_body_bag_is_worn_not_held(self):
        gm = home()
        (satchel,) = give(gm, "item_satchel")
        _, facts = minutes_of(gm, EquipAction(item_name="Satchel"))
        self.assertTrue(facts[0].startswith("Refused"))
        minutes, facts = minutes_of(gm, WearAction(item_name="Satchel"))
        self.assertEqual(minutes, 1)
        self.assertIs(gm.player.worn[BodyLocation.SATCHEL], satchel)
        minutes, _ = minutes_of(gm, TakeOffAction(item_name="Satchel"))
        self.assertEqual(minutes, 1)
        self.assertIn(satchel, gm.player.inventory)

    def test_a_fanny_pack_is_worn_at_the_front(self):
        gm = home()
        give(gm, "item_fanny_pack")
        simulate(gm, WearAction(item_name="Fanny Pack"))
        self.assertEqual(gm.player.worn[BodyLocation.FANNYPACKFRONT].item.id, "item_fanny_pack")

    def test_a_back_bag_cannot_be_worn(self):
        gm = home()
        give(gm, "item_schoolbag")
        _, facts = minutes_of(gm, WearAction(item_name="Schoolbag"))
        self.assertTrue(facts[0].startswith("Refused"))

    def test_unequip_takes_the_bag_off_the_back(self):
        gm = home()
        (bag,) = give(gm, "item_schoolbag")
        simulate(gm, EquipAction(item_name="Schoolbag"))
        minutes, _ = minutes_of(gm, UnequipAction(item_name="Schoolbag"))
        self.assertEqual(minutes, 1)
        self.assertIsNone(gm.player.equipment[CharacterArmorSlot.SHOULDERS])
        self.assertIn(bag, gm.player.inventory)

    def test_a_dropped_bag_keeps_its_contents(self):
        gm = home()
        (bag,) = give(gm, "item_schoolbag")
        bag.contents.append(entity("item_canned_beans"))
        simulate(gm, DropAction(item_name="Schoolbag"))
        floor = [e for e in gm.current_location.entities if e is bag]
        self.assertEqual(len(floor), 1)
        self.assertEqual([e.item.id for e in bag.contents], ["item_canned_beans"])
        self.assertNotIn(bag, gm.player.inventory)

    def test_a_bag_on_the_back_can_be_dropped_with_its_contents(self):
        gm = home()
        (bag,) = give(gm, "item_schoolbag")
        bag.contents.append(entity("item_canned_beans"))
        simulate(gm, EquipAction(item_name="Schoolbag"), DropAction(item_name="Schoolbag"))
        self.assertIsNone(gm.player.equipment[CharacterArmorSlot.SHOULDERS])
        self.assertIn(bag, gm.current_location.entities)
        self.assertEqual(len(bag.contents), 1)


class PutAndTakeTests(unittest.TestCase):
    """carrying-and-loot: Verbs: PUT, TAKE from a bag, TAKE all, DROP."""

    def test_put_moves_an_item_into_a_carried_bag(self):
        gm = home()
        bag, beans = give(gm, "item_schoolbag", "item_canned_beans")
        minutes, facts = minutes_of(
            gm, PutAction(item_name="Canned Beans", target_name="Schoolbag")
        )
        self.assertEqual(bag.contents, [beans])
        self.assertNotIn(beans, gm.player.inventory)
        self.assertEqual(minutes, 1)
        self.assertEqual(facts[0], "Orton puts the canned beans in the schoolbag.")

    def test_put_into_a_worn_bag(self):
        gm = home()
        (bag,) = give(gm, "item_schoolbag")
        simulate(gm, EquipAction(item_name="Schoolbag"))
        give(gm, "item_hammer")
        simulate(gm, PutAction(item_name="Hammer", target_name="Schoolbag"))
        self.assertEqual([e.item.id for e in bag.contents], ["item_hammer"])

    def test_put_takes_an_item_out_of_one_bag_into_another(self):
        gm = home()
        first, second = give(gm, "item_schoolbag", "item_toolbox")
        first.contents.append(entity("item_hammer"))
        simulate(gm, PutAction(item_name="Hammer", target_name="Toolbox"))
        self.assertEqual(first.contents, [])
        self.assertEqual([e.item.id for e in second.contents], ["item_hammer"])

    def test_take_from_a_carried_bag(self):
        gm = home()
        (bag,) = give(gm, "item_schoolbag")
        beans = entity("item_canned_beans")
        bag.contents.append(beans)
        minutes, facts = minutes_of(gm, TakeAction(item_name="Canned Beans", from_name="Schoolbag"))
        self.assertEqual(bag.contents, [])
        self.assertIn(beans, gm.player.inventory)
        self.assertEqual(minutes, 1)
        self.assertEqual(facts[0], "Orton takes the canned beans out of the schoolbag.")

    def test_take_all_from_a_bag_is_one_action_with_the_frames_added(self):
        gm = home()
        (bag,) = give(gm, "item_schoolbag")
        bag.contents = [entity("item_canned_beans") for _ in range(12)]
        minutes, _ = minutes_of(
            gm, TakeAction(item_name="all", from_name="Schoolbag", all_items=True)
        )
        self.assertEqual(bag.contents, [])
        self.assertEqual(sum(e.item.id == "item_canned_beans" for e in gm.player.inventory), 12)
        self.assertEqual(minutes, 6)  # 12 x 96 frames = 1152, a little over 6 minutes

    def test_a_take_all_fact_counts_equal_items(self):
        gm = home()
        (bag,) = give(gm, "item_schoolbag")
        bag.contents = [entity("item_bandage"), entity("item_hammer"), entity("item_bandage")]
        _, facts = minutes_of(
            gm, TakeAction(item_name="all", from_name="Schoolbag", all_items=True)
        )
        self.assertEqual(facts[0], "Orton takes two bandages and a hammer from the schoolbag.")

    def test_take_all_from_the_ground_is_one_action(self):
        gm = home_with_things_on_the_floor()
        minutes, _ = minutes_of(gm, TakeAction(item_name="all", all_items=True))
        self.assertEqual(gm.current_location.entities, [])
        self.assertEqual(minutes, 2)  # 355 frames

    def test_take_all_with_a_bare_floor_empties_every_opened_container_of_the_room(self):
        gm = home()
        gm.player.current_room = "kitchen"
        counter, cupboards, *_ = gm.current_location.rooms["kitchen"].containers
        counter.opened = cupboards.opened = True
        counter.contents = [entity("item_canned_beans")]
        cupboards.contents = [entity("item_bandage")]
        _, facts = minutes_of(gm, TakeAction(item_name="all", all_items=True))
        self.assertEqual(counter.contents + cupboards.contents, [])
        self.assertEqual(
            facts[:2],
            [
                "Orton takes canned beans from the kitchen counter.",
                "Orton takes a bandage from the kitchen cupboards.",
            ],
        )

    def test_dextrous_halves_a_take_all(self):
        gm = home_with_things_on_the_floor()
        gm.player.traits.append("dextrous")
        minutes, _ = minutes_of(gm, TakeAction(item_name="all", all_items=True))
        self.assertEqual(minutes, 1)

    def test_take_all_from_a_corpse_adds_the_frames_before_one_conversion(self):
        gm = home()
        gm.world.corpses["c1"] = CorpseEntity(
            corpse_id="c1",
            zone_id="zone_home",
            gap=1.0,
            female=False,
            outfit="",
            died_at=0,
            rot_at_death=1,
            searched=True,
            contents=[entity("item_canned_beans") for _ in range(12)],
        )
        minutes, _ = minutes_of(gm, TakeAction(item_name="all", from_name="c1", all_items=True))
        self.assertEqual(gm.world.corpses["c1"].contents, [])
        self.assertEqual(minutes, 3)

    def test_drop_takes_an_item_out_of_a_bag(self):
        gm = home()
        (bag,) = give(gm, "item_schoolbag")
        beans = entity("item_canned_beans")
        bag.contents.append(beans)
        minutes, _ = minutes_of(gm, DropAction(item_name="Canned Beans"))
        self.assertEqual(bag.contents, [])
        self.assertIn(beans, gm.current_location.entities)
        self.assertEqual(minutes, 1)

    def test_an_item_in_a_carried_bag_can_be_eaten(self):
        gm = home()
        (bag,) = give(gm, "item_schoolbag")
        bag.contents.append(entity("item_canned_beans"))
        gm.player.stats.set(CharacterStat.HUNGER, 0.5)
        simulate(gm, UseItemAction(item_name="Canned Beans"))
        self.assertEqual(bag.contents, [])
        self.assertLess(gm.player.stats.get(CharacterStat.HUNGER), 0.5)

    def test_an_item_in_a_carried_bag_can_be_worn(self):
        gm = home()
        (bag,) = give(gm, "item_schoolbag")
        jacket = entity("item_black_jacket")
        bag.contents.append(jacket)
        simulate(gm, WearAction(item_name="Black jacket"))
        self.assertEqual(bag.contents, [])
        self.assertIs(gm.player.worn[BodyLocation.JACKET], jacket)

    def test_a_bag_on_the_ground_is_opened_only_by_taking_it(self):
        gm = home()
        bag = entity("item_toolbox")
        bag.contents.append(entity("item_hammer"))
        gm.current_location.entities.append(bag)
        _, facts = minutes_of(gm, TakeAction(item_name="Hammer"))
        self.assertTrue(facts[0].startswith("Refused"))
        simulate(gm, TakeAction(item_name="Toolbox"))
        self.assertIn(bag, gm.player.inventory)
        self.assertEqual([e.item.id for e in bag.contents], ["item_hammer"])

    def test_the_slot_count_is_gone(self):
        self.assertFalse(
            hasattr(PlayerEntity(name="x", current_location_id="y"), "max_inventory_size")
        )


class StrengthXpTests(unittest.TestCase):
    """carrying-and-loot: Strength XP."""

    def test_a_moving_minute_is_three_or_four_checks_of_one_in_twenty(self):
        four_checks = ScriptedRandom(random=[0.5, 0.01, 0.99, 0.99, 0.01])
        self.assertEqual(carry.strength_xp_rolls(four_checks, 1), 2)
        three_checks = ScriptedRandom(random=[0.9, 0.04, 0.04, 0.06, 0.0])
        self.assertEqual(carry.strength_xp_rolls(three_checks, 1), 2)

    def test_the_expectation_is_0_375_xp_a_minute(self):
        rng = random.Random(7)
        minutes = 20000
        xp = 2 * carry.strength_xp_rolls(rng, minutes)
        self.assertAlmostEqual(xp / minutes, 0.375, delta=0.02)

    def walk(self, gm: GameManager, action):
        with mock.patch("managers.simulation.carry.strength_xp_rolls", return_value=2) as hits:
            simulate(gm, action)
        return hits

    def test_above_half_capacity_a_walk_pays_two_xp_a_hit(self):
        gm = bare_game(0, "item_hammer", "item_hammer", "item_bandage")  # 3.1 of 6
        gm.player.current_location_id = "zone_clinic"
        before = gm.player.skills["strength"].xp
        hits = self.walk(gm, MoveAction(destination="out"))
        hits.assert_called_once()
        # the clinic is ten minutes' walk from the neighborhood
        self.assertEqual(hits.call_args.args[1], 10)
        self.assertEqual(gm.player.skills["strength"].xp - before, 4.0)

    def test_at_half_capacity_or_less_there_is_nothing(self):
        gm = bare_game(0, "item_hammer", "item_hammer")  # 3.0 of 6
        self.walk(gm, MoveAction(destination="out")).assert_not_called()

    def test_only_moving_pays(self):
        gm = bare_game(0, "item_barbell")
        self.walk(gm, WaitAction(duration=Duration(minutes=5))).assert_not_called()


class HeavyLoadFactTests(unittest.TestCase):
    """carrying-and-loot: What the narrator and the player see: Heavy Load rising and falling is a fact."""

    def test_taking_the_item_that_tips_the_load_says_so(self):
        gm = bare_game(0, "item_barbell")
        gm.current_location.entities.append(entity("item_plank"))
        _, facts = minutes_of(gm, TakeAction(item_name="Plank"))
        self.assertIn("Orton is now Very Overloaded.", facts)

    def test_dropping_it_says_the_load_is_gone(self):
        gm = bare_game(0, "item_barbell", "item_plank")
        _, facts = minutes_of(gm, DropAction(item_name="Plank"))
        self.assertIn("Orton is no longer Very Overloaded.", facts)

    def test_a_level_that_does_not_change_says_nothing(self):
        gm = bare_game(0, "item_barbell")
        gm.current_location.entities.append(entity("item_bandage"))
        _, facts = minutes_of(gm, TakeAction(item_name="Bandage"))
        self.assertIn("Orton is now Weighed Down.", facts)
        gm.current_location.entities.append(entity("item_bandage"))
        _, facts = minutes_of(gm, TakeAction(item_name="Bandage"))
        self.assertFalse([f for f in facts if "Overloaded" in f or "Weighed" in f])


class BagPlaceTests(unittest.TestCase):
    """carrying-and-loot: What the narrator and the player see: where a bag is, in words."""

    def test_the_five_places(self):
        who = player()
        back = entity("item_schoolbag")
        hand = entity("item_toolbox")
        worn = entity("item_satchel")
        packed = entity("item_duffel_bag")
        inner = entity("item_paper_bag")
        packed.contents.append(inner)
        who.equipment[CharacterArmorSlot.SHOULDERS] = back
        who.equipment[CharacterHoldableSlot.LEFT_HAND] = hand
        who.worn[BodyLocation.SATCHEL] = worn
        who.inventory.append(packed)
        self.assertEqual(carry.bag_place(who, back), "on your back")
        self.assertEqual(carry.bag_place(who, hand), "in your hand")
        self.assertEqual(carry.bag_place(who, worn), "worn")
        self.assertEqual(carry.bag_place(who, packed), "in your pack")
        self.assertEqual(carry.bag_place(who, inner), "inside the duffel bag")


class CapacityZeroTests(unittest.TestCase):
    """carrying-and-loot: Edge cases: capacity 0."""

    def test_anything_carried_at_capacity_zero_is_level_four_and_a_full_ratio(self):
        gm = bare_game(0, "item_hammer")
        gm.player.traits.append("weak")
        for effect_stat, value in ((CharacterStat.HUNGER, 0.9), (CharacterStat.THIRST, 0.9)):
            gm.player.stats.set(effect_stat, value)
        set_health(gm.player, 20)
        levels = player_status_effect_levels(gm.player)
        self.assertEqual(carry.player_max_weight(gm.player, levels), 0)
        self.assertEqual(levels[StatusEffect.HEAVY_LOAD], 4)
        ctx = SimulationCore(gm)._stat_context(None)
        self.assertEqual(ctx.carry_ratio, float("inf"))


class CarriedBodyBonesTests(unittest.TestCase):
    """carrying-and-loot: Carrying a corpse: a carried body that turns to bones weighs less."""

    def test_the_weight_follows_the_body_at_the_next_action(self):
        from tests.corpses.test_carry import carrying

        gm, corpse = carrying()
        gm.player.worn.clear()
        gm.player.inventory.clear()
        corpse.skeleton = True
        simulate(gm, WaitAction(duration=Duration(minutes=1)))
        self.assertTrue(gm.player.carrying_skeleton)
        self.assertAlmostEqual(carry.carried_weight(gm.player), 2.1)


class TakeTimeTests(unittest.TestCase):
    """carrying-and-loot: Moving things: a single ground take is 50 frames a kilo, then traits."""

    def test_all_thumbs_taking_a_three_kilo_plank_is_300_frames_and_two_minutes(self):
        gm = home()
        gm.player.traits.append("allthumbs")
        gm.current_location.entities.append(entity("item_plank"))
        minutes, _ = minutes_of(gm, TakeAction(item_name="Plank"))
        self.assertEqual(minutes, 2)


class BagEffectiveCapacityTests(unittest.TestCase):
    """carrying-and-loot: Containers: a bag holds the lesser of its capacity and 50 kg less its own weight."""

    def setUp(self):
        self.gm = home()
        self.bag = ItemEntity(
            item=ContainerItem(
                id="item_test_big_bag",
                name="Big Bag",
                description="Huge.",
                max_hit_points=1,
                tags=[],
                slots=[CharacterHoldableSlot.LEFT_HAND],
                capacity=60,
                weight_reduction=0,
                weight=5,
            )
        )
        self.gm.player.inventory.append(self.bag)

    def ballast(self, kg: float) -> ItemEntity:
        item = HoldableItem(
            id="item_test_ballast",
            name="Ballast",
            description="Dead weight.",
            max_hit_points=1,
            tags=[],
            slots=[CharacterHoldableSlot.RIGHT_HAND],
            is_two_handed=False,
            weight=kg,
        )
        made = ItemEntity(item=item)
        self.gm.player.inventory.append(made)
        return made

    def test_a_put_that_fits_the_capacity_but_not_fifty_less_the_bag_is_refused(self):
        self.ballast(45.5)
        _, facts = minutes_of(self.gm, PutAction(item_name="Ballast", target_name="Big Bag"))
        self.assertEqual(self.bag.contents, [])
        self.assertIn("The Big Bag is full.", " ".join(facts))

    def test_exactly_fifty_less_the_bag_fits(self):
        self.ballast(45.0)
        minutes_of(self.gm, PutAction(item_name="Ballast", target_name="Big Bag"))
        self.assertEqual(len(self.bag.contents), 1)
