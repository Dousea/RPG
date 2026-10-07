"""Carry weight, capacity, Heavy Load and the cost of moving things (carrying-and-loot)."""

from modules import units
from modules.body.stats import StatusEffect

BASE_MAX_WEIGHT = 8  # carrying-and-loot: kg
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
)  # carrying-and-loot: Strength 0-10
STRONG_ID = "strong"  # carrying-and-loot
STOUT_ID = "stout"  # carrying-and-loot
FEEBLE_ID = "feeble"  # carrying-and-loot
WEAK_ID = "weak"  # carrying-and-loot
MAX_WEIGHT_TRAIT_MULT = {
    STRONG_ID: 1.5,
    STOUT_ID: 1.25,
    FEEBLE_ID: 0.9,
    WEAK_ID: 0.75,
}  # carrying-and-loot
STRENGTH_REDUCERS: dict[
    StatusEffect, tuple[int, int, int, int]
] = {  # carrying-and-loot: kg lost at levels 1-4
    StatusEffect.HUNGRY: (0, 1, 2, 2),
    StatusEffect.THIRST: (0, 1, 2, 2),
    StatusEffect.SICK: (0, 1, 2, 3),
    StatusEffect.BLEEDING: (0, 1, 1, 1),
    StatusEffect.INJURED: (0, 1, 2, 3),
}

EQUIPPED_WEIGHT_MULTIPLIER = 0.3  # carrying-and-loot: worn or held
MAIN_INVENTORY_CAPACITY = 50  # carrying-and-loot: kg
WEIGHT_DECIMALS = 2  # carrying-and-loot: weights compare to a hundredth

HEAVY_LOAD_THRESHOLDS = (
    1.0,
    1.25,
    1.5,
    1.75,
)  # carrying-and-loot: weight / capacity; the first is "above", the rest "at or above"
HEAVY_LOAD_MAX_LEVEL = 4  # carrying-and-loot
HEAVY_ENDURANCE_MULT = (
    1.0,
    1.5,
    1.9,
    2.3,
    2.8,
)  # carrying-and-loot: exercising drain, by level 0-4
HEAVY_WALK_DRAIN_MULT = {3: 1.9, 4: 2.3}  # carrying-and-loot: before the divide by 2
WALK_DRAIN_FRAME_RATE = 0.000052  # carrying-and-loot
WALK_DRAIN_ENDDELTA = 1.4  # carrying-and-loot
WALK_DRAIN_ENDDELTA_OVERWEIGHT = 2.9  # carrying-and-loot
WALK_DRAIN_ENDDELTA_ATHLETIC = 0.8  # carrying-and-loot
WALK_DRAIN_FACTOR = 3.0  # carrying-and-loot
WALK_DRAIN_HALF = 0.5  # carrying-and-loot
WALK_DRAIN_MOD = 0.7  # carrying-and-loot
WALK_DRAIN_MOD_ASTHMATIC = 1.0  # carrying-and-loot
WALK_DRAIN_DIVISOR = 2  # carrying-and-loot
OVERWEIGHT_ID = "overweight"  # carrying-and-loot
ATHLETIC_ID = "athletic"  # carrying-and-loot
ASTHMATIC_ID = "asthmatic"  # carrying-and-loot
OVERLOAD_MIN_LEVEL = 3  # carrying-and-loot
OVERLOAD_HEALTH_ABOVE = 75  # carrying-and-loot: HP
OVERLOAD_HIT_CHANCE = 0.1  # carrying-and-loot: per real frame
OVERLOAD_FRAME_LOSS = (
    0.0165  # carrying-and-loot: HP a hit takes at level 5, before the level divisor
)
OVERLOAD_LEVEL_SPAN = 5  # carrying-and-loot: the divisor is (5 - level) / 10
OVERLOAD_LEVEL_DIVISOR = 10  # carrying-and-loot
REGENERATES_UP_TO_LEVEL = (
    1  # carrying-and-loot: standing and walking regenerate endurance only up to this level
)
HEAVY_FITNESS_DIVISOR = 3  # carrying-and-loot: integer division of the level

