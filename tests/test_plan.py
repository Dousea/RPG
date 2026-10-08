"""llm-contract: The plan screen: which choices a plan leaves open before it runs, and how its steps read."""

import re
import unittest
from dataclasses import replace

from data.items import ITEMS
from data.melee import DOWN_TARGET
from data.story.mentions import AFTER_THE_MOVE
from managers.game import GameManager
from managers.mentions import mentionables
from managers.plan import bind_choices, open_choices, steps_of
from managers.validator import Accepted, ActionValidator
from modules.action.pins import Pinned, pin_of
from modules.action.types import (
    AddGoalAction,
    AttackAction,
    CarryAction,
    MoveAction,
    SearchAction,
    ShoveAction,
    TakeAction,
)
from modules.entity.corpse import CorpseEntity
from modules.entity.item import ItemEntity
from modules.entity.zombie import ZombieState
from modules.resolution import TargetCorpse, Transfer
from tests.support import hold
from tests.test_simulation import add_zombie, zombie_game

BAT = ITEMS["item_baseball_bat"]


def two_bats_on_the_street() -> GameManager:
    gm = zombie_game("zone_street")
    gm.current_location.entities.extend([ItemEntity(item=BAT, condition=0), ItemEntity(item=BAT)])
    return gm


def two_bodies(*garments: str) -> GameManager:
    """The street with one body per entry of `garments` (item ids), c1 first."""
    gm = zombie_game("zone_street")
    for number, garment in enumerate(garments, 1):
        gm.world.corpses[f"c{number}"] = CorpseEntity(
            corpse_id=f"c{number}",
            zone_id="zone_street",
            gap=float(number),
            female=False,
            outfit="generic01",
            died_at=0,
            rot_at_death=1,
            contents=[ItemEntity(item=ITEMS[garment])],
        )
    return gm


