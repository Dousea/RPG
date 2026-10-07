"""Spec 11 through the simulation: holding a weapon and fighting zombies and NPCs."""

import random
import re
import unittest
from unittest import mock

from data.items import ITEMS
from managers.game import GameManager
from managers.melee import MeleeEngine
from managers.simulation import SimulationCore
from managers.skills import SkillEngine
from managers.zombie_attack import AttackOutcome, Wound, WoundKind
from managers.zombies import PlayerMinute, ZombieLoop
from modules.action.parser import parse_action_line
from modules.action.types import AttackAction, EquipAction, ShoveAction, UnequipAction
from modules.body import BodyPart
from modules.character.equipment import CharacterHoldableSlot
from modules.entity.item import ItemEntity
from modules.entity.zombie import AttackSide, ZombieEntity, ZombieState
from modules.stats import CharacterStat
from tests.support import simulate
from tests.test_melee import FixedRng
from tests.test_simulation import add_zombie, put_on_armour, zombie_game

RIGHT = CharacterHoldableSlot.RIGHT_HAND
LEFT = CharacterHoldableSlot.LEFT_HAND


def game_with(*item_ids: str) -> GameManager:
    gm = GameManager()
    gm.player.inventory.extend(ItemEntity(item=ITEMS[i]) for i in item_ids)
    return gm


class EquipTests(unittest.TestCase):
    """Spec 11, Holding a weapon: EQUIP and UNEQUIP."""

    def minutes(self, gm: GameManager, *actions) -> tuple[int, list[str]]:
        before = gm.narrative.minutes
        facts = simulate(gm, *actions, rng=random.Random(1))
        return gm.narrative.minutes - before, facts

    def test_the_verbs_parse(self):
        self.assertEqual(parse_action_line("EQUIP crowbar"), EquipAction(item_name="crowbar"))
        self.assertEqual(parse_action_line("UNEQUIP crowbar"), UnequipAction(item_name="crowbar"))

    def test_a_one_handed_weapon_goes_in_the_right_hand_and_costs_a_minute(self):
        gm = game_with("item_kitchen_knife")
        minutes, facts = self.minutes(gm, EquipAction(item_name="kitchen knife"))
        self.assertEqual(minutes, 1)
        held = gm.player.equipment[RIGHT]
        assert held is not None
        self.assertEqual(held.item.id, "item_kitchen_knife")
        self.assertIsNone(gm.player.equipment[LEFT])
        self.assertNotIn("item_kitchen_knife", [e.item.id for e in gm.player.inventory])
        self.assertFalse(facts[0].startswith("Refused"))

    def test_a_two_handed_weapon_fills_both_hands(self):
        gm = game_with("item_crowbar")
        self.minutes(gm, EquipAction(item_name="crowbar"))
        self.assertIs(gm.player.equipment[RIGHT], gm.player.equipment[LEFT])
        self.assertIsNotNone(gm.player.equipment[LEFT])

    def test_a_one_handed_holdable_listing_both_hands_takes_only_the_right(self):
        gm = game_with("item_pistol", "item_apartment_key")
        self.minutes(gm, EquipAction(item_name="9mm pistol"))
        self.assertIsNotNone(gm.player.equipment[RIGHT])
        self.assertIsNone(gm.player.equipment[LEFT])
        minutes, facts = self.minutes(gm, EquipAction(item_name="apartment key"))
        self.assertEqual(minutes, 0)
        self.assertIn("already holding the", facts[0])

    def test_a_key_is_held_in_the_right_hand_while_the_left_is_taken(self):
        gm = game_with("item_apartment_key")
        gm.player.equipment[LEFT] = ItemEntity(item=ITEMS["item_kitchen_knife"])
        minutes, facts = self.minutes(gm, EquipAction(item_name="apartment key"))
        self.assertEqual(minutes, 1)
        self.assertFalse(facts[0].startswith("Refused"))
        held = gm.player.equipment[RIGHT]
        assert held is not None
        self.assertEqual(held.item.id, "item_apartment_key")

    def test_full_hands_refuse_and_cost_nothing(self):
        gm = game_with("item_kitchen_knife", "item_crowbar")
        self.minutes(gm, EquipAction(item_name="kitchen knife"))
        minutes, facts = self.minutes(gm, EquipAction(item_name="crowbar"))
        self.assertEqual(minutes, 0)
        self.assertTrue(facts[0].startswith("Refused"))
        self.assertIn("already holding the Kitchen Knife", facts[0])

    def test_a_broken_weapon_is_refused(self):
        gm = game_with("item_kitchen_knife")
        gm.player.inventory[-1].condition = 0
        minutes, facts = self.minutes(gm, EquipAction(item_name="kitchen knife"))
        self.assertEqual(minutes, 0)
        self.assertIn("broken", facts[0])
        self.assertIsNone(gm.player.equipment[RIGHT])

    def test_unequip_returns_the_item_to_the_inventory(self):
        gm = game_with("item_crowbar")
        self.minutes(gm, EquipAction(item_name="crowbar"))
        minutes, _ = self.minutes(gm, UnequipAction(item_name="crowbar"))
        self.assertEqual(minutes, 1)
        self.assertIsNone(gm.player.equipment[RIGHT])
        self.assertIsNone(gm.player.equipment[LEFT])
        self.assertIn("item_crowbar", [e.item.id for e in gm.player.inventory])

    def test_unequip_refuses_a_full_inventory_and_an_item_not_held(self):
        gm = game_with("item_crowbar")
        self.minutes(gm, EquipAction(item_name="crowbar"))
        gm.player.max_inventory_size = 0
        minutes, facts = self.minutes(gm, UnequipAction(item_name="crowbar"))
        self.assertEqual(minutes, 0)
        self.assertIn("full", facts[0])
        gm.player.max_inventory_size = 20
        _, facts = self.minutes(gm, UnequipAction(item_name="kitchen knife"))
        self.assertTrue(facts[0].startswith("Refused"))

    def test_equip_refuses_clothing(self):
        gm = game_with("item_black_jacket")
        _, facts = self.minutes(gm, EquipAction(item_name="black jacket"))
        self.assertTrue(facts[0].startswith("Refused"))


