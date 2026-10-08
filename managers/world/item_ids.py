"""Instance ids: every item gets its own id from the world's counter, so one item can be pointed at across turns and loads (carrying-and-loot)."""

from collections.abc import Iterable, Iterator
from typing import Final

from modules.entity.item import ItemEntity
from modules.entity.npc import NpcEntity
from modules.entity.player import PlayerEntity
from modules.world.location import World

ID_PREFIX: Final = "i"


def _with_contents(entities: Iterable[ItemEntity | None]) -> Iterator[ItemEntity]:
    for entity in entities:
        if entity is not None:
            yield entity
            yield from _with_contents(entity.contents)


def every_item(
    world: World, player: PlayerEntity, npcs: Iterable[NpcEntity] = ()
) -> Iterator[ItemEntity]:
    """Each item in the game, bags' contents included, in a fixed order: the player, the NPCs, the zones, the zombies, the bodies."""
    yield from _with_contents(player.inventory)
    yield from _with_contents(player.worn.values())
    yield from _with_contents(player.equipment.values())
    for npc in npcs:
        yield from _with_contents(npc.inventory)
    for location in world.locations.values():
        yield from _with_contents(e for e in location.entities if isinstance(e, ItemEntity))
        for room in location.rooms.values():
            for container in room.containers:
                yield from _with_contents(container.contents)
    for zombie in world.zombies.values():
        yield from _with_contents([*zombie.worn.values(), zombie.attached, *zombie.carried])
    for corpse in world.corpses.values():
        yield from _with_contents([*corpse.contents, corpse.attached])


def stamp(world: World, items: Iterable[ItemEntity]) -> None:
    """Give each of `items` (and what they hold) that has no id the next number of the world's counter."""
    for entity in _with_contents(items):
        if not entity.instance_id:
            entity.instance_id = f"{ID_PREFIX}{world.next_item_number}"
            world.next_item_number += 1


def stamp_world(world: World, player: PlayerEntity, npcs: Iterable[NpcEntity] = ()) -> None:
    """Stamp every item in the game that has no id yet."""
    stamp(world, every_item(world, player, npcs))
