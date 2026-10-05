# In a new modules/npc.py
from dataclasses import dataclass, field

from .faction import CharacterFaction
from .state import CharacterCondition, CharacterDisposition


@dataclass
class State:
    """A comprehensive snapshot of an NPC's current state."""

    # Physical State
    physical_condition: list[CharacterCondition] = field(
        default_factory=list[CharacterCondition]
    )  # e.g., Healthy, Injured, Exhausted
    current_action: str = "standing still"  # A short, descriptive verb phrase

    # Mental State
    disposition: CharacterDisposition = (
        CharacterDisposition.NEUTRAL
    )  # Their current emotional state towards the player
    short_term_goal: str = "assess the situation"  # What they are trying to achieve right now

    # Social State
    faction_standing: dict[CharacterFaction, int] = field(
        default_factory=dict[CharacterFaction, int]
    )  # How they view other factions
