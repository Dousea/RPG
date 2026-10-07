"""Weather model: samples, seasons, noise-driven values and fronts (weather).

Pure: every number a formula needs is passed in, so the same seed, date and
world age always give the same weather. Constants live in `data/climate.py`.
"""

import datetime
import math
import random
from dataclasses import dataclass

from modules.world import simplex

DEGREES_PER_HOUR_ANGLE = 15.0
HOURS_PER_DAY = 24


@dataclass(frozen=True)
class WeatherSample:
    """The weather at one moment, outdoors."""

    air_temperature: float
    humidity: float
    wind_intensity: float
    wind_angle: float
    cloud_intensity: float
    precipitation_intensity: float
    precipitation_is_snow: bool
    fog_intensity: float
    daylight: float
    stage: str | None = None
    thunder: bool = False


@dataclass(frozen=True)
class StageTemplate:
    """A stage of a front: its share of the period and its peak values."""

    name: str
    share: float
    intensity: float
    wind: float
    cloud: float
    thunder: bool


@dataclass(frozen=True)
class PeriodStage:
    name: str
    hours: float
    precipitation: float
    wind: float
    cloud: float
    thunder: bool


@dataclass(frozen=True)
class AirFront:
    """The air mass side last seen, and the strength of the flip that made it."""

    positive: bool
    strength: float
    start_hour: int


@dataclass(frozen=True)
class WeatherPeriod:
    """A timed run of stages a front brings, starting at a world-age hour."""

    start_hour: float
    stages: tuple[PeriodStage, ...]

    @property
    def end_hour(self) -> float:
        return self.start_hour + sum(stage.hours for stage in self.stages)

    def stage_at(self, hour: float) -> PeriodStage | None:
        if hour < self.start_hour:
            return None
        cursor = self.start_hour
        for stage in self.stages:
            cursor += stage.hours
            if hour < cursor:
                return stage
        return None

    @classmethod
    def generate(
        cls,
        rng: random.Random,
        start_hour: float,
        total_hours: float,
        templates: tuple[StageTemplate, ...],
        jitter: tuple[float, float],
    ) -> "WeatherPeriod":
        """Draw one period: each stage's intensity is its template's, jittered."""
        stages: list[PeriodStage] = []
        for template in templates:
            scale = rng.uniform(*jitter)
            stages.append(
                PeriodStage(
                    name=template.name,
                    hours=total_hours * template.share,
                    precipitation=template.intensity * scale,
                    wind=template.wind * scale,
                    cloud=template.cloud,
                    thunder=template.thunder,
                )
            )
        return cls(start_hour=start_hour, stages=tuple(stages))


def period_seed(year: int, month: int, day: int, offset_a: int, offset_b: int) -> int:
    """Seed for a period's generator; `month` is 0-based, `day` starts at 1."""
    return (
        (year - 1990) * 100000
        + month * day * 1234
        + (year - 1990) * month * 10000
        + (int(offset_b) - int(offset_a)) * day
    )


def simplex_offsets(seed: int, offset_max: int) -> tuple[int, int, int, int]:
    """The four noise offsets A to D, each from 0 to `offset_max`."""
    rng = random.Random(seed)
    a, b, c, d = (rng.randint(0, offset_max) for _ in range(4))
    return a, b, c, d


def _unit(value: float) -> float:
    """Map noise in [-1, 1] to [0, 1]."""
    return min(1.0, max(0.0, 0.5 + 0.5 * value))


