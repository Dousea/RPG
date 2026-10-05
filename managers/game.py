import logging
import re
from collections import deque
from dataclasses import dataclass, field
from datetime import date, timedelta

import config
from data.items import ITEMS
from data.locations import STARTING_ZONE_ID, ZONE_EXIT_NOUNS, build_starting_locations
from data.npcs import STARTING_RELATIONSHIPS, build_starting_npcs
from data.perks import PERKS
from data.quests import build_starting_quests
from data.traits import TRAITS
from managers.relationship import RelationshipManager
from modules.action import normalize_key
from modules.character.player import PlayerPerk, PlayerTrait
from modules.character.state import CharacterCondition
from modules.effect import (
    AnyEffect,
    ItemAppliedEffect,
    ItemConsumedEffect,
    QuestCompletedEffect,
    WeaponDamageDealtEffect,
    WeaponDamageTakenEffect,
)
from modules.entity import BaseEntity
from modules.entity.item import ItemEntity
from modules.entity.npc import NpcEntity
from modules.entity.player import PlayerEntity
from modules.event import (
    AnyEvent,
    ApplyItemEvent,
    ConsumeItemEvent,
    QuestCompletionEvent,
    WeaponDealDamageEvent,
    WeaponTakeDamageEvent,
)
from modules.location import Location, World
from modules.modifier import (
    AffinityModifier,
    AnyModifier,
    ConditionsModifier,
    DamageMultiplicativeModifier,
    HPModifier,
    ReputationModifier,
)
from modules.quest import QuestState

logger = logging.getLogger(__name__)

# Which effect-handler classes react to which event classes. Used to be a
# `handler_name.startswith(event_name)` string comparison, which never once
# matched (e.g. "WeaponDamageTakenEffect".startswith("WeaponTakeDamageEvent")
# is False -- the words are transposed), so no trait or perk effect in
# data/traits.py or data/perks.py has ever fired.
EVENT_TO_EFFECT_TYPES: dict[type, tuple[type, ...]] = {
    WeaponDealDamageEvent: (WeaponDamageDealtEffect,),
    WeaponTakeDamageEvent: (WeaponDamageTakenEffect,),
    ApplyItemEvent: (ItemAppliedEffect,),
    ConsumeItemEvent: (ItemConsumedEffect,),
    QuestCompletionEvent: (QuestCompletedEffect,),
}

# Which of an event's two roles ("source" or "target") an entity must occupy
# for a given effect type to be eligible to react at all. Without this, an
# attacker who happens to also carry a "damage taken" trait would have it
# fire off their own outgoing hit.
EFFECT_REQUIRED_ROLE: dict[type, str] = {
    WeaponDamageDealtEffect: "source",
    WeaponDamageTakenEffect: "target",
    ItemAppliedEffect: "target",
    ItemConsumedEffect: "source",
    QuestCompletedEffect: "source",
}

# Number of recent events kept in the prompt as short-term memory.
MAX_RECENT_EVENTS = config.game.max_recent_events

# Once the recent-event buffer is this full, the older half is summarized.
SUMMARY_THRESHOLD = config.game.summary_threshold

TIMES_OF_DAY = ("morning", "afternoon", "evening", "night")

# Words the model reaches for in place of a bare connection direction. Applied
# only when the mapped direction is actually a connection of the current zone
# (see `resolve_location`) -- otherwise "outside" from the street would match
# the zone_street alias of the same name instead of following the exit out.
DIRECTION_SYNONYMS = {"inside": "in", "outside": "out"}

# `current_place` is LLM-authored text that flows into the next prompt and the
# UI panel, so it is bounded here rather than trusted.
MAX_PLACE_LENGTH = 80

# `death_cause` is an outcome-fact string (LLM-adjacent, via narration of
# engine-decided events), bounded the same way. Shared by
# SimulationCore._check_player_death (the sole producer) and
# adapters/persistence.py (which must apply the same cap to a hand-edited or
# migrated save).
DEATH_CAUSE_MAX_LENGTH = 200

