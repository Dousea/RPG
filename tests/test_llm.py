"""Parsing of the parser call's ACTIONS block and the narrator's STORY/EVENT."""

import unittest

from adapters.llm import parse_action_response, parse_narrator_response


class ParseActionResponseTests(unittest.TestCase):
    def test_well_formed_response(self):
        lines = parse_action_response(
            "ACTIONS:\nMOVE_TO hallway\nUPDATE_RELATIONSHIP Emma affection +1"
        )
        self.assertEqual(lines, ["MOVE_TO hallway", "UPDATE_RELATIONSHIP Emma affection +1"])

    def test_none_is_kept_as_a_line(self):
        # modules.action.parse_action_plan is what actually treats NONE as
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
        self.assertEqual(parsed["event"], "Orton entered the hallway")

    def test_blank_lines_inside_the_story_survive(self):
        parsed = parse_narrator_response(
            "STORY:\nFirst paragraph.\n\nSecond paragraph.\n\nEVENT:\nSomething"
        )
        self.assertEqual(parsed["story"], "First paragraph.\n\nSecond paragraph.")

    def test_content_on_the_header_line_is_kept(self):
        parsed = parse_narrator_response("STORY: All on one line.\n\nEVENT: Something")
        self.assertEqual(parsed["story"], "All on one line.")
        self.assertEqual(parsed["event"], "Something")

    def test_headers_are_case_insensitive(self):
        parsed = parse_narrator_response("story:\nx\n\nevent:\ny")
        self.assertEqual(parsed["story"], "x")
        self.assertEqual(parsed["event"], "y")

    def test_missing_sections_fall_back_to_defaults(self):
        parsed = parse_narrator_response("just some prose with no headers at all")
        self.assertEqual(parsed["story"], "The world is silent.")
        self.assertEqual(parsed["event"], "Nothing happened.")

    def test_empty_response(self):
        parsed = parse_narrator_response("")
        self.assertEqual(parsed["story"], "The world is silent.")
        self.assertEqual(parsed["event"], "Nothing happened.")

    def test_a_stray_actions_section_is_not_recognized_as_a_header(self):
        # The narrator is not asked for ACTIONS anymore; if it emits one
        # anyway, it is not authoritative and is simply absorbed as story/
        # event text rather than crashing the parse.
        parsed = parse_narrator_response(
            "STORY:\nYou look around.\n\nEVENT:\nOrton looked around\n\nACTIONS:\nNONE"
        )
        self.assertEqual(parsed["event"], "Orton looked around\n\nACTIONS:\nNONE")

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


if __name__ == "__main__":
    unittest.main()
