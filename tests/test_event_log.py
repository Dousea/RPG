"""llm-contract: Memory: the engine writes the event entry from the turn, not from narrator text."""

import unittest

from managers.events.log import build_event_entry, event_stamp
from managers.game import GameManager


class EventEntryTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()

    def test_stamp_is_day_time_and_zone(self):
        self.assertEqual(event_stamp(self.gm), "Day 1, 08:00 AM, Your Apartment")

    def test_entry_has_stamp_attempt_and_facts(self):
        entry = build_event_entry(
            self.gm,
            "Day 3, 06:32 AM, Your Building",
            "I stab the zombie in the head.",
            [
                "Orton hits z1 with the kitchen knife and it staggers back.",
                "About 1 minute passes.",
            ],
        )
        self.assertEqual(
            entry,
            "Day 3, 06:32 AM, Your Building. "
            'Orton tries: "I stab the zombie in the head." '
            "Orton hits the zombie with the kitchen knife and it staggers back. "
            "About 1 minute passes.",
        )

    def test_entry_without_facts_is_just_the_attempt(self):
        entry = build_event_entry(self.gm, "Day 1, 08:00 AM, Your Apartment", "wait", [])
        self.assertEqual(entry, 'Day 1, 08:00 AM, Your Apartment. Orton tries: "wait"')


if __name__ == "__main__":
    unittest.main()
