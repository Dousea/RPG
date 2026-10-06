"""Spec 08: gaining XP, levels, loss timers, trait swaps and Fitness effects."""

import unittest

from data.presets import ORTON
from managers import creation
from managers.climate import FeltAir
from managers.skills import SkillEngine, level_word
from managers.stats.drivers import StatContext, default_drivers
from managers.stats.engine import StatsEngine
from managers.thermoregulator import thermal_inputs
from modules.character.appearance import Appearance
from modules.character.build import CharacterBuild
from modules.character.skills import SkillState
from modules.entity.player import PlayerEntity
from modules.item import MeleeWeaponItem
from modules.stats import CharacterStat


def make_player(**kwargs) -> PlayerEntity:
    return PlayerEntity(name="Orton", current_location_id="zone_home", **kwargs)


class GainingXpTests(unittest.TestCase):
    """Spec 08, Gaining XP."""

    def setUp(self):
        self.engine = SkillEngine()

    def gain(self, player, skill, amount):
        return self.engine.add_xp(player, skill, amount)

    def test_no_boost_or_boost_zero_gives_a_quarter(self):
        player = make_player()
        self.gain(player, "axe", 100)
        self.assertAlmostEqual(player.skills["axe"].xp, 25)

    def test_boost_one_is_unchanged(self):
        player = make_player(skill_boosts={"axe": 1})
        self.gain(player, "axe", 100)
        self.assertAlmostEqual(player.skills["axe"].xp, 100)

    def test_boost_two_is_one_point_three_three(self):
        player = make_player(skill_boosts={"axe": 2})
        self.gain(player, "axe", 100)
        self.assertAlmostEqual(player.skills["axe"].xp, 133)

    def test_boost_three_is_one_point_six_six(self):
        player = make_player(skill_boosts={"axe": 3})
        self.gain(player, "axe", 100)
        self.assertAlmostEqual(player.skills["axe"].xp, 166)

    def test_fitness_and_strength_skip_the_quarter_and_the_increases(self):
        for skill in ("fitness", "strength"):
            for boost in (0, 3):
                player = make_player(skill_boosts={skill: boost})
                self.gain(player, skill, 100)
                self.assertAlmostEqual(player.skills[skill].xp, 100)

    def test_running_skips_the_quarter_and_boost_one_is_one_and_a_quarter(self):
        player = make_player()
        self.gain(player, "running", 100)
        self.assertAlmostEqual(player.skills["running"].xp, 100)
        boosted = make_player(skill_boosts={"running": 1})
        self.gain(boosted, "running", 100)
        self.assertAlmostEqual(boosted.skills["running"].xp, 125)

    def test_fast_learner_is_one_point_three_but_not_for_fitness_or_strength(self):
        player = make_player(traits=["fastlearner"], skill_boosts={"axe": 1})
        self.gain(player, "axe", 100)
        self.assertAlmostEqual(player.skills["axe"].xp, 130)
        self.gain(player, "fitness", 100)
        self.assertAlmostEqual(player.skills["fitness"].xp, 100)

    def test_slow_learner_is_seven_tenths_but_not_for_fitness_strength_or_running(self):
        player = make_player(traits=["slowlearner"], skill_boosts={"axe": 1, "running": 1})
        self.gain(player, "axe", 100)
        self.assertAlmostEqual(player.skills["axe"].xp, 70)
        self.gain(player, "strength", 100)
        self.assertAlmostEqual(player.skills["strength"].xp, 100)
        self.gain(player, "running", 100)
        self.assertAlmostEqual(player.skills["running"].xp, 125)

    def test_reluctant_fighter_is_three_quarters_on_combat_skills_and_aiming(self):
        player = make_player(
            traits=["pacifist"], skill_boosts={"axe": 1, "aiming": 1, "cooking": 1}
        )
        self.gain(player, "axe", 100)
        self.gain(player, "aiming", 100)
        self.gain(player, "cooking", 100)
        self.assertAlmostEqual(player.skills["axe"].xp, 75)
        self.assertAlmostEqual(player.skills["aiming"].xp, 75)
        self.assertAlmostEqual(player.skills["cooking"].xp, 100)

    def test_reluctant_fighter_skips_maintenance(self):
        player = make_player(traits=["pacifist"], skill_boosts={"maintenance": 1})
        self.gain(player, "maintenance", 100)
        self.assertAlmostEqual(player.skills["maintenance"].xp, 100)

    def test_crafty_is_one_point_three_on_crafting_skills_only(self):
        player = make_player(traits=["crafty"], skill_boosts={"cooking": 1, "axe": 1})
        self.gain(player, "cooking", 100)
        self.gain(player, "axe", 100)
        self.assertAlmostEqual(player.skills["cooking"].xp, 130)
        self.assertAlmostEqual(player.skills["axe"].xp, 100)

    def test_no_xp_while_asleep(self):
        player = make_player(skill_boosts={"axe": 1})
        player.asleep = True
        self.assertEqual(self.gain(player, "axe", 100), [])
        self.assertEqual(player.skills.get("axe", SkillState()).xp, 0)

    def test_one_gain_across_two_levels_gives_two_facts(self):
        player = make_player(skill_boosts={"short_blade": 1})
        facts = self.gain(player, "short_blade", 225)
        self.assertEqual(player.skills["short_blade"].level, 2)
        self.assertEqual(
            facts,
            [
                "Your Short Blade skill is now level 1.",
                "Your Short Blade skill is now level 2.",
            ],
        )

    def test_xp_is_clamped_at_the_level_ten_total(self):
        player = make_player(skill_boosts={"axe": 1})
        self.gain(player, "axe", 100000)
        self.assertEqual(player.skills["axe"].xp, 32775)
        self.assertEqual(player.skills["axe"].level, 10)

    def test_a_loss_drops_a_level_with_its_own_fact(self):
        player = make_player(skills={"fitness": SkillState(6, 67500)})
        facts = self.gain(player, "fitness", -1)
        self.assertEqual(player.skills["fitness"].level, 5)
        self.assertEqual(player.skills["fitness"].xp, 67499)
        self.assertEqual(facts, ["Your Fitness has dropped to level 5."])

    def test_a_loss_never_goes_below_zero(self):
        player = make_player(skills={"fitness": SkillState(0, 0.5)})
        self.gain(player, "fitness", -1)
        self.assertEqual(player.skills["fitness"].xp, 0)

    def test_multipliers_apply_to_losses_too(self):
        player = make_player(skills={"axe": SkillState(1, 100)})
        self.gain(player, "axe", -40)
        self.assertAlmostEqual(player.skills["axe"].xp, 90)

    def test_a_gain_at_the_cap_is_skipped_entirely(self):
        player = make_player(
            skills={"fitness": SkillState(10, 487500)}, loss_timers={"fitness": 5000}
        )
        self.gain(player, "fitness", 100)
        self.assertEqual(player.skills["fitness"].xp, 487500)
        self.assertEqual(player.loss_timers["fitness"], 5000)


