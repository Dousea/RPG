"""Climate engine: weather for any moment, and the hourly front check (spec 04)."""

import datetime
import logging
import random

from data import climate as k
from data.clock import MINUTES_PER_DAY, MINUTES_PER_HOUR
from modules.weather import (
    AirFront,
    ClimateValues,
    WeatherPeriod,
    WeatherSample,
    period_seed,
    simplex_offsets,
)

logger = logging.getLogger(__name__)


class ClimateEngine:
    """Deterministic weather from a world seed and the game clock.

    `minutes` everywhere is the game clock; the world's age in hours is
    `minutes / 60`, and the calendar starts at `start_date` at
    `start_minute_of_day`.
    """

    def __init__(self, seed: int, start_date: datetime.date, start_minute_of_day: int = 0) -> None:
        self.seed = seed
        self.start_date = start_date
        self.start_minute_of_day = start_minute_of_day
        self.offsets = simplex_offsets(seed, k.SIMPLEX_OFFSET_MAX)
        self.season = k.SEASON_MODEL
        self.values = ClimateValues(
            offsets=self.offsets,
            air_mass_hours=k.AIR_MASS_NOISE_FREQUENCY,
            humidity_hours=k.HUMIDITY_NOISE_HOURS,
            wind_hours=k.WIND_NOISE_HOURS,
            wind_angle_hours=k.WIND_ANGLE_NOISE_HOURS,
            cloud_hours=k.CLOUD_NOISE_HOURS,
            wind_base_max=k.WIND_BASE_MAX,
            cloud_base_max=k.CLOUD_BASE_MAX,
            fog_seed=k.FOG_SEED,
            fog_peak_after_dawn=k.FOG_PEAK_AFTER_DAWN_HOURS,
            fog_clear_after_dawn=k.FOG_CLEAR_AFTER_DAWN_HOURS,
            daylight_ramp=k.DAYLIGHT_RAMP_HOURS,
        )
        self.front = AirFront(positive=self.values.air_mass(0) > 0, strength=0.0, start_hour=0)
        self.period: WeatherPeriod | None = None
        self.last_hour = 0
        self.periods_started = 0

    def _calendar(self, minutes: float) -> tuple[datetime.date, float]:
        total = self.start_minute_of_day + minutes
        days, minute_of_day = divmod(total, MINUTES_PER_DAY)
        return self.start_date + datetime.timedelta(
            days=int(days)
        ), minute_of_day / MINUTES_PER_HOUR

    def sample(self, minutes: float) -> WeatherSample:
        """The outdoor weather at a clock moment."""
        hours = minutes / MINUTES_PER_HOUR
        day, hour = self._calendar(minutes)
        values = self.values
        temperature = self.season.day_temperature(
            day, hour
        ) + k.AIR_MASS_TEMP_EFFECT_C * values.air_mass(hours)
        dawn, dusk = self.season.dawn_dusk(day)
        humidity = values.humidity(hours)
        wind = values.wind(hours)
        cloud = values.cloud(hours)
        precipitation = 0.0
        stage_name = None
        thunder = False
        stage = self.period.stage_at(hours) if self.period else None
        if stage is not None:
            stage_name = stage.name
            precipitation = stage.precipitation
            wind = max(wind, stage.wind)
            cloud = max(cloud, stage.cloud)
            humidity = max(humidity, k.STAGE_HUMIDITY_FLOOR)
            thunder = stage.thunder
        fog = k.FOG_BASE + k.FOG_DAY_SCALE * values.fog(day, hour, dawn)
        return WeatherSample(
            air_temperature=temperature,
            humidity=humidity,
            wind_intensity=wind,
            wind_angle=values.wind_angle(hours),
            cloud_intensity=cloud,
            precipitation_intensity=precipitation,
            precipitation_is_snow=temperature < k.SNOW_BELOW_C,
            fog_intensity=fog,
            daylight=values.daylight(hour, dawn, dusk),
            stage=stage_name,
            thunder=thunder,
        )

    def restore(self, minutes: float, front: AirFront | None, period: WeatherPeriod | None) -> None:
        """Resume from saved state at clock `minutes`; the hourly check continues from there."""
        self.last_hour = int(minutes // MINUTES_PER_HOUR)
        if front is None:
            front = AirFront(self.values.air_mass(self.last_hour) > 0, 0.0, 0)
        self.front = front
        self.period = period

    def advance_to(self, minutes: float) -> None:
        """Run the hourly front check for every hour boundary up to `minutes`."""
        target = int(minutes // MINUTES_PER_HOUR)
        while self.last_hour < target:
            self.last_hour += 1
            self._check_front(self.last_hour)

    def _check_front(self, hour: int) -> None:
        positive = self.values.air_mass(hour) > 0
        if positive == self.front.positive:
            return
        slope = abs(self.values.air_mass(hour + 1) - self.values.air_mass(hour - 1)) / 2
        strength = min(1.0, slope * k.FRONT_STRENGTH_GAIN)
        self.front = AirFront(positive=positive, strength=strength, start_hour=hour)
        self.start_period(hour, strength)

    def start_period(self, hour: int, strength: float) -> WeatherPeriod:
        """Begin a period for a front of `strength` (0 to 1) at a world-age hour."""
        day, _ = self._calendar(hour * MINUTES_PER_HOUR)
        rng = random.Random(
            period_seed(day.year, day.month - 1, day.day, self.offsets[0], self.offsets[1])
        )
        low, high = k.PERIOD_HOURS_RANGE
        rain_scale = k.MONTHLY_RAIN[day.month - 1] / k.PERIOD_MEAN_RAIN
        total = rng.uniform(low, high) * rain_scale * k.RAIN_TIME_MULTIPLIER
        tier = sum(strength >= bound for bound in k.STRENGTH_TIERS)
        templates = k.STAGE_TEMPLATES[tier]
        if self.sample(hour * MINUTES_PER_HOUR).air_temperature < k.SNOW_BELOW_C:
            templates = tuple(k.COLD_STORM_STAGE if t.name == "storm" else t for t in templates)
        self.period = WeatherPeriod.generate(rng, float(hour), total, templates, k.STAGE_JITTER)
        self.periods_started += 1
        logger.debug(f"Weather period starts at hour {hour}, strength {strength:.2f}.")
        return self.period


def _band_word(value: float, bands: tuple[tuple[float, str], ...]) -> str | None:
    """The word of the highest band whose exclusive lower bound `value` exceeds."""
    word = None
    for lower, name in bands:
        if value > lower:
            word = name
    return word


def wind_word(wind: float) -> str:
    return _band_word(wind, k.WIND_BANDS) or k.WIND_STILL_WORD


def cloud_word(cloud: float) -> str:
    return _band_word(cloud, k.CLOUD_BANDS) or k.CLOUD_BANDS[0][1]


def fog_word(fog: float) -> str | None:
    """The fog word, or None when the fog is too thin to mention."""
    if fog <= k.FOG_MENTION_ABOVE:
        return None
    if fog == k.FOG_VERY_THICK:
        return k.FOG_VERY_THICK_WORD
    return _band_word(fog, k.FOG_BANDS)


def temperature_word(celsius: float) -> str:
    return _band_word(celsius, k.TEMPERATURE_BANDS) or k.TEMPERATURE_BANDS[0][1]


def precipitation_phrase(stage: str | None, snow: bool) -> str:
    """What is falling, from the stage name; rain becomes snow when it snows."""
    if stage is None:
        return k.DRY_WORD
    rain_phrase, snow_phrase = k.STAGE_PHRASES[stage]
    return snow_phrase if snow else rain_phrase


def sheltered(indoors: bool) -> str:
    return "yes" if indoors else "no"


def describe_weather(sample: WeatherSample, indoors: bool) -> str:
    """The `[WEATHER]` block body: words only, never a number."""
    lines = [
        f"Sky: {cloud_word(sample.cloud_intensity)}",
        f"Precipitation: {precipitation_phrase(sample.stage, sample.precipitation_is_snow)}",
        f"Temperature: {temperature_word(sample.air_temperature)}",
        f"Wind: {wind_word(sample.wind_intensity)}",
    ]
    fog = fog_word(sample.fog_intensity)
    if fog:
        lines.append(f"Fog: {fog}")
    lines.append(f"Sheltered: {sheltered(indoors)}")
    return "\n".join(lines)


def weather_summary(sample: WeatherSample) -> str:
    """One short line for the player's panel."""
    parts = [precipitation_phrase(sample.stage, sample.precipitation_is_snow)]
    if parts[0] == k.DRY_WORD:
        parts = [cloud_word(sample.cloud_intensity)]
    parts.append(temperature_word(sample.air_temperature))
    return ", ".join(parts)


def weather_change_facts(before: WeatherSample, after: WeatherSample) -> list[str]:
    """Outcome facts for what changed between two samples; words only."""
    facts: list[str] = []
    was_falling = before.precipitation_intensity > 0
    is_falling = after.precipitation_intensity > 0
    if is_falling and not was_falling:
        facts.append(f"It starts to {'snow' if after.precipitation_is_snow else 'rain'}.")
    elif was_falling and not is_falling:
        facts.append(f"The {'snow' if before.precipitation_is_snow else 'rain'} stops.")
    elif was_falling and before.precipitation_is_snow != after.precipitation_is_snow:
        if after.precipitation_is_snow:
            facts.append("The rain turns to snow.")
        else:
            facts.append("The snow turns to rain.")
    if after.thunder and not before.thunder:
        facts.append("Thunder rolls overhead.")
    foggy_before = fog_word(before.fog_intensity) is not None
    foggy_after = fog_word(after.fog_intensity) is not None
    if foggy_before and not foggy_after:
        facts.append("The fog lifts.")
    elif foggy_after and not foggy_before:
        facts.append("Fog rolls in.")
    return facts
