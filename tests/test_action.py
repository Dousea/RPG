"""Parsing of ACTIONS: lines into typed proposals (shape only, no resolution)."""

import unittest

from modules.action.parser import ParseFailure, parse_action_line, parse_action_plan
from modules.action.types import (
    AddGoalAction,
    AttackAction,
    Duration,
    MoveAction,
    NpcMoveAction,
    NpcStatusAction,
    RemoveGoalAction,
    SetFlagAction,
    SleepAction,
    StanceAction,
    TakeAction,
    TakeOffAction,
    UpdateConditionAction,
    UpdateInventoryAction,
    UpdateRelationshipAction,
    UseItemAction,
    WaitAction,
    WearAction,
)


class ClockActionTests(unittest.TestCase):
    """Spec 01, Actions."""

    def test_wait_parses_every_duration_form(self):
        cases = {
            "WAIT 10m": Duration(minutes=10),
            "WAIT 2h": Duration(minutes=120),
            "WAIT 1h30m": Duration(minutes=90),
            "WAIT 1H 30M": Duration(minutes=90),
            "WAIT until night": Duration(until_time_of_day="night"),
            "WAIT until Morning.": Duration(until_time_of_day="morning"),
            "WAIT until 14:30": Duration(until_minute_of_day=870),
            "WAIT until 6:05": Duration(until_minute_of_day=365),
        }
        for line, duration in cases.items():
            with self.subTest(line=line):
                self.assertEqual(parse_action_line(line), WaitAction(duration=duration))

    def test_sleep_parses_with_and_without_a_duration(self):
        self.assertEqual(parse_action_line("SLEEP"), SleepAction())
        self.assertEqual(parse_action_line("SLEEP 8h"), SleepAction(duration=Duration(minutes=480)))
        self.assertEqual(
            parse_action_line("SLEEP until 07:00"),
            SleepAction(duration=Duration(until_minute_of_day=420)),
        )

    def test_a_malformed_duration_is_a_parse_failure(self):
        for line in (
            "WAIT",
            "WAIT soon",
            "WAIT 0m",
            "WAIT 5",
            "WAIT 1h30",
            "WAIT until",
            "WAIT until 25:00",
            "WAIT until 12:60",
            "WAIT until 12:3",
            "SLEEP lots",
        ):
            with self.subTest(line=line):
                self.assertIsInstance(parse_action_line(line), ParseFailure)

    def test_time_advance_is_an_unknown_action(self):
        result = parse_action_line("TIME_ADVANCE evening")
        assert isinstance(result, ParseFailure)
        self.assertIn("Unknown action verb", result.reason)


