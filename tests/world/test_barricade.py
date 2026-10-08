"""doors: opening, closing, boarding up, prying off and breaking through."""

import random
import unittest

from data.items import ITEMS
from data.world.barriers import WINDOW_HEALTH_SINGLE
from managers.game import GameManager
from managers.simulation import SimulationCore
from managers.zombies.noise import hammer_sound
from managers.zombies.population import ZombieLoop
from modules.action.types import (
    AttackAction,
    BarricadeAction,
    CloseAction,
    LockAction,
    MoveAction,
    OpenAction,
    UnbarricadeAction,
    UnlockAction,
)
from modules.body.stats import CharacterStat
from modules.character.equipment import CharacterHoldableSlot
from modules.entity.barrier import BarrierEntity, BarrierKind
from modules.entity.item import ItemEntity
from tests.support import load_pack

HOME = "zone_home"
BUILDING = "zone_building"


def stocked_game(*, at_door: bool = True) -> GameManager:
    """The player in the apartment with a hammer, 3 planks and 5 nails."""
    gm = GameManager()
    gm.player.inventory.clear()
    for item_id in ("item_hammer", "item_plank", "item_plank", "item_plank", "item_nails"):
        gm.player.inventory.append(ItemEntity(item=ITEMS[item_id]))
    if at_door:
        gm.player.at_barrier = "door_apartment"
    return gm


def window() -> BarrierEntity:
    return BarrierEntity(
        barrier_id="window_test",
        kind=BarrierKind.WINDOW,
        zones=(HOME, BUILDING),
        inside_zone=HOME,
        name="kitchen window",
        health=WINDOW_HEALTH_SINGLE,
        max_health=WINDOW_HEALTH_SINGLE,
    )


class Spy:
    """Records the sounds each minute of the loop is handed."""

    def __init__(self, core: SimulationCore):
        self.sounds: list[list] = []
        self._real = core._loop.run_minute
        core._loop.run_minute = self  # type: ignore[method-assign]

    def __call__(self, now, minute, extra_sounds=()):
        self.sounds.append(list(extra_sounds))
        return self._real(now, minute, extra_sounds)


class Always(random.Random):
    """A random source whose every roll comes up 0, so every 1-in-N chance happens."""

    def randrange(self, *args, **kwargs):
        return 0


def run(gm: GameManager, *actions, rng: random.Random | None = None) -> tuple[list[str], int]:
    before = gm.narrative.minutes
    facts = SimulationCore(gm, rng=rng or random.Random(1)).resolve(list(actions))
    return facts, gm.narrative.minutes - before


def count(gm: GameManager, item_id: str) -> int:
    return sum(1 for e in gm.player.inventory if e.item.id == item_id)


