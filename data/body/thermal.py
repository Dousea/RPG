"""Body temperature, wetness and cold constants (body-temperature).

Per-frame rates keep their source value. The thermoregulator, thermal damage
tick and sneeze timer are real-frame rates (112.5 frames per game minute); the
wetness walk, the cold course and the catch counter's rise are game-frame
rates (180 per game minute). Per-minute forms go through `modules/units.py`.
"""

from dataclasses import dataclass
from enum import StrEnum

from modules import units
from modules.body.parts import BodyPart


class Metabolic(StrEnum):
    DEFAULT = "default"
    LIGHT_DOMESTIC = "light_domestic"
    HEAVY_DOMESTIC = "heavy_domestic"
    DEFAULT_EXERCISE = "default_exercise"
    USING_TOOLS = "using_tools"
    LIGHT_WORK = "light_work"
    MEDIUM_WORK = "medium_work"
    HEAVY_WORK = "heavy_work"
    WALKING_2KMH = "walking_2kmh"
    WALKING_5KMH = "walking_5kmh"
    RUNNING_10KMH = "running_10kmh"
    RUNNING_15KMH = "running_15kmh"
    FITNESS = "fitness"
    FITNESS_HEAVY = "fitness_heavy"


METABOLICS: dict[Metabolic, float] = {  # body-temperature: in met
    Metabolic.DEFAULT: 1.5,
    Metabolic.LIGHT_DOMESTIC: 1.6,
    Metabolic.HEAVY_DOMESTIC: 2.0,
    Metabolic.DEFAULT_EXERCISE: 3.0,
    Metabolic.USING_TOOLS: 2.5,
    Metabolic.LIGHT_WORK: 3.2,
    Metabolic.MEDIUM_WORK: 3.9,
    Metabolic.HEAVY_WORK: 6.0,
    Metabolic.WALKING_2KMH: 1.9,
    Metabolic.WALKING_5KMH: 3.1,
    Metabolic.RUNNING_10KMH: 6.9,
    Metabolic.RUNNING_15KMH: 9.5,
    Metabolic.FITNESS: 6.0,
    Metabolic.FITNESS_HEAVY: 9.0,
}
METABOLIC_MAX = 10.3  # body-temperature

# Set point and metabolic rate
CORE_SET_POINT_C = 37.0  # body-temperature
SICKNESS_SET_POINT_MULT = 2.0  # body-temperature: dormant, nothing writes sickness
THERMO_SUBSTEP_FRAMES = 10  # body-temperature: real frames
METABOLIC_RATE_INC_PER_FRAME = 0.001  # body-temperature
METABOLIC_RATE_DEC_PER_FRAME = 0.0004  # body-temperature
CARRY_RATIO_COEFF = 0.35  # body-temperature
EXERCISE_TERM_MET = 3.0  # body-temperature: DefaultExercise times energy
METABOLIC_REAL_BASE = 0.2  # body-temperature
METABOLIC_REAL_ENERGY = 0.8  # body-temperature
MOVEMENT_MODIFIER = {
    2: 0.66,
    3: 0.33,
    4: 0.0,
}  # body-temperature: Hypothermia or Hyperthermia level
ENERGY_LINEAR = 0.4  # body-temperature
ENERGY_QUADRATIC = 0.6  # body-temperature
ENERGY_HUNGER_MIX = 0.6  # body-temperature
ENERGY_FATIGUE_MIX = 0.4  # body-temperature

# Clothing per node
TRUE_INSULATION_LINEAR = 2.0  # body-temperature
TRUE_INSULATION_CUBIC = 0.5  # body-temperature
TRUE_WINDRESIST_QUADRATIC = 0.5  # body-temperature
LAYER_BASE = 0.05  # body-temperature: per layer, for insulation and wind resistance
CLOTHING_WET_INSULATION = 0.75  # body-temperature
CLOTHING_WET_WIND = 0.45  # body-temperature
CONDITION_BASE = 0.5  # body-temperature
CONDITION_SCALE = 0.5  # body-temperature