STRENGTH_TRAITS = {"weak", "feeble", "stout", "strong"}
FITNESS_TRAITS = {"unfit", "out_of_shape", "fit", "athletic"}


def build(occupation: str, traits: tuple[str, ...] = ()) -> CharacterBuild:
    return CharacterBuild(
        appearance=Appearance(forename="Sam"), occupation_id=occupation, traits=traits
    )


class TraitsFollowTheLevelTests(unittest.TestCase):
    """Spec 08, Traits that follow the level."""

    def trait_at(self, skill: str, level: int, family: set[str]) -> set[str]:
        player = make_player()
        SkillEngine().set_level(player, skill, level)
        return family & set(player.traits)

    def test_strength_levels_pick_the_strength_trait(self):
        expected = {
            0: "weak", 1: "weak",
            2: "feeble", 3: "feeble", 4: "feeble",
            5: None,
            6: "stout", 7: "stout", 8: "stout",
            9: "strong", 10: "strong",
        }  # fmt: skip
        for level, trait in expected.items():
            with self.subTest(level=level):
                self.assertEqual(
                    self.trait_at("strength", level, STRENGTH_TRAITS), {trait} if trait else set()
                )

    def test_fitness_levels_pick_the_fitness_trait(self):
        expected = {
            0: "unfit", 1: "unfit",
            2: "out_of_shape", 3: "out_of_shape", 4: "out_of_shape",
            5: None,
            6: "fit", 7: "fit", 8: "fit",
            9: "athletic", 10: "athletic",
        }  # fmt: skip
        for level, trait in expected.items():
            with self.subTest(level=level):
                self.assertEqual(
                    self.trait_at("fitness", level, FITNESS_TRAITS), {trait} if trait else set()
                )

    def test_a_level_change_from_xp_swaps_the_trait(self):
        player = make_player(skill_boosts={})
        engine = SkillEngine()
        engine.set_level(player, "strength", 5)
        engine.add_xp(player, "strength", 29999)
        self.assertEqual(player.skills["strength"].level, 5)
        engine.add_xp(player, "strength", 1)
        self.assertEqual(player.skills["strength"].level, 6)
        self.assertIn("stout", player.traits)

    def test_the_swap_leaves_other_traits_alone(self):
        player = make_player(traits=["brave", "weak"])
        SkillEngine().set_level(player, "strength", 6)
        self.assertEqual(player.traits, ["brave", "stout"])

    def test_an_unchanged_trait_keeps_its_place(self):
        player = make_player(traits=["strong", "brave"])
        SkillEngine().set_level(player, "strength", 10)
        self.assertEqual(player.traits, ["strong", "brave"])

    def test_a_firefighter_starts_stout_and_fit(self):
        player = creation.new_player(build("fireofficer"))
        self.assertEqual(player.skills["strength"].level, 6)
        self.assertIn("stout", player.traits)
        self.assertIn("fit", player.traits)

    def test_a_starting_skill_holds_exactly_its_levels_total_xp(self):
        player = creation.new_player(build("fireofficer"))
        self.assertEqual(player.skills["strength"].xp, 1500 + 3000 + 6000 + 9000 + 18000 + 30000)
        self.assertEqual(player.skills["axe"].level, 1)
        self.assertEqual(player.skills["axe"].xp, 75)
        self.assertEqual(player.skills["cooking"].xp, 0)

    def test_every_skill_is_present_at_the_start(self):
        player = creation.new_player(ORTON)
        self.assertEqual(len(player.skills), 35)
        self.assertEqual(player.skills["fitness"].level, 5)
        self.assertNotIn("fit", player.traits)


