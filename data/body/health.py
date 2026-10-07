"""Body-part health, wounds, pain, infection and the zombie infection (health).

Rates ending `_per_hour` are per game hour, with their frame-rate source value
visible where it was converted through `modules/units.py`.
"""

from dataclasses import dataclass

from modules import units
from modules.body.parts import PART_WEIGHT, BodyPart


@dataclass(frozen=True)
class PartRow:
    weight: float
    bleeding: float
    pain: float


def _row(part: BodyPart, bleeding: float, pain: float) -> tuple[BodyPart, PartRow]:
    return part, PartRow(PART_WEIGHT[part], bleeding, pain)


PARTS: dict[BodyPart, PartRow] = dict(  # health
    [
        _row(BodyPart.HAND_L, 0.2, 0.5),
        _row(BodyPart.HAND_R, 0.2, 0.5),
        _row(BodyPart.FOREARM_L, 0.3, 0.6),
        _row(BodyPart.FOREARM_R, 0.3, 0.6),
        _row(BodyPart.UPPERARM_L, 0.4, 0.6),
        _row(BodyPart.UPPERARM_R, 0.4, 0.6),
        _row(BodyPart.TORSO_UPPER, 0.5, 0.7),
        _row(BodyPart.TORSO_LOWER, 0.9, 0.78),
        _row(BodyPart.HEAD, 1.0, 0.8),
        _row(BodyPart.NECK, 1.5, 0.8),
        _row(BodyPart.GROIN, 0.5, 0.7),
        _row(BodyPart.UPPERLEG_L, 0.4, 0.7),
        _row(BodyPart.UPPERLEG_R, 0.4, 0.7),
        _row(BodyPart.LOWERLEG_L, 0.3, 0.6),
        _row(BodyPart.LOWERLEG_R, 0.3, 0.6),
        _row(BodyPart.FOOT_L, 0.2, 0.5),
        _row(BodyPart.FOOT_R, 0.2, 0.5),
    ]
)
PART_COUNT = 17  # health
WAKE_HEALTH = 10  # health: a sleeper is woken at this overall health or less
PART_DAMAGE_SCALER = 0.0057142857  # health
NECK_DAMAGE_SCALER_MULT = 5  # health

# Wounds
SCRATCH = "scratch"
LACERATION = "laceration"
BITE = "bite"
WOUND_TIME = {  # health: U(a, b) game units, normal / Fast Healer / Slow Healer
    SCRATCH: ((7, 15), (4, 10), (15, 25)),
    LACERATION: ((10, 20), (5, 10), (20, 30)),
    BITE: ((50, 80), (30, 50), (80, 150)),
}
BLEEDING_TIME_SCRATCH = (0.3, 0.6)  # health: x scratch_time
BLEEDING_TIME_CUT = (0.7, 1.0)  # health: x cut_time
BLEEDING_TIME_BITE = (7.5, 15.0)  # health: units
FAST_HEALER_INDEX = 1  # health: column of WOUND_TIME
SLOW_HEALER_INDEX = 2  # health: column of WOUND_TIME

# What open wounds cost the part, per game hour (the part's damage scaler is included).
WOUND_DAMAGE_PER_HOUR = {SCRATCH: 57.9, LACERATION: 115.7, BITE: 135.0}  # health

# Wound timers, per game hour: (unbandaged, bandaged).
SCRATCH_DECAY_PER_HOUR = (0.108, 1.62)  # health
CUT_DECAY_PER_HOUR = (0.0108, 0.54)  # health
BITE_DECAY_PER_HOUR = (0.054, 1.08)  # health
BLEEDING_DECAY_PER_HOUR = (0.216, 2.16)  # health

# Bandage wear, per game hour
BANDAGE_WEAR_BITE_PER_HOUR = 1.08  # health
BANDAGE_WEAR_BLEEDING_PER_HOUR = 3.24  # health
BANDAGE_WEAR_INFECTED_PER_HOUR = 2.16  # health
BANDAGE_WEAR_SCRATCH_PER_HOUR = 0.864  # health
BANDAGE_WEAR_CUT_PER_HOUR = 0.108  # health

# Bleeding
BLEED_HP_PER_HOUR_PER_UNIT = 1.763  # health: HP per hour per unit of bleeding_time
BLEED_HP_PER_HOUR_PER_UNIT_NECK = 8.82  # health