# Heat per node
NODE_EXCHANGE_FACTOR = 0.3  # body-temperature
BODY_WET_COOLING = 0.75  # body-temperature
BODY_WET_WARMING_DIVISOR = 3.0  # body-temperature
RESPONSE_GAIN = 1.5  # body-temperature: primary and secondary shiver and cool gain
PRIMARY_FLUIDS_BASE = 0.2  # body-temperature
PRIMARY_FLUIDS_SCALE = 0.8  # body-temperature
PRIMARY_HEATMOD_BASE = 0.1  # body-temperature
PRIMARY_HEATMOD_SCALE = 0.9  # body-temperature
PRIM_HEAT_MOD_RANGE_C = 2.0  # body-temperature: set point band
PRIM_HEAT_MOD_DIVISOR = 4.0  # body-temperature
SECONDARY_SWEAT_MET = 10.3 * 0.75  # body-temperature
SECONDARY_FLUIDS_BASE = 0.1  # body-temperature
SECONDARY_FLUIDS_SCALE = 0.9  # body-temperature
SECONDARY_HUMIDITY_BASE = 0.85  # body-temperature
SECONDARY_HUMIDITY_SCALE = 0.15  # body-temperature
SHIVER_ENERGY_BASE = 0.2  # body-temperature
SHIVER_ENERGY_SCALE = 0.8  # body-temperature
SECONDARY_ENERGY_BASE = 0.1  # body-temperature
SECONDARY_ENERGY_SCALE = 0.9  # body-temperature
HUMIDITY_REFERENCE = 0.5  # body-temperature
WEIGHT_REFERENCE_KG = 75  # body-temperature
WEIGHT_OFFSET = 0.5  # body-temperature
WEIGHT_SCALE = 0.666  # body-temperature
WEIGHT_FITNESS_MULT = 0.2  # body-temperature
DEFAULT_BODY_WEIGHT_KG = 80  # body-temperature

# The core
BODY_HEAT_PER_FRAME = 0.00025  # body-temperature
CORE_MIN_C = 20.0  # body-temperature
CORE_MAX_C = 42.0  # body-temperature
STAT_MIN_C = 20.0  # body-temperature
STAT_MAX_C = 40.0  # body-temperature
CORE_STAT_TOLERANCE = 0.001  # body-temperature
CORE_ABOVE_SET_DIV = 2.0  # body-temperature
CORE_BELOW_SET_DIV = 4.0  # body-temperature
BODY_HEAT_NEAR_GAP = 1.0  # body-temperature
BODY_HEAT_NEAR_MULT = 0.8  # body-temperature
BODY_HEAT_FAR_BASE = -0.8  # body-temperature
BODY_HEAT_FAR_SLOPE = 0.2  # body-temperature
BODY_HEAT_FAR_RANGE = 10.0  # body-temperature
BODY_HEAT_FAR_MAX_GAP = 11.0  # body-temperature
CACHE_COUNTER_PER_FRAME = 1.6  # body-temperature
CACHE_COUNTER_LIMIT = 100  # body-temperature

# The skin
SKIN_REFERENCE_C = 33.0  # body-temperature
SKIN_BASE_BELOW_CORE_C = 4.0  # body-temperature
SKIN_MIN_BELOW_CORE_C = 20.0  # body-temperature
SKIN_COOL_RANGE_C = 12.0  # body-temperature
SKIN_WARM_RANGE_C = 4.0  # body-temperature
SKIN_WARM_INSULATION_MULT = 0.5  # body-temperature
SKIN_DIST_BASE = 0.4  # body-temperature
SKIN_DIST_SCALE = 0.6  # body-temperature
SKIN_MIN_WARM_RANGE_C = 4.0  # body-temperature
SKIN_MIN_WARM_SPAN_C = 6.0  # body-temperature
SKIN_MAX_MARGIN_C = 0.25  # body-temperature
SKIN_RATE_PER_FRAME = 0.0025  # body-temperature
SKIN_FAST_FACTOR = 3.0  # body-temperature
SKIN_RATE_CAP = 1.0  # body-temperature

