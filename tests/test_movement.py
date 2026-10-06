"""MOVE_TO resolution: zones, spots, locked doors and exits."""

import unittest

from managers.context import ContextBuilder
from managers.game import GameManager
from modules.action.types import MoveAction
from tests.support import simulate


class LiveWorldLockedDoorTests(unittest.TestCase):
    """The starting map's real locked door (data/locations.py) -- Orton's own
    apartment door, locked from the building side only -- not a manually
    constructed one, proves the exit-requirement wiring is actually live in
    the shipped game, not just exercised in isolation."""

    def test_leaving_and_returning_succeeds_with_the_key(self):
        gm = GameManager()  # starts holding item_apartment_key
        facts = simulate(gm, MoveAction(destination="out"), MoveAction(destination="in"))
        self.assertFalse(any(f.startswith("Refused:") for f in facts))
        self.assertEqual(gm.player.current_location_id, "zone_home")

    def test_the_apartment_is_locked_without_the_key(self):
        # MOVE_TO never fails -- a locked door soft-lands the player at it.
        gm = GameManager()
        simulate(gm, MoveAction(destination="out"))
        gm.player.inventory.clear()  # drop the apartment key
        facts = simulate(gm, MoveAction(destination="in"))
        self.assertFalse(facts[0].startswith("Refused:"))
        self.assertIn("blocked", facts[0])
        self.assertEqual(gm.player.current_location_id, "zone_building")
        self.assertEqual(gm.player.current_place, "at the locked door to Your Apartment")

    def test_leaving_the_apartment_needs_no_key(self):
        gm = GameManager()
        gm.player.inventory.clear()  # no apartment key
        facts = simulate(gm, MoveAction(destination="out"))
        self.assertFalse(facts[0].startswith("Refused:"))
        self.assertEqual(gm.player.current_location_id, "zone_building")


class MovementResolutionTests(unittest.TestCase):
    def test_move_mutates_player_location(self):
        gm = GameManager()
        facts = simulate(gm, MoveAction(destination="out"))
        self.assertEqual(gm.player.current_location_id, "zone_building")
        self.assertIn("succeeded", facts[0])

    def test_move_to_unknown_becomes_a_spot_in_the_current_zone(self):
        # Rejecting an unmatched name would let the story and the state
        # diverge (MOVE_TO never fails). Location and clock are unchanged,
        # but the fact is not a refusal.
        gm = GameManager()
        facts = simulate(gm, MoveAction(destination="Atlantis"))
        self.assertEqual(gm.player.current_location_id, "zone_home")
        self.assertEqual(gm.player.current_place, "Atlantis")
        self.assertEqual(gm.narrative.time_of_day, "morning")
        self.assertFalse(facts[0].startswith("Refused:"))

    def test_move_by_connection_name_and_id(self):
        gm = GameManager()
        simulate(gm, MoveAction(destination="out"))
        self.assertEqual(gm.player.current_location_id, "zone_building")
        simulate(gm, MoveAction(destination="Your Apartment"))
        self.assertEqual(gm.player.current_location_id, "zone_home")
        # Walking through the building to the street, key still held.
        simulate(gm, MoveAction(destination="zone_street"))
        self.assertEqual(gm.player.current_location_id, "zone_street")

    def test_move_by_alias_keeps_the_alias_as_the_spot(self):
        # "the pharmacy" is the neighborhood as far as the simulation cares,
        # but the words are where Orton actually is, so they are worth keeping.
        gm = GameManager()
        simulate(gm, MoveAction(destination="the pharmacy"))
        self.assertEqual(gm.player.current_location_id, "zone_neighborhood")
        self.assertEqual(gm.player.current_place, "the pharmacy")

    def test_naming_the_zone_itself_clears_the_spot(self):
        gm = GameManager()
        simulate(gm, MoveAction(destination="the kitchen"))
        self.assertEqual(gm.player.current_place, "the kitchen")
        simulate(gm, MoveAction(destination="Your Apartment"))
        self.assertEqual(gm.player.current_place, "")

    def test_bare_directions_are_not_stored_as_a_place(self):
        # "north" with no exit behind it is a shuffle, not a destination.
        gm = GameManager()
        simulate(gm, MoveAction(destination="north"))
        self.assertEqual(gm.player.current_place, "")

    def test_move_to_never_fails(self):
        gm = GameManager()
        for junk in (
            "Atlantis",
            "north",
            "",
            "the roof",
            "???",
            "a place with a very long name that goes on well past any sensible limit for a spot",
            "Emma's kitchen table",
            "12345",
            "MOVE_TO",
            "back",
        ):
            facts = simulate(gm, MoveAction(destination=junk))
            self.assertFalse(
                facts[0].startswith("Refused:"), f"MOVE_TO {junk!r} was refused: {facts[0]}"
            )
            # Whatever happened, the world must still be describable.
            self.assertIn("[SCENE]", ContextBuilder(gm).build_narrator_prompt("look"))
        self.assertLessEqual(len(gm.player.current_place), 80)

    def test_locked_door_soft_lands_at_the_door(self):
        gm = GameManager()
        gm.player.inventory.clear()  # drop the apartment key
        simulate(gm, MoveAction(destination="zone_street"))  # no key needed to leave
        facts = simulate(gm, MoveAction(destination="Your Apartment"))
        self.assertEqual(gm.player.current_location_id, "zone_building")
        self.assertEqual(gm.player.current_place, "at the locked door to Your Apartment")
        self.assertIn("blocked", facts[0])
        self.assertFalse(facts[0].startswith("Refused:"))


