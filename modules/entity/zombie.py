"""A single zombie: the traits it was rolled with and what it is doing (spec 09)."""

from dataclasses import dataclass, field
from enum import StrEnum

from ..body import BodyLocation
from .item import ItemEntity

TIME_SINCE_SEEN_START = 100000.0  # spec 09: frames


class ZombieState(StrEnum):
    IDLE = "idle"
    ALERTED = "alerted"
    CHASING = "chasing"
    ATTACKING = "attacking"
    THUMPING = "thumping"  # spec 13


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
    hits_taken: int = 0  # spec 11: it never resets
    down_until: int = 0  # spec 11: the clock minute it gets up
    staggered: bool = False  # spec 11: set by a hit or shove, cleared at the end of that minute
    thump_barrier: str | None = None  # spec 13: the barrier it pounds on, from its own zone's side
    thump_rate: float = 0.0  # spec 13: thumps per game minute
    thump_carry: float = 0.0  # spec 13: the fraction of a thump left for the next minute
    thump_cooldown: int = 0  # spec 13: minutes before it may thump again
    was_chasing: bool = False  # spec 13: chasing, not alerted, when it started thumping
    female: bool = False  # spec 14: picks the outfit
    outfit: str = ""  # spec 14
    worn: dict[BodyLocation, ItemEntity] = field(
        default_factory=dict[BodyLocation, ItemEntity]
    )  # spec 14
    attached: ItemEntity | None = None  # spec 14: the weapon stuck in it
    crawling: bool = False  # spec 14
    become_crawler: bool = False  # spec 14: a hit flagged it; it crawls once it is on the ground
    was_fake_dead: bool = False  # spec 14: it rose from a corpse and keeps that corpse's clothes
    risen_from_player: bool = False  # spec 14: it is the player's own body
    carried: list[ItemEntity] = field(
        default_factory=list[ItemEntity]
    )  # spec 14, 25: the player's body's things and an outfit's bags

    def is_down(self, now: int) -> bool:
        """Whether it is on the floor during the minute that starts at clock minute `now`."""
        return now < self.down_until

    def on_floor(self, now: int) -> bool:
        """Whether it lies on the ground: knocked down, or a crawler."""
        return self.crawling or self.is_down(now)

    @property
    def poor_sight(self) -> bool:
        return self.sight == 3

    @property
    def poor_hearing(self) -> bool:
        return self.hearing == 3
