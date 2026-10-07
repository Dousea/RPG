"""Zombie settings, population and zone numbers (spec 09)."""

from data.character.traits import (
    BRAVE_ID,
    COWARDLY_ID,
    DESENSITIZED_ID,
    PRONE_TO_ILLNESS_ID,
    RESILIENT_ID,
)
from modules.body.parts import BodyPart
from modules.units import per_minute_from_frame

HOP_TILES = 40  # spec 09: every zone connection

ZOMBIE_STRENGTH = 3  # spec 09
ZOMBIE_MEMORY_FRAMES = 800  # spec 09
SPAWN_CLEARED_ZONE_IDS = ("zone_home",)  # spec 09: the spawn building starts clear

FRAMES_PER_MINUTE = 180  # spec 09

POPULATION_MULTIPLIER = 0.65  # spec 09
POPULATION_START_MULTIPLIER = 1.0  # spec 09
POPULATION_PEAK_MULTIPLIER = 1.5  # spec 09
POPULATION_PEAK_DAY = 28  # spec 09: days
PER_CHUNK_BASE = 0.06  # spec 09: zombies per chunk
PER_CHUNK_SCALE = 11.94  # spec 09: zombies per chunk
INTENSITY_HALF_FACTOR = 0.5  # spec 09
INTENSITY_MAX = 255  # spec 09
REDISTRIBUTE_HOURS = 12  # spec 09: game hours

# zone id -> (size_tiles, chunks, zombie_intensity)
ZONE_ZOMBIE_FIELDS: dict[str, tuple[int, int, int]] = {  # spec 09
    "zone_home": (8, 1, 0),
    "zone_building": (20, 3, 32),
    "zone_street": (40, 6, 96),
    "zone_bodega": (10, 1, 63),
    "zone_neighborhood": (80, 16, 64),
    "zone_flat_vacant": (8, 1, 0),  # spec 25
    "zone_flat_tenant": (8, 1, 64),  # spec 25
    "zone_pharmacy": (14, 2, 63),  # spec 25
    "zone_clinic": (20, 3, 48),  # spec 25
    "zone_supermarket": (30, 6, 63),  # spec 25
    "zone_hardware": (20, 3, 63),  # spec 25
}

STANDING_HIT_PARTS = (  # spec 14: a weapon hit or shove on a standing zombie lands on one, uniformly
    BodyPart.HAND_L,
    BodyPart.HAND_R,
    BodyPart.FOREARM_L,
    BodyPart.FOREARM_R,
    BodyPart.UPPERARM_L,
    BodyPart.UPPERARM_R,
    BodyPart.TORSO_UPPER,
    BodyPart.TORSO_LOWER,
    BodyPart.HEAD,
    BodyPart.NECK,
)
FLOOR_HIT_PARTS = (BodyPart.HEAD, BodyPart.NECK)  # spec 14: a floor attack or stomp
ZOMBIE_ARMOUR_FACTOR = 2  # spec 14: multiplier on a part's defence
ZOMBIE_MAX_DEFENCE = 85  # spec 14: percent
ZOMBIE_SCRATCH_WEIGHT = 0.5  # spec 14: in (scratch x 0.5 + bite) x 2
ZOMBIE_PART_DEFENCE_CAP = 100  # spec 14: the scratch and the bite sum of a part

CRAWLER_ONE_IN_WEAPON = 30  # spec 14: per weapon hit that does not kill
CRAWLER_ONE_IN_STOMP = 15  # spec 14: per bare-handed stomp that does not kill
CRAWLER_SPEED_MOD_BASE = 0.3  # spec 14
CRAWLER_ATTACK_NOTHING_ONE_IN = 2  # spec 14: half its attacks do nothing
CRAWLER_GROIN_ONE_IN = 10  # spec 14: groin to foot, else thigh to foot
CRAWL_FACT = "{target} drops to the ground and starts to crawl."  # spec 14
CRAWLER_STATE_WORDS = {  # spec 14
    "idle": "crawling",
    "alerted": "crawling toward the noise",
    "chasing": "crawling toward you",
    "attacking": "crawling",
}

