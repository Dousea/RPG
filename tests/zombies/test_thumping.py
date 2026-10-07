"""Spec 13: zombies pounding on doors and windows."""

import random
import statistics
import unittest

from data.world.barriers import WINDOW_HEALTH_SINGLE
from managers.character.skills import SkillEngine
from managers.game import GameManager
from managers.zombies import thumping
from managers.zombies.noise import Sound
from managers.zombies.population import PlayerMinute, ZombieLoop, redistribute, shut_behind
from modules.entity.barrier import BarrierEntity, BarrierKind
from modules.entity.zombie import ZombieEntity, ZombieState
from modules.world.weather import WeatherSample

HOME = "zone_home"
BUILDING = "zone_building"
STREET = "zone_street"
CLEAR = WeatherSample(
    air_temperature=15,
    humidity=0.5,
    wind_intensity=0,
    wind_angle=0,
    cloud_intensity=0,
    precipitation_intensity=0,
    precipitation_is_snow=False,
    fog_intensity=0,
    daylight=1.0,
)


def game(player_zone: str = HOME) -> GameManager:
    gm = GameManager()
    gm.player.current_location_id = player_zone
    gm.world.outbreak_started_at = 0
    gm.world.last_redistribution_minute = 0
    gm.climate.sample = lambda minutes: CLEAR  # type: ignore[method-assign]
    return gm


def zombie(
    gm: GameManager, zone_id: str, *, state: ZombieState = ZombieState.IDLE, gap: float = 10.0
) -> ZombieEntity:
    number = gm.world.next_zombie_number
    gm.world.next_zombie_number += 1
    entity = ZombieEntity(
        zombie_id=f"z{number}",
        zone_id=zone_id,
        health=2.0,
        speed_type=3,
        speed_mod=0.6,
        lunger=False,
        strength=3,
        memory=800,
        sight=2,
        hearing=2,
        state=state,
        gap=gap,
        facing_cos=-1.0,
        sound_gap=gap,
    )
    gm.world.zombies[entity.zombie_id] = entity
    return entity


def thumper(gm: GameManager, barrier_id: str, side: str, *, rate: float = 3.0) -> ZombieEntity:
    entity = zombie(gm, side, state=ZombieState.THUMPING)
    entity.thump_barrier = barrier_id
    entity.thump_rate = rate
    return entity


def loop_for(gm: GameManager, seed: int = 1) -> ZombieLoop:
    return ZombieLoop(gm, random.Random(seed), SkillEngine())


def without_spotting(loop: ZombieLoop) -> ZombieLoop:
    """The loop with step 4 switched off, so a test sees only what hearing did."""
    loop._spot = lambda *args, **kwargs: False  # type: ignore[method-assign]
    return loop


def minute(loop: ZombieLoop, gm: GameManager, **kwargs):
    return loop.run_minute(gm.narrative.minutes, PlayerMinute(**kwargs))


