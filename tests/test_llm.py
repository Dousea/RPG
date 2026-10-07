"""Parsing of the parser call's ACTIONS block and the narrator's STORY."""

import json
import unittest
from unittest import mock

import requests

import config
from adapters import llm
from adapters.llm import (
    NARRATOR_SYSTEM_PROMPT,
    PARSER_JSON_SYSTEM_PROMPT,
    PARSER_SYSTEM_PROMPT,
    SUMMARIZER_SYSTEM_PROMPT,
    LLMError,
    has_options_section,
    parse_action_response,
    parse_narrator_response,
    parse_plan_response,
)
from data.memory import DEFAULT_CHARS_PER_TOKEN


class ParseActionResponseTests(unittest.TestCase):
    def test_well_formed_response(self):
        lines = parse_action_response("ACTIONS:\nMOVE_TO hallway\nADD_RELATIONSHIP_NOTE Emma kind")
        self.assertEqual(lines, ["MOVE_TO hallway", "ADD_RELATIONSHIP_NOTE Emma kind"])

    def test_none_is_kept_as_a_line(self):
        # modules.action.parser.parse_action_plan is what actually treats NONE as
        # "no actions" -- this function only extracts lines.
        self.assertEqual(parse_action_response("ACTIONS:\nNONE"), ["NONE"])

    def test_bulleted_actions_are_kept_as_written(self):
        lines = parse_action_response("ACTIONS:\n- TAKE Crowbar\n- DROP Crowbar")
        self.assertEqual(lines, ["- TAKE Crowbar", "- DROP Crowbar"])

    def test_content_on_the_header_line_is_kept(self):
        self.assertEqual(parse_action_response("ACTIONS: MOVE_TO north"), ["MOVE_TO north"])

    def test_header_is_case_insensitive(self):
        self.assertEqual(parse_action_response("actions:\nTAKE Crowbar"), ["TAKE Crowbar"])

    def test_missing_header_falls_back_to_every_line(self):
        # A small local model asked for one section sometimes drops the header.
        self.assertEqual(
            parse_action_response("MOVE_TO north\nTAKE Crowbar"), ["MOVE_TO north", "TAKE Crowbar"]
        )

    def test_blank_lines_are_dropped(self):
        lines = parse_action_response("ACTIONS:\nTAKE Crowbar\n\n   \nDROP Crowbar")
        self.assertEqual(lines, ["TAKE Crowbar", "DROP Crowbar"])

    def test_empty_response(self):
        self.assertEqual(parse_action_response(""), [])


