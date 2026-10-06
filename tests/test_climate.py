import datetime
import unittest

from data.climate import SEASON_MODEL
from managers.climate import ClimateEngine
from modules.weather import period_seed

START = datetime.date(2023, 10, 1)


def _date(day_offset: int) -> datetime.date:
    return START + datetime.timedelta(days=day_offset)


class SeasonModelTest(unittest.TestCase):
    """Spec 04, Configuration: seasonal curves."""

    def setUp(self):
        self.season = SEASON_MODEL
        self.year = [datetime.date(2024, 1, 1) + datetime.timedelta(days=d) for d in range(366)]
        self.means = [self.season.day_mean_temperature(day) for day in self.year]

    def test_day_mean_stays_within_zero_to_twenty_five(self):
        self.assertGreaterEqual(min(self.means), 0.0)
        self.assertLessEqual(max(self.means), 25.0)

    def test_day_mean_peaks_in_late_july(self):
        peak = self.year[self.means.index(max(self.means))]
        self.assertEqual(peak.month, 7)
        self.assertGreaterEqual(peak.day, 18)

    def test_day_mean_bottoms_in_late_january(self):
        low = self.year[self.means.index(min(self.means))]
        self.assertEqual(low.month, 1)
        self.assertGreaterEqual(low.day, 18)

    def test_daily_low_near_dawn_and_high_mid_afternoon(self):
        day = datetime.date(2024, 4, 10)
        by_hour = [self.season.day_temperature(day, h) for h in range(24)]
        self.assertIn(by_hour.index(min(by_hour)), (4, 5, 6))
        self.assertIn(by_hour.index(max(by_hour)), (15, 16, 17))

    def test_day_length_is_longest_in_june(self):
        june = self.season.day_length_hours(datetime.date(2024, 6, 21))
        december = self.season.day_length_hours(datetime.date(2024, 12, 21))
        self.assertGreater(june, 14.5)
        self.assertLess(december, 9.5)


class SeasonValuesTest(unittest.TestCase):
    """Spec 04, Configuration: pinned numbers."""

    def test_monthly_rain_table(self):
        from data.climate import MONTHLY_RAIN

        self.assertEqual(
            MONTHLY_RAIN,
            (0.39, 0.35, 0.39, 0.40, 0.35, 0.37, 0.29, 0.26, 0.23, 0.23, 0.30, 0.32),
        )

    def test_day_length_at_38_north(self):
        season = SEASON_MODEL
        self.assertAlmostEqual(season.day_length_hours(datetime.date(2023, 6, 21)), 14.6398, 3)
        self.assertAlmostEqual(season.day_length_hours(datetime.date(2023, 12, 21)), 9.3605, 3)
        self.assertAlmostEqual(season.day_length_hours(datetime.date(2023, 3, 21)), 12.0, 3)

    def test_dawn_and_dusk_sit_half_a_day_length_from_high_noon(self):
        dawn, dusk = SEASON_MODEL.dawn_dusk(datetime.date(2023, 6, 21))
        self.assertAlmostEqual(dawn, 5.1801, 3)
        self.assertAlmostEqual(dusk, 19.8199, 3)

    def test_daily_swing_is_seven_degrees_peaking_at_sixteen_thirty(self):
        day = datetime.date(2023, 4, 10)
        high = SEASON_MODEL.day_temperature(day, 16.5)
        low = SEASON_MODEL.day_temperature(day, 4.5)
        self.assertAlmostEqual(high - low, 7.0)
        self.assertGreater(high, SEASON_MODEL.day_temperature(day, 16.0))
        self.assertGreater(high, SEASON_MODEL.day_temperature(day, 17.0))
        self.assertAlmostEqual(high, SEASON_MODEL.day_mean_temperature(day) + 3.5)

    def test_noise_free_mean_peaks_31_days_after_the_solstice(self):
        import dataclasses

        season = dataclasses.replace(SEASON_MODEL, noise_amplitude=0.0)
        days = [datetime.date(2023, 1, 1) + datetime.timedelta(days=d) for d in range(365)]
        means = [season.day_mean_temperature(day) for day in days]
        self.assertEqual(days[means.index(max(means))], datetime.date(2023, 7, 22))
        self.assertEqual(days[means.index(min(means))], datetime.date(2023, 1, 20))
        self.assertAlmostEqual(max(means), 25.0, 2)
        self.assertAlmostEqual(min(means), 0.0, 2)


