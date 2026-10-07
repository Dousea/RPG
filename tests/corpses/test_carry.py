"""carrying-and-loot: Carrying a corpse: CARRY, DROP corpse and what a body in the arms refuses."""

import random
import unittest

from data.items import ITEMS
from managers import carry
from managers.corpses.sickness import corpse_count
from managers.game import GameManager
from managers.simulation import SimulationCore
from managers.validator import ActionValidator, Rejected
from modules.action.types import (
    AttackAction,
    BandageAction,
    BarricadeAction,
    CarryAction,
    DisinfectAction,
    DropAction,
    Duration,
    EquipAction,
    ExerciseAction,
    MoveAction,
    PutAction,
    RemoveBandageAction,
    SearchAction,
    ShoutAction,
    ShoveAction,
    SleepAction,
    StanceAction,
    TakeAction,
    TalkAction,
    UnbarricadeAction,
    UnequipAction,
    UseItemAction,
    WaitAction,
)
from modules.body.stats import CharacterStat, StatusEffect
from modules.character.equipment import CharacterArmorSlot, CharacterHoldableSlot
from modules.entity.corpse import CorpseEntity
from modules.entity.item import ItemEntity
from tests.support import simulate
from tests.test_simulation import zombie_game

NAME = "Orton"


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


def with_body(**fields) -> tuple[GameManager, CorpseEntity]:
    gm = zombie_game()
    corpse = body(**fields)
    gm.world.corpses["c1"] = corpse
    return gm, corpse


def minutes_of(gm: GameManager, *actions) -> tuple[int, list[str]]:
    before = gm.narrative.minutes
    facts = simulate(gm, *actions, rng=random.Random(1))
    return gm.narrative.minutes - before, facts


def carrying() -> tuple[GameManager, CorpseEntity]:
    gm, corpse = with_body()
    simulate(gm, CarryAction(corpse_name="c1"), rng=random.Random(1))
    assert gm.player.carrying_corpse == "c1"
    return gm, corpse


def entity(item_id: str) -> ItemEntity:
    return ItemEntity(item=ITEMS[item_id])


