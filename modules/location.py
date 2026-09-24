from dataclasses import dataclass, field

from .entity import BaseEntity


@dataclass
class Location:
    id: str
    name: str
    description: str
    connections: dict[str, str]  # e.g., {"out": "zone_building"}
    entities: list[BaseEntity] = field(
        default_factory=list[BaseEntity]
    )  # For players, items, doors, terminals, etc.
    # Other names the game master calls this place. A zone stands in for many
    # rooms, so "hallway", "lobby" and "stairwell" all resolve to the building.
    aliases: list[str] = field(default_factory=list[str])


@dataclass
class World:
    """The set of live locations, plus the wall clock.

    `time` and `date` are *derived*: GameManager renders them from the narrative
    clock (`NarrativeState.day` / `.time_of_day`) via `_sync_world_clock`, and
    nothing else should write them. They were once an independent clock that
    nothing advanced, which left the prompt claiming noon on 1 October 2023 for
    the whole game. The defaults below are only what day 1 morning renders as.
    """

    time: str = "12:00 PM"
    date: str = "2023-10-01"
    locations: dict[str, Location] = field(
        default_factory=dict[str, Location]
    )  # e.g., {"zone_home": Location(...)}