class BodyChoiceTests(unittest.TestCase):
    """llm-contract: Several bodies perceived and nothing in the player's words naming one is an open choice."""

    def setUp(self):
        self.gm = two_bodies("item_jacket_police", "item_jeans")

    def test_the_generic_body_and_a_body_id_the_parser_picked_both_ask(self):
        for target in ("corpse", "c2"):
            for action in (
                SearchAction(target_name=target),
                CarryAction(corpse_name=target),
                TakeAction(item_name="Jeans", from_name=target),
            ):
                with self.subTest(action=action):
                    (choice,) = open_choices(self.gm, [action], "do it to the body")
                    self.assertEqual({c.id for c in choice.candidates}, {"c1", "c2"})
                    self.assertTrue(all(c.kind == "corpse" for c in choice.candidates))

    def test_the_candidates_are_named_as_the_mention_list_names_them(self):
        (choice,) = open_choices(self.gm, [SearchAction(target_name="corpse")], "search the body")
        listed = {m.id: m for m in mentionables(self.gm) if m.kind == "corpse"}
        for candidate in choice.candidates:
            self.assertEqual(candidate.name, listed[candidate.id].name)
            self.assertEqual(candidate.description, listed[candidate.id].description)
        self.assertEqual(len({c.name for c in choice.candidates}), 2)

    def test_go_binds_the_pick_as_a_body_pin(self):
        plan = [SearchAction(target_name="corpse")]
        (choice,) = open_choices(self.gm, plan, "search the body")
        pick = next(c for c in choice.candidates if c.id == "c2")
        (bound,) = bind_choices(plan, [choice], [pick])
        assert isinstance(bound, SearchAction)
        pin = pin_of(bound.target_name, "corpse")
        assert pin is not None
        self.assertEqual(pin.entity_id, "c2")
        self.assertEqual(open_choices(self.gm, [bound], "search the body"), [])
        result = ActionValidator(self.gm).validate(bound)
        assert isinstance(result, Accepted)
        self.assertEqual(result.expect(TargetCorpse).corpse_id, "c2")

    def test_go_binds_the_pick_for_carry_and_take_too(self):
        for action, field in (
            (CarryAction(corpse_name="corpse"), "corpse_name"),
            (TakeAction(item_name="Jeans", from_name="corpse"), "from_name"),
        ):
            with self.subTest(action=action.verb):
                (choice,) = open_choices(self.gm, [action], "do it to the body")
                pick = next(c for c in choice.candidates if c.id == "c2")
                (bound,) = bind_choices([action], [choice], [pick])
                pin = pin_of(getattr(bound, field), "corpse")
                assert pin is not None
                self.assertEqual(pin.entity_id, "c2")
                self.assertEqual(open_choices(self.gm, [bound], "do it to the body"), [])

    def test_a_label_inside_another_bodys_label_does_not_name_a_body(self):
        stripped = two_bodies("item_jacket_police", "item_jeans")
        stripped.world.corpses["c1"].contents.clear()
        plan = [SearchAction(target_name="c1")]
        self.assertTrue(open_choices(stripped, plan, "search the man in jeans"))
        self.assertTrue(open_choices(stripped, plan, "search the man"))

        jeans = [SearchAction(target_name="c2")]
        self.assertEqual(open_choices(stripped, jeans, "search the man in jeans"), [])

    def test_a_word_inside_another_word_names_nothing(self):
        gm = two_bodies("item_jeans", "item_jeans")
        gm.world.corpses["c1"].female = True
        plan = [SearchAction(target_name="c2")]
        self.assertTrue(open_choices(gm, plan, "search the woman in jeans"))
        self.assertEqual(open_choices(gm, plan, "search the man in jeans"), [])

    def test_words_only_the_chosen_body_matches_ask_nothing(self):
        for text in ("search the man in jeans", "search the body in the jeans", "search the JEANS"):
            with self.subTest(text):
                self.assertEqual(open_choices(self.gm, [SearchAction(target_name="c2")], text), [])
        (choice,) = open_choices(
            self.gm, [SearchAction(target_name="c2")], "search the man in the jacket"
        )
        self.assertEqual({c.id for c in choice.candidates}, {"c1", "c2"})

    def test_a_garment_word_both_bodies_have_names_neither(self):
        gm = two_bodies("item_jeans", "item_jeans")
        self.assertTrue(open_choices(gm, [SearchAction(target_name="c1")], "search the jeans"))

    def test_a_carried_body_is_named_by_a_phrase_for_carrying_it(self):
        self.gm.player.carrying_corpse = "c1"
        plan = [SearchAction(target_name="c1")]
        self.assertEqual(open_choices(self.gm, plan, "search the body I carry"), [])
        self.assertTrue(open_choices(self.gm, plan, "search the body"))

    def test_one_body_a_pinned_body_and_a_place_ask_nothing(self):
        lone = two_bodies("item_jeans")
        self.assertEqual(open_choices(lone, [SearchAction(target_name="corpse")], "search"), [])
        pinned = Pinned("c2", "corpse", "c2")
        self.assertEqual(
            open_choices(self.gm, [SearchAction(target_name=pinned)], "search the body"), []
        )
        self.assertEqual(
            open_choices(self.gm, [SearchAction(target_name="Kitchen")], "search the kitchen"), []
        )

    def test_two_zombies_still_default_to_the_nearest(self):
        gm = zombie_game("zone_street")
        add_zombie(gm, gap=3, state=ZombieState.CHASING)
        add_zombie(gm, gap=9)
        self.assertEqual(
            open_choices(gm, [AttackAction(target_name="zombie")], "hit the zombie"), []
        )


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

    def test_a_zone_the_parser_picked_for_a_kind_word_is_an_open_choice(self):
        gm = zombie_game("zone_building")
        plan = [MoveAction(destination="Your Apartment")]
        (choice,) = open_choices(gm, plan, "go to the apartment")
        self.assertEqual((choice.index, choice.attr), (0, "destination"))
        self.assertEqual(
            {c.id for c in choice.candidates},
            {"zone_home", "zone_building", "zone_flat_vacant", "zone_flat_tenant"},
        )
        pick = next(c for c in choice.candidates if c.id == "zone_flat_vacant")
        (bound,) = bind_choices(plan, [choice], [pick])
        self.assertEqual(open_choices(gm, [bound], "go to the apartment"), [])

    def test_a_pinned_zone_asks_nothing(self):
        gm = zombie_game("zone_building")
        pinned = Pinned("Your Apartment", "zone", "zone_home")
        self.assertEqual(
            open_choices(gm, [MoveAction(destination=pinned)], "go to the apartment"), []
        )

    def test_checking_changes_nothing(self):
        gm = two_bats_on_the_street()
        before = (gm.narrative.minutes, len(gm.current_location.entities))
        open_choices(gm, [TakeAction(item_name="Baseball Bat"), MoveAction(destination="out")])
        self.assertEqual(before, (gm.narrative.minutes, len(gm.current_location.entities)))

    def test_a_choice_binds_into_the_field_it_answers(self):
        gm = two_bats_on_the_street()
        plan = [TakeAction(item_name="Baseball Bat")]
        (choice,) = open_choices(gm, plan)
        good = next(c for c in choice.candidates if c.description == "good")
        (bound,) = bind_choices(plan, [choice], [good])
        self.assertEqual(bound, replace(plan[0], item_name=good.written()))
        self.assertEqual(open_choices(gm, [bound]), [])
        result = ActionValidator(gm).validate(bound)
        assert isinstance(result, Accepted)
        self.assertEqual([e.broken for e in result.expect(Transfer).entities], [False])


