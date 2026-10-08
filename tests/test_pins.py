"""llm-contract: Pinned mentions: binding to parsed actions and resolving exactly that entity."""

import unittest
from unittest import mock

from managers.game import GameManager
from managers.mentions import mentionables
from managers.simulation import SimulationCore
from managers.validator import Accepted, ActionValidator, Rejected
from modules.action.pins import MENTION_MARK, Mention, Pinned, bind, pin_of, render_input
from modules.action.types import (
    AttackAction,
    BandageAction,
    CloseAction,
    MoveAction,
    OpenAction,
    PutAction,
    SearchAction,
    ShoveAction,
    TakeAction,
    TalkAction,
)
from modules.entity.zombie import ZombieState
from modules.resolution import (
    MoveToRoom,
    MoveToZone,
    TargetBarrier,
    TargetContainer,
    TargetNpc,
    TargetZombie,
)
from tests.test_simulation import add_zombie, zombie_game


def pick(gm: GameManager, kind: str, entity_id: str) -> Mention:
    return next(m for m in mentionables(gm) if (m.kind, m.id) == (kind, entity_id))


Z32 = Mention("zombie", "z32", "zombie", "close, coming at you")
Z33 = Mention("zombie", "z33", "zombie", "close, coming at you")


class BindTests(unittest.TestCase):
    """llm-contract: A pinned id overrides the parsed target of the action that names one of that kind."""

    def test_a_pin_replaces_what_the_parser_wrote(self):
        (action,) = bind([AttackAction("z33")], [Z32])
        assert isinstance(action, AttackAction)
        self.assertEqual(action.target_name, "z32")
        pin = pin_of(action.target_name, "zombie")
        assert pin is not None
        self.assertEqual(pin.entity_id, "z32")

    def test_a_pin_takes_the_action_that_already_names_it_before_the_first_free_one(self):
        first, second = bind([AttackAction("zombie"), AttackAction("z32")], [Z32])
        assert isinstance(first, AttackAction) and isinstance(second, AttackAction)
        self.assertNotIsInstance(first.target_name, Pinned)
        self.assertIsInstance(second.target_name, Pinned)

    def test_pins_fill_free_fields_in_order(self):
        first, second = bind([ShoveAction("zombie"), AttackAction("zombie")], [Z32, Z33])
        assert isinstance(first, ShoveAction) and isinstance(second, AttackAction)
        self.assertEqual((first.target_name, second.target_name), ("z32", "z33"))

    def test_a_pin_of_another_kind_is_left_alone(self):
        (action,) = bind([TalkAction("Emma", "chat")], [Z32])
        assert isinstance(action, TalkAction)
        self.assertNotIsInstance(action.npc_name, Pinned)

    def test_an_empty_part_field_takes_a_pinned_part(self):
        part = Mention("body_part", "hand_l", "left hand", "scratch")
        (action,) = bind([BandageAction()], [part])
        assert isinstance(action, BandageAction)
        self.assertEqual(action.part_name, "left hand")

    def test_a_pinned_source_is_not_invented_for_an_item_with_none(self):
        corpse = Mention("corpse", "c1", "body", "close")
        (action,) = bind([TakeAction("bat")], [corpse])
        assert isinstance(action, TakeAction)
        self.assertIsNone(action.from_name)
        (action,) = bind([TakeAction("bat", from_name="body")], [corpse])
        assert isinstance(action, TakeAction)
        self.assertEqual(action.from_name, "c1")

    def test_a_pinned_name_still_reads_as_the_scene_name(self):
        window = Mention("barrier", "window_supermarket", "supermarket window", "closed")
        (action,) = bind([OpenAction("window")], [window])
        assert isinstance(action, OpenAction)
        self.assertEqual(action.barrier_name, "supermarket window")


class RenderTests(unittest.TestCase):
    """llm-contract: The parser sees the pick as the id or name the scene uses, marked as pinned."""

    def test_the_parser_reads_the_written_id_and_everyone_else_the_name(self):
        text = f"hit {MENTION_MARK} with the bat"
        self.assertEqual(
            render_input(text, [Z32], for_parser=True), "hit [pinned: z32] with the bat"
        )
        self.assertEqual(render_input(text, [Z32], for_parser=False), "hit zombie with the bat")

    def test_a_typed_at_sign_is_plain_prose(self):
        self.assertEqual(render_input("hit @z32", [], for_parser=True), "hit @z32")

    def test_a_mark_with_no_mention_is_dropped(self):
        self.assertEqual(render_input(f"a{MENTION_MARK}b", [], for_parser=True), "ab")


