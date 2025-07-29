from collections import defaultdict
from dataclasses import dataclass, field

from modules import modifier
from modules.character import faction, state


@dataclass
class RelationshipManager:
    """
    Manages the social web of relationships between all entities and factions.
    This class serves as the single source of truth for affinity and reputation.
    """

    # The core data structure for individual relationships.
    # Format: {source_entity_id: {target_entity_id: affinity_score}}
    # e.g., {"player_alex": {"npc_dale": 50}, "npc_dale": {"npc_sarah": 80}}
    affinities: dict[str, dict[str, int]] = field(
        default_factory=lambda: defaultdict(dict)
    )

    # The core data structure for faction-to-faction standings.
    # Format: {source_faction: {target_faction: reputation_score}}
    reputations: dict[faction.Faction, dict[faction.Faction, int]] = field(
        default_factory=lambda: defaultdict(dict)
    )

    def get_affinity(self, source_id: str, target_id: str) -> int:
        """
        Safely gets the affinity score of a source entity towards a target entity.
        Defaults to 0 if no specific relationship exists.
        """
        return self.affinities.get(source_id, {}).get(target_id, 0)

    def get_reputation(
        self, source_faction: faction.Faction, target_faction: faction.Faction
    ) -> int:
        """
        Safely gets the reputation score of a source faction towards a target faction.
        Defaults to 0 if no specific relationship exists.
        """
        return self.reputations.get(source_faction, {}).get(target_faction, 0)

    def apply_affinity_modifier(self, mod: modifier.AffinityAdjustment):
        """
        Applies a change to the affinity between two entities.
        Clamps the affinity value between a min and max to prevent runaway scores.
        """
        min_affinity = -100
        max_affinity = 100

        source_opinions = self.affinities.setdefault(mod.source_id, {})
        current_affinity = source_opinions.get(mod.target_id, 0)
        new_affinity = current_affinity + mod.amount

        # Clamp the value to the defined range
        clamped_affinity = max(min_affinity, min(new_affinity, max_affinity))

        source_opinions[mod.target_id] = clamped_affinity
        print(
            f"[Relationship] Affinity of '{mod.source_id}' towards '{mod.target_id}' is now {clamped_affinity}."
        )

    def apply_reputation_modifier(self, mod: modifier.ReputationAdjustment):
        """
        Applies a change to the reputation between two factions.
        Clamps the reputation value to prevent runaway scores.
        """
        min_reputation = -100
        max_reputation = 100

        source_faction_opinions = self.reputations.setdefault(mod.source_faction, {})
        current_reputation = source_faction_opinions.get(mod.target_faction, 0)
        new_reputation = current_reputation + mod.amount

        # Clamp the value
        clamped_reputation = max(min_reputation, min(new_reputation, max_reputation))

        source_faction_opinions[mod.target_faction] = clamped_reputation
        print(
            f"[Relationship] Reputation of Faction '{mod.source_faction.value}' towards '{mod.target_faction.value}' is now {clamped_reputation}."
        )

    def get_disposition_from_affinity(self, affinity: int) -> state.Disposition:
        """
        Calculates a Disposition enum based on a numerical affinity score.
        This can be called to determine an NPC's immediate emotional state.
        """
        if affinity >= 75:
            return state.Disposition.LOYAL
        if affinity >= 40:
            return state.Disposition.FRIENDLY
        if affinity <= -75:
            return state.Disposition.HATED
        if affinity <= -40:
            return state.Disposition.HOSTILE
        if affinity < 0:
            return state.Disposition.WARY

        return state.Disposition.NEUTRAL

    def get_disposition(self, source_id: str, target_id: str) -> state.Disposition:
        """
        Convenience method to get the disposition of one entity to another directly.
        """
        affinity = self.get_affinity(source_id, target_id)
        return self.get_disposition_from_affinity(affinity)
