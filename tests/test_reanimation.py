"""Spec 14, The player who rises: an infected death leaves a zombie."""

import random
import unittest

from adapters.save import codec
from data.items import ITEMS
from managers import corpses
from managers.game import GameManager
from managers.zombies import roll_zombie
from modules.action.types import Duration, WaitAction
from modules.body import BodyPart
from modules.character.appearance import Gender
from modules.character.equipment import CharacterHoldableSlot
from modules.entity.item import ItemEntity
from modules.entity.zombie import ZombieState
from tests.support import make_dying, simulate


def infected_dying_game() -> GameManager:
    gm = GameManager()
    make_dying(gm.player)
    gm.player.body[BodyPart.HAND_L].zombie_infected = True
    gm.player.zombie_infection_since = 0.0
    gm.player.zombie_infection_hours = 60.0
    gm.narrative.minutes = 60 * 10
    return gm


def die(gm: GameManager) -> list[str]:
    return simulate(gm, WaitAction(duration=Duration(minutes=20)), rng=random.Random(4))


class RisingPlayerTests(unittest.TestCase):
    """Spec 14, The player who rises."""

    def test_an_infected_death_leaves_a_zombie_in_the_zone_of_death(self):
        gm = infected_dying_game()
        die(gm)
        self.assertTrue(gm.narrative.game_over)
        self.assertEqual(len(gm.world.zombies), 1)
        zombie = next(iter(gm.world.zombies.values()))
        self.assertEqual(zombie.zone_id, gm.player.current_location_id)
        self.assertTrue(zombie.risen_from_player)
        self.assertEqual(zombie.gap, 1.0)
        self.assertEqual(zombie.state, ZombieState.IDLE)

    def test_it_has_the_players_sex_worn_items_and_carried_inventory(self):
        gm = infected_dying_game()
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_bandage"]))
        die(gm)
        zombie = next(iter(gm.world.zombies.values()))
        self.assertEqual(zombie.female, gm.player.appearance.gender == Gender.FEMALE)
        self.assertEqual(
            {location: entity.item.id for location, entity in zombie.worn.items()},
            {location: entity.item.id for location, entity in gm.player.worn.items()},
        )
        self.assertTrue(zombie.worn)
        self.assertEqual(
            [entity.item.id for entity in zombie.carried],
            [entity.item.id for entity in gm.player.inventory],
        )
        self.assertIn("item_bandage", [entity.item.id for entity in zombie.carried])

    def test_the_players_numbers_follow_the_ordinary_zombie_ids(self):
        gm = infected_dying_game()
        gm.world.next_zombie_number = 9
        die(gm)
        self.assertEqual(list(gm.world.zombies), ["z9"])
        self.assertEqual(gm.world.next_zombie_number, 10)

    def test_held_items_are_dropped_where_the_player_died(self):
        gm = infected_dying_game()
        knife = ItemEntity(item=ITEMS["item_kitchen_knife"])
        gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND] = knife
        die(gm)
        self.assertIsNone(gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND])
        self.assertIn(knife, gm.current_location.entities)

    def test_a_death_without_the_infection_leaves_no_zombie(self):
        gm = GameManager()
        make_dying(gm.player)
        die(gm)
        self.assertTrue(gm.narrative.game_over)
        self.assertEqual(gm.world.zombies, {})

    def test_no_second_fact_is_added_to_the_rose_again_one(self):
        gm = infected_dying_game()
        facts = die(gm)
        self.assertEqual(sum(1 for fact in facts if "rose again" in fact), 1)
        self.assertFalse(any("lurches" in fact or "body" in fact for fact in facts))

    def test_the_delay_lies_in_zero_to_one_minute(self):
        rng = random.Random(6)
        delays = [corpses.reanimate_delay_minutes(rng) for _ in range(2000)]
        self.assertTrue(all(0.0 <= delay < 1.0 for delay in delays))
        self.assertAlmostEqual(sum(delays) / len(delays), 0.5, delta=0.03)
        self.assertLess(min(delays), 0.01)
        self.assertGreater(max(delays), 0.99)

    def test_the_zombie_lies_until_its_delay_is_up(self):
        gm = infected_dying_game()
        die(gm)
        zombie = next(iter(gm.world.zombies.values()))
        died_at = gm.narrative.minutes
        self.assertLessEqual(zombie.down_until, died_at + 1)
        self.assertGreaterEqual(zombie.down_until, died_at - 1)

    def test_it_is_saved_with_its_inventory(self):
        gm = infected_dying_game()
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_bandage"]))
        die(gm)
        loaded = codec.from_dict(codec.to_dict(gm))
        self.assertEqual(loaded.world.zombies, gm.world.zombies)

    def test_when_it_is_killed_its_body_is_already_searched_and_holds_the_inventory(self):
        gm = infected_dying_game()
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_bandage"]))
        die(gm)
        zombie = next(iter(gm.world.zombies.values()))
        body = corpses.kill_corpse(gm.world, zombie, gm.narrative.minutes, random.Random(1))
        self.assertTrue(body.searched)
        self.assertTrue(body.risen_from_player)
        self.assertIn("item_bandage", [entity.item.id for entity in body.contents])

    def test_dressing_a_rolled_zombie_as_the_player(self):
        gm = GameManager()
        zombie = roll_zombie(random.Random(2), "z1", "zone_street")
        corpses.dress_as_player(zombie, gm.player, 100, random.Random(2))
        self.assertTrue(zombie.risen_from_player)
        self.assertEqual(zombie.outfit, "")


if __name__ == "__main__":
    unittest.main()