class StartingTests(unittest.TestCase):
    """Spec 13, Starting: the three animations and the rate."""

    def test_the_three_rates_are_1_5_1_40625_and_3_per_minute(self):
        gm = game()
        seen = set()
        for seed in range(60):
            z = zombie(gm, BUILDING, state=ZombieState.CHASING)
            thumping.start(
                gm.world,
                gm.player,
                z,
                gm.world.barriers["door_apartment"],
                BUILDING,
                random.Random(seed),
            )
            seen.add(z.thump_rate)
        self.assertEqual(seen, {1.5, 1.40625, 3.0})

    def test_the_seeded_mean_rate_is_about_1_97(self):
        gm = game()
        rates = []
        rng = random.Random(7)
        for _ in range(3000):
            z = zombie(gm, BUILDING, state=ZombieState.CHASING)
            thumping.start(
                gm.world, gm.player, z, gm.world.barriers["door_apartment"], BUILDING, rng
            )
            rates.append(z.thump_rate)
        self.assertAlmostEqual(statistics.mean(rates), 1.97, delta=0.04)

    def test_starting_remembers_whether_it_was_chasing_and_stands_one_tile_beyond_d_b(self):
        gm = game()
        chaser = zombie(gm, BUILDING, state=ZombieState.CHASING)
        alerted = zombie(gm, BUILDING, state=ZombieState.ALERTED)
        door = gm.world.barriers["door_apartment"]
        for z in (chaser, alerted):
            thumping.start(gm.world, gm.player, z, door, BUILDING, random.Random(1))
        self.assertTrue(chaser.was_chasing)
        self.assertFalse(alerted.was_chasing)
        self.assertEqual(chaser.gap, 5)
        self.assertEqual(chaser.state, ZombieState.THUMPING)
        self.assertEqual(chaser.thump_barrier, "door_apartment")
        gm.player.at_barrier = "door_apartment"
        thumping.start(gm.world, gm.player, alerted, door, BUILDING, random.Random(1))
        self.assertEqual(alerted.gap, 2)

    def test_a_thumper_at_the_other_barrier_of_the_zone_stands_half_a_zone_beyond_it(self):
        gm = game(BUILDING)
        gm.player.at_barrier = "door_apartment"
        z = zombie(gm, STREET, state=ZombieState.CHASING)
        lobby = gm.world.barriers["door_lobby"]
        thumping.start(gm.world, gm.player, z, lobby, STREET, random.Random(1))
        self.assertEqual(z.gap, 11)

    def test_a_thump_at_the_other_barrier_adds_the_stress_of_d_b_10(self):
        gm = game(BUILDING)
        gm.player.at_barrier = "door_apartment"
        thumper(gm, "door_lobby", STREET, rate=1.0)
        report = minute(loop_for(gm), gm)
        self.assertAlmostEqual(report.sound_stress, 0.0024, places=6)

    def test_opening_the_other_barrier_alerts_its_thumpers_from_half_a_zone_away(self):
        gm = game(BUILDING)
        gm.player.at_barrier = "door_apartment"
        z = thumper(gm, "door_lobby", STREET)
        lobby = gm.world.barriers["door_lobby"]
        lobby.open = True
        thumping.release(gm.world, gm.player, lobby)
        self.assertEqual(z.state, ZombieState.ALERTED)
        self.assertEqual(z.sound_gap, 11)

    def test_a_distant_chaser_walks_to_the_door_and_thumps_when_it_gets_there(self):
        gm = game()
        chaser = zombie(gm, BUILDING, state=ZombieState.CHASING, gap=30)
        chaser.time_since_seen = 0
        loop = loop_for(gm)
        minute(loop, gm)
        self.assertEqual(chaser.state, ZombieState.CHASING)
        self.assertEqual(chaser.zone_id, BUILDING)
        self.assertLess(chaser.gap, 30)
        self.assertGreater(chaser.gap, 5)
        minutes = 1
        while chaser.state == ZombieState.CHASING and minutes < 60:
            minute(loop, gm)
            minutes += 1
        self.assertGreater(minutes, 3)
        self.assertEqual(chaser.state, ZombieState.THUMPING)
        self.assertEqual(chaser.thump_barrier, "door_apartment")
        self.assertEqual(chaser.zone_id, BUILDING)
        self.assertEqual(chaser.gap, 5)

    def test_an_alerted_zombie_walking_to_a_sound_thumps_once_it_arrives(self):
        gm = game()
        walker = zombie(gm, BUILDING, state=ZombieState.ALERTED, gap=30)
        loop = loop_for(gm)
        minute(loop, gm)
        self.assertEqual(walker.state, ZombieState.ALERTED)
        self.assertLess(walker.sound_gap, 30)
        for _ in range(60):
            minute(loop, gm)
        self.assertEqual(walker.state, ZombieState.THUMPING)
        self.assertEqual(walker.zone_id, BUILDING)

    def test_a_zombie_two_zones_away_stops_at_the_hop_boundary_before_the_door(self):
        gm = game()
        chaser = zombie(gm, "zone_neighborhood", state=ZombieState.CHASING, gap=100)
        chaser.time_since_seen = 0
        chaser.memory = 10**6
        loop = loop_for(gm)
        minute(loop, gm)
        self.assertEqual(chaser.state, ZombieState.CHASING)
        self.assertEqual(chaser.zone_id, "zone_neighborhood")
        self.assertLess(chaser.gap, 100)
        for _ in range(60):
            minute(loop, gm)
        self.assertEqual(chaser.state, ZombieState.THUMPING)
        self.assertEqual(chaser.thump_barrier, "door_lobby")
        self.assertEqual(chaser.zone_id, STREET)
        self.assertEqual(chaser.gap, 80)

    def test_a_chaser_already_at_the_door_thumps_at_once(self):
        gm = game()
        chaser = zombie(gm, BUILDING, state=ZombieState.CHASING, gap=5)
        chaser.time_since_seen = 0
        minute(loop_for(gm), gm)
        self.assertEqual(chaser.state, ZombieState.THUMPING)

    def test_an_open_door_lets_a_chaser_through(self):
        gm = game()
        gm.world.barriers["door_apartment"].open = True
        chaser = zombie(gm, BUILDING, state=ZombieState.CHASING, gap=30)
        chaser.time_since_seen = 0
        minute(loop_for(gm), gm)
        self.assertEqual(chaser.state, ZombieState.CHASING)

    def test_a_zombie_in_its_cooldown_does_not_thump(self):
        gm = game()
        chaser = zombie(gm, BUILDING, state=ZombieState.CHASING, gap=30)
        chaser.time_since_seen = 0
        chaser.thump_cooldown = 2
        minute(loop_for(gm), gm)
        self.assertEqual(chaser.state, ZombieState.CHASING)

    def test_an_idle_zombie_never_thumps(self):
        gm = game()
        idler = zombie(gm, BUILDING, state=ZombieState.IDLE, gap=30)
        loop = loop_for(gm)
        for _ in range(30):
            minute(loop, gm)
        self.assertEqual(idler.state, ZombieState.IDLE)