CORPSE_CHUNK_CHANCE_FACTOR = 2 / 3 * 0.1  # spec 14: of the per-chunk zombie count
CORPSE_SKELETON_ONE_IN = 14  # spec 14: 1 in 14
CORPSE_FAKE_DEAD_ONE_IN = 15  # spec 14: of the bodies that are not skeletons
CORPSE_FAKE_DEAD_CRAWLER_ONE_IN = 5  # spec 14: of the fake-dead ones
CORPSE_RANDOM_HOLES = 10  # spec 14: per dressed outbreak corpse
BODY_PART_COUNT = len(BodyPart)  # spec 14: a random hole picks one of the 17
ROT_STAGE_HOURS = 72  # spec 14: game hours per rot stage
HOURS_FOR_CORPSE_REMOVAL = 216  # spec 14: game hours
SKELETON_ROT_ONE_IN = 7  # spec 14: a body past removal age may turn to bones instead
SKELETON_REMOVAL_EXTRA_HOURS = 72  # spec 14: game hours
ROT_STAGE_MAX = 3  # spec 14
ROT_FRESH_DAYS = 20  # spec 14: days since the outbreak when every kill is still stage 1
ROT_MID_DAYS = 90  # spec 14: days when the chances stop moving
ROT_LATE_DAYS = 180  # spec 14: days when stage 1 is gone
ROT_STAGE1_START, ROT_STAGE1_MID, ROT_STAGE1_LATE = 100, 20, 0  # spec 14: percent
ROT_STAGE2_START, ROT_STAGE2_MID, ROT_STAGE2_LATE = 10, 30, 10  # spec 14: percent
ROT_WORDS = {1: "fresh", 2: "decaying", 3: "rotten"}  # spec 14
SKELETON_WORD = "bare bones"  # spec 14

FAKE_DEAD_WAKEUP_MIN = 30  # spec 14: minutes after it died
FAKE_DEAD_RING_TILES = (2, 4)  # spec 14: the player must be this far from the body
RISE_FACT = "A body on the ground lurches to its feet."  # spec 14
RISE_CRAWLING_FACT = (
    "A body on the ground twitches and starts to drag itself across the floor."  # spec 14
)

CORPSE_STRIP_UNHAPPINESS_PER_MIN = per_minute_from_frame(
    0.01
)  # spec 14: unhappiness points per minute of taking an item
STRIP_UNHAPPINESS_TRAIT_MULT = {COWARDLY_ID: 2.0, BRAVE_ID: 0.5, DESENSITIZED_ID: 0.0}  # spec 14
LOOT_ROLL_STEPS = 10000  # spec 14: the pocket roll is a whole number below this
SEARCH_FACT = "{name} goes through {corpse}: {items}."  # spec 14
SEARCH_NOTHING = "nothing"  # spec 14
TAKE_CORPSE_FACT = "{name} takes the dead {sex}'s {item}."  # spec 14
DEAD_MAN, DEAD_WOMAN = "man", "woman"  # spec 14
CORPSE_GONE_FACT = "{name} gets to where {corpse} lay, but the body is gone."  # spec 14
ALREADY_SEARCHED = "{name} has already been through {corpse}."  # spec 14
NOT_SEARCHED = "{name} hasn't been through {corpse} yet."  # spec 14
NO_SUCH_CORPSE = "'{target}' is not here to search."  # spec 14
NOT_ON_CORPSE = "{corpse} holds no '{item}'."  # spec 14
ASLEEP_REFUSAL = "{name} is asleep."  # spec 14
MAN_WORD, WOMAN_WORD = "a man", "a woman"  # spec 14
CORPSE_LOOK_ITEMS = 3  # spec 14: garments named in a corpse's description

CORPSE_COUNT_MAX = 25  # spec 14: bodies counted for corpse sickness
SMELL_FACT = "The smell of the dead hangs thick here."  # spec 14

REANIMATE_DELAY_MAX_MIN = 1.0  # spec 14: the player's body rises within this many minutes

FEMALE_ONE_IN = 2  # spec 14: 50% female
CHANCE_OF_ATTACHED_WEAPON = 6  # spec 14: percent
ATTACHED_CONDITION_SPREAD = 5  # spec 14: condition from max(2, max - 5) up to max, exclusive
ATTACHED_CONDITION_FLOOR = 2  # spec 14

