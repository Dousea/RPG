"""Starting world map, as zones rather than rooms.

A zone is a coarse container the game master narrates freely inside: "Your
Apartment" covers the kitchen, the bedroom and the bathroom, and the player's
position within it is the free-text `PlayerEntity.current_place`.

This is deliberate. The previous map was three rooms -- Hallway, Office, Lobby --
while the system prompt opened on Orton's apartment and the item catalogue held a
key to "apartment 3B". The game master narrated its way into rooms that did not
exist, every `MOVE_TO` at them failed, and the simulated world silently fell out
of step with the story being told. Enumerating every room the story might reach is
unbounded work; four zones plus a free-text spot is not.

`aliases` is what makes that work in practice: the model says "the lobby" or "the
pharmacy", and those resolve to the building and the neighborhood rather than
failing. The lists are deliberately over-broad -- a missed alias is a silent
desync, an extra one is harmless.

Exposed as a builder rather than a module-level dict: `Location.entities` is
mutable game state, so a shared dict would leak one game's dropped items into
the next game after a reset.
"""

from data.items import ITEMS
from data.loot.containers import ENTRY_ROOMS, build_rooms
from data.world.barriers import PLANK_ITEM_ID
from data.world.climate import INDOORS_BY_ZONE
from data.zombies.lore import ZONE_ZOMBIE_FIELDS
from modules.entity.item import ItemEntity
from modules.world.location import Location

# The zone the player starts in, and the fallback for a save that names a zone
# this build no longer has.
STARTING_ZONE_ID = "zone_home"

# Nouns that mean the *whole zone* when they follow an exit verb
# ("leave the apartment", "outside the building") -- kept separate from
# `aliases` because the bare words here (apartment, building, street,
# neighborhood, ...) are deliberately not *global* aliases,
# where they would have matched anywhere in the map. "leave the apartment"
# still has to mean walk out of home no matter where Orton says it from being
# home, so `resolve_location`'s exit-phrase check keys off this table and the
# *current* zone instead of a global alias lookup.
ZONE_EXIT_NOUNS: dict[str, tuple[str, ...]] = {
    "zone_home": ("apartment", "apartment 3b", "3b", "flat", "home", "place"),
    "zone_building": ("building", "apartment building"),
    "zone_street": ("street", "block"),
    "zone_bodega": ("bodega", "corner store", "store", "shop"),
    "zone_neighborhood": ("neighborhood", "neighbourhood"),
    "zone_flat_vacant": ("vacant flat",),
    "zone_flat_tenant": ("tenant flat", "tenant's flat"),
    "zone_pharmacy": ("pharmacy", "drugstore"),
    "zone_clinic": ("clinic",),
    "zone_supermarket": ("supermarket", "grocery store"),
    "zone_hardware": ("hardware store", "tool store"),
}

# Words that name a kind of place several zones share ("the apartment", "the
# store"), kept apart from `aliases` the way container kind words are: a kind
# word finds every zone of the kind the player can reach and asks which one.
ZONE_KINDS: dict[str, tuple[str, ...]] = {  # llm-contract
    "zone_home": ("apartment", "flat"),
    "zone_building": ("apartment", "flat"),
    "zone_flat_vacant": ("apartment", "flat"),
    "zone_flat_tenant": ("apartment", "flat"),
    "zone_bodega": ("store", "shop"),
    "zone_pharmacy": ("store", "shop"),
    "zone_supermarket": ("store", "shop"),
    "zone_hardware": ("store", "shop"),
}

# How a zone reads in a which-one list when its kind comes from a place inside
# it rather than from its own name.
ZONE_KIND_NAMES: dict[str, str] = {  # llm-contract
    "zone_building": "Emma's apartment, in Your Building",
}

ALLEY_CONTENTS = [PLANK_ITEM_ID, PLANK_ITEM_ID]  # doors
APARTMENT_BLOCK_ID = "apartment_block"  # doors
BUILDING_ZONE_IDS = ("zone_home", "zone_building")  # doors
CORNER_STORE_ID = "corner_store"  # doors
OWN_BUILDINGS = {  # carrying-and-loot: the zone to its own building id, so a barrier of it wakes only that place
    "zone_flat_vacant": "flat_vacant",
    "zone_flat_tenant": "flat_tenant",
    "zone_pharmacy": "pharmacy",
    "zone_clinic": "clinic",
    "zone_supermarket": "supermarket",
    "zone_hardware": "hardware_store",
}
FLAT_ZONE_IDS = (
    "zone_flat_vacant",
    "zone_flat_tenant",
)  # carrying-and-loot: floor 1, like zone_home


