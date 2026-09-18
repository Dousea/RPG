"""Starting world map.

Exposed as a builder rather than a module-level dict: `Location.entities` is
mutable game state, so a shared dict would leak one game's dropped items into
the next game after a reset.
"""

from data.items import ITEMS
from modules.entity.item import ItemEntity
from modules.location import Location


def build_starting_locations() -> dict[str, Location]:
    """Build a fresh map with its starting ground items."""
    locations = {
        "location_id_hallway": Location(
            id="location_id_hallway",
            name="Hallway",
            description="A long, narrow corridor with doors on either side.",
            connections={
                "north": "location_id_office",
                "south": "location_id_lobby",
            },
        ),
        "location_id_office": Location(
            id="location_id_office",
            name="Office",
            description="A small office with a desk and a computer.",
            connections={"south": "location_id_hallway"},
        ),
        "location_id_lobby": Location(
            id="location_id_lobby",
            name="Lobby",
            description="A spacious lobby with a reception desk.",
            connections={"north": "location_id_hallway"},
        ),
    }

    starting_ground_items = {
        "location_id_office": ["item_crowbar", "item_canned_beans"],
        "location_id_lobby": ["item_first_aid_kit"],
    }
    for location_id, item_ids in starting_ground_items.items():
        locations[location_id].entities.extend(
            ItemEntity(item=ITEMS[item_id]) for item_id in item_ids
        )

    return locations
