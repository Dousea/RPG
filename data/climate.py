"""Climate configuration: seasons, noise, weather stages and word bands (spec 04)."""

from modules.weather import SeasonModel, StageTemplate

LATITUDE = 38  # spec 04
TEMP_MAX_C = 25  # spec 04
TEMP_MIN_C = 0  # spec 04
TEMP_DIFF = 7  # spec 04
SEASON_LAG_DAYS = 31  # spec 04
HIGH_NOON_HOUR = 12.5  # spec 04
SEASON_NOISE_SEEDS = (64, 128, 255)  # spec 04
MONTHLY_RAIN = (0.39, 0.35, 0.39, 0.40, 0.35, 0.37, 0.29, 0.26, 0.23, 0.23, 0.30, 0.32)  # spec 04
AIR_MASS_NOISE_FREQUENCY = 166  # spec 04
RAIN_TIME_MULTIPLIER = 1.0  # spec 04
FOG_SEED = 1984  # spec 04
FOG_BASE = 0.2  # spec 04
FOG_DAY_SCALE = 0.8  # spec 04
SIMPLEX_OFFSET_MAX = 8000  # spec 04
WIND_TO_KMH = 120  # spec 04
SNOW_BELOW_C = 0  # spec 04

INDOOR_POWERED_C = 22  # spec 06
INDOOR_PULL_BASE = 0.4  # spec 06
INDOOR_PULL_DAYLIGHT = 0.2  # spec 06
UPPER_FLOOR_DIFF_MULT = 0.85  # spec 06
UPPER_FLOOR_NIGHT_TERM = 0.2  # spec 06
WINDCHILL_TERMS = (13.12, 0.6215, 11.37, 0.16, 0.3965)  # spec 06: wind in km/h

# Our own tuning; the spec gives no values.
AXIAL_TILT_DEGREES = 23.44
EQUINOX_DAY = 80
DAILY_HIGH_AFTER_NOON_HOURS = 4  # spec 04: the daily high lags high noon
STAGE_HUMIDITY_FLOOR = 0.9
SEASON_NOISE_AMPLITUDE_C = 0.6
SEASON_NOISE_DAYS = 45
SEASON_PEAK_SOLSTICE_DAY = 172
DAYS_PER_YEAR = 365.25
AIR_MASS_TEMP_EFFECT_C = 3.0
HUMIDITY_NOISE_HOURS = 90
WIND_NOISE_HOURS = 40
WIND_ANGLE_NOISE_HOURS = 120
CLOUD_NOISE_HOURS = 60
WIND_BASE_MAX = 0.4
CLOUD_BASE_MAX = 0.6
DAYLIGHT_RAMP_HOURS = 1.0
FOG_PEAK_AFTER_DAWN_HOURS = 0.0
FOG_CLEAR_AFTER_DAWN_HOURS = 3.0
FRONT_STRENGTH_GAIN = 80.0
PERIOD_HOURS_RANGE = (24.0, 56.0)
PERIOD_MEAN_RAIN = 0.3
STAGE_JITTER = (0.8, 1.0)
STRENGTH_TIERS = (0.34, 0.67)

# Stage templates per strength tier: name, share of the period, intensity,
# wind, cloud, thunder.
_LOW = (
    StageTemplate("drizzle", 0.4, 0.15, 0.1, 0.6, False),
    StageTemplate("showers", 0.3, 0.35, 0.2, 0.7, False),
    StageTemplate("clearing", 0.3, 0.15, 0.15, 0.5, False),
)
_MID = (
    StageTemplate("showers", 0.2, 0.35, 0.2, 0.7, False),
    StageTemplate("moderate", 0.25, 0.5, 0.3, 0.8, False),
    StageTemplate("intermezzo", 0.1, 0.05, 0.2, 0.6, False),
    StageTemplate("heavy_precipitation", 0.25, 0.75, 0.45, 0.9, False),
    StageTemplate("clearing", 0.2, 0.15, 0.2, 0.5, False),
)
_HIGH = (
    StageTemplate("showers", 0.15, 0.35, 0.3, 0.8, False),
    StageTemplate("heavy_precipitation", 0.25, 0.75, 0.5, 0.9, False),
    StageTemplate("storm", 0.3, 1.0, 0.8, 1.0, True),
    StageTemplate("heavy_precipitation", 0.15, 0.75, 0.5, 0.9, False),
    StageTemplate("clearing", 0.15, 0.15, 0.3, 0.6, False),
)
STAGE_TEMPLATES = (_LOW, _MID, _HIGH)
COLD_STORM_STAGE = StageTemplate("blizzard", 0.3, 1.0, 0.8, 1.0, False)

SEASON_MODEL = SeasonModel(
    latitude=LATITUDE,
    temp_max=TEMP_MAX_C,
    temp_min=TEMP_MIN_C,
    temp_diff=TEMP_DIFF,
    season_lag_days=SEASON_LAG_DAYS,
    high_noon_hour=HIGH_NOON_HOUR,
    noise_seed=SEASON_NOISE_SEEDS[0],
    noise_amplitude=SEASON_NOISE_AMPLITUDE_C,
    noise_days=SEASON_NOISE_DAYS,
    solstice_day=SEASON_PEAK_SOLSTICE_DAY,
    days_per_year=DAYS_PER_YEAR,
    axial_tilt=AXIAL_TILT_DEGREES,
    equinox_day=EQUINOX_DAY,
    high_lag_hours=DAILY_HIGH_AFTER_NOON_HOURS,
)

INDOORS_BY_ZONE = {  # spec 04
    "zone_home": True,
    "zone_building": True,
    "zone_street": False,
    "zone_bodega": True,
    "zone_neighborhood": False,
    "zone_flat_vacant": True,  # spec 25
    "zone_flat_tenant": True,  # spec 25
    "zone_pharmacy": True,  # spec 25
    "zone_clinic": True,  # spec 25
    "zone_supermarket": True,  # spec 25
    "zone_hardware": True,  # spec 25
}

# Lower bounds are exclusive; the last band whose bound the value exceeds wins.
WIND_STILL_WORD = "still"
WIND_BANDS = ((0.05, "mild"), (0.25, "moderate"), (0.5, "strong"), (0.75, "storm-strength"))
CLOUD_BANDS = ((0.0, "clear skies"), (0.4, "some clouds"), (0.7, "overcast"))
FOG_MENTION_ABOVE = 0.2
FOG_BANDS = ((0.0, "light fog"), (0.75, "thick fog"))
FOG_VERY_THICK = 1.0
FOG_VERY_THICK_WORD = "very thick fog"
TEMPERATURE_BANDS = (
    (float("-inf"), "freezing"),
    (-10.0, "bitter cold"),
    (0.0, "cold"),
    (8.0, "chilly"),
    (15.0, "mild"),
    (22.0, "warm"),
    (29.0, "hot"),
)
STAGE_PHRASES = {
    "showers": ("rain showers", "snow showers"),
    "heavy_precipitation": ("heavy rain", "heavy snow"),
    "storm": ("a rain storm", "a snow storm"),
    "clearing": ("rain clearing", "snow clearing"),
    "moderate": ("steady rain", "steady snow"),
    "drizzle": ("light rain", "light snow"),
    "blizzard": ("a blizzard", "a blizzard"),
    "tropical_storm": ("a tropical storm", "a tropical storm"),
    "intermezzo": ("a lull in the rain", "a lull in the snow"),
}
DRY_WORD = "dry"
