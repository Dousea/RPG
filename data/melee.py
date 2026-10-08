"""Melee combat: the damage chain's tables, constants and fact wording (melee)."""

from modules.character.equipment import CharacterHoldableSlot
from modules.item import MeleeWeaponItem

CRIT_CLAMP_MIN = 10  # melee: percent
CRIT_CLAMP_MAX = 90  # melee: percent
CRIT_PER_SKILL_LEVEL = 3  # melee: percent per level
SHOVE_CRIT_BASE = 35  # melee: percent
SHOVE_CRIT_PER_STRENGTH = 2  # melee: percent per level
BEHIND_FACING_COS = -0.6  # melee: cos
BEHIND_CRIT_BONUS = 5  # melee: percent
BEHIND_CRIT_BONUS_BARE_UNAWARE = 30  # melee: percent
MIN_CRIT_MULTIPLIER = 2  # melee

STRENGTH_DAMAGE_MOD = (0.75, 0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.25)  # melee
SKILL_DAMAGE_MOD_MID = 1.1  # melee: weapon skill level 3 to 6
SKILL_DAMAGE_MOD_HIGH = 1.2  # melee: weapon skill level 7 and up
SKILL_DAMAGE_MOD_MID_LEVEL = 3  # melee
SKILL_DAMAGE_MOD_HIGH_LEVEL = 7  # melee
HIT_SPLIT_DIVISOR_PER_N = 0.5  # melee
TIRED_FACTOR = (1.0, 0.5, 0.2, 0.1, 0.05)  # melee: by status effect level 0 to 4
STOMP_ROLL_MIN = 0.7  # melee
STOMP_ROLL_MAX = 1.0  # melee
STOMP_STRENGTH_BONUS = 0.2  # melee: per Strength level
BAREFOOT_STOMP_POWER = 0.5  # melee
HEAD_HIT_MULTIPLIER = 3  # melee
HITS_TAKEN_RAMP_FROM = 4  # melee: hit count
HITS_TAKEN_RAMP_FACTOR = 1.5  # melee
HITS_TAKEN_RAMP_OFFSET = 2  # melee
NOT_FACING_MULTIPLIER = 1.5  # melee
NOT_FACING_COS = 0.3  # melee
NON_PLAYER_RECEIVED_DAMAGE_MULTIPLIER = 1.5  # melee
BASE_WEAPON_DAMAGE_MULTIPLIER = 0.3  # melee
WEAPON_LEVEL_DAMAGE_STEP = 0.1  # melee: per level
FLOOR_ATTACK_MIN_CRIT_MULTIPLIER = 5  # melee
GLOBAL_MELEE_DAMAGE_REDUCTION_MULTIPLIER = 0.15  # melee
REACH_TILES = 1.0  # melee: every weapon's reach falls in the one-tile band
REACH_FACTOR_PER_TILE = 2.0  # melee

SHOVE_HIT_COUNT_UNARMED = 1  # melee
SHOVE_HIT_COUNT_ARMED = 3  # melee: a weapon in hand
STOMP_HIT_COUNT = 1  # melee

PLAIN_ZOMBIE_WORDS = frozenset(  # melee: a target that reads as the plain zombie
    {"zombie", "the zombie", "a zombie", "zombies", "the zombies"}
    | {"them", "all of them", "the ones", "all the zombies", "all of the zombies"}
)
DOWN_TARGET_PATTERN = (  # melee: a target that names the zombies on the floor
    r"(?:the |all the |all of the )?"
    r"(?:(?:zombies?|ones?|them|crawlers?)(?: that (?:are|is))? (?:on the (?:floor|ground)|down)|crawlers?)"
)
DOWN_INPUT_PATTERN = (  # melee: the player's own words for the floor, or for a stomp
    r"\bon the (?:floor|ground)\b|\bcrawl(?:er|ers|ing)\b|\bstomp\w*"
)
DOWN_TARGET = "the ones on the floor"  # melee: how the engine writes a down target
NO_ZOMBIE_DOWN = "No zombie within reach is down."  # melee

DOWN_MINUTES = 2  # melee: down this minute and the next

STUCK_KNIFE_BASE_ATTACKING = 3  # melee
STUCK_KNIFE_BASE_OTHER = 8  # melee
STUCK_KNIFE_PER_SHORT_BLADE = 2  # melee
KNIFE_DEATH_REACH_MULTIPLIER = 1000  # melee
ENDURANCE_LOSS_CLOSE_KILL_MODIFIER = 0.2  # melee
CLOSE_KILL_MAX_HUNTERS = 1  # melee: zombies chasing or attacking

SWING_ENDURANCE_WEIGHT_FACTOR = 0.18  # melee
SWING_ENDURANCE_MIN_WEIGHT = 1  # melee: kg
HIT_ENDURANCE_WEIGHT_FACTOR = 0.28  # melee
ENDURANCE_LOSS_SCALE = 0.3 * 0.04  # melee
ENDURANCE_LOSS_FLOOR_SHOVE_MULTIPLIER = 2  # melee: a stomp
ASTHMATIC_ENDURANCE_MULTIPLIER = 1.2  # melee
WEAPON_FATIGUE_MOD_LEVEL8 = 0.8  # melee: at level 8 and up
WEAPON_FATIGUE_LEVEL = 8  # melee
FITNESS_FATIGUE_MOD = (1.0, 0.95, 0.92, 0.89, 0.87, 0.85, 0.83, 0.81, 0.79, 0.77, 0.75)  # melee

KILL_STRESS_DELTA = -0.02  # melee: stress

