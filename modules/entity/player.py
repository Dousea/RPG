import math
from dataclasses import dataclass, field, replace

from ..body import (
    LAYER_ORDER,
    BodyLocation,
    BodyPart,
    PartState,
    new_body,
    overall_health,
)
from ..character.appearance import Appearance
from ..character.equipment import (
    AnyCharacterEquipmentSlot,
    CharacterArmorSlot,
    CharacterHoldableSlot,
)
from ..character.exercise import ExerciseState
from ..character.skills import SkillState
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
    current_room: str | None = None  # spec 25: the id of the room they are in
    inventory: list[ItemEntity] = field(default_factory=list[ItemEntity])
    stats: Stats = field(default_factory=Stats)
    thermal: ThermalState = field(default_factory=ThermalState)
    asleep: bool = False
    # Moving quietly: every walk is at sneak pace (spec 09).
    sneaking: bool = False
    # The 17 parts and their wounds; overall health is derived from them (spec 12).
    body: dict[BodyPart, PartState] = field(default_factory=new_body)
    zombie_infection_since: float | None = (
        None  # hours survived at the first zombie-infected part (spec 12)
    )
    zombie_infection_hours: float = 0.0  # spec 12
    pain_effect_minutes: float = 0.0  # spec 12: painkiller time left
    reduce_infection_power: float = 0.0  # spec 12: antibiotics
    # Well-fed timer: counts down while the player digests; drives Food Eaten.
    food_eaten_timer: float = 0.0
    equipment: dict[AnyCharacterEquipmentSlot, ItemEntity | None] = field(
        default_factory=lambda: {
            **{slot: None for slot in CharacterHoldableSlot},
            **{slot: None for slot in CharacterArmorSlot},
        }
    )
    worn: dict[BodyLocation, ItemEntity] = field(default_factory=dict[BodyLocation, ItemEntity])
    appearance: Appearance = field(default_factory=lambda: Appearance(forename=""))
    occupation_id: str = ""
    job_title: str = ""
    # Trait ids, chosen and granted; the definitions are in data/traits.py.
    traits: list[str] = field(default_factory=list[str])
    skills: dict[str, SkillState] = field(default_factory=dict[str, SkillState])
    skill_boosts: dict[str, int] = field(default_factory=dict[str, int])
    # Fitness and Strength lose XP when untrained: a timer per skill, and the
    # last floor(timer / divisor) that cost an XP.
    loss_timers: dict[str, float] = field(default_factory=dict[str, float])
    loss_timer_steps: dict[str, int] = field(default_factory=dict[str, int])
    exercise: ExerciseState = field(default_factory=ExerciseState)
    conditions: list[CharacterCondition] = field(default_factory=list[CharacterCondition])
    zombie_kills: int = 0  # spec 11
    at_barrier: str | None = None  # spec 13: the barrier the player stands at, for its distance
    carrying_corpse: str | None = None  # spec 25: the id of the body in their arms
    carrying_skeleton: bool = False  # spec 25: whether that body is bones, for its weight

    def __post_init__(self) -> None:
        if not self.appearance.forename:
            self.appearance = replace(self.appearance, forename=self.name)

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
    def health(self) -> float:
        """Overall health from the parts, 0 to 100 (spec 12)."""
        return overall_health(self.body)

    @property
    def hit_points(self) -> int:
        """Overall health rounded up, so only a body at 0 reads as dead (spec 12)."""
        return math.ceil(self.health)

    @hit_points.setter
    def hit_points(self, value: int) -> None:
        raise AttributeError("The player's hit points are derived from the body parts.")

    @property
    def max_hit_points(self) -> int:
        return 100
