"""The skill list, XP tables and the numbers that move XP (spec 08)."""

from modules.character.skills import SkillDefinition as Skill

COMBAT = "combat"
FIREARM = "firearm"
CRAFTING = "crafting"
SURVIVALIST = "survivalist"
PHYSICAL = "physical"
FARMING = "farming"

_ROWS = [
    Skill("axe", "Axe", COMBAT),
    Skill("long_blunt", "Long Blunt", COMBAT),
    Skill("short_blunt", "Short Blunt", COMBAT),
    Skill("long_blade", "Long Blade", COMBAT),
    Skill("short_blade", "Short Blade", COMBAT),
    Skill("spear", "Spear", COMBAT),
    Skill("maintenance", "Maintenance", COMBAT),
    Skill("aiming", "Aiming", FIREARM),
    Skill("reloading", "Reloading", FIREARM),
    Skill("carpentry", "Carpentry", CRAFTING),
    Skill("carving", "Carving", CRAFTING),
    Skill("cooking", "Cooking", CRAFTING),
    Skill("electrical", "Electrical", CRAFTING),
    Skill("glassmaking", "Glassmaking", CRAFTING),
    Skill("knapping", "Knapping", CRAFTING),
    Skill("masonry", "Masonry", CRAFTING),
    Skill("blacksmithing", "Blacksmithing", CRAFTING),
    Skill("mechanics", "Mechanics", CRAFTING),
    Skill("pottery", "Pottery", CRAFTING),
    Skill("tailoring", "Tailoring", CRAFTING),
    Skill("welding", "Welding", CRAFTING),
    Skill("first_aid", "First Aid", SURVIVALIST),
    Skill("fishing", "Fishing", SURVIVALIST),
    Skill("foraging", "Foraging", SURVIVALIST),
    Skill("tracking", "Tracking", SURVIVALIST),
    Skill("trapping", "Trapping", SURVIVALIST),
    Skill("fitness", "Fitness", PHYSICAL, passive=True),
    Skill("strength", "Strength", PHYSICAL, passive=True),
    Skill("lightfooted", "Lightfooted", PHYSICAL),
    Skill("nimble", "Nimble", PHYSICAL),
    Skill("running", "Running", PHYSICAL),
    Skill("sneaking", "Sneaking", PHYSICAL),
    Skill("agriculture", "Agriculture", FARMING),
    Skill("animal_care", "Animal Care", FARMING),
    Skill("butchering", "Butchering", FARMING),
]

SKILLS: dict[str, Skill] = {row.id: row for row in _ROWS}  # spec 08: 35 skills

FITNESS = "fitness"
STRENGTH = "strength"
RUNNING = "running"
PASSIVE_SKILLS = (FITNESS, STRENGTH)  # spec 08

MAX_LEVEL = 10  # spec 08
XP_PER_LEVEL = (75, 150, 300, 750, 1500, 3000, 4500, 6000, 7500, 9000)  # spec 08: XP
XP_PER_LEVEL_PASSIVE = (  # spec 08: XP
    1500,
    3000,
    6000,
    9000,
    18000,
    30000,
    60000,
    90000,
    120000,
    150000,
)


def total_xp_for_level(skill_id: str, level: int) -> int:
    """The XP needed to reach `level` in `skill_id`: the running total of the table."""
    table = XP_PER_LEVEL_PASSIVE if SKILLS[skill_id].passive else XP_PER_LEVEL
    return sum(table[:level])


BOOST_MULTIPLIER = {0: 0.25, 1: 1.0, 2: 1.33, 3: 1.66}  # spec 08: factor by boost
RUNNING_BOOST_ONE_MULTIPLIER = 1.25  # spec 08
FAST_LEARNER_MULT = 1.3  # spec 08
SLOW_LEARNER_MULT = 0.7  # spec 08
RELUCTANT_FIGHTER_MULT = 0.75  # spec 08
CRAFTY_MULT = 1.3  # spec 08
GLOBAL_XP_MULTIPLIER = 1.0  # spec 08
RELUCTANT_FIGHTER_SKILLS = (  # spec 08
    "axe",
    "long_blunt",
    "short_blunt",
    "long_blade",
    "short_blade",
    "spear",
    "aiming",
)

HIT_XP_DAMAGE_FACTOR = 0.9  # spec 08
HIT_XP_CAP = 3.0  # spec 08: XP per hit
HIT_FITNESS_XP = 1.0  # spec 08: XP per hit
HIT_FITNESS_ENDURANCE_ABOVE = 0.5  # spec 08: endurance
HIT_STRENGTH_XP_PER_TARGET = 1.0  # spec 08: XP per target hit
EXHAUSTION_FITNESS_XP_PER_TICK = 6.0  # spec 08: 36 XP per game hour in 10-minute ticks
EXHAUSTION_ENDURANCE_BELOW = 0.25  # spec 08: endurance

TICK_MINUTES = 10  # spec 08: the boundary the loss timers run on
LOSS_TIMER_START = -50000  # spec 08
LOSS_TIMER_STEP_PER_TICK = 10  # spec 08
LOSS_TIMER_GAIN_DROP = 3000  # spec 08
LOSS_TIMER_ACTIVE_ABOVE = 20000  # spec 08
LOSS_TIMER_DIVISOR = 1200  # spec 08
LOSS_TIMER_RESET_ABOVE = 31000  # spec 08
LOSS_XP = 1.0  # spec 08: XP lost per step

SKILL_FACT_UP = "Your {name} skill is now level {level}."  # spec 08
SKILL_FACT_DOWN = "Your {name} has dropped to level {level}."  # spec 08

STRENGTH_TRAITS = ("weak", "feeble", "stout", "strong")  # spec 08
FITNESS_TRAITS = ("unfit", "out_of_shape", "fit", "athletic")  # spec 08
TRAIT_BY_LEVEL = {  # spec 08: (low level, high level) -> trait id, None for no trait
    "strength": ((1, "weak"), (4, "feeble"), (5, None), (8, "stout"), (10, "strong")),
    "fitness": ((1, "unfit"), (4, "out_of_shape"), (5, None), (8, "fit"), (10, "athletic")),
}

FAST_LEARNER_ID = "fastlearner"  # spec 08
SLOW_LEARNER_ID = "slowlearner"  # spec 08
RELUCTANT_FIGHTER_ID = "pacifist"  # spec 08
CRAFTY_ID = "crafty"  # spec 08

ENDURANCE_RECOVERY_BY_FITNESS = (0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.55, 1.6)  # spec 08
DEFAULT_FITNESS_LEVEL = 5  # spec 08: Fitness of a character with no skills recorded
FITNESS_STAT_DIVISOR = 5  # spec 08: fitness stat is level / 5 - 1

LEVEL_WORDS = (  # spec 08: (highest level, word)
    (2, "novice"),
    (4, "capable"),
    (6, "skilled"),
    (8, "expert"),
    (10, "master"),
)
