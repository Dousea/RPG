"""A door or window on the connection between two zones, and its planks (doors)."""

from dataclasses import dataclass, field
from enum import StrEnum


class BarrierKind(StrEnum):
    DOOR = "door"
    WINDOW = "window"


@dataclass
class BarrierEntity:
    """`barricades` maps each side (a zone id) to its plank healths, innermost first."""

    barrier_id: str
    kind: BarrierKind
    zones: tuple[str, str]
    inside_zone: str
    name: str
    health: int
    max_health: int
    aliases: list[str] = field(default_factory=list[str])
    open: bool = False
    broken: bool = False
    locked: bool = False
    key_id: str | None = None
    barricades: dict[str, list[int]] = field(default_factory=dict[str, list[int]])

    def __post_init__(self) -> None:
        for zone_id in self.zones:
            self.barricades.setdefault(zone_id, [])

    def far_side(self, side: str) -> str:
        """The zone on the other side of the barrier from `side`."""
        first, second = self.zones
        return second if side == first else first

    def planks(self, side: str) -> list[int]:
        return self.barricades.get(side, [])

    def plank_count(self, side: str) -> int:
        return len(self.planks(side))

    @property
    def total_planks(self) -> int:
        return sum(len(planks) for planks in self.barricades.values())

    @property
    def joins(self) -> frozenset[str]:
        return frozenset(self.zones)
