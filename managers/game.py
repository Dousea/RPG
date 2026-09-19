from dataclasses import dataclass, field
from datetime import date, timedelta

import config
from data.items import find_item_by_name
from data.locations import build_starting_locations
from data.npcs import STARTING_RELATIONSHIPS, build_starting_npcs
from data.perks import PERKS
from data.traits import TRAITS
from managers.relationship import RelationshipManager
from modules.character.player import PlayerPerk, PlayerTrait
from modules.character.state import CharacterCondition
from modules.effect import AnyEffect
from modules.entity import BaseEntity
from modules.entity.item import ItemEntity
from modules.entity.npc import NpcEntity
from modules.entity.player import PlayerEntity
from modules.event import AnyEvent, WeaponDealDamageEvent, WeaponTakeDamageEvent
from modules.location import Location, World
from modules.modifier import (
    AffinityModifier,
    AnyModifier,
    DamageMultiplicativeModifier,
    ReputationModifier,
)

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

# Narrative condition tracks that have no numeric field on PlayerEntity.
NARRATIVE_CONDITIONS = ("sleep", "infection_risk")


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
    player_status: list[str] = field(default_factory=list[str])
    conditions: dict[str, str] = field(
        default_factory=lambda: {"sleep": "Rested", "infection_risk": "No"}
    )


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

    # === Prompt sections ===

    def _get_current_items_section(self) -> str:
        """Generate the items section for the current location."""
        items = self._ground_items()
        if not items:
            return "No items here."

        items_str = "\n".join(f" - {item.item.name}" for item in items)
        return items_str

    def _get_nearby_locations_section(self) -> str:
        """Generate the nearby locations section."""
        current_location = self.current_location

        if not current_location.connections:
            return "No exits visible."

        nearby_str = "\n".join(
            f" - {direction.capitalize()}: {self.world.locations[loc_id].name}"
            for direction, loc_id in current_location.connections.items()
            if loc_id in self.world.locations
        )
        return nearby_str

    def _get_npcs_present_section(self) -> str:
        """Generate the NPCs present section, with how each one currently
        regards the player."""
        npcs = self.npcs_in_location(self.player.current_location_id)
        if not npcs:
            return "No one else is here."

        lines: list[str] = []
        for npc in npcs:
            disposition = self.relationship_manager.get_disposition(
                npc.npc_id, self.player.entity_id
            )
            affinity = self.relationship_manager.get_affinity(
                npc.npc_id, self.player.entity_id
            )
            trust = self.relationship_manager.get_trust(
                npc.npc_id, self.player.entity_id
            )
            lines.append(
                f" - {npc.name}"
                f"{f' ({npc.age})' if npc.age is not None else ''}: {npc.description}"
            )
            lines.append(
                f"   Disposition: {disposition} "
                f"(affection {affinity:+d}, trust {trust:+d})"
            )
            if npc.status:
                lines.append(f"   Status: {', '.join(npc.status)}")
            if npc.personality:
                lines.append(f"   Personality: {', '.join(npc.personality)}")
            if npc.notes:
                lines.append(f"   Notes: {npc.notes}")
        return "\n".join(lines)

    def _get_summary_section(self) -> str:
        if not self.memory.summaries:
            return "(No summary available yet)"
        return "\n\n".join(self.memory.summaries)

    def _get_events_section(self) -> str:
        if not self.memory.recent_events:
            return "(No recent events)"
        return "\n".join(f" - {event}" for event in self.memory.recent_events)

    def build_prompt(self, player_input: str, deep_memories: list[str] | None = None) -> str:
        """Assemble the full LLM prompt for a turn.

        `deep_memories` are semantically retrieved past events supplied by the
        memory layer; they are woven in as a separate section so the model can
        tell recalled history from what just happened.
        """
        inventory_str = "\n".join(
            f" - {entity.item.name} (condition: {entity.hit_points}/{entity.max_hit_points})"
            for entity in self.player.inventory
        )

        attributes_str = "\n".join(
            f" - {attr.name}: {value}" for attr, value in self.player.attributes.items()
        )

        equipment_str = "\n".join(
            f" - {slot.name}: {f'{entity.item.name} (condition: {entity.hit_points}/{entity.max_hit_points})' if entity else 'None'}"
            for slot, entity in self.player.equipment.items()
        )

        traits_str = "\n".join(
            f" - {trait.name}: {trait.description}" for trait in self.player.traits
        )

        perks_str = "\n".join(
            f" - {perk.name}: {perk.description}" for perk in self.player.perks
        )

        conditions_str = ", ".join(
            [condition.name for condition in self.player.conditions]
        )

        narrative = self.narrative
        goals_str = ""
        if narrative.goals.get("short_term"):
            goals_str += f"Short-term: {', '.join(narrative.goals['short_term'])}. "
        if narrative.goals.get("long_term"):
            goals_str += f"Long-term: {', '.join(narrative.goals['long_term'])}."

        char_context = f"""
Name: {self.player.name}
Level: {self.player.level} (XP: {self.player.experience_points})
Health: {self.player.hit_points}/{self.player.max_hit_points}
Hunger: {self.player.hunger}%
Thirst: {self.player.thirst}%
Morale: {self.player.morale}%
Sleep: {narrative.conditions.get('sleep', 'Rested')}
Infection Risk: {narrative.conditions.get('infection_risk', 'No')}
Conditions: {conditions_str if conditions_str else 'None'}
Status: {', '.join(narrative.player_status) if narrative.player_status else 'None'}
Goals: {goals_str if goals_str else 'None'}
Inventory: {inventory_str if inventory_str else 'Empty'}
Attributes: {attributes_str if attributes_str else 'None'}
Equipment: {equipment_str if equipment_str else 'None'}
Traits: {traits_str if traits_str else 'None'}
Perks: {perks_str if perks_str else 'None'}
"""

        location_context = f"""
Current Location: {self.current_location.name}
Description: {self.current_location.description}
Day {narrative.day}, {narrative.time_of_day.capitalize()} -- {self.world.time}, {self.world.date}
Apocalypse Stage: {narrative.apocalypse_stage}
Flags: {', '.join(f'{k}={v}' for k, v in narrative.flags.items()) if narrative.flags else 'None'}
"""

        deep_memory_section = (
            "\n".join(f" - {memory}" for memory in deep_memories)
            if deep_memories
            else "(No relevant memories surfaced)"
        )

        return f"""[CHARACTER]
{char_context}

[DEEP MEMORY]
(Past events recalled as relevant to what the player just did)

{deep_memory_section}

[CURRENT LOCATION]
{location_context}

[ITEMS IN CURRENT LOCATION]

{self._get_current_items_section().rstrip()}

[NEARBY LOCATIONS]

{self._get_nearby_locations_section().rstrip()}

[NPCS PRESENT]

{self._get_npcs_present_section().rstrip()}

[SUMMARY OF PAST EVENTS]
(A narrative overview of the long-term past)

{self._get_summary_section().rstrip()}

[RECENT EVENTS]
(What just happened)

{self._get_events_section().rstrip()}

[SCENE]
{player_input}"""

    # Kept as the historical entry point; `build_prompt` is the full version.
    def process_player_input(self, player_input: str) -> str:
        return self.build_prompt(player_input)

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

    def apply_action(self, action_str: str) -> tuple[bool, str]:
        """Apply one LLM-issued action line to the game state.

        Returns (succeeded, message). A failure is never fatal -- the narrative
        still stands, the state change just did not happen -- so the caller logs
        the message and moves on.
        """
        action_str = action_str.strip().lstrip("-").strip()
        if not action_str or action_str.upper() == "NONE":
            return True, "No action."

        verb, _, remainder = action_str.partition(" ")
        handler = self._ACTION_HANDLERS.get(verb.upper())
        if handler is None:
            return False, f"Unknown action verb: {verb}"

        try:
            return handler(self, remainder.strip())
        except Exception as exc:  # a malformed action must not kill the turn
            return False, f"Action '{action_str}' failed: {exc}"

    def _action_take(self, args: str) -> tuple[bool, str]:
        entity = self._find_item_entity(self._ground_items(), args)
        if entity is None:
            return False, f"No '{args}' here to take."
        if len(self.player.inventory) >= self.player.max_inventory_size:
            return False, "Inventory is full."
        self.current_location.entities.remove(entity)
        self.player.inventory.append(entity)
        return True, f"Took {entity.item.name}."

    def _action_drop(self, args: str) -> tuple[bool, str]:
        entity = self._find_item_entity(self.player.inventory, args)
        if entity is None:
            return False, f"No '{args}' in inventory to drop."
        self.player.inventory.remove(entity)
        self.current_location.entities.append(entity)
        return True, f"Dropped {entity.item.name}."

    def _action_move_to(self, args: str) -> tuple[bool, str]:
        location = self.resolve_location(args)
        if location is None:
            return False, f"Unknown location: '{args}'."
        self.player.current_location_id = location.id
        return True, f"Moved to {location.name}."

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

    def _action_status_add(self, args: str) -> tuple[bool, str]:
        status = args.strip()
        if not status:
            return False, "STATUS_ADD needs a status name."
        # A status matching a simulated condition goes on the entity too.
        condition = self._as_condition(status)
        if condition is not None and condition not in self.player.conditions:
            self.player.conditions.append(condition)
        if status not in self.narrative.player_status:
            self.narrative.player_status.append(status)
        return True, f"Added status '{status}'."

    def _action_status_remove(self, args: str) -> tuple[bool, str]:
        status = args.strip()
        condition = self._as_condition(status)
        if condition is not None and condition in self.player.conditions:
            self.player.conditions.remove(condition)
        if status in self.narrative.player_status:
            self.narrative.player_status.remove(status)
            return True, f"Removed status '{status}'."
        return False, f"Player did not have status '{status}'."

    @staticmethod
    def _as_condition(name: str) -> CharacterCondition | None:
        try:
            return CharacterCondition(name.strip().casefold())
        except ValueError:
            return None

    def _action_update_condition(self, args: str) -> tuple[bool, str]:
        field_name, _, raw_value = args.strip().partition(" ")
        field_name = field_name.casefold()
        raw_value = raw_value.strip()
        if not raw_value:
            return False, "UPDATE_CONDITION needs a field and a value."

        if field_name in NARRATIVE_CONDITIONS:
            self.narrative.conditions[field_name] = raw_value
            return True, f"{field_name} is now {raw_value}."

        numeric_fields = {
            "health": "hit_points",
            "hunger": "hunger",
            "thirst": "thirst",
            "morale": "morale",
        }
        attribute = numeric_fields.get(field_name)
        if attribute is None:
            return False, f"Unknown condition field: '{field_name}'."

        try:
            # A leading +/- adjusts; a bare number sets.
            if raw_value[0] in "+-":
                new_value = getattr(self.player, attribute) + int(raw_value)
            else:
                new_value = int(raw_value)
        except ValueError:
            return False, f"'{raw_value}' is not a number."

        # hit_points clamps itself via BaseEntity; the rest are plain percentages.
        setattr(
            self.player,
            attribute,
            new_value if attribute == "hit_points" else max(0, min(new_value, 100)),
        )
        return True, f"{field_name} is now {getattr(self.player, attribute)}."

    def _action_add_goal(self, args: str) -> tuple[bool, str]:
        horizon, _, goal = args.strip().partition(" ")
        horizon, goal = horizon.casefold(), goal.strip()
        if horizon not in self.narrative.goals:
            return False, f"Unknown goal horizon: '{horizon}'."
        if not goal:
            return False, "ADD_GOAL needs goal text."
        if goal not in self.narrative.goals[horizon]:
            self.narrative.goals[horizon].append(goal)
        return True, f"Added {horizon} goal: {goal}."

    def _action_remove_goal(self, args: str) -> tuple[bool, str]:
        horizon, _, goal = args.strip().partition(" ")
        horizon, goal = horizon.casefold(), goal.strip()
        if horizon not in self.narrative.goals:
            return False, f"Unknown goal horizon: '{horizon}'."
        if goal not in self.narrative.goals[horizon]:
            return False, f"No such {horizon} goal: '{goal}'."
        self.narrative.goals[horizon].remove(goal)
        return True, f"Removed {horizon} goal: {goal}."

    def _action_update_relationship(self, args: str) -> tuple[bool, str]:
        # "<npc name> <affection|trust> <+/-N>" -- parsed from the right so
        # multi-word NPC names survive.
        parts = args.split()
        if len(parts) < 3:
            return False, "UPDATE_RELATIONSHIP needs a name, an axis, and an amount."
        raw_amount, axis, name = parts[-1], parts[-2].casefold(), " ".join(parts[:-2])

        npc = self.resolve_npc(name)
        if npc is None:
            return False, f"Unknown NPC: '{name}'."
        try:
            amount = int(raw_amount)
        except ValueError:
            return False, f"'{raw_amount}' is not a number."

        if axis == "affection":
            # The NPC's feeling towards the player, so the NPC is the source.
            self.relationship_manager.apply_affinity_modifier(
                AffinityModifier(
                    source_id=npc.npc_id,
                    target_id=self.player.entity_id,
                    amount=amount,
                )
            )
            score = self.relationship_manager.get_affinity(
                npc.npc_id, self.player.entity_id
            )
        elif axis == "trust":
            score = self.relationship_manager.adjust_trust(
                npc.npc_id, self.player.entity_id, amount
            )
        else:
            return False, f"Unknown relationship axis: '{axis}'."

        return True, f"{npc.name} {axis} is now {score}."

    def _action_add_relationship_note(self, args: str) -> tuple[bool, str]:
        name, _, note = args.strip().partition(" ")
        npc = self.resolve_npc(name)
        if npc is None:
            return False, f"Unknown NPC: '{name}'."
        note = note.strip()
        if not note:
            return False, "ADD_RELATIONSHIP_NOTE needs note text."
        npc.notes = f"{npc.notes}; {note}" if npc.notes else note
        return True, f"Noted about {npc.name}: {note}"

    def _action_set_flag(self, args: str) -> tuple[bool, str]:
        flag, _, raw_value = args.strip().partition(" ")
        raw_value = raw_value.strip().casefold()
        if raw_value not in ("true", "false"):
            return False, f"SET_FLAG needs true/false, got '{raw_value}'."
        self.narrative.flags[flag] = raw_value == "true"
        return True, f"Flag '{flag}' is now {raw_value}."

    def _action_update_inventory(self, args: str) -> tuple[bool, str]:
        operations = ("ADD", "REMOVE", "UPDATE_CONDITION", "UPDATE_QUANTITY")
        parts = args.split()
        index = next(
            (i for i, part in enumerate(parts) if part.upper() in operations), None
        )
        if index is None or index == 0:
            return False, f"UPDATE_INVENTORY needs an item and one of {operations}."

        name = " ".join(parts[:index])
        operation = parts[index].upper()
        value = " ".join(parts[index + 1 :]).strip()

        if operation == "ADD":
            item = find_item_by_name(name)
            if item is None:
                return False, f"Unknown item: '{name}'."
            if len(self.player.inventory) >= self.player.max_inventory_size:
                return False, "Inventory is full."
            self.player.inventory.append(ItemEntity(item=item))
            return True, f"Added {item.name} to inventory."

        entity = self._find_item_entity(self.player.inventory, name)
        if entity is None:
            return False, f"No '{name}' in inventory."

        if operation == "REMOVE":
            self.player.inventory.remove(entity)
            return True, f"Removed {entity.item.name} from inventory."

        if operation == "UPDATE_CONDITION":
            try:
                entity.hit_points = int(value)
            except ValueError:
                return False, f"'{value}' is not a number."
            return True, f"{entity.item.name} condition is now {entity.hit_points}."

        # UPDATE_QUANTITY: the entity model has no stack count, so N copies of
        # an item are N entities. Adjust the count to match the target.
        try:
            target_quantity = int(value)
        except ValueError:
            return False, f"'{value}' is not a number."
        matching = [
            e
            for e in self.player.inventory
            if e.item.id == entity.item.id
        ]
        while len(matching) > target_quantity:
            self.player.inventory.remove(matching.pop())
        room = self.player.max_inventory_size - len(self.player.inventory)
        for _ in range(min(target_quantity - len(matching), room)):
            self.player.inventory.append(ItemEntity(item=entity.item))
        return True, f"{entity.item.name} quantity is now {target_quantity}."

    def _action_npc_move(self, args: str) -> tuple[bool, str]:
        name, separator, destination = args.partition(" TO ")
        if not separator:
            return False, "NPC_MOVE needs the form '<npc> TO <location>'."
        npc = self.resolve_npc(name)
        if npc is None:
            return False, f"Unknown NPC: '{name.strip()}'."
        location = self.resolve_location(destination)
        if location is None:
            return False, f"Unknown location: '{destination.strip()}'."
        npc.current_location_id = location.id
        return True, f"{npc.name} moved to {location.name}."

    def _action_npc_status(self, args: str) -> tuple[bool, str]:
        parts = args.split()
        index = next(
            (i for i, part in enumerate(parts) if part.upper() in ("ADD", "REMOVE")),
            None,
        )
        if index is None or index == 0:
            return False, "NPC_STATUS needs '<npc> ADD|REMOVE <status>'."

        npc = self.resolve_npc(" ".join(parts[:index]))
        if npc is None:
            return False, f"Unknown NPC: '{' '.join(parts[:index])}'."
        operation = parts[index].upper()
        status = " ".join(parts[index + 1 :]).strip()
        if not status:
            return False, "NPC_STATUS needs a status name."

        if operation == "ADD":
            if status not in npc.status:
                npc.status.append(status)
            return True, f"{npc.name} is now '{status}'."

        if status not in npc.status:
            return False, f"{npc.name} did not have status '{status}'."
        npc.status.remove(status)
        return True, f"{npc.name} is no longer '{status}'."

    _ACTION_HANDLERS = {
        "TAKE": _action_take,
        "DROP": _action_drop,
        "MOVE_TO": _action_move_to,
        "TIME_ADVANCE": _action_time_advance,
        "STATUS_ADD": _action_status_add,
        "STATUS_REMOVE": _action_status_remove,
        "UPDATE_CONDITION": _action_update_condition,
        "ADD_GOAL": _action_add_goal,
        "REMOVE_GOAL": _action_remove_goal,
        "UPDATE_RELATIONSHIP": _action_update_relationship,
        "ADD_RELATIONSHIP_NOTE": _action_add_relationship_note,
        "SET_FLAG": _action_set_flag,
        "UPDATE_INVENTORY": _action_update_inventory,
        "NPC_MOVE": _action_npc_move,
        "NPC_STATUS": _action_npc_status,
    }

    # === Event pipeline ===

    def process_turn(self, player_action: dict[str, str]) -> str:
        """
        Processes a single game turn based on player input.
        This is the main game loop.
        """
        # Step 1: Parse player input and create an initial event
        # (This part will eventually be driven by your LLM's action parser)
        # For now, we can simulate it.
        # e.g., player_action = {"action": "attack", "target_id": "npc_dale"}

        # This is where you would translate the player's intent into a game event.
        # Let's assume we create a WeaponDealDamage event for this example.
        # initial_event = self._create_event_from_action(player_action)
        # self.event_queue.append(initial_event)

        # Step 2: Process all events in the queue
        self.drain_event_queue()

        # Step 3: Generate narrative output for the player
        # This is where you would assemble the prompt for the LLM based on what happened.
        narrative = self._generate_narrative_for_turn()
        return narrative

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
        Sends an event to all relevant entities and collects their responses.
        """
        collected_modifiers: list[AnyModifier] = []

        # Determine which entities are relevant to this event
        # This could be the player, the event's target, and any NPCs in the same location.
        relevant_entities = self._get_relevant_entities_for_event(event)

        for entity in relevant_entities:
            # Check the entity's traits and perks for relevant effects
            all_effects: list[PlayerTrait | PlayerPerk] = []
            if hasattr(entity, "traits"):
                all_effects.extend(getattr(entity, "traits", []))
            if hasattr(entity, "perks"):
                all_effects.extend(getattr(entity, "perks", []))

            for trait_or_perk in all_effects:
                for effect_handler in trait_or_perk.effects:
                    # Check if the effect handler (e.g., effect.WeaponDamageTaken)
                    # is designed to handle the current event type.
                    if self._event_matches_effect_handler(event, effect_handler):
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
                            f"[GameManager] Effect '{trait_or_perk.name}' on entity #'{entity.id}' generated modifier: {type(mod).__name__}"
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

        # Example for relationship changes:
        for mod in modifiers:
            if isinstance(mod, AffinityModifier):
                self.relationship_manager.apply_affinity_modifier(mod)
            elif isinstance(mod, ReputationModifier):
                self.relationship_manager.apply_reputation_modifier(mod)

        # ... and so on for every other type of modifier (XP, Attributes, etc.)

    def _get_relevant_entities_for_event(self, event: AnyEvent) -> list[BaseEntity]:
        """A helper to find all entities that should react to an event."""
        # This can be simple or complex. For now, let's just include the source and target.
        entities: list[BaseEntity] = []
        if hasattr(event, "source") and isinstance(event.source, BaseEntity):
            entities.append(event.source)
        if hasattr(event, "target") and isinstance(
            getattr(event, "target", None), BaseEntity
        ):
            target: BaseEntity = getattr(event, "target")
            if target not in entities:
                entities.append(target)
        return entities

    def _event_matches_effect_handler(
        self, event: AnyEvent, handler: AnyEffect
    ) -> bool:
        """Checks if an effect handler class is designed for the given event instance."""
        # This is a bit of Python introspection to make the system generic.
        # e.g., Does a 'WeaponDamageTaken' handler match a 'WeaponTakeDamage' event?
        # A simple string comparison of the class names is often sufficient.
        handler_name = handler.__class__.__name__  # e.g., "WeaponDamageTaken"
        event_name = event.__class__.__name__  # e.g., "WeaponTakeDamage"

        # This logic might need to be more robust, but it's a good start.
        return handler_name.startswith(event_name)

    def _generate_narrative_for_turn(self) -> str:
        """Assembles the context and generates the final story text from the LLM."""
        # This is where you would build the large prompt with world state,
        # NPC states, recent events, etc., and send it to your LLM.
        return "The turn is over. A narrative description would go here."