# Healing, health per game hour
HEAL_AWAKE_PER_HOUR = units.per_hour_from_frame(0.002)  # health: 21.6
HEAL_REDUCED_PER_HOUR = units.per_hour_from_frame(0.0013)  # health: 14.04
HEAL_SEVERELY_REDUCED_PER_HOUR = units.per_hour_from_frame(0.0008)  # health: 8.64
HEAL_ASLEEP_PER_HOUR = units.per_hour_from_frame(0.02)  # health: 216
HEAL_FOOD_PER_HOUR = units.per_hour_from_frame(0.015)  # health: 162
HEAL_REDUCED_LEVEL = 2  # health
HEAL_SEVERELY_REDUCED_LEVEL = 3  # health
HEAL_NONE_LEVEL = 4  # health: Hungry or Thirst

# Pain
PAIN_BITE_BANDAGED = 30  # health
PAIN_BITE_OPEN = 50  # health
PAIN_BANDAGE_DIVISOR = 1.5  # health
PAIN_SCRATCH_PER_UNIT = 1.7  # health
PAIN_CUT_PER_UNIT = 2.5  # health
PAIN_STIFFNESS_DIVISOR = 3.5  # health
EXTRA_PAIN_DECAY_PER_HOUR = 54.0  # health
STIFFNESS_DECAY_PER_HOUR = 21.6  # health
PAIN_RISE_PER_MIN_FACTOR = 0.7985  # health: share of the gap left after a minute
PAINKILLER_MINUTES = 48  # health
PAINKILLER_PAIN_DROP_PER_HOUR = 157.5  # health

# Slower actions
ACTION_TIME_UNHAPPY_DIVISOR = 4  # health
ACTION_TIME_DRUNK_DIVISOR = 4  # health
ACTION_TIME_HAND_PAIN_DIVISOR = 300  # health
ACTION_TIME_COLD_HANDS = {  # health: k per part
    BodyPart.HAND_L: 0.3,
    BodyPart.HAND_R: 0.3,
    BodyPart.FOREARM_L: 0.15,
    BodyPart.FOREARM_R: 0.15,
    BodyPart.UPPERARM_L: 0.1,
    BodyPart.UPPERARM_R: 0.1,
}
ACTION_TIME_COLD_HANDS_WEIGHT = 0.25  # health
COLD_HANDS_SKIN_FLOOR_C = 20.0  # health
COLD_HANDS_SKIN_RANGE_C = 13.0  # health
COLD_HANDS_SKIN_LIMIT_C = 33.0  # health: no effect at or above
HAND_PAIN_PARTS = (  # health: both hands and both forearms
    BodyPart.HAND_L,
    BodyPart.HAND_R,
    BodyPart.FOREARM_L,
    BodyPart.FOREARM_R,
)

# The limp
LIMP_PARTS = (  # health
    BodyPart.GROIN,
    BodyPart.UPPERLEG_L,
    BodyPart.UPPERLEG_R,
    BodyPart.LOWERLEG_L,
    BodyPart.LOWERLEG_R,
    BodyPart.FOOT_L,
    BodyPart.FOOT_R,
)
LIMP_FOOT_PARTS = (BodyPart.FOOT_L, BodyPart.FOOT_R)  # health
LIMP_SCRATCH_DIVISOR = 45.0  # health: groin, thighs, shins
LIMP_CUT_DIVISOR = 55.0  # health
LIMP_FOOT_SCRATCH_DIVISOR = 35.0  # health
LIMP_FOOT_CUT_DIVISOR = 45.0  # health
LIMP_BITE_DIVISOR = 20.0  # health
LIMP_FOOT_BITE_TERM = 1.0  # health
LIMP_FOOT_BITE_BANDAGED_MULT = 0.7  # health
LIMP_SCRATCH_MIN = 2.0  # health: scratch_time above this counts
LIMP_CUT_MIN = 5.0  # health: cut_time above this counts
LIMP_BANDAGED_DIVISOR = 2.0  # health
LIMP_THRESHOLD = 0.1  # health
LIMP_SPEED_DIVISOR = 1.5  # health
LIMP_SPEED_FLOOR = 0.25  # health

