"""llm-contract: The plan screen: which choices a plan leaves open before it runs, and how its steps read."""

import re
import unittest
from dataclasses import replace

from data.items import ITEMS
from data.story.mentions import DECIDED_ON_ARRIVAL
from managers.game import GameManager
from managers.plan import bind_choices, open_choices, steps_of
from modules.action.types import AddGoalAction, AttackAction, MoveAction, TakeAction
from modules.entity.item import ItemEntity
from modules.entity.zombie import ZombieState
from tests.test_simulation import add_zombie, zombie_game

BAT = ITEMS["item_baseball_bat"]


def two_bats_on_the_street() -> GameManager:
    gm = zombie_game("zone_street")
    gm.current_location.entities.extend([ItemEntity(item=BAT, condition=0), ItemEntity(item=BAT)])
    return gm


class OpenChoiceTests(unittest.TestCase):
    def test_every_target_up_to_the_first_zone_change_is_checked(self):
        gm = two_bats_on_the_street()
        plan = [
            TakeAction(item_name="Baseball Bat"),
            MoveAction(destination="out"),
            TakeAction(item_name="Baseball Bat"),
        ]
        choices = open_choices(gm, plan)
        self.assertEqual([(c.index, c.attr) for c in choices], [(0, "item_name")])

    def test_two_open_choices_in_one_plan_are_both_found(self):
        gm = two_bats_on_the_street()
        plan = [TakeAction(item_name="Baseball Bat"), MoveAction(destination="the store")]
        choices = open_choices(gm, plan)
        self.assertEqual(
            [(c.index, c.attr) for c in choices], [(0, "item_name"), (1, "destination")]
        )

    def test_a_plan_with_nothing_unclear_has_no_choices(self):
        gm = two_bats_on_the_street()
        plan = [AddGoalAction(horizon="short_term", goal_text="Find water")]
        self.assertEqual(open_choices(gm, plan), [])

    def test_checking_changes_nothing(self):
        gm = two_bats_on_the_street()
        before = (gm.narrative.minutes, len(gm.current_location.entities))
        open_choices(gm, [TakeAction(item_name="Baseball Bat"), MoveAction(destination="out")])
        self.assertEqual(before, (gm.narrative.minutes, len(gm.current_location.entities)))

    def test_a_choice_binds_into_the_field_it_answers(self):
        gm = two_bats_on_the_street()
        plan = [TakeAction(item_name="Baseball Bat")]
        (choice,) = open_choices(gm, plan)
        (bound,) = bind_choices(plan, [choice], [choice.candidates[1]])
        self.assertEqual(bound, replace(plan[0], item_name="good Baseball Bat"))
        self.assertEqual(open_choices(gm, [bound]), [])


class StepTests(unittest.TestCase):
    def test_a_default_zombie_target_is_shown_by_its_looks(self):
        gm = zombie_game("zone_street")
        add_zombie(gm, gap=3, state=ZombieState.CHASING)
        add_zombie(gm, gap=9)
        (step,) = steps_of(gm, [], [AttackAction(target_name="zombie")], [])
        self.assertIn("nearest zombie", step.text)
        self.assertEqual(step.default, "man, close, coming at you")
        self.assertIsNone(step.choice)

    def test_a_zombie_named_by_id_reads_as_its_looks(self):
        gm = zombie_game("zone_street")
        zombie = add_zombie(gm, gap=3, state=ZombieState.CHASING)
        (step,) = steps_of(gm, [], [AttackAction(target_name=zombie.zombie_id)], [])
        self.assertNotRegex(step.text, r"\bz\d+\b")
        self.assertIn("man", step.text)

    def test_a_step_after_a_zone_change_has_no_default_target_until_arrival(self):
        gm = zombie_game("zone_street")
        add_zombie(gm, gap=3, state=ZombieState.CHASING)
        plan = [
            TakeAction(item_name="Baseball Bat"),
            MoveAction(destination="out"),
            AttackAction(target_name="zombie"),
        ]
        steps = steps_of(gm, [], plan, [])
        self.assertIsNone(steps[2].default)
        self.assertIn(DECIDED_ON_ARRIVAL, steps[2].text)
        self.assertNotIn("nearest", steps[2].text)

    def test_a_step_after_a_move_that_asks_has_no_default_either(self):
        gm = zombie_game("zone_home")
        add_zombie(gm, gap=3, state=ZombieState.CHASING)
        plan = [MoveAction(destination="the apartment"), AttackAction(target_name="zombie")]
        steps = steps_of(gm, [], plan, open_choices(gm, plan))
        self.assertIsNone(steps[1].default)
        self.assertIn(DECIDED_ON_ARRIVAL, steps[1].text)

    def test_done_steps_come_first_and_an_open_choice_marks_its_step(self):
        gm = two_bats_on_the_street()
        goal = AddGoalAction(horizon="short_term", goal_text="Find water")
        take = TakeAction(item_name="Baseball Bat")
        choices = open_choices(gm, [take])
        steps = steps_of(gm, [goal], [take], choices)
        self.assertEqual([(s.done, s.choice) for s in steps], [(True, None), (False, 0)])
        self.assertIsNone(re.search(r"\d", steps[1].text))


if __name__ == "__main__":
    unittest.main()