class BarricadeTests(unittest.TestCase):
    """doors: `BARRICADE`."""

    def test_it_costs_1_minute_one_plank_and_one_nail(self):
        gm = stocked_game()
        facts, minutes = run(gm, BarricadeAction(barrier_name="apartment door"))
        self.assertEqual(minutes, 2 - 1)
        self.assertEqual(count(gm, "item_plank"), 2)
        nails = next(e for e in gm.player.inventory if e.item.id == "item_nails")
        self.assertEqual(nails.uses, 4)
        self.assertEqual(gm.world.barriers["door_apartment"].barricades[HOME], [1000])
        self.assertIn("nails a plank across the apartment door", facts[0])

    def test_getting_to_the_door_costs_a_minute_first(self):
        gm = stocked_game(at_door=False)
        _, minutes = run(gm, BarricadeAction(barrier_name="apartment door"))
        self.assertEqual(minutes, 2)
        self.assertEqual(gm.player.at_barrier, "door_apartment")

    def test_it_gives_carpentry_10_through_the_xp_chain(self):
        gm = stocked_game()
        gm.player.traits.clear()
        run(gm, BarricadeAction(barrier_name="apartment door"))
        self.assertAlmostEqual(gm.player.skills["carpentry"].xp, 2.5)
        boosted = stocked_game()
        boosted.player.traits.clear()
        boosted.player.skill_boosts["carpentry"] = 1
        run(boosted, BarricadeAction(barrier_name="apartment door"))
        self.assertAlmostEqual(boosted.player.skills["carpentry"].xp, 10.0)

    def test_plank_health_follows_carpentry(self):
        gm = stocked_game()
        from managers.character.skills import SkillEngine

        SkillEngine().set_level(gm.player, "carpentry", 10)
        run(gm, BarricadeAction(barrier_name="apartment door"))
        self.assertEqual(gm.world.barriers["door_apartment"].barricades[HOME], [1500])

    def test_a_worn_plank_makes_a_weaker_barricade(self):
        gm = stocked_game()
        for entity in gm.player.inventory:
            if entity.item.id == "item_plank":
                entity.condition = 5
        run(gm, BarricadeAction(barrier_name="apartment door"))
        self.assertEqual(gm.world.barriers["door_apartment"].barricades[HOME], [500])

    def test_the_best_plank_is_used_first(self):
        gm = stocked_game()
        planks = [e for e in gm.player.inventory if e.item.id == "item_plank"]
        planks[0].condition = 3
        planks[1].condition = 8
        run(gm, BarricadeAction(barrier_name="apartment door"))
        self.assertEqual(gm.world.barriers["door_apartment"].barricades[HOME], [1000])

    def test_the_last_nail_leaves_the_pack(self):
        gm = stocked_game()
        nails = next(e for e in gm.player.inventory if e.item.id == "item_nails")
        nails.uses = 1
        run(gm, BarricadeAction(barrier_name="apartment door"))
        self.assertEqual(count(gm, "item_nails"), 0)

    def test_a_hammer_in_the_hand_works(self):
        gm = stocked_game()
        hammer = next(e for e in gm.player.inventory if e.item.id == "item_hammer")
        gm.player.inventory.remove(hammer)
        gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND] = hammer
        run(gm, BarricadeAction(barrier_name="apartment door"))
        self.assertEqual(gm.world.barriers["door_apartment"].plank_count(HOME), 1)

    def test_the_refusals_cost_nothing(self):
        def without(item_id: str) -> GameManager:
            gm = stocked_game()
            gm.player.inventory[:] = [e for e in gm.player.inventory if e.item.id != item_id]
            return gm

        open_door = stocked_game()
        open_door.world.barriers["door_apartment"].open = True
        full = stocked_game()
        full.world.barriers["door_apartment"].barricades[HOME] = [1000] * 4
        broken = stocked_game()
        broken.world.barriers["door_apartment"].broken = True
        cases = {
            "an open door": (open_door, "Close it first."),
            "a fifth plank": (full, "boarded"),
            "a broken door": (broken, "There's nothing left to board up."),
            "no hammer": (without("item_hammer"), "has no hammer"),
            "no plank": (without("item_plank"), "has no plank"),
            "no nails": (without("item_nails"), "has no nails"),
        }
        for label, (gm, text) in cases.items():
            with self.subTest(label):
                facts, minutes = run(gm, BarricadeAction(barrier_name="apartment door"))
                self.assertEqual(minutes, 0)
                self.assertTrue(facts[0].startswith("Refused:"), facts)
                self.assertIn(text, facts[0])

    def test_a_barrier_that_is_not_here_is_refused(self):
        gm = stocked_game()
        facts, minutes = run(gm, BarricadeAction(barrier_name="lobby door"))
        self.assertEqual(minutes, 0)
        self.assertIn("There's no door here.", facts[0])

    def test_a_broken_hammer_cannot_board_a_door_up(self):
        gm = stocked_game()
        next(e for e in gm.player.inventory if e.item.id == "item_hammer").condition = 0
        facts, _ = run(gm, BarricadeAction(barrier_name="apartment door"))
        self.assertIn("has no hammer", facts[0])

    def test_the_hammer_wears_at_one_in_180_plus_carpentry(self):
        gm = stocked_game()
        run(gm, BarricadeAction(barrier_name="apartment door"), rng=Always())
        hammer = next(e for e in gm.player.inventory if e.item.id == "item_hammer")
        self.assertEqual(hammer.condition, 9)

    def test_a_calm_roll_leaves_the_hammer_alone(self):
        wear = 0
        for seed in range(40):
            gm = stocked_game()
            run(gm, BarricadeAction(barrier_name="apartment door"), rng=random.Random(seed))
            hammer = next(e for e in gm.player.inventory if e.item.id == "item_hammer")
            wear += 10 - hammer.condition
        self.assertLessEqual(wear, 2)

    def test_it_makes_one_hammering_sound_that_zombies_hear(self):
        gm = stocked_game()
        core = SimulationCore(gm, rng=random.Random(1))
        spy = Spy(core)
        core.resolve([BarricadeAction(barrier_name="apartment door")])
        self.assertEqual([(s.radius, s.volume) for s in spy.sounds[0]], [(20, 20)])

    def test_the_hammering_radius_is_20_16_12_and_8_at_carpentry_0_2_3_and_4(self):
        self.assertEqual([hammer_sound(level).radius for level in (0, 2, 3, 4)], [20, 16, 12, 8])
        self.assertEqual(hammer_sound(1).radius, 20)
        self.assertEqual(hammer_sound(10).radius, 8)

    def test_it_takes_longer_with_the_pain_slowdown_but_never_less_than_a_minute(self):
        gm = stocked_game()
        _, minutes = run(gm, BarricadeAction(barrier_name="apartment door"))
        self.assertGreaterEqual(minutes, 1)

    def test_a_window_can_be_boarded_up_even_when_smashed(self):
        gm = stocked_game()
        gm.world.barriers["window_test"] = window()
        gm.world.barriers["window_test"].broken = True
        facts, _ = run(gm, BarricadeAction(barrier_name="kitchen window"))
        self.assertFalse(facts[0].startswith("Refused:"), facts)
        self.assertEqual(gm.world.barriers["window_test"].plank_count(HOME), 1)


