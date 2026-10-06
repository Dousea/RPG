"""Status effect thresholds and names (specs 02 and 03).

A status effect level is 0 to 4. Levels compare strictly: a value above a column
gives that level. Endurance is inverted: a value at or below a column.
"""

from dataclasses import dataclass

from modules.stats import CharacterStat, StatusEffect


@dataclass(frozen=True)
class StatusEffectspec:
    stat: CharacterStat | None
    thresholds: tuple[float, float, float, float]
    names: tuple[str, str, str, str]
    inverted: bool = False


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
}
