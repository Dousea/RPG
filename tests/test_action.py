"""Parsing of ACTIONS: lines into typed proposals (shape only, no resolution)."""

import unittest

from adapters import llm
from managers.game import GameManager
from managers.simulation import SimulationCore
from managers.validator import ActionValidator
from modules.action.parser import (
    ASK_REQUEST_LABELS,
    TALK_APPROACH_LABELS,
    VERBS,
    ParseFailure,
    available_verbs,
    parse_action_line,
    parse_action_plan,
)
from modules.action.types import (
    AddGoalAction,
    AskAction,
    AttackAction,
    Duration,
    GiveAction,
    MoveAction,
    RemoveGoalAction,
    ShoutAction,
    SleepAction,
    StanceAction,
    TakeAction,
    TakeOffAction,
    TalkAction,
    UseItemAction,
    WaitAction,
    WearAction,
)


class ClockActionTests(unittest.TestCase):
    """clock: Actions."""

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

    def test_wait_accepts_spelled_out_units(self):
        cases = {
            "WAIT 18 hours": Duration(minutes=18 * 60),
            "WAIT 1 hour": Duration(minutes=60),
            "WAIT 30 minutes": Duration(minutes=30),
            "WAIT 1 hour 30 minutes": Duration(minutes=90),
            "WAIT 2 hrs 15 mins": Duration(minutes=135),
        }
        for line, duration in cases.items():
            with self.subTest(line=line):
                self.assertEqual(parse_action_line(line), WaitAction(duration=duration))

    def test_eat_and_drink_are_use_item(self):
        self.assertEqual(parse_action_line("DRINK Water Bottle"), UseItemAction("Water Bottle"))
        self.assertEqual(parse_action_line("EAT Canned Beans"), UseItemAction("Canned Beans"))

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

    def test_unknown_verb(self):
        result = parse_action_line("FROBNICATE the widget")
        assert isinstance(result, ParseFailure)
        self.assertIn("Unknown action verb", result.reason)

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

    def test_malformed_line_never_raises(self):
        for line in (
            "ADD_GOAL",
            "ADD_RELATIONSHIP_NOTE",
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
    """clothing: Actions: WEAR and TAKE_OFF."""

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
    """zombies: Pace: MOVE_TO gains a run pace; STANCE toggles sneaking."""

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


class VerbRegistryTests(unittest.TestCase):
    """llm-contract: Verbs: one registry of verbs."""

    EXPECTED = {
        "MOVE_TO",
        "STANCE",
        "WAIT",
        "SLEEP",
        "TAKE",
        "DROP",
        "USE_ITEM",
        "WEAR",
        "TAKE_OFF",
        "EXERCISE",
        "ATTACK",
        "SHOUT",
        "ADD_GOAL",
        "REMOVE_GOAL",
        "ADD_RELATIONSHIP_NOTE",
    }
    REMOVED = (
        "TIME_ADVANCE",
        "UPDATE_CONDITION",
        "UPDATE_RELATIONSHIP",
        "SET_FLAG",
        "DISCOVER_FLAG",
        "NPC_MOVE",
        "NPC_STATUS",
        "STATUS_ADD",
        "STATUS_REMOVE",
        "UPDATE_INVENTORY",
    )

    def test_the_registry_holds_the_verbs_of_specs_01_to_09_and_shout(self):
        self.assertEqual(self.EXPECTED, set(VERBS) & self.EXPECTED)
        self.assertTrue(set(VERBS) >= self.EXPECTED)

    def test_every_verb_in_the_registry_has_a_validator_and_a_resolver(self):
        self.assertEqual(set(VERBS), set(ActionValidator._VALIDATORS))
        self.assertEqual(set(VERBS), set(SimulationCore._RESOLVERS))

    def test_each_removed_verb_is_a_parse_failure(self):
        for verb in self.REMOVED:
            with self.subTest(verb=verb):
                result = parse_action_line(f"{verb} something 3")
                assert isinstance(result, ParseFailure)
                self.assertIn("not an available action", result.reason)

    def test_a_verb_of_a_later_spec_is_a_parse_failure_until_it_lands(self):
        for line in ("REPAIR knife", "SHARPEN knife"):
            with self.subTest(line=line):
                self.assertIsInstance(parse_action_line(line), ParseFailure)

    def test_shout_takes_no_arguments(self):
        self.assertEqual(parse_action_line("SHOUT"), ShoutAction())
        self.assertEqual(parse_action_line("shout for help"), ShoutAction())

    def test_fixed_costs_in_the_registry_match_the_time_cost_table(self):
        self.assertEqual(VERBS["STANCE"].minutes, 0)
        self.assertEqual(VERBS["TAKE"].minutes, 1)
        self.assertEqual(VERBS["ATTACK"].minutes, 1)
        self.assertEqual(VERBS["SHOUT"].minutes, 0)
        self.assertEqual(VERBS["ADD_GOAL"].minutes, 0)
        self.assertIsNone(VERBS["WAIT"].minutes)
        self.assertIsNone(VERBS["MOVE_TO"].minutes)

    def test_every_verb_parses_its_own_example(self):
        examples = {
            "MOVE_TO": "MOVE_TO out",
            "STANCE": "STANCE sneak",
            "WAIT": "WAIT 10m",
            "SLEEP": "SLEEP",
            "TAKE": "TAKE Crowbar",
            "DROP": "DROP Crowbar",
            "USE_ITEM": "USE_ITEM Water Bottle",
            "WEAR": "WEAR Jeans",
            "TAKE_OFF": "TAKE_OFF Jeans",
            "EXERCISE": "EXERCISE Push-ups 10",
            "ATTACK": "ATTACK z1",
            "SHOVE": "SHOVE z1",
            "EQUIP": "EQUIP Crowbar",
            "UNEQUIP": "UNEQUIP Crowbar",
            "SHOUT": "SHOUT",
            "ADD_GOAL": "ADD_GOAL short_term Find water",
            "REMOVE_GOAL": "REMOVE_GOAL short_term Find water",
            "ADD_RELATIONSHIP_NOTE": "ADD_RELATIONSHIP_NOTE Emma kind",
        }
        for name, line in examples.items():
            with self.subTest(verb=name):
                self.assertNotIsInstance(parse_action_line(line), ParseFailure)
                self.assertEqual(VERBS[name].parse(line.partition(" ")[2]).verb, name)

    def test_the_parser_prompt_drops_the_story_vocabulary(self):
        self.assertNotIn("STORY VOCABULARY", llm.PARSER_SYSTEM_PROMPT)
        self.assertNotIn("Orton", llm.PARSER_SYSTEM_PROMPT)


class SocialParseTests(unittest.TestCase):
    """llm-contract: Verbs: TALK, ASK and GIVE."""

    def test_talk_takes_a_name_and_an_approach(self):
        self.assertEqual(
            parse_action_line("TALK Emma compliment"),
            TalkAction(npc_name="Emma", approach="compliment"),
        )
        self.assertEqual(
            parse_action_line("TALK Mary Ann Flirt."),
            TalkAction(npc_name="Mary Ann", approach="flirt"),
        )

    def test_talk_accepts_only_the_eight_approaches(self):
        for approach in TALK_APPROACH_LABELS:
            with self.subTest(approach=approach):
                self.assertEqual(
                    parse_action_line(f"TALK Emma {approach}"),
                    TalkAction(npc_name="Emma", approach=approach),
                )
        self.assertEqual(len(TALK_APPROACH_LABELS), 8)
        for line in ("TALK Emma gossip", "TALK Emma", "TALK", "TALK chat"):
            with self.subTest(line=line):
                self.assertIsInstance(parse_action_line(line), ParseFailure)

    def test_talk_ignores_the_spoken_line_after_the_approach(self):
        cases = {
            'TALK Emma chat "Hi, I\'m the new guy in 3B"': TalkAction("Emma", "chat"),
            'TALK Emma compliment "Your apartment is really nice"': TalkAction(
                "Emma", "compliment"
            ),
            "TALK Mary Ann flirt you look nice today": TalkAction("Mary Ann", "flirt"),
        }
        for line, expected in cases.items():
            with self.subTest(line=line):
                self.assertEqual(parse_action_line(line), expected)

    def test_ask_accepts_only_the_four_requests(self):
        self.assertEqual(set(ASK_REQUEST_LABELS), {"follow", "stay", "give", "about"})
        self.assertEqual(
            parse_action_line("ASK Emma follow"),
            AskAction(npc_name="Emma", request="follow"),
        )
        self.assertEqual(
            parse_action_line("ASK Emma stay"), AskAction(npc_name="Emma", request="stay")
        )
        self.assertEqual(
            parse_action_line("ASK Emma give Water Bottle"),
            AskAction(npc_name="Emma", request="give", argument="Water Bottle"),
        )
        self.assertEqual(
            parse_action_line("ASK Jen about outbreak_news"),
            AskAction(npc_name="Jen", request="about", argument="outbreak_news"),
        )
        for line in ("ASK Emma dance", "ASK Emma give", "ASK Jen about", "ASK Emma", "ASK"):
            with self.subTest(line=line):
                self.assertIsInstance(parse_action_line(line), ParseFailure)

    def test_give_takes_an_item_and_an_npc(self):
        self.assertEqual(
            parse_action_line("GIVE Water Bottle Emma"),
            GiveAction(item_name="Water Bottle", npc_name="Emma"),
        )
        self.assertEqual(
            parse_action_line("GIVE Water Bottle to Mary Ann"),
            GiveAction(item_name="Water Bottle", npc_name="Mary Ann"),
        )
        for line in ("GIVE", "GIVE Emma"):
            with self.subTest(line=line):
                self.assertIsInstance(parse_action_line(line), ParseFailure)

    def test_the_social_verbs_cost_five_minutes_in_the_registry(self):
        for name in ("TALK", "ASK", "GIVE"):
            self.assertEqual(VERBS[name].minutes, 5)


ALWAYS_LISTED = [
    "MOVE_TO",
    "STANCE",
    "WAIT",
    "SLEEP",
    "EXERCISE",
    "SHOUT",
    "ADD_GOAL",
    "ADD_RELATIONSHIP_NOTE",
]


class SceneFilteringTests(unittest.TestCase):
    """llm-contract: Scene filtering."""

    def names(self, *keys: str) -> list[str]:
        return [verb.name for verb in available_verbs(frozenset(keys))]  # type: ignore[arg-type]

    def test_an_empty_scene_lists_the_eight_always_listed_verbs(self):
        self.assertEqual(self.names(), ALWAYS_LISTED)

    def test_each_key_adds_exactly_its_verbs_in_registry_order(self):
        expected = {
            "goals": ["REMOVE_GOAL"],
            "items_here": ["TAKE"],
            "corpses": ["CARRY", "SEARCH"],
            "loot": ["TAKE"],
            "bags": ["TAKE", "PUT"],
            "carried": ["DROP", "USE_ITEM", "EQUIP"],
            "held": ["UNEQUIP"],
            "wearable": ["WEAR"],
            "worn": ["TAKE_OFF"],
            "npcs_here": ["ATTACK", "TALK", "ASK", "GIVE"],
            "threats": ["ATTACK", "SHOVE"],
        }
        for key, added in expected.items():
            with self.subTest(key=key):
                listed = self.names(key)
                self.assertEqual(set(listed), set(ALWAYS_LISTED) | set(added))
                self.assertEqual(listed, [name for name in VERBS if name in listed])

    def test_every_key_present_lists_every_verb(self):
        keys = {key for verb in VERBS.values() for key in verb.listed_when}
        self.assertEqual(self.names(*keys), list(VERBS))

    def test_a_verb_that_is_not_listed_still_parses(self):
        self.assertNotIn("TAKE", self.names())
        self.assertEqual(parse_action_line("TAKE Crowbar"), TakeAction(item_name="Crowbar"))

    def test_a_verb_that_is_not_listed_reaches_the_validator(self):
        gm = GameManager()
        facts = SimulationCore(gm).resolve([TakeAction(item_name="Unicorn")])
        self.assertTrue(facts[0].startswith("Refused:"))