class UnbarricadeTests(unittest.TestCase):
    """doors: `UNBARRICADE`."""

    def planked(self, *planks: int) -> GameManager:
        gm = stocked_game()
        gm.world.barriers["door_apartment"].barricades[HOME] = list(planks)
        return gm

    def test_it_takes_the_outermost_plank_in_one_minute_and_loses_the_nail(self):
        gm = self.planked(1000, 500)
        before = count(gm, "item_plank")
        facts, minutes = run(gm, UnbarricadeAction(barrier_name="apartment door"))
        self.assertEqual(minutes, 1)
        self.assertEqual(gm.world.barriers["door_apartment"].barricades[HOME], [1000])
        self.assertEqual(count(gm, "item_plank"), before + 1)
        returned = [e for e in gm.player.inventory if e.item.id == "item_plank"][-1]
        self.assertEqual(returned.condition, 5)
        self.assertIn("pries a plank off the apartment door", facts[0])

    def test_it_gives_carpentry_2_flat_and_strength_2(self):
        gm = self.planked(1000)
        gm.player.skill_boosts["carpentry"] = 0
        gm.player.traits.clear()
        before = gm.player.skills["strength"].xp if "strength" in gm.player.skills else 0.0
        run(gm, UnbarricadeAction(barrier_name="apartment door"))
        self.assertAlmostEqual(gm.player.skills["carpentry"].xp, 2.0)
        self.assertAlmostEqual(gm.player.skills["strength"].xp - before, 2.0)

    def test_the_crowbar_pries_too_and_a_pack_without_a_tool_does_not(self):
        gm = self.planked(1000)
        gm.player.inventory[:] = [ItemEntity(item=ITEMS["item_crowbar"])]
        facts, _ = run(gm, UnbarricadeAction(barrier_name="apartment door"))
        self.assertFalse(facts[0].startswith("Refused:"), facts)
        bare = self.planked(1000)
        bare.player.inventory.clear()
        facts, minutes = run(bare, UnbarricadeAction(barrier_name="apartment door"))
        self.assertEqual(minutes, 0)
        self.assertIn("nothing to pry with", facts[0])

    def test_only_the_players_own_side_can_be_pried(self):
        gm = stocked_game()
        gm.world.barriers["door_apartment"].barricades[BUILDING] = [1000]
        facts, minutes = run(gm, UnbarricadeAction(barrier_name="apartment door"))
        self.assertEqual(minutes, 0)
        self.assertIn("The planks are on the other side.", facts[0])
        self.assertEqual(gm.world.barriers["door_apartment"].barricades[BUILDING], [1000])

    def test_a_door_with_no_planks_is_refused(self):
        gm = stocked_game()
        facts, minutes = run(gm, UnbarricadeAction(barrier_name="apartment door"))
        self.assertEqual(minutes, 0)
        self.assertTrue(facts[0].startswith("Refused:"))

    def test_prying_makes_a_radius_10_sound(self):
        gm = self.planked(1000)
        core = SimulationCore(gm, rng=random.Random(1))
        spy = Spy(core)
        core.resolve([UnbarricadeAction(barrier_name="apartment door")])
        self.assertEqual([(s.radius, s.volume) for s in spy.sounds[0]], [(10, 1)])

    def test_a_full_pack_drops_the_plank_on_the_floor(self):
        gm = self.planked(1000)
        load_pack(gm.player, 49.9)
        run(gm, UnbarricadeAction(barrier_name="apartment door"))
        floor = [e for e in gm.current_location.entities if isinstance(e, ItemEntity)]
        self.assertTrue(any(e.item.id == "item_plank" for e in floor))