TRANSFER_FRAMES_CARRIED = 120  # carrying-and-loot: frames x weight, out of or into a bag
TRANSFER_FRAMES_WORLD = 50  # carrying-and-loot: frames x weight
TRANSFER_WEIGHT_CAP = 3.0  # carrying-and-loot: kg
TRANSFER_FILL_MIN = 0.4  # carrying-and-loot: ratio
TRANSFER_FLOOR_FACTOR = 0.1  # carrying-and-loot
TRANSFER_DEXTROUS = 0.5  # carrying-and-loot
TRANSFER_ALL_THUMBS = 2.0  # carrying-and-loot
DEXTROUS_ID = "dextrous"  # carrying-and-loot
ALL_THUMBS_ID = "allthumbs"  # carrying-and-loot

CARRY_XP_WEIGHT_FRACTION = 0.5  # carrying-and-loot: of capacity
CARRY_XP_CHECKS_PER_MIN = 3.75  # carrying-and-loot
CARRY_XP_CHANCE = 0.05  # carrying-and-loot
CARRY_XP_AMOUNT = 2.0  # carrying-and-loot

CORPSE_WEIGHT = 20.0  # carrying-and-loot: kg
SKELETON_WEIGHT = 7.0  # carrying-and-loot: kg
CARRY_CORPSE_MIN = 1  # carrying-and-loot: minutes
SPRINTING_ENDURANCE_REDUCE = 0.000455  # carrying-and-loot: per frame
CORPSE_CARRY_ENDURANCE_DRAIN_per_hour = units.per_hour_from_frame(
    SPRINTING_ENDURANCE_REDUCE * 0.5
)  # carrying-and-loot: moving a body, 8.75 times the exercising drain

CANT_CARRY_MORE = "{name} can't carry any more."  # carrying-and-loot
BAG_FULL = "The {bag} is full."  # carrying-and-loot
BAG_IN_ITSELF = "A bag can't go into itself."  # carrying-and-loot
ALREADY_IN_BAG = "The {item} is already in the {bag}."  # carrying-and-loot
BAG_NOT_CARRIED = "{name} has no '{bag}' to put things in."  # carrying-and-loot
NOT_CARRIED_TO_PUT = "No '{item}' carried to put away."  # carrying-and-loot
NO_BAG_SOURCE = "{name} has no '{source}' to take from."  # carrying-and-loot
NOT_IN_BAG = "The {bag} holds no '{item}'."  # carrying-and-loot
BAG_EMPTY = "There is nothing in the {source} to take."  # carrying-and-loot
NOTHING_HERE = "There is nothing here to take."  # carrying-and-loot
HANDS_AND_BACK_FULL = "{name}'s hands and back are full."  # carrying-and-loot
HAND_FULL = "{name}'s hand is full."  # carrying-and-loot
PLACE_BACK = "on your back"  # carrying-and-loot
PLACE_HAND = "in your hand"  # carrying-and-loot
PLACE_WORN = "worn"  # carrying-and-loot
PLACE_PACK = "in your pack"  # carrying-and-loot
PLACE_INSIDE = "inside the {bag}"  # carrying-and-loot
BAG_IS_WORN = "The {item} is worn, not held."  # carrying-and-loot
BAG_NOT_WORN = "The {item} can't be worn."  # carrying-and-loot

PUT_FACT = "{name} puts the {item} in the {bag}."  # carrying-and-loot
TAKE_FROM_BAG_FACT = "{name} takes the {item} out of the {bag}."  # carrying-and-loot
TAKE_ALL_FACT = "{name} takes {items} from {source}."  # carrying-and-loot
TAKE_ALL_CORPSE_FACT = "{name} takes {items} from the dead {sex}."  # carrying-and-loot
TAKE_ALL_GROUND_FACT = "{name} gathers up {items}."  # carrying-and-loot
SHOULDER_BAG_FACT = "{name} sets the {item} on {possessive} back."  # carrying-and-loot

BODY_BLOCKED_VERBS = frozenset(  # carrying-and-loot: what a body in the arms refuses
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
CARRIED_WORD = "carried"  # carrying-and-loot: how a body in the arms reads
BODY_IN_ARMS = "{name} is carrying a body."  # carrying-and-loot
ALREADY_CARRYING = "{name} is already carrying a body."  # carrying-and-loot
NOT_CARRYING = "{name} is not carrying a body."  # carrying-and-loot
HANDS_FULL = "{name}'s hands are full."  # carrying-and-loot
CARRY_BODY_FACT = "{name} hauls the body up and carries it."  # carrying-and-loot
DROP_BODY_FACT = "{name} lets the body fall."  # carrying-and-loot
BODY_GONE_FACT = "{name} reaches {corpse}, but it is gone."  # carrying-and-loot
DROPPED_BODY_GAP = 1.0  # carrying-and-loot: tiles
