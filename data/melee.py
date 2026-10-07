"""Melee combat: the damage chain's tables, constants and fact wording (spec 11)."""

from modules.character.equipment import CharacterHoldableSlot
from modules.item import MeleeWeaponItem

CRIT_CLAMP_MIN = 10  # spec 11: percent
CRIT_CLAMP_MAX = 90  # spec 11: percent
CRIT_PER_SKILL_LEVEL = 3  # spec 11: percent per level
SHOVE_CRIT_BASE = 35  # spec 11: percent
SHOVE_CRIT_PER_STRENGTH = 2  # spec 11: percent per level
BEHIND_FACING_COS = -0.6  # spec 11: cos
BEHIND_CRIT_BONUS = 5  # spec 11: percent
BEHIND_CRIT_BONUS_BARE_UNAWARE = 30  # spec 11: percent
MIN_CRIT_MULTIPLIER = 2  # spec 11

STRENGTH_DAMAGE_MOD = (0.75, 0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.25)  # spec 11
SKILL_DAMAGE_MOD_MID = 1.1  # spec 11: weapon skill level 3 to 6
SKILL_DAMAGE_MOD_HIGH = 1.2  # spec 11: weapon skill level 7 and up
SKILL_DAMAGE_MOD_MID_LEVEL = 3  # spec 11
SKILL_DAMAGE_MOD_HIGH_LEVEL = 7  # spec 11
HIT_SPLIT_DIVISOR_PER_N = 0.5  # spec 11
TIRED_FACTOR = (1.0, 0.5, 0.2, 0.1, 0.05)  # spec 11: by status effect level 0 to 4
STOMP_ROLL_MIN = 0.7  # spec 11
STOMP_ROLL_MAX = 1.0  # spec 11
STOMP_STRENGTH_BONUS = 0.2  # spec 11: per Strength level
BAREFOOT_STOMP_POWER = 0.5  # spec 11
HEAD_HIT_MULTIPLIER = 3  # spec 11
HITS_TAKEN_RAMP_FROM = 4  # spec 11: hit count
HITS_TAKEN_RAMP_FACTOR = 1.5  # spec 11
HITS_TAKEN_RAMP_OFFSET = 2  # spec 11
NOT_FACING_MULTIPLIER = 1.5  # spec 11
NOT_FACING_COS = 0.3  # spec 11
NON_PLAYER_RECEIVED_DAMAGE_MULTIPLIER = 1.5  # spec 11
BASE_WEAPON_DAMAGE_MULTIPLIER = 0.3  # spec 11
WEAPON_LEVEL_DAMAGE_STEP = 0.1  # spec 11: per level
FLOOR_ATTACK_MIN_CRIT_MULTIPLIER = 5  # spec 11
GLOBAL_MELEE_DAMAGE_REDUCTION_MULTIPLIER = 0.15  # spec 11
REACH_TILES = 1.0  # spec 11: every weapon's reach falls in the one-tile band
REACH_FACTOR_PER_TILE = 2.0  # spec 11

DOWN_MINUTES = 2  # spec 11: down this minute and the next

STUCK_KNIFE_BASE_ATTACKING = 3  # spec 11
STUCK_KNIFE_BASE_OTHER = 8  # spec 11
STUCK_KNIFE_PER_SHORT_BLADE = 2  # spec 11
KNIFE_DEATH_REACH_MULTIPLIER = 1000  # spec 11
ENDURANCE_LOSS_CLOSE_KILL_MODIFIER = 0.2  # spec 11
CLOSE_KILL_MAX_HUNTERS = 1  # spec 11: zombies chasing or attacking

SWING_ENDURANCE_WEIGHT_FACTOR = 0.18  # spec 11
SWING_ENDURANCE_MIN_WEIGHT = 1  # spec 11: kg
HIT_ENDURANCE_WEIGHT_FACTOR = 0.28  # spec 11
ENDURANCE_LOSS_SCALE = 0.3 * 0.04  # spec 11
ENDURANCE_LOSS_FLOOR_SHOVE_MULTIPLIER = 2  # spec 11: a stomp
ASTHMATIC_ENDURANCE_MULTIPLIER = 1.2  # spec 11
WEAPON_FATIGUE_MOD_LEVEL8 = 0.8  # spec 11: at level 8 and up
WEAPON_FATIGUE_LEVEL = 8  # spec 11
FITNESS_FATIGUE_MOD = (1.0, 0.95, 0.92, 0.89, 0.87, 0.85, 0.83, 0.81, 0.79, 0.77, 0.75)  # spec 11

KILL_STRESS_DELTA = -0.02  # spec 11: stress

HIT_XP_CATEGORY_CAP = 3.0  # spec 11: XP
HIT_XP_SPLIT_FACTOR = 0.9  # spec 11
MAINTENANCE_XP_CHANCE = 50  # spec 11: percent
MAINTENANCE_XP_FIXED = 2  # spec 11: XP
MAINTENANCE_XP_NUMERATOR = 20  # spec 11: 20 / condition_lower_chance when above 10
MAINTENANCE_XP_NUMERATOR_MIN = 10  # spec 11
KNOCKBACK_STRENGTH_XP = 2  # spec 11: XP

