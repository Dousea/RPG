"""Spec 08, Skills and XP and levels: the skill list and its XP tables."""

import unittest

from data.character import exercises, skills
from data.character.creation import SKILLS as CREATION_SKILLS


class SkillListTests(unittest.TestCase):
    """Spec 08, Skills."""

    def test_there_are_35_skills_in_six_categories(self):
        self.assertEqual(len(skills.SKILLS), 35)
        counts: dict[str, int] = {}
        for skill in skills.SKILLS.values():
            counts[skill.category] = counts.get(skill.category, 0) + 1
        self.assertEqual(
            counts,
            {
                "combat": 7,
                "firearm": 2,
                "crafting": 12,
                "survivalist": 5,
                "physical": 6,
                "farming": 3,
            },
        )

    def test_display_names(self):
        self.assertEqual(skills.SKILLS["long_blunt"].name, "Long Blunt")
        self.assertEqual(skills.SKILLS["carpentry"].name, "Carpentry")
        self.assertEqual(skills.SKILLS["running"].name, "Running")
        self.assertEqual(skills.SKILLS["animal_care"].name, "Animal Care")

    def test_every_creation_skill_is_a_skill(self):
        for skill in CREATION_SKILLS:
            self.assertIn(skill, skills.SKILLS)

    def test_only_fitness_and_strength_are_passive(self):
        self.assertEqual(
            [s.id for s in skills.SKILLS.values() if s.passive], ["fitness", "strength"]
        )


class XpTableTests(unittest.TestCase):
    """Spec 08, XP and levels."""

    def test_normal_skill_table(self):
        self.assertEqual(
            skills.XP_PER_LEVEL, (75, 150, 300, 750, 1500, 3000, 4500, 6000, 7500, 9000)
        )

    def test_passive_table(self):
        self.assertEqual(
            skills.XP_PER_LEVEL_PASSIVE,
            (1500, 3000, 6000, 9000, 18000, 30000, 60000, 90000, 120000, 150000),
        )

    def test_level_three_of_a_normal_skill_needs_525(self):
        self.assertEqual(skills.total_xp_for_level("axe", 3), 525)

    def test_fitness_level_six_needs_67500(self):
        self.assertEqual(skills.total_xp_for_level("fitness", 6), 67500)

    def test_the_level_ten_totals(self):
        self.assertEqual(skills.total_xp_for_level("axe", 10), 32775)
        self.assertEqual(skills.total_xp_for_level("strength", 10), 487500)

    def test_level_zero_needs_nothing(self):
        self.assertEqual(skills.total_xp_for_level("axe", 0), 0)


class ExerciseTableTests(unittest.TestCase):
    """Spec 08, Exercise."""

    def test_seven_exercises_with_their_periods_and_mods(self):
        rows = {
            e.id: (e.regions, e.heavy, e.xp_mod, e.rep_period_s, e.item_id)
            for e in exercises.EXERCISES.values()
        }
        self.assertEqual(
            rows,
            {
                "squats": (("legs",), False, 1.0, 3.0, ""),
                "push_ups": (("arms", "chest"), False, 1.0, 1.3, ""),
                "sit_ups": (("abs",), False, 1.0, 1.3, ""),
                "burpees": (("legs", "arms", "chest"), True, 0.8, 2.4, ""),
                "barbell_curls": (("arms", "chest"), True, 1.2, 2.2, "item_barbell"),
                "dumbbell_press": (("arms",), True, 1.8, 1.5, "item_dumbbell"),
                "biceps_curls": (("arms",), True, 1.8, 1.9, "item_dumbbell"),
            },
        )