# Thermal damage
THERMAL_TICK_FRAMES = 2  # body-temperature: real frames
THERMAL_TICK_SECONDS = 1.07  # body-temperature: game seconds a tick spans
THERMAL_DAMAGE_COLD_AIR_C = 0  # body-temperature: wind-chill air, Hypothermia 4
THERMAL_DAMAGE_HOT_AIR_C = 37  # body-temperature: wind-chill air, Hyperthermia 4
THERMAL_COLD_BASE_SECONDS = 120  # body-temperature
THERMAL_COLD_SPAN_SECONDS = 480  # body-temperature
THERMAL_COLD_CORE_FLOOR_C = 20  # body-temperature
THERMAL_COLD_CORE_RANGE_C = 5  # body-temperature
THERMAL_COLD_AIR_RANGE_C = 10  # body-temperature
THERMAL_COLD_GROWTH = 1.2  # body-temperature
THERMAL_DURATION_DIV = 7200  # body-temperature: game seconds
THERMAL_HOT_CORE_C = 41  # body-temperature
THERMAL_HOT_BASE_SECONDS = 120  # body-temperature
THERMAL_HOT_SPAN_SECONDS = 480  # body-temperature
THERMAL_HOT_AIR_RANGE_C = 8  # body-temperature
THERMAL_HOT_CAP = 0.3  # body-temperature
THERMAL_FALL_PER_TICK = 0.011111  # body-temperature
HEALTH_CAP_BASE = 100  # body-temperature: health cap is 100 - 100 x stage
HEALTH_CAP_PER_STAGE = 100  # body-temperature

# Body multipliers
ENERGY_MULT_COEFFS = (0.05, 0.1)  # body-temperature: p squared, s squared
FLUIDS_MULT_COEFFS = (0.25, 3.75)  # body-temperature
FATIGUE_COLD_COEFFS = (0.25, 0.75)  # body-temperature
FATIGUE_HOT_COEFFS = (0.25, 1.75)  # body-temperature


@dataclass(frozen=True)
class Node:
    """Skin surface and distance to core of one body part."""

    skin_surface: float
    distance_to_core: float


THERMAL_NODES: dict[BodyPart, Node] = {  # body-temperature
    BodyPart.TORSO_UPPER: Node(0.18, 0.0),
    BodyPart.TORSO_LOWER: Node(0.12, 0.05),
    BodyPart.HEAD: Node(0.08, 0.05),
    BodyPart.NECK: Node(0.02, 0.02),
    BodyPart.GROIN: Node(0.06, 0.3),
    BodyPart.UPPERARM_L: Node(0.045, 0.3),
    BodyPart.UPPERARM_R: Node(0.045, 0.3),
    BodyPart.FOREARM_L: Node(0.035, 0.6),
    BodyPart.FOREARM_R: Node(0.035, 0.6),
    BodyPart.HAND_L: Node(0.01, 0.8),
    BodyPart.HAND_R: Node(0.01, 0.8),
    BodyPart.UPPERLEG_L: Node(0.09, 0.45),
    BodyPart.UPPERLEG_R: Node(0.09, 0.45),
    BodyPart.LOWERLEG_L: Node(0.07, 0.75),
    BodyPart.LOWERLEG_R: Node(0.07, 0.75),
    BodyPart.FOOT_L: Node(0.02, 1.0),
    BodyPart.FOOT_R: Node(0.02, 1.0),
}

