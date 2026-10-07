"""Exercises and the training state a character carries (skills)."""

from dataclasses import dataclass, field


@dataclass(frozen=True)
class ExerciseDefinition:
    """`item_id` is the item the exercise needs, or empty; `regions` are the stiffness regions it trains."""

    id: str
    name: str
    regions: tuple[str, ...]
    heavy: bool
    xp_mod: float
    rep_period_s: float
    item_id: str = ""


@dataclass
class ExerciseState:
    """Regularity per exercise, when each was last done, and the stiffness still to come."""

    regularity: dict[str, float] = field(default_factory=dict[str, float])
    last_done_minute: dict[str, int] = field(default_factory=dict[str, int])
    future_stiffness: dict[str, float] = field(default_factory=dict[str, float])
    region_timers: dict[str, int] = field(default_factory=dict[str, int])
