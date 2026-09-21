from dataclasses import dataclass, field
from datetime import date, timedelta

import config
from data.locations import build_starting_locations
from data.npcs import STARTING_RELATIONSHIPS, build_starting_npcs
from data.perks import PERKS
from data.quests import build_starting_quests
from data.traits import TRAITS
from managers.relationship import RelationshipManager
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

# The game has one clock. `NarrativeState.day` and `.time_of_day` are it;
# `World.time` and `World.date` are a wall-clock rendering of the same instant,
# derived by `_sync_world_clock`. They used to be independent, and since nothing
# ever wrote them the game master was told it was noon on 1 October 2023 for the
# entire game while the narrative clock moved underneath.
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
    goals: dict[str, list[str]] = field(
        default_factory=lambda: {"short_term": [], "long_term": []}
    )
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
    # Defensive fallback only, never the normal path: actions are now
    # validated and simulated *before* narration (see managers/validator.py,
    # managers/simulation.py, and the [OUTCOMES] section in
    # managers/context.py), so a refusal is already surfaced to the narrator
    # the same turn it happens. `GameEngine.play` no longer writes to this
    # field at all. It exists for the one case that can still slip past
    # pre-narration validation: an unexpected exception inside the Simulation
    # Core itself, which no [OUTCOMES] fact could describe because the
    # engine never finished deciding what happened. Kept as a list (not
    # retired outright) so that escape hatch still has somewhere to go.
    pending_corrections: list[str] = field(default_factory=list[str])


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
        self.world = (
            world
            if world is not None
            else World(locations=build_starting_locations())
        )
        self.player = (
            player
            if player is not None
            else PlayerEntity(
                name="Orton",
                current_location_id="location_id_hallway",
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
        return [
            npc
            for npc in self.npcs.values()
            if npc.current_location_id == location_id
        ]

    def resolve_npc(self, name: str) -> NpcEntity | None:
        """Resolve an NPC by display name or id, case-insensitively."""
        needle = name.strip().casefold()
        for npc in self.npcs.values():
            if needle in (npc.name.casefold(), npc.npc_id.casefold()):
                return npc
        return None

    def resolve_location(self, name: str) -> Location | None:
        """Resolve a location by id, display name, or a direction leading out of
        the player's current location ("north")."""
        needle = name.strip().casefold()
        if not needle:
            return None

        # A compass direction out of where the player is standing.
        for direction, loc_id in self.current_location.connections.items():
            if needle == direction.casefold() and loc_id in self.world.locations:
                return self.world.locations[loc_id]

        for loc_id, location in self.world.locations.items():
            if needle in (loc_id.casefold(), location.name.casefold()):
                return location
        return None

    @staticmethod
    def _find_item_entity(
        entities: list[ItemEntity], name: str
    ) -> ItemEntity | None:
        needle = name.strip().casefold()
        for entity in entities:
            if needle in (entity.item.name.casefold(), entity.item.id.casefold()):
                return entity
        return None

    def _ground_items(self) -> list[ItemEntity]:
        return [
            entity
            for entity in self.current_location.entities
            if isinstance(entity, ItemEntity)
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
        if TIMES_OF_DAY.index(target) < TIMES_OF_DAY.index(
            self.narrative.time_of_day
        ):
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
            print(f"[GameManager] Processing Event: {type(current_event).__name__}")

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

                    print(
                        f"[GameManager] Effect '{trait_or_perk.name}' on entity #'{entity.id}' ({role}) generated modifier: {type(mod).__name__}"
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
                print(
                    f"[GameManager] Event target is not an Entity: {event.target}. Cannot apply damage."
                )
                return

            event.target.hit_points -= final_damage
            print(
                f"[GameManager] Applied {final_damage} damage to #'{event.target.id}'. HP is now {event.target.hit_points}."
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

    def _event_matches_effect_handler(
        self, event: AnyEvent, handler: AnyEffect, role: str
    ) -> bool:
        """Whether an effect handler (from a trait's or perk's `.effects`)
        reacts to this event's type when held by the entity occupying `role`
        ("source" or "target"), via the explicit EVENT_TO_EFFECT_TYPES and
        EFFECT_REQUIRED_ROLE maps above."""
        if not isinstance(handler, EVENT_TO_EFFECT_TYPES.get(type(event), ())):
            return False
        required_role = EFFECT_REQUIRED_ROLE.get(type(handler))
        return required_role is None or required_role == role
