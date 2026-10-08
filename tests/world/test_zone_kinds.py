"""llm-contract: A MOVE_TO destination: a kind word and a tie in the whole-word match give the zones to choose from."""

import unittest

from data.world.locations import build_starting_locations
from managers.world.locations import kind_choice, resolve_location
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
        found = self.resolve("back to the park", "zone_home")
        assert isinstance(found, Location)
        self.assertEqual(found.id, "zone_neighborhood")


class PlaceWordsCheckTests(unittest.TestCase):
    """llm-contract: A parsed destination of one zone is an open choice when the player's words only gave a kind word."""

    def setUp(self):
        self.locations = build_starting_locations()

    def check(self, text: str, destination: str, standing_in: str):
        current = self.locations[standing_in]
        found = resolve_location(destination, current, self.locations)
        assert isinstance(found, Location)
        return kind_choice(text, found, current, self.locations)

    def test_a_kind_word_with_a_zone_the_parser_picked_gives_the_whole_kind(self):
        found = self.check("go to the apartment", "Your Apartment", "zone_building")
        assert found is not None
        self.assertEqual({zone.id for zone in found}, HOMES)
        found = self.check("go to the store", "The Corner Store", "zone_home")
        assert found is not None
        self.assertEqual(
            {zone.id for zone in found},
            {"zone_bodega", "zone_pharmacy", "zone_supermarket", "zone_hardware"},
        )

    def test_words_that_name_the_zone_ask_nothing(self):
        for text, destination, standing_in in (
            ("go to my apartment", "Your Apartment", "zone_building"),
            ("go home", "Your Apartment", "zone_building"),
            ("go to the corner store", "The Corner Store", "zone_home"),
            ("go to the supermarket", "The Supermarket", "zone_neighborhood"),
            ("leave the apartment", "Your Building", "zone_home"),
            ("go to the store", "store", "zone_street"),
        ):
            with self.subTest(text):
                self.assertIsNone(self.check(text, destination, standing_in))

    def test_words_that_only_resemble_a_kind_word_never_count(self):
        for text in ("go to the stockroom", "check the storeroom", "go to the storefront"):
            with self.subTest(text):
                self.assertIsNone(self.check(text, "Your Apartment", "zone_building"))

    def test_one_reachable_zone_of_the_kind_is_no_question(self):
        neighborhood = self.locations["zone_neighborhood"]
        for exit_key in ("pharmacy", "supermarket", "hardware store"):
            del neighborhood.connections[exit_key]
        self.assertIsNone(self.check("go to the shop", "The Corner Store", "zone_street"))

    def test_a_zone_outside_the_kind_is_not_second_guessed(self):
        self.assertIsNone(self.check("go to the store", "The Street", "zone_bodega"))


if __name__ == "__main__":
    unittest.main()
