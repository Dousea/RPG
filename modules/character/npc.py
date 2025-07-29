# In a new modules/npc.py
from dataclasses import dataclass, field

from . import faction, state


@dataclass
class State:
    """A comprehensive snapshot of an NPC's current state."""

    # Physical State
    physical_condition: list[state.Condition] = field(
        default_factory=list[state.Condition]
    )  # e.g., Healthy, Injured, Exhausted
    current_action: str = "standing still"  # A short, descriptive verb phrase

    # Mental State
    disposition: state.Disposition = (
        state.Disposition.NEUTRAL
    )  # Their current emotional state towards the player
    short_term_goal: str = (
        "assess the situation"  # What they are trying to achieve right now
    )

    # Social State
    faction_standing: dict[faction.Faction, int] = field(
        default_factory=dict[faction.Faction, int]
    )  # How they view other factions
