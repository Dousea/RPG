from dataclasses import dataclass, field
from enum import StrEnum


class QuestStyle(StrEnum):
    NON_VIOLENT = "non-violent"
    VIOLENT = "violent"
    STEALTH = "stealth"
    DIPLOMATIC = "diplomatic"
    SOCIAL = "social"
    NEUTRAL = "neutral"


class QuestStatus(StrEnum):
    ACTIVE = "active"
    COMPLETED = "completed"
    FAILED = "failed"


@dataclass
class QuestState:
    """Minimal engine-tracked quest progress.

    Objectives are plain strings matched against the same kind of key the
    Simulation Core already uses internally (e.g. "discover:flag_name",
    "defeat:npc_marcus") -- there is no LLM verb that can mark a quest
    complete directly; only the engine advances one, by noticing a matching
    action was actually validated and resolved. A full Story Director that
    reacts to arbitrary world state (docs/07-story-architecture.md) is out of
    scope; this only tracks completion of a fixed objective list.
    """

    quest_id: str
    status: QuestStatus = QuestStatus.ACTIVE
    objectives: list[str] = field(default_factory=list[str])
    completed_objectives: list[str] = field(default_factory=list[str])

    def is_complete(self) -> bool:
        return all(objective in self.completed_objectives for objective in self.objectives)
