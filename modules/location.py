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
    # What the player sleeps on here, and the spots inside the zone that
    # override it: a word in `current_place` selects its bed type (spec 02).
    bed_type: str = "floor"
    place_bed_types: dict[str, str] = field(default_factory=dict[str, str])

    def bed_type_at(self, place: str) -> str:
        """The bed type at a free-text spot inside this zone."""
        spot = place.casefold()
        for word, bed_type in self.place_bed_types.items():
            if word in spot:
                return bed_type
        return self.bed_type


@dataclass
class World:
    """The set of live locations, plus the wall clock.

    `time` and `date` are *derived*: GameManager renders them from the narrative
    clock (`NarrativeState.minutes`) via `_sync_world_clock`, and nothing else
    should write them. The defaults below are only what day 1, 08:00 renders as.
    """

    time: str = "08:00 AM"
    date: str = "2023-10-01"
    locations: dict[str, Location] = field(
        default_factory=dict[str, Location]
    )  # e.g., {"zone_home": Location(...)}
