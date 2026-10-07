from dataclasses import dataclass, field
from enum import StrEnum

from modules.entity import BaseEntity
from modules.entity.item import ItemEntity
from modules.item import BaseItem


class UnlockableEntityLockState(StrEnum):
    LOCKED = "locked"
    UNLOCKED = "unlocked"


@dataclass(kw_only=True)
class UnlockableEntity(BaseEntity):
    state: UnlockableEntityLockState = UnlockableEntityLockState.UNLOCKED
    key_id: str | None = None

    def unlock(self, key: BaseItem) -> bool:
        if self.state == UnlockableEntityLockState.LOCKED and self.key_id == key.id:
            self.state = UnlockableEntityLockState.UNLOCKED
            return True
        return False


@dataclass
class ContainerEntity(UnlockableEntity):
    items: list[ItemEntity] = field(default_factory=list[ItemEntity])

    @property
    def max_hit_points(self) -> int:
        return 50
