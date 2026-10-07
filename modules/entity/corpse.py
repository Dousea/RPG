"""A dead body lying in a zone (spec 14)."""

from dataclasses import dataclass, field

from .item import ItemEntity


@dataclass
class CorpseEntity:
    """What a corpse was and holds; `fake_dead` and `crawling` are never shown to the player."""

    corpse_id: str
    zone_id: str
    gap: float
    female: bool
    outfit: str
    died_at: int  # the game minute it was made
    rot_at_death: int  # 1, 2 or 3
    skeleton: bool = False
    # `attached` is the weapon stuck in the body; it is also in `contents` until taken
    contents: list[ItemEntity] = field(default_factory=list[ItemEntity])
    attached: ItemEntity | None = None
    searched: bool = False
    fake_dead: bool = False
    crawling: bool = False
    risen_from_player: bool = False