class LossTimerTests(unittest.TestCase):
    """Spec 08, Losing them when you stop training."""

    def trained(self, timer: float, step: int, level: int = 5) -> PlayerEntity:
        player = make_player()
        SkillEngine().set_level(player, "fitness", level)
        player.loss_timers = {"fitness": timer, "strength": -50000}
        player.loss_timer_steps = {"fitness": step, "strength": -42}
        return player

    def test_the_timer_rises_by_ten_each_tick(self):
        player = self.trained(-50000, -42)
        SkillEngine().tick(player, walking=False)
        self.assertEqual(player.loss_timers["fitness"], -49990)
        self.assertEqual(player.loss_timers["strength"], -49990)

    def test_a_character_with_no_timer_starts_at_minus_fifty_thousand(self):
        player = make_player()
        SkillEngine().tick(player, walking=False)
        self.assertEqual(player.loss_timers["fitness"], -49990)

    def test_no_loss_at_or_below_20000(self):
        player = self.trained(19990, 15)
        SkillEngine().tick(player, walking=False)
        self.assertEqual(player.loss_timers["fitness"], 20000)
        self.assertEqual(player.skills["fitness"].xp, 37500)

    def test_one_xp_is_lost_each_time_the_step_changes_above_20000(self):
        player = self.trained(20390, 16)
        SkillEngine().tick(player, walking=False)
        self.assertEqual(player.skills["fitness"].xp, 37499)
        self.assertEqual(player.loss_timer_steps["fitness"], 17)
        SkillEngine().tick(player, walking=False)
        self.assertEqual(player.skills["fitness"].xp, 37499)

    def test_the_timer_resets_above_31000(self):
        player = self.trained(30995, 25)
        SkillEngine().tick(player, walking=False)
        self.assertEqual(player.loss_timers["fitness"], 0)

    def test_a_gain_lowers_the_timer_by_3000_to_at_least_minus_50000(self):
        player = self.trained(5000, -42)
        SkillEngine().add_xp(player, "fitness", 10)
        self.assertEqual(player.loss_timers["fitness"], 2000)
        player.loss_timers["fitness"] = -49000
        SkillEngine().add_xp(player, "fitness", 10)
        self.assertEqual(player.loss_timers["fitness"], -50000)

    def test_a_loss_can_cost_a_level_and_says_so(self):
        player = self.trained(20390, 16, level=6)
        facts = SkillEngine().tick(player, walking=False)
        self.assertEqual(player.skills["fitness"].level, 5)
        self.assertEqual(facts, ["Your Fitness has dropped to level 5."])

    def test_timers_run_while_asleep_but_no_xp_is_lost(self):
        player = self.trained(20390, 16)
        player.asleep = True
        SkillEngine().tick(player, walking=False)
        self.assertEqual(player.loss_timers["fitness"], 20400)
        self.assertEqual(player.skills["fitness"].xp, 37500)


class ExhaustionXpTests(unittest.TestCase):
    """Spec 08, Where XP comes from: exhausted and not walking."""

    def tick_at(self, endurance: float, *, walking: bool = False) -> PlayerEntity:
        player = make_player()
        SkillEngine().set_level(player, "fitness", 5)
        player.stats.set(CharacterStat.ENDURANCE, endurance)
        SkillEngine().tick(player, walking=walking)
        return player

    def test_six_fitness_xp_per_boundary_below_a_quarter_endurance(self):
        self.assertEqual(self.tick_at(0.2).skills["fitness"].xp, 37506)

    def test_nothing_at_a_quarter_or_while_walking(self):
        self.assertEqual(self.tick_at(0.25).skills["fitness"].xp, 37500)
        self.assertEqual(self.tick_at(0.2, walking=True).skills["fitness"].xp, 37500)

    def test_the_gain_lowers_the_loss_timer(self):
        player = self.tick_at(0.2)
        self.assertEqual(player.loss_timers["fitness"], -50000)