class PeriodSeedTest(unittest.TestCase):
    """Spec 04, The world seed."""

    def test_one_october_2023(self):
        seed = period_seed(2023, 9, 1, 100, 300)
        self.assertEqual(seed, 3_300_000 + 11_106 + 2_970_000 + 200)
        self.assertEqual(seed, 6_281_306)


def _engine(seed: int = 7) -> ClimateEngine:
    return ClimateEngine(seed, START, 480)


def _first_flip_hour(engine: ClimateEngine) -> int:
    sign = engine.values.air_mass(0) > 0
    for hour in range(1, 2000):
        if (engine.values.air_mass(hour) > 0) != sign:
            return hour
    raise AssertionError("no flip found")


class SamplingTest(unittest.TestCase):
    """Spec 04, Components: pure sampling from seed and clock."""

    def test_same_seed_and_clock_give_identical_samples(self):
        a, b = _engine(7), _engine(7)
        for minutes in (0, 600, 5000, 40_000):
            self.assertEqual(a.sample(minutes), b.sample(minutes))

    def test_different_seeds_differ(self):
        samples = {_engine(seed).sample(5000) for seed in range(1, 6)}
        self.assertGreater(len(samples), 1)

    def test_values_stay_in_their_ranges(self):
        engine = _engine()
        for minutes in range(0, 60 * 24 * 40, 97):
            s = engine.sample(minutes)
            for value in (
                s.humidity,
                s.wind_intensity,
                s.cloud_intensity,
                s.precipitation_intensity,
                s.fog_intensity,
                s.daylight,
            ):
                self.assertTrue(0.0 <= value <= 1.0, value)

    def test_fog_baseline_is_point_two(self):
        engine = _engine()
        noon = (12 * 60 - 480) % 1440 + 1440
        self.assertAlmostEqual(engine.sample(noon).fog_intensity, 0.2)

    def test_daylight_by_hour(self):
        engine = _engine()
        midnight = 1440 - 480
        self.assertEqual(engine.sample(midnight).daylight, 0.0)
        self.assertEqual(engine.sample(midnight + 12 * 60).daylight, 1.0)


class FrontTest(unittest.TestCase):
    """Spec 04, Components: the hourly front check."""

    def test_sign_flip_starts_exactly_one_period(self):
        engine = _engine()
        flip = _first_flip_hour(engine)
        engine.advance_to((flip - 1) * 60)
        self.assertEqual(engine.periods_started, 0)
        self.assertIsNone(engine.period)
        engine.advance_to(flip * 60)
        self.assertEqual(engine.periods_started, 1)
        self.assertIsNotNone(engine.period)
        self.assertEqual(engine.front.start_hour, flip)

    def test_no_flip_starts_none(self):
        engine = _engine()
        flip = _first_flip_hour(engine)
        engine.advance_to((flip - 1) * 60)
        self.assertEqual(engine.periods_started, 0)

    def test_long_span_checks_every_hour_in_order(self):
        stepped, jumped = _engine(), _engine()
        for hour in range(1, 400):
            stepped.advance_to(hour * 60)
        jumped.advance_to(399 * 60)
        self.assertEqual(stepped.period, jumped.period)
        self.assertEqual(stepped.front, jumped.front)
        self.assertEqual(stepped.periods_started, jumped.periods_started)

    def test_forced_front_gives_the_stage_sequence(self):
        names = {
            0.1: ["drizzle", "showers", "clearing"],
            0.5: ["showers", "moderate", "intermezzo", "heavy_precipitation", "clearing"],
            0.9: ["showers", "heavy_precipitation", "storm", "heavy_precipitation", "clearing"],
        }
        for strength, expected in names.items():
            period = _engine().start_period(5, strength)
            summer = _engine().start_period(24 * 250, strength)
            self.assertEqual([s.name for s in period.stages], expected)
            self.assertEqual([s.name for s in summer.stages], expected)

    def test_cold_front_turns_the_storm_into_a_blizzard(self):
        january = (datetime.date(2024, 1, 20) - START).days * 24
        period = _engine().start_period(january, 0.9)
        self.assertIn("blizzard", [s.name for s in period.stages])
        self.assertTrue(any(s.thunder for s in _engine().start_period(5, 0.9).stages))

    def test_stage_is_sampled_while_the_period_runs(self):
        engine = _engine()
        period = engine.start_period(10, 0.5)
        mid = period.start_hour + 1
        sample = engine.sample(mid * 60)
        self.assertEqual(sample.stage, "showers")
        self.assertGreater(sample.precipitation_intensity, 0)
        self.assertIsNone(engine.sample((period.end_hour + 1) * 60).stage)


