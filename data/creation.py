"""Rules and limits of character creation (spec 07)."""

MIN_POINTS_TO_ACCEPT = 0  # spec 07: points
BASE_FITNESS = 5  # spec 07: skill level
BASE_STRENGTH = 5  # spec 07: skill level
SKILL_LEVEL_MIN = 0  # spec 07
SKILL_LEVEL_MAX = 10  # spec 07
SKILL_BOOST_CAP = 3  # spec 07
NAME_MAX_CHARS = 20  # spec 07
JOB_TITLE_MAX_CHARS = 40  # spec 07
BACKSTORY_MAX_CHARS = 200  # spec 07
SKIN_TONE_MIN = 1  # spec 07
SKIN_TONE_MAX = 5  # spec 07
RANDOM_TRAITS_PER_SIDE_MIN = 1  # spec 07: traits, good and bad each
RANDOM_TRAITS_PER_SIDE_MAX = 5  # spec 07
RANDOM_ADJUST_ROUNDS_MAX = 1000  # spec 07: rounds
RANDOM_POINTS_MIN = 0  # spec 07: points left
RANDOM_POINTS_MAX = 3  # spec 07: points left
RANDOM_BEARD_CHANCE = 50  # our rule: percent of random male characters with a beard

SKILLS = (
    "fitness",
    "strength",
    "aiming",
    "reloading",
    "nimble",
    "sneaking",
    "lightfooted",
    "running",
    "axe",
    "short_blade",
    "short_blunt",
    "long_blunt",
    "cooking",
    "maintenance",
    "tailoring",
    "first_aid",
    "agriculture",
    "animal_care",
    "butchering",
    "carpentry",
    "carving",
    "masonry",
    "electrical",
    "fishing",
    "foraging",
    "mechanics",
    "welding",
    "trapping",
    "knapping",
    "blacksmithing",
    "tracking",
    "glassmaking",
    "pottery",
)  # spec 07: the skills occupations and traits can boost
