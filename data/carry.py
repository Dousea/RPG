"""Carry weight, capacity, Heavy Load and the cost of moving things (spec 25)."""

from modules import units
from modules.body.stats import StatusEffect

BASE_MAX_WEIGHT = 8  # spec 25: kg
WEIGHT_MOD_BY_STRENGTH = (
    0.8,
    0.9,
    1.07,
    1.24,
    1.41,
    1.58,
    1.75,
    1.92,
    2.09,
    2.26,
    2.5,
)  # spec 25: Strength 0-10
STRONG_ID = "strong"  # spec 25
STOUT_ID = "stout"  # spec 25
FEEBLE_ID = "feeble"  # spec 25
WEAK_ID = "weak"  # spec 25
MAX_WEIGHT_TRAIT_MULT = {STRONG_ID: 1.5, STOUT_ID: 1.25, FEEBLE_ID: 0.9, WEAK_ID: 0.75}  # spec 25
STRENGTH_REDUCERS: dict[
    StatusEffect, tuple[int, int, int, int]
] = {  # spec 25: kg lost at levels 1-4
    StatusEffect.HUNGRY: (0, 1, 2, 2),
    StatusEffect.THIRST: (0, 1, 2, 2),
    StatusEffect.SICK: (0, 1, 2, 3),
    StatusEffect.BLEEDING: (0, 1, 1, 1),
    StatusEffect.INJURED: (0, 1, 2, 3),
}

EQUIPPED_WEIGHT_MULTIPLIER = 0.3  # spec 25: worn or held
MAIN_INVENTORY_CAPACITY = 50  # spec 25: kg
WEIGHT_DECIMALS = 2  # spec 25: weights compare to a hundredth

HEAVY_LOAD_THRESHOLDS = (
    1.0,
    1.25,
    1.5,
    1.75,
)  # spec 25: weight / capacity; the first is "above", the rest "at or above"
HEAVY_LOAD_MAX_LEVEL = 4  # spec 25
HEAVY_ENDURANCE_MULT = (1.0, 1.5, 1.9, 2.3, 2.8)  # spec 25: exercising drain, by level 0-4
HEAVY_WALK_DRAIN_MULT = {3: 1.9, 4: 2.3}  # spec 25: before the divide by 2
WALK_DRAIN_FRAME_RATE = 0.000052  # spec 25
WALK_DRAIN_ENDDELTA = 1.4  # spec 25
WALK_DRAIN_ENDDELTA_OVERWEIGHT = 2.9  # spec 25
WALK_DRAIN_ENDDELTA_ATHLETIC = 0.8  # spec 25
WALK_DRAIN_FACTOR = 3.0  # spec 25
WALK_DRAIN_HALF = 0.5  # spec 25
WALK_DRAIN_MOD = 0.7  # spec 25
WALK_DRAIN_MOD_ASTHMATIC = 1.0  # spec 25
WALK_DRAIN_DIVISOR = 2  # spec 25
OVERWEIGHT_ID = "overweight"  # spec 25
ATHLETIC_ID = "athletic"  # spec 25
ASTHMATIC_ID = "asthmatic"  # spec 25
OVERLOAD_MIN_LEVEL = 3  # spec 25
OVERLOAD_HEALTH_ABOVE = 75  # spec 25: HP
OVERLOAD_HIT_CHANCE = 0.1  # spec 25: per real frame
OVERLOAD_FRAME_LOSS = 0.0165  # spec 25: HP a hit takes at level 5, before the level divisor
OVERLOAD_LEVEL_SPAN = 5  # spec 25: the divisor is (5 - level) / 10
OVERLOAD_LEVEL_DIVISOR = 10  # spec 25
REGENERATES_UP_TO_LEVEL = (
    1  # spec 25: standing and walking regenerate endurance only up to this level
)
HEAVY_FITNESS_DIVISOR = 3  # spec 25: integer division of the level

TRANSFER_FRAMES_CARRIED = 120  # spec 25: frames x weight, out of or into a bag
TRANSFER_FRAMES_WORLD = 50  # spec 25: frames x weight
TRANSFER_WEIGHT_CAP = 3.0  # spec 25: kg
TRANSFER_FILL_MIN = 0.4  # spec 25: ratio
TRANSFER_FLOOR_FACTOR = 0.1  # spec 25
TRANSFER_DEXTROUS = 0.5  # spec 25
TRANSFER_ALL_THUMBS = 2.0  # spec 25
DEXTROUS_ID = "dextrous"  # spec 25
ALL_THUMBS_ID = "allthumbs"  # spec 25