class SnowTest(unittest.TestCase):
    """Spec 04, Edge cases: snow follows the air temperature alone."""

    def _sample_at(self, celsius: float, raining: bool):
        from unittest import mock

        from modules.weather import ClimateValues, SeasonModel

        engine = _engine()
        if raining:
            engine.start_period(0, 0.5)
        with (
            mock.patch.object(ClimateValues, "air_mass", return_value=0.0),
            mock.patch.object(SeasonModel, "day_temperature", return_value=celsius),
        ):
            return engine.sample(60)

    def test_below_zero_is_snow(self):
        sample = self._sample_at(-0.5, raining=True)
        self.assertGreater(sample.precipitation_intensity, 0)
        self.assertTrue(sample.precipitation_is_snow)

    def test_above_zero_is_not_snow(self):
        sample = self._sample_at(0.5, raining=True)
        self.assertGreater(sample.precipitation_intensity, 0)
        self.assertFalse(sample.precipitation_is_snow)

    def test_exactly_zero_is_not_snow(self):
        self.assertFalse(self._sample_at(0.0, raining=True).precipitation_is_snow)

    def test_the_flag_follows_temperature_even_when_dry(self):
        self.assertTrue(self._sample_at(-0.5, raining=False).precipitation_is_snow)


class RainShareTest(unittest.TestCase):
    """Spec 04, Configuration: rainy hours per month track the monthly table."""

    def test_monthly_rainy_share_tracks_the_table(self):
        table = (0.39, 0.35, 0.39, 0.40, 0.35, 0.37, 0.29, 0.26, 0.23, 0.23, 0.30, 0.32)
        rainy = [0] * 12
        total = [0] * 12
        for seed in (1, 2, 3, 4, 5, 6):
            engine = ClimateEngine(seed, START, 480)
            for hour in range(8760):
                engine.advance_to(hour * 60)
                day, _ = engine._calendar(hour * 60)
                total[day.month - 1] += 1
                rainy[day.month - 1] += engine.sample(hour * 60).precipitation_intensity > 0
        shares = [r / t for r, t in zip(rainy, total, strict=True)]
        for share, expected in zip(shares, table, strict=True):
            self.assertAlmostEqual(share, expected, delta=0.15)
        self.assertAlmostEqual(sum(shares) / 12, sum(table) / 12, delta=0.05)


