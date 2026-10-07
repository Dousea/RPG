"""Spec 06, Wetness; The layer walk; The body merge."""

import unittest

from managers.body.stats.drivers import StatContext
from managers.body.stats.engine import StatsEngine
from managers.body.wetness import WetnessDriver, drying_rate, rain_intensity
from modules.body.parts import BodyLocation, BodyPart
from modules.body.stats import CharacterStat, Stats
from modules.entity.item import ItemEntity
from modules.entity.player import PlayerEntity
from modules.item import ClothingItem
from modules.world.weather import WeatherSample

TORSO = {BodyPart.TORSO_UPPER}
RAIN_PER_MIN = 0.015 * 180
DRY_PER_MIN = 0.01 * 180


def weather(temperature=22.0, rain=0.0, snow=False):
    return WeatherSample(
        air_temperature=temperature,
        humidity=0.5,
        wind_intensity=0.0,
        wind_angle=0.0,
        cloud_intensity=0.0,
        precipitation_intensity=rain,
        precipitation_is_snow=snow,
        fog_intensity=0.0,
        daylight=1.0,
    )


def garment(name, location, covers=TORSO, water_resistance=0.0, wetness=0.0) -> ItemEntity:
    item = ClothingItem(
        id=name,
        name=name,
        description="",
        max_hit_points=10,
        tags=[],
        body_location=location,
        covers=frozenset(covers),
        insulation=0.3,
        wind_resistance=0.1,
        water_resistance=water_resistance,
        weight=1.0,
    )
    return ItemEntity(item=item, wetness=wetness)


def dressed(outer_resistance=0.0, outer=0.0, inner=0.0):
    player = PlayerEntity(name="Orton", current_location_id="zone_street")
    shirt = garment("shirt", BodyLocation.TSHIRT, wetness=inner)
    coat = garment("coat", BodyLocation.JACKET, water_resistance=outer_resistance, wetness=outer)
    player.worn = {BodyLocation.TSHIRT: shirt, BodyLocation.JACKET: coat}
    cool_skin(player)
    return player, shirt, coat


def cool_skin(player):
    """Skin at 20 C does not evaporate, so a test sees only the rain, sweat or air it sets up."""
    for part in BodyPart:
        player.thermal.skin[part] = 20.0


def run(player, minutes, sample, *, indoors=False, **ctx):
    engine = StatsEngine([WetnessDriver()])
    engine.advance(player, minutes, StatContext(weather=sample, indoors=indoors, **ctx))


class SourceTests(unittest.TestCase):
    """Spec 06, Wetness: the source."""

    def ctx(self, sample, indoors=False):
        return StatContext(weather=sample, indoors=indoors)

    def test_rain_intensity_boundary_is_a_tenth(self):
        self.assertEqual(rain_intensity(self.ctx(weather(rain=0.09))), 0.0)
        self.assertEqual(rain_intensity(self.ctx(weather(rain=0.1))), 0.1)
        self.assertEqual(rain_intensity(self.ctx(weather(rain=0.15))), 0.15)

    def test_snow_and_shelter_do_not_wet(self):
        self.assertEqual(rain_intensity(self.ctx(weather(rain=0.8, snow=True))), 0.0)
        self.assertEqual(rain_intensity(self.ctx(weather(rain=0.8), indoors=True)), 0.0)
        self.assertEqual(rain_intensity(StatContext()), 0.0)

    def test_drying_rate_is_0_1_plus_t_minus_5_over_10_and_never_below_0_1(self):
        self.assertAlmostEqual(drying_rate(25.0), 2.1)
        self.assertAlmostEqual(drying_rate(6.0), 0.2)
        self.assertEqual(drying_rate(5.0), 0.1)
        self.assertEqual(drying_rate(-20.0), 0.1)

    def test_rates_are_2_7_wetting_and_1_8_drying_per_minute(self):
        from data.body.thermal import WETNESS_DECREASE_per_min, WETNESS_INCREASE_per_min

        self.assertAlmostEqual(WETNESS_INCREASE_per_min, 2.7)
        self.assertAlmostEqual(WETNESS_DECREASE_per_min, 1.8)