HEALTH_BASE_MIN = 0.5  # spec 09
HEALTH_BASE_MAX = 3.5  # spec 09
HEALTH_BONUS_MAX = 0.3  # spec 09
SPEED_TYPE_SHAMBLER = 3  # spec 09
SPEED_TYPE_FAST_SHAMBLER = 2  # spec 09
SHAMBLER_SPEED_MOD_BASE = 0.55  # spec 09
LUNGER_SPEED_MOD_BASE = 0.85  # spec 09
SPEED_MOD_STEPS = 1500  # spec 09: the roll is a whole number below this, over 10000
SPEED_MOD_DIVISOR = 10000  # spec 09
FAST_SHAMBLER_LUNGER_CHANCE = 1 / 3  # spec 09
SENSE_NORMAL = 2  # spec 09
SENSE_POOR = 3  # spec 09

PACE_SPEED_TILES_PER_MIN = {"walk": 4, "run": 8, "sneak": 2, "still": 0}  # spec 09
PACE_MOVEMENT_MOD = {
    "walk": 1.0,
    "run": 1.5,
    "sneak": 0.8,
    "still": 0.8,
}  # spec 09: spotting factor
WALK_APPROACH_TILES_PER_MIN = 4  # spec 09: closing on a target at walking pace

# Perk level 0-10.
LIGHTFOOT_MOD = (0.99, 0.90, 0.79, 0.71, 0.65, 0.59, 0.52, 0.45, 0.37, 0.30, 0.20)  # spec 09
NIMBLE_MOD = (1.00, 1.10, 1.14, 1.18, 1.22, 1.26, 1.30, 1.34, 1.38, 1.42, 1.50)  # spec 09
SNEAK_SPOT_BASE = (0.95, 0.90, 0.80, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50, 0.45, 0.40)  # spec 09
SNEAK_SPOT_FACTOR = 1.2  # spec 09

FOOTSTEP_PACE_SPEED = {"walk": 0.5, "run": 0.75, "sneak": 0.25}  # spec 09
FOOTSTEP_VOLUME_FACTOR = 1.4  # spec 09
GRACEFUL_VOLUME_FACTOR = 0.6  # spec 09
CLUMSY_VOLUME_FACTOR = 1.2  # spec 09
BAREFOOT_VOLUME_FACTOR = 0.5  # spec 09
INDOORS_RADIUS_FACTOR = 0.5  # spec 09
RADIUS_PER_VOLUME = 10  # spec 09
STEPS_PER_MOVING_MINUTE = 8  # spec 09
STEP_EMIT_ODDS = 2  # spec 09: one step in this many makes a sound
SNEAK_STEP_ODDS_BASE = 4  # spec 09
SNEAK_STEP_ODDS_CAP = 12  # spec 09
COUGH_RADIUS = 35  # spec 09: tiles
COUGH_VOLUME = 40  # spec 09
SHOUT_RADIUS = 30  # spec 10: tiles
SHOUT_VOLUME = 30  # spec 10
SHOUT_SNEAK_RADIUS = 6  # spec 10: tiles
SHOUT_SNEAK_VOLUME = 6  # spec 10
MEGAPHONE_SHOUT = 90  # spec 10: radius and volume, unused until the catalogue has a megaphone
MEGAPHONE_SHOUT_SNEAK = 18  # spec 10: radius and volume

CORPSE_SICKNESS_TRAIT_MULT = {RESILIENT_ID: 0.75, PRONE_TO_ILLNESS_ID: 1.25}  # spec 14

HEARING_POOR_FACTOR = 0.45  # spec 09
HEARING_RAIN_FACTOR = 0.33  # spec 09
HEARING_FOG_FACTOR = 0.1  # spec 09
HEARING_OTHER_ZONE_FACTOR = 1.2  # spec 09
HEARING_INDOOR_MISMATCH_FACTOR = 1.4  # spec 09

