"""doors: Breaking through: a count of swings, or until it gives, on one ATTACK."""

import random
import re
import unittest

from data.items import ITEMS
from data.world.barriers import MAX_BARRIER_SWINGS
from managers.character.exercise import endurance_level
from managers.game import GameManager
from managers.simulation import SimulationCore
from managers.world.barriers import blocks
from modules.action.parser import parse_action_line
from modules.action.schema import parse_plan
from modules.action.types import UNTIL_IT_GIVES, AttackAction
from modules.body.stats import CharacterStat
from modules.character.equipment import CharacterHoldableSlot
from modules.entity.item import ItemEntity
from modules.entity.zombie import AttackSide, ZombieState
from tests.test_context import add_zombie
from tests.world.test_barricade import HOME, Spy, run, stocked_game, window

DOOR = "apartment door"


class BarrierSwingTests(unittest.TestCase):
    """doors: Breaking through."""

    def armed(self, item_id: str = "item_crowbar") -> GameManager:
        gm = stocked_game()
        entity = ItemEntity(item=ITEMS[item_id])
        gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND] = entity
        if ITEMS[item_id].is_two_handed:  # type: ignore[attr-defined]
            gm.player.equipment[CharacterHoldableSlot.LEFT_HAND] = entity
        return gm

    def swings(self, swings, *, name: str = DOOR):
        return AttackAction(target_name=name, swings=swings)

    def test_until_it_gives_breaks_a_door_at_a_minute_a_swing(self):
        gm = self.armed()
        facts, minutes = run(gm, self.swings(UNTIL_IT_GIVES))
        barrier = gm.world.barriers["door_apartment"]
        self.assertTrue(barrier.broken)
        self.assertTrue(8 <= minutes <= MAX_BARRIER_SWINGS, minutes)
        self.assertTrue(any("bursts from its hinges" in fact for fact in facts), facts)

    def test_a_count_of_5_stops_after_5_with_the_door_holding(self):
        gm = self.armed()
        facts, minutes = run(gm, self.swings(5))
        self.assertEqual(minutes, 5)
        barrier = gm.world.barriers["door_apartment"]
        self.assertFalse(barrier.broken)
        self.assertLess(barrier.health, 500)
        self.assertEqual(sum("keeps hitting" in fact for fact in facts), 1, facts)

    def test_a_count_of_50_is_clamped_to_30(self):
        gm = self.armed("item_baseball_bat")
        _, minutes = run(gm, self.swings(50))
        self.assertEqual(minutes, MAX_BARRIER_SWINGS)

    def test_until_it_gives_also_stops_at_the_cap_with_the_door_holding(self):
        gm = self.armed("item_baseball_bat")
        facts, minutes = run(gm, self.swings(UNTIL_IT_GIVES))
        self.assertEqual(minutes, MAX_BARRIER_SWINGS)
        self.assertTrue(blocks(gm.world.barriers["door_apartment"]))
        self.assertTrue(any("still holding" in fact for fact in facts), facts)

    def test_one_swing_keeps_the_single_hit_fact(self):
        gm = self.armed()
        facts, minutes = run(gm, self.swings(1))
        self.assertEqual(minutes, 1)
        self.assertIn("slams the crowbar into the apartment door", facts[0])

    def test_a_window_smashes_on_the_first_swing_whatever_the_count(self):
        gm = self.armed()
        gm.world.barriers["window_test"] = window()
        gm.player.at_barrier = "window_test"
        _, minutes = run(gm, self.swings(10, name="kitchen window"))
        self.assertTrue(gm.world.barriers["window_test"].broken)
        self.assertEqual(minutes, 1)

    def test_planks_are_hit_then_the_door_until_it_gives(self):
        gm = self.armed()
        gm.world.barriers["door_apartment"].barricades[HOME] = [100, 100]
        facts, minutes = run(gm, self.swings(UNTIL_IT_GIVES))
        self.assertTrue(gm.world.barriers["door_apartment"].broken)
        self.assertEqual(sum("splinters" in fact for fact in facts), 2, facts)
        self.assertGreater(minutes, 3)

    def test_an_open_door_with_its_last_plank_gone_ends_the_run(self):
        gm = self.armed()
        barrier = gm.world.barriers["door_apartment"]
        barrier.open = True
        barrier.barricades[HOME] = [100]
        _, minutes = run(gm, self.swings(UNTIL_IT_GIVES))
        self.assertEqual(minutes, 3)
        self.assertFalse(barrier.broken)

    def test_a_zombie_arriving_interrupts_the_run(self):
        gm = self.armed("item_baseball_bat")
        gm.world.outbreak_started_at = 0
        add_zombie(gm, 6.0, ZombieState.CHASING)
        facts, minutes = run(gm, self.swings(UNTIL_IT_GIVES))
        self.assertLess(minutes, MAX_BARRIER_SWINGS)
        self.assertTrue(blocks(gm.world.barriers["door_apartment"]))
        self.assertTrue(any("breaks off" in fact for fact in facts), facts)

    def test_a_zombie_attack_with_a_count_is_one_swing(self):
        for swings in (5, UNTIL_IT_GIVES):
            with self.subTest(swings=swings):
                gm = self.armed()
                gm.world.outbreak_started_at = 0
                zombie = add_zombie(gm, 1, ZombieState.ATTACKING, health=100.0)
                zombie.time_since_seen = 0
                zombie.side = AttackSide.FRONT
                facts, minutes = run(gm, self.swings(swings, name=zombie.zombie_id))
                self.assertEqual(minutes, 1, facts)
                self.assertFalse(any("keeps hitting" in fact for fact in facts), facts)

    def test_a_run_that_ends_on_its_first_swing_reads_as_one_hit(self):
        gm = self.armed()
        gm.world.barriers["window_test"] = window()
        gm.player.at_barrier = "window_test"
        facts, _ = run(gm, self.swings(10, name="kitchen window"))
        self.assertFalse(any("keeps hitting" in fact for fact in facts), facts)
        self.assertIn("slams the crowbar into the kitchen window", facts[0])

    def test_the_endurance_stop_level_ends_the_run(self):
        gm = self.armed("item_baseball_bat")
        gm.player.stats.set(CharacterStat.ENDURANCE, 0.55)
        facts, minutes = run(gm, self.swings(UNTIL_IT_GIVES))
        self.assertLess(minutes, MAX_BARRIER_SWINGS)
        self.assertGreaterEqual(endurance_level(gm.player), 2)
        self.assertTrue(any("winded" in fact for fact in facts), facts)

    def test_one_swing_still_happens_when_already_past_the_stop_level(self):
        gm = self.armed()
        gm.player.stats.set(CharacterStat.ENDURANCE, 0.05)
        facts, minutes = run(gm, self.swings(UNTIL_IT_GIVES))
        self.assertEqual(minutes, 1)
        self.assertLess(gm.world.barriers["door_apartment"].health, 500)
        self.assertTrue(any("winded" in fact for fact in facts), facts)

    def test_a_weapon_that_breaks_ends_the_run(self):
        gm = self.armed()
        crowbar = gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND]
        assert crowbar is not None
        crowbar.condition = 1

        class Always(random.Random):
            def randrange(self, *args, **kwargs):
                return 0

        facts, minutes = run(gm, self.swings(UNTIL_IT_GIVES), rng=Always())
        self.assertEqual(minutes, 1)
        self.assertTrue(any("snaps" in fact for fact in facts), facts)

    def test_the_facts_hold_no_digits_and_no_repeats(self):
        gm = self.armed()
        facts, _ = run(gm, self.swings(UNTIL_IT_GIVES))
        told = [fact for fact in facts if not fact.startswith("About")]
        self.assertFalse(any(re.search(r"\d", fact) for fact in told), facts)
        self.assertEqual(len(facts), len(set(facts)), facts)
        self.assertTrue(any("until it gives way" in fact for fact in facts), facts)

    def test_every_swing_makes_its_sound(self):
        gm = self.armed()
        core = SimulationCore(gm, rng=random.Random(1))
        spy = Spy(core)
        core.resolve([self.swings(4)])
        self.assertEqual([len(sounds) for sounds in spy.sounds], [1, 1, 1, 1])


class SwingFormTests(unittest.TestCase):
    """doors: Breaking through (the forms the parser reads)."""

    def test_a_bare_attack_is_one_swing(self):
        self.assertEqual(parse_action_line("ATTACK lobby door"), AttackAction("lobby door", 1))

    def test_a_count_in_text(self):
        self.assertEqual(parse_action_line("ATTACK lobby door 5"), AttackAction("lobby door", 5))

    def test_until_it_gives_in_text(self):
        self.assertEqual(
            parse_action_line("ATTACK lobby door until it gives"),
            AttackAction("lobby door", UNTIL_IT_GIVES),
        )

    def test_json_forms(self):
        actions, failures = parse_plan(
            {
                "actions": [
                    {"verb": "ATTACK", "target": "lobby door", "swings": 5},
                    {"verb": "ATTACK", "target": "lobby door", "swings": "until it gives"},
                    {"verb": "ATTACK", "target": "z3"},
                ]
            }
        )
        self.assertEqual(failures, [])
        self.assertEqual(
            actions,
            [
                AttackAction("lobby door", 5),
                AttackAction("lobby door", UNTIL_IT_GIVES),
                AttackAction("z3", 1),
            ],
        )


if __name__ == "__main__":
    unittest.main()
