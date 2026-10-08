"""Quest state: engine-only completion, no LLM-declarable verb for it."""

import unittest

from data.items import ITEMS
from data.story.quests import TAKE_ANY_WEAPON, build_starting_quests
from managers.game import GameManager
from managers.simulation import SimulationCore
from modules.action.types import (
    AddGoalAction,
    AttackAction,
    MoveAction,
    TakeAction,
)
from modules.entity.item import ItemEntity
from modules.story.quest import QuestState, QuestStatus
from tests.support import adjust_regard, resolve_actions


class QuestAdvancementTests(unittest.TestCase):
    def test_discovering_a_flag_completes_a_matching_single_objective_quest(self):
        gm = GameManager()
        gm.quests["find_the_bunker"] = QuestState(
            quest_id="find_the_bunker",
            objectives=["discover:bunker_location"],
        )
        note = SimulationCore(gm).discover_flag("bunker_location")

        quest = gm.quests["find_the_bunker"]
        self.assertEqual(quest.status, QuestStatus.COMPLETED)
        self.assertIn("discover:bunker_location", quest.completed_objectives)
        self.assertIn("completed", note)

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
        resolve_actions(gm, MoveAction(destination="out"))
        resolve_actions(gm, MoveAction(destination="out"))
        resolve_actions(gm, TakeAction(item_name="Crowbar"))
        self.assertEqual(gm.quests["get_crowbar"].status, QuestStatus.COMPLETED)

    def _weapon_quest_gm(self, item_id):
        gm = GameManager()
        gm.quests.clear()
        gm.quests["quest_supply_run"] = build_starting_quests()["quest_supply_run"]
        gm.quests["quest_supply_run"].objectives = [TAKE_ANY_WEAPON, "reach:zone_neighborhood"]
        gm.current_location.entities.append(ItemEntity(item=ITEMS[item_id]))
        return gm

    def test_taking_any_melee_weapon_ticks_the_weapon_step(self):
        for item_id, name in (("item_baseball_bat", "Baseball bat"), ("item_crowbar", "Crowbar")):
            with self.subTest(item_id):
                gm = self._weapon_quest_gm(item_id)
                facts = resolve_actions(gm, TakeAction(item_name=name))
                quest = gm.quests["quest_supply_run"]
                self.assertIn(TAKE_ANY_WEAPON, quest.completed_objectives)
                self.assertIn(quest.objective_labels[TAKE_ANY_WEAPON], str(facts))
                self.assertIn(quest.title, str(facts))
                self.assertNotIn(TAKE_ANY_WEAPON, str(facts))

    def test_taking_a_non_weapon_does_not_tick_the_weapon_step(self):
        gm = self._weapon_quest_gm("item_water_bottle")
        resolve_actions(gm, TakeAction(item_name="Water bottle"))
        self.assertEqual(gm.quests["quest_supply_run"].completed_objectives, [])

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
            objectives=["npc_status:npc_marcus:trusts_player"],
        )
        adjust_regard(gm, "npc_marcus", trust=40)
        resolve_actions(gm, AddGoalAction(horizon="short_term", goal_text="Rest"))
        self.assertEqual(gm.quests["marcus_likes_me"].status, QuestStatus.COMPLETED)

    def test_a_quest_with_multiple_objectives_needs_all_of_them(self):
        gm = GameManager()
        gm.quests["multi"] = QuestState(quest_id="multi", objectives=["discover:a", "discover:b"])
        core = SimulationCore(gm)
        core.discover_flag("a")
        self.assertEqual(gm.quests["multi"].status, QuestStatus.ACTIVE)

        core.discover_flag("b")
        self.assertEqual(gm.quests["multi"].status, QuestStatus.COMPLETED)

    def test_unrelated_actions_do_not_touch_unrelated_quests(self):
        gm = GameManager()
        gm.quests["unrelated"] = QuestState(quest_id="unrelated", objectives=["discover:x"])
        SimulationCore(gm).discover_flag("y")
        self.assertEqual(gm.quests["unrelated"].status, QuestStatus.ACTIVE)
        self.assertEqual(gm.quests["unrelated"].completed_objectives, [])

    def test_a_completed_quest_is_not_reopened_by_repeated_discovery(self):
        gm = GameManager()
        gm.quests["once"] = QuestState(quest_id="once", objectives=["discover:x"])
        core = SimulationCore(gm)
        core.discover_flag("x")
        self.assertEqual(gm.quests["once"].status, QuestStatus.COMPLETED)

        # Discovering it again must not re-fire the completion note or crash.
        self.assertNotIn("completed", core.discover_flag("x"))


class StartingQuestContentTests(unittest.TestCase):
    """The seeded quest roster (data/quests.py) is only useful if its
    objective keys actually reference real ids -- a typo here would leave a
    quest permanently unwinnable with no error anywhere."""

    def setUp(self):
        self.gm = GameManager()

    def test_every_starting_quest_has_a_label_for_each_objective(self):
        for quest in build_starting_quests().values():
            for objective in quest.objectives:
                self.assertIn(objective, quest.objective_labels, f"{quest.quest_id}: {objective}")

    def test_take_objectives_reference_real_items(self):
        for quest in build_starting_quests().values():
            for objective in quest.objectives:
                if objective.startswith("take:") and objective != TAKE_ANY_WEAPON:
                    self.assertIn(objective.removeprefix("take:"), ITEMS)

    def test_reach_objectives_reference_real_locations(self):
        for quest in build_starting_quests().values():
            for objective in quest.objectives:
                if objective.startswith("reach:"):
                    self.assertIn(objective.removeprefix("reach:"), self.gm.world.locations)

    def test_npc_status_and_defeat_objectives_reference_real_npcs(self):
        for quest in build_starting_quests().values():
            for objective in quest.objectives:
                if objective.startswith("defeat:"):
                    self.assertIn(objective.removeprefix("defeat:"), self.gm.npcs)
                elif objective.startswith("npc_status:"):
                    npc_id = objective.removeprefix("npc_status:").split(":", 1)[0]
                    self.assertIn(npc_id, self.gm.npcs)

    def test_a_new_game_starts_with_the_seeded_quests_active(self):
        for quest_id, quest in self.gm.quests.items():
            self.assertEqual(quest.status, QuestStatus.ACTIVE, quest_id)


if __name__ == "__main__":
    unittest.main()


class QuestFactTests(unittest.TestCase):
    """llm-contract: Outcome facts name a quest by its title, never its id."""

    def test_an_objective_fact_names_the_title_and_label(self):
        gm = GameManager()
        resolve_actions(gm, MoveAction(destination="out"))
        resolve_actions(gm, MoveAction(destination="out"))
        facts = resolve_actions(gm, TakeAction(item_name="Crowbar"))
        self.assertIn(
            'Quest "Make a Supply Run": done -- Find something to defend yourself with.',
            " ".join(facts),
        )

    def test_a_completion_fact_names_the_title(self):
        gm = GameManager()
        note = SimulationCore(gm).discover_flag("apocalypse_cause")
        self.assertIn('Quest "Understand What\'s Happening" completed.', note)