class ShutBehindTests(unittest.TestCase):
    """Spec 13, `MOVE_TO` through a barrier: chasers behind a door the player shut."""

    def test_every_hunter_left_behind_thumps_whatever_its_gap(self):
        gm = game()
        door = gm.world.barriers["door_apartment"]
        near = zombie(gm, BUILDING, state=ZombieState.ATTACKING, gap=1)
        mid = zombie(gm, BUILDING, state=ZombieState.CHASING, gap=2)
        far = zombie(gm, BUILDING, state=ZombieState.CHASING, gap=5)
        shut_behind(gm.world, gm.player, door, BUILDING, random.Random(1))
        for z in (near, mid, far):
            self.assertEqual(z.state, ZombieState.THUMPING)
            self.assertEqual(z.thump_barrier, "door_apartment")

    def test_only_the_zombies_released_on_the_hop_are_left_out(self):
        gm = game()
        door = gm.world.barriers["door_apartment"]
        freed = zombie(gm, BUILDING, state=ZombieState.CHASING, gap=2)
        other = zombie(gm, BUILDING, state=ZombieState.CHASING, gap=2)
        shut_behind(
            gm.world, gm.player, door, BUILDING, random.Random(1), frozenset({freed.zombie_id})
        )
        self.assertEqual(freed.state, ZombieState.CHASING)
        self.assertEqual(other.state, ZombieState.THUMPING)