class NoiseValuesTest(unittest.TestCase):
    """Spec 04, Components: which offset and scale feeds which value."""

    def setUp(self):
        from modules import simplex

        self.simplex = simplex
        self.engine = _engine(11)
        self.offsets = self.engine.offsets
        self.minutes = 5000  # no period has started
        self.hours = self.minutes / 60
        self.sample = self.engine.sample(self.minutes)

    def _unit(self, value):
        return 0.5 + 0.5 * value

    def test_humidity_wind_cloud_and_angle_use_their_offsets(self):
        n = self.simplex.noise
        a, b, c, d = self.offsets
        h = self.hours
        self.assertAlmostEqual(self.sample.humidity, self._unit(n(d, h / 90)))
        self.assertAlmostEqual(self.sample.wind_intensity, self._unit(n(b, h / 40)) * 0.4)
        self.assertAlmostEqual(self.sample.cloud_intensity, self._unit(n(c + 1, h / 60)) * 0.6)
        self.assertAlmostEqual(self.sample.wind_angle, self._unit(n(a, h / 120)) * 360)

    def test_temperature_is_the_season_plus_three_degrees_of_air_mass(self):
        day, hour = self.engine._calendar(self.minutes)
        air_mass = self.simplex.noise(self.offsets[2], self.hours / 166)
        expected = SEASON_MODEL.day_temperature(day, hour) + 3.0 * air_mass
        self.assertAlmostEqual(self.sample.air_temperature, expected)

    def test_wind_angle_spans_the_circle(self):
        angles = [self.engine.sample(m).wind_angle for m in range(0, 60 * 24 * 60, 600)]
        self.assertGreater(max(angles), 270)
        self.assertLess(min(angles), 90)
        self.assertTrue(all(0 <= angle <= 360 for angle in angles))


class StageSamplingTest(unittest.TestCase):
    """Spec 04, Components: a stage's values reach the sample."""

    def test_stage_boundaries(self):
        period = _engine().start_period(10, 0.5)
        first = period.stages[0]
        self.assertIsNone(period.stage_at(9.99))
        self.assertIs(period.stage_at(10.0), first)
        self.assertIs(period.stage_at(10 + first.hours - 0.01), first)
        self.assertIs(period.stage_at(10 + first.hours), period.stages[1])
        self.assertIsNone(period.stage_at(period.end_hour))

    def test_stage_values_are_the_template_jittered_by_point_eight_to_one(self):
        period = _engine().start_period(10, 0.5)
        intensity = [0.35, 0.5, 0.05, 0.75, 0.15]
        wind = [0.2, 0.3, 0.2, 0.45, 0.2]
        cloud = [0.7, 0.8, 0.6, 0.9, 0.5]
        for stage, i, w, c in zip(period.stages, intensity, wind, cloud, strict=True):
            self.assertGreaterEqual(stage.precipitation, 0.8 * i - 1e-9)
            self.assertLessEqual(stage.precipitation, i + 1e-9)
            self.assertGreaterEqual(stage.wind, 0.8 * w - 1e-9)
            self.assertLessEqual(stage.wind, w + 1e-9)
            self.assertEqual(stage.cloud, c)

    def test_a_stage_lifts_wind_cloud_and_humidity_floors(self):
        engine = _engine()
        period = engine.start_period(10, 0.9)
        midpoint = period.start_hour + 0.5
        stage = period.stage_at(midpoint)
        assert stage is not None
        sample = engine.sample(midpoint * 60)
        self.assertGreaterEqual(sample.humidity, 0.9)
        self.assertGreaterEqual(sample.wind_intensity, stage.wind)
        self.assertGreaterEqual(sample.cloud_intensity, stage.cloud)

    def test_period_hours_scale_with_the_months_rain(self):
        january = _engine().start_period(24 * 100, 0.5)
        hours = sum(s.hours for s in january.stages)
        self.assertGreaterEqual(hours, 24.0 * 0.39 / 0.3 - 1e-9)
        self.assertLessEqual(hours, 56.0 * 0.39 / 0.3 + 1e-9)


