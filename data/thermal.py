"""Body temperature, wetness and cold constants (spec 06).

Per-frame rates keep their source value. The thermoregulator, thermal damage
tick and sneeze timer are real-frame rates (112.5 frames per game minute); the
wetness walk, the cold course and the catch counter's rise are game-frame
rates (180 per game minute). Per-minute forms go through `modules/units.py`.
"""

from dataclasses import dataclass
from enum import StrEnum

from modules.body import BodyPart
from modules.units import per_minute_from_frame, per_minute_from_real_frame, real_frames_per_minute


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


METABOLICS: dict[Metabolic, float] = {  # spec 06, in met
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
METABOLIC_MAX = 10.3  # spec 06

# Set point and metabolic rate
CORE_SET_POINT_C = 37.0  # spec 06
SICKNESS_SET_POINT_MULT = 2.0  # spec 06: dormant, nothing writes sickness
THERMO_SUBSTEP_FRAMES = 10  # spec 06: real frames
METABOLIC_RATE_INC_PER_FRAME = 0.001  # spec 06
METABOLIC_RATE_DEC_PER_FRAME = 0.0004  # spec 06
CARRY_RATIO_COEFF = 0.35  # spec 06
EXERCISE_TERM_MET = 3.0  # spec 06: DefaultExercise times energy
METABOLIC_REAL_BASE = 0.2  # spec 06
METABOLIC_REAL_ENERGY = 0.8  # spec 06
MOVEMENT_MODIFIER = {2: 0.66, 3: 0.33, 4: 0.0}  # spec 06: Hypothermia or Hyperthermia level
ENERGY_LINEAR = 0.4  # spec 06
ENERGY_QUADRATIC = 0.6  # spec 06
ENERGY_HUNGER_MIX = 0.6  # spec 06
ENERGY_FATIGUE_MIX = 0.4  # spec 06

# Clothing per node
TRUE_INSULATION_LINEAR = 2.0  # spec 06
TRUE_INSULATION_CUBIC = 0.5  # spec 06
TRUE_WINDRESIST_QUADRATIC = 0.5  # spec 06
LAYER_BASE = 0.05  # spec 06: per layer, for insulation and wind resistance
CLOTHING_WET_INSULATION = 0.75  # spec 06
CLOTHING_WET_WIND = 0.45  # spec 06
CONDITION_BASE = 0.5  # spec 06
CONDITION_SCALE = 0.5  # spec 06

# Heat per node
NODE_EXCHANGE_FACTOR = 0.3  # spec 06
BODY_WET_COOLING = 0.75  # spec 06
BODY_WET_WARMING_DIVISOR = 3.0  # spec 06
RESPONSE_GAIN = 1.5  # spec 06: primary and secondary shiver and cool gain
PRIMARY_FLUIDS_BASE = 0.2  # spec 06
PRIMARY_FLUIDS_SCALE = 0.8  # spec 06
PRIMARY_HEATMOD_BASE = 0.1  # spec 06
PRIMARY_HEATMOD_SCALE = 0.9  # spec 06
PRIM_HEAT_MOD_RANGE_C = 2.0  # spec 06: set point band
PRIM_HEAT_MOD_DIVISOR = 4.0  # spec 06
SECONDARY_SWEAT_MET = 10.3 * 0.75  # spec 06
SECONDARY_FLUIDS_BASE = 0.1  # spec 06
SECONDARY_FLUIDS_SCALE = 0.9  # spec 06
SECONDARY_HUMIDITY_BASE = 0.85  # spec 06
SECONDARY_HUMIDITY_SCALE = 0.15  # spec 06
SHIVER_ENERGY_BASE = 0.2  # spec 06
SHIVER_ENERGY_SCALE = 0.8  # spec 06
SECONDARY_ENERGY_BASE = 0.1  # spec 06
SECONDARY_ENERGY_SCALE = 0.9  # spec 06
HUMIDITY_REFERENCE = 0.5  # spec 06
WEIGHT_REFERENCE_KG = 75  # spec 06
WEIGHT_OFFSET = 0.5  # spec 06
WEIGHT_SCALE = 0.666  # spec 06
WEIGHT_FITNESS_MULT = 0.2  # spec 06
DEFAULT_BODY_WEIGHT_KG = 80  # spec 06
FITNESS_STAT_STUB = 0.0  # spec 06: Fitness stat until skills land

# The core
BODY_HEAT_PER_FRAME = 0.00025  # spec 06
CORE_MIN_C = 20.0  # spec 06
CORE_MAX_C = 42.0  # spec 06
STAT_MIN_C = 20.0  # spec 06
STAT_MAX_C = 40.0  # spec 06
CORE_STAT_TOLERANCE = 0.001  # spec 06
CORE_ABOVE_SET_DIV = 2.0  # spec 06
CORE_BELOW_SET_DIV = 4.0  # spec 06
BODY_HEAT_NEAR_GAP = 1.0  # spec 06
BODY_HEAT_NEAR_MULT = 0.8  # spec 06
BODY_HEAT_FAR_BASE = -0.8  # spec 06
BODY_HEAT_FAR_SLOPE = 0.2  # spec 06
BODY_HEAT_FAR_RANGE = 10.0  # spec 06
BODY_HEAT_FAR_MAX_GAP = 11.0  # spec 06
CACHE_COUNTER_PER_FRAME = 1.6  # spec 06
CACHE_COUNTER_LIMIT = 100  # spec 06

# The skin
SKIN_REFERENCE_C = 33.0  # spec 06
SKIN_BASE_BELOW_CORE_C = 4.0  # spec 06
SKIN_MIN_BELOW_CORE_C = 20.0  # spec 06
SKIN_COOL_RANGE_C = 12.0  # spec 06
SKIN_WARM_RANGE_C = 4.0  # spec 06
SKIN_WARM_INSULATION_MULT = 0.5  # spec 06
SKIN_DIST_BASE = 0.4  # spec 06
SKIN_DIST_SCALE = 0.6  # spec 06
SKIN_MIN_WARM_RANGE_C = 4.0  # spec 06
SKIN_MIN_WARM_SPAN_C = 6.0  # spec 06
SKIN_MAX_MARGIN_C = 0.25  # spec 06
SKIN_RATE_PER_FRAME = 0.0025  # spec 06
SKIN_FAST_FACTOR = 3.0  # spec 06
SKIN_RATE_CAP = 1.0  # spec 06

# Thermal damage
THERMAL_TICK_FRAMES = 2  # spec 06: real frames
THERMAL_TICK_SECONDS = 1.07  # spec 06: game seconds a tick spans
THERMAL_DAMAGE_COLD_AIR_C = 0  # spec 06: wind-chill air, Hypothermia 4
THERMAL_DAMAGE_HOT_AIR_C = 37  # spec 06: wind-chill air, Hyperthermia 4
THERMAL_COLD_BASE_SECONDS = 120  # spec 06
THERMAL_COLD_SPAN_SECONDS = 480  # spec 06
THERMAL_COLD_CORE_FLOOR_C = 20  # spec 06
THERMAL_COLD_CORE_RANGE_C = 5  # spec 06
THERMAL_COLD_AIR_RANGE_C = 10  # spec 06
THERMAL_COLD_GROWTH = 1.2  # spec 06
THERMAL_DURATION_DIV = 7200  # spec 06: game seconds
THERMAL_HOT_CORE_C = 41  # spec 06
THERMAL_HOT_BASE_SECONDS = 120  # spec 06
THERMAL_HOT_SPAN_SECONDS = 480  # spec 06
THERMAL_HOT_AIR_RANGE_C = 8  # spec 06
THERMAL_HOT_CAP = 0.3  # spec 06
THERMAL_FALL_PER_TICK = 0.011111  # spec 06
HEALTH_CAP_BASE = 100  # spec 06: health cap is 100 - 100 x stage
HEALTH_CAP_PER_STAGE = 100  # spec 06

# Body multipliers
ENERGY_MULT_COEFFS = (0.05, 0.1)  # spec 06: p squared, s squared
FLUIDS_MULT_COEFFS = (0.25, 3.75)  # spec 06
FATIGUE_COLD_COEFFS = (0.25, 0.75)  # spec 06
FATIGUE_HOT_COEFFS = (0.25, 1.75)  # spec 06


@dataclass(frozen=True)
class Node:
    """Skin surface and distance to core of one body part."""

    skin_surface: float
    distance_to_core: float


THERMAL_NODES: dict[BodyPart, Node] = {  # spec 06
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
RAIN_MIN_INTENSITY = 0.1  # spec 06
DRYING_BASE_RATE = 0.1  # spec 06
DRYING_REFERENCE_C = 5  # spec 06
DRYING_PER_DEGREE = 0.1  # spec 06: (T - 5) / 10
WETNESS_INCREASE_per_min = per_minute_from_frame(0.015)  # spec 06
WETNESS_DECREASE_per_min = per_minute_from_frame(0.01)  # spec 06
WETNESS_HYSTERESIS_WET = 25  # spec 06: sweat reaches clothing at or above this skin wetness
WETNESS_HYSTERESIS_DRY = 50  # spec 06: skin dries clothing at or below this skin wetness
PERSPIRATION_MIN = 0.1  # spec 06
PERSPIRATION_DIST_BASE = 0.2  # spec 06
PERSPIRATION_DIST_SCALE = 0.8  # spec 06
EVAPORATION_SKIN_FLOOR_C = 20  # spec 06
EVAPORATION_SKIN_RANGE_C = 22  # spec 06
SWEAT_OUTDOOR_BASE = 0.4  # spec 06
SWEAT_OUTDOOR_SCALE = 0.6  # spec 06
SWEAT_OUTDOOR_OFFSET_C = 10  # spec 06
SWEAT_OUTDOOR_SPAN_C = 20  # spec 06
LAYER_SOAK_MAX = 100  # spec 06
LAYER_DIVIDER = 2  # spec 06: doubles after each layer that takes the delta
SKIN_RAIN_INNER_MIN = 50  # spec 06
SKIN_DRY_INNER_MAX = 50  # spec 06
BODY_MERGE_FACTOR = 0.1  # spec 06: net 0.9 x the mean change per frame

# Colds
CATCH_COLD_NODE_WEIGHTS: dict[BodyPart, float] = {  # spec 06: others 1
    BodyPart.NECK: 8,
    BodyPart.TORSO_UPPER: 16,
    BodyPart.HEAD: 4,
}
COLD_SKIN_BELOW_C = 33  # spec 06
COLD_SKIN_FLOOR_C = 20  # spec 06
COLD_SKIN_RANGE_C = 13  # spec 06
COLD_NODE_FACTOR = 0.25  # spec 06
WET_CLOTHING_FROM = 0.5  # spec 06
HYPOTHERMIA_DELTA_FROM_LEVEL = 1  # spec 06: the delta is multiplied above this level
CATCH_COLD_DELTA_MIN = 0.1  # spec 06
CATCH_COLD_INCREASE_per_min = per_minute_from_frame(0.003)  # spec 06: per unit of delta
CATCH_COLD_DECREASE_per_min = per_minute_from_real_frame(0.175)  # spec 06
CATCH_COLD_THRESHOLD = 100  # spec 06
COLD_START_STRENGTH = 20  # spec 06
COLD_STRENGTH_MAX = 100  # spec 06
COLD_PROGRESSION_per_min = per_minute_from_frame(0.0112)  # spec 06
COLD_REDUCTION_per_min = per_minute_from_frame(0.005)  # spec 06
COLD_REDUCTION_STRENGTH_MULT = 2  # spec 06: strength falls twice as fast
COLD_RECOVER_FATIGUE_MAX = 0.5  # spec 06
COLD_RECOVER_HUNGER_MAX = 0.25  # spec 06
COLD_RECOVER_THIRST_MAX = 0.25  # spec 06
SNEEZE_FRAMES_PER_MIN = real_frames_per_minute()  # spec 06
SNEEZE_MIN_LEVEL = 2  # spec 06: Has a Cold level
SNEEZE_TIMER_FRAMES = {2: (600, 800), 3: (300, 600), 4: (200, 300)}  # spec 06
SNEEZE_COIN_SIDES = 100  # spec 06
SNEEZE_COIN_ABOVE = 50  # spec 06: a roll above this is a sneeze
SNEEZE_OR_COUGH_ACTIVE_FRAMES = 25  # spec 06
SNEEZE_NOISE = (20, 25)  # spec 06: radius in tiles, volume; nothing hears it yet
COUGH_NOISE = (35, 40)  # spec 06
SNEEZE_FACT = "{name} sneezes."
COUGH_FACT = "{name} coughs."
