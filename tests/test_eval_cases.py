"""The hand-run parser cases stay valid against the verb registry (llm-contract: Checking the models)."""

import unittest
from pathlib import Path

import yaml

from data.items import ITEMS
from data.story import check as story_check_k
from managers.game import GameManager
from modules.action.parser import parse_action_plan
from modules.character.equipment import CharacterHoldableSlot
from scripts.eval_parser import scene
from scripts.eval_plan_check import run_case
from tests.support import FakeFactChecker

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

    def test_every_alternative_plan_parses(self):
        for case in CASES:
            for lines in case.get("expect_instead", []):
                with self.subTest(case=case["name"], lines=lines):
                    actions, failures = parse_action_plan(list(lines))
                    self.assertEqual(failures, [])
                    self.assertEqual(len(actions), len(lines))

    def test_a_scene_holds_the_zombies_and_the_weapon_the_case_names(self):
        case = next(c for c in CASES if c["name"] == "stomp one while holding a pan")
        manager = scene(case)
        self.assertEqual(len(manager.world.zombies), case["downed_zombies"])
        self.assertTrue(
            all(z.on_floor(manager.narrative.minutes) for z in manager.world.zombies.values())
        )
        held = manager.player.equipment[CharacterHoldableSlot.RIGHT_HAND]
        assert held is not None
        self.assertEqual(held.item.id, case["holding"])
        case = next(c for c in CASES if c["name"] == "shove them back")
        manager = scene(case)
        self.assertEqual(len(manager.world.zombies), case["standing_zombies"])
        self.assertFalse(
            any(z.on_floor(manager.narrative.minutes) for z in manager.world.zombies.values())
        )

    def test_every_case_names_a_real_zone(self):
        zones = GameManager().world.locations
        for case in CASES:
            self.assertIn(case["zone"], zones, case["name"])

    def test_every_carried_item_exists(self):
        for case in CASES:
            for item_id in [*case.get("carrying", []), *filter(None, [case.get("holding")])]:
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


class KindWordCaseTests(unittest.TestCase):
    """llm-contract: Checking the models: a place word that fits several zones is judged as the words copied."""

    def setUp(self):
        from scripts.eval_parser import same_plan

        self.same_plan = same_plan
        self.manager = GameManager()
        self.manager.player.current_location_id = "zone_street"

    def test_a_picked_zone_is_not_the_players_words(self):
        copied, _ = parse_action_plan(["MOVE_TO the apartment"])
        picked, _ = parse_action_plan(["MOVE_TO Your Building"])
        self.assertTrue(self.same_plan(self.manager, copied, copied))
        self.assertFalse(self.same_plan(self.manager, picked, copied))

    def test_the_kind_word_cases_are_in_the_file(self):
        inputs = {case["input"] for case in CASES}
        self.assertIn("run to the apartment and hit the zombie", inputs)
        self.assertLessEqual({"go to the apartment", "go to the store"}, inputs)


PLAN_CASES = yaml.safe_load(
    (Path(__file__).resolve().parent.parent / "evals" / "plan_check_cases.yaml").read_text("utf-8")
)


class PlanCheckCaseFileTests(unittest.TestCase):
    """llm-contract: Checking the models: the plan-check cases are well formed."""

    def test_every_case_names_a_zone_items_and_a_reason_key(self):
        zones = GameManager().world.locations
        for case in PLAN_CASES:
            with self.subTest(case=case["name"]):
                self.assertIn(case["zone"], zones)
                self.assertTrue(set(case.get("carrying", [])) <= set(ITEMS))
                self.assertIn(case["reason"], story_check_k.UNSUPPORTED_REASONS)
                self.assertTrue(case["input"] and case["unsupported"])

    def test_each_reason_has_a_case(self):
        self.assertEqual(
            {case["reason"] for case in PLAN_CASES}, set(story_check_k.UNSUPPORTED_REASONS)
        )

    def test_a_scene_builds_for_every_case(self):
        for case in PLAN_CASES:
            with self.subTest(case=case["name"]):
                self.assertEqual(run_case(case, FakeFactChecker()), "none")