class OpenCloseTests(unittest.TestCase):
    """doors: `OPEN <barrier>` / `CLOSE <barrier>`."""

    def test_open_and_close_cost_nothing_at_the_door(self):
        gm = stocked_game()
        facts, minutes = run(gm, OpenAction(barrier_name="apartment door"))
        self.assertEqual(minutes, 0)
        self.assertTrue(gm.world.barriers["door_apartment"].open)
        self.assertIn("opens the apartment door", facts[0])
        facts, minutes = run(gm, CloseAction(barrier_name="apartment door"))
        self.assertEqual(minutes, 0)
        self.assertFalse(gm.world.barriers["door_apartment"].open)

    def test_opening_a_locked_door_from_inside_unlocks_it(self):
        gm = stocked_game()
        door = gm.world.barriers["door_apartment"]
        self.assertTrue(door.locked)
        run(gm, OpenAction(barrier_name="apartment door"))
        self.assertFalse(door.locked)

    def test_crossing_a_locked_door_from_inside_unlocks_it(self):
        from modules.action.types import MoveAction

        gm = stocked_game(at_door=False)
        door = gm.world.barriers["door_apartment"]
        run(gm, MoveAction(destination="out"))
        self.assertEqual(gm.player.current_location_id, BUILDING)
        self.assertFalse(door.locked)

    def test_opening_with_the_key_from_outside_keeps_the_lock(self):
        gm = stocked_game()
        gm.player.current_location_id = BUILDING
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_apartment_key"]))
        door = gm.world.barriers["door_apartment"]
        run(gm, OpenAction(barrier_name="apartment door"))
        self.assertTrue(door.open)
        self.assertTrue(door.locked)

    def test_a_boarded_open_window_cannot_be_closed(self):
        gm = stocked_game(at_door=False)
        gm.world.barriers["window_test"] = window()
        gm.world.barriers["window_test"].open = True
        gm.world.barriers["window_test"].barricades[HOME] = [1000]
        facts, minutes = run(gm, CloseAction(barrier_name="kitchen window"))
        self.assertEqual(minutes, 0)
        self.assertTrue(facts[0].startswith("Refused:"), facts)
        self.assertIn("The kitchen window is barricaded.", facts[0])
        self.assertTrue(gm.world.barriers["window_test"].open)

    def test_getting_to_the_door_costs_a_minute(self):
        gm = stocked_game(at_door=False)
        _, minutes = run(gm, OpenAction(barrier_name="apartment door"))
        self.assertEqual(minutes, 1)

    def test_the_door_can_be_opened_from_inside_without_the_key(self):
        gm = stocked_game()
        gm.player.inventory.clear()
        facts, _ = run(gm, OpenAction(barrier_name="apartment door"))
        self.assertFalse(facts[0].startswith("Refused:"))

    def test_refusals_cost_nothing(self):
        broken = stocked_game()
        broken.world.barriers["door_apartment"].broken = True
        barricaded = stocked_game()
        barricaded.world.barriers["door_apartment"].barricades[HOME] = [1000]
        already_open = stocked_game()
        already_open.world.barriers["door_apartment"].open = True
        outside = stocked_game()
        outside.player.current_location_id = BUILDING
        outside.player.inventory.clear()
        for label, gm, action in (
            ("broken", broken, OpenAction(barrier_name="apartment door")),
            ("barricaded", barricaded, OpenAction(barrier_name="apartment door")),
            ("already open", already_open, OpenAction(barrier_name="apartment door")),
            ("already closed", stocked_game(), CloseAction(barrier_name="apartment door")),
            ("locked out", outside, OpenAction(barrier_name="apartment door")),
        ):
            with self.subTest(label):
                facts, minutes = run(gm, action)
                self.assertEqual(minutes, 0)
                self.assertTrue(facts[0].startswith("Refused:"), facts)

    def test_opening_a_barrier_the_player_is_not_at_the_zone_of_is_refused(self):
        gm = stocked_game()
        facts, _ = run(gm, OpenAction(barrier_name="lobby door"))
        self.assertIn("There's no door here.", facts[0])


