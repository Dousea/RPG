"""Spec 14, Crawlers: becoming one, what changes and what a crawler does."""

import random
import unittest

from managers.character.skills import SkillEngine
from managers.combat.melee import MeleeEngine
from managers.game import GameManager
from managers.zombies.attack import resolve_attack, roll_crawler_body_part
from managers.zombies.population import PlayerMinute
from modules.action.types import ShoveAction
from modules.body.parts import BodyPart
from modules.body.stats import CharacterStat
from modules.entity.zombie import AttackSide, ZombieEntity, ZombieState
from tests.combat.test_melee import FixedRng, add, hold, make_zombie, street_game, swing
from tests.support import ScriptedRandom, simulate
from tests.test_simulation import add_zombie, zombie_game
from tests.zombies.test_thumping import BUILDING, game, loop_for, minute
from tests.zombies.test_thumping import zombie as thump_zombie


def flagged(zombie: ZombieEntity) -> bool:
    """A hit flagged it: still waiting to go down, or already crawling because it went down."""
    return zombie.become_crawler or zombie.crawling


class BecomingACrawlerTests(unittest.TestCase):
    """Spec 14, Becoming a crawler: the roll after a hit that does not kill."""

    def test_a_weapon_hit_flags_one_in_thirty(self):
        gm = street_game(weapon="item_crowbar")
        hit = add(gm, make_zombie(1, health=1000))
        swing(gm, "z1", rng=FixedRng(by_size={30: 0}))
        self.assertTrue(hit.become_crawler)
        gm = street_game(weapon="item_crowbar")
        spared = add(gm, make_zombie(1, health=1000))
        swing(gm, "z1", rng=FixedRng(by_size={30: 1}))
        self.assertFalse(spared.become_crawler)

    def test_a_bare_handed_stomp_flags_one_in_fifteen(self):
        gm = street_game()
        zombie = add(gm, make_zombie(1, health=1000))
        zombie.down_until = 5
        swing(gm, "z1", rng=FixedRng(by_size={15: 0}))
        self.assertTrue(flagged(zombie))
        gm = street_game()
        zombie = add(gm, make_zombie(1, health=1000))
        zombie.down_until = 5
        swing(gm, "z1", rng=FixedRng(by_size={15: 1}))
        self.assertFalse(flagged(zombie))

    def test_a_floor_attack_with_a_weapon_uses_one_in_thirty(self):
        gm = street_game(weapon="item_crowbar")
        zombie = add(gm, make_zombie(1, health=1000))
        zombie.down_until = 5
        swing(gm, "z1", rng=FixedRng(by_size={30: 0}))
        self.assertTrue(flagged(zombie))

    def test_a_shove_never_flags(self):
        gm = street_game(weapon="item_crowbar")
        zombie = add(gm, make_zombie(1, health=1000))
        swing(gm, "z1", rng=FixedRng(by_size={30: 0, 15: 0}), shove=True)
        self.assertFalse(zombie.become_crawler)
        gm = street_game()
        zombie = add(gm, make_zombie(1, health=1000))
        swing(gm, "z1", rng=FixedRng(by_size={30: 0, 15: 0}))
        self.assertFalse(zombie.become_crawler)

    def test_a_killing_hit_never_flags(self):
        gm = street_game(weapon="item_crowbar")
        zombie = add(gm, make_zombie(1, health=0.001))
        result = swing(gm, "z1", rng=FixedRng(by_size={30: 0}))
        self.assertEqual(result.killed, ["z1"])
        self.assertFalse(zombie.become_crawler)

    def test_a_knife_close_kill_never_flags(self):
        gm = street_game()
        hold(gm, "item_kitchen_knife")
        zombie = add(gm, make_zombie(1, health=1000))
        result = swing(gm, "z1", rng=FixedRng(script=[0], by_size={30: 0}))
        self.assertEqual(result.killed, ["z1"])
        self.assertFalse(zombie.become_crawler)

    def test_a_zombie_that_is_already_a_crawler_is_not_rolled_again(self):
        gm = street_game(weapon="item_crowbar")
        zombie = add(gm, make_zombie(1, health=1000))
        zombie.crawling = True
        swing(gm, "z1", rng=FixedRng(by_size={30: 0}))
        self.assertFalse(zombie.become_crawler)

    def test_one_weapon_hit_in_thirty_over_many_hits(self):
        gm = street_game(weapon="item_crowbar")
        engine = MeleeEngine(random.Random(5), SkillEngine())
        crowbar = hold(gm, "item_crowbar")
        count = 0
        total = 9000
        for _ in range(total):
            zombie = add(gm, make_zombie(1, health=10**9))
            engine.swing(gm.player, gm.world, 0, "z1")
            crowbar.condition = 15
            gm.player.stats.set(CharacterStat.ENDURANCE, 1.0)
            count += flagged(zombie)
        self.assertAlmostEqual(count / total, 1 / 30, delta=0.008)


