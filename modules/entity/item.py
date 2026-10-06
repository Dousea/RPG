from dataclasses import dataclass, field

from ..body import BodyPart
from ..item import BaseItem, MedicalItem, MeleeWeaponItem
from . import BaseEntity


@dataclass
class ItemEntity(BaseEntity):
    item: BaseItem
    wetness: float = 0.0  # 0-100, spec 05
    holes: set[BodyPart] = field(default_factory=set[BodyPart])  # spec 05, written from spec 09
    condition: int = -1  # a melee weapon's wear: -1 until set to full, 0 is broken; spec 11
    uses: int = -1  # a medical item's uses left: -1 until set to full; spec 12

    def __post_init__(self):
        super().__post_init__()
        if isinstance(self.item, MeleeWeaponItem) and self.condition < 0:
            self.condition = self.item.condition_max
        if isinstance(self.item, MedicalItem) and self.uses < 0:
            self.uses = self.item.uses

    @property
    def max_hit_points(self) -> int:
        return self.item.max_hit_points

    @property
    def broken(self) -> bool:
        return isinstance(self.item, MeleeWeaponItem) and self.condition <= 0
