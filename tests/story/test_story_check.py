"""The state questions built from a turn's facts (Spec 10, The fact check)."""

import logging
import unittest

from data.story import check as words
from managers.game import GameManager
from managers.story.check import StateQuestion, build_questions
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
    """Spec 10, The fact check."""

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
        self.assertFalse(any(c.isdigit() for c in words.ZOMBIE_DEATH_QUESTION))
        self.assertFalse(any(c.isdigit() for c in words.ZOMBIE_DEAD_FACT + words.ZOMBIE_ALIVE_FACT))

    def test_a_question_is_frozen(self):
        (question,) = build_questions(self.manager, ["z12 lunges."])
        self.assertIsInstance(question, StateQuestion)
        with self.assertRaises(AttributeError):
            question.text = "x"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
