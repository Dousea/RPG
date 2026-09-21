"""ContextBuilder: the knowledge-firewall boundary between state and prompts."""

import unittest

from managers.context import ContextBuilder
from managers.game import GameManager
from modules.action import DiscoverFlagAction, MoveAction, SetFlagAction, TakeAction
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


class NpcGoalVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()
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
        self.gm.quests["get_key"] = QuestState(
            quest_id="get_key",
            title="Get the Key",
            objectives=["take:item_storage_key", "reach:location_id_storage"],
            objective_labels={
                "take:item_storage_key": "Find the storage key",
                "reach:location_id_storage": "Get into the storage room",
            },
        )
        resolve_actions(
            self.gm, MoveAction(destination="north"), TakeAction(item_name="Storage Room Key")
        )
        prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("[x] Find the storage key", prompt)
        self.assertIn("[ ] Get into the storage room", prompt)

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
