"""GameManager: starting state, prompt assembly, memory tiers.

Action-verb behavior (what's legal, what it does) now lives in
tests/test_validator.py and tests/test_simulation.py -- there is no
`apply_action`/`_ACTION_HANDLERS` on GameManager anymore; the Action
Validator and Simulation Core are the only path to mutating state.
"""

import unittest

from managers.game import (
    CONDITION_LADDERS,
    GameManager,
    MAX_RECENT_EVENTS,
    SUMMARY_THRESHOLD,
)
from modules.action import (
    MoveAction,
    NARRATIVE_CONDITION_FIELDS,
    NpcStatusAction,
    TakeAction,
    UpdateRelationshipAction,
)
from tests.support import resolve_actions


class StartingStateTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()

    def test_player_starts_at_home(self):
        self.assertEqual(self.gm.player.current_location_id, "zone_home")
        self.assertEqual(
            [e.item.name for e in self.gm.player.inventory], ["Apartment Key"]
        )

    def test_every_connection_points_at_a_real_location(self):
        # Regression: a location keyed under the wrong id would leave a
        # connection pointing nowhere, with nothing to catch it.
        for location in self.gm.world.locations.values():
            for direction, target in location.connections.items():
                self.assertIn(
                    target,
                    self.gm.world.locations,
                    f"{location.id} {direction} -> missing {target}",
                )

    def test_location_keys_match_their_ids(self):
        for key, location in self.gm.world.locations.items():
            self.assertEqual(key, location.id)

    def test_zone_roster_is_exactly_the_four_zones(self):
        self.assertEqual(
            set(self.gm.world.locations.keys()),
            {"zone_home", "zone_building", "zone_street", "zone_neighborhood"},
        )

    def test_resolve_location_by_alias(self):
        self.assertEqual(
            self.gm.resolve_location("the pharmacy").id, "zone_neighborhood"
        )
        self.assertEqual(
            self.gm.resolve_location("emma's apartment").id, "zone_building"
        )
        # Whole-word fallback: "emma's apartment" is a more specific alias of
        # zone_building, so this must not collide with it.
        self.assertEqual(
            self.gm.resolve_location("back to my apartment").id, "zone_home"
        )
        self.assertIsNone(self.gm.resolve_location("Atlantis"))

    def test_outside_follows_the_exit_first(self):
        # "outside" is also a zone_street alias; DIRECTION_SYNONYMS must make
        # the exit win over the current zone's own alias.
        self.gm.player.current_location_id = "zone_street"
        self.assertEqual(self.gm.resolve_location("inside").id, "zone_building")

    def test_npc_roster_is_loaded_and_placed(self):
        self.assertEqual(len(self.gm.npcs), 3)
        for npc in self.gm.npcs.values():
            self.assertIn(npc.current_location_id, self.gm.world.locations)

    def test_starting_relationships_are_npc_towards_player(self):
        # Direction matters: every reader asks how the NPC regards the player,
        # so seeding the other way round would leave the values unreachable.
        self.assertEqual(
            self.gm.relationship_manager.get_trust("npc_emma", "player"), 5
        )
        # The prompt shows the band, never the number -- see the firewall
        # tests. Orton now starts alone in his apartment, so move to where
        # Emma is to see her disposition line.
        self.gm.player.current_location_id = "zone_building"
        self.assertIn("trust: unformed", self.gm.build_narrator_prompt("look"))

    def test_two_games_do_not_share_mutable_state(self):
        # Locations and NPCs used to be module-level singletons, so a dropped
        # item or an NPC's status leaked into the next game after a reset.
        first = GameManager()
        resolve_actions(
            first,
            MoveAction(destination="out"),
            MoveAction(destination="out"),
            TakeAction(item_name="Crowbar"),
            NpcStatusAction(npc_name="Emma", operation="ADD", status="frightened"),
        )

        second = GameManager()
        street = second.world.locations["zone_street"]
        self.assertIn("Crowbar", [e.item.name for e in street.entities])
        self.assertEqual(second.resolve_npc("Emma").status, ["friendly", "curious about new neighbor"])
        # Starting key, not an empty inventory.
        self.assertEqual([e.item.name for e in second.player.inventory], ["Apartment Key"])


class PromptTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()

    def test_prompt_contains_every_section(self):
        prompt = self.gm.build_narrator_prompt("look around", deep_memories=["Orton heard sirens."])
        for section in (
            "[CHARACTER]",
            "[DEEP MEMORY]",
            "[CURRENT LOCATION]",
            "[ITEMS IN CURRENT LOCATION]",
            "[NEARBY LOCATIONS]",
            "[NPCS PRESENT]",
            "[SUMMARY OF PAST EVENTS]",
            "[RECENT EVENTS]",
            "[OUTCOMES]",
            "[SCENE]",
        ):
            self.assertIn(section, prompt)

    def test_prompt_carries_deep_memories(self):
        prompt = self.gm.build_narrator_prompt("look", deep_memories=["Orton heard sirens."])
        self.assertIn("Orton heard sirens.", prompt)

    def test_prompt_carries_outcome_facts(self):
        self.assertIn("(No actions were taken this turn)", self.gm.build_narrator_prompt("look"))
        prompt = self.gm.build_narrator_prompt("look", outcome_facts=["Move to Office: succeeded."])
        self.assertIn("[OUTCOMES]", prompt)
        self.assertIn("Move to Office: succeeded.", prompt)

    def test_prompt_carries_pending_corrections(self):
        self.assertIn("(Nothing to correct)", self.gm.build_narrator_prompt("look"))
        self.gm.narrative.pending_corrections = ["TAKE Medkit -- No 'Medkit' here to take."]
        prompt = self.gm.build_narrator_prompt("look")
        self.assertIn("[CONTINUITY]", prompt)
        self.assertIn("No 'Medkit' here to take.", prompt)

    def test_prompt_describes_present_npcs_only(self):
        # Orton now starts alone in his apartment.
        self.gm.player.current_location_id = "zone_building"
        prompt = self.gm.build_narrator_prompt("look")
        self.assertIn("Emma", prompt)  # in the building with the player
        self.assertNotIn("Jen", prompt)  # in the neighborhood

    def test_prompt_lists_exits_by_direction(self):
        self.assertIn("Out: Your Building", self.gm.build_narrator_prompt("look"))

    def test_prompt_reflects_recent_events_and_summaries(self):
        self.assertIn("(No recent events)", self.gm.build_narrator_prompt("look"))
        self.gm.record_event("Orton locked the door.")
        self.gm.memory.summaries.append("The city grew quiet.")
        prompt = self.gm.build_narrator_prompt("look")
        self.assertIn("Orton locked the door.", prompt)
        self.assertIn("The city grew quiet.", prompt)


class ParserPromptTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()

    def test_parser_prompt_contains_minimal_scene_context(self):
        prompt = self.gm.build_parser_prompt("go north")
        for section in (
            "[LOCATION]",
            "[EXITS]",
            "[ITEMS HERE]",
            "[NPCS HERE]",
            "[INVENTORY]",
            "[EQUIPPED]",
            "[PLAYER INPUT]",
        ):
            self.assertIn(section, prompt)
        self.assertIn("go north", prompt)

    def test_parser_prompt_has_no_prose_context(self):
        # The parser proposes actions, not prose -- it gets none of the
        # narrator's memory/summary/disposition sections.
        prompt = self.gm.build_parser_prompt("look")
        for section in ("[DEEP MEMORY]", "[SUMMARY OF PAST EVENTS]", "[OUTCOMES]"):
            self.assertNotIn(section, prompt)

    def test_parser_prompt_lists_present_npcs_by_name_only(self):
        # Orton now starts alone in his apartment.
        self.gm.player.current_location_id = "zone_building"
        prompt = self.gm.build_parser_prompt("look")
        self.assertIn("Emma", prompt)
        self.assertNotIn("Disposition", prompt)