class LayerWalkRainTests(unittest.TestCase):
    """Spec 06, The layer walk: pass 2, rain."""

    def test_the_outer_layer_soaks_first_and_only_it(self):
        player, shirt, coat = dressed()
        run(player, 1, weather(rain=0.5))
        self.assertAlmostEqual(coat.wetness, 0.5 * RAIN_PER_MIN)
        self.assertEqual(shirt.wetness, 0.0)

    def test_the_rate_is_the_intensity_times_2_7_per_minute(self):
        player, _, coat = dressed()
        run(player, 10, weather(rain=0.5))
        self.assertAlmostEqual(coat.wetness, 13.5)

    def test_a_saturated_layer_passes_the_rain_inward_at_half_rate(self):
        player, shirt, coat = dressed(outer=100.0)
        run(player, 1, weather(rain=0.5))
        self.assertEqual(coat.wetness, 100.0)
        self.assertAlmostEqual(shirt.wetness, 0.5 * RAIN_PER_MIN / 2)

    def test_a_holed_layer_passes_the_rain_on_at_half_rate_and_takes_none(self):
        player, shirt, coat = dressed()
        coat.holes.add(BodyPart.TORSO_UPPER)
        run(player, 1, weather(rain=0.5))
        self.assertEqual(coat.wetness, 0.0)
        self.assertAlmostEqual(shirt.wetness, 0.5 * RAIN_PER_MIN / 2)

    def test_water_resistance_scales_what_a_layer_takes(self):
        player, _, coat = dressed(outer_resistance=0.4)
        run(player, 1, weather(rain=0.5))
        self.assertAlmostEqual(coat.wetness, 0.5 * RAIN_PER_MIN * 0.6)

    def test_water_resistance_1_stops_the_walk(self):
        player, shirt, coat = dressed(outer_resistance=1.0)
        run(player, 1, weather(rain=1.0))
        self.assertEqual(coat.wetness, 0.0)
        self.assertEqual(shirt.wetness, 0.0)
        self.assertAlmostEqual(
            player.stats.get(CharacterStat.WETNESS), 0.9 * 16 * RAIN_PER_MIN / 17
        )

    def test_an_item_covering_two_parts_takes_half_from_each(self):
        player = PlayerEntity(name="Orton", current_location_id="zone_street")
        shirt = garment(
            "shirt", BodyLocation.TSHIRT, covers={BodyPart.TORSO_UPPER, BodyPart.TORSO_LOWER}
        )
        player.worn = {BodyLocation.TSHIRT: shirt}
        cool_skin(player)
        run(player, 1, weather(rain=0.5))
        self.assertAlmostEqual(shirt.wetness, 0.5 * RAIN_PER_MIN)

    def test_a_layer_never_exceeds_100(self):
        player, _, coat = dressed(outer=99.5)
        run(player, 5, weather(rain=1.0))
        self.assertEqual(coat.wetness, 100.0)

    def test_rain_below_a_tenth_does_not_wet_and_at_a_tenth_does(self):
        player, _, coat = dressed()
        run(player, 5, weather(rain=0.09))
        self.assertEqual(coat.wetness, 0.0)
        run(player, 5, weather(rain=0.1))
        self.assertGreater(coat.wetness, 0.0)

    def test_snow_does_not_wet(self):
        player, _, coat = dressed()
        run(player, 10, weather(temperature=-5.0, rain=0.8, snow=True))
        self.assertEqual(coat.wetness, 0.0)

    def test_indoors_the_rain_does_not_reach_the_player(self):
        player, _, coat = dressed()
        run(player, 10, weather(rain=0.8), indoors=True)
        self.assertEqual(coat.wetness, 0.0)

    def test_the_thresholds_read_the_state_at_the_start_of_each_minute(self):
        player, shirt, coat = dressed(outer=99.0)
        run(player, 1, weather(rain=1.0))
        self.assertEqual(coat.wetness, 100.0)
        self.assertEqual(shirt.wetness, 0.0)
        run(player, 1, weather(rain=1.0))
        self.assertAlmostEqual(shirt.wetness, RAIN_PER_MIN / 2)


