"""The exercises and the numbers behind reps, regularity and stiffness (skills)."""

from modules.body.parts import BodyPart
from modules.character.exercise import ExerciseDefinition as Ex

BARBELL_ID = "item_barbell"  # skills
DUMBBELL_ID = "item_dumbbell"  # skills

_ROWS = [
    Ex("squats", "Squats", ("legs",), False, 1.0, 3.0),
    Ex("push_ups", "Push-ups", ("arms", "chest"), False, 1.0, 1.3),
    Ex("sit_ups", "Sit-ups", ("abs",), False, 1.0, 1.3),
    Ex("burpees", "Burpees", ("legs", "arms", "chest"), True, 0.8, 2.4),
    Ex("barbell_curls", "Barbell curls", ("arms", "chest"), True, 1.2, 2.2, BARBELL_ID),
    Ex("dumbbell_press", "Dumbbell press", ("arms",), True, 1.8, 1.5, DUMBBELL_ID),
    Ex("biceps_curls", "Biceps curls", ("arms",), True, 1.8, 1.9, DUMBBELL_ID),
]  # skills: the 7 exercises

EXERCISES: dict[str, Ex] = {row.id: row for row in _ROWS}


def _fold(name: str) -> str:
    return name.strip().strip("\"'.,;:").casefold().replace("-", "_").replace(" ", "_")


def find_exercise(name: str) -> Ex | None:
    """The exercise a name points to, ignoring case, hyphens and spaces."""
    folded = _fold(name)
    for exercise in EXERCISES.values():
        if folded in (exercise.id, _fold(exercise.name)):
            return exercise
    return None


REGION_PARTS = {  # skills
    "arms": (
        BodyPart.FOREARM_L,
        BodyPart.FOREARM_R,
        BodyPart.UPPERARM_L,
        BodyPart.UPPERARM_R,
    ),
    "legs": (
        BodyPart.UPPERLEG_L,
        BodyPart.UPPERLEG_R,
        BodyPart.LOWERLEG_L,
        BodyPart.LOWERLEG_R,
    ),
    "chest": (BodyPart.TORSO_UPPER,),
    "abs": (BodyPart.TORSO_LOWER,),
}

EXERCISE_MINUTES_MIN = 10  # skills: min
EXERCISE_MINUTES_MAX = 60  # skills: min
EXERCISE_MINUTES_STEP = 10  # skills: min
EXERCISE_MINUTES_DEFAULT = 10  # skills: min

REP_SECONDS_PER_GAME_MINUTE = 3.75  # skills: s
SPEED_MAX = 1.5  # skills: factor
SPEED_STRUGGLE_BELOW = 0.85  # skills: factor
SPEED_STRUGGLE_VALUE = 1.0  # skills: factor
SPEED_FITNESS_DIVISOR = 5.0  # skills
SPEED_FITNESS_SCALE = 1.1  # skills
SPEED_ENDURANCE_DIVISOR = 20.0  # skills
EXERCISE_ENDURANCE_STOP_LEVEL = 2  # skills: status effect level; above it refuses and stops

REGULARITY_GAIN = 0.08  # skills: per rep
REGULARITY_LOG_NUMERATOR = 5.0  # skills
REGULARITY_FITNESS_DIVISOR = 5.0  # skills
REGULARITY_FITNESS_OFFSET = 4.0  # skills
REGULARITY_MAX = 100.0  # skills
ENDURANCE_PER_REP = 0.015  # skills: per rep
ENDURANCE_REGULARITY_DIVISOR = 50.0  # skills
ENDURANCE_REGULARITY_OFFSET = 50.0  # skills
ENDURANCE_LOG_BASE_ARG = 51.0  # skills
HEAVY_FACTOR = 1.3  # skills
STIFFNESS_PER_REP = 0.5  # skills: per rep
STIFFNESS_REGULARITY_BASE = 120.0  # skills
STIFFNESS_REGULARITY_DIVISOR = 170.0  # skills
STIFFNESS_CAP = 150.0  # skills
TIRED_STIFFNESS_DIVISOR = 3  # skills: integer division, a kept quirk

XP_ARMS_STRENGTH = 4.0  # skills: XP per rep
XP_CHEST_STRENGTH = 2.0  # skills: XP per rep
XP_LEGS_FITNESS = 4.0  # skills: XP per rep
XP_ABS_FITNESS = 2.0  # skills: XP per rep

REGULARITY_DECAY = 0.002  # skills: per 10-minute tick
REGULARITY_GRACE_HOURS = 24  # skills: hours
STIFFNESS_TIMER_TICKS = 72  # skills: ticks of 10 minutes
STIFFNESS_PER_UNIT = 2.5  # skills: stiffness per drained unit
STIFFNESS_DRAIN_PER_TICK = 1.0  # skills: units per tick

STARTING_REGULARITY = {  # skills: occupation id -> (min, max excluded)
    "fireofficer": (10, 20),
    "fitnessinstructor": (40, 60),
    "securityguard": (7, 12),
}