@dataclass(frozen=True)
class SeasonModel:
    """Seasonal temperature curves and day length for a latitude."""

    latitude: float
    temp_max: float
    temp_min: float
    temp_diff: float
    season_lag_days: float
    high_noon_hour: float
    noise_seed: int
    noise_amplitude: float
    noise_days: float
    solstice_day: int
    days_per_year: float
    axial_tilt: float
    equinox_day: int
    high_lag_hours: float

    def day_mean_temperature(self, day: datetime.date) -> float:
        """Mean temperature of a day: a cosine that peaks `season_lag_days` after the solstice."""
        yday = day.timetuple().tm_yday
        middle = (self.temp_max + self.temp_min) / 2
        swing = (self.temp_max - self.temp_min) / 2 - self.noise_amplitude
        peak_day = self.solstice_day + self.season_lag_days
        seasonal = math.cos(2 * math.pi * (yday - peak_day) / self.days_per_year)
        noise = simplex.noise(self.noise_seed, yday / self.noise_days)
        return middle + swing * seasonal + self.noise_amplitude * noise

    def day_temperature(self, day: datetime.date, hour: float) -> float:
        """Temperature at an hour: the daily high comes `high_lag_hours` after high noon."""
        mean = self.day_mean_temperature(day)
        peak_hour = self.high_noon_hour + self.high_lag_hours
        return mean + (self.temp_diff / 2) * math.cos(
            2 * math.pi * (hour - peak_hour) / HOURS_PER_DAY
        )

    def day_length_hours(self, day: datetime.date) -> float:
        yday = day.timetuple().tm_yday
        declination = math.radians(
            self.axial_tilt * math.sin(2 * math.pi * (yday - self.equinox_day) / self.days_per_year)
        )
        cos_angle = -math.tan(math.radians(self.latitude)) * math.tan(declination)
        half_angle = math.degrees(math.acos(max(-1.0, min(1.0, cos_angle))))
        return 2 * half_angle / DEGREES_PER_HOUR_ANGLE

    def dawn_dusk(self, day: datetime.date) -> tuple[float, float]:
        half = self.day_length_hours(day) / 2
        return self.high_noon_hour - half, self.high_noon_hour + half


@dataclass(frozen=True)
class ClimateValues:
    """The noise-driven values of a world: air mass, humidity, wind, clouds, fog."""

    offsets: tuple[int, int, int, int]
    air_mass_hours: float
    humidity_hours: float
    wind_hours: float
    wind_angle_hours: float
    cloud_hours: float
    wind_base_max: float
    cloud_base_max: float
    fog_seed: int
    fog_peak_after_dawn: float
    fog_clear_after_dawn: float
    daylight_ramp: float

    def air_mass(self, hours: float) -> float:
        return simplex.noise(self.offsets[2], hours / self.air_mass_hours)

    def humidity(self, hours: float) -> float:
        return _unit(simplex.noise(self.offsets[3], hours / self.humidity_hours))

    def wind(self, hours: float) -> float:
        return _unit(simplex.noise(self.offsets[1], hours / self.wind_hours)) * self.wind_base_max

    def wind_angle(self, hours: float) -> float:
        return _unit(simplex.noise(self.offsets[0], hours / self.wind_angle_hours)) * 360.0

    def cloud(self, hours: float) -> float:
        return (
            _unit(simplex.noise(self.offsets[2] + 1, hours / self.cloud_hours))
            * self.cloud_base_max
        )

    def day_fog_strength(self, day: datetime.date) -> float:
        """The day's fog strength, drawn from a generator reseeded each day."""
        return random.Random(self.fog_seed + day.toordinal()).random()

    def fog(self, day: datetime.date, hour: float, dawn: float) -> float:
        """Fog strength at an hour: it builds to dawn and burns off after it."""
        since = hour - dawn
        if since < -self.fog_clear_after_dawn or since > self.fog_clear_after_dawn:
            return 0.0
        profile = 1.0 - abs(since - self.fog_peak_after_dawn) / self.fog_clear_after_dawn
        return self.day_fog_strength(day) * max(0.0, profile)

    def daylight(self, hour: float, dawn: float, dusk: float) -> float:
        ramp = self.daylight_ramp
        rising = (hour - (dawn - ramp / 2)) / ramp
        setting = ((dusk + ramp / 2) - hour) / ramp
        return min(1.0, max(0.0, min(rising, setting)))
