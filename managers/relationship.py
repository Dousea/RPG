from collections import defaultdict
from dataclasses import dataclass, field

from modules.character.faction import CharacterFaction
from modules.character.state import CharacterDisposition
from modules.modifier import AffinityModifier, ReputationModifier


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
    reputations: dict[CharacterFaction, dict[CharacterFaction, int]] = field(
        default_factory=lambda: defaultdict(dict)
    )

    # How much one entity trusts another. Tracked separately from affinity:
    # liking someone and relying on them are different axes, and the narrative
    # layer moves them independently.
    # Format: {source_entity_id: {target_entity_id: trust_score}}
    trusts: dict[str, dict[str, int]] = field(default_factory=lambda: defaultdict(dict))

    def get_trust(self, source_id: str, target_id: str) -> int:
        """Safely gets the trust score of a source entity towards a target."""
        return self.trusts.get(source_id, {}).get(target_id, 0)

    def adjust_trust(self, source_id: str, target_id: str, amount: int) -> int:
        """Applies a change to trust, clamped to the same range as affinity."""
        source_trust = self.trusts.setdefault(source_id, {})
        new_trust = max(-100, min(source_trust.get(target_id, 0) + amount, 100))
        source_trust[target_id] = new_trust
        print(
            f"[Relationship] Trust of '{source_id}' towards '{target_id}' is now {new_trust}."
        )
        return new_trust

    def get_affinity(self, source_id: str, target_id: str) -> int:
        """
        Safely gets the affinity score of a source entity towards a target entity.
        Defaults to 0 if no specific relationship exists.
        """
        return self.affinities.get(source_id, {}).get(target_id, 0)

    def get_reputation(
        self,
        source_faction: CharacterFaction,
        target_faction: CharacterFaction,
    ) -> int:
        """
        Safely gets the reputation score of a source faction towards a target
        Defaults to 0 if no specific relationship exists.
        """
        return self.reputations.get(source_faction, {}).get(target_faction, 0)

    def apply_affinity_modifier(self, mod: AffinityModifier):
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

    def apply_reputation_modifier(self, mod: ReputationModifier):
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
            f"[Relationship] Reputation of Faction '{mod.source_faction}' towards '{mod.target_faction}' is now {clamped_reputation}."
        )

    def get_disposition_from_affinity(self, affinity: int) -> CharacterDisposition:
        """
        Calculates a Disposition enum based on a numerical affinity score.
        This can be called to determine an NPC's immediate emotional
        """
        if affinity >= 75:
            return CharacterDisposition.LOYAL
        if affinity >= 40:
            return CharacterDisposition.FRIENDLY
        if affinity <= -75:
            return CharacterDisposition.HATED
        if affinity <= -40:
            return CharacterDisposition.HOSTILE
        if affinity < 0:
            return CharacterDisposition.WARY

        return CharacterDisposition.NEUTRAL

    def get_disposition(self, source_id: str, target_id: str) -> CharacterDisposition:
        """
        Convenience method to get the disposition of one entity to another directly.
        """
        affinity = self.get_affinity(source_id, target_id)
        return self.get_disposition_from_affinity(affinity)