class ParseActionLineTests(unittest.TestCase):
    def test_move_to(self):
        self.assertEqual(parse_action_line("MOVE_TO north"), MoveAction(destination="north"))

    def test_take(self):
        self.assertEqual(parse_action_line("TAKE Crowbar"), TakeAction(item_name="Crowbar"))

    def test_attack_is_a_new_verb(self):
        self.assertEqual(parse_action_line("ATTACK Zombie"), AttackAction(target_name="Zombie"))

    def test_use_item_is_a_new_verb(self):
        self.assertEqual(
            parse_action_line("USE_ITEM First Aid Kit"),
            UseItemAction(item_name="First Aid Kit"),
        )

    def test_update_condition_health_is_retired(self):
        result = parse_action_line("UPDATE_CONDITION health +9999")
        assert isinstance(result, ParseFailure)
        self.assertIn("not an available action", result.reason)

    def test_update_condition_hunger_still_works(self):
        self.assertEqual(
            parse_action_line("UPDATE_CONDITION hunger -10"),
            UpdateConditionAction(field_name="hunger", raw_value="-10"),
        )

    def test_unknown_verb(self):
        result = parse_action_line("FROBNICATE the widget")
        assert isinstance(result, ParseFailure)
        self.assertIn("Unknown action verb", result.reason)

    def test_update_relationship(self):
        self.assertEqual(
            parse_action_line("UPDATE_RELATIONSHIP Emma affection +12"),
            UpdateRelationshipAction(npc_name="Emma", axis="affection", amount=12),
        )

    def test_update_relationship_unknown_axis(self):
        result = parse_action_line("UPDATE_RELATIONSHIP Emma loyalty +1")
        self.assertIsInstance(result, ParseFailure)

    def test_update_relationship_affinity_is_an_affection_synonym(self):
        self.assertEqual(
            parse_action_line("UPDATE_RELATIONSHIP Emma affinity +5"),
            UpdateRelationshipAction(npc_name="Emma", axis="affection", amount=5),
        )

    def test_add_goal_normalizes_a_colon_suffixed_horizon(self):
        self.assertEqual(
            parse_action_line("ADD_GOAL short_term: Find water"),
            AddGoalAction(horizon="short_term", goal_text="Find water"),
        )

    def test_add_goal_normalizes_a_two_word_horizon(self):
        self.assertEqual(
            parse_action_line("ADD_GOAL Short Term Find water"),
            AddGoalAction(horizon="short_term", goal_text="Find water"),
        )

    def test_add_goal_normalizes_a_hyphenated_horizon(self):
        self.assertEqual(
            parse_action_line("ADD_GOAL short-term Find water"),
            AddGoalAction(horizon="short_term", goal_text="Find water"),
        )

    def test_remove_goal_normalizes_a_hyphenated_horizon(self):
        self.assertEqual(
            parse_action_line("REMOVE_GOAL long-term Leave the city"),
            RemoveGoalAction(horizon="long_term", goal_text="Leave the city"),
        )

    def test_add_goal_with_an_unknown_horizon_still_parses(self):
        # Not a synonym, so it falls through to the normalized first word --
        # the validator (not the parser) is what rejects "someday" as a
        # horizon, so ADD_GOAL doesn't ParseFailure here.
        self.assertEqual(
            parse_action_line("ADD_GOAL someday Find water"),
            AddGoalAction(horizon="someday", goal_text="Find water"),
        )

    def test_set_flag_normalizes_name_and_yes_no_value(self):
        self.assertEqual(
            parse_action_line("SET_FLAG Power-Grid yes"),
            SetFlagAction(flag_name="power_grid", value=True),
        )

    def test_set_flag_rejects_an_unrecognized_value(self):
        result = parse_action_line("SET_FLAG x maybe")
        self.assertIsInstance(result, ParseFailure)

    def test_update_condition_normalizes_field_name_and_strips_punctuation(self):
        self.assertEqual(
            parse_action_line("UPDATE_CONDITION Infection_Risk +1."),
            UpdateConditionAction(field_name="infection_risk", raw_value="+1"),
        )

    def test_update_inventory(self):
        self.assertEqual(
            parse_action_line("UPDATE_INVENTORY Canned Beans UPDATE_QUANTITY 3"),
            UpdateInventoryAction(item_name="Canned Beans", operation="UPDATE_QUANTITY", value="3"),
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
            assert isinstance(result, ParseFailure)
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
        actions, failures = parse_action_plan(["MOVE_TO north", "FROBNICATE x", "TAKE Crowbar"])
        self.assertEqual(
            actions, [MoveAction(destination="north"), TakeAction(item_name="Crowbar")]
        )
        self.assertEqual(len(failures), 1)
        self.assertEqual(failures[0].raw, "FROBNICATE x")


class WearParseTests(unittest.TestCase):
    """Spec 05, Actions: WEAR and TAKE_OFF."""

    def test_wear(self):
        self.assertEqual(
            parse_action_line("WEAR Black jacket"), WearAction(item_name="Black jacket")
        )

    def test_take_off(self):
        self.assertEqual(parse_action_line("TAKE_OFF Jeans"), TakeOffAction(item_name="Jeans"))

    def test_wear_needs_an_item(self):
        self.assertIsInstance(parse_action_line("WEAR"), ParseFailure)
        self.assertIsInstance(parse_action_line("TAKE_OFF"), ParseFailure)


if __name__ == "__main__":
    unittest.main()


class PaceParseTests(unittest.TestCase):
    """Spec 09, Pace: MOVE_TO gains a run pace; STANCE toggles sneaking."""

    def test_move_to_defaults_to_walking(self):
        action = parse_action_line("MOVE_TO the street")
        self.assertEqual(action, MoveAction(destination="the street"))
        assert isinstance(action, MoveAction)
        self.assertFalse(action.run)

    def test_move_to_with_run(self):
        self.assertEqual(
            parse_action_line("MOVE_TO the street run"),
            MoveAction(destination="the street", run=True),
        )
        self.assertEqual(
            parse_action_line("MOVE_TO out, running"), MoveAction(destination="out", run=True)
        )

    def test_a_lone_run_is_a_spot_not_a_pace(self):
        self.assertEqual(parse_action_line("MOVE_TO run"), MoveAction(destination="run"))

    def test_stance_sneak_and_stand(self):
        self.assertEqual(parse_action_line("STANCE sneak"), StanceAction(sneaking=True))
        self.assertEqual(parse_action_line("STANCE stand"), StanceAction(sneaking=False))

    def test_a_bad_stance_is_a_parse_failure(self):
        self.assertIsInstance(parse_action_line("STANCE crouch"), ParseFailure)
        self.assertIsInstance(parse_action_line("STANCE"), ParseFailure)