class ParseNarratorResponseTests(unittest.TestCase):
    def test_well_formed_response(self):
        parsed = parse_narrator_response(
            "STORY:\nYou step into the hall.\n\nEVENT:\nOrton entered the hallway"
        )
        self.assertEqual(parsed["story"], "You step into the hall.")
        self.assertNotIn("event", parsed)

    def test_blank_lines_inside_the_story_survive(self):
        parsed = parse_narrator_response(
            "STORY:\nFirst paragraph.\n\nSecond paragraph.\n\nEVENT:\nSomething"
        )
        self.assertEqual(parsed["story"], "First paragraph.\n\nSecond paragraph.")

    def test_content_on_the_header_line_is_kept(self):
        parsed = parse_narrator_response("STORY: All on one line.\n\nEVENT: Something")
        self.assertEqual(parsed["story"], "All on one line.")

    def test_headers_are_case_insensitive(self):
        parsed = parse_narrator_response("story:\nx\n\nevent:\ny")
        self.assertEqual(parsed["story"], "x")

    def test_prose_before_options_with_no_story_header_is_the_story(self):
        parsed = parse_narrator_response(
            "The apartment is quiet...\n\nYou lift the knife.\n\n**What do you do?**"
            "\n\nOPTIONS:\n- Lock the door\n- Hide"
        )
        self.assertEqual(
            parsed["story"],
            "The apartment is quiet...\n\nYou lift the knife.\n\n**What do you do?**",
        )
        self.assertEqual(parsed["options"], ["Lock the door", "Hide"])

    def test_prose_with_no_headers_at_all_is_the_story(self):
        parsed = parse_narrator_response("just some prose\n\nwith no headers at all")
        self.assertEqual(parsed["story"], "just some prose\n\nwith no headers at all")
        self.assertEqual(parsed["options"], [])

    def test_an_echoed_prompt_block_is_dropped_from_the_story(self):
        parsed = parse_narrator_response(
            "STORY:\nThe screen goes dark.\n\n[OUTCOMES]\n- Take Kitchen Knife: succeeded.\n"
            "- About 2 minutes pass.\n\nOPTIONS:\n- Barricade the door"
        )
        self.assertEqual(parsed["story"], "The screen goes dark.")
        self.assertEqual(parsed["options"], ["Barricade the door"])

    def test_empty_response(self):
        parsed = parse_narrator_response("")
        self.assertEqual(parsed["story"], "The world is silent.")

    def test_a_stray_event_section_is_dropped_never_shown_as_story(self):
        parsed = parse_narrator_response(
            "STORY:\nYou look around.\n\nEVENT:\nOrton looked around\n\nOPTIONS:\n- Wait"
        )
        self.assertEqual(parsed["story"], "You look around.")
        self.assertEqual(parsed["options"], ["Wait"])

    def test_event_before_story_is_dropped_too(self):
        parsed = parse_narrator_response("EVENT: Orton looked around\nSTORY:\nYou look around.")
        self.assertEqual(parsed["story"], "You look around.")

    def test_options_are_extracted_as_a_list_with_dashes_stripped(self):
        parsed = parse_narrator_response(
            "STORY:\nYou pause.\n\nEVENT:\nOrton paused\n\n"
            "OPTIONS:\n- Knock on the door\n- Walk away"
        )
        self.assertEqual(parsed["options"], ["Knock on the door", "Walk away"])

    def test_options_none_yields_an_empty_list(self):
        parsed = parse_narrator_response(
            "STORY:\nYou pause.\n\nEVENT:\nOrton paused\n\nOPTIONS:\nNONE"
        )
        self.assertEqual(parsed["options"], [])

    def test_options_none_on_the_header_line_yields_an_empty_list(self):
        # The death-narration instruction (adapters/llm.py's
        # NARRATOR_SYSTEM_PROMPT) tells the model to write "OPTIONS: NONE" on
        # one line rather than the header and NONE on separate lines -- make
        # sure that shape parses to no options too, not a stray "NONE" entry.
        parsed = parse_narrator_response(
            "STORY:\nOrton is dead.\n\nEVENT:\nOrton died\n\nOPTIONS: NONE"
        )
        self.assertEqual(parsed["options"], [])

    def test_options_none_with_trailing_punctuation_yields_an_empty_list(self):
        # The model sometimes punctuates "NONE" (a period, an
        # exclamation mark, a semicolon, a colon) -- strip it before the
        # comparison rather than treating it as a stray option.
        parsed = parse_narrator_response(
            "STORY:\nYou pause.\n\nEVENT:\nOrton paused\n\nOPTIONS: NONE."
        )
        self.assertEqual(parsed["options"], [])

    def test_missing_options_section_yields_an_empty_list(self):
        # Older-shaped responses (no OPTIONS at all) must still parse cleanly.
        parsed = parse_narrator_response("STORY:\nYou pause.\n\nEVENT:\nOrton paused")
        self.assertEqual(parsed["options"], [])

    def test_a_bracketed_options_header_is_read_as_options(self):
        parsed = parse_narrator_response(
            "STORY:\nThe hallway is quiet.\n\n[OPTIONS]\n- Knock on 3A\n- Go back inside"
        )
        self.assertEqual(parsed["story"], "The hallway is quiet.")
        self.assertEqual(parsed["options"], ["Knock on 3A", "Go back inside"])

    def test_a_bracketed_story_header_is_read_as_the_story(self):
        parsed = parse_narrator_response("[STORY]\nThe hallway is quiet.\n\nOPTIONS:\n- Wait")
        self.assertEqual(parsed["story"], "The hallway is quiet.")
        self.assertEqual(parsed["options"], ["Wait"])

    def test_a_bulleted_none_is_not_an_option(self):
        parsed = parse_narrator_response(
            "STORY:\nYou pause.\n\nOPTIONS:\n- Call out to Emma\n- NONE"
        )
        self.assertEqual(parsed["options"], ["Call out to Emma"])


class HasOptionsSectionTests(unittest.TestCase):
    def test_a_reply_with_options_has_the_section(self):
        self.assertTrue(has_options_section("STORY:\nYou wait.\n\nOPTIONS:\n- Rest"))

    def test_options_none_still_counts_as_the_section(self):
        self.assertTrue(has_options_section("STORY:\nYou wait.\n\nOPTIONS: NONE"))

    def test_a_bracketed_header_counts(self):
        self.assertTrue(has_options_section("[STORY]\nYou wait.\n\n[OPTIONS]\n- Rest"))

    def test_a_story_alone_has_no_section(self):
        self.assertFalse(has_options_section("STORY:\nYou wait. Your options are few."))


