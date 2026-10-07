"""Rooms inside a zone and the containers in them (spec 25)."""

from dataclasses import dataclass, field

from modules.entity.item import ItemEntity


@dataclass
class ContainerEntity:
    """A piece of furniture that holds items; it fills from its table when first opened.

    `source` is the (room, container type) pair of the table it rolls; a `fixed` container
    has none and holds a set list of items.
    """

    container_id: str
    name: str
    kind: str
    capacity: float
    aliases: list[str] = field(default_factory=list[str])
    source: tuple[str, str] | None = None
    contents: list[ItemEntity] = field(default_factory=list[ItemEntity])
    opened: bool = False
    fixed: bool = False


@dataclass
class RoomEntity:
    """A named room of a zone. `proc_spawned` counts the procedural tables used here, for their min and max."""

    room_id: str
    name: str
    kind: str
    aliases: list[str] = field(default_factory=list[str])
    containers: list[ContainerEntity] = field(default_factory=list[ContainerEntity])
    proc_spawned: dict[str, int] = field(default_factory=dict[str, int])
