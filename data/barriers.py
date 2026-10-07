"""Doors, windows, planks and thumping: the shipped barriers, tables and wording (spec 13)."""

from modules.entity.barrier import BarrierEntity, BarrierKind
from modules.units import minutes_from_timed_action_frames

DOOR_HEALTH = 500  # spec 13: health
WINDOW_HEALTH_SINGLE = 50  # spec 13: health, fixtures only
WINDOW_HEALTH_DOUBLE = 100  # spec 13: health, fixtures only
MAX_PLANKS_PER_SIDE = 4  # spec 13: planks
SIGHT_BLOCKING_PLANKS = 3  # spec 13: planks on one side

APARTMENT_DOOR_ID = "door_apartment"
LOBBY_DOOR_ID = "door_lobby"
SHOP_WINDOW_ID = "window_bodega"
APARTMENT_KEY_ID = "item_apartment_key"


def build_starting_barriers() -> dict[str, BarrierEntity]:
    """The two shipped doors and the shop window."""
    barriers = [
        BarrierEntity(
            barrier_id=APARTMENT_DOOR_ID,
            kind=BarrierKind.DOOR,
            zones=("zone_home", "zone_building"),
            inside_zone="zone_home",
            name="apartment door",
            aliases=["front door", "my door", "door", "apartment door", "the door"],
            health=DOOR_HEALTH,
            max_health=DOOR_HEALTH,
            locked=True,
            key_id=APARTMENT_KEY_ID,
        ),
        BarrierEntity(
            barrier_id=LOBBY_DOOR_ID,
            kind=BarrierKind.DOOR,
            zones=("zone_building", "zone_street"),
            inside_zone="zone_building",
            name="lobby door",
            aliases=["street door", "front door", "door", "building door", "the door"],
            health=DOOR_HEALTH,
            max_health=DOOR_HEALTH,
        ),
        BarrierEntity(
            barrier_id=SHOP_WINDOW_ID,
            kind=BarrierKind.WINDOW,
            zones=("zone_street", "zone_bodega"),
            inside_zone="zone_bodega",
            name="shop window",
            aliases=["window", "store window", "bodega window", "the window", "shop window"],
            health=WINDOW_HEALTH_SINGLE,
            max_health=WINDOW_HEALTH_SINGLE,
            locked=True,
        ),
    ]
    return {barrier.barrier_id: barrier for barrier in barriers}


THUMP_STRENGTH = 3  # spec 13: damage per thump
THUMPS_PER_MIN_DOOR_BANG = 1.5  # spec 13: per game minute
THUMPS_PER_MIN_DOOR_CLAW = 1.40625  # spec 13: per game minute
THUMPS_PER_MIN_DOOR = 3.0  # spec 13: per game minute
THUMP_RATES_PER_MIN = (
    THUMPS_PER_MIN_DOOR_BANG,
    THUMPS_PER_MIN_DOOR_CLAW,
    THUMPS_PER_MIN_DOOR,
)
THUMPERS_TO_BREAK_DOOR = 2  # spec 13: zombies
THUMP_COOLDOWN_MIN = 2  # spec 13: minutes
THUMP_STOP_SOUND_RADIUS = 10  # spec 13: tiles
LUNGE_GAP = 2.0  # spec 13: tiles

THUMP_SOUND_RADIUS = 20  # spec 13: tiles
THUMP_SOUND_VOLUME = 20  # spec 13
BREAK_SOUND_RADIUS = 10  # spec 13: tiles
BREAK_SOUND_VOLUME = 20  # spec 13
BREAK_SOUND_IGNORE_TILES = 4  # spec 13: tiles
HIT_SOUND_RADIUS = 20  # spec 13: tiles
HIT_SOUND_VOLUME = 20  # spec 13
HAMMER_SOUND_RADIUS_BASE = 20  # spec 13: tiles
PRY_SOUND_RADIUS = 10  # spec 13: tiles
PRY_SOUND_VOLUME = 1  # spec 13
HAMMER_MOD_BY_CARPENTRY = (1.0, 1.0, 0.8, 0.6, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4)  # spec 13

STRESS_FROM_SOUNDS_MULTIPLIER = 0.00002  # spec 13: per real frame
BARRIER_SOUND_STRESS_MOD = 15  # spec 13
SOUND_LIFE_FRAMES = 16  # spec 13: real frames
STRESS_PER_BARRIER_SOUND = (
    SOUND_LIFE_FRAMES * BARRIER_SOUND_STRESS_MOD * STRESS_FROM_SOUNDS_MULTIPLIER
)  # spec 13: at distance 0

