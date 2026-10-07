"""zombies: Noise and Hearing."""

import random
import unittest

from managers.game import GameManager
from managers.zombies.noise import (
    Sound,
    cough_sound,
    footstep_emit_chance,
    footstep_sound,
)
from managers.zombies.population import hears, roll_zombie
from modules.body.parts import BodyLocation
from modules.character.skills import SkillState
from modules.world.pace import Pace
from modules.world.weather import WeatherSample


def sample(rain: float = 0.0, fog: float = 0.0) -> WeatherSample:
    return WeatherSample(
        air_temperature=15,
        humidity=0.5,
        wind_intensity=0,
        wind_angle=0,
        cloud_intensity=0,
        precipitation_intensity=rain,
        precipitation_is_snow=False,
        fog_intensity=fog,
        daylight=1.0,
    )


class FootstepTests(unittest.TestCase):
    """zombies: Noise: footstep radius and volume for a default character."""

    def setUp(self):
        self.player = GameManager().player

    def test_default_radii_outdoors(self):
        self.assertEqual(footstep_sound(self.player, Pace.WALK, indoors=False).radius, 7)
        self.assertEqual(footstep_sound(self.player, Pace.RUN, indoors=False).radius, 11)
        self.assertEqual(footstep_sound(self.player, Pace.SNEAK, indoors=False).radius, 4)

    def test_default_radii_indoors(self):
        self.assertEqual(footstep_sound(self.player, Pace.WALK, indoors=True).radius, 3)
        self.assertEqual(footstep_sound(self.player, Pace.RUN, indoors=True).radius, 5)
        self.assertEqual(footstep_sound(self.player, Pace.SNEAK, indoors=True).radius, 2)

    def test_volume_equals_radius(self):
        sound = footstep_sound(self.player, Pace.WALK, indoors=False)
        self.assertEqual(sound.volume, sound.radius)

    def test_graceful_and_bare_feet_and_lightfooted_lower_it(self):
        self.player.traits.append("graceful")
        self.assertEqual(footstep_sound(self.player, Pace.WALK, indoors=False).radius, 5)
        self.player.traits.remove("graceful")
        del self.player.worn[BodyLocation.SHOES]
        self.assertEqual(footstep_sound(self.player, Pace.WALK, indoors=False).radius, 4)
        self.player.skills["lightfooted"] = SkillState(level=10, xp=0)
        self.assertEqual(footstep_sound(self.player, Pace.WALK, indoors=False).radius, 1)

    def test_clumsy_raises_it(self):
        self.player.traits.append("clumsy")
        self.assertEqual(footstep_sound(self.player, Pace.WALK, indoors=False).radius, 9)

    def test_nimble_lowers_it(self):
        self.player.skills["nimble"] = SkillState(level=10, xp=0)
        self.assertEqual(footstep_sound(self.player, Pace.WALK, indoors=False).radius, 4)

    def test_sneaking_skill_lowers_the_sneak_radius(self):
        self.player.skills["sneaking"] = SkillState(level=10, xp=0)
        self.assertEqual(footstep_sound(self.player, Pace.SNEAK, indoors=False).radius, 2)

    def test_sneak_radius_is_at_least_one(self):
        self.player.skills["sneaking"] = SkillState(level=10, xp=0)
        self.player.skills["lightfooted"] = SkillState(level=10, xp=0)
        del self.player.worn[BodyLocation.SHOES]
        self.assertEqual(footstep_sound(self.player, Pace.SNEAK, indoors=True).radius, 1)

    def test_emit_chance_per_moving_minute(self):
        self.assertAlmostEqual(footstep_emit_chance(self.player, Pace.WALK), 1 - 0.5**8)
        self.assertAlmostEqual(footstep_emit_chance(self.player, Pace.RUN), 1 - 0.5**8)
        self.assertAlmostEqual(footstep_emit_chance(self.player, Pace.SNEAK), 1 - 0.75**8)

    def test_lightfooted_makes_sneak_steps_rarer(self):
        self.player.skills["lightfooted"] = SkillState(level=8, xp=0)
        self.assertAlmostEqual(footstep_emit_chance(self.player, Pace.SNEAK), 1 - (11 / 12) ** 8)

    def test_a_cough_is_loud(self):
        self.assertEqual(cough_sound(), Sound(radius=35, volume=40))


class HearingTests(unittest.TestCase):
    """zombies: Hearing: radius, weather, zones and the poor-hearing factor."""

    def setUp(self):
        rng = random.Random(0)
        self.normal = roll_zombie(rng, "z1", "zone_street")
        self.normal.hearing = 2
        self.poor = roll_zombie(rng, "z2", "zone_street")
        self.poor.hearing = 3

    def test_a_poor_hearing_zombie_at_five_tiles_misses_a_seven_tile_sound(self):
        sound = Sound(radius=7, volume=7)
        self.assertTrue(hears(self.normal, sound, 5, False, False, sample()))
        self.assertFalse(hears(self.poor, sound, 5, False, False, sample()))

    def test_a_poor_hearing_zombie_hears_inside_a_three_point_one_five_radius(self):
        self.assertTrue(hears(self.poor, Sound(7, 7), 3, False, False, sample()))

    def test_rain_shrinks_the_radius(self):
        sound = Sound(radius=7, volume=7)
        self.assertTrue(hears(self.normal, sound, 5, False, False, sample()))
        self.assertFalse(hears(self.normal, sound, 5, False, False, sample(rain=1.0)))
        self.assertTrue(hears(self.normal, sound, 4, False, False, sample(rain=1.0)))

    def test_fog_shrinks_the_radius_less(self):
        sound = Sound(radius=10, volume=10)
        self.assertTrue(hears(self.normal, sound, 8.5, False, False, sample(fog=1.0)))
        self.assertFalse(hears(self.normal, sound, 9.5, False, False, sample(fog=1.0)))

    def test_another_zone_and_indoor_mismatch_weaken_the_sound(self):
        sound = Sound(radius=10, volume=10)
        self.assertTrue(hears(self.normal, sound, 8, False, False, sample()))
        self.assertTrue(hears(self.normal, sound, 8, True, False, sample()))
        self.assertFalse(hears(self.normal, sound, 8, True, True, sample()))
        self.assertTrue(hears(self.normal, sound, 5, True, True, sample()))

    def test_beyond_the_radius_is_never_heard(self):
        self.assertFalse(hears(self.normal, Sound(35, 40), 36, False, False, sample()))
        self.assertTrue(hears(self.normal, Sound(35, 40), 34, False, False, sample()))

    def test_a_lone_zone_hop_is_too_far_for_a_footstep(self):
        self.assertFalse(hears(self.normal, Sound(11, 11), 40, True, False, sample()))
        self.assertTrue(hears(self.normal, Sound(35, 40), 30, True, False, sample()))


if __name__ == "__main__":
    unittest.main()
