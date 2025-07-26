from dataclasses import dataclass


@dataclass
class Entity:
    id: str
    hit_points: int
    max_hit_points: int