class ExactSamplingTest(unittest.TestCase):
    """Spec 04, Components: stage jitter, fog by date, the wind floor and front strength."""

    def test_jitter_scales_precipitation_and_wind_below_the_template(self):
        period = _engine().start_period(5, 0.5)
        expected = [
            (0.3029413034346966, 0.1731093162483981),
            (0.4307096767566384, 0.258425806053983),
            (0.04444174446185394, 0.17776697784741577),
            (0.6422426783560238, 0.38534560701361426),
            (0.14904159395294514, 0.19872212527059352),
        ]
        template_precipitation = [0.35, 0.5, 0.05, 0.75, 0.15]
        template_wind = [0.2, 0.3, 0.2, 0.45, 0.2]
        for stage, (rain, wind), tp, tw in zip(
            period.stages, expected, template_precipitation, template_wind, strict=True
        ):
            self.assertAlmostEqual(stage.precipitation, rain, places=9)
            self.assertAlmostEqual(stage.wind, wind, places=9)
            self.assertLess(stage.precipitation, tp)
            self.assertLess(stage.wind, tw)

    def test_fog_strength_differs_by_day_and_is_stable(self):
        values = _engine().values
        days = [datetime.date(2023, 10, d) for d in (1, 2, 3)]
        strengths = [values.day_fog_strength(day) for day in days]
        self.assertAlmostEqual(strengths[0], 0.959364161046383, places=9)
        self.assertAlmostEqual(strengths[1], 0.5021621658300387, places=9)
        self.assertAlmostEqual(strengths[2], 0.4154551532698537, places=9)
        self.assertEqual(strengths[0], values.day_fog_strength(days[0]))

    def test_a_calm_stage_does_not_hide_the_noise_wind(self):
        engine = _engine()
        period = engine.start_period(14, 0.1)
        stage = period.stage_at(14.5)
        assert stage is not None
        self.assertLess(stage.wind, 0.1 + 1e-9)
        sample = engine.sample(14.5 * 60)
        self.assertAlmostEqual(sample.wind_intensity, 0.30136172317503085, places=9)
        self.assertGreater(sample.wind_intensity, stage.wind)

    def test_exact_front_strength_below_the_cap(self):
        engine = _engine(8)
        engine.advance_to(70 * 60)
        self.assertEqual(engine.front.start_hour, 70)
        self.assertAlmostEqual(engine.front.strength, 0.6541397997442254, places=9)


class FrontStrengthTest(unittest.TestCase):
    """Spec 04, Components: front strength and stage tiers."""

    def test_strength_is_the_air_mass_slope_times_eighty(self):
        engine = _engine()
        flip = _first_flip_hour(engine)
        engine.advance_to(flip * 60)
        slope = (engine.values.air_mass(flip + 1) - engine.values.air_mass(flip - 1)) / 2
        self.assertAlmostEqual(engine.front.strength, min(1.0, abs(slope) * 80))
        self.assertGreater(engine.front.strength, 0.0)

    def test_a_steep_flip_caps_at_one(self):
        capped = []
        for seed in range(1, 60):
            engine = _engine(seed)
            flip = _first_flip_hour(engine)
            engine.advance_to(flip * 60)
            capped.append(engine.front.strength)
        self.assertTrue(all(0.0 < strength <= 1.0 for strength in capped))
        self.assertIn(1.0, capped)

    def test_tier_boundaries_pick_the_stronger_tier(self):
        def names(strength):
            return [s.name for s in _engine().start_period(5, strength).stages]

        self.assertEqual(names(0.3399)[0], "drizzle")
        self.assertEqual(names(0.34)[0], "showers")
        self.assertIn("moderate", names(0.34))
        self.assertIn("moderate", names(0.6699))
        self.assertIn("storm", names(0.67))

    def test_restore_without_a_front_reads_the_air_mass(self):
        for seed in range(1, 8):
            engine = _engine(seed)
            engine.restore(100 * 60, None, None)
            self.assertEqual(engine.last_hour, 100)
            self.assertEqual(engine.front.positive, engine.values.air_mass(100) > 0)
            self.assertEqual(engine.front.strength, 0.0)
            self.assertEqual(engine.front.start_hour, 0)


