"""zombies: Spotting: how a zombie notices the player."""

import dataclasses
import random
import unittest

from managers.game import GameManager
from managers.zombies.population import detection_range, light_level, roll_zombie, spot_chance
from modules.body.parts import BodyLocation
from modules.body.stats import CharacterStat
from modules.character.skills import SkillState
from modules.entity.item import ItemEntity
from modules.item import ClothingItem
from modules.world.pace import Pace
from modules.world.weather import WeatherSample


def sample(daylight: float = 1.0, rain: float = 0.0, fog: float = 0.0) -> WeatherSample:
    return WeatherSample(
        air_temperature=15,
        humidity=0.5,
        wind_intensity=0,
        wind_angle=0,
        cloud_intensity=0,
        precipitation_intensity=rain,
        precipitation_is_snow=False,
        fog_intensity=fog,
        daylight=daylight,
    )


class SpotTests(unittest.TestCase):
    """zombies: Spotting: the per-frame chance and the minute chance."""

    def setUp(self):
        self.player = GameManager().player
        self.zombie = roll_zombie(random.Random(0), "z1", "zone_street")
        self.zombie.sight = 2
        self.zombie.gap = 8
        self.zombie.facing_cos = 0.1
        self.zombie.bonus_spot_time = 0

    def chance(self, light: float = 0.5, pace: Pace = Pace.WALK, weather=None):
        return spot_chance(self.zombie, self.player, weather or sample(light), light, pace)

    def test_a_zombie_facing_the_player_in_daylight_always_spots(self):
        self.zombie.facing_cos = 1.0
        self.zombie.gap = 10
        result = self.chance(1.0)
        self.assertEqual(result.per_frame, 1.0)
        self.assertEqual(result.per_minute, 1.0)

    def test_facing_below_minus_point_four_never_spots(self):
        self.zombie.facing_cos = -0.41
        self.zombie.gap = 2
        result = self.chance(1.0)
        self.assertEqual(result.per_frame, 0.0)
        self.assertEqual(result.per_minute, 0.0)

    def test_the_facing_bands(self):
        expected = {
            -0.4: 100 / 8,
            -0.21: 100 / 8,
            -0.2: 100 / 4,
            -0.01: 100 / 4,
            0.0: 100 / 2,
            0.19: 100 / 2,
            0.2: 200,
            0.4: 200,
            0.41: 800,
        }
        for cos, raw in expected.items():
            with self.subTest(cos=cos):
                self.zombie.facing_cos = cos
                self.zombie.gap = 8
                self.assertAlmostEqual(self.chance(1.0, Pace.WALK).raw, raw)

    def test_a_hand_computed_dim_light_chance(self):
        # light 0.5 -> 50, facing 0.1 halves it -> 25, walking x1.0: 25/400 per frame.
        result = self.chance(0.5)
        self.assertEqual(result.raw, 25)
        self.assertAlmostEqual(result.per_frame, 25 / 400)
        self.assertAlmostEqual(result.per_minute, 1 - (1 - 25 / 400) ** 180)

    def test_the_minute_chance_is_one_minus_the_frames_missed(self):
        self.zombie.gap = 6
        self.zombie.facing_cos = 0.1
        result = self.chance(0.1)
        self.assertAlmostEqual(result.per_frame, 5 / 400)
        self.assertAlmostEqual(result.per_minute, 1 - (1 - 0.0125) ** 180)

    def test_standing_still_uses_the_sneaky_movement_factor(self):
        self.assertEqual(self.chance(0.5, Pace.STILL).raw, 20)
        self.assertEqual(self.chance(0.5, Pace.RUN).raw, 37.5)

    def test_gap_beyond_the_vision_radius_never_spots(self):
        self.zombie.facing_cos = 1.0
        self.zombie.gap = 20
        self.assertGreater(self.chance(1.0).per_frame, 0)
        self.zombie.gap = 21
        self.assertEqual(self.chance(1.0).per_frame, 0)

    def test_poor_sight_vision_clamps_to_ten_tiles(self):
        self.zombie.sight = 3
        self.zombie.facing_cos = 1.0
        self.zombie.gap = 10
        self.assertGreater(self.chance(1.0).per_frame, 0)
        self.zombie.gap = 11
        self.assertEqual(self.chance(1.0).per_frame, 0)

    def test_darkness_shrinks_vision(self):
        self.zombie.facing_cos = 1.0
        self.zombie.gap = 16
        self.assertGreater(self.chance(0.2).per_frame, 0)
        self.zombie.gap = 17
        self.assertEqual(self.chance(0.2).per_frame, 0)
        self.assertGreater(self.chance(1.0).per_frame, 0)

    def test_no_light_never_spots(self):
        self.zombie.facing_cos = 1.0
        self.zombie.gap = 3
        self.assertEqual(self.chance(0.0).per_frame, 0)

    def test_rain_and_fog_shrink_vision(self):
        self.zombie.facing_cos = 1.0
        self.zombie.gap = 18
        self.assertGreater(self.chance(1.0, weather=sample(1.0)).per_frame, 0)
        self.assertEqual(self.chance(1.0, weather=sample(1.0, rain=1.0)).per_frame, 0)
        self.zombie.gap = 14
        self.assertEqual(self.chance(1.0, weather=sample(1.0, fog=1.0)).per_frame, 0)

    def test_near_zombies_get_triple_chance_unless_sneaking(self):
        self.zombie.gap = 4
        self.assertEqual(self.chance(0.5).raw, 75)
        self.player.sneaking = True
        self.assertAlmostEqual(self.chance(0.5, Pace.SNEAK).raw, 22.8)

    def test_sneaking_lowers_the_chance(self):
        walking = self.chance(0.5).per_frame
        self.player.sneaking = True
        sneaking = self.chance(0.5, Pace.SNEAK)
        self.assertAlmostEqual(sneaking.raw, 22.8)
        self.assertEqual(sneaking.per_frame, 22 / 400)
        self.assertLess(sneaking.per_frame, walking)

    def test_a_higher_sneaking_level_lowers_it_more(self):
        self.player.sneaking = True
        self.player.skills["sneaking"] = SkillState(level=10, xp=0)
        self.assertAlmostEqual(self.chance(0.5, Pace.SNEAK).raw, 9.6)

    def test_bonus_time_multiplies_by_five(self):
        self.zombie.bonus_spot_time = 360
        self.assertEqual(self.chance(0.5).raw, 125)

    def test_poor_sight_multiplies_by_point_four_five(self):
        self.zombie.sight = 3
        self.assertEqual(self.chance(0.5).raw, 11.25)

    def test_inconspicuous_lowers_and_conspicuous_raises(self):
        self.player.traits.append("inconspicuous")
        self.assertAlmostEqual(self.chance(0.5).raw, 20)
        self.player.traits[:] = ["conspicuous"]
        self.assertAlmostEqual(self.chance(0.5).raw, 30)

    def test_the_per_frame_chance_is_capped_at_one(self):
        self.zombie.facing_cos = 1.0
        self.zombie.gap = 2
        self.assertEqual(self.chance(1.0).per_frame, 1.0)

    def test_the_floor_is_taken_before_dividing(self):
        self.player.traits.append("conspicuous")
        self.zombie.sight = 3
        self.assertEqual(self.chance(0.5).per_frame, 13 / 400)


