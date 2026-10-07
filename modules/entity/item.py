from dataclasses import dataclass, field

from modules.body.parts import BodyPart
from modules.entity import BaseEntity
from modules.item import BaseItem, MedicalItem, MeleeWeaponItem, StackItem


@dataclass
class ItemEntity(BaseEntity):
    item: BaseItem
    wetness: float = 0.0  # 0-100, spec 05
    holes: set[BodyPart] = field(default_factory=set[BodyPart])  # spec 05, written from spec 09
    condition: int = -1  # a melee weapon's wear: -1 until set to full, 0 is broken; spec 11
    uses: int = -1  # a medical item's or stack's uses left: -1 until set to full; spec 12, 13
    contents: list["ItemEntity"] = field(
        default_factory=list["ItemEntity"]
    )  # a bag's items; spec 25
    loot_pending: bool = False  # a bag from an outfit that has not rolled its table yet; spec 25

    def __post_init__(self):
        super().__post_init__()
        if isinstance(self.item, MeleeWeaponItem) and self.condition < 0:
            self.condition = self.item.condition_max
        if isinstance(self.item, MedicalItem | StackItem) and self.uses < 0:
            self.uses = self.item.uses

    @property
    def actual_weight(self) -> float:
        """The item's own weight in kg; a stack weighs by the uses it has left."""
        if isinstance(self.item, StackItem):
            return self.item.unit_weight * self.uses
        return self.item.weight

    @property
    def weight(self) -> float:
        """What it weighs lying loose: its own weight and everything inside, in full (spec 25)."""
        return self.actual_weight + sum(entity.weight for entity in self.contents)

    @property
    def max_hit_points(self) -> int:
        return self.item.max_hit_points

    @property
    def broken(self) -> bool:
        return isinstance(self.item, MeleeWeaponItem) and self.condition <= 0