class LayerWalkDryingTests(unittest.TestCase):
    """Spec 06, The layer walk: pass 2, drying."""

    def test_drying_at_25_degrees_takes_2_1_times_1_8_per_minute(self):
        player, _, coat = dressed(outer=50.0)
        run(player, 1, weather(temperature=25.0))
        self.assertAlmostEqual(coat.wetness, 50.0 - 2.1 * DRY_PER_MIN)

    def test_drying_is_faster_at_25_degrees_than_at_6_and_uses_still_air(self):
        warm, _, warm_coat = dressed(outer=50.0)
        cool, _, cool_coat = dressed(outer=50.0)
        run(warm, 1, weather(temperature=25.0))
        run(cool, 1, weather(temperature=6.0))
        self.assertAlmostEqual(cool_coat.wetness, 50.0 - 0.2 * DRY_PER_MIN)
        self.assertLess(warm_coat.wetness, cool_coat.wetness)

    def test_indoors_it_dries_at_the_felt_temperature(self):
        player, _, coat = dressed(outer=50.0)
        run(player, 1, weather(temperature=-10.0), indoors=True, power_on=True)
        self.assertAlmostEqual(coat.wetness, 50.0 - (0.1 + 17 / 10) * DRY_PER_MIN)

    def test_it_still_dries_a_little_at_or_below_5_degrees(self):
        player, _, coat = dressed(outer=50.0)
        run(player, 1, weather(temperature=0.0))
        self.assertAlmostEqual(coat.wetness, 50.0 - 0.1 * DRY_PER_MIN)

    def test_every_layer_that_is_wet_dries_at_the_same_rate_when_none_is_skipped(self):
        player, shirt, coat = dressed(outer=50.0, inner=50.0)
        run(player, 1, weather(temperature=25.0))
        self.assertAlmostEqual(coat.wetness, 50.0 - 2.1 * DRY_PER_MIN)
        self.assertAlmostEqual(shirt.wetness, 50.0 - 2.1 * DRY_PER_MIN)

    def test_a_layer_already_dry_is_skipped_and_the_next_dries_at_half_rate(self):
        player, shirt, coat = dressed(outer=0.0, inner=50.0)
        run(player, 1, weather(temperature=25.0))
        self.assertEqual(coat.wetness, 0.0)
        self.assertAlmostEqual(shirt.wetness, 50.0 - 2.1 * DRY_PER_MIN / 2)

    def test_a_dry_layer_then_two_wet_ones_dry_at_half_then_quarter(self):
        player = PlayerEntity(name="Orton", current_location_id="zone_street")
        a = garment("a", BodyLocation.TSHIRT, wetness=50.0)
        b = garment("b", BodyLocation.SWEATER, wetness=50.0)
        dry = garment("dry", BodyLocation.JACKET, wetness=0.0)
        player.worn = {BodyLocation.TSHIRT: a, BodyLocation.SWEATER: b, BodyLocation.JACKET: dry}
        cool_skin(player)
        run(player, 1, weather(temperature=25.0))
        self.assertAlmostEqual(b.wetness, 50.0 - 2.1 * DRY_PER_MIN / 2)
        self.assertAlmostEqual(a.wetness, 50.0 - 2.1 * DRY_PER_MIN / 4)

    def test_a_wet_layer_never_dries_below_zero(self):
        player, _, coat = dressed(outer=1.0)
        run(player, 3, weather(temperature=25.0))
        self.assertEqual(coat.wetness, 0.0)


class DividerTests(unittest.TestCase):
    """Spec 06, The layer walk: the divider."""

    def stack(self, outer, middle, inner, holed=None):
        player = PlayerEntity(name="Orton", current_location_id="zone_street")
        a = garment("a", BodyLocation.JACKET, wetness=outer)
        b = garment("b", BodyLocation.SWEATER, wetness=middle)
        c = garment("c", BodyLocation.TSHIRT, wetness=inner)
        if holed is not None:
            holed_item = {"a": a, "b": b, "c": c}[holed]
            holed_item.holes.add(BodyPart.TORSO_UPPER)
        player.worn = {BodyLocation.JACKET: a, BodyLocation.SWEATER: b, BodyLocation.TSHIRT: c}
        cool_skin(player)
        return player, a, b, c

    def test_wet_dry_wet_the_last_gets_half_not_a_quarter(self):
        player, a, b, c = self.stack(50.0, 0.0, 50.0)
        run(player, 1, weather(temperature=25.0))
        full = 2.1 * DRY_PER_MIN
        self.assertAlmostEqual(a.wetness, 50.0 - full)
        self.assertEqual(b.wetness, 0.0)
        self.assertAlmostEqual(c.wetness, 50.0 - full / 2)

    def test_a_holed_layer_above_does_not_double_the_divider(self):
        player, a, b, c = self.stack(50.0, 50.0, 50.0, holed="a")
        run(player, 1, weather(temperature=25.0))
        full = 2.1 * DRY_PER_MIN
        self.assertEqual(a.wetness, 50.0)
        self.assertAlmostEqual(b.wetness, 50.0 - full / 2)
        self.assertAlmostEqual(c.wetness, 50.0 - full / 4)

    def test_wet_layers_with_nothing_skipped_all_dry_at_the_full_amount(self):
        player, a, b, c = self.stack(50.0, 50.0, 50.0)
        run(player, 1, weather(temperature=25.0))
        for item in (a, b, c):
            self.assertAlmostEqual(item.wetness, 50.0 - 2.1 * DRY_PER_MIN)


