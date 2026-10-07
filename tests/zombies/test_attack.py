"""zombies: Zombie attacks and Wounds."""

import dataclasses
import random
import unittest

from data.items import ITEMS
from managers.game import GameManager
from managers.zombies.attack import (
    WoundKind,
    WoundOdds,
    clothing_defence,
    defence_value,
    player_defence,
    resolve_attack,
    roll_body_part,
    roll_wound_damage,
    roll_wound_kind,
    roll_zombie_infection,
    weapon_level,
    wound_odds,
)
from modules.body.parts import BodyLocation, BodyPart
from modules.body.stats import CharacterStat
from modules.character.skills import SkillState
from modules.entity.item import ItemEntity
from modules.entity.zombie import AttackSide
from modules.item import ClothingItem


class ScriptedRng(random.Random):
    """Feeds `randrange` a fixed list of answers, in order."""

    def __init__(self, answers: list[int]):
        super().__init__(0)
        self.answers = list(answers)

    def randrange(self, start: int, stop: int | None = None, step: int = 1) -> int:
        return self.answers.pop(0)


def armour(scratch: int, bite: int, covers: set[BodyPart], neck: float = 1.0) -> ItemEntity:
    item = ClothingItem(
        id="item_test_armour",
        name="Test armour",
        description="",
        max_hit_points=100,
        tags=[],
        body_location=BodyLocation.JACKET,
        covers=frozenset(covers),
        insulation=0.5,
        wind_resistance=0.5,
        water_resistance=0.5,
        weight=1.0,
        scratch_defense=scratch,
        bite_defense=bite,
        neck_protection=neck,
    )
    return ItemEntity(item=item)


class DefenceTests(unittest.TestCase):
    """zombies: Zombie attacks: the defence formula."""

    def test_formula_with_skills_and_status_effects(self):
        # 3*4 + 2*6 + 2*7 - 5*2 - 2*1 - 2*0 - 3*2 - 2*1
        self.assertEqual(
            defence_value(
                weapon_level=4,
                fitness=6,
                strength=7,
                attackers=2,
                endurance=1,
                heavy_load=0,
                tired=2,
                drunk=1,
            ),
            18,
        )

    def test_a_default_character_with_bare_hands(self):
        self.assertEqual(defence_value(0, 5, 5, 1, endurance=0, heavy_load=0, tired=0, drunk=0), 15)

    def test_weapon_level_is_zero_bare_handed_and_the_category_skill_minus_one_armed(self):
        player = GameManager().player
        self.assertEqual(weapon_level(player), 0)

    def test_weapon_level_with_a_crowbar(self):
        gm = GameManager()
        crowbar = ItemEntity(item=ITEMS["item_crowbar"])
        gm.player.equipment[next(iter(gm.player.equipment))] = crowbar
        gm.player.skills["long_blunt"] = SkillState(level=4, xp=0)
        self.assertEqual(weapon_level(gm.player), 3)
        gm.player.skills["long_blunt"] = SkillState(level=0, xp=0)
        self.assertEqual(weapon_level(gm.player), 0)
        gm.player.skills["long_blunt"] = SkillState(level=10, xp=0)
        self.assertEqual(weapon_level(gm.player), 9)

    def test_an_axe_takes_its_level_whole(self):
        gm = GameManager()
        axe = dataclasses.replace(ITEMS["item_crowbar"], categories=("axe",))
        gm.player.equipment[next(iter(gm.player.equipment))] = ItemEntity(item=axe)
        gm.player.skills["axe"] = SkillState(level=5, xp=0)
        self.assertEqual(weapon_level(gm.player), 5)
        gm.player.skills["axe"] = SkillState(level=10, xp=0)
        self.assertEqual(weapon_level(gm.player), 10)