class LightTests(unittest.TestCase):
    """zombies: Spotting: light outdoors and indoors, with and without power."""

    def test_outdoors_is_daylight(self):
        self.assertEqual(light_level(False, True, 0.4), 0.4)

    def test_indoors_with_power_is_full_light(self):
        self.assertEqual(light_level(True, True, 0.1), 1.0)

    def test_indoors_without_power_is_six_tenths_of_daylight(self):
        self.assertAlmostEqual(light_level(True, False, 0.5), 0.3)


if __name__ == "__main__":
    unittest.main()


class DetectionRangeTests(unittest.TestCase):
    """zombies: Hearing: how far the player hears a zombie."""

    def setUp(self):
        self.player = GameManager().player
        self.player.worn.clear()

    def test_the_base_range_is_three_and_a_half_tiles(self):
        self.assertEqual(detection_range(self.player), 3.5)

    def test_fatigue_takes_its_value_off_the_range(self):
        self.player.stats.set(CharacterStat.FATIGUE, 0.5)
        self.assertAlmostEqual(detection_range(self.player), 3.0)

    def test_intoxication_takes_a_hundredth_of_a_tile_per_point(self):
        self.player.stats.set(CharacterStat.INTOXICATION, 50)
        self.assertAlmostEqual(detection_range(self.player), 3.0)

    def _worn(self, modifier: float) -> ItemEntity:
        base = ClothingItem(
            id="item_test_hat",
            name="Test hat",
            description="",
            max_hit_points=10,
            tags=[],
            body_location=BodyLocation.HAT,
            covers=frozenset(),
            insulation=0.5,
            wind_resistance=0.5,
            water_resistance=0.5,
            weight=1.0,
            hearing_modifier=modifier,
        )
        return ItemEntity(item=dataclasses.replace(base))

    def test_a_muffling_item_shrinks_the_range_above_the_floor(self):
        self.player.worn[BodyLocation.HAT] = self._worn(0.5)
        self.assertAlmostEqual(detection_range(self.player), 2.75)

    def test_an_item_at_zero_or_below_is_skipped(self):
        self.player.worn[BodyLocation.HAT] = self._worn(0.0)
        self.assertEqual(detection_range(self.player), 3.5)
        self.player.worn[BodyLocation.HAT] = self._worn(-1.0)
        self.assertEqual(detection_range(self.player), 3.5)