class LockTests(unittest.TestCase):
    """doors: `LOCK <barrier>` / `UNLOCK <barrier>`."""

    def inside(self, *, locked: bool = False):
        gm = stocked_game()
        door = gm.world.barriers["door_apartment"]
        door.locked = locked
        return gm, door

    def outside(self, *, locked: bool, key: bool):
        gm = stocked_game()
        gm.player.current_location_id = BUILDING
        gm.player.at_barrier = "door_apartment"
        gm.player.inventory.clear()
        if key:
            gm.player.inventory.append(ItemEntity(item=ITEMS["item_apartment_key"]))
        door = gm.world.barriers["door_apartment"]
        door.locked = locked
        return gm, door

    def test_locking_a_closed_door_from_inside_costs_nothing(self):
        gm, door = self.inside()
        facts, minutes = run(gm, LockAction(barrier_name="apartment door"))
        self.assertEqual(minutes, 0)
        self.assertTrue(door.locked)
        self.assertFalse(door.open)
        self.assertIn("locks the apartment door", facts[0])

    def test_getting_to_the_door_to_lock_it_costs_a_minute(self):
        gm, door = self.inside()
        gm.player.at_barrier = None
        _, minutes = run(gm, LockAction(barrier_name="apartment door"))
        self.assertEqual(minutes, 1)
        self.assertTrue(door.locked)

    def test_lock_is_refused_for_each_reason_at_no_cost(self):
        is_open, _ = self.inside()
        is_open.world.barriers["door_apartment"].open = True
        locked, _ = self.inside(locked=True)
        broken, _ = self.inside()
        broken.world.barriers["door_apartment"].broken = True
        smashed, _ = self.inside()
        smashed.world.barriers["window_test"] = window()
        smashed.world.barriers["window_test"].broken = True
        no_key, _ = self.outside(locked=False, key=False)
        keyless, _ = self.outside(locked=False, key=True)
        keyless.world.barriers["door_apartment"].key_id = None
        for label, gm, name, reason in (
            ("open", is_open, "apartment door", "Close it first."),
            ("already locked", locked, "apartment door", "already locked"),
            ("broken", broken, "apartment door", "no door left"),
            ("smashed", smashed, "kitchen window", "smashed"),
            ("outside, no key", no_key, "apartment door", "no key"),
            ("outside, keyless barrier", keyless, "apartment door", "no key"),
            ("not here", self.inside()[0], "lobby door", "There's no door here."),
        ):
            with self.subTest(label):
                facts, minutes = run(gm, LockAction(barrier_name=name))
                self.assertEqual(minutes, 0)
                self.assertTrue(facts[0].startswith("Refused:"), facts)
                self.assertIn(reason, facts[0])

    def test_locking_from_outside_with_the_key(self):
        gm, door = self.outside(locked=False, key=True)
        _, minutes = run(gm, LockAction(barrier_name="apartment door"))
        self.assertEqual(minutes, 0)
        self.assertTrue(door.locked)

    def test_unlocking_from_inside_leaves_the_door_closed(self):
        gm, door = self.inside(locked=True)
        facts, minutes = run(gm, UnlockAction(barrier_name="apartment door"))
        self.assertEqual(minutes, 0)
        self.assertFalse(door.locked)
        self.assertFalse(door.open)
        self.assertIn("unlocks the apartment door", facts[0])

    def test_unlocking_from_outside_with_the_key(self):
        gm, door = self.outside(locked=True, key=True)
        run(gm, UnlockAction(barrier_name="apartment door"))
        self.assertFalse(door.locked)

    def test_unlock_is_refused_for_each_reason_at_no_cost(self):
        not_locked, _ = self.inside()
        no_key, _ = self.outside(locked=True, key=False)
        broken, _ = self.inside(locked=True)
        broken.world.barriers["door_apartment"].broken = True
        smashed, _ = self.inside()
        smashed.world.barriers["window_test"] = window()
        smashed.world.barriers["window_test"].broken = True
        smashed.world.barriers["window_test"].locked = True
        for label, gm, name, reason in (
            ("not locked", not_locked, "apartment door", "isn't locked"),
            ("outside, no key", no_key, "apartment door", "no key"),
            ("broken", broken, "apartment door", "no door left"),
            ("smashed", smashed, "kitchen window", "smashed"),
            ("not here", self.inside()[0], "lobby door", "There's no door here."),
        ):
            with self.subTest(label):
                facts, minutes = run(gm, UnlockAction(barrier_name=name))
                self.assertEqual(minutes, 0)
                self.assertTrue(facts[0].startswith("Refused:"), facts)
                self.assertIn(reason, facts[0])

    def test_a_door_locked_by_the_verb_stops_a_move_from_outside(self):
        gm, door = self.inside()
        run(gm, LockAction(barrier_name="apartment door"))
        gm.player.current_location_id = BUILDING
        gm.player.inventory.clear()
        facts, _ = run(gm, MoveAction(destination="Your Apartment"))
        self.assertEqual(gm.player.current_location_id, BUILDING)
        self.assertTrue(door.locked)
        self.assertIn("locked", " ".join(facts))

    def test_a_door_locked_by_the_verb_unlocks_when_opened_from_inside(self):
        gm, door = self.inside()
        run(gm, LockAction(barrier_name="apartment door"))
        run(gm, OpenAction(barrier_name="apartment door"))
        self.assertTrue(door.open)
        self.assertFalse(door.locked)


