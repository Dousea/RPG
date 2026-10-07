"""Status effect levels read off the survival stats, their penalties, and what a drink adds (status-effects)."""

from data.body import status_effects as status_effect_k
from data.body.status_effects import (
    BLEEDING_LEVEL_CAP,
    CRIT_PENALTY_ENDURANCE,
    CRIT_PENALTY_HEAVY_LOAD,
    CRIT_PENALTY_PANIC,
    DEFENCE_PENALTY_DRUNK,
    DEFENCE_PENALTY_ENDURANCE,
    DEFENCE_PENALTY_TIRED,
    INJURY_WORDS,
    MELEE_DAMAGE_FLOOR,
    PANIC_MELEE_PENALTY_PER_LEVEL,
    STATUS_EFFECT_THRESHOLDS,
    STRESS_MELEE_PENALTY_PER_LEVEL,
)
from managers import carry
from modules.body.parts import BodyPart, general_wound_infection
from modules.body.stats import CharacterStat, Stats, StatusEffect
from modules.entity.player import PlayerEntity
from modules.item import ConsumableItem


def status_effect_level(status_effect: StatusEffect, value: float) -> int:
    """The 0 to 4 level a stat value gives a status effect; endurance counts downward."""
    spec = STATUS_EFFECT_THRESHOLDS[status_effect]
    level = 0
    for index, threshold in enumerate(spec.thresholds, start=1):
        if spec.inverted:
            reached = value < threshold if spec.strict else value <= threshold
        else:
            reached = value > threshold
        if reached:
            level = index
    return level


def sick_value(stats: Stats, wound_infection: float = 0.0) -> float:
    """The number the Sick status effect reads: the worst of food sickness, zombie infection and wound infection."""
    worst = max(
        stats.get(CharacterStat.FOOD_SICKNESS),
        stats.get(CharacterStat.ZOMBIE_INFECTION),
        wound_infection,
    )
    return worst / 100 + stats.get(CharacterStat.SICKNESS)


def bleeding_level(bleeding_parts: int, neck: bool) -> int:
    """The Bleeding status effect level: bleeding body parts capped at 4, or 4 if the neck bleeds."""
    if neck:
        return BLEEDING_LEVEL_CAP
    return min(bleeding_parts, BLEEDING_LEVEL_CAP)


def hypothermia_level(core: float, intoxication: float) -> int:
    """The Hypothermia level the player sees: levels 1 and 2 hide while intoxication is above 30 and 70."""
    level = status_effect_level(StatusEffect.HYPOTHERMIA, core)
    suppress_1, suppress_2 = status_effect_k.HYPOTHERMIA_SUPPRESS_INTOXICATION
    if (level == 1 and intoxication > suppress_1) or (level == 2 and intoxication > suppress_2):
        return 0
    return level


def status_effect_levels(
    stats: Stats,
    food_eaten_timer: float = 0.0,
    hit_points: float | None = None,
    bleeding: int = 0,
    wound_infection: float = 0.0,
) -> dict[StatusEffect, int]:
    """Every status effect's current level, in table order.

    Injured is off when `hit_points` is not given or is 0; `bleeding` is the
    Bleeding level and `wound_infection` the general wound infection.
    """
    levels: dict[StatusEffect, int] = {}
    for status_effect, spec in STATUS_EFFECT_THRESHOLDS.items():
        if status_effect is StatusEffect.FOOD_EATEN:
            levels[status_effect] = status_effect_level(status_effect, food_eaten_timer)
        elif status_effect is StatusEffect.SICK:
            levels[status_effect] = status_effect_level(
                status_effect, sick_value(stats, wound_infection)
            )
        elif status_effect is StatusEffect.INJURED:
            injured = hit_points is not None and hit_points > 0
            levels[status_effect] = (
                status_effect_level(status_effect, 100 - (hit_points or 0)) if injured else 0
            )
        elif status_effect is StatusEffect.BLEEDING:
            levels[status_effect] = bleeding
        elif status_effect is StatusEffect.HEAVY_LOAD:
            levels[status_effect] = 0
        else:
            assert spec.stat is not None
            levels[status_effect] = status_effect_level(status_effect, stats.get(spec.stat))
    levels[StatusEffect.HYPOTHERMIA] = hypothermia_level(
        stats.get(CharacterStat.TEMPERATURE), stats.get(CharacterStat.INTOXICATION)
    )
    return levels


def injury_words(hit_points: int, max_hit_points: int) -> str:
    """How hurt a body is, by the Injured status effect's bands scaled to its max."""
    if hit_points >= max_hit_points:
        return "unhurt"
    lost_per_hundred = 100 * (max_hit_points - hit_points) / max_hit_points
    return INJURY_WORDS[status_effect_level(StatusEffect.INJURED, lost_per_hundred)]


