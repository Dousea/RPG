"""Climate engine: weather for any moment, and the hourly front check (spec 04)."""

import datetime
import logging
import random
from dataclasses import dataclass

from data.world import climate as climate_k
from data.world.clock import MINUTES_PER_DAY, MINUTES_PER_HOUR
from modules.world.weather import (
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
        self.offsets = simplex_offsets(seed, climate_k.SIMPLEX_OFFSET_MAX)
        self.season = climate_k.SEASON_MODEL
        self.values = ClimateValues(
            offsets=self.offsets,
            air_mass_hours=climate_k.AIR_MASS_NOISE_FREQUENCY,
            humidity_hours=climate_k.HUMIDITY_NOISE_HOURS,
            wind_hours=climate_k.WIND_NOISE_HOURS,
            wind_angle_hours=climate_k.WIND_ANGLE_NOISE_HOURS,
            cloud_hours=climate_k.CLOUD_NOISE_HOURS,
            wind_base_max=climate_k.WIND_BASE_MAX,
            cloud_base_max=climate_k.CLOUD_BASE_MAX,
            fog_seed=climate_k.FOG_SEED,
            fog_peak_after_dawn=climate_k.FOG_PEAK_AFTER_DAWN_HOURS,
            fog_clear_after_dawn=climate_k.FOG_CLEAR_AFTER_DAWN_HOURS,
            daylight_ramp=climate_k.DAYLIGHT_RAMP_HOURS,
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
        ) + climate_k.AIR_MASS_TEMP_EFFECT_C * values.air_mass(hours)
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
            humidity = max(humidity, climate_k.STAGE_HUMIDITY_FLOOR)
            thunder = stage.thunder
        fog = climate_k.FOG_BASE + climate_k.FOG_DAY_SCALE * values.fog(day, hour, dawn)
        return WeatherSample(
            air_temperature=temperature,
            humidity=humidity,
            wind_intensity=wind,
            wind_angle=values.wind_angle(hours),
            cloud_intensity=cloud,
            precipitation_intensity=precipitation,
            precipitation_is_snow=temperature < climate_k.SNOW_BELOW_C,
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
        strength = min(1.0, slope * climate_k.FRONT_STRENGTH_GAIN)
        self.front = AirFront(positive=positive, strength=strength, start_hour=hour)
        self.start_period(hour, strength)

    def start_period(self, hour: int, strength: float) -> WeatherPeriod:
        """Begin a period for a front of `strength` (0 to 1) at a world-age hour."""
        day, _ = self._calendar(hour * MINUTES_PER_HOUR)
        rng = random.Random(
            period_seed(day.year, day.month - 1, day.day, self.offsets[0], self.offsets[1])
        )
        low, high = climate_k.PERIOD_HOURS_RANGE
        rain_scale = climate_k.MONTHLY_RAIN[day.month - 1] / climate_k.PERIOD_MEAN_RAIN
        total = rng.uniform(low, high) * rain_scale * climate_k.RAIN_TIME_MULTIPLIER
        tier = sum(strength >= bound for bound in climate_k.STRENGTH_TIERS)
        templates = climate_k.STAGE_TEMPLATES[tier]
        if self.sample(hour * MINUTES_PER_HOUR).air_temperature < climate_k.SNOW_BELOW_C:
            templates = tuple(
                climate_k.COLD_STORM_STAGE if t.name == "storm" else t for t in templates
            )
        self.period = WeatherPeriod.generate(
            rng, float(hour), total, templates, climate_k.STAGE_JITTER
        )
        self.periods_started += 1
        logger.debug(f"Weather period starts at hour {hour}, strength {strength:.2f}.")
        return self.period


def felt_air_temperature(
    temperature: float, *, indoors: bool, floor: int, power_on: bool, daylight: float
) -> float:
    """The air temperature a body feels (spec 06).

    `daylight` is the outdoor daylight (0 to 1); the night term is its complement.
    """
    if not indoors:
        return temperature
    if power_on:
        return climate_k.INDOOR_POWERED_C
    pull = climate_k.INDOOR_PULL_BASE + climate_k.INDOOR_PULL_DAYLIGHT * daylight
    difference = temperature - climate_k.INDOOR_POWERED_C
    if difference <= 0:
        mult = climate_k.UPPER_FLOOR_DIFF_MULT if floor >= 1 else 1.0
        return temperature - difference * pull * mult
    if floor >= 1:
        return temperature - difference * (pull + climate_k.UPPER_FLOOR_NIGHT_TERM * (1 - daylight))
    return temperature - difference * climate_k.UPPER_FLOOR_DIFF_MULT * pull


def wind_chill_temperature(temperature: float, wind_kmh: float) -> float:
    """The wind-chill temperature: the formula's value, or the temperature if that is lower."""
    a, b, c, d, e = climate_k.WINDCHILL_TERMS
    wind = wind_kmh**d
    return min(a + b * temperature - c * wind + e * temperature * wind, temperature)


@dataclass(frozen=True)
class FeltAir:
    """The air a body feels: still air, and the air with wind chill."""

    still_c: float
    wind_chill_c: float

    @property
    def windchill_amount(self) -> float:
        """How many degrees colder the wind makes it; 0 indoors."""
        return max(0.0, self.still_c - self.wind_chill_c)


def felt_air(
    temperature: float,
    wind_kmh: float,
    *,
    indoors: bool,
    floor: int,
    power_on: bool,
    daylight: float,
) -> FeltAir:
    """Still and wind-chill felt air; indoors the two are equal."""
    still = felt_air_temperature(
        temperature, indoors=indoors, floor=floor, power_on=power_on, daylight=daylight
    )
    if indoors:
        return FeltAir(still, still)
    return FeltAir(still, wind_chill_temperature(still, wind_kmh))


def _band_word(value: float, bands: tuple[tuple[float, str], ...]) -> str | None:
    """The word of the highest band whose exclusive lower bound `value` exceeds."""
    word = None
    for lower, name in bands:
        if value > lower:
            word = name
    return word


def wind_word(wind: float) -> str:
    return _band_word(wind, climate_k.WIND_BANDS) or climate_k.WIND_STILL_WORD


def cloud_word(cloud: float) -> str:
    return _band_word(cloud, climate_k.CLOUD_BANDS) or climate_k.CLOUD_BANDS[0][1]


def fog_word(fog: float) -> str | None:
    """The fog word, or None when the fog is too thin to mention."""
    if fog <= climate_k.FOG_MENTION_ABOVE:
        return None
    if fog == climate_k.FOG_VERY_THICK:
        return climate_k.FOG_VERY_THICK_WORD
    return _band_word(fog, climate_k.FOG_BANDS)


def temperature_word(celsius: float) -> str:
    return _band_word(celsius, climate_k.TEMPERATURE_BANDS) or climate_k.TEMPERATURE_BANDS[0][1]


def precipitation_phrase(stage: str | None, snow: bool) -> str:
    """What is falling, from the stage name; rain becomes snow when it snows."""
    if stage is None:
        return climate_k.DRY_WORD
    rain_phrase, snow_phrase = climate_k.STAGE_PHRASES[stage]
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
    if parts[0] == climate_k.DRY_WORD:
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