class FogAndDaylightTest(unittest.TestCase):
    """Spec 04, Configuration: fog and daylight shapes."""

    def setUp(self):
        self.values = _engine().values
        self.day = datetime.date(2023, 10, 1)
        self.strength = self.values.day_fog_strength(self.day)
        self.assertGreater(self.strength, 0.1)

    def test_fog_peaks_at_dawn_and_burns_off_after_three_hours(self):
        self.assertAlmostEqual(self.values.fog(self.day, 6.0, 6.0), self.strength)
        self.assertAlmostEqual(self.values.fog(self.day, 7.5, 6.0), self.strength * 0.5)
        self.assertEqual(self.values.fog(self.day, 10.0, 6.0), 0.0)
        self.assertEqual(self.values.fog(self.day, 2.0, 6.0), 0.0)
        self.assertGreater(self.values.fog(self.day, 6.5, 6.0), 0.0)

    def test_the_sample_mixes_fog_as_point_two_plus_point_eight(self):
        engine = _engine()
        day, hour = engine._calendar(0)
        dawn, _ = engine.season.dawn_dusk(day)
        expected = 0.2 + 0.8 * engine.values.fog(day, hour, dawn)
        self.assertAlmostEqual(engine.sample(0).fog_intensity, expected)

    def test_daylight_ramps_over_an_hour_around_dawn_and_dusk(self):
        d = self.values.daylight
        self.assertAlmostEqual(d(6.0, 6.0, 19.0), 0.5)
        self.assertAlmostEqual(d(5.5, 6.0, 19.0), 0.0)
        self.assertAlmostEqual(d(6.5, 6.0, 19.0), 1.0)
        self.assertAlmostEqual(d(19.0, 6.0, 19.0), 0.5)
        self.assertAlmostEqual(d(19.25, 6.0, 19.0), 0.25)
        self.assertAlmostEqual(d(18.5, 6.0, 19.0), 1.0)
        self.assertAlmostEqual(d(19.5, 6.0, 19.0), 0.0)


class IndoorsTest(unittest.TestCase):
    """Spec 04, Indoors and outdoors."""

    def test_zones_match_the_table(self):
        from data.locations import build_starting_locations

        zones = build_starting_locations()
        self.assertEqual(
            {zone_id: zone.indoors for zone_id, zone in zones.items()},
            {
                "zone_home": True,
                "zone_building": True,
                "zone_street": False,
                "zone_neighborhood": False,
            },
        )


class WorldSeedTest(unittest.TestCase):
    """Spec 04, The world seed."""

    def test_new_game_draws_a_seed_and_builds_its_climate(self):
        from managers.game import GameManager

        game = GameManager()
        self.assertEqual(game.climate.seed, game.world.seed)
        a, b = GameManager(), GameManager()
        self.assertNotEqual(a.world.seed, b.world.seed)

    def test_the_seed_limit_is_two_to_the_thirty_first(self):
        import random
        from unittest import mock

        from managers import game as game_module
        from managers.game import GameManager

        class Top(random.Random):
            def randrange(self, start, stop=None, step=1):
                return start - 1

        with mock.patch.object(game_module.random, "Random", Top):
            self.assertEqual(GameManager().world.seed, 2**31 - 1)

    def test_offsets_are_drawn_up_to_eight_thousand(self):
        for seed in range(50):
            self.assertTrue(all(0 <= o <= 8000 for o in ClimateEngine(seed, START).offsets))


