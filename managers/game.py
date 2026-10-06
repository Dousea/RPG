import logging
import random
from dataclasses import dataclass, field
from datetime import date, timedelta

import config
from data.clock import (
    WORLD_START_MINUTE_OF_DAY,
    day_number,
    minute_of_day,
    time_of_day_at,
)
from data.items import ITEMS
from data.locations import STARTING_ZONE_ID, build_starting_locations
from data.npcs import STARTING_RELATIONSHIPS, build_starting_npcs
from data.perks import PERKS
from data.quests import build_starting_quests
from data.traits import TRAITS
from managers import locations
from managers.climate import ClimateEngine
from managers.events import apply_event_modifiers, broadcast_event
from managers.relationship import RelationshipManager
from modules.character.state import CharacterCondition
from modules.entity.item import ItemEntity
from modules.entity.npc import NpcEntity
from modules.entity.player import PlayerEntity
from modules.event import AnyEvent
from modules.location import Location, World
from modules.modifier import AffinityModifier
from modules.quest import QuestState

logger = logging.getLogger(__name__)

# Number of recent events kept in the prompt as short-term memory.
MAX_RECENT_EVENTS = config.game.max_recent_events

# Once the recent-event buffer is this full, the older half is summarized.
SUMMARY_THRESHOLD = config.game.summary_threshold

# `current_place` is LLM-authored text that flows into the next prompt and the
# UI panel, so it is bounded here rather than trusted.
MAX_PLACE_LENGTH = 80

# `death_cause` is an outcome-fact string (LLM-adjacent, via narration of
# engine-decided events), bounded the same way. Shared by
# SimulationCore._check_player_death (the sole producer) and
# adapters/save/codec.py (which must apply the same cap to a hand-edited or
# migrated save).
DEATH_CAUSE_MAX_LENGTH = 200

# The game has one clock: `NarrativeState.minutes`. `World.time` and
# `World.date` are a rendering of the same instant, derived by
# `_sync_world_clock`, so the game master never sees a stale time.

# The calendar date of day 1.
WORLD_START_DATE = date(2023, 10, 1)

# New worlds draw their seed below this (spec 04).
WORLD_SEED_LIMIT = 2**31


@dataclass
class NarrativeState:
    """Story-level state that has no home on the entity model.

    These are things the game master tracks in prose -- goals, world flags, the
    clock -- as opposed to the simulated values (hit points, survival stats) that live
    on PlayerEntity.
    """

    minutes: int = 0
    apocalypse_stage: str = "Normal"
    goals: dict[str, list[str]] = field(default_factory=lambda: {"short_term": [], "long_term": []})
    flags: dict[str, bool] = field(default_factory=dict[str, bool])
    # Flags the player has actually learned in the story, as opposed to ones
    # that are merely true in the simulation. Only these render in the
    # narrator prompt (managers/context.py) -- doc 11's knowledge firewall
    # applied to world flags, not just relationship scores.
    discovered_flags: set[str] = field(default_factory=set[str])
    player_status: list[str] = field(default_factory=list[str])
    # Defensive fallback only, never the normal path: actions are validated
    # and simulated *before* narration, so a refusal already reaches the
    # narrator as an [OUTCOMES] fact (managers/context.py). This holds the one
    # case that can slip past: an unexpected exception inside the Simulation
    # Core itself, which no [OUTCOMES] fact could describe.
    pending_corrections: list[str] = field(default_factory=list[str])
    # Set once Orton dies. The turn that kills him is still recorded and saved,
    # so reloading the page does not quietly resurrect him.
    game_over: bool = False
    death_cause: str = ""

    @property
    def day(self) -> int:
        return day_number(self.minutes)

    @property
    def hour(self) -> int:
        return minute_of_day(self.minutes) // 60

    @property
    def minute(self) -> int:
        return minute_of_day(self.minutes) % 60

    @property
    def time_of_day(self) -> str:
        return time_of_day_at(minute_of_day(self.minutes))


@dataclass
class MemoryState:
    """The game's event memory: recent buffer, full log, and summaries."""

    recent_events: list[str] = field(default_factory=list[str])
    full_event_log: list[str] = field(default_factory=list[str])
    summaries: list[str] = field(default_factory=list[str])


