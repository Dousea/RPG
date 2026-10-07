"""Survival stat constants (survival-stats).

Rates ending `_per_hour` are per game hour, converted from their per-frame or
per-day source rate through `modules/units.py`. The frame-rate source value
sits in the conversion call so the original number stays visible.
"""

from modules import units

MAX_CHUNK_MINUTES = 10  # survival-stats

# Hunger
HUNGER_INCREASE_per_hour = units.per_hour_from_day_scaled(0.0000096)  # survival-stats
HUNGER_INCREASE_WHEN_EXERCISE_per_hour = units.per_hour_from_day_scaled(0.0000192)  # survival-stats
HUNGER_EXERCISE_FASTED_DIVISOR = 3  # survival-stats: exercising on an empty stomach uses a third
HUNGER_INCREASE_WHEN_WELL_FED_per_hour = 0.0  # survival-stats
HUNGER_INCREASE_WHILE_ASLEEP_per_hour = units.per_hour_from_day_scaled(0.000001)  # survival-stats

# Thirst
THIRST_INCREASE_per_hour = units.per_hour_from_day_scaled(0.000008)  # survival-stats
THIRST_EXERCISE_MULTIPLIER = 1.2  # survival-stats
THIRST_SLEEPING_INCREASE_per_hour = 0.0036  # survival-stats

# Fatigue
FATIGUE_INCREASE_per_hour = 0.1242  # survival-stats
FATIGUE_ENDURANCE_FLOOR = 0.3  # survival-stats: endurance never counts below this loss
FATIGUE_RESTING_DIVISOR = 1.5  # survival-stats
SLEEP_FATIGUE_LOW_THRESHOLD = 0.3  # survival-stats
SLEEP_FATIGUE_LOW_per_hour = 0.3 / 7  # survival-stats
SLEEP_FATIGUE_HIGH_per_hour = 0.7 / 5  # survival-stats

# Stress
STRESS_DECREASE_per_hour = units.per_hour_from_day_scaled(0.00003)  # survival-stats

# Endurance
EXERCISE_ENDURANCE_DRAIN_per_hour = units.per_hour_from_frame(0.000052 * 0.5)  # survival-stats
IMOBILE_ENDURANCE_INCREASE = 0.000031  # survival-stats
IMOBILE_ENDURANCE_INCREASE_per_hour = units.per_hour_from_frame(
    IMOBILE_ENDURANCE_INCREASE
)  # survival-stats
SITTING_ENDURANCE_MULTIPLIER = 5  # survival-stats
SITTING_FATIGUE_PENALTY = 0.8  # survival-stats
STANDING_FATIGUE_PENALTY = 0.85  # survival-stats
WALKING_ENDURANCE_DIVISOR = 4  # survival-stats
WALKING_DRAIN_ENDURANCE_LEVEL = (
    2  # survival-stats: Endurance status effect level that turns walking into a drain
)
WALKING_ENDURANCE_DRAIN_per_hour = units.per_hour_from_real_frame(0.000052 / 7)  # survival-stats
SNEAK_ENDURANCE_FACTOR = 1.5  # survival-stats
SLEEPING_ENDURANCE_REGEN_per_hour = units.per_hour_from_frame(0.000031 * 2 / 3)  # survival-stats

# Idleness
IDLE_INCREASE_per_hour = units.per_hour_from_day_scaled(0.0005)  # survival-stats
IDLE_INDOORS_BONUS_per_hour = 0.6  # survival-stats
IDLE_DECREASE_per_hour = units.per_hour_from_day_scaled(0.006)  # survival-stats

