"""TALK, GIVE and REQUEST: what saying and handing things to an NPC is worth (llm-contract).

Resolution only; the validator decides legality. Every score change goes through
`RelationshipManager`, with the NPC as source and the player as target.
"""

import random

from data.story import social as social_k
from data.story.topics import Topic
from managers import carry
from managers.game import GameManager
from modules.character.state import CharacterDisposition, CharacterTrust
from modules.entity.item import ItemEntity
from modules.entity.npc import NpcEntity
from modules.events.modifier import AffinityModifier
from modules.item import ConsumableItem
from modules.story.social import GIVE_KEY, SocialLog

REQUEST_FOLLOW = "follow"
REQUEST_GIVE = "give"

_GUARDED_DISPOSITIONS = (CharacterDisposition.HOSTILE, CharacterDisposition.HATED)

TRUST_ORDER = (
    CharacterTrust.BROKEN,
    CharacterTrust.GUARDED,
    CharacterTrust.UNFORMED,
    CharacterTrust.TENTATIVE,
    CharacterTrust.SOLID,
    CharacterTrust.UNWAVERING,
)


def trust_at_least(band: CharacterTrust, minimum: CharacterTrust) -> bool:
    return TRUST_ORDER.index(band) >= TRUST_ORDER.index(minimum)


def clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))


def locked_out(manager: GameManager, npc: NpcEntity, request: str) -> bool:
    """Whether a refusal of this request is still within its lockout."""
    refused = manager.narrative.social_log.refused_at(npc.npc_id, request)
    if refused is None:
        return False
    return manager.narrative.minutes - refused < social_k.REQUEST_REFUSAL_LOCKOUT_MIN


class SocialManager:
    def __init__(self, manager: GameManager, rng: random.Random) -> None:
        self._manager = manager
        self._rng = rng

    @property
    def _name(self) -> str:
        return self._manager.player.appearance.forename

    @property
    def _relationships(self):
        return self._manager.relationship_manager

    @property
    def _player_id(self) -> str:
        return self._manager.player.entity_id

    def _log(self) -> SocialLog:
        log = self._manager.narrative.social_log
        log.roll_to_day(self._manager.narrative.day)
        return log

    def trust_of(self, npc: NpcEntity) -> int:
        return self._relationships.get_trust(npc.npc_id, self._player_id)

    def disposition_of(self, npc: NpcEntity) -> CharacterDisposition:
        return self._relationships.get_disposition(npc.npc_id, self._player_id)

    def trust_band_of(self, npc: NpcEntity) -> CharacterTrust:
        return self._relationships.get_trust_level(npc.npc_id, self._player_id)

    # === Scores ===

    def _apply(self, npc: NpcEntity, key: str, affection: int, trust: int) -> list[str]:
        """Apply base deltas under the repetition and Guarded rules; returns the facts they cause."""
        log = self._log()
        repeats = log.count(npc.npc_id, key) + 1
        guarded = self.disposition_of(npc) in _GUARDED_DISPOSITIONS
        disposition_before, trust_before = self.disposition_of(npc), self.trust_band_of(npc)

        def scaled(delta: int) -> int:
            if delta <= 0:
                return delta
            delta = int(delta / repeats)
            return int(delta * social_k.GUARDED_POSITIVE_FACTOR) if guarded else delta

        d_affection, d_trust = scaled(affection), scaled(trust)
        if d_affection:
            self._relationships.apply_affinity_modifier(
                AffinityModifier(
                    source_id=npc.npc_id, target_id=self._player_id, amount=d_affection
                )
            )
        if d_trust:
            self._relationships.adjust_trust(npc.npc_id, self._player_id, d_trust)
        log.record_use(npc.npc_id, key)

        total = d_affection + d_trust
        if total > 0:
            facts = [f"{npc.name} responds warmly."]
        elif total < 0:
            facts = [f"{npc.name} bristles."]
        else:
            facts = [f"{npc.name} seems unmoved."]
        disposition_after, trust_after = self.disposition_of(npc), self.trust_band_of(npc)
        if disposition_after != disposition_before:
            facts.append(f"{npc.name} now regards {self._name} as {disposition_after.value}.")
        if trust_after != trust_before:
            facts.append(f"{npc.name}'s trust in {self._name} is now {trust_after.value}.")
        return facts

    # === TALK and GIVE ===

    def talk(self, npc: NpcEntity, approach: str, speech: str = "") -> list[str]:
        row = social_k.TALK_APPROACHES[approach]
        affection = row.affection
        if approach == "flirt" and not npc.romance_eligible:
            affection = social_k.FLIRT_INELIGIBLE_AFFECTION
        lead = row.fact.format(name=self._name, npc=npc.name)
        said = [social_k.SPEECH_FACT.format(name=self._name, speech=speech)] if speech else []
        return [lead, *said, *self._apply(npc, approach, affection, row.trust)]

    def give(self, entity: ItemEntity, npc: NpcEntity) -> list[str]:
        carry.take_out(self._manager.player, entity)
        npc.inventory.append(entity)
        food = isinstance(entity.item, ConsumableItem)
        delta = social_k.GIVE_FOOD_DELTA if food else social_k.GIVE_OTHER_DELTA
        lead = f"{self._name} gives {npc.name} the {entity.item.name}."
        return [lead, *self._apply(npc, GIVE_KEY, delta.affection, delta.trust)]

    # === REQUEST ===

    def follow_chance(self, npc: NpcEntity) -> float:
        if self.disposition_of(npc) in _GUARDED_DISPOSITIONS:
            return 0.0
        return clamp01(self.trust_of(npc) / social_k.REQUEST_FOLLOW_TRUST_DIVISOR)

    def give_chance(self, npc: NpcEntity) -> float:
        return clamp01(
            (self.trust_of(npc) - social_k.REQUEST_GIVE_TRUST_OFFSET)
            / social_k.REQUEST_GIVE_TRUST_DIVISOR
        )

    def _refuse(self, npc: NpcEntity, request: str) -> None:
        self._log().refuse(npc.npc_id, request, self._manager.narrative.minutes)

    def request_follow(self, npc: NpcEntity) -> list[str]:
        if npc.following or self._rng.random() < self.follow_chance(npc):
            npc.following = True
            return [f"{npc.name} agrees to follow {self._name}."]
        self._refuse(npc, REQUEST_FOLLOW)
        return [f"{npc.name} refuses to follow {self._name}."]

    def request_stay(self, npc: NpcEntity) -> list[str]:
        if not npc.following:
            return [f"{npc.name} wasn't following {self._name}."]
        npc.following = False
        return [f"{npc.name} stops following {self._name}."]

    def request_about(self, npc: NpcEntity, topic: Topic) -> tuple[list[str], str | None]:
        """Tell the topic if trust allows; returns the facts and the flag the telling reveals."""
        if not trust_at_least(self.trust_band_of(npc), topic.min_trust):
            return [f"{npc.name} deflects the question."], None
        self._manager.narrative.social_log.told_topics.add(topic.topic_id)
        return [f"{npc.name} tells {self._name}: {topic.fact}"], topic.discovers

    def request_give(self, npc: NpcEntity, entity: ItemEntity) -> list[str]:
        if self._rng.random() < self.give_chance(npc):
            npc.inventory.remove(entity)
            self._manager.player.inventory.append(entity)
            return [f"{npc.name} hands {self._name} the {entity.item.name}."]
        self._refuse(npc, REQUEST_GIVE)
        return [f"{npc.name} won't hand over the {entity.item.name}."]
