"""Finding rooms and containers by name inside the player's zone (spec 25)."""

from managers import carry
from modules.entity.player import PlayerEntity
from modules.world.location import Location
from modules.world.room import ContainerEntity, RoomEntity


def current_room(zone: Location, player: PlayerEntity) -> RoomEntity | None:
    """The room the player is in, or None when the zone has none or the saved room is not one of its."""
    if player.current_room is None:
        return None
    return zone.rooms.get(player.current_room)


def resolve_room(zone: Location, name: str) -> RoomEntity | None:
    """The room of `zone` that `name` is, by its name or an alias, ignoring case and a leading article."""
    needle = carry.clean_name(name)
    if not needle:
        return None
    for room in zone.rooms.values():
        if needle == room.name.casefold() or needle in (a.casefold() for a in room.aliases):
            return room
    return None


def room_holding(zone: Location, container: ContainerEntity) -> RoomEntity | None:
    """The room that has `container`."""
    for room in zone.rooms.values():
        if any(container is each for each in room.containers):
            return room
    return None


def container_by_name(zone: Location, name: str) -> ContainerEntity | None:
    """The container of `zone` whose full name is `name`."""
    needle = carry.clean_name(name)
    for room in zone.rooms.values():
        for container in room.containers:
            if needle == container.name.casefold():
                return container
    return None


def resolve_container(
    zone: Location, room_id: str | None, name: str
) -> ContainerEntity | list[ContainerEntity] | None:
    """The container `name` points at in `zone`.

    A full name finds its container from any room. A bare kind word (an alias) finds one only among
    the containers of the room `room_id`; with more than one match the choices come back as a list.
    """
    needle = carry.clean_name(name)
    if not needle:
        return None
    every = [c for room in zone.rooms.values() for c in room.containers]
    for container in every:
        if needle == container.name.casefold():
            return container
    here = zone.rooms.get(room_id or "")
    pool = here.containers if here is not None else every
    matches = [c for c in pool if needle in (a.casefold() for a in c.aliases)]
    if not matches:
        return None
    return matches[0] if len(matches) == 1 else matches


def move_to_room(player: PlayerEntity, room: RoomEntity) -> None:
    """Put the player in `room`; the room's name becomes their spot."""
    player.current_room = room.room_id
    player.current_place = room.name