# Boredom
BOREDOM_DECREASE_per_hour = units.per_hour_from_frame(0.0385 * 0.1)  # survival-stats
BOREDOM_INCREASE_per_hour = units.per_hour_from_frame(0.001)  # survival-stats
BOREDOM_BUSY_INCREASE_DIVISOR = 10  # survival-stats
BOREDOM_BUSY_DECAY_per_hour = units.per_hour_from_frame(0.0385 * 0.5)  # survival-stats
BOREDOM_BUSY_IDLENESS_LIMIT = 0.1  # survival-stats
BOREDOM_TALKING_DECAY_per_hour = units.per_hour_from_frame(0.0385)  # survival-stats
BOREDOM_NPC_DECAY_per_hour = BOREDOM_DECREASE_per_hour  # survival-stats
BOREDOM_DRUNK_DECAY_per_hour = units.per_hour_from_frame(0.0385 * 2)  # survival-stats
BOREDOM_DRUNK_THRESHOLD = 20  # survival-stats: intoxication above this
BOREDOM_PANIC_RESET_THRESHOLD = 5  # survival-stats: panic above this resets boredom

# Unhappiness
UNHAPPINESS_INCREASE_per_hour = units.per_hour_from_frame(0.0005)  # survival-stats
UNHAPPINESS_STRESS_FACTOR = 0.5  # survival-stats
UNHAPPINESS_STATUS_EFFECT_LEVEL = 2  # survival-stats: Bored and Stress level from which it grows

# Panic
PANIC_PER_ZOMBIE = 7  # survival-stats
PANIC_REDUCTION_per_hour = units.per_hour_from_real_frame(0.06)  # survival-stats
PANIC_REDUCTION_MONTH_CAP = 5  # survival-stats
PANIC_REDUCTION_ASLEEP_FACTOR = 2  # survival-stats
SLEEP_INTERRUPTION_PANIC_MIN = 30  # survival-stats
SLEEP_INTERRUPTION_PANIC_MAX = 60  # survival-stats
HOURS_PER_MONTH = 720  # survival-stats: 30 game days

# Intoxication
INTOXICATION_DECREASE_per_hour = units.per_hour_from_frame(0.0042)  # survival-stats

# Food sickness
CORPSE_SICKNESS_per_hour = units.per_hour_from_frame(0.000105)  # survival-stats
CORPSE_SICKNESS_FREE_CORPSES = 5  # survival-stats
CORPSE_SICKNESS_CORPSE_CAP = 20  # survival-stats
FOOD_SICKNESS_DECREASE_per_hour = units.per_hour_from_frame(0.0015)  # survival-stats

# Sleep
BED_MULTIPLIERS = {  # survival-stats
    "good_bed_pillow": 1.15,
    "good_bed": 1.10,
    "average_bed_pillow": 1.05,
    "average_bed": 1.00,
    "bad_bed_pillow": 0.95,
    "bad_bed": 0.90,
    "floor_pillow": 0.75,
    "floor": 0.60,
}
DEFAULT_BED_TYPE = "floor"  # survival-stats
SLEEP_MAX_HOURS = 16  # survival-stats
SLEEP_DEFAULT_WAKE_MINUTE_OF_DAY = 540  # survival-stats: 09:00
SLEEP_FATIGUE_WAKE_MIN_HOURS = (
    1  # survival-stats: our rule, fatigue 0 after this long wakes the player
)
SLEEP_REFUSED_PANIC_LEVEL = 1  # survival-stats
SLEEP_REFUSED_PAIN_LEVEL = 2  # survival-stats
SLEEP_PAIN_FATIGUE_EXCEPTION = 0.85  # survival-stats
SLEEP_WAKE_STATUS_EFFECT_LEVEL = (
    4  # survival-stats: Hungry or Thirst at this level wakes the player
)

# Health loss from status effects
HEALTH_REDUCTION_SEVERE_FRAME = 0.0165  # survival-stats
STARVING_HP_LOSS_per_hour = units.per_hour_from_frame(
    HEALTH_REDUCTION_SEVERE_FRAME / 50
)  # survival-stats
DYING_OF_THIRST_HP_LOSS_per_hour = units.per_hour_from_frame(
    HEALTH_REDUCTION_SEVERE_FRAME / 10
)  # survival-stats
FEVER_HP_LOSS_per_hour = units.per_hour_from_frame(HEALTH_REDUCTION_SEVERE_FRAME)  # survival-stats
SEVERE_STATUS_EFFECT_LEVEL = 4  # survival-stats
