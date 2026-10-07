"""Standing among many bodies: how many count, how well the player is shielded, the smell (zombie-lifecycle)."""

from data.zombies import lore as zombie_lore
from modules.entity.player import PlayerEntity
from modules.item import ClothingItem
from modules.world.location import World


def corpse_count(world: World, zone_id: str) -> int:
    """Bodies in the zone, or in every zone of its building, capped at 25; skeletons count."""
    building = world.locations[zone_id].building
    zones = {
        zone.id
        for zone in world.locations.values()
        if zone.id == zone_id or (building is not None and zone.building == building)
    }
    return min(
        sum(1 for c in world.corpses.values() if c.zone_id in zones), zombie_lore.CORPSE_COUNT_MAX
    )


def corpse_defence(player: PlayerEntity) -> float:
    """The best corpse sickness defence among the worn items, in percent."""
    return float(
        max(
            (
                entity.item.corpse_sickness_defense
                for entity in player.worn.values()
                if isinstance(entity.item, ClothingItem)
            ),
            default=0,
        )
    )


def smell_fact(world: World, zone_id: str, count: int, free_count: int) -> str | None:
    """The fact when the count first passes the free count in a zone, once until it falls again."""
    if count <= free_count:
        world.smell_zone_id = None
        return None
    if world.smell_zone_id == zone_id:
        return None
    world.smell_zone_id = zone_id
    return zombie_lore.SMELL_FACT