# Wound infection
WOUND_INFECTION_N_BASE = 40000  # health: 1 in N per real frame
WOUND_INFECTION_N_NO_BANDAGE = -10000  # health
WOUND_INFECTION_N_DIRTY_BANDAGE = -35000  # health
WOUND_INFECTION_N_SCRATCH = -20000  # health
WOUND_INFECTION_N_CUT = -25000  # health
WOUND_INFECTION_N_FLOOR = 5000  # health
WOUND_INFECTION_ALCOHOL_PER_HOUR = units.per_hour_from_frame(0.0002)  # health: 2.16
WOUND_INFECTION_POWER_PER_HOUR = units.per_hour_from_frame(0.0002)  # health: 2.16
WOUND_INFECTION_ZOMBIE_RISE_PER_HOUR = units.per_hour_from_frame(0.0002)  # health: 2.16
WOUND_INFECTION_RISE_PER_HOUR = units.per_hour_from_frame(0.00001)  # health: 0.108
WOUND_INFECTION_ALCOHOL_BANDAGE_PER_HOUR = units.per_hour_from_frame(0.0006)  # health: 6.48
WOUND_INFECTION_MAX = 10.0  # health
WOUND_INFECTION_FLOOR = -2.0  # health
ALCOHOL_DECAY_PER_HOUR = WOUND_INFECTION_ALCOHOL_PER_HOUR  # health

# The zombie infection
ZOMBIE_INFECTION_DAYS_RANGE = (2, 3)  # health: days
ZOMBIE_INFECTION_HOURS_PER_DAY = 24  # health
ZOMBIE_INFECTION_RESILIENT_MULT = 1.25  # health
ZOMBIE_INFECTION_PRONE_MULT = 0.75  # health
ZOMBIE_INFECTION_CAP_EXPONENT = 4  # health
ZOMBIE_INFECTION_CAP_NONE_ABOVE = 99  # health: no cap applies while the cap is above this
RISE_INFECTION_MIN = 0.001  # health: zombie_infection that makes a dead player rise

# Stress
STRESS_FROM_WOUND_PER_HOUR = 0.18  # health: 0.00005 per day-scaled frame, per source

# Treatment
BANDAGE_LIFE_RANGE = (0.5, 1.0)  # health: x (First Aid + 1)
BANDAGE_XP = 5  # health
FEAR_OF_BLOOD_PANIC = 50  # health
DISINFECT_ALCOHOL = 4  # health
DISINFECT_EXTRA_PAIN_BASE = 52  # health: at First Aid 0
DISINFECT_EXTRA_PAIN_PER_FIRST_AID = 0.5  # health: less per level
ANTIBIOTIC_DECAY_PER_HOUR = 10.8  # health
FIRST_AID_SKILL = "first_aid"  # health
MOST_NEEDED_BLEEDING = 100  # health
MOST_NEEDED_SCRATCH = 50  # health
MOST_NEEDED_BITE = 50  # health

# Death causes
DEATH_BLEEDING = "{name} bled to death."  # health
DEATH_WOUNDS = "{name} died of the wounds."  # health
DEATH_ZOMBIE_INFECTION = "{name} died of the zombie infection."  # health
DEATH_STATUS_EFFECT = "{name} died of {cause}."  # health
DEATH_COLD = "{name} died of the cold."  # health
DEATH_HEAT = "{name} died of the heat."  # health
ROSE_AGAIN_SUFFIX = "...and rose again."  # health
WEAKENING_FACT = "{name} is weakening from {cause}."  # health
WEAKENING_WORD = {  # health: the word a weakening fact uses for each status effect cause
    "starvation": "hunger",
    "thirst": "thirst",
    "fever": "fever",
    "infection": "infection",
}

# Facts
BANDAGE_FACT = "{name} bandages the {part}."  # health
REMOVE_BANDAGE_FACT = "{name} takes the bandage off the {part}."  # health
REMOVE_DIRTY_BANDAGE_FACT = "{name} takes the dirty bandage off the {part}."  # health
DISINFECT_FACT = "{name} dabs disinfectant on the {part}. It stings."  # health
STOPPED_BLEEDING_FACT = "The {part} has stopped bleeding."  # health
SOAKED_FACT = "The bandage on the {part} is soaked through."  # health
HEALED_FACT = "The {kind} on the {part} has healed."  # health
PAINKILLER_FACT = "{name} takes a painkiller."  # health
ANTIBIOTIC_FACT = "{name} takes an antibiotic."  # health
WEAKER_FACT = "{name} is getting weaker."  # health
USE_HINT = "Use BANDAGE or DISINFECT."  # health

PART_ALIASES = {  # health: other ways to name a part, beside its words in the threat facts
    "upper torso": BodyPart.TORSO_UPPER,
    "torso": BodyPart.TORSO_UPPER,
    "lower torso": BodyPart.TORSO_LOWER,
    "belly": BodyPart.TORSO_LOWER,
    "abdomen": BodyPart.TORSO_LOWER,
    "left upper leg": BodyPart.UPPERLEG_L,
    "right upper leg": BodyPart.UPPERLEG_R,
    "left lower leg": BodyPart.LOWERLEG_L,
    "right lower leg": BodyPart.LOWERLEG_R,
}