class HitBarrierTests(unittest.TestCase):
    """doors: Breaking through."""

    def armed(self, item_id: str = "item_crowbar") -> GameManager:
        gm = stocked_game()
        entity = ItemEntity(item=ITEMS[item_id])
        gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND] = entity
        if ITEMS[item_id].is_two_handed:  # type: ignore[attr-defined]
            gm.player.equipment[CharacterHoldableSlot.LEFT_HAND] = entity
        return gm

    def test_a_crowbar_does_40_to_a_plank_in_one_minute(self):
        gm = self.armed()
        gm.world.barriers["door_apartment"].barricades[HOME] = [1000]
        facts, minutes = run(gm, AttackAction(target_name="apartment door"))
        self.assertEqual(minutes, 1)
        self.assertEqual(gm.world.barriers["door_apartment"].barricades[HOME], [960])
        self.assertIn("slams the crowbar into the apartment door", facts[0])

    def test_a_hammer_does_45_to_a_plank(self):
        gm = self.armed("item_hammer")
        gm.world.barriers["door_apartment"].barricades[HOME] = [1000]
        run(gm, AttackAction(target_name="apartment door"))
        self.assertEqual(gm.world.barriers["door_apartment"].barricades[HOME], [955])

    def test_a_crowbar_does_16_to_a_door_at_strength_5(self):
        gm = self.armed()
        run(gm, AttackAction(target_name="apartment door"), rng=random.Random(2))
        health = gm.world.barriers["door_apartment"].health
        self.assertIn(500 - health, (16, 64))

    def test_bare_hands_do_nothing_but_the_noise_carries(self):
        gm = stocked_game()
        core = SimulationCore(gm, rng=random.Random(1))
        spy = Spy(core)
        facts = core.resolve([AttackAction(target_name="apartment door")])
        self.assertEqual(gm.world.barriers["door_apartment"].health, 500)
        self.assertEqual([(s.radius, s.volume) for s in spy.sounds[0]], [(20, 20)])
        self.assertIn("with his hands", facts[0])

    def test_any_hit_smashes_a_window(self):
        gm = stocked_game()
        gm.world.barriers["window_test"] = window()
        facts, _ = run(gm, AttackAction(target_name="kitchen window"))
        self.assertTrue(gm.world.barriers["window_test"].broken)
        self.assertTrue(any("Glass shatters" in fact for fact in facts), facts)

    def test_a_door_that_gives_way_drops_planks_and_sounds_a_break(self):
        gm = self.armed()
        gm.world.barriers["door_apartment"].health = 10
        core = SimulationCore(gm, rng=random.Random(1))
        facts = core.resolve([AttackAction(target_name="apartment door")])
        self.assertTrue(gm.world.barriers["door_apartment"].broken)
        self.assertTrue(any("bursts from its hinges" in fact for fact in facts), facts)
        planks = [
            e
            for e in gm.current_location.entities
            if getattr(e, "item", None) == ITEMS["item_plank"]
        ]
        self.assertIn(len(planks), (1, 2))

    def test_an_open_barrier_with_no_planks_has_nothing_to_hit(self):
        gm = self.armed()
        gm.world.barriers["door_apartment"].open = True
        facts, minutes = run(gm, AttackAction(target_name="apartment door"))
        self.assertEqual(minutes, 0)
        self.assertIn("There's nothing to hit.", facts[0])

    def test_a_hit_wears_the_weapon_by_its_usual_roll(self):
        gm = self.armed()
        run(gm, AttackAction(target_name="apartment door"), rng=Always())
        crowbar = gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND]
        assert crowbar is not None
        self.assertEqual(crowbar.condition, 14)

    def test_a_door_hit_costs_extra_endurance_by_fitness(self):
        def endurance_after(planked: bool) -> float:
            gm = self.armed()
            if planked:
                gm.world.barriers["door_apartment"].barricades[HOME] = [1000]
            run(gm, AttackAction(target_name="apartment door"), rng=random.Random(5))
            return gm.player.stats.get(CharacterStat.ENDURANCE)

        door = endurance_after(planked=False)
        plank = endurance_after(planked=True)
        self.assertAlmostEqual(plank - door, 0.004, places=6)

    def test_jogger_spends_90_percent_of_that(self):
        def endurance_after(traits: list[str]) -> float:
            gm = self.armed()
            gm.player.traits.extend(traits)
            run(gm, AttackAction(target_name="apartment door"), rng=random.Random(5))
            return gm.player.stats.get(CharacterStat.ENDURANCE)

        base = endurance_after([])
        jogger = endurance_after(["jogger"])
        self.assertAlmostEqual(jogger - base, 0.0004, places=6)

    def test_strength_changes_the_damage(self):
        gm = self.armed()
        gm.world.barriers["door_apartment"].barricades[HOME] = [1000]
        run(gm, AttackAction(target_name="apartment door"))
        self.assertEqual(gm.world.barriers["door_apartment"].barricades[HOME], [960])


