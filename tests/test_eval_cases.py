"""The hand-run parser cases stay valid against the verb registry (llm-contract: Checking the models)."""

import unittest
from pathlib import Path

import yaml

from data.items import ITEMS
from managers.game import GameManager
from modules.action.parser import parse_action_plan

CASES = yaml.safe_load(
    (Path(__file__).resolve().parent.parent / "evals" / "parser_cases.yaml").read_text("utf-8")
)


class ParserCaseFileTests(unittest.TestCase):
    def test_every_expected_line_parses(self):
        for case in CASES:
            with self.subTest(case=case["name"]):
                actions, failures = parse_action_plan(list(case["expect"]))
                self.assertEqual(failures, [])
                self.assertEqual(len(actions), len(case["expect"]))

    def test_every_case_names_a_real_zone(self):
        zones = GameManager().world.locations
        for case in CASES:
            self.assertIn(case["zone"], zones, case["name"])

    def test_every_carried_item_exists(self):
        for case in CASES:
            for item_id in case.get("carrying", []):
                self.assertIn(item_id, ITEMS, case["name"])

    def test_the_unsupported_cases_are_present_in_both_directions(self):
        expected = {
            ("drink from the tap", ("UNSUPPORTED drink from the tap",)),
            ("put on the schoolbag", ("UNSUPPORTED put on the schoolbag",)),
            ("eat the chocolate bar", ("USE_ITEM Chocolate Bar",)),
            ("go outside", ("MOVE_TO out",)),
        }
        present = {(case["input"], tuple(case["expect"])) for case in CASES}
        self.assertTrue(expected <= present)

    def test_the_cases_the_spec_names_are_present(self):
        expected = {
            ("I creep down to the lobby", ("STANCE sneak", "MOVE_TO building")),
            ("tell Emma she looks great", ('TALK Emma compliment "words"',)),
            ("I scream for help", ("SHOUT",)),
        }
        present = {(case["input"], tuple(case["expect"])) for case in CASES}
        self.assertTrue(expected <= present)


class SamePlanTests(unittest.TestCase):
    """llm-contract: Checking the models: a plan is judged by what the engine makes of it."""

    def setUp(self):
        from scripts.eval_parser import same_plan

        self.same_plan = same_plan
        self.manager = GameManager()
        self.manager.player.current_location_id = "zone_street"

    def test_a_talk_matches_by_whether_it_carries_words(self):
        said, _ = parse_action_plan(['TALK Emma chat "we leave at dawn"'])
        other, _ = parse_action_plan(['TALK Emma chat "words"'])
        silent, _ = parse_action_plan(["TALK Emma chat"])
        self.assertTrue(self.same_plan(self.manager, said, other))
        self.assertFalse(self.same_plan(self.manager, said, silent))

    def test_a_move_matches_by_the_zone_it_reaches(self):
        got, _ = parse_action_plan(["MOVE_TO In"])
        want, _ = parse_action_plan(["MOVE_TO in"])
        self.assertTrue(self.same_plan(self.manager, got, want))

    def test_a_zone_alias_matches_the_zone(self):
        self.manager.player.current_location_id = "zone_home"
        got, _ = parse_action_plan(["MOVE_TO lobby"])
        want, _ = parse_action_plan(["MOVE_TO building"])
        self.assertTrue(self.same_plan(self.manager, got, want))

    def test_a_move_to_another_zone_does_not_match(self):
        got, _ = parse_action_plan(["MOVE_TO neighborhood"])
        want, _ = parse_action_plan(["MOVE_TO in"])
        self.assertFalse(self.same_plan(self.manager, got, want))

    def test_other_actions_still_match_exactly(self):
        got, _ = parse_action_plan(["TAKE Crowbar"])
        want, _ = parse_action_plan(["TAKE Water Bottle"])
        self.assertFalse(self.same_plan(self.manager, got, want))
