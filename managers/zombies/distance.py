"""Distance in tiles across zones (zombies)."""

from data.time_costs import zone_hop_minutes
from data.zombies import lore as zombie_lore
from managers.world.locations import zone_path
from modules.world.location import Location


def tiles_between(locations: dict[str, Location], start_id: str, target_id: str) -> int | None:
    """Tiles along the shortest path between two zones: each connection is its walking
    minutes at walking pace. None when they are not connected."""
    path = zone_path(locations, start_id, target_id)
    if path is None:
        return None
    walk_speed = zombie_lore.PACE_SPEED_TILES_PER_MIN["walk"]
    here = start_id
    tiles = 0
    for step in path:
        tiles += zone_hop_minutes(here, step) * walk_speed
        here = step
    return tiles