class GoingDownTests(unittest.TestCase):
    """Spec 14, Becoming a crawler: the flag takes effect on the ground."""

    def test_a_flagged_zombie_knocked_down_becomes_a_crawler(self):
        gm = street_game(weapon="item_crowbar")
        zombie = add(gm, make_zombie(1, health=1000))
        zombie.become_crawler = True
        zombie.lunger = True
        result = swing(gm, "z1", rng=FixedRng(by_size={100: 0}))
        self.assertTrue(zombie.crawling)
        self.assertFalse(zombie.become_crawler)
        self.assertFalse(zombie.lunger)
        self.assertEqual(zombie.down_until, 0)
        self.assertIn("z1 drops to the ground and starts to crawl.", result.facts)

    def test_a_flagged_zombie_hit_while_already_down_becomes_a_crawler(self):
        gm = street_game(weapon="item_crowbar")
        zombie = add(gm, make_zombie(1, health=1000))
        zombie.become_crawler = True
        zombie.down_until = 5
        swing(gm, "z1")
        self.assertTrue(zombie.crawling)

    def test_a_flagged_zombie_that_is_never_knocked_down_stays_standing(self):
        gm = street_game(weapon="item_crowbar")
        zombie = add(gm, make_zombie(1, health=1000))
        zombie.become_crawler = True
        swing(gm, "z1")
        self.assertFalse(zombie.crawling)
        self.assertTrue(zombie.become_crawler)
        self.assertTrue(zombie.staggered)

    def test_a_crawlers_speed_is_re_rolled_between_30_and_45_hundredths(self):
        speeds = set()
        for seed in range(400):
            gm = street_game(weapon="item_crowbar")
            zombie = add(gm, make_zombie(1, health=1000))
            zombie.become_crawler = True
            zombie.speed_mod = 0.9
            zombie.lunger = True
            swing(gm, "z1", rng=_CritRng(seed))
            speeds.add(zombie.speed_mod)
            self.assertFalse(zombie.lunger)
        self.assertGreaterEqual(min(speeds), 0.30)
        self.assertLess(max(speeds), 0.45)
        self.assertGreater(len(speeds), 100)


class _CritRng(random.Random):
    """A seeded generator whose crit roll always lands."""

    def randrange(self, start: int, stop: int | None = None, step: int = 1) -> int:
        if stop is None and start == 100:
            return 0
        return super().randrange(start, stop, step)


class CrawlerPostureTests(unittest.TestCase):
    """Spec 14, What changes: a crawler counts as down for swings, never gets a timer, cannot be shoved."""

    def test_a_weapon_swing_at_a_crawler_is_a_floor_attack(self):
        crawling = street_game(weapon="item_crowbar")
        down = street_game(weapon="item_crowbar")
        a = add(crawling, make_zombie(1))
        a.crawling = True
        b = add(down, make_zombie(1))
        b.down_until = 5
        swing(crawling)
        swing(down)
        self.assertGreater(100 - a.health, 0)
        self.assertAlmostEqual(100 - a.health, 100 - b.health)

    def test_a_hit_crawler_is_staggered_and_gets_no_knockdown_timer(self):
        gm = street_game(weapon="item_crowbar")
        zombie = add(gm, make_zombie(1, health=1000))
        zombie.crawling = True
        swing(gm, "z1", rng=FixedRng(by_size={100: 0}))
        self.assertTrue(zombie.staggered)
        self.assertEqual(zombie.down_until, 0)

    def test_shoving_a_crawler_is_refused(self):
        gm = zombie_game()
        zombie = add_zombie(gm, gap=1, state=ZombieState.CHASING)
        zombie.crawling = True
        zombie.time_since_seen = 0
        facts = simulate(gm, ShoveAction(target_name="z1"))
        self.assertTrue(any("It's already down." in fact for fact in facts), facts)

    def test_bare_hands_stomp_a_crawler(self):
        stomped = street_game()
        a = add(stomped, make_zombie(1))
        a.crawling = True
        swing(stomped)
        self.assertLess(a.health, 100)


