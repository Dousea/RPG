"""The state questions built from a turn's facts (llm-contract: The fact check)."""

import dataclasses
import logging
import unittest

from data.story import check as story_check_k
from managers.game import GameManager
from managers.story.check import StateQuestion, build_questions, plan_questions
from modules.action.types import ShoveAction, TalkAction, UnsupportedAction, UseItemAction
from modules.entity.zombie import ZombieEntity, ZombieState


def zombie(zombie_id: str) -> ZombieEntity:
    return ZombieEntity(
        zombie_id=zombie_id,
        zone_id="zone_home",
        health=2.0,
        speed_type=3,
        speed_mod=0.6,
        lunger=False,
        strength=3,
        memory=800,
        sight=2,
        hearing=2,
        state=ZombieState.CHASING,
        gap=3.0,
    )


class BuildQuestionsTests(unittest.TestCase):
    """llm-contract: The fact check."""

    def setUp(self):
        self.manager = GameManager()
        self.manager.world.zombies["z12"] = zombie("z12")

    def test_a_zombie_missing_from_the_world_was_killed(self):
        (question,) = build_questions(self.manager, ["You shoot z7 and it falls."])
        self.assertEqual(question.allowed, frozenset({"yes", "unclear"}))
        self.assertEqual(question.correction, "The zombie is dead at the end of this turn.")

    def test_a_zombie_in_the_world_is_alive(self):
        (question,) = build_questions(self.manager, ["z12 staggers back.", "You are winded."])
        self.assertEqual(question.allowed, frozenset({"no", "unclear"}))
        self.assertEqual(question.correction, "The zombie is still alive at the end of this turn.")

    def test_the_question_and_options_are_fixed_and_in_order(self):
        (question,) = build_questions(self.manager, ["z12 staggers back."])
        self.assertEqual(
            question.text,
            "By the end of the story, has the zombie been killed or put down for good?",
        )
        self.assertEqual(
            question.options,
            (
                ("yes", "The story says or implies the zombie is dead or will not get up again."),
                ("no", "The zombie is still alive, even if hurt or knocked down."),
                ("unclear", "The story does not say."),
            ),
        )

    def test_the_same_id_twice_is_one_zombie(self):
        questions = build_questions(self.manager, ["z12 lunges.", "You hit z12."])
        self.assertEqual(len(questions), 1)

    def test_no_zombie_id_means_no_question(self):
        self.assertEqual(build_questions(self.manager, ["You are winded."]), [])

    def test_two_zombies_mean_no_question_and_a_debug_log(self):
        with self.assertLogs("managers.story.check", logging.DEBUG):
            self.assertEqual(build_questions(self.manager, ["z12 lunges.", "z7 falls."]), [])

    def test_no_text_carries_a_digit(self):
        self.assertFalse(any(c.isdigit() for c in story_check_k.ZOMBIE_DEATH_QUESTION))
        self.assertFalse(
            any(
                c.isdigit()
                for c in story_check_k.ZOMBIE_DEAD_FACT + story_check_k.ZOMBIE_ALIVE_FACT
            )
        )

    def test_a_refused_action_asks_whether_the_story_did_it(self):
        (question,) = build_questions(
            self.manager,
            [],
            refused_actions=[("take the Kitchen Knife", "No 'Kitchen Knife' here to take.")],
        )
        self.assertEqual(
            question.text, "Does the story say that Orton managed to take the Kitchen Knife?"
        )
        self.assertEqual(
            question.options,
            (
                ("yes", "The story says or clearly shows that this happened."),
                (
                    "no",
                    "The story says it did not happen, or shows something else happening instead.",
                ),
                ("unclear", "The story does not say."),
            ),
        )
        self.assertEqual(question.allowed, frozenset({"no", "unclear"}))
        self.assertEqual(
            question.correction,
            "Orton does not take the Kitchen Knife: No 'Kitchen Knife' here to take.",
        )

    def test_a_refused_action_names_a_zombie_in_words(self):
        (question,) = build_questions(
            self.manager, [], refused_actions=[("shove z12", "z12 is out of reach.")]
        )
        self.assertEqual(
            question.text, "Does the story say that Orton managed to shove the zombie?"
        )

    def test_a_search_with_finds_asks_whether_the_story_denies_them(self):
        (question,) = build_questions(self.manager, [], found_items=True)
        self.assertEqual(
            question.text, "Does the story say that Orton's search found nothing at all?"
        )
        self.assertEqual(
            question.options,
            (
                (
                    "yes",
                    "The story says the search turned up nothing, or that the place was bare "
                    "or empty.",
                ),
                ("no", "The story names at least one thing that was found."),
                ("unclear", "The story does not say."),
            ),
        )
        self.assertEqual(question.allowed, frozenset({"no", "unclear"}))
        self.assertEqual(
            question.correction,
            "Orton's search turns things up; the story names what was found.",
        )

    def test_questions_come_zombie_first_then_refusals_then_finds(self):
        questions = build_questions(
            self.manager,
            ["z12 lunges."],
            refused_actions=[("take the Kitchen Knife", "Gone."), ("open the fridge", "Stuck.")],
            found_items=True,
        )
        self.assertEqual(
            [q.text for q in questions],
            [
                "By the end of the story, has the zombie been killed or put down for good?",
                "Does the story say that Orton managed to take the Kitchen Knife?",
                "Does the story say that Orton managed to open the fridge?",
                "Does the story say that Orton's search found nothing at all?",
            ],
        )

    def test_the_player_is_named_by_their_forename(self):
        self.manager.player.appearance = dataclasses.replace(
            self.manager.player.appearance, forename="Dana"
        )
        (question,) = build_questions(self.manager, [], found_items=True)
        self.assertEqual(
            question.text, "Does the story say that Dana's search found nothing at all?"
        )

    def test_a_question_is_frozen(self):
        (question,) = build_questions(self.manager, ["z12 lunges."])
        self.assertIsInstance(question, StateQuestion)
        with self.assertRaises(AttributeError):
            question.text = "x"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()