class CarryTests(unittest.TestCase):
    """carrying-and-loot: Carrying a corpse: picking up and putting down."""

    def test_carry_takes_a_minute_and_the_body_is_in_the_arms(self):
        gm, corpse = with_body()
        minutes, facts = minutes_of(gm, CarryAction(corpse_name="c1"))
        self.assertEqual(minutes, 1)
        self.assertEqual(gm.player.carrying_corpse, "c1")
        self.assertEqual(corpse.gap, 0.0)
        self.assertEqual(facts[0], f"{NAME} hauls the body up and carries it.")

    def test_corpse_means_the_nearest(self):
        gm, near = with_body(gap=2.0)
        gm.world.corpses["c2"] = body(corpse_id="c2", gap=5.0)
        simulate(gm, CarryAction(corpse_name="corpse"), rng=random.Random(1))
        self.assertEqual(gm.player.carrying_corpse, "c1")

    def test_a_body_further_than_a_tile_is_walked_up_to_first(self):
        gm, _ = with_body(gap=11.0)
        minutes, _ = minutes_of(gm, CarryAction(corpse_name="c1"))
        self.assertGreater(minutes, 1)
        self.assertEqual(gm.player.carrying_corpse, "c1")

    def test_a_carried_body_weighs_6_and_a_skeleton_2_1(self):
        gm, _ = carrying()
        gm.player.worn.clear()
        gm.player.inventory.clear()
        self.assertAlmostEqual(carry.carried_weight(gm.player), 6.0)
        gm2, _ = with_body(skeleton=True)
        simulate(gm2, CarryAction(corpse_name="c1"), rng=random.Random(1))
        gm2.player.worn.clear()
        gm2.player.inventory.clear()
        self.assertAlmostEqual(carry.carried_weight(gm2.player), 2.1)

    def test_the_weight_feeds_heavy_load(self):
        gm, _ = carrying()
        gm.player.worn.clear()
        gm.player.skills["strength"].level = 0
        gm.player.inventory = [entity("item_barbell")]  # 6 + 6 against 6
        from managers.body.stats.status_effects import player_status_effect_levels

        self.assertEqual(player_status_effect_levels(gm.player)[StatusEffect.HEAVY_LOAD], 4)

    def test_drop_corpse_puts_it_down_at_a_tile(self):
        gm, corpse = carrying()
        minutes, facts = minutes_of(gm, DropAction(item_name="corpse", corpse=True))
        self.assertEqual(minutes, 1)
        self.assertIsNone(gm.player.carrying_corpse)
        self.assertEqual(corpse.gap, 1.0)
        self.assertEqual(corpse.zone_id, "zone_street")
        self.assertEqual(facts[0], f"{NAME} lets the body fall.")

    def test_the_body_follows_the_player_and_keeps_its_gap(self):
        gm, corpse = carrying()
        simulate(gm, MoveAction(destination="Your Building"), rng=random.Random(1))
        self.assertEqual(gm.player.current_location_id, "zone_building")
        self.assertEqual(corpse.zone_id, "zone_building")
        self.assertEqual(corpse.gap, 0.0)

    def test_moving_it_out_of_a_zone_lowers_that_zones_corpse_count_by_one(self):
        gm, _ = carrying()
        self.assertEqual(corpse_count(gm.world, "zone_street"), 1)
        simulate(gm, MoveAction(destination="Your Building"), rng=random.Random(1))
        self.assertEqual(corpse_count(gm.world, "zone_street"), 0)
        self.assertEqual(corpse_count(gm.world, "zone_building"), 1)

    def test_a_body_dropped_in_the_new_zone_stays_there(self):
        gm, corpse = carrying()
        simulate(
            gm,
            MoveAction(destination="Your Building"),
            DropAction(item_name="corpse", corpse=True),
            rng=random.Random(1),
        )
        self.assertEqual(corpse.zone_id, "zone_building")
        self.assertEqual(corpse.gap, 1.0)

    def test_a_body_that_rots_away_is_no_longer_in_the_arms(self):
        gm, corpse = carrying()
        del gm.world.corpses["c1"]
        simulate(gm, WaitAction(duration=Duration(minutes=1)), rng=random.Random(1))
        self.assertIsNone(gm.player.carrying_corpse)
        gm.player.worn.clear()
        gm.player.inventory.clear()
        self.assertEqual(carry.carried_weight(gm.player), 0.0)

    def test_a_fake_dead_body_in_the_arms_does_not_get_up(self):
        gm, corpse = with_body(fake_dead=True)
        simulate(gm, CarryAction(corpse_name="c1"), rng=random.Random(1))
        corpse.died_at = -10_000
        simulate(
            gm,
            MoveAction(destination="Your Building"),
            MoveAction(destination="The Street"),
            rng=random.Random(1),
        )
        self.assertIn("c1", gm.world.corpses)
        self.assertEqual(gm.player.carrying_corpse, "c1")


