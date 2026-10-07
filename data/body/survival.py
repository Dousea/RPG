"""Survival stat constants (spec 02).

Rates ending `_per_hour` are per game hour, converted from their per-frame or
per-day source rate through `modules/units.py`. The frame-rate source value
sits in the conversion call so the original number stays visible.
"""

from modules.units import (
    DAY_SCALED_PER_HOUR,
    FRAME_RATE_PER_HOUR,
    REAL_TIME_PER_HOUR,
    per_hour_from_day_scaled,
    per_hour_from_frame,
    per_hour_from_real_frame,
)

MAX_CHUNK_MINUTES = 10  # spec 02

__all__ = ["DAY_SCALED_PER_HOUR", "FRAME_RATE_PER_HOUR", "REAL_TIME_PER_HOUR"]

# Hunger
HUNGER_INCREASE_per_hour = per_hour_from_day_scaled(0.0000096)  # spec 02
HUNGER_INCREASE_WHEN_EXERCISE_per_hour = per_hour_from_day_scaled(0.0000192)  # spec 02
HUNGER_EXERCISE_FASTED_DIVISOR = 3  # spec 02: exercising on an empty stomach uses a third
HUNGER_INCREASE_WHEN_WELL_FED_per_hour = 0.0  # spec 02
HUNGER_INCREASE_WHILE_ASLEEP_per_hour = per_hour_from_day_scaled(0.000001)  # spec 02

# Thirst
THIRST_INCREASE_per_hour = per_hour_from_day_scaled(0.000008)  # spec 02
THIRST_EXERCISE_MULTIPLIER = 1.2  # spec 02
THIRST_SLEEPING_INCREASE_per_hour = 0.0036  # spec 02

# Fatigue
FATIGUE_INCREASE_per_hour = 0.1242  # spec 02
FATIGUE_ENDURANCE_FLOOR = 0.3  # spec 02: endurance never counts below this loss
FATIGUE_RESTING_DIVISOR = 1.5  # spec 02
SLEEP_FATIGUE_LOW_THRESHOLD = 0.3  # spec 02
SLEEP_FATIGUE_LOW_per_hour = 0.3 / 7  # spec 02
SLEEP_FATIGUE_HIGH_per_hour = 0.7 / 5  # spec 02

# Stress
STRESS_DECREASE_per_hour = per_hour_from_day_scaled(0.00003)  # spec 02

# Endurance
EXERCISE_ENDURANCE_DRAIN_per_hour = per_hour_from_frame(0.000052 * 0.5)  # spec 02
IMOBILE_ENDURANCE_INCREASE = 0.000031  # spec 02
IMOBILE_ENDURANCE_INCREASE_per_hour = per_hour_from_frame(IMOBILE_ENDURANCE_INCREASE)  # spec 02
SITTING_ENDURANCE_MULTIPLIER = 5  # spec 02
SITTING_FATIGUE_PENALTY = 0.8  # spec 02
STANDING_FATIGUE_PENALTY = 0.85  # spec 02
WALKING_ENDURANCE_DIVISOR = 4  # spec 02
WALKING_DRAIN_ENDURANCE_LEVEL = (
    2  # spec 02: Endurance status effect level that turns walking into a drain
)
WALKING_ENDURANCE_DRAIN_per_hour = per_hour_from_real_frame(0.000052 / 7)  # spec 02
SNEAK_ENDURANCE_FACTOR = 1.5  # spec 02
SLEEPING_ENDURANCE_REGEN_per_hour = per_hour_from_frame(0.000031 * 2 / 3)  # spec 02

# Idleness
IDLE_INCREASE_per_hour = per_hour_from_day_scaled(0.0005)  # spec 02
IDLE_INDOORS_BONUS_per_hour = 0.6  # spec 02
IDLE_DECREASE_per_hour = per_hour_from_day_scaled(0.006)  # spec 02