# Direction words with no destination behind them. If one of these did not
# match a connection, it describes a shuffle inside the current zone -- it is
# not the name of a place, so it must not be stored as one.
BARE_DIRECTIONS = frozenset(
    {
        "north",
        "south",
        "east",
        "west",
        "up",
        "down",
        "in",
        "out",
        "inside",
        "outside",
        "back",
        "forward",
        "left",
        "right",
        "upstairs",
        "downstairs",
        "onwards",
        "onward",
        "further",
    }
)

# Laddered narrative conditions: rungs the field can hold, worst-to-best order
# not implied -- position in the tuple is what "+1"/"-1" steps along.
CONDITION_LADDERS: dict[str, tuple[str, ...]] = {
    "sleep": ("Rested", "Tired", "Drowsy", "Exhausted"),
    "infection_risk": ("No", "Low", "Moderate", "High", "Infected"),
}

# Words the model reaches for that are not rungs. Keys are normalized.
CONDITION_SYNONYMS: dict[str, dict[str, str]] = {
    "sleep": {
        "none": "Rested",
        "fine": "Rested",
        "well_rested": "Rested",
        "rested": "Rested",
        "fatigued": "Tired",
        "sleepy": "Drowsy",
        "tired": "Tired",
    },
    "infection_risk": {
        "none": "No",
        "no": "No",
        "safe": "No",
        "minimal": "Low",
        "medium": "Moderate",
        "moderate": "Moderate",
        "severe": "High",
        "critical": "High",
        "infected": "Infected",
    },
}


def _first_contiguous_match(haystack: list[str], needle: list[str]) -> int | None:
    """The index in `haystack` where `needle` first appears as a contiguous,
    in-order run, or None. Used by `GameManager.resolve_location`'s
    whole-word fallback -- a subset test (`set(needle) <= set(haystack)`)
    let "the street" and "the building" both claim position 0 of any phrase
    starting with "the", regardless of where their real words actually sat.
    """
    span = len(needle)
    for start in range(len(haystack) - span + 1):
        if haystack[start : start + span] == needle:
            return start
    return None


def _exit_noun_prefix(words: list[str]) -> tuple[str, int] | None:
    """The zone whose ZONE_EXIT_NOUNS entry starts `words`, with that noun's
    word count, or None. The longest noun wins, so "apartment building" is the
    building rather than "apartment" (home) followed by a stray word.
    """
    best: tuple[str, int] | None = None
    for zone_id, nouns in ZONE_EXIT_NOUNS.items():
        for noun in nouns:
            noun_words = noun.split()
            if words[: len(noun_words)] == noun_words and (
                best is None or len(noun_words) > best[1]
            ):
                best = (zone_id, len(noun_words))
    return best


def resolve_condition_value(field: str, raw: str, current: str) -> str | None:
    """Resolve a laddered condition update to its new rung, or None if invalid.

    Pure: no mutation. A signed step ('+1'/'-2') moves `current` along
    `CONDITION_LADDERS[field]`, clamped to its ends -- unlike the numeric
    tracks these have no natural arithmetic, but the model writes '+1' at
    them anyway, so a signed value walks the ladder instead of being stored
    verbatim (so 'Infection Risk: +1' never reaches the UI as literal
    text). Otherwise the value is matched case-insensitively against a
    rung name, then a synonym. `ActionValidator` calls this to decide
    Accepted/Rejected; `SimulationCore` stores whatever it returned.
    """
    ladder = CONDITION_LADDERS[field]

    if raw and raw[0] in "+-" and raw[1:].isdigit():
        try:
            position = ladder.index(current)
        except ValueError:
            position = 0
        step = int(raw)
        return ladder[max(0, min(position + step, len(ladder) - 1))]

    needle = normalize_key(raw)
    for rung in ladder:
        if needle == rung.casefold():
            return rung

    return CONDITION_SYNONYMS.get(field, {}).get(needle)