class SweatTests(unittest.TestCase):
    """Spec 06, The layer walk: pass 1."""

    def sweating(self, secondary, *, body=0.0, rain=0.0, air=22.0, **layers):
        player, shirt, coat = dressed(**layers)
        player.thermal.secondary[BodyPart.TORSO_UPPER] = secondary
        player.stats.set(CharacterStat.WETNESS, body)
        sample = weather(temperature=air, rain=rain)
        return player, shirt, coat, sample

    def test_sweat_under_25_stays_on_the_skin(self):
        player, shirt, coat, sample = self.sweating(0.8, body=0.0)
        run(player, 1, sample, indoors=True)
        self.assertEqual(shirt.wetness, 0.0)
        self.assertEqual(coat.wetness, 0.0)

    def test_sweat_from_25_wets_the_innermost_layer_first_at_full_outdoor_scale(self):
        player, shirt, coat, sample = self.sweating(0.8, body=24.0)
        run(player, 1, sample, indoors=True)
        self.assertAlmostEqual(shirt.wetness, 0.64 * RAIN_PER_MIN)
        self.assertEqual(coat.wetness, 0.0)

    def test_cold_air_soaks_clothing_less_from_the_inside(self):
        results = {}
        for air in (-10.0, 0.0, 10.0, 30.0):
            player, shirt, _, sample = self.sweating(0.8, body=24.0, air=air)
            run(player, 1, sample, indoors=False)
            results[air] = shirt.wetness
        full = 0.64 * RAIN_PER_MIN
        self.assertAlmostEqual(results[-10.0], full * 0.4)
        self.assertAlmostEqual(results[0.0], full * 0.7)
        self.assertAlmostEqual(results[10.0], full)
        self.assertAlmostEqual(results[30.0], full)

    def test_sweat_goes_through_the_water_resistance_of_the_layer_it_wets(self):
        player = PlayerEntity(name="Orton", current_location_id="zone_street")
        shirt = garment("shirt", BodyLocation.TSHIRT, water_resistance=0.5)
        player.worn = {BodyLocation.TSHIRT: shirt}
        cool_skin(player)
        player.thermal.secondary[BodyPart.TORSO_UPPER] = 0.8
        player.stats.set(CharacterStat.WETNESS, 24.0)
        run(player, 1, weather(), indoors=True)
        self.assertAlmostEqual(shirt.wetness, 0.64 * RAIN_PER_MIN * 0.5)

    def test_a_waterproof_inner_layer_stops_the_sweat(self):
        player = PlayerEntity(name="Orton", current_location_id="zone_street")
        shirt = garment("shirt", BodyLocation.TSHIRT, water_resistance=1.0)
        coat = garment("coat", BodyLocation.JACKET)
        player.worn = {BodyLocation.TSHIRT: shirt, BodyLocation.JACKET: coat}
        cool_skin(player)
        player.thermal.secondary[BodyPart.TORSO_UPPER] = 0.8
        player.stats.set(CharacterStat.WETNESS, 24.0)
        run(player, 1, weather(), indoors=True)
        self.assertEqual(shirt.wetness, 0.0)
        self.assertEqual(coat.wetness, 0.0)

    def test_a_saturated_inner_layer_is_skipped_and_the_next_gets_half(self):
        player, shirt, coat, sample = self.sweating(0.8, body=24.0, inner=100.0)
        run(player, 1, sample, indoors=True)
        self.assertEqual(shirt.wetness, 100.0)
        self.assertAlmostEqual(coat.wetness, 0.64 * RAIN_PER_MIN / 2)

    def test_perspiration_under_a_tenth_does_not_sweat(self):
        player, shirt, _, sample = self.sweating(0.3, body=40.0)
        run(player, 1, sample, indoors=True)
        self.assertEqual(shirt.wetness, 0.0)

    def test_the_skin_gets_the_sweat(self):
        player, _, _, sample = self.sweating(0.8, body=0.0)
        run(player, 1, sample, indoors=True)
        gained = 0.64 * RAIN_PER_MIN
        self.assertAlmostEqual(player.stats.get(CharacterStat.WETNESS), 0.9 * gained / 17)