class EachThumpTests(unittest.TestCase):
    """Spec 13, Each thump."""

    def breaking_minute(self, rates: list[float]) -> int | None:
        gm = game()
        door = gm.world.barriers["door_apartment"]
        for rate in rates:
            thumper(gm, "door_apartment", BUILDING, rate=rate)
        for elapsed in range(1, 200):
            thumping.minute(gm.world, gm.player, random.Random(elapsed))
            if door.broken:
                return elapsed
        return None

    def test_one_zombie_never_breaks_a_door_in_48_hours(self):
        gm = game()
        door = gm.world.barriers["door_apartment"]
        z = zombie(gm, BUILDING, state=ZombieState.CHASING)
        rng = random.Random(3)
        thumping.start(gm.world, gm.player, z, door, BUILDING, rng)
        for _ in range(48 * 60):
            thumping.minute(gm.world, gm.player, rng)
        self.assertFalse(door.broken)
        self.assertEqual(door.health, 500)

    def test_two_zombies_at_the_mean_rate_break_a_full_door_in_35_to_50_minutes(self):
        minutes = self.breaking_minute([1.97, 1.97])
        assert minutes is not None
        self.assertTrue(35 <= minutes <= 50, minutes)

    def test_three_zombies_at_the_mean_rate_break_it_in_about_28_minutes(self):
        minutes = self.breaking_minute([1.97, 1.97, 1.97])
        assert minutes is not None
        self.assertTrue(26 <= minutes <= 30, minutes)

    def test_the_door_never_breaks_below_two_thumpers_whatever_their_rate(self):
        self.assertIsNone(self.breaking_minute([3.0]))

    def test_two_thumpers_on_opposite_sides_of_one_door_damage_it(self):
        gm = game()
        door = gm.world.barriers["door_apartment"]
        thumper(gm, "door_apartment", HOME)
        thumper(gm, "door_apartment", BUILDING)
        thumping.minute(gm.world, gm.player, random.Random(1))
        self.assertEqual(door.health, 500 - 3 * 6)

    def test_a_lone_thumper_on_either_side_does_not(self):
        for side in (HOME, BUILDING):
            with self.subTest(side=side):
                gm = game()
                door = gm.world.barriers["door_apartment"]
                thumper(gm, "door_apartment", side)
                for _ in range(20):
                    thumping.minute(gm.world, gm.player, random.Random(1))
                self.assertEqual(door.health, 500)

    def test_a_barricade_falls_to_one_zombie(self):
        gm = game()
        door = gm.world.barriers["door_apartment"]
        door.barricades[HOME] = [9]
        thumper(gm, "door_apartment", BUILDING)
        thumping.minute(gm.world, gm.player, random.Random(1))
        self.assertEqual(door.barricades[HOME], [])

    def test_the_thumps_left_over_when_the_door_breaks_are_dropped_and_the_carry_is_0(self):
        gm = game()
        door = gm.world.barriers["door_apartment"]
        door.health = 3
        first = thumper(gm, "door_apartment", BUILDING, rate=3.0)
        second = thumper(gm, "door_apartment", BUILDING, rate=1.5)
        second.thump_carry = 0.25
        thumping.minute(gm.world, gm.player, random.Random(1))
        self.assertTrue(door.broken)
        self.assertEqual(door.health, 0)
        for z in (first, second):
            self.assertEqual(z.thump_carry, 0.0)
            self.assertNotEqual(z.state, ZombieState.THUMPING)
            self.assertIsNone(z.thump_barrier)

    def test_the_carry_keeps_the_fraction_between_minutes(self):
        gm = game()
        z = thumper(gm, "door_apartment", BUILDING, rate=1.40625)
        other = thumper(gm, "door_apartment", HOME, rate=3.0)
        other.thump_carry = 0.0
        thumping.minute(gm.world, gm.player, random.Random(1))
        self.assertAlmostEqual(z.thump_carry, 0.40625)
        thumping.minute(gm.world, gm.player, random.Random(1))
        self.assertAlmostEqual(z.thump_carry, 0.8125)
        thumping.minute(gm.world, gm.player, random.Random(1))
        self.assertAlmostEqual(z.thump_carry, 0.21875)

    def test_a_broken_door_drops_one_or_two_planks_on_the_zombies_side(self):
        counts = set()
        for seed in range(20):
            gm = game()
            gm.world.barriers["door_apartment"].health = 3
            thumper(gm, "door_apartment", BUILDING)
            thumper(gm, "door_apartment", BUILDING)
            thumping.minute(gm.world, gm.player, random.Random(seed))
            planks = [
                e
                for e in gm.world.locations[BUILDING].entities
                if getattr(getattr(e, "item", None), "id", "") == "item_plank"
            ]
            counts.add(len(planks))
        self.assertEqual(counts, {1, 2})


class ReleaseTests(unittest.TestCase):
    """Spec 13, When the way opens."""

    def test_when_the_door_breaks_with_the_player_at_it_the_thumpers_lunge_at_gap_2(self):
        gm = game()
        gm.player.at_barrier = "door_apartment"
        gm.world.barriers["door_apartment"].health = 3
        a = thumper(gm, "door_apartment", BUILDING)
        b = thumper(gm, "door_apartment", BUILDING)
        thumping.minute(gm.world, gm.player, random.Random(1))
        for z in (a, b):
            self.assertEqual(z.state, ZombieState.CHASING)
            self.assertEqual(z.gap, 2)
            self.assertEqual(z.time_since_seen, 0)
            self.assertEqual(z.zone_id, HOME)
            self.assertEqual(z.thump_cooldown, 2)

    def test_otherwise_they_are_alerted_toward_where_the_player_was(self):
        gm = game()
        gm.world.barriers["door_apartment"].health = 3
        a = thumper(gm, "door_apartment", BUILDING)
        thumper(gm, "door_apartment", BUILDING)
        thumping.minute(gm.world, gm.player, random.Random(1))
        self.assertEqual(a.state, ZombieState.ALERTED)
        self.assertEqual(a.sound_gap, 5)
        self.assertEqual(a.zone_id, BUILDING)

    def test_opening_the_door_releases_them_with_a_cooldown(self):
        gm = game()
        gm.player.at_barrier = "door_apartment"
        z = thumper(gm, "door_apartment", BUILDING)
        door = gm.world.barriers["door_apartment"]
        door.open = True
        released = thumping.release(gm.world, gm.player, door)
        self.assertEqual(released, frozenset({z.zombie_id}))
        self.assertEqual(z.thump_cooldown, 2)
        self.assertEqual(z.state, ZombieState.CHASING)

    def test_the_last_plank_going_releases_thumpers_of_an_open_door(self):
        gm = game()
        door = gm.world.barriers["door_apartment"]
        door.open = True
        door.barricades[HOME] = [3]
        z = thumper(gm, "door_apartment", BUILDING)
        thumping.minute(gm.world, gm.player, random.Random(1))
        self.assertEqual(door.barricades[HOME], [])
        self.assertNotEqual(z.state, ZombieState.THUMPING)

    def test_a_thumper_keeps_going_after_its_memory_runs_out(self):
        gm = game()
        z = thumper(gm, "door_apartment", BUILDING)
        z.time_since_seen = 100000
        loop = loop_for(gm)
        for _ in range(20):
            minute(loop, gm)
        self.assertEqual(z.state, ZombieState.THUMPING)


