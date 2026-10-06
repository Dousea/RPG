"""A single zombie: the traits it was rolled with and what it is doing (spec 09)."""

from dataclasses import dataclass
from enum import StrEnum

TIME_SINCE_SEEN_START = 100000.0  # spec 09: frames


class ZombieState(StrEnum):
    IDLE = "idle"
    ALERTED = "alerted"
    CHASING = "chasing"
    ATTACKING = "attacking"


class AttackSide(StrEnum):
    FRONT = "front"
    LEFT = "left"
    RIGHT = "right"
    BEHIND = "behind"


@dataclass
class ZombieEntity:
    """`gap` and `facing_cos` only matter while it shares the player's zone or chases."""

    zombie_id: str
    zone_id: str
    health: float
    speed_type: int
    speed_mod: float
    lunger: bool
    strength: int
    memory: int
    sight: int
    hearing: int
    state: ZombieState = ZombieState.IDLE
    gap: float = 0.0
    facing_cos: float = 0.0
    time_since_seen: float = TIME_SINCE_SEEN_START
    has_chased: bool = False
    bonus_spot_time: float = 0.0
    side: AttackSide | None = None
    sound_gap: float = 0.0

    @property
    def poor_sight(self) -> bool:
        return self.sight == 3

    @property
    def poor_hearing(self) -> bool:
        return self.hearing == 3
