from dataclasses import dataclass, field

from modules.character.faction import CharacterFaction
from modules.character.state import CharacterCondition
from modules.entity import BaseEntity
from modules.entity.item import ItemEntity


@dataclass
class NpcEntity(BaseEntity):
    """A non-player character that lives in a location and can be talked to.

    `npc_id` is the stable identity used for saves and for RelationshipManager
    keys. `BaseEntity.id` is `id(self)`, which changes every process restart, so
    it must never be persisted or used as a relationship key.
    """

    npc_id: str
    name: str
    description: str
    current_location_id: str
    age: int | None = None
    faction: CharacterFaction = CharacterFaction.NEUTRAL
    personality: list[str] = field(default_factory=list[str])
    status: list[str] = field(default_factory=list[str])
    notes: str = ""
    romance_eligible: bool = False
    # What the NPC is currently trying to do -- shown to the narrator as
    # visible intent (managers/context.py), since goals are the kind of thing
    # Orton could plausibly infer from behavior.
    goals: list[str] = field(default_factory=list[str])
    # Fact-ids/topics this NPC currently knows. Deliberately never rendered
    # into a prompt wholesale -- the knowledge firewall means this exists
    # to gate what an NPC can truthfully say (a future dialogue system's
    # job), not to be read out directly.
    knowledge: set[str] = field(default_factory=set[str])
    conditions: list[CharacterCondition] = field(default_factory=list[CharacterCondition])
    inventory: list[ItemEntity] = field(default_factory=list[ItemEntity])
    base_max_hit_points: int = 100
    # Walks with the player: arrives with them whenever they change zone (llm-contract).
    following: bool = False

    @property
    def max_hit_points(self) -> int:
        return self.base_max_hit_points
