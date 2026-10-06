"""The hand-run parser cases stay valid against the verb registry (spec 10, Checking the models)."""

import unittest
from pathlib import Path

import yaml

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

    def test_the_cases_the_spec_names_are_present(self):
        expected = {
            ("I creep down to the lobby", ("STANCE sneak", "MOVE_TO building")),
            ("tell Emma she looks great", ("TALK Emma compliment",)),
            ("I scream for help", ("SHOUT",)),
        }
        present = {(case["input"], tuple(case["expect"])) for case in CASES}
        self.assertTrue(expected <= present)