BARRICADE_MOD_BY_CARPENTRY = (  # spec 13: levels 0 to 10
    1.0,
    1.0,
    1.1,
    1.14,
    1.18,
    1.22,
    1.26,
    1.3,
    1.34,
    1.4,
    1.5,
)
PLANK_BASE_HEALTH = 1000  # spec 13: health at full condition
BARRICADE_TIME_FRAMES = 200  # spec 13
UNBARRICADE_TIME_FRAMES_BASE = 200  # spec 13
UNBARRICADE_TIME_FRAMES_PER_CARPENTRY = 5  # spec 13
UNBARRICADE_TIME_FRAMES_HANDY_BONUS = 20  # spec 13
BARRICADE_XP_CARPENTRY = 10  # spec 13: XP, through the XP chain
UNBARRICADE_XP_CARPENTRY = 2  # spec 13: XP, flat
UNBARRICADE_XP_STRENGTH = 2  # spec 13: XP, flat
HAMMER_WEAR_MULT = 6.0  # spec 13
BARRICADE_MIN = minutes_from_timed_action_frames(BARRICADE_TIME_FRAMES)  # spec 13
UNBARRICADE_MIN = minutes_from_timed_action_frames(UNBARRICADE_TIME_FRAMES_BASE)  # spec 13

DOOR_HIT_MULT = 2  # spec 13
DOOR_HIT_EXTRA_MULT = 6  # spec 13
DOOR_HIT_EXTRA_ONE_IN = 10  # spec 13
BARRICADE_HIT_MULT = 5  # spec 13
DOOR_DAMAGE_STRENGTH_MULT = (  # spec 13: m, levels 0 to 10
    0.5,
    0.63,
    0.76,
    0.89,
    1.02,
    1.0,
    1.15,
    1.27,
    1.3,
    1.45,
    1.7,
)
DOOR_HIT_ENDURANCE_BY_FITNESS = (  # spec 13: endurance, levels 0 to 10
    0.01,
    0.007,
    0.0065,
    0.006,
    0.005,
    0.004,
    0.0035,
    0.003,
    0.0025,
    0.002,
    0.0,
)
JOGGER_DOOR_ENDURANCE_MULT = 0.9  # spec 13

PLAYER_AT_BARRIER_DISTANCE = 1  # spec 13: tiles
BROKEN_DOOR_PLANKS_MIN = 1  # spec 13: planks
BROKEN_DOOR_PLANKS_MAX = 2  # spec 13: planks
HEARD_THUMP_INTERRUPT_RADIUS = 20  # spec 13: tiles

PLANK_ITEM_ID = "item_plank"
HAMMER_ITEM_ID = "item_hammer"
NAILS_ITEM_ID = "item_nails"
HAMMER_TAG = "hammer"
REMOVE_BARRICADE_TAG = "removes_barricade"

THUMP_START_FACT = "Something starts pounding on the {barrier}."
PLANK_BREAKS_FACT = "A plank on the {barrier} splinters."
DOOR_BREAKS_FACT = "The {barrier} bursts from its hinges."
WINDOW_BREAKS_FACT = "Glass shatters: the {barrier} gives."
BARRICADE_FACT = "{name} nails a plank across the {barrier}."
UNBARRICADE_FACT = "{name} pries a plank off the {barrier}."
HIT_FACT = "{name} slams the {weapon} into the {barrier}."
HIT_HANDS_FACT = "{name} slams into the {barrier} with {possessive} hands."
OPEN_FACT = "{name} opens the {barrier}."
CLOSE_FACT = "{name} closes the {barrier}."
CLIMB_FACT = "{name} climbs through the {barrier}."

NOTHING_TO_HIT = "There's nothing to hit."
NO_BARRIER_HERE = "There's no {name} here."
ALREADY_OPEN = "The {barrier} is already open."
ALREADY_CLOSED = "The {barrier} is already closed."
NO_DOOR_LEFT = "There's no door left to close."
NO_DOOR_LEFT_OPEN = "There's no door left to open."
SMASHED_WINDOW = "The window is smashed."
BARRICADED = "The {barrier} is barricaded."
LOCKED = "It's locked."
CLOSE_FIRST = "Close it first."
NOTHING_TO_BOARD = "There's nothing left to board up."
FULL_BARRICADE = "The {barrier} is already boarded as much as it can be."
NO_HAMMER = "{name} has no hammer."
NO_PLANK = "{name} has no plank."
NO_NAILS = "{name} has no nails."
NO_PLANKS = "There are no planks on the {barrier}."
PLANKS_ON_OTHER_SIDE = "The planks are on the other side."
NO_PRY_TOOL = "{name} has nothing to pry with."
OTHER_SIDE_OF_BARRIER = "It's on the other side of the {kind}."
