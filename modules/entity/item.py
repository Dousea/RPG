from dataclasses import dataclass

from ..item import BaseItem
from . import BaseEntity


@dataclass
class ItemEntity(BaseEntity):
    item: BaseItem

    @property
    def max_hit_points(self) -> int:
        return self.item.max_hit_points
