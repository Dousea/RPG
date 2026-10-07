"""Zombie settings, population and zone numbers (zombies)."""

from data.character.traits import (
    BRAVE_ID,
    COWARDLY_ID,
    DESENSITIZED_ID,
    PRONE_TO_ILLNESS_ID,
    RESILIENT_ID,
)
from modules import units
from modules.body.parts import BodyPart

HOP_TILES = 40  # zombies: every zone connection

ZOMBIE_STRENGTH = 3  # zombies
ZOMBIE_MEMORY_FRAMES = 800  # zombies
SPAWN_CLEARED_ZONE_IDS = ("zone_home",)  # zombies: the spawn building starts clear

FRAMES_PER_MINUTE = 180  # zombies

POPULATION_MULTIPLIER = 0.65  # zombies
POPULATION_START_MULTIPLIER = 1.0  # zombies
POPULATION_PEAK_MULTIPLIER = 1.5  # zombies
POPULATION_PEAK_DAY = 28  # zombies: days
PER_CHUNK_BASE = 0.06  # zombies: zombies per chunk
PER_CHUNK_SCALE = 11.94  # zombies: zombies per chunk
INTENSITY_HALF_FACTOR = 0.5  # zombies
INTENSITY_MAX = 255  # zombies
REDISTRIBUTE_HOURS = 12  # zombies: game hours

# zone id -> (size_tiles, chunks, zombie_intensity)
ZONE_ZOMBIE_FIELDS: dict[str, tuple[int, int, int]] = {  # zombies
    "zone_home": (8, 1, 0),
    "zone_building": (20, 3, 32),
    "zone_street": (40, 6, 96),
    "zone_bodega": (10, 1, 63),
    "zone_neighborhood": (80, 16, 64),
    "zone_flat_vacant": (8, 1, 0),  # carrying-and-loot
    "zone_flat_tenant": (8, 1, 64),  # carrying-and-loot
    "zone_pharmacy": (14, 2, 63),  # carrying-and-loot
    "zone_clinic": (20, 3, 48),  # carrying-and-loot
    "zone_supermarket": (30, 6, 63),  # carrying-and-loot
    "zone_hardware": (20, 3, 63),  # carrying-and-loot
}

