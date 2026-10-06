from dataclasses import dataclass

from .body import BodyLocation, BodyPart
from .character.equipment import AnyCharacterEquipmentSlot, CharacterHoldableSlot
from .modifier import AnyModifier
from .weapon import RangedWeaponType

DEFAULT_EAT_MINUTES = 5  # spec 03
SCRATCH_DEFENSE_DEFAULT = 0  # spec 05
BITE_DEFENSE_DEFAULT = 0  # spec 05
NECK_PROTECTION_DEFAULT = 1.0  # spec 05
STOMP_POWER_DEFAULT = 1.0  # spec 05
HEARING_MODIFIER_DEFAULT = 1.0  # spec 05
CORPSE_SICKNESS_DEFENSE_DEFAULT = 0  # spec 05


@dataclass
class BaseItem:
    id: str
    name: str
    description: str
    max_hit_points: int
    tags: list[str]


@dataclass
class EquippableItem(BaseItem):
    slots: list[AnyCharacterEquipmentSlot]

    def __post_init__(self):
        if not self.slots:
            raise ValueError("Equippable items must have at least one slot defined.")


@dataclass
class ClothingItem(BaseItem):
    """A wearable item; the damage-side stats are stored, not yet read."""

    body_location: BodyLocation
    covers: frozenset[BodyPart]
    insulation: float
    wind_resistance: float
    water_resistance: float
    weight: float
    scratch_defense: int = SCRATCH_DEFENSE_DEFAULT
    bite_defense: int = BITE_DEFENSE_DEFAULT
    neck_protection: float = NECK_PROTECTION_DEFAULT
    stomp_power: float = STOMP_POWER_DEFAULT
    hearing_modifier: float = HEARING_MODIFIER_DEFAULT
    corpse_sickness_defense: int = CORPSE_SICKNESS_DEFENSE_DEFAULT


@dataclass
class HoldableItem(EquippableItem):
    is_two_handed: bool

    def __post_init__(self):
        super().__post_init__()
        if not all(isinstance(slot, CharacterHoldableSlot) for slot in self.slots):
            raise ValueError("Holdable can only use HoldableSlot instances")
        if self.is_two_handed and len(self.slots) != 2:
            raise ValueError("Two-handed items must occupy exactly two slots.")


# Consumable is a type of Holdable that can be consumed for an effect.
@dataclass
class ConsumableItem(HoldableItem):
    modifiers: list[AnyModifier]
    # Stat changes applied once on consuming. Hunger, thirst and stress are on
    # the stats' 0-1 scale (negative lowers); unhappiness and boredom are points.
    hunger_change: float = 0.0
    thirst_change: float = 0.0
    unhappy_change: float = 0.0
    boredom_change: float = 0.0
    stress_change: float = 0.0
    alcoholic: bool = False
    low_alcohol: bool = False
    cooked: bool = False
    eat_minutes: int = DEFAULT_EAT_MINUTES


# Appliable is a type of Holdable that can apply effects when used.
@dataclass
class AppliableItem(HoldableItem):
    modifiers: list[AnyModifier]


@dataclass
class MeleeWeaponItem(HoldableItem):
    """A melee weapon's stats; the runtime `condition` lives on its `ItemEntity`."""

    damage: int  # HP in a fight with an NPC (spec 11)
    min_damage: float
    max_damage: float
    max_range: float
    categories: tuple[str, ...] = ()
    critical_chance: float = 0.0
    crit_dmg_multiplier: float = 2.0
    max_hit_count: int = 1
    knockback_on_no_death: bool = False
    condition_max: int = 1
    condition_lower_chance: int = 1
    weight: float = 1.0
    endurance_mod: float = 1.0
    base_speed: float = 1.0
    is_stab: bool = False
    door_damage: int = 1
    no_criticals: bool = False
    no_maintenance_xp: bool = False

    def __post_init__(self):
        super().__post_init__()
        if self.damage <= 0:
            raise ValueError("Weapon damage must be greater than zero.")


@dataclass
class RangedWeaponItem(HoldableItem):
    type: RangedWeaponType
    damage: int
    range: int

    def __post_init__(self):
        super().__post_init__()
        if self.damage <= 0:
            raise ValueError("Weapon damage must be greater than zero.")
        if self.range < 1:
            raise ValueError("Weapon range must be at least 1.")