CARRY_XP_WEIGHT_FRACTION = 0.5  # spec 25: of capacity
CARRY_XP_CHECKS_PER_MIN = 3.75  # spec 25
CARRY_XP_CHANCE = 0.05  # spec 25
CARRY_XP_AMOUNT = 2.0  # spec 25

CORPSE_WEIGHT = 20.0  # spec 25: kg
SKELETON_WEIGHT = 7.0  # spec 25: kg
CARRY_CORPSE_MIN = 1  # spec 25: minutes
SPRINTING_ENDURANCE_REDUCE = 0.000455  # spec 25: per frame
CORPSE_CARRY_ENDURANCE_DRAIN_per_hour = units.per_hour_from_frame(
    SPRINTING_ENDURANCE_REDUCE * 0.5
)  # spec 25: moving a body, 8.75 times the exercising drain

CANT_CARRY_MORE = "{name} can't carry any more."  # spec 25
BAG_FULL = "The {bag} is full."  # spec 25
BAG_IN_ITSELF = "A bag can't go into itself."  # spec 25
ALREADY_IN_BAG = "The {item} is already in the {bag}."  # spec 25
BAG_NOT_CARRIED = "{name} has no '{bag}' to put things in."  # spec 25
NOT_CARRIED_TO_PUT = "No '{item}' carried to put away."  # spec 25
NO_BAG_SOURCE = "{name} has no '{source}' to take from."  # spec 25
NOT_IN_BAG = "The {bag} holds no '{item}'."  # spec 25
BAG_EMPTY = "There is nothing in the {source} to take."  # spec 25
NOTHING_HERE = "There is nothing here to take."  # spec 25
HANDS_AND_BACK_FULL = "{name}'s hands and back are full."  # spec 25
HAND_FULL = "{name}'s hand is full."  # spec 25
PLACE_BACK = "on your back"  # spec 25
PLACE_HAND = "in your hand"  # spec 25
PLACE_WORN = "worn"  # spec 25
PLACE_PACK = "in your pack"  # spec 25
PLACE_INSIDE = "inside the {bag}"  # spec 25
BAG_IS_WORN = "The {item} is worn, not held."  # spec 25
BAG_NOT_WORN = "The {item} can't be worn."  # spec 25

PUT_FACT = "{name} puts the {item} in the {bag}."  # spec 25
TAKE_FROM_BAG_FACT = "{name} takes the {item} out of the {bag}."  # spec 25
TAKE_ALL_FACT = "{name} takes {items} from {source}."  # spec 25
TAKE_ALL_CORPSE_FACT = "{name} takes {items} from the dead {sex}."  # spec 25
TAKE_ALL_GROUND_FACT = "{name} gathers up {items}."  # spec 25
SHOULDER_BAG_FACT = "{name} sets the {item} on {possessive} back."  # spec 25

BODY_BLOCKED_VERBS = frozenset(  # spec 25: what a body in the arms refuses
    {
        "EQUIP",
        "UNEQUIP",
        "ATTACK",
        "SHOVE",
        "USE_ITEM",
        "TAKE",
        "PUT",
        "SEARCH",
        "BANDAGE",
        "REMOVE_BANDAGE",
        "DISINFECT",
        "BARRICADE",
        "UNBARRICADE",
        "EXERCISE",
        "SLEEP",
    }
)
CARRIED_WORD = "carried"  # spec 25: how a body in the arms reads
BODY_IN_ARMS = "{name} is carrying a body."  # spec 25
ALREADY_CARRYING = "{name} is already carrying a body."  # spec 25
NOT_CARRYING = "{name} is not carrying a body."  # spec 25
HANDS_FULL = "{name}'s hands are full."  # spec 25
CARRY_BODY_FACT = "{name} hauls the body up and carries it."  # spec 25
DROP_BODY_FACT = "{name} lets the body fall."  # spec 25
BODY_GONE_FACT = "{name} reaches {corpse}, but it is gone."  # spec 25
DROPPED_BODY_GAP = 1.0  # spec 25: tiles