HIT_SOUND_ANY = 5  # spec 11: radius, volume 1
HIT_SOUND_ANY_VOLUME = 1  # spec 11
HIT_SOUND_BASE = 8  # spec 11: radius = volume
HIT_SOUND_LOUD = 10  # spec 11
HIT_SOUND_LOUD_ODDS = 3  # spec 11: one in
HIT_SOUND_LOUDER = 16  # spec 11
HIT_SOUND_LOUDER_ODDS = 7  # spec 11: one in
HIT_SOUND_STAB = 4  # spec 11

CONDITION_WORD_BANDS = ((0.75, "good"), (0.4, "worn"))  # spec 11: fraction of condition_max
CONDITION_WORD_BADLY_WORN = "badly worn"  # spec 11
CONDITION_WORD_BROKEN = "broken"  # spec 11

NPC_BARE_DAMAGE = 2  # spec 11: HP
NPC_BAT_DAMAGE = 5  # spec 11: HP
NPC_PAN_DAMAGE = 2  # spec 11: HP
NPC_AXE_DAMAGE = 6  # spec 11: HP
TAG_REPAIRABLE_WITH_GLUE = "repairable_with_glue"  # spec 11
TAG_REPAIRABLE_WITH_TAPE = "repairable_with_tape"  # spec 11
TAG_SHARPENABLE = "sharpenable"  # spec 11

SHARPNESS = 1.0  # spec 11: stays 1 until the weapon upkeep spec
SHARPNESS_MULT = 1.0  # spec 11: stays 1 until the weapon upkeep spec
ARMS_PAIN_DIVISOR = 1.0  # spec 11: stays 1 until the arm injuries spec
ARM_SPEED_FACTOR = 1.0  # spec 11: stays 1 until the arm injuries spec

CATEGORY_AXE = "axe"
CATEGORY_BLUNT = "blunt"
CATEGORY_SMALL_BLUNT = "smallblunt"
CATEGORY_LONG_BLADE = "longblade"
CATEGORY_SMALL_BLADE = "smallblade"
CATEGORY_SPEAR = "spear"
CATEGORY_SKILL = {  # spec 11: the skill each weapon category trains
    CATEGORY_AXE: "axe",
    CATEGORY_BLUNT: "long_blunt",
    CATEGORY_SMALL_BLUNT: "short_blunt",
    CATEGORY_LONG_BLADE: "long_blade",
    CATEGORY_SMALL_BLADE: "short_blade",
    CATEGORY_SPEAR: "spear",
}
CRIT_SKILL_ORDER = (  # spec 11: later entries replace earlier ones; the first is the default
    CATEGORY_BLUNT,
    CATEGORY_AXE,
    CATEGORY_LONG_BLADE,
    CATEGORY_SPEAR,
    CATEGORY_SMALL_BLADE,
    CATEGORY_SMALL_BLUNT,
)
WEAPON_LEVEL_CATEGORIES = (CATEGORY_AXE, CATEGORY_BLUNT, CATEGORY_SPEAR)  # spec 11
SHORT_BLADE_SKILL = "short_blade"
MAINTENANCE_SKILL = "maintenance"

BARE_HANDS = MeleeWeaponItem(  # spec 11
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

HIT_FACT = "{name} hits {target} with the {weapon} and it staggers back."  # spec 11
HIT_KILL_FACT = "{name} hits {target} with the {weapon}."  # spec 11
CRIT_FACT = "A crushing blow: {target} goes down."  # spec 11
SHOVE_FACT = "{name} shoves {target} back."  # spec 11
SHOVE_DOWN_FACT = "{name} shoves {target} off its feet."  # spec 11
STOMP_FACT = "{name} stomps on {target}'s head."  # spec 11
FLOOR_ATTACK_FACT = "{name} brings the {weapon} down on {target}'s head."  # spec 11
JAW_STAB_FACT = "The knife goes in under {target}'s jaw."  # spec 11
KILL_FACT = "{target} goes still."  # spec 11
STUCK_KNIFE_FACT = "The knife stays lodged in {target}'s jaw and falls with it."  # spec 11
WEAR_FACTS = {  # spec 11: the word the weapon's condition has just reached
    "worn": "The {weapon} is getting worn.",
    "badly worn": "The {weapon} is badly worn.",
}
BREAK_FACT = "The {weapon} snaps."  # spec 11
EQUIP_FACT = "{name} takes the {item} in hand."  # spec 11
UNEQUIP_FACT = "{name} puts the {item} away."  # spec 11


def condition_word(condition: int, condition_max: int) -> str:
    """A weapon's wear in words, by its share of full condition."""
    if condition <= 0:
        return CONDITION_WORD_BROKEN
    share = condition / condition_max
    for floor, word in CONDITION_WORD_BANDS:
        if share >= floor:
            return word
    return CONDITION_WORD_BADLY_WORN