class RecoveryByFitnessTests(unittest.TestCase):
    """Spec 08, Effects wired now."""

    def regen(self, fitness: int, **ctx) -> float:
        player = make_player()
        player.stats.set(CharacterStat.ENDURANCE, 0.0)
        levels = {"fitness": fitness}
        StatsEngine(default_drivers()).advance(
            player, 6, StatContext(skills=levels, resting=True, **ctx)
        )
        return player.stats.get(CharacterStat.ENDURANCE)

    def test_fitness_zero_recovers_at_seven_tenths_and_ten_at_one_point_six(self):
        base = self.regen(5) / 1.2
        self.assertAlmostEqual(self.regen(0) / base, 0.7, places=3)
        self.assertAlmostEqual(self.regen(10) / base, 1.6, places=3)

    def test_each_level_has_its_factor(self):
        base = self.regen(5) / 1.2
        expected = [0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.55, 1.6]
        for level, factor in enumerate(expected):
            with self.subTest(level=level):
                self.assertAlmostEqual(self.regen(level) / base, factor, places=3)

    def test_asleep_regeneration_uses_the_factor_too(self):
        low = self.regen(0, asleep=True)
        high = self.regen(10, asleep=True)
        self.assertAlmostEqual(high / low, 1.6 / 0.7, places=3)

    def test_standing_regeneration_uses_the_factor_too(self):
        player = make_player()
        player.stats.set(CharacterStat.ENDURANCE, 0.0)
        StatsEngine(default_drivers()).advance(player, 6, StatContext(skills={"fitness": 10}))
        low = make_player()
        low.stats.set(CharacterStat.ENDURANCE, 0.0)
        StatsEngine(default_drivers()).advance(low, 6, StatContext(skills={"fitness": 0}))
        ratio = player.stats.get(CharacterStat.ENDURANCE) / low.stats.get(CharacterStat.ENDURANCE)
        self.assertAlmostEqual(ratio, 1.6 / 0.7, places=3)


class FitnessStatTests(unittest.TestCase):
    """Spec 08, Effects wired now: the Fitness stat in the heat balance."""

    def stat(self, level: int) -> float:
        player = make_player()
        ctx = StatContext(skills={"fitness": level}, wearer=player)
        air = FeltAir(22.0, 22.0)
        return thermal_inputs(player.stats, ctx, air, 0.5).fitness

    def test_fitness_stat_runs_from_minus_one_to_one(self):
        self.assertEqual(self.stat(0), -1.0)
        self.assertEqual(self.stat(5), 0.0)
        self.assertEqual(self.stat(10), 1.0)


class LevelWordTests(unittest.TestCase):
    """Spec 08, What the narrator and the player see."""

    def test_words_by_level(self):
        expected = {
            0: "",
            1: "novice", 2: "novice",
            3: "capable", 4: "capable",
            5: "skilled", 6: "skilled",
            7: "expert", 8: "expert",
            9: "master", 10: "master",
        }  # fmt: skip
        for level, word in expected.items():
            self.assertEqual(level_word(level), word)


class HitXpCapTests(unittest.TestCase):
    """Spec 08, Where XP comes from: the hit XP cap."""

    def category_xp(self, split: float) -> float:
        from data.items import ITEMS

        crowbar = ITEMS["item_crowbar"]
        assert isinstance(crowbar, MeleeWeaponItem)
        player = make_player(skill_boosts={"long_blunt": 1})
        SkillEngine().hit_xp(player, crowbar, split, 1)
        return player.skills["long_blunt"].xp

    def test_the_category_xp_is_capped_at_three(self):
        self.assertAlmostEqual(self.category_xp(5.0), 3.0)
        self.assertAlmostEqual(self.category_xp(3.7), 3.0)

    def test_below_the_cap_it_is_point_nine_of_the_split(self):
        self.assertAlmostEqual(self.category_xp(2.0), 1.8)


class LossTimerOnlyGainsDropTests(unittest.TestCase):
    """Spec 08, Losing them when you stop training: only gains lower the timer."""

    def test_a_loss_leaves_the_timer_and_a_gain_drops_it_by_three_thousand(self):
        player = make_player()
        player.loss_timers = {"fitness": 25000}
        SkillEngine().add_xp(player, "fitness", -1)
        self.assertEqual(player.loss_timers["fitness"], 25000)
        SkillEngine().add_xp(player, "fitness", 1)
        self.assertEqual(player.loss_timers["fitness"], 22000)


if __name__ == "__main__":
    unittest.main()