def melee_status_effect_penalty(stats: Stats) -> float:
    """Damage the Panic and Stress status effects subtract from a melee hit (level 2 and up)."""
    penalty = 0.0
    panic = status_effect_level(StatusEffect.PANIC, stats.get(CharacterStat.PANIC))
    if panic >= 2:
        penalty += PANIC_MELEE_PENALTY_PER_LEVEL * panic
    stress = status_effect_level(StatusEffect.STRESS, stats.get(CharacterStat.STRESS))
    if stress >= 2:
        penalty += STRESS_MELEE_PENALTY_PER_LEVEL * stress
    return penalty


def damage_after_status_effects(damage: float, stats: Stats) -> float:
    """A melee hit less the status effect penalty, floored at the minimum damage."""
    reduced = damage - melee_status_effect_penalty(stats)
    return MELEE_DAMAGE_FLOOR if reduced < 0 else reduced


def crit_penalty(endurance: int, heavy_load: int, panic: int) -> float:
    """Crit chance points lost to the Endurance, Heavy Load and Panic levels."""
    return (
        CRIT_PENALTY_ENDURANCE * endurance
        + CRIT_PENALTY_HEAVY_LOAD * heavy_load
        + CRIT_PENALTY_PANIC * panic
    )


def defence_penalty(endurance: int, tired: int, drunk: int) -> int:
    """Defence points lost to the Endurance, Tired and Drunk levels."""
    return (
        DEFENCE_PENALTY_ENDURANCE * endurance
        + DEFENCE_PENALTY_TIRED * tired
        + DEFENCE_PENALTY_DRUNK * drunk
    )


def player_bleeding_level(player: PlayerEntity) -> int:
    bleeding = [part for part, state in player.body.items() if state.bleeding]
    return bleeding_level(len(bleeding), BodyPart.NECK in bleeding)


def player_status_effect_levels(player: PlayerEntity) -> dict[StatusEffect, int]:
    levels = status_effect_levels(
        player.stats,
        player.food_eaten_timer,
        player.health,
        player_bleeding_level(player),
        general_wound_infection(player.body),
    )
    if player.health > 0:
        capacity = carry.player_max_weight(player, levels)
        levels[StatusEffect.HEAVY_LOAD] = carry.heavy_load_level(
            carry.carried_weight(player), capacity
        )
    return levels


def food_eaten_level(player: PlayerEntity) -> int:
    return status_effect_level(StatusEffect.FOOD_EATEN, player.food_eaten_timer)


def active_status_effects(player: PlayerEntity) -> list[tuple[StatusEffect, int, str]]:
    """Status effects above level 0 as (type, level, name), in table order."""
    return [
        (status_effect, level, STATUS_EFFECT_THRESHOLDS[status_effect].names[level - 1])
        for status_effect, level in player_status_effect_levels(player).items()
        if level > 0
    ]


def level_change_facts(
    name: str, before: dict[StatusEffect, int], after: dict[StatusEffect, int]
) -> list[str]:
    """One fact per status effect whose level changed to a differently named one, in table order."""
    facts: list[str] = []
    for status_effect, level in after.items():
        was = before[status_effect]
        names = STATUS_EFFECT_THRESHOLDS[status_effect].names
        if level == was or (level and was and names[level - 1] == names[was - 1]):
            continue
        if level == 0:
            facts.append(f"{name} is no longer {names[was - 1]}.")
        else:
            facts.append(f"{name} is now {names[level - 1]}.")
    return facts


def level_change_fact_texts(name: str) -> frozenset[str]:
    """Every fact `level_change_facts` can write for this name."""
    return frozenset(
        f"{name} is {word} {level_name}."
        for spec in STATUS_EFFECT_THRESHOLDS.values()
        for level_name in spec.names
        for word in ("now", "no longer")
    )


def alcohol_intoxication(item: ConsumableItem, hunger: float) -> float:
    """Intoxication a drink adds, given hunger after the drink's own hunger change."""
    amount = status_effect_k.ALCOHOL_INTOXICATION_PER_UNIT * item.alcohol
    if hunger > status_effect_k.ALCOHOL_HUNGER_HIGH:
        amount *= status_effect_k.ALCOHOL_HUNGER_HIGH_MULT
    elif hunger > status_effect_k.ALCOHOL_HUNGER_MID:
        amount *= status_effect_k.ALCOHOL_HUNGER_MID_MULT
    return amount