# The game has one clock. `NarrativeState.day` and `.time_of_day` are it;
# `World.time` and `World.date` are a wall-clock rendering of the same instant,
# derived by `_sync_world_clock`, so the game master never sees a stale time.
CLOCK_BY_TIME_OF_DAY = {
    "morning": "08:00 AM",
    "afternoon": "01:00 PM",
    "evening": "07:00 PM",
    "night": "11:00 PM",
}

# The calendar date of day 1.
WORLD_START_DATE = date(2023, 10, 1)


@dataclass
class NarrativeState:
    """Story-level state that has no home on the entity model.

    These are things the game master tracks in prose -- goals, world flags, the
    clock -- as opposed to the simulated values (hit points, hunger) that live
    on PlayerEntity.
    """

    day: int = 1
    time_of_day: str = "morning"
    apocalypse_stage: str = "Normal"
    goals: dict[str, list[str]] = field(default_factory=lambda: {"short_term": [], "long_term": []})
    flags: dict[str, bool] = field(default_factory=dict[str, bool])
    # Flags the player has actually learned in the story, as opposed to ones
    # that are merely true in the simulation. Only these render in the
    # narrator prompt (managers/context.py) -- doc 11's knowledge firewall
    # applied to world flags, not just relationship scores.
    discovered_flags: set[str] = field(default_factory=set[str])
    player_status: list[str] = field(default_factory=list[str])
    conditions: dict[str, str] = field(
        default_factory=lambda: {"sleep": "Rested", "infection_risk": "No"}
    )
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
    ):
        """Build a manager. Every component defaults to its new-game value, so
        `GameManager()` starts a fresh game and the persistence layer can
        reconstruct a saved one by passing components in."""
        self.world = world if world is not None else World(locations=build_starting_locations())
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
        self.world.time = CLOCK_BY_TIME_OF_DAY.get(
            self.narrative.time_of_day, CLOCK_BY_TIME_OF_DAY["morning"]
        )
        days_elapsed = max(self.narrative.day, 1) - 1
        self.world.date = (WORLD_START_DATE + timedelta(days=days_elapsed)).isoformat()

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
        """Resolve a zone by connection direction, id, display name, or alias.

        Returns None when nothing matches. That matters: `NPC_MOVE` resolves
        through here too, and NPCs have no free-text place to fall back on, so a
        resolver that always succeeded would scatter them into invented zones.
        """
        needle = name.strip().strip("\"'.,;:!?").casefold()
        if not needle:
            return None

        # A direction out of where the player is standing ("out", "in"), with
        # DIRECTION_SYNONYMS applied first -- but only ever matches an actual
        # connection key, so an unmapped synonym simply falls through below.
        needle_direction = DIRECTION_SYNONYMS.get(needle, needle)
        for direction, loc_id in self.current_location.connections.items():
            if needle_direction == direction.casefold() and loc_id in self.world.locations:
                return self.world.locations[loc_id]

        # Zone identity, matched globally. Adjacency is deliberately not
        # enforced here: resolve_location backs narration and NPC_MOVE, not
        # player movement legality (that's `ActionValidator._validate_move`).
        for loc_id, location in self.world.locations.items():
            if needle in (loc_id.casefold(), location.name.casefold()):
                return location
            if any(needle == alias.casefold() for alias in location.aliases):
                return location

        # Exit phrases ("outside the building", "out of the building",
        # "leave the apartment", "exit my flat") mean walk *out* of the zone
        # Orton is standing in right now -- but only when the phrase's object
        # names the zone itself (ZONE_EXIT_NOUNS), never a landmark inside it.
        # "outside the bodega" while already on the street must not walk him
        # into the neighborhood, and "outside Emma's apartment" while in the
        # building must not walk him onto the street -- both fall through to
        # the whole-word fallback below instead, which lands him on the
        # landmark itself. This runs before that fallback (an exit phrase is
        # never itself a landmark name) and is keyed off the *current* zone,
        # not whatever the fallback would have matched.
        #
        # The zone noun only has to *start* the object, so trailing words
        # ("leave the building now", "exit the building to the street") still
        # count. An exit phrase naming some *other* zone ("exit the building
        # to the street" said on the street) can't be walked out of from here,
        # so that zone must not win; whatever follows the noun decides, and
        # nothing following means a spot where Orton already is.
        exit_match = re.match(
            r"^(?:outside(?: of)?|out of|leaving|leave|exiting|exit)\s+"
            r"(?:(?:the|my|your|this|orton's)\s+)?(.+)$",
            needle,
        )
        if exit_match:
            exit_words = re.findall(r"[a-z0-9']+", exit_match.group(1))
            named = _exit_noun_prefix(exit_words)
            if named is not None:
                zone_id, noun_length = named
                if zone_id == self.current_location.id:
                    out_id = self.current_location.connections.get("out")
                    if out_id is not None and out_id in self.world.locations:
                        return self.world.locations[out_id]
                    return self.current_location
                rest = " ".join(exit_words[noun_length:])
                return self.resolve_location(rest) if rest else None

        # Last pass: the model writes "back to my apartment" or "the lobby
        # downstairs" rather than a bare name. Only whole words count, and only
        # names long enough not to collide by accident -- a loose substring
        # match here would quietly send the player to the wrong zone, which is
        # the failure mode this whole design is meant to avoid.
        #
        # A trailing possessive 's is stripped from every token
        # before matching ("clinic's" -> "clinic"), and a leading "the" is
        # dropped from the candidate's own words (so "the street" matches as
        # "street"). The candidate must then appear as a contiguous, in-order
        # run of words in the phrase -- a subset test would let "the
        # street" and "the building" both claim position 0 of any phrase
        # starting with "the" ("the street outside the building" must not go
        # to the building). The winning candidate is the one whose run starts
        # earliest in the phrase. "the street outside my apartment" must
        # resolve to "street" (starts at word 1) over "my apartment" (starts
        # at word 3). Ties break by more words, then by the current zone.
        phrase_words = [
            word[:-2] if word.endswith("'s") else word for word in re.findall(r"[a-z0-9']+", needle)
        ]

        best: tuple[tuple[int, int, int], Location] | None = None
        for location in self.world.locations.values():
            for candidate in (location.name, *location.aliases):
                folded = candidate.casefold()
                if len(folded) < 4:
                    continue
                candidate_words = [
                    word[:-2] if word.endswith("'s") else word
                    for word in re.findall(r"[a-z0-9']+", folded)
                ]
                if candidate_words and candidate_words[0] == "the":
                    candidate_words = candidate_words[1:]
                if not candidate_words:
                    continue
                position = _first_contiguous_match(phrase_words, candidate_words)
                if position is None:
                    continue
                is_current_zone = 0 if location.id == self.current_location.id else 1
                score = (position, -len(candidate_words), is_current_zone)
                if best is None or score < best[0]:
                    best = (score, location)

        return best[1] if best is not None else None

    def resolve_zone_exact(self, name: str) -> Location | None:
        """Resolve a zone strictly: id, display name, or an exact global
        alias only, casefolded and stripped.

        `NPC_MOVE` uses this instead of `resolve_location`. NPCs have no
        free-text spot to fall back on, so the player's forgiving resolution
        -- connection directions, the whole-word fallback, exit phrases -- is
        deliberately not available here: it exists to turn a vague phrase
        into *somewhere* for prose to keep going, which is the wrong
        trade-off for an engine-issued NPC placement.
        """
        needle = name.strip().strip("\"'.,;:").casefold()
        if not needle:
            return None
        for location in self.world.locations.values():
            if needle in (location.id.casefold(), location.name.casefold()):
                return location
            if any(needle == alias.casefold() for alias in location.aliases):
                return location
        return None

    def zone_path(self, start_id: str, target_id: str) -> list[str] | None:
        """BFS over `Location.connections` from `start_id` to `target_id`.

        Returns the hop list (zone ids), excluding `start_id` itself, so
        callers can walk it one connection at a time and stop at the first
        locked door they can't get through. `None` means the two zones are
        not connected at all -- not reachable with the shipped map, but a
        possible future one, so `_validate_move` still has to handle it.
        """
        if start_id == target_id:
            return []
        visited = {start_id}
        queue: deque[tuple[str, list[str]]] = deque([(start_id, [])])
        while queue:
            current_id, path = queue.popleft()
            location = self.world.locations.get(current_id)
            if location is None:
                continue
            for loc_id in location.connections.values():
                if loc_id in visited:
                    continue
                new_path = path + [loc_id]
                if loc_id == target_id:
                    return new_path
                visited.add(loc_id)
                queue.append((loc_id, new_path))
        return None

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

    # === Prompt building ===
    #
    # Delegated to managers/context.py's ContextBuilder, which is the actual
    # knowledge-firewall boundary (doc 11) -- kept as thin methods here so
    # existing callers don't need to know about ContextBuilder directly.

    def build_parser_prompt(self, player_input: str) -> str:
        from managers.context import ContextBuilder

        return ContextBuilder(self).build_parser_prompt(player_input)

    def build_narrator_prompt(
        self,
        player_input: str,
        outcome_facts: list[str] | None = None,
        deep_memories: list[str] | None = None,
    ) -> str:
        from managers.context import ContextBuilder

        return ContextBuilder(self).build_narrator_prompt(
            player_input, outcome_facts, deep_memories
        )

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
    # There is no `apply_action`/`_ACTION_HANDLERS` dispatch anymore: the
    # Action Validator (managers/validator.py) and Simulation Core
    # (managers/simulation.py) are the only path to mutating state from a
    # proposed action, and they run before any prose exists rather than
    # after. `_action_time_advance` and `_as_condition` remain because
    # SimulationCore calls them directly -- the day-rollover and
    # condition-mapping logic they hold didn't need to move.

    def _action_time_advance(self, args: str) -> tuple[bool, str]:
        target = args.strip().casefold()
        if target not in TIMES_OF_DAY:
            return False, f"Unknown time of day: '{args}'."
        # Rolling *backwards* past night means a new day began. Strictly
        # backwards: re-declaring the part of the day we are already in is a
        # no-op, not midnight.
        if TIMES_OF_DAY.index(target) < TIMES_OF_DAY.index(self.narrative.time_of_day):
            self.narrative.day += 1
        self.narrative.time_of_day = target
        self._sync_world_clock()
        return True, f"Time is now {target} (day {self.narrative.day})."

    @staticmethod
    def _as_condition(name: str) -> CharacterCondition | None:
        try:
            return CharacterCondition(name.strip().casefold())
        except ValueError:
            return None

    # === Event pipeline ===
    #
    # `managers/simulation.py` is the real caller now: combat calls
    # `_broadcast_event` directly (it needs to combine "dealt" and "taken"
    # modifiers from two events before applying damage once), and item use
    # does the same. `drain_event_queue`/`_apply_modifiers`/`event_queue`
    # remain as a single-event broadcast+apply convenience for any future
    # event that only needs one perspective.

    def drain_event_queue(self) -> None:
        """Process every queued event, broadcasting it and applying the
        modifiers the world's traits and perks produce in response."""
        while self.event_queue:
            current_event = self.event_queue.pop(0)
            logger.debug(f"Processing Event: {type(current_event).__name__}")

            all_modifiers = self._broadcast_event(current_event)
            self._apply_modifiers(current_event, all_modifiers)

    def _broadcast_event(self, event: AnyEvent) -> list[AnyModifier]:
        """
        Sends an event to its source and target and collects their reactions.

        An entity's effect only reacts in the role it is written for: a
        `WeaponDamageTakenEffect` fires only for the entity that is this
        event's *target*, never for one that merely also appears as its
        source (e.g. the attacker's own Small Frame must not treat their own
        swing as damage they took). `EFFECT_REQUIRED_ROLE` encodes that.
        """
        collected_modifiers: list[AnyModifier] = []

        role_entities: dict[str, BaseEntity] = {}
        source = getattr(event, "source", None)
        target = getattr(event, "target", None)
        if isinstance(source, BaseEntity):
            role_entities["source"] = source
        if isinstance(target, BaseEntity):
            role_entities["target"] = target

        for role, entity in role_entities.items():
            all_effects: list[PlayerTrait | PlayerPerk] = []
            if hasattr(entity, "traits"):
                all_effects.extend(getattr(entity, "traits", []))
            if hasattr(entity, "perks"):
                all_effects.extend(getattr(entity, "perks", []))

            for trait_or_perk in all_effects:
                for effect_handler in trait_or_perk.effects:
                    if not self._event_matches_effect_handler(event, effect_handler, role):
                        continue

                    condition = getattr(effect_handler, "condition", None)
                    effect = getattr(effect_handler, "effect", None)

                    if condition is None or not callable(condition):
                        continue

                    if effect is None or not callable(effect):
                        continue

                    if not condition(event):
                        continue

                    mod = effect(event)

                    if not isinstance(mod, AnyModifier):
                        continue

                    logger.debug(
                        f"Effect '{trait_or_perk.name}' on entity #'{entity.id}' ({role}) generated modifier: {type(mod).__name__}"
                    )
                    collected_modifiers.append(mod)

        return collected_modifiers

    def _apply_modifiers(self, event: AnyEvent, modifiers: list[AnyModifier]):
        """
        Applies a list of collected modifiers to the game state in a controlled order.
        """
        # This is where the logic from our previous discussions goes.
        # You would sort or process modifiers based on their type.

        # Example for damage calculation:
        if isinstance(event, (WeaponDealDamageEvent, WeaponTakeDamageEvent)):
            base_damage = event.damage
            damage_multiplier = 1.0

            for mod in modifiers:
                if isinstance(mod, DamageMultiplicativeModifier):
                    damage_multiplier *= mod.multiplier

            final_damage = int(base_damage * damage_multiplier)

            if not isinstance(event.target, BaseEntity):
                logger.warning(
                    f"Event target is not an Entity: {event.target}. Cannot apply damage."
                )
                return

            event.target.hit_points -= final_damage
            logger.debug(
                f"Applied {final_damage} damage to #'{event.target.id}'. HP is now {event.target.hit_points}."
            )

        # Every other modifier type applies to the event's target (falling
        # back to its source for an event with no target), which is the
        # entity the reaction was about.
        target = getattr(event, "target", None)
        source = getattr(event, "source", None)
        recipient = target if isinstance(target, BaseEntity) else source

        for mod in modifiers:
            if isinstance(mod, AffinityModifier):
                self.relationship_manager.apply_affinity_modifier(mod)
            elif isinstance(mod, ReputationModifier):
                self.relationship_manager.apply_reputation_modifier(mod)
            elif isinstance(mod, HPModifier) and isinstance(recipient, BaseEntity):
                recipient.hit_points += mod.amount
            elif isinstance(mod, ConditionsModifier) and isinstance(recipient, BaseEntity):
                for condition, active in mod.conditions.items():
                    conditions = getattr(recipient, "conditions", None)
                    if conditions is None:
                        continue
                    if active and condition not in conditions:
                        conditions.append(condition)
                    elif not active and condition in conditions:
                        conditions.remove(condition)
            # AttributesModifier/XPModifier/XPMultiplicativeModifier have no
            # current producer on this path (OnceEffect runs at character
            # creation, not per-event; QuestCompletionEvent has no emitter
            # yet -- a real Story Director is doc 07, out of scope here) and
            # are intentionally left unhandled rather than guessed at.

    def _event_matches_effect_handler(self, event: AnyEvent, handler: AnyEffect, role: str) -> bool:
        """Whether an effect handler (from a trait's or perk's `.effects`)
        reacts to this event's type when held by the entity occupying `role`
        ("source" or "target"), via the explicit EVENT_TO_EFFECT_TYPES and
        EFFECT_REQUIRED_ROLE maps above."""
        if not isinstance(handler, EVENT_TO_EFFECT_TYPES.get(type(event), ())):
            return False
        required_role = EFFECT_REQUIRED_ROLE.get(type(handler))
        return required_role is None or required_role == role