# Boredom
BOREDOM_DECREASE_per_hour = per_hour_from_frame(0.0385 * 0.1)  # spec 02
BOREDOM_INCREASE_per_hour = per_hour_from_frame(0.001)  # spec 02
BOREDOM_BUSY_INCREASE_DIVISOR = 10  # spec 02
BOREDOM_BUSY_DECAY_per_hour = per_hour_from_frame(0.0385 * 0.5)  # spec 02
BOREDOM_BUSY_IDLENESS_LIMIT = 0.1  # spec 02
BOREDOM_TALKING_DECAY_per_hour = per_hour_from_frame(0.0385)  # spec 02
BOREDOM_NPC_DECAY_per_hour = BOREDOM_DECREASE_per_hour  # spec 02
BOREDOM_DRUNK_DECAY_per_hour = per_hour_from_frame(0.0385 * 2)  # spec 02
BOREDOM_DRUNK_THRESHOLD = 20  # spec 02: intoxication above this
BOREDOM_PANIC_RESET_THRESHOLD = 5  # spec 02: panic above this resets boredom

# Unhappiness
UNHAPPINESS_INCREASE_per_hour = per_hour_from_frame(0.0005)  # spec 02
UNHAPPINESS_STRESS_FACTOR = 0.5  # spec 02
UNHAPPINESS_STATUS_EFFECT_LEVEL = 2  # spec 02: Bored and Stress level from which it grows

# Panic
PANIC_PER_ZOMBIE = 7  # spec 02
PANIC_REDUCTION_per_hour = per_hour_from_real_frame(0.06)  # spec 02
PANIC_REDUCTION_MONTH_CAP = 5  # spec 02
PANIC_REDUCTION_ASLEEP_FACTOR = 2  # spec 02
SLEEP_INTERRUPTION_PANIC_MIN = 30  # spec 02
SLEEP_INTERRUPTION_PANIC_MAX = 60  # spec 02
HOURS_PER_MONTH = 720  # spec 02: 30 game days

# Intoxication
INTOXICATION_DECREASE_per_hour = per_hour_from_frame(0.0042)  # spec 02

# Food sickness
CORPSE_SICKNESS_per_hour = per_hour_from_frame(0.000105)  # spec 02
CORPSE_SICKNESS_FREE_CORPSES = 5  # spec 02
CORPSE_SICKNESS_CORPSE_CAP = 20  # spec 02
FOOD_SICKNESS_DECREASE_per_hour = per_hour_from_frame(0.0015)  # spec 02

# Sleep
BED_MULTIPLIERS = {  # spec 02
    "good_bed_pillow": 1.15,
    "good_bed": 1.10,
    "average_bed_pillow": 1.05,
    "average_bed": 1.00,
    "bad_bed_pillow": 0.95,
    "bad_bed": 0.90,
    "floor_pillow": 0.75,
    "floor": 0.60,
}
DEFAULT_BED_TYPE = "floor"  # spec 02
SLEEP_MAX_HOURS = 16  # spec 02
SLEEP_DEFAULT_WAKE_MINUTE_OF_DAY = 540  # spec 02: 09:00
SLEEP_FATIGUE_WAKE_MIN_HOURS = 1  # spec 02: our rule, fatigue 0 after this long wakes the player
SLEEP_REFUSED_PANIC_LEVEL = 1  # spec 02
SLEEP_REFUSED_PAIN_LEVEL = 2  # spec 02
SLEEP_PAIN_FATIGUE_EXCEPTION = 0.85  # spec 02
SLEEP_WAKE_STATUS_EFFECT_LEVEL = 4  # spec 02: Hungry or Thirst at this level wakes the player

# Health loss from status effects
HEALTH_REDUCTION_SEVERE_FRAME = 0.0165  # spec 02
STARVING_HP_LOSS_per_hour = per_hour_from_frame(HEALTH_REDUCTION_SEVERE_FRAME / 50)  # spec 02
DYING_OF_THIRST_HP_LOSS_per_hour = per_hour_from_frame(
    HEALTH_REDUCTION_SEVERE_FRAME / 10
)  # spec 02
FEVER_HP_LOSS_per_hour = per_hour_from_frame(HEALTH_REDUCTION_SEVERE_FRAME)  # spec 02
SEVERE_STATUS_EFFECT_LEVEL = 4  # spec 02
