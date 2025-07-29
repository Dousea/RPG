from dataclasses import dataclass
from typing import Any

import effect


@dataclass
class Trait:
    id: str
    name: str
    description: str
    effects: list[
        effect.Once
        | effect.QuestCompleted
        | effect.WeaponDamageTaken[Any, Any]
        | effect.WeaponDamageDealt[Any, Any]
        | effect.ItemApplied[Any, Any]
        | effect.ItemConsumed[Any]
    ]