def attacking_zombie(gm: GameManager, health: float = 100.0) -> ZombieEntity:
    zombie = add_zombie(gm, gap=1, health=health, state=ZombieState.ATTACKING)
    zombie.time_since_seen = 0
    zombie.side = AttackSide.FRONT
    return zombie


class DownAndStaggeredLoopTests(unittest.TestCase):
    """Spec 11, Knockdowns and staggers: step 6 of the minute loop."""

    def loop(self, gm: GameManager) -> ZombieLoop:
        return ZombieLoop(gm, FixedRng(), SkillEngine())

    def test_a_down_zombie_skips_its_attack_this_minute_and_the_next(self):
        gm = zombie_game()
        zombie = attacking_zombie(gm)
        zombie.down_until = 2
        loop = self.loop(gm)
        attacked = [loop.run_minute(now, PlayerMinute()).attacked for now in (0, 1, 2)]
        self.assertEqual(attacked, [False, False, True])

    def test_a_staggered_zombie_skips_this_minute_only(self):
        gm = zombie_game()
        zombie = attacking_zombie(gm)
        zombie.staggered = True
        loop = self.loop(gm)
        first = loop.run_minute(0, PlayerMinute())
        self.assertFalse(first.attacked)
        self.assertFalse(zombie.staggered)
        self.assertTrue(loop.run_minute(1, PlayerMinute()).attacked)

    def test_the_approach_step_closes_the_gap_at_the_limp_scaled_walking_pace(self):
        for limp, closed in ((1.0, 4.0), (0.75, 3.0)):
            gm = zombie_game()
            zombie = add_zombie(gm, gap=10, state=ZombieState.IDLE)
            with mock.patch("managers.zombies.limp_factor", return_value=limp):
                self.loop(gm).run_minute(0, PlayerMinute(approach_target=zombie.zombie_id))
            self.assertAlmostEqual(zombie.gap, 10 - closed)

    def test_a_down_zombie_does_not_move(self):
        gm = zombie_game()
        zombie = add_zombie(gm, gap=6, state=ZombieState.CHASING)
        zombie.time_since_seen = 0
        zombie.down_until = 2
        self.loop(gm).run_minute(0, PlayerMinute())
        self.assertEqual(zombie.gap, 6)

    def test_the_swing_is_step_zero_so_the_hit_zombie_does_not_attack_that_minute(self):
        gm = zombie_game()
        hold_crowbar(gm)
        zombie = attacking_zombie(gm)
        loop = self.loop(gm)
        report = loop.run_minute(0, PlayerMinute(swing_target=zombie.zombie_id))
        self.assertFalse(report.attacked)
        self.assertLess(zombie.health, 100.0)
        self.assertTrue(loop.run_minute(1, PlayerMinute()).attacked)

    def test_a_crit_swing_keeps_the_zombie_from_attacking_for_two_minutes(self):
        gm = zombie_game()
        hold_crowbar(gm)
        zombie = attacking_zombie(gm)
        engine = MeleeEngine(CritRng(), SkillEngine())
        engine.swing(gm.player, gm.world, 0, zombie.zombie_id)
        loop = self.loop(gm)
        attacked = [loop.run_minute(now, PlayerMinute()).attacked for now in (0, 1, 2)]
        self.assertEqual(attacked, [False, False, True])


