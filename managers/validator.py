"""Action Validator: precondition checks only, no state mutation.

This is the piece docs/01-engine-authority.md calls the Action Validator. It
answers "is this legal" for every proposed action *before* the Simulation
Core decides "what happens" and long before the narrator writes a word about
it -- the inversion that makes the engine authoritative instead of the old
narrate-then-vet order.

Every check here is read-only. `Accepted.resolved` carries whatever entities
the check already looked up (the target NPC, the item entity, the door) so
`managers/simulation.py` never has to re-resolve them and never has to
re-derive the reason something was legal.
"""

from dataclasses import dataclass, field
from typing import Any

from managers.game import TIMES_OF_DAY, GameManager
from modules.action import (
    AddGoalAction,
    AddRelationshipNoteAction,
    AnyAction,
    AttackAction,
    DiscoverFlagAction,
    DropAction,
    MoveAction,
    NARRATIVE_CONDITION_FIELDS,
    NpcMoveAction,
    NpcStatusAction,
    RemoveGoalAction,
    SetFlagAction,
    StatusAddAction,
    StatusRemoveAction,
    TakeAction,
    TimeAdvanceAction,
    UpdateConditionAction,
    UpdateInventoryAction,
    UpdateRelationshipAction,
    UseItemAction,
)
from modules.entity.object import DoorEntity, UnlockableEntityLockState
from modules.item import AppliableItem, ConsumableItem
from data.items import find_item_by_name

GOAL_HORIZONS = ("short_term", "long_term")

# Statuses that block the player from taking a physical action. Free text, not
# an enum, because narrative status ("settled in") and simulated capability
# ("unconscious") share one field (`NarrativeState.player_status`) today.
INCAPACITATING_STATUSES = frozenset({"unconscious", "incapacitated", "restrained"})


@dataclass
class Accepted:
    action: AnyAction
    resolved: dict[str, Any] = field(default_factory=dict)


@dataclass
class Rejected:
    action: AnyAction
    reason: str


ValidationResult = Accepted | Rejected