class WoundOddsTests(unittest.TestCase):
    """zombies: Zombie attacks: wound odds by attackers and side."""

    def test_front_with_one_two_and_three_attackers(self):
        self.assertEqual(wound_odds(0, 1, AttackSide.FRONT, []), WoundOdds(10, 65, 85))
        self.assertEqual(wound_odds(0, 2, AttackSide.FRONT, []), WoundOdds(0, 50, 55))
        self.assertEqual(wound_odds(0, 3, AttackSide.FRONT, []), WoundOdds(-10, 35, 25))

    def test_combat_mod_by_weapon_level(self):
        self.assertEqual(wound_odds(2, 1, AttackSide.FRONT, []).base, 15)
        self.assertEqual(wound_odds(10, 1, AttackSide.FRONT, []).base, 22)
        self.assertEqual(wound_odds(1, 1, AttackSide.FRONT, []).base, 13)

    def test_from_behind(self):
        self.assertEqual(wound_odds(0, 1, AttackSide.BEHIND, []), WoundOdds(-5, 30, 60))
        self.assertEqual(wound_odds(0, 3, AttackSide.BEHIND, []), WoundOdds(-25, -15, -15))

    def test_from_the_side(self):
        self.assertEqual(wound_odds(0, 1, AttackSide.LEFT, []), WoundOdds(-20, 38, 78))
        self.assertEqual(wound_odds(0, 2, AttackSide.RIGHT, []), WoundOdds(-30, 23, 48))

    def test_skin_traits(self):
        self.assertEqual(wound_odds(0, 1, AttackSide.FRONT, ["thickskinned"]).base, 13)
        self.assertEqual(wound_odds(0, 1, AttackSide.FRONT, ["thinskinned"]).base, 7)


class BodyPartTests(unittest.TestCase):
    """zombies: Zombie attacks: body part rolls."""

    def test_a_head_roll_that_fails_the_check_is_redrawn_without_head_neck_or_groin(self):
        # narrow range, index 8 (head), check 99 (> 70), redraw index 3.
        part = roll_body_part(ScriptedRng([5, 8, 99, 3]), AttackSide.FRONT, 1)
        self.assertEqual(part, BodyPart.FOREARM_R)

    def test_a_head_roll_that_passes_the_check_stands(self):
        self.assertEqual(
            roll_body_part(ScriptedRng([5, 8, 70]), AttackSide.FRONT, 1), BodyPart.HEAD
        )
        self.assertEqual(
            roll_body_part(ScriptedRng([5, 9, 10]), AttackSide.FRONT, 1), BodyPart.NECK
        )

    def test_one_in_ten_reaches_the_groin(self):
        self.assertEqual(roll_body_part(ScriptedRng([0, 10]), AttackSide.FRONT, 1), BodyPart.GROIN)

    def test_from_behind_the_neck_chance_is_ten_per_attacker_plus_five(self):
        # 1 attacker: 15%. Roll 14 -> neck; the head check then uses 90.
        self.assertEqual(
            roll_body_part(ScriptedRng([5, 0, 14, 90]), AttackSide.BEHIND, 1), BodyPart.NECK
        )
        part = roll_body_part(ScriptedRng([5, 0, 15]), AttackSide.BEHIND, 1)
        self.assertEqual(part, BodyPart.HAND_L)

    def test_a_behind_neck_is_redrawn_above_ninety(self):
        part = roll_body_part(ScriptedRng([5, 0, 0, 91, 2]), AttackSide.BEHIND, 1)
        self.assertEqual(part, BodyPart.FOREARM_L)

    def test_head_and_neck_stand_about_71_percent_of_the_time_from_the_front(self):
        rng = random.Random(2)
        rolls = 40000
        hits = sum(
            roll_body_part(rng, AttackSide.FRONT, 1) in (BodyPart.HEAD, BodyPart.NECK)
            for _ in range(rolls)
        )
        # 2 of 10 from the narrow range, kept 71% of the time (the groin branch adds none).
        self.assertAlmostEqual(hits / rolls, 0.2 * 0.71 * 0.9 + 0.1 * (2 / 11) * 0.71, delta=0.01)


class DamageAndKindTests(unittest.TestCase):
    """zombies: Zombie attacks: damage, kind and the infection roll."""

    def test_damage_is_a_thousandth_times_ten_to_nineteen(self):
        self.assertEqual(roll_wound_damage(ScriptedRng([500, 0])), 5.0)
        self.assertAlmostEqual(roll_wound_damage(ScriptedRng([999, 9])), 0.999 * 19)
        self.assertEqual(roll_wound_damage(ScriptedRng([0, 9])), 0.0)

    def test_a_roll_at_or_below_the_base_is_no_wound(self):
        odds = WoundOdds(base=10, laceration=65, bite=85)
        self.assertIsNone(roll_wound_kind(ScriptedRng([10]), odds))
        self.assertEqual(roll_wound_kind(ScriptedRng([11, 65, 85]), odds), WoundKind.SCRATCH)

    def test_kinds_step_up_on_high_rolls(self):
        odds = WoundOdds(base=10, laceration=65, bite=85)
        self.assertEqual(roll_wound_kind(ScriptedRng([50, 66, 85]), odds), WoundKind.LACERATION)
        self.assertEqual(roll_wound_kind(ScriptedRng([50, 66, 86]), odds), WoundKind.BITE)
        self.assertEqual(roll_wound_kind(ScriptedRng([50, 10, 86]), odds), WoundKind.BITE)

    def test_a_negative_base_always_wounds(self):
        odds = WoundOdds(base=-10, laceration=-15, bite=-15)
        self.assertEqual(roll_wound_kind(ScriptedRng([0, 0, 0]), odds), WoundKind.BITE)

    def test_bites_always_carry_zombie_infection(self):
        rng = random.Random(3)
        self.assertTrue(all(roll_zombie_infection(WoundKind.BITE, rng) for _ in range(500)))

    def test_scratches_carry_zombie_infection_about_seven_percent_of_the_time(self):
        rng = random.Random(4)
        share = sum(roll_zombie_infection(WoundKind.SCRATCH, rng) for _ in range(20000)) / 20000
        self.assertAlmostEqual(share, 0.07, delta=0.01)

    def test_lacerations_carry_zombie_infection_about_a_quarter_of_the_time(self):
        rng = random.Random(5)
        share = sum(roll_zombie_infection(WoundKind.LACERATION, rng) for _ in range(20000)) / 20000
        self.assertAlmostEqual(share, 0.25, delta=0.015)


