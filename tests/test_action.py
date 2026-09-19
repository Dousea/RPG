"""Parsing of ACTIONS: lines into typed proposals (shape only, no resolution)."""

import unittest

from modules.action import (
    AttackAction,
    MoveAction,
    NpcMoveAction,
    NpcStatusAction,
    ParseFailure,
    TakeAction,
    UpdateConditionAction,
    UpdateInventoryAction,
    UpdateRelationshipAction,
    UseItemAction,
    parse_action_line,
    parse_action_plan,
)


class ParseActionLineTests(unittest.TestCase):
    def test_move_to(self):
        self.assertEqual(parse_action_line("MOVE_TO north"), MoveAction(destination="north"))

    def test_take(self):
        self.assertEqual(parse_action_line("TAKE Crowbar"), TakeAction(item_name="Crowbar"))

    def test_attack_is_a_new_verb(self):
        self.assertEqual(
            parse_action_line("ATTACK Zombie"), AttackAction(target_name="Zombie")
        )

    def test_use_item_is_a_new_verb(self):
        self.assertEqual(
            parse_action_line("USE_ITEM First Aid Kit"),
            UseItemAction(item_name="First Aid Kit"),
        )

    def test_update_condition_health_is_retired(self):
        result = parse_action_line("UPDATE_CONDITION health +9999")
        self.assertIsInstance(result, ParseFailure)
        self.assertIn("not an available action", result.reason)

    def test_update_condition_hunger_still_works(self):
        self.assertEqual(
            parse_action_line("UPDATE_CONDITION hunger -10"),
            UpdateConditionAction(field_name="hunger", raw_value="-10"),
        )

    def test_unknown_verb(self):
        result = parse_action_line("FROBNICATE the widget")
        self.assertIsInstance(result, ParseFailure)
        self.assertIn("Unknown action verb", result.reason)

    def test_update_relationship(self):
        self.assertEqual(
            parse_action_line("UPDATE_RELATIONSHIP Emma affection +12"),
            UpdateRelationshipAction(npc_name="Emma", axis="affection", amount=12),
        )

    def test_update_relationship_unknown_axis(self):
        result = parse_action_line("UPDATE_RELATIONSHIP Emma loyalty +1")
        self.assertIsInstance(result, ParseFailure)

    def test_update_inventory(self):
        self.assertEqual(
            parse_action_line("UPDATE_INVENTORY Canned Beans UPDATE_QUANTITY 3"),
            UpdateInventoryAction(
                item_name="Canned Beans", operation="UPDATE_QUANTITY", value="3"
            ),
        )

    def test_npc_move_needs_the_to_separator(self):
        result = parse_action_line("NPC_MOVE Emma Lobby")
        self.assertIsInstance(result, ParseFailure)

    def test_npc_move(self):
        self.assertEqual(
            parse_action_line("NPC_MOVE Emma TO Lobby"),
            NpcMoveAction(npc_name="Emma", destination="Lobby"),
        )

    def test_npc_status(self):
        self.assertEqual(
            parse_action_line("NPC_STATUS Emma ADD frightened"),
            NpcStatusAction(npc_name="Emma", operation="ADD", status="frightened"),
        )

    def test_malformed_line_never_raises(self):
        for line in (
            "UPDATE_RELATIONSHIP",
            "NPC_STATUS ADD",
            "UPDATE_INVENTORY",
            "SET_FLAG",
            "ADD_GOAL",
        ):
            result = parse_action_line(line)
            self.assertIsInstance(result, ParseFailure)
            self.assertTrue(result.reason)


class ParseActionPlanTests(unittest.TestCase):
    def test_none_and_blank_lines_produce_nothing(self):
        actions, failures = parse_action_plan(["NONE", "", "   "])
        self.assertEqual(actions, [])
        self.assertEqual(failures, [])

    def test_leading_bullet_is_tolerated(self):
        actions, failures = parse_action_plan(["- TAKE Crowbar"])
        self.assertEqual(actions, [TakeAction(item_name="Crowbar")])
        self.assertEqual(failures, [])

    def test_mixed_valid_and_invalid_lines(self):
        actions, failures = parse_action_plan(
            ["MOVE_TO north", "FROBNICATE x", "TAKE Crowbar"]
        )
        self.assertEqual(
            actions, [MoveAction(destination="north"), TakeAction(item_name="Crowbar")]
        )
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].raw, "FROBNICATE x")


if __name__ == "__main__":
    unittest.main()