HIT_XP_CATEGORY_CAP = 3.0  # melee: XP
HIT_XP_SPLIT_FACTOR = 0.9  # melee
MAINTENANCE_XP_CHANCE = 50  # melee: percent
MAINTENANCE_XP_FIXED = 2  # melee: XP
MAINTENANCE_XP_NUMERATOR = 20  # melee: 20 / condition_lower_chance when above 10
MAINTENANCE_XP_NUMERATOR_MIN = 10  # melee
KNOCKBACK_STRENGTH_XP = 2  # melee: XP

HIT_SOUND_ANY = 5  # melee: radius, volume 1
HIT_SOUND_ANY_VOLUME = 1  # melee
HIT_SOUND_BASE = 8  # melee: radius = volume
HIT_SOUND_LOUD = 10  # melee
HIT_SOUND_LOUD_ODDS = 3  # melee: one in
HIT_SOUND_LOUDER = 16  # melee
HIT_SOUND_LOUDER_ODDS = 7  # melee: one in
HIT_SOUND_STAB = 4  # melee

CONDITION_WORD_BANDS = ((0.75, "good"), (0.4, "worn"))  # melee: fraction of condition_max
CONDITION_WORD_BADLY_WORN = "badly worn"  # melee
CONDITION_WORD_BROKEN = "broken"  # melee

NPC_BARE_DAMAGE = 2  # melee: HP
NPC_BAT_DAMAGE = 5  # melee: HP
NPC_PAN_DAMAGE = 2  # melee: HP
NPC_AXE_DAMAGE = 6  # melee: HP
TAG_REPAIRABLE_WITH_GLUE = "repairable_with_glue"  # melee
TAG_REPAIRABLE_WITH_TAPE = "repairable_with_tape"  # melee
TAG_SHARPENABLE = "sharpenable"  # melee

SHARPNESS = 1.0  # melee: stays 1 until the weapon upkeep spec
SHARPNESS_MULT = 1.0  # melee: stays 1 until the weapon upkeep spec
ARMS_PAIN_DIVISOR = 1.0  # melee: stays 1 until the arm injuries spec
ARM_SPEED_FACTOR = 1.0  # melee: stays 1 until the arm injuries spec

CATEGORY_AXE = "axe"
CATEGORY_BLUNT = "blunt"
CATEGORY_SMALL_BLUNT = "smallblunt"
CATEGORY_LONG_BLADE = "longblade"
CATEGORY_SMALL_BLADE = "smallblade"
CATEGORY_SPEAR = "spear"
CATEGORY_SKILL = {  # melee: the skill each weapon category trains
    CATEGORY_AXE: "axe",
    CATEGORY_BLUNT: "long_blunt",
    CATEGORY_SMALL_BLUNT: "short_blunt",
    CATEGORY_LONG_BLADE: "long_blade",
    CATEGORY_SMALL_BLADE: "short_blade",
    CATEGORY_SPEAR: "spear",
}
CRIT_SKILL_ORDER = (  # melee: later entries replace earlier ones; the first is the default
    CATEGORY_BLUNT,
    CATEGORY_AXE,
    CATEGORY_LONG_BLADE,
    CATEGORY_SPEAR,
    CATEGORY_SMALL_BLADE,
    CATEGORY_SMALL_BLUNT,
)
WEAPON_LEVEL_CATEGORIES = (CATEGORY_AXE, CATEGORY_BLUNT, CATEGORY_SPEAR)  # melee
SHORT_BLADE_SKILL = "short_blade"
MAINTENANCE_SKILL = "maintenance"

BARE_HANDS = MeleeWeaponItem(  # melee
    id="bare_hands",
    name="bare hands",
    description="No weapon, just hands.",
    max_hit_points=1,
    tags=["unarmed"],
    slots=[CharacterHoldableSlot.RIGHT_HAND],
    is_two_handed=False,
    damage=NPC_BARE_DAMAGE,
    min_damage=0.2,
    max_damage=0.4,
    max_range=1.1,
    max_hit_count=3,
    knockback_on_no_death=True,
    condition_max=1,
    condition_lower_chance=1,
    weight=1.0,
    endurance_mod=1.7,
    base_speed=0.9,
    door_damage=0,
    no_maintenance_xp=True,
)

HIT_FACT = "{name} hits {target} with the {weapon} and it staggers back."  # melee
HIT_KILL_FACT = "{name} hits {target} with the {weapon}."  # melee
CRIT_FACT = "A crushing blow: {target} goes down."  # melee
SHOVE_FACT = "{name} shoves {target} back."  # melee
SHOVE_DOWN_FACT = "{name} shoves {target} off its feet."  # melee
STOMP_FACT = "{name} stomps on {target}'s head."  # melee
FLOOR_ATTACK_FACT = "{name} brings the {weapon} down on {target}'s head."  # melee
JAW_STAB_FACT = "The knife goes in under {target}'s jaw."  # melee
KILL_FACT = "{target} goes still."  # melee
STUCK_KNIFE_FACT = "The knife stays lodged in {target}'s jaw and falls with it."  # melee
WEAR_FACTS = {  # melee: the word the weapon's condition has just reached
    "worn": "The {weapon} is getting worn.",
    "badly worn": "The {weapon} is badly worn.",
}
BREAK_FACT = "The {weapon} snaps."  # melee
EQUIP_FACT = "{name} takes the {item} in hand."  # melee
UNEQUIP_FACT = "{name} puts the {item} away."  # melee


def condition_word(condition: int, condition_max: int) -> str:
    """A weapon's wear in words, by its share of full condition."""
    if condition <= 0:
        return CONDITION_WORD_BROKEN
    share = condition / condition_max
    for floor, word in CONDITION_WORD_BANDS:
        if share >= floor:
            return word
    return CONDITION_WORD_BADLY_WORN
