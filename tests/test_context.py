"""ContextBuilder: the knowledge-firewall boundary between state and prompts."""

import unittest

from managers.context import ContextBuilder
from managers.game import GameManager
from modules.action import DiscoverFlagAction, MoveAction, SetFlagAction
from modules.quest import QuestState
from tests.support import resolve_actions


class WorldFlagFirewallTests(unittest.TestCase):
    """doc 11's actual complaint: every world flag went out unfiltered,
    whether or not anything in the story ever revealed it to the player."""

    def setUp(self):
        self.gm = GameManager()
        self.builder = ContextBuilder(self.gm)

    def test_an_undiscovered_flag_never_reaches_the_narrator_prompt(self):
        resolve_actions(self.gm, SetFlagAction(flag_name="power_grid_stable", value=False))
        prompt = self.builder.build_narrator_prompt("look")
        self.assertNotIn("power_grid_stable", prompt)

    def test_a_discovered_flag_reaches_the_narrator_prompt(self):
        resolve_actions(
            self.gm,
            SetFlagAction(flag_name="power_grid_stable", value=False),
            DiscoverFlagAction(flag_name="power_grid_stable"),
        )
        prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("power_grid_stable=False", prompt)

    def test_discovering_a_flag_that_was_never_set_is_harmless(self):
        resolve_actions(self.gm, DiscoverFlagAction(flag_name="never_set"))
        prompt = self.builder.build_narrator_prompt("look")
        # Nothing to show -- the flag has no value -- but this must not raise.
        self.assertIn("Flags: None", prompt)

    def test_setting_the_same_flag_twice_does_not_undiscover_it(self):
        resolve_actions(
            self.gm,
            SetFlagAction(flag_name="power_grid_stable", value=False),
            DiscoverFlagAction(flag_name="power_grid_stable"),
            SetFlagAction(flag_name="power_grid_stable", value=True),
        )
        prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("power_grid_stable=True", prompt)


class ParserPromptFirewallTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()
        self.builder = ContextBuilder(self.gm)

    def test_parser_prompt_carries_no_relationship_or_flag_data_at_all(self):
        resolve_actions(
            self.gm,
            SetFlagAction(flag_name="power_grid_stable", value=False),
            DiscoverFlagAction(flag_name="power_grid_stable"),
        )
        prompt = self.builder.build_parser_prompt("look")
        self.assertNotIn("power_grid_stable", prompt)
        self.assertNotIn("Disposition", prompt)


class ZoneContextTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()
        self.builder = ContextBuilder(self.gm)

    def test_parser_prompt_lists_the_zone_roster(self):
        # The parser can only aim MOVE_TO at a zone it has been told exists.
        prompt = self.builder.build_parser_prompt("look")
        self.assertIn("[ZONES]", prompt)
        for zone in ("Your Apartment", "Your Building", "The Street", "The Neighborhood"):
            self.assertIn(zone, prompt)

    def test_prompts_carry_the_specific_spot(self):
        resolve_actions(self.gm, MoveAction(destination="the kitchen"))
        parser_prompt = self.builder.build_parser_prompt("look")
        narrator_prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("Specific spot: the kitchen", parser_prompt)
        self.assertIn("Specific spot: the kitchen", narrator_prompt)


class NpcGoalVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()
        # Orton now starts alone in his apartment; Emma starts in zone_building.
        self.gm.player.current_location_id = "zone_building"
        self.builder = ContextBuilder(self.gm)

    def test_npc_goals_are_shown_as_visible_intent(self):
        emma = self.gm.resolve_npc("Emma")
        emma.goals.append("find out who the new neighbor is")
        prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("Visible intent: find out who the new neighbor is", prompt)

    def test_npc_knowledge_is_never_rendered(self):
        emma = self.gm.resolve_npc("Emma")
        emma.knowledge.add("secret_bunker_location")
        prompt = self.builder.build_narrator_prompt("look")
        self.assertNotIn("secret_bunker_location", prompt)


class QuestVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()
        self.builder = ContextBuilder(self.gm)

    def test_an_active_quests_title_and_open_objective_are_shown(self):
        self.gm.quests.clear()
        self.gm.quests["find_the_bunker"] = QuestState(
            quest_id="find_the_bunker",
            title="Find the Bunker",
            objectives=["discover:bunker_location"],
            objective_labels={"discover:bunker_location": "Locate the bunker"},
        )
        prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("Find the Bunker", prompt)
        self.assertIn("[ ] Locate the bunker", prompt)

    def test_a_completed_objective_is_checked_off(self):
        # Two objectives, not one -- a quest whose only objective just
        # finished completes outright and drops out of [QUESTS] entirely
        # (see ContextBuilder._quests_section), so a single-objective quest
        # here would never render its own checkmark to assert on.
        self.gm.quests.clear()
        self.gm.quests["get_gear"] = QuestState(
            quest_id="get_gear",
            title="Get Some Gear",
            objectives=["reach:zone_street", "take:item_crowbar"],
            objective_labels={
                "reach:zone_street": "Get to the street",
                "take:item_crowbar": "Find something to defend yourself with",
            },
        )
        resolve_actions(
            self.gm, MoveAction(destination="out"), MoveAction(destination="out")
        )
        prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("[x] Get to the street", prompt)
        self.assertIn("[ ] Find something to defend yourself with", prompt)

    def test_a_quest_with_no_label_falls_back_to_its_raw_key(self):
        self.gm.quests.clear()
        self.gm.quests["mystery"] = QuestState(
            quest_id="mystery", objectives=["discover:something"]
        )
        prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("[ ] discover:something", prompt)

    def test_no_active_quests_renders_none(self):
        self.gm.quests.clear()
        prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("[QUESTS]", prompt)
        self.assertIn("None", prompt)


if __name__ == "__main__":
    unittest.main()
