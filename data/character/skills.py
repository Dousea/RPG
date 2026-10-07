"""The skill list, XP tables and the numbers that move XP (skills)."""

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

SKILLS: dict[str, Skill] = {row.id: row for row in _ROWS}  # skills: 35 skills

FITNESS = "fitness"
STRENGTH = "strength"
CARPENTRY = "carpentry"  # doors
RUNNING = "running"
AXE = "axe"  # zombies
LIGHTFOOTED = "lightfooted"  # zombies
NIMBLE = "nimble"  # zombies
SNEAKING = "sneaking"  # zombies
PASSIVE_SKILLS = (FITNESS, STRENGTH)  # skills

MAX_LEVEL = 10  # skills
XP_PER_LEVEL = (75, 150, 300, 750, 1500, 3000, 4500, 6000, 7500, 9000)  # skills: XP
XP_PER_LEVEL_PASSIVE = (  # skills: XP
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


BOOST_MULTIPLIER = {0: 0.25, 1: 1.0, 2: 1.33, 3: 1.66}  # skills: factor by boost
RUNNING_BOOST_ONE_MULTIPLIER = 1.25  # skills
FAST_LEARNER_MULT = 1.3  # skills
SLOW_LEARNER_MULT = 0.7  # skills
RELUCTANT_FIGHTER_MULT = 0.75  # skills
CRAFTY_MULT = 1.3  # skills
GLOBAL_XP_MULTIPLIER = 1.0  # skills
RELUCTANT_FIGHTER_SKILLS = (  # skills
    "axe",
    "long_blunt",
    "short_blunt",
    "long_blade",
    "short_blade",
    "spear",
    "aiming",
)

HIT_FITNESS_XP = 1.0  # skills: XP per hit
HIT_FITNESS_ENDURANCE_ABOVE = 0.5  # skills: endurance
EXHAUSTION_FITNESS_XP_PER_TICK = 6.0  # skills: 36 XP per game hour in 10-minute ticks
EXHAUSTION_ENDURANCE_BELOW = 0.25  # skills: endurance

TICK_MINUTES = 10  # skills: the boundary the loss timers run on
LOSS_TIMER_START = -50000  # skills
LOSS_TIMER_STEP_PER_TICK = 10  # skills
LOSS_TIMER_GAIN_DROP = 3000  # skills
LOSS_TIMER_ACTIVE_ABOVE = 20000  # skills
LOSS_TIMER_DIVISOR = 1200  # skills
LOSS_TIMER_RESET_ABOVE = 31000  # skills
LOSS_XP = 1.0  # skills: XP lost per step

SKILL_FACT_UP = "Your {name} skill is now level {level}."  # skills
SKILL_FACT_DOWN = "Your {name} has dropped to level {level}."  # skills

STRENGTH_TRAITS = ("weak", "feeble", "stout", "strong")  # skills
FITNESS_TRAITS = ("unfit", "out_of_shape", "fit", "athletic")  # skills
TRAIT_BY_LEVEL = {  # skills: (low level, high level) -> trait id, None for no trait
    "strength": ((1, "weak"), (4, "feeble"), (5, None), (8, "stout"), (10, "strong")),
    "fitness": ((1, "unfit"), (4, "out_of_shape"), (5, None), (8, "fit"), (10, "athletic")),
}

FAST_LEARNER_ID = "fastlearner"  # skills
SLOW_LEARNER_ID = "slowlearner"  # skills
RELUCTANT_FIGHTER_ID = "pacifist"  # skills
CRAFTY_ID = "crafty"  # skills

ENDURANCE_RECOVERY_BY_FITNESS = (0.7, 0.8, 0.9, 1.0, 1.1, 1.2, 1.3, 1.4, 1.5, 1.55, 1.6)  # skills
DEFAULT_FITNESS_LEVEL = 5  # skills: Fitness of a character with no skills recorded
FITNESS_STAT_DIVISOR = 5  # skills: fitness stat is level / 5 - 1

LEVEL_WORDS = (  # skills: (highest level, word)
    (2, "novice"),
    (4, "capable"),
    (6, "skilled"),
    (8, "expert"),
    (10, "master"),
)