class StepTests(unittest.TestCase):
    def test_a_default_zombie_target_is_shown_by_its_looks(self):
        gm = zombie_game("zone_street")
        add_zombie(gm, gap=3, state=ZombieState.CHASING)
        add_zombie(gm, gap=9)
        (step,) = steps_of(gm, [], [AttackAction(target_name="zombie")], [])
        self.assertIn("nearest zombie", step.text)
        self.assertEqual(step.default, "man, close, coming at you")
        self.assertIsNone(step.choice)

    def test_a_swing_that_reaches_several_says_so_without_a_count(self):
        gm = zombie_game("zone_street")
        hold(gm, "item_crowbar")
        for _ in range(3):
            add_zombie(gm, gap=1, state=ZombieState.CHASING)
        (step,) = steps_of(gm, [], [ShoveAction(target_name="zombie")], [])
        self.assertIn("nearest zombie and the ones beside it", step.text)
        self.assertIsNone(re.search(r"\d", step.text))

        gm = zombie_game("zone_street")
        hold(gm, "item_crowbar")
        add_zombie(gm, gap=1, state=ZombieState.CHASING)
        add_zombie(gm, gap=5, state=ZombieState.CHASING)
        (step,) = steps_of(gm, [], [ShoveAction(target_name="zombie")], [])
        self.assertNotIn("beside", step.text)

    def test_a_floor_attack_names_the_nearest_down_zombie_and_those_beside_it(self):
        gm = zombie_game("zone_street")
        hold(gm, "item_crowbar")
        add_zombie(gm, gap=1, state=ZombieState.CHASING)
        for _ in range(2):
            down = add_zombie(gm, gap=1, state=ZombieState.CHASING)
            down.down_until = gm.narrative.minutes + 5
        (step,) = steps_of(gm, [], [AttackAction(target_name=DOWN_TARGET)], [])
        self.assertIn("nearest zombie and the ones beside it", step.text)
        self.assertIsNotNone(step.default)

    def test_a_zombie_named_by_id_reads_as_its_looks(self):
        gm = zombie_game("zone_street")
        zombie = add_zombie(gm, gap=3, state=ZombieState.CHASING)
        (step,) = steps_of(gm, [], [AttackAction(target_name=zombie.zombie_id)], [])
        self.assertNotRegex(step.text, r"\bz\d+\b")
        self.assertIn("man", step.text)

    def test_the_steps_after_a_zone_change_give_way_to_the_arrival_line(self):
        gm = zombie_game("zone_street")
        add_zombie(gm, gap=3, state=ZombieState.CHASING)
        plan = [
            TakeAction(item_name="Baseball Bat"),
            MoveAction(destination="out"),
            AttackAction(target_name="zombie"),
        ]
        steps = steps_of(gm, [], plan, [])
        self.assertEqual(len(steps), 3)
        self.assertEqual(steps[2].text, AFTER_THE_MOVE)
        self.assertIsNone(steps[2].default)
        self.assertIsNone(steps[2].choice)
        self.assertNotIn("zombie", " ".join(step.text for step in steps))

    def test_a_plan_without_a_zone_change_has_no_arrival_line(self):
        gm = two_bats_on_the_street()
        steps = steps_of(gm, [], [TakeAction(item_name="Baseball Bat")], [])
        self.assertNotIn(AFTER_THE_MOVE, [step.text for step in steps])

    def test_a_step_after_a_move_that_asks_gives_way_to_the_arrival_line_too(self):
        gm = zombie_game("zone_home")
        add_zombie(gm, gap=3, state=ZombieState.CHASING)
        plan = [MoveAction(destination="the apartment"), AttackAction(target_name="zombie")]
        steps = steps_of(gm, [], plan, open_choices(gm, plan))
        self.assertEqual(steps[1].text, AFTER_THE_MOVE)

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
