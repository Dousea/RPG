"""llm-contract: The scene's setting comes from the zone, with a fallback for a zone the table lacks."""

import unittest

from data.world.locations import build_starting_locations
from data.world.scenes import SETTING_BY_ZONE
from managers.world.scenes import setting_word
from modules.world.location import Location

SETTINGS = {"apartment", "hallway", "street", "neighborhood", "store", "clinic"}


class SettingTest(unittest.TestCase):
    def test_every_zone_has_a_setting_of_its_own_table(self):
        for zone in build_starting_locations().values():
            with self.subTest(zone.id):
                self.assertIn(zone.id, SETTING_BY_ZONE)
                self.assertIn(setting_word(zone), SETTINGS)

    def test_a_zone_missing_from_the_table_falls_back_by_where_it_is(self):
        outdoors = Location(
            id="zone_new_yard", name="Yard", description="", connections={}, indoors=False
        )
        indoors = Location(
            id="zone_new_room", name="Room", description="", connections={}, indoors=True
        )
        with self.assertLogs("managers.world.scenes", "WARNING") as logged:
            self.assertEqual(setting_word(outdoors), "street")
            self.assertEqual(setting_word(indoors), "apartment")
            setting_word(outdoors)
        self.assertEqual(len(logged.records), 2)
