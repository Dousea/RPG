"""Doors, windows, planks and thumping: the shipped barriers, tables and wording (doors)."""

from modules import units
from modules.entity.barrier import BarrierEntity, BarrierKind

DOOR_HEALTH = 500  # doors: health
WINDOW_HEALTH_SINGLE = 50  # doors: health, fixtures only
WINDOW_HEALTH_DOUBLE = 100  # doors: health, fixtures only
MAX_PLANKS_PER_SIDE = 4  # doors: planks
SIGHT_BLOCKING_PLANKS = 3  # doors: planks on one side

APARTMENT_DOOR_ID = "door_apartment"
LOBBY_DOOR_ID = "door_lobby"
SHOP_WINDOW_ID = "window_bodega"
APARTMENT_KEY_ID = "item_apartment_key"


def _place_barriers() -> list[BarrierEntity]:
    """The one barrier of each flat and shop; none has a key (carrying-and-loot)."""

    def door(barrier_id: str, parent: str, zone: str, name: str, *, locked: bool) -> BarrierEntity:
        return BarrierEntity(
            barrier_id=barrier_id,
            kind=BarrierKind.DOOR,
            zones=(parent, zone),
            inside_zone=zone,
            name=name,
            aliases=["door", "the door", name],
            health=DOOR_HEALTH,
            max_health=DOOR_HEALTH,
            locked=locked,
        )

    def window(barrier_id: str, zone: str, name: str, health: int) -> BarrierEntity:
        return BarrierEntity(
            barrier_id=barrier_id,
            kind=BarrierKind.WINDOW,
            zones=("zone_neighborhood", zone),
            inside_zone=zone,
            name=name,
            aliases=["window", "the window", name],
            health=health,
            max_health=health,
            locked=True,
        )

    return [
        door(
            "door_flat_vacant",
            "zone_building",
            "zone_flat_vacant",
            "vacant flat door",
            locked=False,
        ),
        door(
            "door_flat_tenant", "zone_building", "zone_flat_tenant", "tenant flat door", locked=True
        ),
        window("window_pharmacy", "zone_pharmacy", "pharmacy window", WINDOW_HEALTH_SINGLE),
        door("door_clinic", "zone_neighborhood", "zone_clinic", "clinic door", locked=False),
        window(
            "window_supermarket", "zone_supermarket", "supermarket window", WINDOW_HEALTH_DOUBLE
        ),
        door(
            "door_hardware",
            "zone_neighborhood",
            "zone_hardware",
            "hardware store door",
            locked=True,
        ),
    ]


def build_starting_barriers() -> dict[str, BarrierEntity]:
    """The shipped doors and windows."""
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
        *_place_barriers(),
    ]
    return {barrier.barrier_id: barrier for barrier in barriers}


THUMP_STRENGTH = 3  # doors: damage per thump
THUMPS_PER_MIN_DOOR_BANG = 1.5  # doors: per game minute
THUMPS_PER_MIN_DOOR_CLAW = 1.40625  # doors: per game minute
THUMPS_PER_MIN_DOOR = 3.0  # doors: per game minute
THUMP_RATES_PER_MIN = (
    THUMPS_PER_MIN_DOOR_BANG,
    THUMPS_PER_MIN_DOOR_CLAW,
    THUMPS_PER_MIN_DOOR,
)
THUMPERS_TO_BREAK_DOOR = 2  # doors: zombies
THUMP_COOLDOWN_MIN = 2  # doors: minutes
THUMP_STOP_SOUND_RADIUS = 10  # doors: tiles
LUNGE_GAP = 2.0  # doors: tiles

THUMP_SOUND_RADIUS = 20  # doors: tiles
THUMP_SOUND_VOLUME = 20  # doors
BREAK_SOUND_RADIUS = 10  # doors: tiles
BREAK_SOUND_VOLUME = 20  # doors
BREAK_SOUND_IGNORE_TILES = 4  # doors: tiles
HIT_SOUND_RADIUS = 20  # doors: tiles
HIT_SOUND_VOLUME = 20  # doors
HAMMER_SOUND_RADIUS_BASE = 20  # doors: tiles
PRY_SOUND_RADIUS = 10  # doors: tiles
PRY_SOUND_VOLUME = 1  # doors
HAMMER_MOD_BY_CARPENTRY = (1.0, 1.0, 0.8, 0.6, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4, 0.4)  # doors

