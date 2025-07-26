from dataclasses import dataclass, field

import entity


@dataclass
class Location:
    id: str
    name: str
    description: str
    connections: dict[str, str]  # e.g., {"north": "location_id_hallway"}
    entities: list[entity.Entity] = field(
        default_factory=list[entity.Entity]
    )  # For players, items, doors, terminals, etc.
