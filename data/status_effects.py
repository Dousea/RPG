"""Status effect thresholds and names (specs 02 and 03).

A status effect level is 0 to 4. Levels compare strictly: a value above a column
gives that level. Endurance is inverted: a value at or below a column.
"""

from dataclasses import dataclass

from modules.stats import CharacterStat, StatusEffect
from modules.units import per_hour_from_frame


@dataclass(frozen=True)
class StatusEffectspec:
    stat: CharacterStat | None
    thresholds: tuple[float, float, float, float]
    names: tuple[str, str, str, str]
    inverted: bool = False
    strict: bool = False  # inverted levels compare with `<` instead of `<=`


STATUS_EFFECT_THRESHOLDS: dict[StatusEffect, StatusEffectspec] = {  # spec 03
    StatusEffect.HUNGRY: StatusEffectspec(
        CharacterStat.HUNGER,
        (0.15, 0.25, 0.45, 0.70),
        ("Peckish", "Hungry", "Very Hungry", "Starving"),
    ),
    StatusEffect.THIRST: StatusEffectspec(
        CharacterStat.THIRST,
        (0.12, 0.25, 0.70, 0.84),
        ("Slightly Thirsty", "Thirsty", "Parched", "Dying of Thirst"),
    ),
    StatusEffect.TIRED: StatusEffectspec(
        CharacterStat.FATIGUE,
        (0.60, 0.70, 0.80, 0.90),
        ("Drowsy", "Tired", "Very Tired", "Ridiculously Tired"),
    ),
    StatusEffect.ENDURANCE: StatusEffectspec(
        CharacterStat.ENDURANCE,
        (0.75, 0.50, 0.25, 0.10),
        ("Moderate Exertion", "High Exertion", "Excessive Exertion", "Exhausted"),
        inverted=True,
    ),
    StatusEffect.STRESS: StatusEffectspec(
        CharacterStat.STRESS,
        (0.25, 0.50, 0.75, 0.90),
        ("Anxious", "Agitated", "Stressed", "Nervous Wreck"),
    ),
    StatusEffect.PANIC: StatusEffectspec(
        CharacterStat.PANIC,
        (6, 30, 65, 80),
        ("Slight Panic", "Panic", "Strong Panic", "Extreme Panic"),
    ),
    StatusEffect.BORED: StatusEffectspec(
        CharacterStat.BOREDOM,
        (25, 50, 75, 90),
        ("Bit Bored", "Bored", "Very Bored", "Extremely Bored"),
    ),
    StatusEffect.UNHAPPY: StatusEffectspec(
        CharacterStat.UNHAPPINESS,
        (20, 45, 60, 80),
        ("Sad", "Very Sad", "Depressed", "Severely Depressed"),
    ),
    StatusEffect.PAIN: StatusEffectspec(
        CharacterStat.PAIN,
        (10, 20, 50, 75),
        ("Minor Pain", "Pain", "Severe Pain", "Agony"),
    ),
    StatusEffect.DRUNK: StatusEffectspec(
        CharacterStat.INTOXICATION,
        (10, 30, 50, 70),
        ("Tipsy", "Drunk", "Very Drunk", "Hammered"),
    ),
    StatusEffect.SICK: StatusEffectspec(
        None,
        (0.25, 0.50, 0.75, 0.90),
        ("Queasy", "Nauseous", "Sick", "Fever"),
    ),
    StatusEffect.FOOD_EATEN: StatusEffectspec(
        None,
        (0, 1600, 3200, 4800),
        ("Well Fed", "Well Fed", "Well Fed", "Well Fed"),
    ),
    StatusEffect.INJURED: StatusEffectspec(
        None,
        (20, 40, 60, 75),
        ("A Little Hurt", "Injured", "Severe Injuries", "Critical Injuries"),
    ),
    StatusEffect.BLEEDING: StatusEffectspec(  # level is the bleeding-part count, so 1 part is level 1
        None,
        (0, 1, 2, 3),
        ("Minor Bleeding", "Bleeding", "Severe Bleeding", "Massive Blood Loss"),
    ),
    StatusEffect.WET: StatusEffectspec(  # spec 06
        CharacterStat.WETNESS,
        (15, 40, 70, 90),
        ("Damp", "Wet", "Soaked", "Drenched"),
    ),
    StatusEffect.HAS_A_COLD: StatusEffectspec(  # spec 06
        CharacterStat.COLD_STRENGTH,
        (20, 40, 60, 75),
        ("Sniffly", "Has a Cold", "Heavy Cold", "Bad Cold"),
    ),
    StatusEffect.HYPOTHERMIA: StatusEffectspec(  # spec 06
        CharacterStat.TEMPERATURE,
        (36.5, 35, 30, 25),
        ("Chilled", "Cold", "Freezing", "Hypothermia"),
        inverted=True,
        strict=True,
    ),
    StatusEffect.HYPERTHERMIA: StatusEffectspec(  # spec 06
        CharacterStat.TEMPERATURE,
        (37.5, 39, 40, 41),
        ("Warm", "Hot", "Overheated", "Hyperthermia"),
    ),
    StatusEffect.WINDCHILL: StatusEffectspec(  # spec 06
        CharacterStat.WINDCHILL,
        (5, 10, 15, 20),
        ("Breezy", "Wind Chill", "Biting Wind", "Freezing Wind"),
    ),
}

STATUS_EFFECT_MAX_LEVEL = 4  # spec 03
HYPOTHERMIA_SUPPRESS_INTOXICATION = (30, 70)  # spec 06: level 1 and level 2

# Our rule: how an outcome fact describes a hurt body, by Injured level 0 to 4.
# Level 0 here still means some hit points are lost; a full body is unhurt.
INJURY_WORDS = ("barely hurt", "a little hurt", "injured", "badly injured", "critically injured")
BLEEDING_LEVEL_CAP = 4  # spec 03
FOOD_EATEN_PER_HUNGER = 13000  # spec 03: timer units per 1.0 hunger
FOOD_EATEN_COOKED_MULT = 2  # spec 03
FOOD_EATEN_CAP = 11000  # spec 03: timer units
FOOD_EATEN_DRAIN_per_hour = per_hour_from_frame(1)  # spec 03: 1 timer unit per frame
PANIC_MELEE_PENALTY_PER_LEVEL = 0.1  # spec 03: Panic level 2 and up
STRESS_MELEE_PENALTY_PER_LEVEL = 0.1  # spec 03: Stress level 2 and up
MELEE_DAMAGE_FLOOR = 0.1  # spec 03
CRIT_PENALTY_ENDURANCE = 5  # spec 03: per level
CRIT_PENALTY_HEAVY_LOAD = 5  # spec 03: per level
CRIT_PENALTY_PANIC = 1.3  # spec 03: per level
DEFENCE_PENALTY_ENDURANCE = 2  # spec 03: per level
DEFENCE_PENALTY_TIRED = 3  # spec 03: per level
DEFENCE_PENALTY_DRUNK = 2  # spec 03: per level
ALCOHOL_INTOXICATION_PER_PORTION = 400  # spec 03
ALCOHOL_WHOLE_ITEM_PORTION = 2  # spec 03: a whole item that has a hunger change
ALCOHOL_PARTIAL_PORTION = 1  # spec 03: an item with no hunger change
ALCOHOL_LOW_MULT = 0.25  # spec 03
ALCOHOL_HUNGER_HIGH = 0.8  # spec 03
ALCOHOL_HUNGER_HIGH_MULT = 1.25  # spec 03
ALCOHOL_HUNGER_MID = 0.6  # spec 03
ALCOHOL_HUNGER_MID_MULT = 1.1  # spec 03