class LoopWiringTests(unittest.TestCase):
    def test_the_loop_class_is_the_one_the_core_runs(self):
        gm = stocked_game()
        self.assertIsInstance(SimulationCore(gm)._loop, ZombieLoop)


if __name__ == "__main__":
    unittest.main()


class TimedActionTests(unittest.TestCase):
    """doors: `BARRICADE` and `UNBARRICADE`: the time in frames."""

    def test_barricading_is_200_frames_so_1_minute(self):
        from data.world.barriers import BARRICADE_MIN

        self.assertEqual(BARRICADE_MIN, 1)

    def test_prying_takes_1_minute_at_every_carpentry_level_with_or_without_handy(self):
        from managers.world.barrier_use import unbarricade_minutes

        for level in range(11):
            for handy in (False, True):
                with self.subTest(level=level, handy=handy):
                    self.assertEqual(unbarricade_minutes(level, handy=handy), 1)

    def test_a_timed_action_under_a_minute_and_a_half_is_one_minute(self):
        from modules import units

        self.assertEqual(units.minutes_from_timed_action_frames(269), 1)
        self.assertEqual(units.minutes_from_timed_action_frames(270), 2)
        self.assertEqual(units.minutes_from_timed_action_frames(0), 1)


class OpeningIntoTheDeadTests(unittest.TestCase):
    """doors: Edge cases."""

    def test_opening_a_door_with_thumpers_behind_it_puts_them_on_the_player(self):
        from tests.zombies.test_thumping import game, thumper

        gm = game("zone_home")
        gm.player.at_barrier = "door_apartment"
        z = thumper(gm, "door_apartment", BUILDING)
        run(gm, OpenAction(barrier_name="apartment door"))
        self.assertEqual(z.state.value, "chasing")
        self.assertEqual(z.gap, 2)
        self.assertEqual(z.zone_id, HOME)


class WindowCrossingTests(unittest.TestCase):
    """doors: `MOVE_TO` through a barrier: windows."""

    def setUp(self):
        self.gm = GameManager()
        del self.gm.world.barriers["door_apartment"]
        self.gm.world.barriers["window_test"] = window()

    def move(self) -> int:
        from modules.action.types import MoveAction

        _, minutes = run(self.gm, MoveAction(destination="out"))
        return minutes

    def test_a_smashed_window_is_climbed_through_for_a_minute_more(self):
        self.gm.world.barriers["window_test"].broken = True
        self.assertEqual(self.move(), 2)
        self.assertEqual(self.gm.player.current_location_id, BUILDING)
        self.assertEqual(self.gm.player.at_barrier, "window_test")

    def test_a_closed_window_is_opened_first_and_stays_open(self):
        self.assertEqual(self.move(), 2)
        self.assertTrue(self.gm.world.barriers["window_test"].open)

    def test_an_open_window_stays_open(self):
        self.gm.world.barriers["window_test"].open = True
        self.move()
        self.assertTrue(self.gm.world.barriers["window_test"].open)