class GameManager:
    """
    The central orchestrator of the game. It holds the game state,
    processes player input, manages the event loop, and applies modifications.
    """

    def __init__(
        self,
        world: World | None = None,
        player: PlayerEntity | None = None,
        relationship_manager: RelationshipManager | None = None,
        npcs: dict[str, NpcEntity] | None = None,
        narrative: NarrativeState | None = None,
        memory: MemoryState | None = None,
        quests: dict[str, QuestState] | None = None,
        climate: ClimateEngine | None = None,
    ):
        """Build a manager. Every component defaults to its new-game value, so
        `GameManager()` starts a fresh game and the persistence layer can
        reconstruct a saved one by passing components in."""
        self.world = (
            world
            if world is not None
            else World(
                locations=build_starting_locations(),
                seed=random.Random().randrange(WORLD_SEED_LIMIT),
            )
        )
        self.climate = (
            climate
            if climate is not None
            else ClimateEngine(self.world.seed, WORLD_START_DATE, WORLD_START_MINUTE_OF_DAY)
        )
        self.player = (
            player
            if player is not None
            else PlayerEntity(
                name="Orton",
                current_location_id=STARTING_ZONE_ID,
                # His own front-door key. Leaving it on the floor of an
                # apartment he starts locked out of would strand him on turn
                # one -- see data/locations.py's apartment_door.
                inventory=[ItemEntity(item=ITEMS["item_apartment_key"])],
                traits=[
                    TRAITS["TraitID_Hemophobia"],
                    TRAITS["TraitID_SmallFrame"],
                ],
                perks=[
                    PERKS["PerkID_Charismatic"],
                ],
            )
        )
        self.npcs = npcs if npcs is not None else build_starting_npcs()
        self.narrative = narrative if narrative is not None else NarrativeState()
        self.memory = memory if memory is not None else MemoryState()
        self.quests: dict[str, QuestState] = (
            quests if quests is not None else build_starting_quests()
        )
        self.event_queue: list[AnyEvent] = []

        if relationship_manager is not None:
            self.relationship_manager = relationship_manager
        else:
            self.relationship_manager = RelationshipManager()
            for npc_id, scores in STARTING_RELATIONSHIPS.items():
                # Source is the NPC: these are their feelings about the player.
                self.relationship_manager.apply_affinity_modifier(
                    AffinityModifier(
                        source_id=npc_id,
                        target_id=self.player.entity_id,
                        amount=scores.get("affection", 0),
                    )
                )
                self.relationship_manager.adjust_trust(
                    npc_id, self.player.entity_id, scores.get("trust", 0)
                )

        # Whatever the world arrived with, the narrative clock is authoritative.
        # Doing this here also repairs saves written while the two could drift.
        self._sync_world_clock()

    # === Clock ===

    def _sync_world_clock(self) -> None:
        """Render the narrative clock onto `World.time` and `World.date`.

        Called on construction and whenever the narrative clock moves. Nothing
        else may write those two fields: they are a view, not a second clock.
        """
        narrative = self.narrative
        hour_12 = narrative.hour % 12 or 12
        suffix = "AM" if narrative.hour < 12 else "PM"
        self.world.time = f"{hour_12:02d}:{narrative.minute:02d} {suffix}"
        self.world.date = (WORLD_START_DATE + timedelta(days=narrative.day - 1)).isoformat()

    def advance_clock(self, minutes: int) -> None:
        """Move the one clock forward and re-render `World.time` / `World.date`."""
        self.narrative.minutes += minutes
        self._sync_world_clock()

    # === Lookup helpers ===

    @property
    def current_location(self) -> Location:
        return self.world.locations[self.player.current_location_id]

    def npcs_in_location(self, location_id: str) -> list[NpcEntity]:
        return [npc for npc in self.npcs.values() if npc.current_location_id == location_id]

    def resolve_npc(self, name: str) -> NpcEntity | None:
        """Resolve an NPC by display name or id, case-insensitively."""
        needle = name.strip().casefold()
        for npc in self.npcs.values():
            if needle in (npc.name.casefold(), npc.npc_id.casefold()):
                return npc
        return None

    def resolve_location(self, name: str) -> Location | None:
        return locations.resolve_location(name, self.current_location, self.world.locations)

    def resolve_zone_exact(self, name: str) -> Location | None:
        return locations.resolve_zone_exact(name, self.world.locations)

    def zone_path(self, start_id: str, target_id: str) -> list[str] | None:
        return locations.zone_path(self.world.locations, start_id, target_id)

    @staticmethod
    def _find_item_entity(entities: list[ItemEntity], name: str) -> ItemEntity | None:
        needle = name.strip().casefold()
        for entity in entities:
            if needle in (entity.item.name.casefold(), entity.item.id.casefold()):
                return entity
        return None

    def _ground_items(self) -> list[ItemEntity]:
        return [
            entity for entity in self.current_location.entities if isinstance(entity, ItemEntity)
        ]

    # === Memory ===

    def record_event(self, event_text: str) -> None:
        """Push an event into both the short-term buffer and the full log."""
        if not event_text:
            return
        self.memory.recent_events.insert(0, event_text)
        del self.memory.recent_events[MAX_RECENT_EVENTS:]
        self.memory.full_event_log.append(event_text)

    def events_pending_summary(self) -> list[str]:
        """Return the events that should be folded into a summary, or []."""
        if len(self.memory.full_event_log) < SUMMARY_THRESHOLD:
            return []
        already_summarized = len(self.memory.summaries) * SUMMARY_THRESHOLD
        pending = self.memory.full_event_log[already_summarized:]
        if len(pending) < SUMMARY_THRESHOLD:
            return []
        return pending[:SUMMARY_THRESHOLD]

    # === Action application ===
    #
    # State changes from proposed actions go through managers/validator.py and
    # managers/simulation.py, before any prose exists.

    @staticmethod
    def _as_condition(name: str) -> CharacterCondition | None:
        try:
            return CharacterCondition(name.strip().casefold())
        except ValueError:
            return None

    # === Event pipeline ===

    def drain_event_queue(self) -> None:
        """Process every queued event, broadcasting it and applying the
        modifiers the world's traits and perks produce in response."""
        while self.event_queue:
            current_event = self.event_queue.pop(0)
            logger.debug(f"Processing Event: {type(current_event).__name__}")
            apply_event_modifiers(
                self.relationship_manager, current_event, broadcast_event(current_event)
            )
