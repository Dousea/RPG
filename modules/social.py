"""What has been said and asked today, and which topics have been told (spec 10)."""

from dataclasses import dataclass, field

GIVE_KEY = "give"


def _key(npc_id: str, label: str) -> str:
    return f"{npc_id}|{label}"


@dataclass
class SocialLog:
    """Per-day approach and `GIVE` counts, refused `ASK`s with their minute, told topics.

    The counts belong to one clock day; `roll_to_day` clears them when the day changes,
    which is the 00:00 reset.
    """

    day: int = 1
    counts: dict[str, int] = field(default_factory=dict[str, int])
    refusals: dict[str, int] = field(default_factory=dict[str, int])
    told_topics: set[str] = field(default_factory=set[str])

    def roll_to_day(self, day: int) -> None:
        if day != self.day:
            self.day = day
            self.counts.clear()

    def count(self, npc_id: str, label: str) -> int:
        return self.counts.get(_key(npc_id, label), 0)

    def record_use(self, npc_id: str, label: str) -> None:
        key = _key(npc_id, label)
        self.counts[key] = self.counts.get(key, 0) + 1

    def refuse(self, npc_id: str, request: str, minute: int) -> None:
        self.refusals[_key(npc_id, request)] = minute

    def refused_at(self, npc_id: str, request: str) -> int | None:
        return self.refusals.get(_key(npc_id, request))