class CritRng(random.Random):
    """Every chance roll succeeds."""

    def randrange(self, start: int, stop: int | None = None, step: int = 1) -> int:
        return 0


def hold_crowbar(gm: GameManager) -> ItemEntity:
    entity = ItemEntity(item=ITEMS["item_crowbar"])
    gm.player.equipment[RIGHT] = entity
    gm.player.equipment[LEFT] = entity
    return entity


class FightingNpcTests(unittest.TestCase):
    """Spec 11, Fighting NPCs: today's resolution, with the weapon's NPC damage."""

    def damage(self, item_id: str | None, seed: int) -> int:
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        if item_id is not None:
            entity = ItemEntity(item=ITEMS[item_id])
            for slot in entity.item.slots:  # type: ignore[attr-defined]
                gm.player.equipment[slot] = entity  # type: ignore[index]
        emma = gm.resolve_npc("Emma")
        assert emma is not None
        before = emma.hit_points
        simulate(gm, AttackAction(target_name="Emma"), rng=random.Random(seed))
        return before - emma.hit_points

    def test_a_crowbar_hit_takes_four_or_five(self):
        self.assertEqual({self.damage("item_crowbar", s) for s in range(60)}, {4, 5})

    def test_a_knife_takes_two_or_three(self):
        self.assertEqual({self.damage("item_kitchen_knife", s) for s in range(60)}, {2, 3})

    def test_a_bat_takes_four_or_five(self):
        self.assertEqual({self.damage("item_baseball_bat", s) for s in range(60)}, {4, 5})

    def test_a_pan_takes_one_or_two(self):
        self.assertEqual({self.damage("item_frying_pan", s) for s in range(60)}, {1, 2})

    def test_an_axe_takes_five_or_six(self):
        self.assertEqual({self.damage("item_hand_axe", s) for s in range(60)}, {5, 6})

    def test_bare_hands_take_one_or_two(self):
        self.assertEqual({self.damage(None, s) for s in range(60)}, {1, 2})

    def test_shoving_an_npc_is_refused(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        facts = simulate(gm, ShoveAction(target_name="Emma"))
        self.assertTrue(facts[0].startswith("Refused"))


def fight_game() -> GameManager:
    gm = zombie_game()
    hold_crowbar(gm)
    return gm


class ZombieFightTests(unittest.TestCase):
    """Spec 11, Kills and XP: a fight through ATTACK."""

    def run_plan(self, gm: GameManager, *actions, seed: int = 1) -> tuple[int, list[str]]:
        before = gm.narrative.minutes
        facts = simulate(gm, *actions, rng=random.Random(seed))
        return gm.narrative.minutes - before, facts

    def test_a_kill_removes_the_zombie_lowers_stress_and_counts(self):
        gm = fight_game()
        zombie = add_zombie(gm, gap=1, health=0.05)
        gm.player.stats.set(CharacterStat.STRESS, 0.5)
        _, facts = self.run_plan(gm, AttackAction(target_name=zombie.zombie_id))
        self.assertNotIn(zombie.zombie_id, gm.world.zombies)
        self.assertEqual(gm.player.zombie_kills, 1)
        self.assertLess(gm.player.stats.get(CharacterStat.STRESS), 0.5)
        self.assertTrue(any("goes still" in fact for fact in facts))

    def test_a_crowbar_hit_gives_blunt_strength_and_fitness_xp(self):
        gm = fight_game()
        zombie = add_zombie(gm, gap=1, health=100)
        self.run_plan(gm, AttackAction(target_name=zombie.zombie_id))
        skills = gm.player.skills
        self.assertGreater(skills["long_blunt"].xp, 0)
        self.assertGreater(skills["fitness"].xp, 37500)
        # +1 for the hit, +2 for a hit that does not kill
        self.assertAlmostEqual(skills["strength"].xp, 37503)

    def test_no_fact_carries_a_number(self):
        gm = fight_game()
        zombie = add_zombie(gm, gap=1, health=100)
        _, facts = self.run_plan(gm, AttackAction(target_name=zombie.zombie_id))
        fight_facts = [f for f in facts if "minute" not in f]
        self.assertTrue(fight_facts)
        for fact in fight_facts:
            self.assertNotRegex(re.sub(r"z\d+", "zombie", fact), r"\d")

    def test_a_planned_attack_on_a_dead_zombie_is_refused_and_costs_nothing(self):
        gm = fight_game()
        zombie = add_zombie(gm, gap=1, health=0.05)
        minutes, facts = self.run_plan(
            gm,
            AttackAction(target_name=zombie.zombie_id),
            AttackAction(target_name=zombie.zombie_id),
        )
        self.assertEqual(minutes, 1)
        self.assertTrue(any(f.startswith("Refused") for f in facts))

    def test_the_word_zombie_picks_the_nearest_remaining_one(self):
        gm = fight_game()
        near = add_zombie(gm, gap=1, health=0.05)
        far = add_zombie(gm, gap=1, health=100)
        far.gap = 1
        self.run_plan(gm, AttackAction(target_name="zombie"), AttackAction(target_name="zombie"))
        self.assertNotIn(near.zombie_id, gm.world.zombies)
        self.assertGreater(far.hits_taken, 0)

    def test_a_weapon_that_breaks_mid_plan_leaves_a_bare_handed_shove(self):
        gm = fight_game()
        crowbar = gm.player.equipment[RIGHT]
        assert crowbar is not None
        crowbar.condition = 1
        zombie = add_zombie(gm, gap=1, health=100)
        rng = FixedRng(by_size={70: 0})
        core_facts = SimulationCore(gm, rng=rng).resolve(
            [AttackAction(target_name=zombie.zombie_id)] * 2
        )
        self.assertTrue(crowbar.broken)
        self.assertIsNone(gm.player.equipment[RIGHT])
        self.assertTrue(any("snaps" in fact for fact in core_facts))
        self.assertEqual(zombie.hits_taken, 1)


class ShoveActionTests(unittest.TestCase):
    """Spec 11, Shoves: SHOVE through the simulation."""

    def test_a_shove_costs_one_minute_and_staggers_a_standing_zombie(self):
        gm = fight_game()
        zombie = add_zombie(gm, gap=1, health=100, state=ZombieState.IDLE)
        before = gm.narrative.minutes
        facts = simulate(gm, ShoveAction(target_name=zombie.zombie_id), rng=random.Random(1))
        self.assertEqual(gm.narrative.minutes - before, 1)
        self.assertEqual(zombie.health, 100)
        self.assertEqual(zombie.hits_taken, 0)
        self.assertEqual(zombie.state, ZombieState.ATTACKING)
        self.assertFalse(any(f.startswith("Refused") for f in facts))

    def test_a_shove_closes_the_gap_first(self):
        gm = fight_game()
        put_on_armour(gm)
        zombie = add_zombie(gm, gap=6, health=100, state=ZombieState.IDLE)
        before = gm.narrative.minutes
        simulate(gm, ShoveAction(target_name=zombie.zombie_id), rng=random.Random(1))
        self.assertEqual(gm.narrative.minutes - before, 3)

    def test_a_shove_on_a_down_zombie_is_refused(self):
        gm = fight_game()
        zombie = add_zombie(gm, gap=1, health=100)
        zombie.down_until = gm.narrative.minutes + 2
        facts = simulate(gm, ShoveAction(target_name=zombie.zombie_id))
        self.assertEqual(facts[0], "Refused: Orton can't shove z1: It's already down.")

    def test_attack_on_a_down_zombie_stomps_or_floor_attacks(self):
        gm = fight_game()
        zombie = add_zombie(gm, gap=1, health=100)
        zombie.down_until = gm.narrative.minutes + 2
        facts = simulate(gm, AttackAction(target_name=zombie.zombie_id), rng=random.Random(1))
        self.assertTrue(any("head" in fact for fact in facts))
        self.assertGreater(zombie.hits_taken, 0)


class FightInterruptionTests(unittest.TestCase):
    """Spec 11, Interruptions during a fight."""

    def setup_fight(self) -> tuple[GameManager, ZombieEntity]:
        gm = zombie_game()
        entity = ItemEntity(item=ITEMS["item_kitchen_knife"])
        gm.player.equipment[RIGHT] = entity
        target = attacking_zombie(gm, health=1000)
        other = attacking_zombie(gm, health=1000)
        other.side = AttackSide.LEFT
        return gm, target

    def five_attacks(self, gm: GameManager, target: ZombieEntity):
        return SimulationCore(gm, rng=random.Random(1)).resolve(
            [AttackAction(target_name=target.zombie_id)] * 5
        )

    def test_defended_attacks_do_not_stop_five_planned_attacks(self):
        gm, target = self.setup_fight()
        before = gm.narrative.minutes
        defended = AttackOutcome(defended=True)
        with mock.patch("managers.zombies.resolve_attack", return_value=defended):
            facts = self.five_attacks(gm, target)
        self.assertEqual(gm.narrative.minutes - before, 5)
        self.assertFalse(any("never gets to" in fact for fact in facts))
        self.assertEqual(target.hits_taken, 5)

    def test_a_defended_attack_during_the_approach_minutes_stops_the_plan(self):
        gm, target = self.setup_fight()
        target.gap = 4
        target.state = ZombieState.CHASING
        before = gm.narrative.minutes
        defended = AttackOutcome(defended=True)
        with mock.patch("managers.zombies.resolve_attack", return_value=defended):
            facts = self.five_attacks(gm, target)
        self.assertEqual(gm.narrative.minutes - before, 1)
        self.assertTrue(any("never gets to" in fact for fact in facts))

    def test_an_attack_stopped_during_the_approach_says_the_swing_never_happens(self):
        gm, target = self.setup_fight()
        target.gap = 4
        target.state = ZombieState.CHASING
        defended = AttackOutcome(defended=True)
        with mock.patch("managers.zombies.resolve_attack", return_value=defended):
            facts = SimulationCore(gm, rng=random.Random(1)).resolve(
                [AttackAction(target_name=target.zombie_id)]
            )
        self.assertIn("Orton never gets to swing.", facts)
        self.assertEqual(target.hits_taken, 0)

    def test_a_wounding_attack_stops_the_plan(self):
        gm, target = self.setup_fight()
        before = gm.narrative.minutes
        wounded = AttackOutcome(wound=Wound(WoundKind.SCRATCH, BodyPart.HAND_L, 1.0, False))
        with mock.patch("managers.zombies.resolve_attack", return_value=wounded):
            facts = self.five_attacks(gm, target)
        self.assertEqual(gm.narrative.minutes - before, 1)
        self.assertTrue(any("never gets to" in fact for fact in facts))

    def test_a_new_zombie_spotting_the_player_stops_the_plan(self):
        gm, target = self.setup_fight()
        newcomer = add_zombie(gm, gap=8, state=ZombieState.IDLE, facing_cos=1.0)
        before = gm.narrative.minutes
        defended = AttackOutcome(defended=True)
        with mock.patch("managers.zombies.resolve_attack", return_value=defended):
            facts = self.five_attacks(gm, target)
        self.assertEqual(gm.narrative.minutes - before, 1)
        self.assertTrue(any("never gets to" in fact for fact in facts))
        self.assertIn(newcomer.state, (ZombieState.CHASING, ZombieState.ATTACKING))


if __name__ == "__main__":
    unittest.main()