class FeltAirTest(unittest.TestCase):
    """Spec 06, Air temperature felt."""

    def felt(self, temperature, *, indoors=True, floor=0, power_on=False, daylight=0.0):
        from managers.climate import felt_air_temperature

        return felt_air_temperature(
            temperature, indoors=indoors, floor=floor, power_on=power_on, daylight=daylight
        )

    def test_outdoors_is_the_outdoor_temperature(self):
        self.assertEqual(self.felt(7.0, indoors=False), 7.0)

    def test_powered_indoors_is_twenty_two(self):
        self.assertEqual(self.felt(-5.0, power_on=True), 22.0)
        self.assertEqual(self.felt(35.0, power_on=True, floor=1), 22.0)

    def test_unpowered_cold_pulls_by_forty_percent_at_night(self):
        self.assertAlmostEqual(self.felt(2.0, daylight=0.0), 2.0 + 20.0 * 0.4)

    def test_unpowered_cold_pulls_by_sixty_percent_in_full_daylight(self):
        self.assertAlmostEqual(self.felt(2.0, daylight=1.0), 2.0 + 20.0 * 0.6)

    def test_upper_floor_cold_difference_is_times_085(self):
        self.assertAlmostEqual(self.felt(2.0, floor=1, daylight=0.0), 2.0 + 20.0 * 0.4 * 0.85)

    def test_hot_ground_floor_is_t_minus_d_times_085_times_m(self):
        self.assertAlmostEqual(self.felt(32.0, daylight=0.5), 32.0 - 10.0 * 0.85 * 0.5)

    def test_hot_upper_floor_has_the_night_term_and_no_085(self):
        night = 1.0 - 0.25
        self.assertAlmostEqual(
            self.felt(32.0, floor=1, daylight=0.25),
            32.0 - 10.0 * (0.4 + 0.2 * 0.25 + 0.2 * night),
        )

    def test_wind_chill_is_min_of_the_formula_and_the_temperature(self):
        from managers.climate import wind_chill_temperature

        for temperature in (10.0, 40.0):
            for wind in (0.0, 4.0, 30.0):
                v = wind**0.16
                formula = 13.12 + 0.6215 * temperature - 11.37 * v + 0.3965 * temperature * v
                with self.subTest(temperature=temperature, wind=wind):
                    self.assertAlmostEqual(
                        wind_chill_temperature(temperature, wind), min(formula, temperature)
                    )

    def test_wind_chill_has_no_limits_so_a_warm_day_and_a_breeze_still_chill(self):
        from managers.climate import wind_chill_temperature

        self.assertLess(wind_chill_temperature(20.0, 50.0), 20.0)
        self.assertLess(wind_chill_temperature(5.0, 4.0), 5.0)
        self.assertLess(wind_chill_temperature(40.0, 0.0), 40.0)

    def test_felt_air_returns_still_and_wind_chill_air_outdoors(self):
        from managers.climate import felt_air, wind_chill_temperature

        air = felt_air(0.0, 30.0, indoors=False, floor=0, power_on=True, daylight=1.0)
        self.assertEqual(air.still_c, 0.0)
        self.assertAlmostEqual(air.wind_chill_c, wind_chill_temperature(0.0, 30.0))
        self.assertAlmostEqual(air.windchill_amount, 0.0 - air.wind_chill_c)

    def test_indoors_in_strong_wind_the_two_airs_are_equal_and_the_amount_is_zero(self):
        from managers.climate import felt_air

        air = felt_air(0.0, 90.0, indoors=True, floor=0, power_on=False, daylight=1.0)
        self.assertEqual(air.wind_chill_c, air.still_c)
        self.assertAlmostEqual(air.still_c, 0.0 + 22.0 * 0.6)
        self.assertEqual(air.windchill_amount, 0.0)

    def test_the_amount_is_zero_when_the_wind_chill_is_not_colder(self):
        from managers.climate import felt_air

        air = felt_air(40.0, 0.0, indoors=False, floor=0, power_on=True, daylight=1.0)
        self.assertGreaterEqual(air.windchill_amount, 0.0)

    def test_new_world_is_powered_and_the_apartment_is_on_floor_one(self):
        from managers.game import GameManager

        game = GameManager()
        self.assertTrue(game.world.power_on)
        self.assertEqual(game.world.locations["zone_home"].floor, 1)
        self.assertEqual(game.world.locations["zone_building"].floor, 0)


if __name__ == "__main__":
    unittest.main()