STANDING_HIT_PARTS = (  # zombie-lifecycle: a weapon hit or shove on a standing zombie lands on one, uniformly
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
FLOOR_HIT_PARTS = (BodyPart.HEAD, BodyPart.NECK)  # zombie-lifecycle: a floor attack or stomp
ZOMBIE_ARMOUR_FACTOR = 2  # zombie-lifecycle: multiplier on a part's defence
ZOMBIE_MAX_DEFENCE = 85  # zombie-lifecycle: percent
ZOMBIE_SCRATCH_WEIGHT = 0.5  # zombie-lifecycle: in (scratch x 0.5 + bite) x 2
ZOMBIE_PART_DEFENCE_CAP = 100  # zombie-lifecycle: the scratch and the bite sum of a part

CRAWLER_ONE_IN_WEAPON = 30  # zombie-lifecycle: per weapon hit that does not kill
CRAWLER_ONE_IN_STOMP = 15  # zombie-lifecycle: per bare-handed stomp that does not kill
CRAWLER_SPEED_MOD_BASE = 0.3  # zombie-lifecycle
CRAWLER_ATTACK_NOTHING_ONE_IN = 2  # zombie-lifecycle: half its attacks do nothing
CRAWLER_GROIN_ONE_IN = 10  # zombie-lifecycle: groin to foot, else thigh to foot
CRAWL_FACT = "{target} drops to the ground and starts to crawl."  # zombie-lifecycle
CRAWLER_STATE_WORDS = {  # zombie-lifecycle
    "idle": "crawling",
    "alerted": "crawling toward the noise",
    "chasing": "crawling toward you",
    "attacking": "crawling",
}

CORPSE_CHUNK_CHANCE_FACTOR = 2 / 3 * 0.1  # zombie-lifecycle: of the per-chunk zombie count
CORPSE_SKELETON_ONE_IN = 14  # zombie-lifecycle: 1 in 14
CORPSE_FAKE_DEAD_ONE_IN = 15  # zombie-lifecycle: of the bodies that are not skeletons
CORPSE_FAKE_DEAD_CRAWLER_ONE_IN = 5  # zombie-lifecycle: of the fake-dead ones
CORPSE_RANDOM_HOLES = 10  # zombie-lifecycle: per dressed outbreak corpse
BODY_PART_COUNT = len(BodyPart)  # zombie-lifecycle: a random hole picks one of the 17
ROT_STAGE_HOURS = 72  # zombie-lifecycle: game hours per rot stage
HOURS_FOR_CORPSE_REMOVAL = 216  # zombie-lifecycle: game hours
SKELETON_ROT_ONE_IN = 7  # zombie-lifecycle: a body past removal age may turn to bones instead
SKELETON_REMOVAL_EXTRA_HOURS = 72  # zombie-lifecycle: game hours
ROT_STAGE_MAX = 3  # zombie-lifecycle
ROT_FRESH_DAYS = 20  # zombie-lifecycle: days since the outbreak when every kill is still stage 1
ROT_MID_DAYS = 90  # zombie-lifecycle: days when the chances stop moving
ROT_LATE_DAYS = 180  # zombie-lifecycle: days when stage 1 is gone
ROT_STAGE1_START, ROT_STAGE1_MID, ROT_STAGE1_LATE = 100, 20, 0  # zombie-lifecycle: percent
ROT_STAGE2_START, ROT_STAGE2_MID, ROT_STAGE2_LATE = 10, 30, 10  # zombie-lifecycle: percent
ROT_WORDS = {1: "fresh", 2: "decaying", 3: "rotten"}  # zombie-lifecycle
SKELETON_WORD = "bare bones"  # zombie-lifecycle

FAKE_DEAD_WAKEUP_MIN = 30  # zombie-lifecycle: minutes after it died
FAKE_DEAD_RING_TILES = (2, 4)  # zombie-lifecycle: the player must be this far from the body
RISE_FACT = "A body on the ground lurches to its feet."  # zombie-lifecycle
RISE_CRAWLING_FACT = (
    "A body on the ground twitches and starts to drag itself across the floor."  # zombie-lifecycle
)

CORPSE_STRIP_UNHAPPINESS_PER_MIN = units.per_minute_from_frame(
    0.01
)  # zombie-lifecycle: unhappiness points per minute of taking an item
STRIP_UNHAPPINESS_TRAIT_MULT = {
    COWARDLY_ID: 2.0,
    BRAVE_ID: 0.5,
    DESENSITIZED_ID: 0.0,
}  # zombie-lifecycle
LOOT_ROLL_STEPS = 10000  # zombie-lifecycle: the pocket roll is a whole number below this
SEARCH_FACT = "{name} goes through {corpse}: {items}."  # zombie-lifecycle
SEARCH_NOTHING = "nothing"  # zombie-lifecycle
TAKE_CORPSE_FACT = "{name} takes the dead {sex}'s {item}."  # zombie-lifecycle
DEAD_MAN, DEAD_WOMAN = "man", "woman"  # zombie-lifecycle
CORPSE_GONE_FACT = "{name} gets to where {corpse} lay, but the body is gone."  # zombie-lifecycle
ALREADY_SEARCHED = "{name} has already been through {corpse}."  # zombie-lifecycle
NOT_SEARCHED = "{name} hasn't been through {corpse} yet."  # zombie-lifecycle
NO_SUCH_CORPSE = "'{target}' is not here to search."  # zombie-lifecycle
NOT_ON_CORPSE = "{corpse} holds no '{item}'."  # zombie-lifecycle
ASLEEP_REFUSAL = "{name} is asleep."  # zombie-lifecycle
MAN_WORD, WOMAN_WORD = "a man", "a woman"  # zombie-lifecycle
CORPSE_LOOK_ITEMS = 3  # zombie-lifecycle: garments named in a corpse's description

CORPSE_COUNT_MAX = 25  # zombie-lifecycle: bodies counted for corpse sickness
SMELL_FACT = "The smell of the dead hangs thick here."  # zombie-lifecycle

REANIMATE_DELAY_MAX_MIN = 1.0  # zombie-lifecycle: the player's body rises within this many minutes

FEMALE_ONE_IN = 2  # zombie-lifecycle: 50% female
CHANCE_OF_ATTACHED_WEAPON = 6  # zombie-lifecycle: percent
ATTACHED_CONDITION_SPREAD = (
    5  # zombie-lifecycle: condition from max(2, max - 5) up to max, exclusive
)
ATTACHED_CONDITION_FLOOR = 2  # zombie-lifecycle

HEALTH_BASE_MIN = 0.5  # zombies
HEALTH_BASE_MAX = 3.5  # zombies
HEALTH_BONUS_MAX = 0.3  # zombies
SPEED_TYPE_SHAMBLER = 3  # zombies
SPEED_TYPE_FAST_SHAMBLER = 2  # zombies
SHAMBLER_SPEED_MOD_BASE = 0.55  # zombies
LUNGER_SPEED_MOD_BASE = 0.85  # zombies
SPEED_MOD_STEPS = 1500  # zombies: the roll is a whole number below this, over 10000
SPEED_MOD_DIVISOR = 10000  # zombies
FAST_SHAMBLER_LUNGER_CHANCE = 1 / 3  # zombies
SENSE_NORMAL = 2  # zombies
SENSE_POOR = 3  # zombies

PACE_SPEED_TILES_PER_MIN = {"walk": 4, "run": 8, "sneak": 2, "still": 0}  # zombies
PACE_MOVEMENT_MOD = {
    "walk": 1.0,
    "run": 1.5,
    "sneak": 0.8,
    "still": 0.8,
}  # zombies: spotting factor
WALK_APPROACH_TILES_PER_MIN = 4  # zombies: closing on a target at walking pace

# Perk level 0-10.
LIGHTFOOT_MOD = (0.99, 0.90, 0.79, 0.71, 0.65, 0.59, 0.52, 0.45, 0.37, 0.30, 0.20)  # zombies
NIMBLE_MOD = (1.00, 1.10, 1.14, 1.18, 1.22, 1.26, 1.30, 1.34, 1.38, 1.42, 1.50)  # zombies
SNEAK_SPOT_BASE = (0.95, 0.90, 0.80, 0.75, 0.70, 0.65, 0.60, 0.55, 0.50, 0.45, 0.40)  # zombies
SNEAK_SPOT_FACTOR = 1.2  # zombies

FOOTSTEP_PACE_SPEED = {"walk": 0.5, "run": 0.75, "sneak": 0.25}  # zombies
FOOTSTEP_VOLUME_FACTOR = 1.4  # zombies
GRACEFUL_VOLUME_FACTOR = 0.6  # zombies
CLUMSY_VOLUME_FACTOR = 1.2  # zombies
BAREFOOT_VOLUME_FACTOR = 0.5  # zombies
INDOORS_RADIUS_FACTOR = 0.5  # zombies
RADIUS_PER_VOLUME = 10  # zombies
STEPS_PER_MOVING_MINUTE = 8  # zombies
STEP_EMIT_ODDS = 2  # zombies: one step in this many makes a sound
SNEAK_STEP_ODDS_BASE = 4  # zombies
SNEAK_STEP_ODDS_CAP = 12  # zombies
COUGH_RADIUS = 35  # zombies: tiles
COUGH_VOLUME = 40  # zombies
SHOUT_RADIUS = 30  # llm-contract: tiles
SHOUT_VOLUME = 30  # llm-contract
SHOUT_SNEAK_RADIUS = 6  # llm-contract: tiles
SHOUT_SNEAK_VOLUME = 6  # llm-contract
MEGAPHONE_SHOUT = 90  # llm-contract: radius and volume, unused until the catalogue has a megaphone
MEGAPHONE_SHOUT_SNEAK = 18  # llm-contract: radius and volume

CORPSE_SICKNESS_TRAIT_MULT = {RESILIENT_ID: 0.75, PRONE_TO_ILLNESS_ID: 1.25}  # zombie-lifecycle

HEARING_POOR_FACTOR = 0.45  # zombies
HEARING_RAIN_FACTOR = 0.33  # zombies
HEARING_FOG_FACTOR = 0.1  # zombies
HEARING_OTHER_ZONE_FACTOR = 1.2  # zombies
HEARING_INDOOR_MISMATCH_FACTOR = 1.4  # zombies

UNLIT_INDOOR_LIGHT = 0.6  # zombies: factor on daylight indoors without power
VISION_RADIUS = 20  # zombies: tiles
VISION_RADIUS_MIN = 10  # zombies: tiles
VISION_RADIUS_MAX = 20  # zombies: tiles
VISION_DARK_TILES = 5  # zombies: tiles lost at no light
VISION_RAIN_TILES = 2.5  # zombies: tiles lost to full rain
VISION_FOG_TILES = 7  # zombies: tiles lost to full fog
VISION_POOR_FACTOR = 0.35  # zombies
FACING_BELOW = (
    (-0.4, 0.0),
    (-0.2, 1 / 8),
    (0.0, 1 / 4),
    (0.2, 1 / 2),
)  # zombies: (cos below, factor)
FACING_UP_TO = ((0.4, 2.0), (0.6, 8.0), (0.8, 16.0))  # zombies: (cos up to, factor)
FACING_ABOVE_FACTOR = 32.0  # zombies
SPOT_NEAR_TILES = 5  # zombies: tiles
SPOT_NEAR_FACTOR = 3.0  # zombies
SPOT_BONUS_FACTOR = 5.0  # zombies
SPOT_BONUS_FRAMES = 720  # zombies
SPOT_POOR_SIGHT_FACTOR = 0.45  # zombies
SPOT_CAP = 400  # zombies
INCONSPICUOUS_SPOT_FACTOR = 0.8  # zombies
CONSPICUOUS_SPOT_FACTOR = 1.2  # zombies
SNEAK_XP_PER_FRAME_CHANCE = 1 / 1100  # zombies
SNEAK_XP_CLOSE_CHANCE = 20  # zombies: a raw spot chance above this counts as a close call
SNEAK_XP_CLOSE_TILES = 15  # zombies: tiles
SNEAK_XP_AMOUNT = 1.0  # zombies

HEARING_RANGE_BASE = 3.5  # zombies: tiles the player hears a zombie at
HEARING_RANGE_DEAF = 2.0  # zombies: tiles
HEARING_RANGE_KEEN = 3.0  # zombies: tiles gained
HEARING_RANGE_HARD = 1.0  # zombies: tiles lost
HEARING_RANGE_FLOOR = 2.0  # zombies: tiles
HEARING_RANGE_INTOXICATION_PER_POINT = 0.01  # zombies: tiles lost per point of intoxication
SIGHT_RANGE = 20  # zombies: tiles the player sees a zombie at in full light
SIGHT_RANGE_MIN_LIGHT = 0.25  # zombies: factor
CHASE_SPEED_TILES_PER_MIN = 4  # zombies
CHASE_GAP_DIVISOR = 24  # zombies: tiles
CHASE_GAP_FACTOR_MIN = 1.0  # zombies
CHASE_GAP_FACTOR_MAX = 1.3  # zombies
ATTACK_RANGE_TILES = 1  # zombies: a zombie this close attacks

SPOTTED_FACT = "A zombie notices {name} and heads straight for {object}."  # zombies
REACHED_FACT = "A zombie closes in on {name}."  # zombies

DEFENCE_WEAPON_LEVEL_WEIGHT = 3  # zombies
DEFENCE_FITNESS_WEIGHT = 2  # zombies
DEFENCE_STRENGTH_WEIGHT = 2  # zombies
DEFENCE_ATTACKER_PENALTY = 5  # zombies: per attacker
DEFENCE_HEAVY_LOAD_PENALTY = 2  # zombies: per Heavy Load level
DEFENCE_MAX_ATTACKERS = 3  # zombies: no defence against more than this many
DRAG_DOWN_ATTACKERS = 3  # zombies: at Normal zombie strength
MELEE_COMBAT_MOD = (-5, -2, 0, 1, 2, 3, 4, 5, 5, 6, 7)  # zombies: by weapon level 0-10
WOUND_BASE = 15  # zombies: percent
WOUND_BITE = 85  # zombies: percent
WOUND_LACERATION = 65  # zombies: percent
WOUND_BASE_PER_EXTRA_ATTACKER = 10  # zombies: percent lost
WOUND_BITE_PER_EXTRA_ATTACKER = 30  # zombies: percent lost
WOUND_LACERATION_PER_EXTRA_ATTACKER = 15  # zombies: percent lost
BEHIND_BASE_PENALTY = 15  # zombies: percent
BEHIND_BITE_PENALTY = 25  # zombies: percent
BEHIND_LACERATION_PENALTY = 35  # zombies: percent
BEHIND_CROWD_ATTACKERS = 2  # zombies: more attackers than this
BEHIND_CROWD_PENALTY = 15  # zombies: percent, on bite and laceration
SIDE_BASE_PENALTY = 30  # zombies: percent
SIDE_BITE_PENALTY = 7  # zombies: percent
SIDE_LACERATION_PENALTY = 27  # zombies: percent
SKIN_FACTOR = 1.3  # zombies: Thick Skinned multiplies the base, Thin Skinned divides it
BODY_PART_ROLL_WIDE = 11  # zombies: Hand_L to Groin
BODY_PART_ROLL_NARROW = 10  # zombies: Hand_L to Neck
BODY_PART_WIDE_ODDS = 10  # zombies: 1 in this many rolls the wide range
BODY_PART_RETRY_RANGE = 8  # zombies: Hand_L to Torso_Lower
NECK_FROM_BEHIND_PER_ATTACKER = 10  # zombies: percent
NECK_FROM_BEHIND_BASE = 5  # zombies: percent
HEAD_RETRY_ABOVE = {"front": 70, "left": 80, "right": 80, "behind": 90}  # zombies: percent
DAMAGE_THOUSANDTHS = 1000  # zombies
DAMAGE_STEPS = 10  # zombies
DAMAGE_OFFSET = 10  # zombies
ZOMBIE_INFECTION_CHANCE_PERCENT = {"scratch": 7, "laceration": 25, "bite": 100}  # zombies
CLOTHING_DEFENCE_CAP = 100  # zombies

BODY_PART_WORDS = {  # zombies
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
WOUND_VERBS = {"scratch": "scratches", "laceration": "tears into", "bite": "bites"}  # zombies
DEFENDED_FACT = "{name} shoves the zombie off."  # zombies
BLOCKED_FACT = "A zombie claws at {name}, but the clothing holds."  # zombies
THUMP_FACT = "A zombie's blow glances off {name}."  # zombies
WOUND_FACT = "A zombie {verb} {name}'s {part}."  # zombies
DRAGGED_FACT = "{name} was dragged down by the dead."  # zombies

DISTANCE_WORDS = ((1, "on you"), (5, "close"), (15, "nearby"))  # zombies: (gap up to, word)
DISTANCE_WORD_FAR = "far off"  # zombies
STATE_WORDS = {  # zombies
    "idle": "hasn't noticed you",
    "alerted": "turning toward the noise",
    "chasing": "coming at you",
    "attacking": "attacking you",
}
STATE_WORD_FAST = "coming at you fast"  # zombies: a lunger that has chased the player
STATE_WORD_BEHIND = "right behind you"  # zombies
STATE_WORD_DOWN = "down"  # melee
STATE_WORD_THUMPING = "pounding"  # doors
THUMPER_SEEN_WORD = "behind the {barrier}"  # doors
THUMPER_HEARD_WORD = "something at the {barrier}"  # doors
HEARD_WORD_HUNTING = "something behind you"  # zombies
HEARD_WORD_OTHER = "something shuffling nearby"  # zombies