class StoppingTests(unittest.TestCase):
    """Spec 13, Stopping."""

    def test_a_player_sound_from_the_zombies_side_stops_it(self):
        gm = game(BUILDING)
        z = thumper(gm, "door_apartment", BUILDING)
        z.gap = 15
        without_spotting(loop_for(gm)).run_minute(
            gm.narrative.minutes, PlayerMinute(), [Sound(radius=20, volume=20)]
        )
        self.assertEqual(z.state, ZombieState.ALERTED)
        self.assertIsNone(z.thump_barrier)
        self.assertGreaterEqual(z.thump_cooldown, 1)

    def test_a_player_sound_from_behind_the_door_does_not(self):
        gm = game(HOME)
        z = thumper(gm, "door_apartment", BUILDING)
        loop = loop_for(gm)
        loop.run_minute(gm.narrative.minutes, PlayerMinute(), [Sound(radius=20, volume=20)])
        self.assertEqual(z.state, ZombieState.THUMPING)

    def test_a_quiet_sound_does_not_stop_it(self):
        gm = game(BUILDING)
        z = thumper(gm, "door_apartment", BUILDING)
        z.gap = 3
        loop_for(gm).run_minute(gm.narrative.minutes, PlayerMinute(), [Sound(radius=5, volume=5)])
        self.assertEqual(z.state, ZombieState.THUMPING)


class SoundTests(unittest.TestCase):
    """Spec 13, Sounds."""

    def test_thumps_make_no_sound_for_the_zombies(self):
        gm = game(HOME)
        thumper(gm, "door_apartment", BUILDING)
        thumper(gm, "door_apartment", BUILDING)
        loop = loop_for(gm)
        for _ in range(5):
            minute(loop, gm)
        self.assertEqual(loop._barrier_sounds, [])

    def test_a_break_sound_is_radius_10_volume_20_and_ignored_by_the_zombies_it_released(self):
        gm = game(HOME)
        gm.world.barriers["door_apartment"].health = 3
        a = thumper(gm, "door_apartment", BUILDING)
        b = thumper(gm, "door_apartment", BUILDING)
        loop = loop_for(gm)
        minute(loop, gm)
        (heard,) = loop._barrier_sounds
        self.assertEqual((heard.sound.radius, heard.sound.volume), (10, 20))
        self.assertEqual(heard.ignored, frozenset({a.zombie_id, b.zombie_id}))

    def test_a_break_sound_draws_an_idle_zombie_in_the_players_zone(self):
        gm = game(HOME)
        gm.world.barriers["door_apartment"].health = 3
        thumper(gm, "door_apartment", BUILDING)
        thumper(gm, "door_apartment", BUILDING)
        near = zombie(gm, HOME, state=ZombieState.IDLE, gap=7)
        near.facing_cos = -1.0
        loop = without_spotting(loop_for(gm))
        minute(loop, gm)
        near.state = ZombieState.IDLE
        minute(loop, gm)
        self.assertEqual(near.state, ZombieState.ALERTED)


