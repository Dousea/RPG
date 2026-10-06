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

from data.climate import INDOORS_BY_ZONE
from data.items import ITEMS
from modules.entity.item import ItemEntity
from modules.entity.object import DoorEntity, UnlockableEntityLockState
from modules.location import Location

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
    "zone_neighborhood": ("neighborhood", "neighbourhood"),
}


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
            bed_type="floor",  # spec 02
            place_bed_types={"bedroom": "average_bed", "bed": "average_bed"},  # spec 02
        ),
        "zone_building": Location(
            id="zone_building",
            name="Your Building",
            description=(
                "The shared parts of the building: the third-floor hallway, the "
                "stairwell, the elevator, the ground-floor lobby and its mailboxes, "
                "the laundry room in the basement, and your neighbours' doors."
            ),
            connections={"in": "zone_home", "out": "zone_street"},
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
            connections={"in": "zone_building", "out": "zone_neighborhood"},
            # "outside" is not a global alias -- it collides with
            # zone_building's own "outside the building" and is handled as a
            # direction synonym (`DIRECTION_SYNONYMS`) instead.
            aliases=[
                "street",
                "sidewalk",
                "road",
                "alley",
                "bodega",
                "corner store",
                "bus stop",
                "parking lot",
                "my car",
                "the block",
                "front steps",
                "out front",
            ],
        ),
        "zone_neighborhood": Location(
            id="zone_neighborhood",
            name="The Neighborhood",
            description=(
                "The wider few blocks: a coffee shop, the pharmacy, a supermarket, "
                "a walk-in clinic, the subway entrance, the park."
            ),
            connections={"in": "zone_street"},
            # Bare "store" is not an alias -- too generic (any shop). "grocery
            # store" and "corner store" (zone_street) stay, being specific.
            aliases=[
                "neighborhood",
                "neighbourhood",
                "coffee shop",
                "cafe",
                "pharmacy",
                "drugstore",
                "supermarket",
                "grocery store",
                "shops",
                "clinic",
                "hospital",
                "subway",
                "station",
                "park",
                "downtown",
                "the city",
                "town",
            ],
        ),
    }

    for zone_id, indoors in INDOORS_BY_ZONE.items():
        locations[zone_id].indoors = indoors

    # Locked from the building side only: leaving the apartment needs no key.
    apartment_door = DoorEntity(
        leads_to="zone_home",
        state=UnlockableEntityLockState.LOCKED,
        key_id="item_apartment_key",
    )
    locations["zone_building"].entities.append(apartment_door)

    starting_ground_items = {
        "zone_home": ["item_canned_beans", "item_water_bottle"],
        "zone_building": ["item_first_aid_kit"],
        "zone_street": ["item_crowbar"],
    }
    for location_id, item_ids in starting_ground_items.items():
        locations[location_id].entities.extend(
            ItemEntity(item=ITEMS[item_id]) for item_id in item_ids
        )

    return locations