# Wetness (per-frame source rates, applied once per game minute)
RAIN_MIN_INTENSITY = 0.1  # body-temperature
DRYING_BASE_RATE = 0.1  # body-temperature
DRYING_REFERENCE_C = 5  # body-temperature
DRYING_PER_DEGREE = 0.1  # body-temperature: (T - 5) / 10
WETNESS_INCREASE_per_min = units.per_minute_from_frame(0.015)  # body-temperature
WETNESS_DECREASE_per_min = units.per_minute_from_frame(0.01)  # body-temperature
WETNESS_HYSTERESIS_WET = (
    25  # body-temperature: sweat reaches clothing at or above this skin wetness
)
WETNESS_HYSTERESIS_DRY = 50  # body-temperature: skin dries clothing at or below this skin wetness
PERSPIRATION_MIN = 0.1  # body-temperature
PERSPIRATION_DIST_BASE = 0.2  # body-temperature
PERSPIRATION_DIST_SCALE = 0.8  # body-temperature
EVAPORATION_SKIN_FLOOR_C = 20  # body-temperature
EVAPORATION_SKIN_RANGE_C = 22  # body-temperature
SWEAT_OUTDOOR_BASE = 0.4  # body-temperature
SWEAT_OUTDOOR_SCALE = 0.6  # body-temperature
SWEAT_OUTDOOR_OFFSET_C = 10  # body-temperature
SWEAT_OUTDOOR_SPAN_C = 20  # body-temperature
LAYER_SOAK_MAX = 100  # body-temperature
LAYER_DIVIDER = 2  # body-temperature: doubles after each layer that takes the delta
SKIN_RAIN_INNER_MIN = 50  # body-temperature
SKIN_DRY_INNER_MAX = 50  # body-temperature
BODY_MERGE_FACTOR = 0.1  # body-temperature: net 0.9 x the mean change per frame

# Colds
CATCH_COLD_NODE_WEIGHTS: dict[BodyPart, float] = {  # body-temperature: others 1
    BodyPart.NECK: 8,
    BodyPart.TORSO_UPPER: 16,
    BodyPart.HEAD: 4,
}
COLD_SKIN_BELOW_C = 33  # body-temperature
COLD_SKIN_FLOOR_C = 20  # body-temperature
COLD_SKIN_RANGE_C = 13  # body-temperature
COLD_NODE_FACTOR = 0.25  # body-temperature
WET_CLOTHING_FROM = 0.5  # body-temperature
HYPOTHERMIA_DELTA_FROM_LEVEL = 1  # body-temperature: the delta is multiplied above this level
CATCH_COLD_DELTA_MIN = 0.1  # body-temperature
CATCH_COLD_INCREASE_per_min = units.per_minute_from_frame(
    0.003
)  # body-temperature: per unit of delta
CATCH_COLD_DECREASE_per_min = units.per_minute_from_real_frame(0.175)  # body-temperature
CATCH_COLD_THRESHOLD = 100  # body-temperature
COLD_START_STRENGTH = 20  # body-temperature
COLD_STRENGTH_MAX = 100  # body-temperature
COLD_PROGRESSION_per_min = units.per_minute_from_frame(0.0112)  # body-temperature
COLD_REDUCTION_per_min = units.per_minute_from_frame(0.005)  # body-temperature
COLD_REDUCTION_STRENGTH_MULT = 2  # body-temperature: strength falls twice as fast
COLD_RECOVER_FATIGUE_MAX = 0.5  # body-temperature
COLD_RECOVER_HUNGER_MAX = 0.25  # body-temperature
COLD_RECOVER_THIRST_MAX = 0.25  # body-temperature
SNEEZE_FRAMES_PER_MIN = units.real_frames_per_minute()  # body-temperature
SNEEZE_MIN_LEVEL = 2  # body-temperature: Has a Cold level
SNEEZE_TIMER_FRAMES = {2: (600, 800), 3: (300, 600), 4: (200, 300)}  # body-temperature
SNEEZE_COIN_SIDES = 100  # body-temperature
SNEEZE_COIN_ABOVE = 50  # body-temperature: a roll above this is a sneeze
SNEEZE_OR_COUGH_ACTIVE_FRAMES = 25  # body-temperature
SNEEZE_NOISE = (20, 25)  # body-temperature: radius in tiles, volume; nothing hears it yet
COUGH_NOISE = (35, 40)  # body-temperature
SNEEZE_FACT = "{name} sneezes."
COUGH_FACT = "{name} coughs."
