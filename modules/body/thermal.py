"""The player's thermal state: node temperatures, totals and the cold (spec 06)."""

import logging
from dataclasses import dataclass, field
from typing import Any

from modules.body.parts import BodyPart

logger = logging.getLogger(__name__)

INITIAL_CORE_C = 37.0  # spec 06
INITIAL_SKIN_C = 33.0  # spec 06
INITIAL_METABOLIC_RATE = 1.5  # spec 06: the Default target

_SCALAR_FIELDS = (
    "metabolic_rate",
    "primary_total",
    "secondary_total",
    "energy_mult",
    "fluids_mult",
    "fatigue_mult",
    "core_cache",
    "cache_counter",
    "catch_cold",
    "cold_reduction",
    "sneeze_timer",
    "sneeze_active",
    "thermal_damage",
    "thermal_duration",
    "tick_frames",
)
_PART_FIELDS = ("skin", "node_temp", "primary", "secondary")


@dataclass
class ThermalState:
    """Everything the thermoregulator, wetness and cold drivers carry between chunks.

    The core temperature is the `TEMPERATURE` stat and body wetness the
    `WETNESS` stat. `facts` holds the narration facts a chunk produced and is
    never saved.
    """

    skin: dict[BodyPart, float] = field(
        default_factory=lambda: {part: INITIAL_SKIN_C for part in BodyPart}
    )
    node_temp: dict[BodyPart, float] = field(
        default_factory=lambda: {part: INITIAL_CORE_C for part in BodyPart}
    )
    primary: dict[BodyPart, float] = field(default_factory=lambda: {part: 0.0 for part in BodyPart})
    secondary: dict[BodyPart, float] = field(
        default_factory=lambda: {part: 0.0 for part in BodyPart}
    )
    metabolic_rate: float = INITIAL_METABOLIC_RATE
    primary_total: float = 0.0
    secondary_total: float = 0.0
    energy_mult: float = 1.0
    fluids_mult: float = 1.0
    fatigue_mult: float = 1.0
    core_cache: float = INITIAL_CORE_C
    cache_counter: float = 0.0
    catch_cold: float = 0.0
    cold_reduction: float = 0.0
    sneeze_timer: float = 0.0
    sneeze_active: float = 0.0
    thermal_damage: float = 0.0
    thermal_duration: float = 0.0
    tick_frames: float = 0.0
    facts: list[str] = field(default_factory=list[str])

    def to_dict(self) -> dict[str, Any]:
        data: dict[str, Any] = {name: getattr(self, name) for name in _SCALAR_FIELDS}
        for name in _PART_FIELDS:
            data[name] = {part.value: value for part, value in getattr(self, name).items()}
        return data

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ThermalState":
        state = cls()
        for name in _PART_FIELDS:
            target: dict[BodyPart, float] = getattr(state, name)
            raw = data.get(name, {})
            for part_name, value in raw.items() if isinstance(raw, dict) else ():
                try:
                    target[BodyPart(part_name)] = float(value)
                except (ValueError, TypeError):
                    logger.warning(f"Dropping bad entry '{part_name}' in saved {name}.")
        for name in _SCALAR_FIELDS:
            if name not in data:
                continue
            try:
                setattr(state, name, float(data[name]))
            except (ValueError, TypeError):
                logger.warning(f"Dropping bad thermal value '{name}'.")
        return state
