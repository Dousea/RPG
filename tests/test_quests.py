"""Quest state: engine-only completion, no LLM-declarable verb for it."""

import unittest

from managers.game import GameManager
from modules.action import AttackAction, DiscoverFlagAction, SetFlagAction
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


if __name__ == "__main__":
    unittest.main()
