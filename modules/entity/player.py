from dataclasses import dataclass, field

from ..body import LAYER_ORDER, BodyLocation, BodyPart
from ..character.equipment import (
    AnyCharacterEquipmentSlot,
    CharacterArmorSlot,
    CharacterHoldableSlot,
)
from ..character.player import PlayerAttribute, PlayerPerk, PlayerTrait
from ..character.state import CharacterCondition
from ..item import ClothingItem
from ..stats import Stats
from ..thermal import ThermalState
from . import BaseEntity
from .item import ItemEntity


@dataclass
class PlayerEntity(BaseEntity):
    name: str
    current_location_id: str
    # Stable identity for saves and RelationshipManager keys. `BaseEntity.id`
    # is `id(self)` and changes every restart, so it must not be used for either.
    entity_id: str = "player"
    # Free-text spot inside the current zone ("the kitchen", "the pharmacy
    # counter"). A zone is deliberately coarse; this is what keeps the prompt
    # specific without needing a room for every corner. LLM-authored, so it is
    # capped and rendered as text, never markup.
    current_place: str = ""
    experience_points: int = 0
    level: int = 1
    max_inventory_size: int = 20
    inventory: list[ItemEntity] = field(default_factory=list[ItemEntity])
    stats: Stats = field(default_factory=Stats)
    thermal: ThermalState = field(default_factory=ThermalState)
    asleep: bool = False
    # HP the status effects have taken that has not yet added up to a whole point.
    fractional_hp_loss: float = 0.0
    # Well-fed timer: counts down while the player digests; drives Food Eaten.
    food_eaten_timer: float = 0.0
    attributes: dict[PlayerAttribute, int] = field(
        default_factory=lambda: {
            PlayerAttribute.AGILITY: 3,
            PlayerAttribute.STRENGTH: 3,
            PlayerAttribute.INTELLIGENCE: 3,
            PlayerAttribute.WILLPOWER: 3,
            PlayerAttribute.LUCK: 3,
            PlayerAttribute.CHARISMA: 3,
        }
    )
    equipment: dict[AnyCharacterEquipmentSlot, ItemEntity | None] = field(
        default_factory=lambda: {
            **{slot: None for slot in CharacterHoldableSlot},
            **{slot: None for slot in CharacterArmorSlot},
        }
    )
    worn: dict[BodyLocation, ItemEntity] = field(default_factory=dict[BodyLocation, ItemEntity])
    traits: list[PlayerTrait] = field(default_factory=list[PlayerTrait])
    perks: list[PlayerPerk] = field(default_factory=list[PlayerPerk])
    conditions: list[CharacterCondition] = field(default_factory=list[CharacterCondition])

    def worn_outer_to_inner(self) -> list[tuple[BodyLocation, ItemEntity]]:
        return sorted(self.worn.items(), key=lambda pair: LAYER_ORDER[pair[0]], reverse=True)

    def layers_for(self, part: BodyPart) -> list[ItemEntity]:
        """Worn items covering `part`, inner to outer."""
        layers = [
            (LAYER_ORDER[location], entity)
            for location, entity in self.worn.items()
            if isinstance(entity.item, ClothingItem) and part in entity.item.covers
        ]
        return [entity for _, entity in sorted(layers, key=lambda pair: pair[0])]

    @property
    def max_hit_points(self) -> int:
        return 100
