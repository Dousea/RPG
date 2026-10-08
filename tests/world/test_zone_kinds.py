"""llm-contract: A MOVE_TO destination: a kind word and a tie in the whole-word match give the zones to choose from."""

import unittest

from data.world.locations import build_starting_locations
from managers.world.locations import resolve_location
from modules.world.location import Location

HOMES = {"zone_home", "zone_building", "zone_flat_vacant", "zone_flat_tenant"}


def ids(found: Location | list[Location] | None) -> set[str]:
    assert isinstance(found, list), type(found)
    return {zone.id for zone in found}


class KindWordTests(unittest.TestCase):
    def setUp(self):
        self.locations = build_starting_locations()

    def resolve(self, phrase: str, standing_in: str = "zone_home"):
        return resolve_location(phrase, self.locations[standing_in], self.locations)

    def test_a_kind_word_gives_every_zone_of_the_kind_including_the_current_one(self):
        for phrase in ("the apartment", "an apartment", "apartment"):
            with self.subTest(phrase):
                self.assertEqual(ids(self.resolve(phrase)), HOMES)

    def test_apartment_and_flat_are_one_kind(self):
        for phrase in ("the apartment", "the flat"):
            with self.subTest(phrase):
                self.assertEqual(ids(self.resolve(phrase, "zone_building")), HOMES)

    def test_a_kind_word_is_read_from_wherever_the_player_stands(self):
        self.assertEqual(
            ids(self.resolve("the store", "zone_neighborhood")),
            {"zone_bodega", "zone_pharmacy", "zone_supermarket", "zone_hardware"},
        )

    def test_one_reachable_zone_of_the_kind_is_the_answer(self):
        neighborhood = self.locations["zone_neighborhood"]
        for exit_key in ("pharmacy", "supermarket", "hardware store"):
            del neighborhood.connections[exit_key]
        found = self.resolve("the shop", "zone_street")
        assert isinstance(found, Location)
        self.assertEqual(found.id, "zone_bodega")

    def test_an_exact_name_or_exit_phrase_is_not_a_kind(self):
        found = self.resolve("my apartment", "zone_building")
        assert isinstance(found, Location)
        self.assertEqual(found.id, "zone_home")
        leaving = self.resolve("leave the apartment", "zone_home")
        assert isinstance(leaving, Location)
        self.assertEqual(leaving.id, "zone_building")

    def test_the_head_of_a_longer_phrase_still_decides(self):
        found = self.resolve("the street outside my apartment", "zone_building")
        assert isinstance(found, Location)
        self.assertEqual(found.id, "zone_street")

    def test_two_zones_tied_on_position_and_length_are_both_offered(self):
        for zone_id in ("zone_home", "zone_street"):
            self.locations[zone_id].aliases.append("red door")
        self.assertEqual(
            ids(self.resolve("the red door", "zone_home")), {"zone_home", "zone_street"}
        )

    def test_a_unique_whole_word_match_is_unchanged(self):
        found = self.resolve("back to the hospital", "zone_home")
        assert isinstance(found, Location)
        self.assertEqual(found.id, "zone_neighborhood")


if __name__ == "__main__":
    unittest.main()