class ActionValidator:
    def __init__(self, manager: GameManager):
        self.manager = manager

    def validate_all(self, actions: list[AnyAction]) -> list[ValidationResult]:
        return [self.validate(action) for action in actions]

    def validate(self, action: AnyAction) -> ValidationResult:
        handler = self._VALIDATORS.get(type(action))
        if handler is None:
            return Rejected(action, f"No validator registered for {type(action).__name__}.")
        return handler(self, action)

    # === Movement ===

    def _validate_move(self, action: MoveAction) -> ValidationResult:
        manager = self.manager
        location = manager.current_location
        needle = action.destination.strip().casefold()
        if not needle:
            return Rejected(action, "MOVE_TO needs a destination.")

        target_id = None
        for direction, loc_id in location.connections.items():
            connected = manager.world.locations.get(loc_id)
            if connected is None:
                continue
            if needle in (direction.casefold(), loc_id.casefold(), connected.name.casefold()):
                target_id = loc_id
                break

        if target_id is None:
            # Deliberately does not fall through to a global name match: a
            # location existing somewhere in the world does not make it
            # reachable from here. That fallthrough was the reachability bug.
            return Rejected(
                action, f"'{action.destination}' is not reachable from {location.name}."
            )

        door = self._door_blocking(location, target_id)
        target = manager.world.locations[target_id]
        if door is not None and door.state == UnlockableEntityLockState.LOCKED:
            if not self._has_key(door.key_id):
                return Rejected(action, f"The way to {target.name} is locked.")

        return Accepted(action, {"location": target, "door": door})

    @staticmethod
    def _door_blocking(location, target_id: str) -> DoorEntity | None:
        for entity in location.entities:
            if isinstance(entity, DoorEntity) and entity.leads_to == target_id:
                return entity
        return None

    def _has_key(self, key_id: str | None) -> bool:
        if key_id is None:
            return True
        return any(
            entity.item.id == key_id for entity in self.manager.player.inventory
        )

    # === Items ===

    def _validate_take(self, action: TakeAction) -> ValidationResult:
        manager = self.manager
        entity = manager._find_item_entity(manager._ground_items(), action.item_name)
        if entity is None:
            return Rejected(action, f"No '{action.item_name}' here to take.")
        if len(manager.player.inventory) >= manager.player.max_inventory_size:
            return Rejected(action, "Inventory is full.")
        return Accepted(action, {"item_entity": entity})

    def _validate_drop(self, action: DropAction) -> ValidationResult:
        entity = self.manager._find_item_entity(
            self.manager.player.inventory, action.item_name
        )
        if entity is None:
            return Rejected(action, f"No '{action.item_name}' in inventory to drop.")
        return Accepted(action, {"item_entity": entity})

    def _validate_use_item(self, action: UseItemAction) -> ValidationResult:
        entity = self.manager._find_item_entity(
            self.manager.player.inventory, action.item_name
        )
        if entity is None:
            return Rejected(action, f"No '{action.item_name}' in inventory to use.")
        if not isinstance(entity.item, (ConsumableItem, AppliableItem)):
            return Rejected(action, f"{entity.item.name} cannot be used this way.")
        return Accepted(action, {"item_entity": entity})

    def _validate_update_inventory(self, action: UpdateInventoryAction) -> ValidationResult:
        manager = self.manager
        if action.operation == "ADD":
            item = find_item_by_name(action.item_name)
            if item is None:
                return Rejected(action, f"Unknown item: '{action.item_name}'.")
            if len(manager.player.inventory) >= manager.player.max_inventory_size:
                return Rejected(action, "Inventory is full.")
            return Accepted(action, {"item": item})

        entity = manager._find_item_entity(manager.player.inventory, action.item_name)
        if entity is None:
            return Rejected(action, f"No '{action.item_name}' in inventory.")
        if action.operation not in ("REMOVE", "UPDATE_CONDITION", "UPDATE_QUANTITY"):
            return Rejected(action, f"Unknown inventory operation: '{action.operation}'.")
        if action.operation in ("UPDATE_CONDITION", "UPDATE_QUANTITY"):
            try:
                int(action.value)
            except ValueError:
                return Rejected(action, f"'{action.value}' is not a number.")
        return Accepted(action, {"item_entity": entity})

    # === Combat ===

    def _validate_attack(self, action: AttackAction) -> ValidationResult:
        manager = self.manager
        if self._player_incapacitated():
            return Rejected(action, "Orton is in no state to attack anything.")
        npc = manager.resolve_npc(action.target_name)
        if npc is None or npc.current_location_id != manager.player.current_location_id:
            return Rejected(action, f"'{action.target_name}' is not here to attack.")
        if npc.hit_points <= 0:
            return Rejected(action, f"{npc.name} is already down.")
        return Accepted(action, {"npc": npc})

    def _player_incapacitated(self) -> bool:
        statuses = {s.casefold() for s in self.manager.narrative.player_status}
        return bool(INCAPACITATING_STATUSES & statuses)

    # === Status / conditions ===

    def _validate_status_add(self, action: StatusAddAction) -> ValidationResult:
        return Accepted(action, {})

    def _validate_status_remove(self, action: StatusRemoveAction) -> ValidationResult:
        if action.status not in self.manager.narrative.player_status:
            return Rejected(action, f"Player did not have status '{action.status}'.")
        return Accepted(action, {})

    def _validate_update_condition(self, action: UpdateConditionAction) -> ValidationResult:
        if action.field_name in NARRATIVE_CONDITION_FIELDS:
            return Accepted(action, {})
        try:
            int(action.raw_value)
        except ValueError:
            return Rejected(action, f"'{action.raw_value}' is not a number.")
        return Accepted(action, {})

    # === Time ===

    def _validate_time_advance(self, action: TimeAdvanceAction) -> ValidationResult:
        if action.time_of_day.strip().casefold() not in TIMES_OF_DAY:
            return Rejected(action, f"Unknown time of day: '{action.time_of_day}'.")
        return Accepted(action, {})

    # === Goals ===

    def _validate_add_goal(self, action: AddGoalAction) -> ValidationResult:
        if action.horizon not in GOAL_HORIZONS:
            return Rejected(action, f"Unknown goal horizon: '{action.horizon}'.")
        return Accepted(action, {})

    def _validate_remove_goal(self, action: RemoveGoalAction) -> ValidationResult:
        if action.horizon not in GOAL_HORIZONS:
            return Rejected(action, f"Unknown goal horizon: '{action.horizon}'.")
        if action.goal_text not in self.manager.narrative.goals.get(action.horizon, []):
            return Rejected(action, f"No such {action.horizon} goal: '{action.goal_text}'.")
        return Accepted(action, {})

    # === Relationships ===

    def _validate_update_relationship(self, action: UpdateRelationshipAction) -> ValidationResult:
        npc = self.manager.resolve_npc(action.npc_name)
        if npc is None:
            return Rejected(action, f"Unknown NPC: '{action.npc_name}'.")
        return Accepted(action, {"npc": npc})

    def _validate_add_relationship_note(
        self, action: AddRelationshipNoteAction
    ) -> ValidationResult:
        npc = self.manager.resolve_npc(action.npc_name)
        if npc is None:
            return Rejected(action, f"Unknown NPC: '{action.npc_name}'.")
        return Accepted(action, {"npc": npc})

    # === World flags ===

    def _validate_set_flag(self, action: SetFlagAction) -> ValidationResult:
        return Accepted(action, {})

    def _validate_discover_flag(self, action: DiscoverFlagAction) -> ValidationResult:
        return Accepted(action, {})

    # === NPCs ===

    def _validate_npc_move(self, action: NpcMoveAction) -> ValidationResult:
        manager = self.manager
        npc = manager.resolve_npc(action.npc_name)
        if npc is None:
            return Rejected(action, f"Unknown NPC: '{action.npc_name}'.")
        location = manager.resolve_location(action.destination)
        if location is None:
            return Rejected(action, f"Unknown location: '{action.destination}'.")
        return Accepted(action, {"npc": npc, "location": location})

    def _validate_npc_status(self, action: NpcStatusAction) -> ValidationResult:
        npc = self.manager.resolve_npc(action.npc_name)
        if npc is None:
            return Rejected(action, f"Unknown NPC: '{action.npc_name}'.")
        if action.operation not in ("ADD", "REMOVE"):
            return Rejected(action, f"Unknown NPC_STATUS operation: '{action.operation}'.")
        if action.operation == "REMOVE" and action.status not in npc.status:
            return Rejected(action, f"{npc.name} did not have status '{action.status}'.")
        return Accepted(action, {"npc": npc})

    _VALIDATORS = {
        MoveAction: _validate_move,
        TakeAction: _validate_take,
        DropAction: _validate_drop,
        AttackAction: _validate_attack,
        UseItemAction: _validate_use_item,
        TimeAdvanceAction: _validate_time_advance,
        StatusAddAction: _validate_status_add,
        StatusRemoveAction: _validate_status_remove,
        UpdateConditionAction: _validate_update_condition,
        AddGoalAction: _validate_add_goal,
        RemoveGoalAction: _validate_remove_goal,
        UpdateRelationshipAction: _validate_update_relationship,
        AddRelationshipNoteAction: _validate_add_relationship_note,
        SetFlagAction: _validate_set_flag,
        DiscoverFlagAction: _validate_discover_flag,
        UpdateInventoryAction: _validate_update_inventory,
        NpcMoveAction: _validate_npc_move,
        NpcStatusAction: _validate_npc_status,
    }