UNLIT_INDOOR_LIGHT = 0.6  # spec 09: factor on daylight indoors without power
VISION_RADIUS = 20  # spec 09: tiles
VISION_RADIUS_MIN = 10  # spec 09: tiles
VISION_RADIUS_MAX = 20  # spec 09: tiles
VISION_DARK_TILES = 5  # spec 09: tiles lost at no light
VISION_RAIN_TILES = 2.5  # spec 09: tiles lost to full rain
VISION_FOG_TILES = 7  # spec 09: tiles lost to full fog
VISION_POOR_FACTOR = 0.35  # spec 09
FACING_BELOW = (
    (-0.4, 0.0),
    (-0.2, 1 / 8),
    (0.0, 1 / 4),
    (0.2, 1 / 2),
)  # spec 09: (cos below, factor)
FACING_UP_TO = ((0.4, 2.0), (0.6, 8.0), (0.8, 16.0))  # spec 09: (cos up to, factor)
FACING_ABOVE_FACTOR = 32.0  # spec 09
SPOT_NEAR_TILES = 5  # spec 09: tiles
SPOT_NEAR_FACTOR = 3.0  # spec 09
SPOT_BONUS_FACTOR = 5.0  # spec 09
SPOT_BONUS_FRAMES = 720  # spec 09
SPOT_POOR_SIGHT_FACTOR = 0.45  # spec 09
SPOT_CAP = 400  # spec 09
INCONSPICUOUS_SPOT_FACTOR = 0.8  # spec 09
CONSPICUOUS_SPOT_FACTOR = 1.2  # spec 09
SNEAK_XP_PER_FRAME_CHANCE = 1 / 1100  # spec 09
SNEAK_XP_CLOSE_CHANCE = 20  # spec 09: a raw spot chance above this counts as a close call
SNEAK_XP_CLOSE_TILES = 15  # spec 09: tiles
SNEAK_XP_AMOUNT = 1.0  # spec 09

HEARING_RANGE_BASE = 3.5  # spec 09: tiles the player hears a zombie at
HEARING_RANGE_DEAF = 2.0  # spec 09: tiles
HEARING_RANGE_KEEN = 3.0  # spec 09: tiles gained
HEARING_RANGE_HARD = 1.0  # spec 09: tiles lost
HEARING_RANGE_FLOOR = 2.0  # spec 09: tiles
HEARING_RANGE_INTOXICATION_PER_POINT = 0.01  # spec 09: tiles lost per point of intoxication
SIGHT_RANGE = 20  # spec 09: tiles the player sees a zombie at in full light
SIGHT_RANGE_MIN_LIGHT = 0.25  # spec 09: factor
CHASE_SPEED_TILES_PER_MIN = 4  # spec 09
CHASE_GAP_DIVISOR = 24  # spec 09: tiles
CHASE_GAP_FACTOR_MIN = 1.0  # spec 09
CHASE_GAP_FACTOR_MAX = 1.3  # spec 09
ATTACK_RANGE_TILES = 1  # spec 09: a zombie this close attacks

SPOTTED_FACT = "A zombie notices {name} and heads straight for {object}."  # spec 09
REACHED_FACT = "A zombie closes in on {name}."  # spec 09

