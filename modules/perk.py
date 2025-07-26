from dataclasses import dataclass

import effect
import event


@dataclass
class Perk:
    id: str
    name: str
    description: str
    effects: list[
        effect.Once
        | effect.Event[event.QuestCompletion]
        | effect.Event[event.WeaponTakeDamage]
        | effect.Event[event.WeaponDealDamage]
        | effect.Event[event.ApplyItem]
        | effect.Event[event.ConsumeItem]
    ]
