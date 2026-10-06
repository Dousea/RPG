from dataclasses import dataclass, field

from ..body import BodyPart
from ..item import BaseItem
from . import BaseEntity


@dataclass
class ItemEntity(BaseEntity):
    item: BaseItem
    wetness: float = 0.0  # 0-100, spec 05
    holes: set[BodyPart] = field(default_factory=set[BodyPart])  # spec 05, written from spec 09

    @property
    def max_hit_points(self) -> int:
        return self.item.max_hit_points
