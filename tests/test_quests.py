"""Quest state: engine-only completion, no LLM-declarable verb for it."""

import unittest

from adapters.llm import PARSER_SYSTEM_PROMPT
from data.items import ITEMS
from data.quests import NPC_STATUSES, STORY_FLAGS, build_starting_quests
from managers.game import GameManager
from modules.action import (
    AttackAction,
    DiscoverFlagAction,
    MoveAction,
    NpcStatusAction,
    SetFlagAction,
    TakeAction,
)
from modules.quest import QuestState, QuestStatus
from tests.support import resolve_actions


class QuestAdvancementTests(unittest.TestCase):
    def test_discovering_a_flag_completes_a_matching_single_objective_quest(self):
        gm = GameManager()
        gm.quests["find_the_bunker"] = QuestState(
            quest_id="find_the_bunker",
            objectives=["discover:bunker_location"],
        )
        facts = resolve_actions(gm, DiscoverFlagAction(flag_name="bunker_location"))

        quest = gm.quests["find_the_bunker"]
        self.assertEqual(quest.status, QuestStatus.COMPLETED)
        self.assertIn("discover:bunker_location", quest.completed_objectives)
        self.assertIn("completed", facts[0])

    def test_defeating_an_npc_completes_a_matching_objective(self):
        gm = GameManager()
        gm.quests["deal_with_marcus"] = QuestState(
            quest_id="deal_with_marcus", objectives=["defeat:npc_marcus"]
        )
        marcus = gm.resolve_npc("Marcus")
        marcus.current_location_id = gm.player.current_location_id
        marcus.hit_points = 1

        resolve_actions(gm, AttackAction(target_name="Marcus"))

        self.assertEqual(gm.quests["deal_with_marcus"].status, QuestStatus.COMPLETED)

    def test_taking_an_item_completes_a_matching_objective(self):
        gm = GameManager()
        gm.quests["get_crowbar"] = QuestState(
            quest_id="get_crowbar", objectives=["take:item_crowbar"]
        )
        resolve_actions(
            gm,
            MoveAction(destination="out"),
            MoveAction(destination="out"),
            TakeAction(item_name="Crowbar"),
        )
        self.assertEqual(gm.quests["get_crowbar"].status, QuestStatus.COMPLETED)

    def test_moving_into_a_location_completes_a_matching_objective(self):
        gm = GameManager()
        gm.quests["reach_building"] = QuestState(
            quest_id="reach_building", objectives=["reach:zone_building"]
        )
        resolve_actions(gm, MoveAction(destination="out"))
        self.assertEqual(gm.quests["reach_building"].status, QuestStatus.COMPLETED)

    def test_an_npc_status_completes_a_matching_objective(self):
        gm = GameManager()
        gm.quests["marcus_likes_me"] = QuestState(
            quest_id="marcus_likes_me",
            objectives=["npc_status:npc_marcus:trusts_orton"],
        )
        resolve_actions(gm, NpcStatusAction(npc_name="Marcus", operation="ADD", status="trusts_orton"))
        self.assertEqual(gm.quests["marcus_likes_me"].status, QuestStatus.COMPLETED)

    def test_a_quest_with_multiple_objectives_needs_all_of_them(self):
        gm = GameManager()
        gm.quests["multi"] = QuestState(
            quest_id="multi", objectives=["discover:a", "discover:b"]
        )
        resolve_actions(gm, DiscoverFlagAction(flag_name="a"))
        self.assertEqual(gm.quests["multi"].status, QuestStatus.ACTIVE)

        resolve_actions(gm, DiscoverFlagAction(flag_name="b"))
        self.assertEqual(gm.quests["multi"].status, QuestStatus.COMPLETED)

    def test_unrelated_actions_do_not_touch_unrelated_quests(self):
        gm = GameManager()
        gm.quests["unrelated"] = QuestState(quest_id="unrelated", objectives=["discover:x"])
        resolve_actions(gm, SetFlagAction(flag_name="y", value=True))
        self.assertEqual(gm.quests["unrelated"].status, QuestStatus.ACTIVE)
        self.assertEqual(gm.quests["unrelated"].completed_objectives, [])

    def test_a_completed_quest_is_not_reopened_by_repeated_discovery(self):
        gm = GameManager()
        gm.quests["once"] = QuestState(quest_id="once", objectives=["discover:x"])
        resolve_actions(gm, DiscoverFlagAction(flag_name="x"))
        self.assertEqual(gm.quests["once"].status, QuestStatus.COMPLETED)

        # Discovering it again must not re-fire the completion note or crash.
        facts = resolve_actions(gm, DiscoverFlagAction(flag_name="x"))
        self.assertNotIn("completed", facts[0])


class StartingQuestContentTests(unittest.TestCase):
    """The seeded quest roster (data/quests.py) is only useful if its
    objective keys actually reference real ids -- a typo here would leave a
    quest permanently unwinnable with no error anywhere."""

    def setUp(self):
        self.gm = GameManager()

    def test_every_starting_quest_has_a_label_for_each_objective(self):
        for quest in build_starting_quests().values():
            for objective in quest.objectives:
                self.assertIn(
                    objective, quest.objective_labels, f"{quest.quest_id}: {objective}"
                )

    def test_take_objectives_reference_real_items(self):
        for quest in build_starting_quests().values():
            for objective in quest.objectives:
                if objective.startswith("take:"):
                    self.assertIn(objective.removeprefix("take:"), ITEMS)

    def test_reach_objectives_reference_real_locations(self):
        for quest in build_starting_quests().values():
            for objective in quest.objectives:
                if objective.startswith("reach:"):
                    self.assertIn(
                        objective.removeprefix("reach:"), self.gm.world.locations
                    )

    def test_npc_status_and_defeat_objectives_reference_real_npcs(self):
        for quest in build_starting_quests().values():
            for objective in quest.objectives:
                if objective.startswith("defeat:"):
                    self.assertIn(objective.removeprefix("defeat:"), self.gm.npcs)
                elif objective.startswith("npc_status:"):
                    npc_id = objective.removeprefix("npc_status:").split(":", 1)[0]
                    self.assertIn(npc_id, self.gm.npcs)

    def test_flag_and_status_objectives_reference_the_declared_vocabulary(self):
        # The one check the id-namespace tests above cannot make for us.
        # Flag names and NPC statuses come from whatever the parser model
        # invents, so an objective keyed on a name the parser was never
        # taught is unwinnable with nothing to catch it -- STORY_FLAGS /
        # NPC_STATUSES exist to close that namespace, and this asserts the
        # roster stays inside it.
        for quest in build_starting_quests().values():
            for objective in quest.objectives:
                if objective.startswith("discover:"):
                    self.assertIn(objective.removeprefix("discover:"), STORY_FLAGS)
                elif objective.startswith("npc_status:"):
                    status = objective.removeprefix("npc_status:").split(":", 1)[1]
                    self.assertIn(status, NPC_STATUSES)

    def test_the_parser_is_taught_every_declared_name(self):
        # The vocabulary is only useful if it actually reaches the model.
        for name in (*STORY_FLAGS, *NPC_STATUSES):
            self.assertIn(name, PARSER_SYSTEM_PROMPT)

    def test_a_new_game_starts_with_the_seeded_quests_active(self):
        for quest_id, quest in self.gm.quests.items():
            self.assertEqual(quest.status, QuestStatus.ACTIVE, quest_id)


if __name__ == "__main__":
    unittest.main()