class ClothingDefenceTests(unittest.TestCase):
    """zombies: Zombie attacks: clothing blocks hits and tears."""

    def setUp(self):
        self.player = GameManager().player
        self.player.worn.clear()

    def test_defence_sums_worn_items_covering_the_part(self):
        self.player.worn[BodyLocation.JACKET] = armour(20, 40, {BodyPart.TORSO_UPPER})
        self.assertEqual(clothing_defence(self.player, BodyPart.TORSO_UPPER, WoundKind.SCRATCH), 20)
        self.assertEqual(
            clothing_defence(self.player, BodyPart.TORSO_UPPER, WoundKind.LACERATION), 20
        )
        self.assertEqual(clothing_defence(self.player, BodyPart.TORSO_UPPER, WoundKind.BITE), 40)
        self.assertEqual(clothing_defence(self.player, BodyPart.HAND_L, WoundKind.BITE), 0)

    def test_it_is_capped_at_100(self):
        self.player.worn[BodyLocation.JACKET] = armour(80, 80, {BodyPart.TORSO_UPPER})
        self.player.worn[BodyLocation.SWEATER] = armour(80, 80, {BodyPart.TORSO_UPPER})
        self.assertEqual(clothing_defence(self.player, BodyPart.TORSO_UPPER, WoundKind.BITE), 100)

    def test_a_hole_removes_that_items_defence(self):
        jacket = armour(50, 50, {BodyPart.TORSO_UPPER})
        self.player.worn[BodyLocation.JACKET] = jacket
        jacket.holes.add(BodyPart.TORSO_UPPER)
        self.assertEqual(clothing_defence(self.player, BodyPart.TORSO_UPPER, WoundKind.BITE), 0)

    def test_neck_protection_scales_an_items_defence_on_the_neck(self):
        self.player.worn[BodyLocation.JACKET] = armour(40, 40, {BodyPart.NECK}, neck=2.0)
        self.assertEqual(clothing_defence(self.player, BodyPart.NECK, WoundKind.BITE), 80)