class ResolveTests(unittest.TestCase):
    """llm-contract: The validator resolves a pinned mention to exactly that entity."""

    def validate(self, gm: GameManager, action):
        return ActionValidator(gm).validate(action)

    def test_a_pinned_zombie_is_the_one_attacked_not_the_nearest(self):
        gm = zombie_game()
        near = add_zombie(gm, gap=2, state=ZombieState.CHASING)
        far = add_zombie(gm, gap=4, state=ZombieState.CHASING)
        (action,) = bind([AttackAction("zombie")], [pick(gm, "zombie", far.zombie_id)])
        result = self.validate(gm, action)
        assert isinstance(result, Accepted)
        self.assertEqual(result.expect(TargetZombie).zombie_id, far.zombie_id)
        self.assertNotEqual(near.zombie_id, far.zombie_id)

    def test_a_pinned_zone_moves_there_without_phrase_matching(self):
        gm = zombie_game("zone_street")
        for barrier in gm.world.barriers.values():
            barrier.open = True
        (action,) = bind([MoveAction("somewhere else")], [pick(gm, "zone", "zone_neighborhood")])
        with mock.patch.object(GameManager, "resolve_location") as resolve:
            result = self.validate(gm, action)
        resolve.assert_not_called()
        assert isinstance(result, Accepted)
        self.assertEqual(result.expect(MoveToZone).location.id, "zone_neighborhood")

    def test_a_pinned_room_is_moved_into(self):
        gm = GameManager()
        gm.player.current_room = "kitchen"
        (action,) = bind([MoveAction("there")], [pick(gm, "room", "bedroom")])
        result = self.validate(gm, action)
        assert isinstance(result, Accepted)
        self.assertEqual(result.expect(MoveToRoom).room.room_id, "bedroom")

    def test_a_pinned_container_skips_the_which_one_question(self):
        gm = GameManager()
        gm.player.current_room = None
        counter = pick(gm, "container", "kitchen_counter")
        bare = self.validate(gm, SearchAction("counter"))
        self.assertIsInstance(bare, Rejected)
        assert isinstance(bare, Rejected)
        self.assertIn("Which one", bare.reason)
        (action,) = bind([SearchAction("counter")], [counter])
        result = self.validate(gm, action)
        assert isinstance(result, Accepted)
        self.assertEqual(result.expect(TargetContainer).container.container_id, counter.id)

    def test_a_pinned_container_goes_into_put_without_a_bag_lookup(self):
        gm = GameManager()
        counter = pick(gm, "container", "kitchen_counter")
        (action,) = bind([PutAction("Bandage", "counter")], [counter])
        assert isinstance(action, PutAction)
        self.assertIsInstance(action.target_name, Pinned)

    def test_a_pinned_barrier_of_a_neighbouring_zone_is_the_one_swung_at(self):
        gm = zombie_game("zone_neighborhood")
        gm.world.barriers["window_supermarket"].open = False
        pinned = pick(gm, "barrier", "window_supermarket")
        (action,) = bind([AttackAction("window")], [pinned])
        result = self.validate(gm, action)
        assert isinstance(result, Accepted)
        self.assertEqual(result.expect(TargetBarrier).barrier.barrier_id, "window_supermarket")

    def test_a_pinned_barrier_out_of_the_zone_is_refused(self):
        gm = zombie_game("zone_neighborhood")
        far = Mention("barrier", "door_apartment", "apartment door", "closed")
        (action,) = bind([CloseAction("door")], [far])
        result = self.validate(gm, action)
        self.assertIsInstance(result, Rejected)

    def test_a_pinned_npc_is_resolved_by_id(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        marcus = next(n for n in gm.npcs.values() if n.name == "Marcus")
        (action,) = bind([AttackAction("Emma")], [pick(gm, "npc", marcus.npc_id)])
        result = self.validate(gm, action)
        assert isinstance(result, Accepted)
        self.assertIs(result.expect(TargetNpc).npc, marcus)

    def test_a_pinned_mention_out_of_reach_is_refused_with_the_first_actions_kept(self):
        gm = zombie_game("zone_neighborhood")
        gm.world.barriers["window_supermarket"].open = False
        pinned = pick(gm, "barrier", "window_supermarket")
        gm.player.current_location_id = "zone_hardware"
        actions = bind([AttackAction("window")], [pinned])
        facts = SimulationCore(gm).resolve(actions)
        self.assertTrue(facts[0].startswith("Refused:"), facts)


if __name__ == "__main__":
    unittest.main()
