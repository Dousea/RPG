from dataclasses import dataclass, field

from .entity import BaseEntity


@dataclass
class Location:
    id: str
    name: str
    description: str
    connections: dict[str, str]  # e.g., {"north": "location_id_hallway"}
    entities: list[BaseEntity] = field(
        default_factory=list[BaseEntity]
    )  # For players, items, doors, terminals, etc.


@dataclass
class World:
    time: str = "12:00 PM"
    date: str = "2023-10-01"
    locations: dict[str, Location] = field(
        default_factory=dict[str, Location]
    )  # e.g., {"location_id_town_square": Location(...)}