class FinalFixWaveMoveRoutingTests(unittest.TestCase):
    """R1-R7: routing cases from the final whole-branch code review,
    reproduced through SimulationCore (final-fix-wave.md)."""

    def test_r1_clinics_bathroom_stays_in_the_neighborhood_as_a_spot(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_neighborhood"
        before_tick = gm.narrative.time_of_day
        facts = simulate(gm, MoveAction(destination="the clinic's bathroom"))
        self.assertEqual(gm.player.current_location_id, "zone_neighborhood")
        self.assertEqual(gm.player.current_place, "the clinic's bathroom")
        self.assertEqual(gm.narrative.time_of_day, before_tick)
        self.assertFalse(facts[0].startswith("Refused:"))

    def test_r2_emmas_kitchen_stays_in_the_building_as_a_spot(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        facts = simulate(gm, MoveAction(destination="Emma's kitchen"))
        self.assertEqual(gm.player.current_location_id, "zone_building")
        self.assertEqual(gm.player.current_place, "Emma's kitchen")
        self.assertFalse(facts[0].startswith("Refused:"))

    def test_r3_the_street_outside_my_apartment_keeps_the_street(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_street"
        facts = simulate(gm, MoveAction(destination="the street outside my apartment"))
        self.assertEqual(gm.player.current_location_id, "zone_street")
        self.assertFalse(facts[0].startswith("Refused:"))

    def test_r4_outside_the_building_reaches_the_street(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        facts = simulate(gm, MoveAction(destination="outside the building"))
        self.assertEqual(gm.player.current_location_id, "zone_street")
        self.assertFalse(facts[0].startswith("Refused:"))

    def test_r5_upstairs_is_a_shuffle_that_keeps_the_place(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        gm.player.current_place = "the lobby"
        facts = simulate(gm, MoveAction(destination="upstairs"))
        self.assertEqual(gm.player.current_location_id, "zone_building")
        self.assertEqual(gm.player.current_place, "the lobby")
        self.assertEqual(facts[0], "Moved upstairs within Your Building.")

    def test_r6_the_kitchen_from_home_is_a_spot_in_home(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_home"
        facts = simulate(gm, MoveAction(destination="the kitchen"))
        self.assertEqual(gm.player.current_location_id, "zone_home")
        self.assertFalse(facts[0].startswith("Refused:"))

    def test_r7_naming_the_current_zone_clears_the_place(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        gm.player.current_place = "the lobby"
        facts = simulate(gm, MoveAction(destination="Your Building"))
        self.assertEqual(facts[0], "Already in Your Building.")
        self.assertEqual(gm.player.current_place, "")


class ResidualFixExitPhraseTests(unittest.TestCase):
    """The exit rule fires only when the phrase's object names the zone
    itself, never a landmark inside it."""

    def test_outside_the_bodega_stays_on_the_street_as_a_spot(self):
        # bodega is a zone_street landmark, not the zone -- must not exit
        # into the neighborhood. A spot, not a zone change: no tick.
        gm = GameManager()
        gm.player.current_location_id = "zone_street"
        before_tick = gm.narrative.time_of_day
        facts = simulate(gm, MoveAction(destination="outside the bodega"))
        self.assertEqual(gm.player.current_location_id, "zone_street")
        self.assertEqual(gm.narrative.time_of_day, before_tick)
        self.assertFalse(facts[0].startswith("Refused:"))

    def test_leave_the_apartment_reaches_the_building_unlocked_from_inside(self):
        gm = GameManager()  # starts holding item_apartment_key
        facts = simulate(gm, MoveAction(destination="leave the apartment"))
        self.assertEqual(gm.player.current_location_id, "zone_building")
        self.assertFalse(facts[0].startswith("Refused:"))

    def test_exit_my_flat_reaches_the_building_even_without_the_key(self):
        # The apartment door is locked from the building side only -- leaving
        # needs no key.
        gm = GameManager()
        gm.player.inventory.clear()  # drop the apartment key
        facts = simulate(gm, MoveAction(destination="exit my flat"))
        self.assertEqual(gm.player.current_location_id, "zone_building")
        self.assertFalse(facts[0].startswith("Refused:"))


if __name__ == "__main__":
    unittest.main()
