from dataclasses import dataclass

import effect


@dataclass
class Trait:
    id: str
    name: str
    description: str
    effects: list[effect.AnyEffect]