class PlanQuestionsTests(unittest.TestCase):
    """llm-contract: The plan check."""

    def setUp(self):
        self.manager = GameManager()

    def test_one_question_per_action_in_order(self):
        questions = plan_questions(
            self.manager,
            [UseItemAction(item_name="Frying Pan"), TalkAction(npc_name="Emma", approach="chat")],
        )
        self.assertEqual(
            [q.text for q in questions],
            [
                'Is "use the Frying Pan" something the player asked for, or a step needed '
                "to do what they asked?",
                'Is "chat with Emma" something the player asked for, or a step needed '
                "to do what they asked?",
            ],
        )

    def test_an_unsupported_action_is_asked_about_against_the_listed_verbs(self):
        verbs = "- TAKE <item> -- a thing\n- SHOUT -- call out"
        (question,) = plan_questions(
            self.manager, [UnsupportedAction(text="drink from the tap")], verbs
        )
        self.assertEqual(
            question.text,
            "Given these verbs:\n- TAKE <item> -- a thing\n- SHOUT -- call out\n"
            'does one of them do "drink from the tap"?',
        )
        self.assertEqual([key for key, _ in question.options], ["yes", "no", "unclear"])
        self.assertEqual(question.allowed, frozenset({"no", "unclear"}))
        self.assertEqual(
            question.correction, story_check_k.PLAN_NOT_UNDERSTOOD_FACT.format(name="Orton")
        )
        self.assertIn("rephrase", question.correction)
        self.assertFalse(any(c.isdigit() for c in question.correction))

    def test_the_options_and_what_is_allowed(self):
        (question,) = plan_questions(self.manager, [UseItemAction(item_name="Frying Pan")])
        self.assertEqual(
            question.options,
            (
                ("yes", "It is what the player asked for, part of it, or a step needed for it."),
                (
                    "no",
                    "It is something else: the player did not ask for it and it does not "
                    "lead there.",
                ),
                ("unclear", "Cannot tell."),
            ),
        )
        self.assertEqual(question.allowed, frozenset({"yes", "unclear"}))

    def test_the_correction_is_a_refusal_fact(self):
        (question,) = plan_questions(self.manager, [UseItemAction(item_name="Frying Pan")])
        self.assertEqual(
            question.correction,
            "Refused: Orton can't do that here, and does not use the Frying Pan.",
        )

    def test_a_zombie_is_named_in_words(self):
        (question,) = plan_questions(self.manager, [ShoveAction(target_name="z3")])
        self.assertIn('"shove the zombie"', question.text)
        self.assertNotIn("z3", question.correction)