def build_starting_locations() -> dict[str, Location]:
    """Build a fresh map with its starting ground items."""
    locations = {
        "zone_home": Location(
            id="zone_home",
            name="Your Apartment",
            description=(
                "Apartment 3B. A one-bedroom you moved into a few weeks ago and "
                "still have not finished unpacking. A kitchenette, a bathroom, a "
                "bedroom, a window over the street, and a door with a deadbolt."
            ),
            connections={"out": "zone_building"},
            # Generic room nouns (bedroom, kitchen, bathroom, ...) and
            # direction words (inside, back inside) are not global aliases --
            # a story that mentions "the kitchen" almost never means Orton's
            # kitchen specifically, and a global alias here would silently
            # teleport him home. Removed ones become a spot in whatever zone
            # he's already standing in via `_validate_move`'s unresolved path
            # instead. Only names that unambiguously mean *this* apartment
            # survive.
            aliases=[
                "apartment 3b",
                "3b",
                "my apartment",
                "your apartment",
                "home",
                "my flat",
                "my place",
                "my room",
            ],
            bed_type="floor",  # survival-stats
            place_bed_types={"bedroom": "average_bed", "bed": "average_bed"},  # survival-stats
        ),
        "zone_building": Location(
            id="zone_building",
            name="Your Building",
            description=(
                "The shared parts of the building: the third-floor hallway, the "
                "stairwell, the elevator, the ground-floor lobby and its mailboxes, "
                "the laundry room in the basement, and your neighbours' doors."
            ),
            connections={
                "in": "zone_home",
                "out": "zone_street",
                "vacant flat": "zone_flat_vacant",  # carrying-and-loot
                "tenant flat": "zone_flat_tenant",  # carrying-and-loot
            },
            # upstairs/downstairs/office/entrance are generic enough to
            # mean anywhere, so they are not global aliases -- they become a
            # spot in the current zone instead. "storage room" stays
            # because v2 saves could have a player standing there
            # (`adapters/persistence._V2_ROOM_PLACES`).
            aliases=[
                "hallway",
                "corridor",
                "stairwell",
                "stairs",
                "elevator",
                "lobby",
                "foyer",
                "laundry room",
                "basement",
                "mailroom",
                "emma's apartment",
                "3a",
                "the building",
                "building",
                "next door",
                "storage room",
            ],
        ),
        "zone_street": Location(
            id="zone_street",
            name="The Street",
            description=(
                "The block outside: the sidewalk, parked cars, the bodega on the "
                "corner, the alley behind the building, a bus stop."
            ),
            connections={
                "in": "zone_building",
                "out": "zone_neighborhood",
                "store": "zone_bodega",
            },
            # "outside" is not a global alias -- it collides with
            # zone_building's own "outside the building" and is handled as a
            # direction synonym (`DIRECTION_SYNONYMS`) instead.
            aliases=[
                "street",
                "sidewalk",
                "road",
                "alley",
                "bus stop",
                "parking lot",
                "my car",
                "the block",
                "front steps",
                "out front",
            ],
        ),
        "zone_bodega": Location(
            id="zone_bodega",
            name="The Corner Store",
            description=(
                "The bodega on the corner: a narrow shop with the shelves half "
                "emptied, the till, and a back room. The front door is chained "
                "shut from inside, so the shop window is the way in."
            ),
            connections={"out": "zone_street"},
            aliases=[
                "bodega",
                "corner store",
                "the bodega",
                "the corner store",
            ],
        ),
        "zone_neighborhood": Location(
            id="zone_neighborhood",
            name="The Neighborhood",
            description=(
                "The wider few blocks: a coffee shop, the pharmacy, a supermarket, "
                "a walk-in clinic, a hardware store, the subway entrance, the park."
            ),
            connections={
                "in": "zone_street",
                "pharmacy": "zone_pharmacy",  # carrying-and-loot
                "clinic": "zone_clinic",  # carrying-and-loot
                "supermarket": "zone_supermarket",  # carrying-and-loot
                "hardware store": "zone_hardware",  # carrying-and-loot
            },
            # Bare "store" and "shop" are not aliases anywhere -- too generic
            # (any shop).
            aliases=[
                "neighborhood",
                "neighbourhood",
                "coffee shop",
                "cafe",
                "shops",
                "hospital",
                "subway",
                "station",
                "park",
                "downtown",
                "the city",
                "town",
            ],
        ),
        "zone_flat_vacant": Location(
            id="zone_flat_vacant",
            name="The Vacant Flat",
            description=(
                "A flat nobody has lived in for months: bare floors, a kitchen "
                "counter, a wardrobe with the doors ajar and a medicine cabinet "
                "on the bathroom wall."
            ),
            connections={"out": "zone_building"},
            aliases=["vacant flat"],
        ),
        "zone_flat_tenant": Location(
            id="zone_flat_tenant",
            name="The Tenant's Flat",
            description=(
                "A neighbour's flat, lived in and left in a hurry: a kitchen, a "
                "bedroom, a bathroom and a living room, the door locked from outside."
            ),
            connections={"out": "zone_building"},
            aliases=["tenant flat"],
            bed_type="floor",  # survival-stats
            place_bed_types={"bedroom": "average_bed", "bed": "average_bed"},  # survival-stats
        ),
        "zone_pharmacy": Location(
            id="zone_pharmacy",
            name="The Pharmacy",
            description=(
                "A small pharmacy: the shop floor with its counter, shelves and "
                "fridge, and a back room with the dispensing counter. The door is "
                "shuttered, so the window is the way in."
            ),
            connections={"out": "zone_neighborhood"},
            aliases=["pharmacy", "drugstore"],
        ),
        "zone_clinic": Location(
            id="zone_clinic",
            name="The Clinic",
            description=(
                "A walk-in clinic: an exam room, an office and a supply room behind them."
            ),
            connections={"out": "zone_neighborhood"},
            aliases=["clinic", "walk-in clinic"],
        ),
        "zone_supermarket": Location(
            id="zone_supermarket",
            name="The Supermarket",
            description=(
                "A big supermarket: long aisles of shelves, the checkout counter, "
                "and a stockroom at the back. The doors are locked, so the window "
                "is the way in."
            ),
            connections={"out": "zone_neighborhood"},
            aliases=["supermarket", "grocery store"],
        ),
        "zone_hardware": Location(
            id="zone_hardware",
            name="The Hardware Store",
            description=(
                "A hardware store: the shop floor with its counter, shelves and "
                "stock crates, and a storeroom behind. The front door is locked."
            ),
            connections={"out": "zone_neighborhood"},
            aliases=["hardware store", "tool store"],
        ),
    }

    for zone_id, indoors in INDOORS_BY_ZONE.items():
        locations[zone_id].indoors = indoors
    for zone_id, kinds in ZONE_KINDS.items():
        locations[zone_id].kinds = list(kinds)
    locations["zone_home"].floor = 1  # body-temperature
    for zone_id in FLAT_ZONE_IDS:
        locations[zone_id].floor = 1  # carrying-and-loot
    for zone_id, (size_tiles, chunks, intensity) in ZONE_ZOMBIE_FIELDS.items():
        locations[zone_id].size_tiles = size_tiles
        locations[zone_id].chunks = chunks
        locations[zone_id].zombie_intensity = intensity

    for zone_id in BUILDING_ZONE_IDS:
        locations[zone_id].building = APARTMENT_BLOCK_ID  # doors
    locations["zone_bodega"].building = CORNER_STORE_ID
    for zone_id, building in OWN_BUILDINGS.items():
        locations[zone_id].building = building

    for zone_id, entry_room in ENTRY_ROOMS.items():
        locations[zone_id].rooms = build_rooms(zone_id)
        locations[zone_id].entry_room = entry_room

    starting_ground_items = {
        "zone_neighborhood": ["item_baseball_bat"],  # melee
        "zone_street": ["item_crowbar", *ALLEY_CONTENTS],
    }
    for location_id, item_ids in starting_ground_items.items():
        locations[location_id].entities.extend(
            ItemEntity(item=ITEMS[item_id]) for item_id in item_ids
        )

    return locations