STRESS_FROM_SOUNDS_MULTIPLIER = 0.00002  # doors: per real frame
BARRIER_SOUND_STRESS_MOD = 15  # doors
SOUND_LIFE_FRAMES = 16  # doors: real frames
STRESS_PER_BARRIER_SOUND = (
    SOUND_LIFE_FRAMES * BARRIER_SOUND_STRESS_MOD * STRESS_FROM_SOUNDS_MULTIPLIER
)  # doors: at distance 0

BARRICADE_MOD_BY_CARPENTRY = (  # doors: levels 0 to 10
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
PLANK_BASE_HEALTH = 1000  # doors: health at full condition
BARRICADE_TIME_FRAMES = 200  # doors
UNBARRICADE_TIME_FRAMES_BASE = 200  # doors
UNBARRICADE_TIME_FRAMES_PER_CARPENTRY = 5  # doors
UNBARRICADE_TIME_FRAMES_HANDY_BONUS = 20  # doors
BARRICADE_XP_CARPENTRY = 10  # doors: XP, through the XP chain
UNBARRICADE_XP_CARPENTRY = 2  # doors: XP, flat
UNBARRICADE_XP_STRENGTH = 2  # doors: XP, flat
HAMMER_WEAR_MULT = 6.0  # doors
BARRICADE_MIN = units.minutes_from_timed_action_frames(BARRICADE_TIME_FRAMES)  # doors

DOOR_HIT_MULT = 2  # doors
DOOR_HIT_EXTRA_MULT = 6  # doors
DOOR_HIT_EXTRA_ONE_IN = 10  # doors
BARRICADE_HIT_MULT = 5  # doors
DOOR_DAMAGE_STRENGTH_MULT = (  # doors: m, levels 0 to 10
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
DOOR_HIT_ENDURANCE_BY_FITNESS = (  # doors: endurance, levels 0 to 10
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
JOGGER_DOOR_ENDURANCE_MULT = 0.9  # doors

MAX_BARRIER_SWINGS = 30  # doors: swings in one ATTACK
BARRIER_SWINGS_STOP_ENDURANCE_LEVEL = 2  # doors: status effect level at which a run of swings ends

PLAYER_AT_BARRIER_DISTANCE = 1  # doors: tiles
BROKEN_DOOR_PLANKS_MIN = 1  # doors: planks
BROKEN_DOOR_PLANKS_MAX = 2  # doors: planks
HEARD_THUMP_INTERRUPT_RADIUS = 20  # doors: tiles

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
LOCK_FACT = "{name} locks the {barrier}."
UNLOCK_FACT = "{name} unlocks the {barrier}."
CLIMB_FACT = "{name} climbs through the {barrier}."

KEEPS_HITTING_FACT = "{name} keeps hitting the {barrier}."
KEEPS_HITTING_UNTIL_FACT = "{name} keeps hitting the {barrier} until it gives way."
SWINGS_TIRED_FACT = "{name} is too winded to keep swinging."
SWINGS_INTERRUPTED_FACT = "{name} breaks off the blows."
SWINGS_CAPPED_FACT = "{name} stops to catch {possessive} breath, the {barrier} still holding."

NOTHING_TO_HIT = "There's nothing to hit."
NO_BARRIER_HERE = "There's no {name} here."
ALREADY_OPEN = "The {barrier} is already open."
ALREADY_CLOSED = "The {barrier} is already closed."
NO_DOOR_LEFT = "There's no door left to close."
NO_DOOR_LEFT_TO_LOCK = "There's no door left to lock."
NO_DOOR_LEFT_TO_UNLOCK = "There's no door left to unlock."
NO_DOOR_LEFT_OPEN = "There's no door left to open."
SMASHED_WINDOW = "The window is smashed."
BARRICADED = "The {barrier} is barricaded."
LOCKED = "It's locked."
ALREADY_LOCKED = "The {barrier} is already locked."
NOT_LOCKED = "The {barrier} isn't locked."
NO_KEY = "{name} has no key for the {barrier}."
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


def unbarricade_minutes(carpentry: int, *, handy: bool) -> int:
    """Minutes to pry a plank off: 200 frames less 5 per Carpentry level and 20 for Handy."""
    frames = UNBARRICADE_TIME_FRAMES_BASE - UNBARRICADE_TIME_FRAMES_PER_CARPENTRY * carpentry
    if handy:
        frames -= UNBARRICADE_TIME_FRAMES_HANDY_BONUS
    return units.minutes_from_timed_action_frames(frames)