class CarryRefusalTests(unittest.TestCase):
    """carrying-and-loot: Carrying a corpse: the refusals."""

    def reason(self, gm: GameManager, action) -> str:
        result = ActionValidator(gm).validate(action)
        assert isinstance(result, Rejected), result
        return result.reason

    def test_a_sleeper_cannot_carry(self):
        gm, _ = with_body()
        gm.player.asleep = True
        self.assertEqual(self.reason(gm, CarryAction(corpse_name="c1")), f"{NAME} is asleep.")

    def test_no_such_corpse(self):
        gm, _ = with_body()
        self.assertIn("c9", self.reason(gm, CarryAction(corpse_name="c9")))

    def test_already_carrying_one(self):
        gm, _ = carrying()
        gm.world.corpses["c2"] = body(corpse_id="c2")
        self.assertEqual(
            self.reason(gm, CarryAction(corpse_name="c2")), f"{NAME} is already carrying a body."
        )

    def test_a_hand_in_use_refuses(self):
        for slot in CharacterHoldableSlot:
            gm, _ = with_body()
            gm.player.equipment[slot] = entity("item_hammer")
            self.assertEqual(
                self.reason(gm, CarryAction(corpse_name="c1")), f"{NAME}'s hands are full."
            )

    def test_a_bag_on_the_back_does_not_refuse(self):
        gm, _ = with_body()
        gm.player.equipment[CharacterArmorSlot.SHOULDERS] = entity("item_schoolbag")
        simulate(gm, CarryAction(corpse_name="c1"), rng=random.Random(1))
        self.assertEqual(gm.player.carrying_corpse, "c1")

    def test_a_body_that_rose_while_closing_in_is_gone(self):
        gm, corpse = with_body(gap=11.0)
        core = SimulationCore(gm, rng=random.Random(1))
        original = core._spend

        def spend(minutes, action=None, **kwargs):
            gm.world.corpses.pop("c1", None)
            return original(minutes, action, **kwargs)

        core._spend = spend  # type: ignore[method-assign]
        facts = core.resolve([CarryAction(corpse_name="c1")])
        self.assertIsNone(gm.player.carrying_corpse)
        self.assertTrue(any("c1" in fact for fact in facts))

    def test_drop_corpse_with_nothing_in_the_arms(self):
        gm, _ = with_body()
        self.assertEqual(
            self.reason(gm, DropAction(item_name="corpse", corpse=True)),
            f"{NAME} is not carrying a body.",
        )

    def test_these_verbs_are_refused_while_carrying(self):
        gm, _ = carrying()
        gm.player.inventory.append(entity("item_canned_beans"))
        actions = [
            EquipAction(item_name="Canned Beans"),
            UnequipAction(item_name="Hammer"),
            AttackAction(target_name="z1"),
            ShoveAction(target_name="z1"),
            UseItemAction(item_name="Canned Beans"),
            TakeAction(item_name="Crowbar"),
            PutAction(item_name="Canned Beans", target_name="Schoolbag"),
            SearchAction(target_name="c1"),
            BandageAction(part_name="left hand"),
            RemoveBandageAction(part_name="left hand"),
            DisinfectAction(part_name="left hand"),
            BarricadeAction(barrier_name="shop window"),
            UnbarricadeAction(barrier_name="shop window"),
            ExerciseAction(exercise_name="Squats"),
            SleepAction(),
        ]
        for action in actions:
            self.assertEqual(self.reason(gm, action), f"{NAME} is carrying a body.", action)

    def test_these_verbs_stay_available_while_carrying(self):
        gm, _ = carrying()
        validator = ActionValidator(gm)
        for action in (
            MoveAction(destination="Your Building"),
            WaitAction(duration=Duration(minutes=5)),
            StanceAction(sneaking=True),
            ShoutAction(),
            DropAction(item_name="corpse", corpse=True),
        ):
            self.assertNotIsInstance(validator.validate(action), Rejected, action)

    def test_talk_stays_available(self):
        gm, _ = carrying()
        gm.player.current_location_id = "zone_building"
        result = ActionValidator(gm).validate(TalkAction(npc_name="Emma", approach="chat"))
        self.assertNotIsInstance(result, Rejected)


class CarryEnduranceTests(unittest.TestCase):
    """carrying-and-loot: Carrying a corpse: moving with a body is exercising at 8.75 times the drain."""

    def test_a_walk_with_a_body_costs_more_endurance_than_one_without(self):
        gm, _ = carrying()
        gm.player.stats.set(CharacterStat.ENDURANCE, 1.0)
        simulate(gm, MoveAction(destination="Your Building"), rng=random.Random(1))
        with_body_drop = 1.0 - gm.player.stats.get(CharacterStat.ENDURANCE)
        plain = zombie_game()
        plain.player.stats.set(CharacterStat.ENDURANCE, 1.0)
        simulate(plain, MoveAction(destination="Your Building"), rng=random.Random(1))
        without_drop = 1.0 - plain.player.stats.get(CharacterStat.ENDURANCE)
        self.assertGreater(with_body_drop, without_drop + 0.1)