class KnowledgeFirewallTests(unittest.TestCase):
    """The prompt must not hand the narrator numbers Orton cannot know."""

    def setUp(self):
        self.gm = GameManager()
        # Orton now starts alone in his apartment; Emma starts in zone_building.
        self.gm.player.current_location_id = "zone_building"

    def _npcs_section(self) -> str:
        prompt = self.gm.build_narrator_prompt("look")
        return prompt.split("[NPCS PRESENT]")[1].split("[SUMMARY OF PAST EVENTS]")[0]

    def test_raw_relationship_scores_never_reach_the_prompt(self):
        resolve_actions(
            self.gm,
            UpdateRelationshipAction(npc_name="Emma", axis="affection", amount=37),
            UpdateRelationshipAction(npc_name="Emma", axis="trust", amount=42),
        )
        section = self._npcs_section()

        self.assertIn("Emma", section)
        for leak in ("37", "42", "affection", "trust +"):
            self.assertNotIn(leak, section)

    def test_scores_are_reported_as_bands(self):
        resolve_actions(
            self.gm,
            UpdateRelationshipAction(npc_name="Emma", axis="affection", amount=50),
            UpdateRelationshipAction(npc_name="Emma", axis="trust", amount=45),
        )
        self.assertIn(
            "Disposition: friendly (trust: solid)", self.gm.build_narrator_prompt("look")
        )

    def test_bands_move_with_the_underlying_scores(self):
        self.assertIn(
            "Disposition: neutral (trust: unformed)", self.gm.build_narrator_prompt("look")
        )
        resolve_actions(
            self.gm,
            UpdateRelationshipAction(npc_name="Emma", axis="affection", amount=-50),
            UpdateRelationshipAction(npc_name="Emma", axis="trust", amount=-45),
        )
        self.assertIn(
            "Disposition: hostile (trust: broken)", self.gm.build_narrator_prompt("look")
        )


class ConditionLadderDriftTests(unittest.TestCase):
    def test_ladder_keys_match_the_declared_narrative_fields(self):
        # modules/action.NARRATIVE_CONDITION_FIELDS gates parsing/validation
        # of which fields are laddered at all; managers/game.CONDITION_LADDERS
        # is what they're laddered against. Nothing enforces they agree except
        # this test -- if they drift, one field silently stops being laddered.
        self.assertEqual(tuple(CONDITION_LADDERS), NARRATIVE_CONDITION_FIELDS)


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()

    def test_recent_buffer_is_capped_and_newest_first(self):
        for i in range(MAX_RECENT_EVENTS + 3):
            self.gm.record_event(f"Event {i}")
        self.assertEqual(len(self.gm.memory.recent_events), MAX_RECENT_EVENTS)
        self.assertEqual(self.gm.memory.recent_events[0], f"Event {MAX_RECENT_EVENTS + 2}")

    def test_full_log_keeps_everything(self):
        for i in range(20):
            self.gm.record_event(f"Event {i}")
        self.assertEqual(len(self.gm.memory.full_event_log), 20)

    def test_empty_events_are_ignored(self):
        self.gm.record_event("")
        self.assertEqual(self.gm.memory.full_event_log, [])

    def test_summary_batches_appear_once_the_threshold_is_crossed(self):
        for i in range(SUMMARY_THRESHOLD - 1):
            self.gm.record_event(f"Event {i}")
        self.assertEqual(self.gm.events_pending_summary(), [])

        self.gm.record_event("One more")
        self.assertEqual(len(self.gm.events_pending_summary()), SUMMARY_THRESHOLD)

        # Once summarized, the same batch is not offered again.
        self.gm.memory.summaries.append("A summary.")
        self.assertEqual(self.gm.events_pending_summary(), [])


if __name__ == "__main__":
    unittest.main()