class ResolveAttackTests(unittest.TestCase):
    """zombies: Zombie attacks and Wounds: a whole attack, step by step."""

    def setUp(self):
        self.player = GameManager().player
        self.player.worn.clear()

    def test_a_defended_attack_ends_with_no_damage(self):
        outcome = resolve_attack(self.player, AttackSide.FRONT, 1, ScriptedRng([0]))
        self.assertTrue(outcome.defended)
        self.assertIsNone(outcome.wound)
        self.assertFalse(outcome.dragged_down)
        self.assertEqual(self.player.hit_points, 100)

    def test_no_defence_from_behind_or_the_side(self):
        for side in (AttackSide.BEHIND, AttackSide.LEFT, AttackSide.RIGHT):
            with self.subTest(side=side):
                outcome = resolve_attack(self.player, side, 1, random.Random(1))
                self.assertFalse(outcome.defended)

    def test_no_defence_with_four_attackers_and_the_first_connecting_attack_drags_down(self):
        outcome = resolve_attack(self.player, AttackSide.FRONT, 4, ScriptedRng([]))
        self.assertFalse(outcome.defended)
        self.assertTrue(outcome.dragged_down)

    def test_three_attackers_drag_the_player_down(self):
        outcome = resolve_attack(self.player, AttackSide.FRONT, 3, ScriptedRng([99]))
        self.assertTrue(outcome.dragged_down)
        self.assertIsNone(outcome.wound)

    def test_three_attackers_can_still_be_defended_and_then_do_not_drag_down(self):
        self.player.skills["fitness"] = SkillState(level=10, xp=0)
        self.player.skills["strength"] = SkillState(level=10, xp=0)
        # defence: 20 + 20 - 15 = 25
        outcome = resolve_attack(self.player, AttackSide.FRONT, 3, ScriptedRng([24]))
        self.assertTrue(outcome.defended)
        self.assertFalse(outcome.dragged_down)

    def test_two_attackers_do_not_drag_down(self):
        outcome = resolve_attack(self.player, AttackSide.FRONT, 2, random.Random(7))
        self.assertFalse(outcome.dragged_down)

    def test_a_bite_on_the_neck_lowers_overall_health_by_damage_times_weight(self):
        script = [50, 5, 9, 50, 500, 0, 70, 70, 90, 50]
        outcome = resolve_attack(self.player, AttackSide.FRONT, 1, ScriptedRng(script))
        wound = outcome.wound
        assert wound is not None
        self.assertEqual(wound.kind, WoundKind.BITE)
        self.assertEqual(wound.part, BodyPart.NECK)
        self.assertEqual(wound.damage, 5.0)
        self.assertTrue(wound.zombie_infected)
        self.assertAlmostEqual(self.player.health, 100 - 5 * 0.7)
        self.assertAlmostEqual(self.player.body[BodyPart.NECK].health, 95.0)
        self.assertGreater(self.player.body[BodyPart.NECK].bite_time, 0)
        self.assertTrue(self.player.body[BodyPart.NECK].zombie_infected)

    def test_clothing_defence_100_always_blocks(self):
        self.player.worn[BodyLocation.JACKET] = armour(100, 100, set(BodyPart))
        for seed in range(200):
            outcome = resolve_attack(self.player, AttackSide.BEHIND, 1, random.Random(seed))
            self.assertIsNone(outcome.wound)
        self.assertEqual(self.player.hit_points, 100)

    def test_an_unblocked_wound_tears_every_layer_over_the_part(self):
        inner = armour(0, 0, {BodyPart.NECK})
        outer = armour(0, 0, {BodyPart.NECK, BodyPart.HEAD})
        self.player.worn[BodyLocation.SWEATER] = inner
        self.player.worn[BodyLocation.JACKET] = outer
        script = [50, 5, 9, 50, 500, 0, 70, 70, 90, 50]
        resolve_attack(self.player, AttackSide.FRONT, 1, ScriptedRng(script))
        self.assertIn(BodyPart.NECK, inner.holes)
        self.assertIn(BodyPart.NECK, outer.holes)

    def test_a_blocked_hit_leaves_the_clothes_untorn(self):
        jacket = armour(100, 100, {BodyPart.NECK})
        self.player.worn[BodyLocation.JACKET] = jacket
        script = [50, 5, 9, 50, 500, 0, 70, 70, 90, 50]
        outcome = resolve_attack(self.player, AttackSide.FRONT, 1, ScriptedRng(script))
        self.assertTrue(outcome.blocked)
        self.assertEqual(jacket.holes, set())

    def test_a_low_kind_roll_is_a_harmless_thump(self):
        script = [50, 5, 3, 0, 500, 0, 5]
        outcome = resolve_attack(self.player, AttackSide.FRONT, 1, ScriptedRng(script))
        self.assertIsNone(outcome.wound)
        self.assertFalse(outcome.blocked)
        self.assertEqual(self.player.hit_points, 100)

    def test_status_effects_lower_the_defence(self):
        self.player.stats.set(CharacterStat.FATIGUE, 1.0)
        outcome = resolve_attack(
            self.player, AttackSide.FRONT, 1, ScriptedRng([14, 5, 3, 0, 500, 0, 5])
        )
        self.assertFalse(outcome.defended)


if __name__ == "__main__":
    unittest.main()


class HeavyLoadDefenceTests(unittest.TestCase):
    """carrying-and-loot: What Heavy Load does: defence drops 2 a level against a zombie attack."""

    def test_two_levels_cost_four_points(self):
        gm = GameManager()
        gm.player.worn.clear()
        gm.player.inventory.clear()
        gm.player.skills["strength"] = SkillState(level=0)
        base = player_defence(gm.player, 1)
        gm.player.inventory.extend(
            ItemEntity(item=ITEMS[item_id]) for item_id in ("item_barbell", "item_hammer")
        )
        self.assertEqual(player_defence(gm.player, 1), base - 4)