class EvaporationTests(unittest.TestCase):
    """Spec 06, The layer walk: skin evaporation."""

    def evaporating(self, body, skin_c, inner=30.0):
        player, shirt, coat = dressed(inner=inner)
        player.thermal.skin[BodyPart.TORSO_UPPER] = skin_c
        player.stats.set(CharacterStat.WETNESS, body)
        return player, shirt, coat

    def test_body_heat_dries_a_wet_skin_and_reaches_the_clothing_at_or_below_50(self):
        player, shirt, _ = self.evaporating(40.0, 30.0)
        run(player, 1, weather(temperature=5.0), indoors=False)
        loss = (10 / 22) ** 2 * DRY_PER_MIN
        self.assertAlmostEqual(shirt.wetness, 30.0 - loss - 0.1 * DRY_PER_MIN / 2)

    def test_a_skin_wetter_than_50_does_not_dry_through_clothes(self):
        player, shirt, _ = self.evaporating(60.0, 30.0)
        run(player, 1, weather(temperature=5.0), indoors=False)
        self.assertAlmostEqual(shirt.wetness, 30.0 - 0.1 * DRY_PER_MIN / 2)

    def test_a_drying_part_does_not_count_as_sweating_so_the_skin_dries_under_the_layer(self):
        player = PlayerEntity(name="Orton", current_location_id="zone_street")
        shirt = garment("shirt", BodyLocation.TSHIRT, wetness=30.0)
        player.worn = {BodyLocation.TSHIRT: shirt}
        cool_skin(player)
        player.thermal.skin[BodyPart.TORSO_UPPER] = 30.0
        player.stats.set(CharacterStat.WETNESS, 40.0)
        run(player, 1, weather(temperature=5.0), indoors=False)
        evaporation = (10 / 22) ** 2 * DRY_PER_MIN
        air = 0.1 * DRY_PER_MIN
        total = -(evaporation + air / 2) - 16 * air
        self.assertAlmostEqual(player.stats.get(CharacterStat.WETNESS), 40.0 + 0.9 * total / 17)

    def test_evaporation_reaches_the_layers_just_under_50_and_not_just_over(self):
        loss = (10 / 22) ** 2 * DRY_PER_MIN
        for after, reaches in ((49.9, True), (50.1, False)):
            with self.subTest(after=after):
                player, shirt, _ = self.evaporating(after + loss, 30.0)
                run(player, 1, weather(temperature=5.0), indoors=False)
                evaporated = shirt.wetness < 30.0 - 0.1 * DRY_PER_MIN / 2 - 0.01
                self.assertEqual(evaporated, reaches)

    def test_perspiration_above_a_tenth_sweats_and_below_it_evaporates(self):
        for secondary, sweats in ((0.15**0.5, True), (0.05**0.5, False)):
            with self.subTest(secondary=secondary):
                player = PlayerEntity(name="Orton", current_location_id="zone_street")
                cool_skin(player)
                player.thermal.skin[BodyPart.TORSO_UPPER] = 30.0
                player.thermal.secondary[BodyPart.TORSO_UPPER] = secondary
                player.stats.set(CharacterStat.WETNESS, 40.0)
                run(player, 1, weather(temperature=22.0), indoors=True)
                torso = 0.15 * RAIN_PER_MIN if sweats else -((10 / 22) ** 2) * DRY_PER_MIN
                others = -17 * 1.8 * DRY_PER_MIN
                self.assertAlmostEqual(
                    player.stats.get(CharacterStat.WETNESS), 40.0 + 0.9 * (torso + others) / 17
                )

    def test_rain_reaches_the_skin_when_the_innermost_layer_holds_50_not_49(self):
        for inner, reaches in ((50.0, True), (49.9, False)):
            with self.subTest(inner=inner):
                player = PlayerEntity(name="Orton", current_location_id="zone_street")
                shirt = garment("shirt", BodyLocation.TSHIRT, wetness=inner)
                player.worn = {BodyLocation.TSHIRT: shirt}
                cool_skin(player)
                run(player, 1, weather(rain=0.5))
                bare = 16 * 0.5 * RAIN_PER_MIN
                covered = 0.5 * RAIN_PER_MIN / 2 if reaches else 0.0
                self.assertAlmostEqual(
                    player.stats.get(CharacterStat.WETNESS), 0.9 * (bare + covered) / 17
                )

    def test_rain_stops_the_skin_from_drying(self):
        player, shirt, coat = self.evaporating(40.0, 30.0)
        run(player, 1, weather(temperature=5.0, rain=0.5), indoors=False)
        self.assertEqual(shirt.wetness, 30.0)
        self.assertAlmostEqual(coat.wetness, 0.5 * RAIN_PER_MIN)