class PromptRuleTests(unittest.TestCase):
    """Spec 10, What the narrator must not do and Memory."""

    def test_the_narrator_is_told_refused_means_it_did_not_happen(self):
        self.assertIn("Refused", NARRATOR_SYSTEM_PROMPT)
        self.assertIn("did not happen", NARRATOR_SYSTEM_PROMPT)

    def test_nothing_appears_in_anyones_hands_unless_the_blocks_say_so(self):
        self.assertIn("in anyone's hands", NARRATOR_SYSTEM_PROMPT)

    def test_only_listed_loose_items_can_be_found(self):
        self.assertIn(
            "only loose things to find or take are in [ITEMS IN CURRENT LOCATION]",
            NARRATOR_SYSTEM_PROMPT,
        )

    def test_the_narrator_is_not_asked_for_an_event_line(self):
        self.assertNotIn("EVENT:", NARRATOR_SYSTEM_PROMPT)
        self.assertNotIn("After EVENT", NARRATOR_SYSTEM_PROMPT)

    def test_the_narrator_may_only_use_listed_zombies_corpses_and_people(self):
        for block in ("[THREATS]", "[CORPSES]", "[NPCS PRESENT]"):
            self.assertIn(block, NARRATOR_SYSTEM_PROMPT)

    def test_the_narrator_is_told_state_wins_over_memory(self):
        self.assertIn("current blocks win", NARRATOR_SYSTEM_PROMPT)
        self.assertIn("only an attempt", NARRATOR_SYSTEM_PROMPT)

    def test_a_topic_is_said_only_when_outcomes_says_it_was_told(self):
        self.assertIn("only when [OUTCOMES] says it was told", NARRATOR_SYSTEM_PROMPT)

    def test_the_narrator_prompt_has_no_stale_story_tools(self):
        for word in ("UPDATE_", "SET_FLAG", "Orton"):
            self.assertNotIn(word, NARRATOR_SYSTEM_PROMPT)

    def test_the_parser_is_told_a_request_for_someone_absent_is_no_action(self):
        for prompt in (PARSER_SYSTEM_PROMPT, PARSER_JSON_SYSTEM_PROMPT):
            self.assertIn("not listed in [NPCS HERE]", prompt)
            self.assertIn("Input: 'ask Dana to open the gate'", prompt)

    def test_the_summarizer_is_told_an_attempt_is_not_an_outcome(self):
        self.assertIn("only an attempt", SUMMARIZER_SYSTEM_PROMPT)
        self.assertIn("what actually happened", SUMMARIZER_SYSTEM_PROMPT)


class FakeResponse:
    def __init__(self, status_code: int, content: str = "", prompt_tokens: int | None = None):
        self.status_code = status_code
        self._content = content
        self._prompt_tokens = prompt_tokens

    def raise_for_status(self) -> None:
        if self.status_code >= 400:
            raise requests.exceptions.HTTPError(f"HTTP {self.status_code}")

    def json(self) -> dict:
        body: dict = {"choices": [{"message": {"content": self._content}}]}
        if self._prompt_tokens is not None:
            body["usage"] = {"prompt_tokens": self._prompt_tokens}
        return body


SCHEMA = {"type": "object", "properties": {"actions": {"type": "array"}}}


class ReadParserReplyTests(unittest.TestCase):
    """Spec 10, Plans."""

    def test_a_structured_reply_is_read_as_a_json_plan(self):
        reply = llm.ParserReply('{"actions": [{"verb": "SHOUT"}]}', structured=True)
        actions, failures = llm.read_parser_reply(reply)
        self.assertEqual([type(action).__name__ for action in actions], ["ShoutAction"])
        self.assertEqual(failures, [])

    def test_a_text_reply_is_read_as_action_lines(self):
        reply = llm.ParserReply("ACTIONS:\nSHOUT", structured=False)
        actions, failures = llm.read_parser_reply(reply)
        self.assertEqual([type(action).__name__ for action in actions], ["ShoutAction"])
        self.assertEqual(failures, [])


