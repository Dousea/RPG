from dataclasses import dataclass

import effect


@dataclass
class Perk:
    id: str
    name: str
    description: str
    effects: list[effect.AnyEffect]