class BodyMergeTests(unittest.TestCase):
    """Spec 06, The body merge."""

    def test_a_bare_player_in_rain_gains_0_9_times_the_mean_part_change(self):
        player = PlayerEntity(name="Orton", current_location_id="zone_street")
        cool_skin(player)
        run(player, 1, weather(rain=0.5))
        self.assertAlmostEqual(player.stats.get(CharacterStat.WETNESS), 0.9 * 0.5 * RAIN_PER_MIN)

    def test_bare_wetness_accumulates_each_minute(self):
        player = PlayerEntity(name="Orton", current_location_id="zone_street")
        cool_skin(player)
        run(player, 10, weather(rain=0.5))
        self.assertAlmostEqual(
            player.stats.get(CharacterStat.WETNESS), 10 * 0.9 * 0.5 * RAIN_PER_MIN
        )

    def test_a_bare_player_dries_by_the_same_merge(self):
        player = PlayerEntity(name="Orton", current_location_id="zone_street")
        cool_skin(player)
        player.stats.set(CharacterStat.WETNESS, 50.0)
        run(player, 1, weather(temperature=25.0))
        self.assertAlmostEqual(
            player.stats.get(CharacterStat.WETNESS), 50.0 - 0.9 * 2.1 * DRY_PER_MIN
        )

    def test_a_clothed_torso_is_a_share_of_the_average(self):
        player, shirt, coat = dressed()
        player.stats.set(CharacterStat.WETNESS, 0.0)
        run(player, 1, weather(rain=0.5))
        gained_by_bare_parts = 16 * 0.5 * RAIN_PER_MIN
        self.assertAlmostEqual(
            player.stats.get(CharacterStat.WETNESS), 0.9 * gained_by_bare_parts / 17
        )

    def test_rain_reaches_the_skin_under_clothes_only_when_the_innermost_layer_is_at_50(self):
        for inner, share in ((60.0, 0.5), (40.0, 0.0)):
            with self.subTest(inner=inner):
                player, shirt, coat = dressed(inner=inner)
                run(player, 1, weather(rain=0.5))
                bare = 16 * 0.5 * RAIN_PER_MIN
                skin = 0.5 * RAIN_PER_MIN * share
                self.assertAlmostEqual(
                    player.stats.get(CharacterStat.WETNESS), 0.9 * (bare + skin) / 17
                )

    def test_air_dries_the_skin_under_clothes_only_while_the_innermost_layer_is_at_or_under_50(
        self,
    ):
        for inner, share in ((50.0, 0.5), (51.0, 0.0)):
            with self.subTest(inner=inner):
                player, _, _ = dressed(inner=inner)
                player.stats.set(CharacterStat.WETNESS, 40.0)
                run(player, 1, weather(temperature=25.0))
                bare = 16 * 2.1 * DRY_PER_MIN
                covered = 2.1 * DRY_PER_MIN * share
                self.assertAlmostEqual(
                    player.stats.get(CharacterStat.WETNESS), 40.0 - 0.9 * (bare + covered) / 17
                )

    def test_the_stat_never_leaves_0_to_100(self):
        player = PlayerEntity(name="Orton", current_location_id="zone_street")
        player.stats.set(CharacterStat.WETNESS, 99.9)
        run(player, 10, weather(rain=1.0))
        self.assertLessEqual(player.stats.get(CharacterStat.WETNESS), 100.0)
        self.assertGreater(player.stats.get(CharacterStat.WETNESS), 99.9)
        dry = PlayerEntity(name="Orton", current_location_id="zone_street")
        run(dry, 10, weather(temperature=25.0))
        self.assertEqual(dry.stats.get(CharacterStat.WETNESS), 0.0)

    def test_taking_the_wet_layer_off_drops_it_from_the_model(self):
        player, shirt, coat = dressed(outer=90.0)
        del player.worn[BodyLocation.JACKET]
        run(player, 1, weather(temperature=25.0))
        self.assertEqual(coat.wetness, 90.0)

    def test_without_a_wearer_the_driver_does_nothing(self):
        stats = Stats()
        WetnessDriver().apply(stats, 1.0, StatContext(weather=weather(rain=1.0)))
        self.assertEqual(stats.get(CharacterStat.WETNESS), 0)


if __name__ == "__main__":
    unittest.main()