DEFENCE_WEAPON_LEVEL_WEIGHT = 3  # spec 09
DEFENCE_FITNESS_WEIGHT = 2  # spec 09
DEFENCE_STRENGTH_WEIGHT = 2  # spec 09
DEFENCE_ATTACKER_PENALTY = 5  # spec 09: per attacker
DEFENCE_HEAVY_LOAD_PENALTY = 2  # spec 09: per Heavy Load level
DEFENCE_MAX_ATTACKERS = 3  # spec 09: no defence against more than this many
DRAG_DOWN_ATTACKERS = 3  # spec 09: at Normal zombie strength
MELEE_COMBAT_MOD = (-5, -2, 0, 1, 2, 3, 4, 5, 5, 6, 7)  # spec 09: by weapon level 0-10
WOUND_BASE = 15  # spec 09: percent
WOUND_BITE = 85  # spec 09: percent
WOUND_LACERATION = 65  # spec 09: percent
WOUND_BASE_PER_EXTRA_ATTACKER = 10  # spec 09: percent lost
WOUND_BITE_PER_EXTRA_ATTACKER = 30  # spec 09: percent lost
WOUND_LACERATION_PER_EXTRA_ATTACKER = 15  # spec 09: percent lost
BEHIND_BASE_PENALTY = 15  # spec 09: percent
BEHIND_BITE_PENALTY = 25  # spec 09: percent
BEHIND_LACERATION_PENALTY = 35  # spec 09: percent
BEHIND_CROWD_ATTACKERS = 2  # spec 09: more attackers than this
BEHIND_CROWD_PENALTY = 15  # spec 09: percent, on bite and laceration
SIDE_BASE_PENALTY = 30  # spec 09: percent
SIDE_BITE_PENALTY = 7  # spec 09: percent
SIDE_LACERATION_PENALTY = 27  # spec 09: percent
SKIN_FACTOR = 1.3  # spec 09: Thick Skinned multiplies the base, Thin Skinned divides it
BODY_PART_ROLL_WIDE = 11  # spec 09: Hand_L to Groin
BODY_PART_ROLL_NARROW = 10  # spec 09: Hand_L to Neck
BODY_PART_WIDE_ODDS = 10  # spec 09: 1 in this many rolls the wide range
BODY_PART_RETRY_RANGE = 8  # spec 09: Hand_L to Torso_Lower
NECK_FROM_BEHIND_PER_ATTACKER = 10  # spec 09: percent
NECK_FROM_BEHIND_BASE = 5  # spec 09: percent
HEAD_RETRY_ABOVE = {"front": 70, "left": 80, "right": 80, "behind": 90}  # spec 09: percent
DAMAGE_THOUSANDTHS = 1000  # spec 09
DAMAGE_STEPS = 10  # spec 09
DAMAGE_OFFSET = 10  # spec 09
ZOMBIE_INFECTION_CHANCE_PERCENT = {"scratch": 7, "laceration": 25, "bite": 100}  # spec 09
CLOTHING_DEFENCE_CAP = 100  # spec 09

BODY_PART_WORDS = {  # spec 09
    "hand_l": "left hand",
    "hand_r": "right hand",
    "forearm_l": "left forearm",
    "forearm_r": "right forearm",
    "upperarm_l": "left upper arm",
    "upperarm_r": "right upper arm",
    "torso_upper": "chest",
    "torso_lower": "stomach",
    "head": "head",
    "neck": "neck",
    "groin": "groin",
    "upperleg_l": "left thigh",
    "upperleg_r": "right thigh",
    "lowerleg_l": "left shin",
    "lowerleg_r": "right shin",
    "foot_l": "left foot",
    "foot_r": "right foot",
}
WOUND_VERBS = {"scratch": "scratches", "laceration": "tears into", "bite": "bites"}  # spec 09
DEFENDED_FACT = "{name} shoves the zombie off."  # spec 09
BLOCKED_FACT = "A zombie claws at {name}, but the clothing holds."  # spec 09
THUMP_FACT = "A zombie's blow glances off {name}."  # spec 09
WOUND_FACT = "A zombie {verb} {name}'s {part}."  # spec 09
DRAGGED_FACT = "{name} was dragged down by the dead."  # spec 09

DISTANCE_WORDS = ((1, "on you"), (5, "close"), (15, "nearby"))  # spec 09: (gap up to, word)
DISTANCE_WORD_FAR = "far off"  # spec 09
STATE_WORDS = {  # spec 09
    "idle": "hasn't noticed you",
    "alerted": "turning toward the noise",
    "chasing": "coming at you",
    "attacking": "attacking you",
}
STATE_WORD_FAST = "coming at you fast"  # spec 09: a lunger that has chased the player
STATE_WORD_BEHIND = "right behind you"  # spec 09
STATE_WORD_DOWN = "down"  # spec 11
STATE_WORD_THUMPING = "pounding"  # spec 13
THUMPER_SEEN_WORD = "behind the {barrier}"  # spec 13
THUMPER_HEARD_WORD = "something at the {barrier}"  # spec 13
HEARD_WORD_HUNTING = "something behind you"  # spec 09
HEARD_WORD_OTHER = "something shuffling nearby"  # spec 09