class ParserRequestTests(unittest.TestCase):
    """Spec 10, Plans."""

    def ask(self, *responses: FakeResponse, schema=SCHEMA):
        with mock.patch.object(llm.requests, "post", side_effect=responses) as post:
            reply = llm.query_parser("prompt", schema)
        return reply, [call.kwargs["json"] for call in post.call_args_list]

    def test_the_request_carries_the_schema_as_a_strict_response_format(self):
        reply, payloads = self.ask(FakeResponse(200, '{"actions": []}'))
        self.assertEqual(
            payloads[0]["response_format"],
            {
                "type": "json_schema",
                "json_schema": {"name": "action_plan", "strict": True, "schema": SCHEMA},
            },
        )
        self.assertEqual(payloads[0]["messages"][0]["content"], PARSER_JSON_SYSTEM_PROMPT)
        self.assertEqual((reply.text, reply.structured), ('{"actions": []}', True))

    def test_a_4xx_falls_back_once_to_the_text_prompt(self):
        with self.assertLogs("adapters.llm", level="WARNING"):
            reply, payloads = self.ask(FakeResponse(400), FakeResponse(200, "ACTIONS:\nNONE"))
        self.assertEqual(len(payloads), 2)
        self.assertNotIn("response_format", payloads[1])
        self.assertEqual(payloads[1]["messages"][0]["content"], PARSER_SYSTEM_PROMPT)
        self.assertEqual((reply.text, reply.structured), ("ACTIONS:\nNONE", False))

    def test_a_server_error_is_not_retried_as_text(self):
        with self.assertRaises(LLMError):
            self.ask(FakeResponse(500))

    def test_a_4xx_on_the_text_prompt_is_an_error(self):
        with self.assertRaises(LLMError), self.assertLogs("adapters.llm", level="WARNING"):
            self.ask(FakeResponse(400), FakeResponse(400))

    def test_without_a_schema_the_request_is_the_text_prompt(self):
        reply, payloads = self.ask(FakeResponse(200, "NONE"), schema=None)
        self.assertNotIn("response_format", payloads[0])
        self.assertFalse(reply.structured)

    def test_the_narrator_request_has_no_response_format(self):
        with mock.patch.object(llm.requests, "post", return_value=FakeResponse(200, "x")) as post:
            llm.query_narrator("prompt")
        self.assertNotIn("response_format", post.call_args.kwargs["json"])

    def test_the_json_prompt_asks_for_the_object_and_keeps_the_rules(self):
        self.assertIn('"actions"', PARSER_JSON_SYSTEM_PROMPT)
        self.assertNotIn("ACTIONS:", PARSER_JSON_SYSTEM_PROMPT)
        for rule in ("CRITICAL", "one action, never two", "there is no action for dealing"):
            self.assertIn(rule, PARSER_JSON_SYSTEM_PROMPT)
            self.assertIn(rule, PARSER_SYSTEM_PROMPT)

    def test_the_json_examples_are_plans_the_parser_reads(self):
        examples = [line for line in PARSER_JSON_SYSTEM_PROMPT.splitlines() if line.startswith("{")]
        verbs = []
        for example in examples:
            actions, failures = parse_plan_response(example)
            self.assertEqual(failures, [])
            verbs.append([a.verb for a in actions])
        self.assertEqual(verbs, [["TAKE", "MOVE_TO"], ["ASK"], ["TALK"], []])

    def test_a_question_with_no_listed_topic_is_shown_as_talk(self):
        self.assertIn("Input: 'Emma, what's going on downstairs?'", PARSER_JSON_SYSTEM_PROMPT)
        self.assertIn(
            '{"verb": "TALK", "npc": "Emma", "approach": "chat"}', PARSER_JSON_SYSTEM_PROMPT
        )


class ParsePlanResponseTests(unittest.TestCase):
    def test_a_plan_becomes_actions(self):
        actions, failures = parse_plan_response(json.dumps({"actions": [{"verb": "SHOUT"}]}))
        self.assertEqual(([a.verb for a in actions], failures), (["SHOUT"], []))

    def test_an_empty_plan_is_none(self):
        self.assertEqual(parse_plan_response('{"actions": []}'), ([], []))

    def test_bad_json_is_a_refusal_not_a_crash(self):
        for text in ("", "ACTIONS:\nNONE", '{"actions": [', "null"):
            actions, failures = parse_plan_response(text)
            self.assertEqual((actions, len(failures)), ([], 1), text)


