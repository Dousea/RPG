"""Parsing of the STORY / EVENT / ACTIONS response format."""

import unittest

from adapters.llm import parse_response


class ParseResponseTests(unittest.TestCase):
    def test_well_formed_response(self):
        parsed = parse_response(
            "STORY:\nYou step into the hall.\n\n"
            "EVENT:\nOrton entered the hallway\n\n"
            "ACTIONS:\nMOVE_TO hallway\nUPDATE_RELATIONSHIP Emma affection +1"
        )
        self.assertEqual(parsed["story"], "You step into the hall.")
        self.assertEqual(parsed["event"], "Orton entered the hallway")
        self.assertEqual(
            parsed["actions"],
            ["MOVE_TO hallway", "UPDATE_RELATIONSHIP Emma affection +1"],
        )

    def test_blank_lines_inside_the_story_survive(self):
        # Sections are found by header, not by splitting on blank lines, so a
        # multi-paragraph story stays intact.
        parsed = parse_response(
            "STORY:\nFirst paragraph.\n\nSecond paragraph.\n\n"
            "EVENT:\nSomething\n\nACTIONS:\nNONE"
        )
        self.assertEqual(parsed["story"], "First paragraph.\n\nSecond paragraph.")

    def test_none_means_no_actions(self):
        parsed = parse_response("STORY:\nQuiet.\n\nEVENT:\nIdle\n\nACTIONS:\nNONE")
        self.assertEqual(parsed["actions"], [])

    def test_bulleted_actions_are_cleaned(self):
        parsed = parse_response(
            "STORY:\nx\n\nEVENT:\ny\n\nACTIONS:\n- TAKE Crowbar\n- DROP Crowbar"
        )
        self.assertEqual(parsed["actions"], ["TAKE Crowbar", "DROP Crowbar"])

    def test_content_on_the_header_line_is_kept(self):
        parsed = parse_response("STORY: All on one line.\n\nEVENT: Something\n\nACTIONS: NONE")
        self.assertEqual(parsed["story"], "All on one line.")
        self.assertEqual(parsed["event"], "Something")
        self.assertEqual(parsed["actions"], [])

    def test_headers_are_case_insensitive(self):
        parsed = parse_response("story:\nx\n\nevent:\ny\n\nactions:\nNONE")
        self.assertEqual(parsed["story"], "x")
        self.assertEqual(parsed["event"], "y")

    def test_missing_sections_fall_back_to_defaults(self):
        parsed = parse_response("just some prose with no headers at all")
        self.assertEqual(parsed["story"], "The world is silent.")
        self.assertEqual(parsed["event"], "Nothing happened.")
        self.assertEqual(parsed["actions"], [])

    def test_empty_response(self):
        parsed = parse_response("")
        self.assertEqual(parsed["story"], "The world is silent.")
        self.assertEqual(parsed["actions"], [])

    def test_blank_action_lines_are_dropped(self):
        parsed = parse_response(
            "STORY:\nx\n\nEVENT:\ny\n\nACTIONS:\nTAKE Crowbar\n\n   \nDROP Crowbar"
        )
        self.assertEqual(parsed["actions"], ["TAKE Crowbar", "DROP Crowbar"])


if __name__ == "__main__":
    unittest.main()
