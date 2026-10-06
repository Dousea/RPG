"""Zombie settings, population and zone numbers (spec 09)."""

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
    "zone_neighborhood": (80, 16, 64),
}

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
HEARD_WORD_HUNTING = "something behind you"  # spec 09
HEARD_WORD_OTHER = "something shuffling nearby"  # spec 09