class ReplyCapTests(unittest.TestCase):
    """Spec 10, Token budget: reply caps."""

    def sent(self, call) -> dict:
        with mock.patch.object(llm.requests, "post", return_value=FakeResponse(200, "x")) as post:
            call()
        return post.call_args.kwargs["json"]

    def test_the_defaults_are_the_documented_caps(self):
        self.assertEqual(
            (
                config.llm.context_tokens,
                config.llm.narrator_max_tokens,
                config.llm.parser_max_tokens,
                config.llm.summarizer_max_tokens,
            ),
            (8192, 800, 400, 300),
        )

    def test_the_narrator_request_is_capped(self):
        self.assertEqual(self.sent(lambda: llm.query_narrator("p"))["max_tokens"], 800)

    def test_the_parser_request_is_capped_in_both_formats(self):
        self.assertEqual(self.sent(lambda: llm.query_parser("p", SCHEMA))["max_tokens"], 400)
        self.assertEqual(self.sent(lambda: llm.query_parser("p"))["max_tokens"], 400)

    def test_the_summary_request_is_capped(self):
        self.assertEqual(self.sent(lambda: llm.query_summary("p"))["max_tokens"], 300)


class ReasoningTests(unittest.TestCase):
    """Spec 10, The rule."""

    def sent(self, call) -> dict:
        with mock.patch.object(llm.requests, "post", return_value=FakeResponse(200, "x")) as post:
            call()
        return post.call_args.kwargs["json"]

    def test_every_game_request_turns_reasoning_off(self):
        calls = (
            lambda: llm.query_narrator("p"),
            lambda: llm.query_parser("p", SCHEMA),
            lambda: llm.query_parser("p"),
            lambda: llm.query_summary("p"),
        )
        for call in calls:
            self.assertEqual(self.sent(call)["reasoning_effort"], "none")


class ModelPerRoleTests(unittest.TestCase):
    """Spec 10, The rule."""

    def model(self, call) -> str:
        with (
            mock.patch.object(llm, "MODEL_NAME", "narrator-model"),
            mock.patch.object(llm, "PARSER_MODEL_NAME", "parser-model"),
            mock.patch.object(llm.requests, "post", return_value=FakeResponse(200, "x")) as post,
        ):
            call()
        return post.call_args.kwargs["json"]["model"]

    def test_the_parser_asks_its_own_model_in_both_formats(self):
        self.assertEqual(self.model(lambda: llm.query_parser("p", SCHEMA)), "parser-model")
        self.assertEqual(self.model(lambda: llm.query_parser("p")), "parser-model")

    def test_the_narrator_and_summary_ask_the_narrator_model(self):
        self.assertEqual(self.model(lambda: llm.query_narrator("p")), "narrator-model")
        self.assertEqual(self.model(lambda: llm.query_summary("p")), "narrator-model")

    def test_by_default_the_parser_shares_the_narrator_model(self):
        self.assertEqual(config._DEFAULTS["llm"]["parser_model_name"], "")


class CharsPerTokenTests(unittest.TestCase):
    """Spec 10, Token budget: characters per token."""

    def setUp(self):
        llm.reset_chars_per_token()
        self.addCleanup(llm.reset_chars_per_token)

    def ask(self, response: FakeResponse) -> None:
        with mock.patch.object(llm.requests, "post", return_value=response):
            llm.query_narrator("u" * 100)

    def test_it_starts_at_the_default(self):
        self.assertEqual(llm.chars_per_token(), DEFAULT_CHARS_PER_TOKEN)
        self.assertEqual(DEFAULT_CHARS_PER_TOKEN, 3.5)

    def test_a_reply_with_usage_sets_the_ratio_of_characters_sent_to_prompt_tokens(self):
        self.ask(FakeResponse(200, "x", prompt_tokens=100))
        sent = len(NARRATOR_SYSTEM_PROMPT) + 100
        self.assertAlmostEqual(llm.chars_per_token(), sent / 100)

    def test_the_latest_reply_wins(self):
        self.ask(FakeResponse(200, "x", prompt_tokens=100))
        self.ask(FakeResponse(200, "x", prompt_tokens=200))
        self.assertAlmostEqual(llm.chars_per_token(), (len(NARRATOR_SYSTEM_PROMPT) + 100) / 200)

    def test_a_reply_without_usage_leaves_it_alone(self):
        self.ask(FakeResponse(200, "x", prompt_tokens=100))
        before = llm.chars_per_token()
        self.ask(FakeResponse(200, "x"))
        self.assertEqual(llm.chars_per_token(), before)


class NarratorPromptLengthTests(unittest.TestCase):
    def test_the_system_prompt_fits_three_thousand_two_hundred_characters(self):
        self.assertLessEqual(len(NARRATOR_SYSTEM_PROMPT), 3200)


if __name__ == "__main__":
    unittest.main()
