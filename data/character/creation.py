"""Rules and limits of character creation (character-creation)."""

MIN_POINTS_TO_ACCEPT = 0  # character-creation: points
BASE_FITNESS = 5  # character-creation: skill level
BASE_STRENGTH = 5  # character-creation: skill level
SKILL_LEVEL_MIN = 0  # character-creation
SKILL_LEVEL_MAX = 10  # character-creation
SKILL_BOOST_CAP = 3  # character-creation
NAME_MAX_CHARS = 20  # character-creation
JOB_TITLE_MAX_CHARS = 40  # character-creation
BACKSTORY_MAX_CHARS = 200  # character-creation
SKIN_TONE_MIN = 1  # character-creation
SKIN_TONE_MAX = 5  # character-creation
RANDOM_TRAITS_PER_SIDE_MIN = 1  # character-creation: traits, good and bad each
RANDOM_TRAITS_PER_SIDE_MAX = 5  # character-creation
RANDOM_ADJUST_ROUNDS_MAX = 1000  # character-creation: rounds
RANDOM_POINTS_MIN = 0  # character-creation: points left
RANDOM_POINTS_MAX = 3  # character-creation: points left
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
)  # character-creation: the skills occupations and traits can boost