class CrawlerMovementTests(unittest.TestCase):
    """Spec 14, What changes: a crawler keeps moving and never thumps."""

    def test_a_crawler_at_a_closed_door_stops_and_does_not_thump(self):
        gm = game()
        crawler = thump_zombie(gm, BUILDING, state=ZombieState.CHASING, gap=30)
        crawler.crawling = True
        crawler.time_since_seen = 0
        loop = loop_for(gm)
        for _ in range(80):
            minute(loop, gm)
        self.assertEqual(crawler.state, ZombieState.CHASING)
        self.assertIsNone(crawler.thump_barrier)
        self.assertEqual(crawler.gap, 5)

    def test_a_crawler_still_closes_on_the_player_each_minute(self):
        gm = game("zone_street")
        crawler = thump_zombie(gm, "zone_street", state=ZombieState.CHASING, gap=20)
        crawler.crawling = True
        crawler.speed_mod = 0.4
        crawler.time_since_seen = 0
        before = crawler.gap
        minute(loop_for(gm), gm)
        self.assertLess(crawler.gap, before)
        self.assertAlmostEqual(before - crawler.gap, 4 * 0.4 * 1.0, delta=0.01)

    def test_a_crawler_attacks_while_a_knocked_down_zombie_does_not(self):
        gm = game("zone_street")
        crawler = thump_zombie(gm, "zone_street", state=ZombieState.ATTACKING, gap=1)
        crawler.crawling = True
        crawler.time_since_seen = 0
        crawler.side = AttackSide.FRONT
        report = minute(loop_for(gm, seed=2), gm)
        self.assertTrue(report.attacked)


class CrawlerAttackTests(unittest.TestCase):
    """Spec 14, Crawler attacks."""

    def player(self):
        return GameManager().player

    def test_half_the_time_it_does_nothing(self):
        outcome = resolve_attack(
            self.player(), AttackSide.FRONT, 1, ScriptedRandom(randrange=[1]), crawler=True
        )
        self.assertTrue(outcome.idle)
        self.assertIsNone(outcome.wound)
        self.assertFalse(outcome.defended)

    def test_it_takes_no_defence_roll_and_aims_at_the_legs(self):
        # nothing roll 0 (acts), groin roll 5 (not 0), part index 3 of the six leg parts
        rng = ScriptedRandom(randrange=[0, 5, 3, 500, 5, 99, 0, 99, 99])
        player = self.player()
        outcome = resolve_attack(player, AttackSide.FRONT, 1, rng, crawler=True)
        self.assertFalse(outcome.defended)
        self.assertFalse(outcome.dragged_down)
        assert outcome.wound is not None
        self.assertEqual(outcome.wound.part, BodyPart.LOWERLEG_R)

    def test_a_crawler_never_drags_down_even_with_three_standing_attackers(self):
        rng = ScriptedRandom(randrange=[0, 5, 0])
        outcome = resolve_attack(self.player(), AttackSide.FRONT, 3, rng, crawler=True)
        self.assertFalse(outcome.dragged_down)

    def test_the_part_is_groin_or_a_leg_never_above(self):
        rng = random.Random(6)
        parts = [roll_crawler_body_part(rng) for _ in range(6000)]
        self.assertEqual(
            set(parts),
            {
                BodyPart.GROIN,
                BodyPart.UPPERLEG_L,
                BodyPart.UPPERLEG_R,
                BodyPart.LOWERLEG_L,
                BodyPart.LOWERLEG_R,
                BodyPart.FOOT_L,
                BodyPart.FOOT_R,
            },
        )
        self.assertAlmostEqual(parts.count(BodyPart.GROIN) / 6000, 1 / 10 * 1 / 7, delta=0.01)
        self.assertAlmostEqual(parts.count(BodyPart.FOOT_R) / 6000, 0.9 / 6 + 0.1 / 7, delta=0.015)


class CrawlersInTheMinuteTests(unittest.TestCase):
    """Spec 14, Crawler attacks: a crawler is not counted in `attackers`."""

    def crowd(self, standing: int, crawlers: int, seed: int) -> str:
        """The death fact of one minute with this crowd on the player, or ''."""
        gm = game("zone_street")
        for _ in range(standing + crawlers):
            z = thump_zombie(gm, "zone_street", state=ZombieState.ATTACKING, gap=1)
            z.time_since_seen = 0
            z.side = AttackSide.FRONT
            z.facing_cos = 1.0
        for z in list(gm.world.zombies.values())[standing:]:
            z.crawling = True
        return loop_for(gm, seed).run_minute(0, PlayerMinute()).death_fact

    def test_three_standing_zombies_and_a_crawler_still_drag_down(self):
        facts = [self.crowd(3, 1, seed) for seed in range(20)]
        self.assertIn("Orton was dragged down by the dead.", facts)

    def test_two_standing_zombies_and_a_crawler_never_drag_down(self):
        for seed in range(60):
            self.assertNotIn("dragged", self.crowd(2, 1, seed))

    def test_only_crawlers_on_the_player_never_drag_down(self):
        for seed in range(60):
            self.assertNotIn("dragged", self.crowd(0, 4, seed))


if __name__ == "__main__":
    unittest.main()