class StressTests(unittest.TestCase):
    """Spec 13, Stress from sounds."""

    def test_a_thump_at_d_b_4_adds_0_00384_to_the_minutes_stress(self):
        gm = game(HOME)
        thumper(gm, "door_apartment", BUILDING, rate=1.0)
        thumper(gm, "door_apartment", BUILDING, rate=1.0)
        report = minute(loop_for(gm), gm)
        self.assertAlmostEqual(report.sound_stress, 2 * 0.00384, places=6)

    def test_deaf_gets_no_stress(self):
        gm = game(HOME)
        gm.player.traits.append("deaf")
        thumper(gm, "door_apartment", BUILDING, rate=1.0)
        report = minute(loop_for(gm), gm)
        self.assertEqual(report.sound_stress, 0.0)

    def test_one_zombie_at_the_apartment_door_adds_about_0_45_stress_an_hour(self):
        gm = game(HOME)
        gm.world.barriers["door_apartment"]
        total = 0.0
        loop = loop_for(gm)
        thumper(gm, "door_apartment", BUILDING, rate=1.97)
        for _ in range(60):
            total += minute(loop, gm).sound_stress
        self.assertAlmostEqual(total, 0.45, delta=0.02)


class CutOffTests(unittest.TestCase):
    """Spec 13, Thumping: a zone whose every connection is blocked gains no zombies."""

    def counts(self, gm: GameManager) -> dict[str, int]:
        counts = {zone_id: 0 for zone_id in gm.world.locations}
        for z in gm.world.zombies.values():
            counts[z.zone_id] += 1
        return counts

    def test_the_building_and_the_apartment_gain_nothing_while_both_doors_are_shut(self):
        gm = game(STREET)
        redistribute(gm.world, 720, STREET, random.Random(3))
        self.assertEqual(self.counts(gm)["zone_home"], 0)
        self.assertEqual(self.counts(gm)[BUILDING], 0)

    def test_the_building_gains_zombies_again_once_the_lobby_door_opens(self):
        gm = game(STREET)
        gm.world.barriers["door_lobby"].open = True
        redistribute(gm.world, 720, STREET, random.Random(3))
        self.assertGreaterEqual(self.counts(gm)[BUILDING], 1)

    def test_a_cut_off_zone_with_every_connection_blocked_stays_empty(self):
        gm = game(STREET)
        gm.world.locations["zone_neighborhood"].connections = {"in": STREET}
        # the street's only link to the neighbourhood: board it up with a made-up door
        gm.world.barriers["gate"] = BarrierEntity(
            barrier_id="gate",
            kind=BarrierKind.DOOR,
            zones=(STREET, "zone_neighborhood"),
            inside_zone=STREET,
            name="gate",
            health=500,
            max_health=500,
        )
        redistribute(gm.world, 720, STREET, random.Random(3))
        self.assertEqual(self.counts(gm)["zone_neighborhood"], 0)
        gm.world.barriers["gate"].open = True
        redistribute(gm.world, 720, STREET, random.Random(3))
        self.assertGreater(self.counts(gm)["zone_neighborhood"], 0)

    def test_redistribution_never_passes_the_shut_lobby_door(self):
        gm = game(HOME)
        for _ in range(30):
            zombie(gm, STREET)
        redistribute(gm.world, 720, HOME, random.Random(3))
        self.assertEqual(self.counts(gm)[BUILDING], 0)


class SightTests(unittest.TestCase):
    """Spec 13, Stopping: a thumper rolls spotting only through glass."""

    def test_behind_a_closed_door_it_cannot_spot_the_player(self):
        gm = game(HOME)
        z = thumper(gm, "door_apartment", BUILDING)
        z.time_since_seen = 5000
        minute(loop_for(gm), gm)
        self.assertEqual(z.time_since_seen, 5000 + 180)

    def test_behind_glass_it_rolls_spotting_each_minute(self):
        gm = game(BUILDING)
        gm.world.barriers["window_test"] = BarrierEntity(
            barrier_id="window_test",
            kind=BarrierKind.WINDOW,
            zones=(BUILDING, STREET),
            inside_zone=BUILDING,
            name="lobby window",
            health=WINDOW_HEALTH_SINGLE,
            max_health=WINDOW_HEALTH_SINGLE,
        )
        z = thumper(gm, "window_test", STREET)
        z.time_since_seen = 5000
        loop = loop_for(gm)
        for _ in range(5):
            minute(loop, gm)
            if z.time_since_seen < 5000:
                break
        self.assertLess(z.time_since_seen, 5000)
        self.assertEqual(z.state, ZombieState.THUMPING)


if __name__ == "__main__":
    unittest.main()
