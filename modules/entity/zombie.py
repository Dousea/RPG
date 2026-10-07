"""A single zombie: the traits it was rolled with and what it is doing (zombies)."""

from dataclasses import dataclass, field
from enum import StrEnum

from modules.body.parts import BodyLocation
from modules.entity.item import ItemEntity

TIME_SINCE_SEEN_START = 100000.0  # zombies: frames


class ZombieState(StrEnum):
    IDLE = "idle"
    ALERTED = "alerted"
    CHASING = "chasing"
    ATTACKING = "attacking"
    THUMPING = "thumping"  # doors


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
    hits_taken: int = 0  # melee: it never resets
    down_until: int = 0  # melee: the clock minute it gets up
    staggered: bool = False  # melee: set by a hit or shove, cleared at the end of that minute
    thump_barrier: str | None = None  # doors: the barrier it pounds on, from its own zone's side
    thump_rate: float = 0.0  # doors: thumps per game minute
    thump_carry: float = 0.0  # doors: the fraction of a thump left for the next minute
    thump_cooldown: int = 0  # doors: minutes before it may thump again
    was_chasing: bool = False  # doors: chasing, not alerted, when it started thumping
    female: bool = False  # zombie-lifecycle: picks the outfit
    outfit: str = ""  # zombie-lifecycle
    worn: dict[BodyLocation, ItemEntity] = field(
        default_factory=dict[BodyLocation, ItemEntity]
    )  # zombie-lifecycle
    attached: ItemEntity | None = None  # zombie-lifecycle: the weapon stuck in it
    crawling: bool = False  # zombie-lifecycle
    become_crawler: bool = (
        False  # zombie-lifecycle: a hit flagged it; it crawls once it is on the ground
    )
    was_fake_dead: bool = (
        False  # zombie-lifecycle: it rose from a corpse and keeps that corpse's clothes
    )
    risen_from_player: bool = False  # zombie-lifecycle: it is the player's own body
    carried: list[ItemEntity] = field(
        default_factory=list[ItemEntity]
    )  # zombie-lifecycle and carrying-and-loot: the player's body's things and an outfit's bags

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
