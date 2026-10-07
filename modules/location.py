from dataclasses import dataclass, field

from .entity import BaseEntity
from .entity.barrier import BarrierEntity
from .entity.corpse import CorpseEntity
from .entity.zombie import ZombieEntity


@dataclass
class Location:
    id: str
    name: str
    description: str
    connections: dict[str, str]  # e.g., {"out": "zone_building"}
    entities: list[BaseEntity] = field(
        default_factory=list[BaseEntity]
    )  # For players, items, doors, terminals, etc.
    # Other names the game master calls this place. A zone stands in for many
    # rooms, so "hallway", "lobby" and "stairwell" all resolve to the building.
    aliases: list[str] = field(default_factory=list[str])
    # What the player sleeps on here, and the spots inside the zone that
    # override it: a word in `current_place` selects its bed type (spec 02).
    bed_type: str = "floor"
    place_bed_types: dict[str, str] = field(default_factory=dict[str, str])
    # Rain and wind do not reach the player here (spec 04).
    indoors: bool = False
    # Which storey an indoor zone is on; upper floors hold heat differently (spec 06).
    floor: int = 0
    # The farthest a zombie in the zone can be from the player, the zone's size in
    # 8x8-tile chunks, and its per-chunk zombie intensity from 0 to 255 (spec 09).
    size_tiles: int = 8
    chunks: int = 1
    zombie_intensity: int = 0
    # The building the zone is part of, if any; a barrier of the building wakes everyone in it (spec 13).
    building: str | None = None

    def bed_type_at(self, place: str) -> str:
        """The bed type at a free-text spot inside this zone."""
        spot = place.casefold()
        for word, bed_type in self.place_bed_types.items():
            if word in spot:
                return bed_type
        return self.bed_type


@dataclass
class World:
    """The set of live locations, plus the wall clock.

    `time` and `date` are *derived*: GameManager renders them from the narrative
    clock (`NarrativeState.minutes`) via `_sync_world_clock`, and nothing else
    should write them. The defaults below are only what day 1, 08:00 renders as.
    """

    time: str = "08:00 AM"
    date: str = "2023-10-01"
    # Drawn once when a new game starts; fixes the weather for the whole game (spec 04).
    seed: int = 0
    # Mains power; nothing turns it off yet (spec 06).
    power_on: bool = True
    locations: dict[str, Location] = field(
        default_factory=dict[str, Location]
    )  # e.g., {"zone_home": Location(...)}
    # Game minute the dead started walking; None before then, and no zombies exist (spec 09).
    outbreak_started_at: int | None = None
    zombies: dict[str, ZombieEntity] = field(default_factory=dict[str, ZombieEntity])
    next_zombie_number: int = 1
    last_redistribution_minute: int | None = None
    # Zombies killed in each zone; the zone's population never grows back over them.
    zombie_kills: dict[str, int] = field(default_factory=dict[str, int])
    # Story beats that have fired, by id, with the game minute they fired (spec 10).
    fired_beats: dict[str, int] = field(default_factory=dict[str, int])
    # Doors and windows, each on the connection between two zones (spec 13).
    barriers: dict[str, BarrierEntity] = field(default_factory=dict[str, BarrierEntity])
    # Dead bodies by id, numbered c1, c2, ... in order of creation (spec 14).
    corpses: dict[str, CorpseEntity] = field(default_factory=dict[str, CorpseEntity])
    next_corpse_number: int = 1
    # The zone the smell of the dead was last reported in, so the fact is not repeated (spec 14).
    smell_zone_id: str | None = None
