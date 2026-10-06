"""Action Validator: precondition checks only, no state mutation.

This is the piece docs/01-engine-authority.md calls the Action Validator. It
answers "is this legal" for every proposed action *before* the Simulation
Core decides "what happens" and long before the narrator writes a word about
it -- the inversion that makes the engine authoritative instead of the old
narrate-then-vet order.

Every check here is read-only. `Accepted.resolved` carries whatever the check
already looked up (the target NPC, the item entity, the destination zone) as a
`modules.resolution` type, so
`managers/simulation.py` never has to re-resolve them and never has to
re-derive the reason something was legal.
"""

from dataclasses import dataclass

from data import survival
from data.body_locations import EXCLUSIVE_LOCATIONS
from data.clock import (
    SLEEP_CAP_MIN,
    TIME_OF_DAY_START,
    WAIT_CAP_MIN,
    minutes_until,
)
from data.items import find_item_by_name
from managers.game import MAX_PLACE_LENGTH, GameManager
from managers.locations import BARE_DIRECTIONS, connection_target
from managers.stats.status_effects import status_effect_level
from modules.action.types import (
    AddGoalAction,
    AddRelationshipNoteAction,
    AnyAction,
    AttackAction,
    DiscoverFlagAction,
    DropAction,
    Duration,
    MoveAction,
    NpcMoveAction,
    NpcStatusAction,
    RemoveGoalAction,
    SetFlagAction,
    SleepAction,
    StatusAddAction,
    StatusRemoveAction,
    TakeAction,
    TakeOffAction,
    UpdateConditionAction,
    UpdateInventoryAction,
    UpdateRelationshipAction,
    UseItemAction,
    WaitAction,
    WearAction,
)
from modules.entity.object import DoorEntity, UnlockableEntityLockState
from modules.item import AppliableItem, ClothingItem, ConsumableItem
from modules.resolution import (
    HeldItem,
    MoveBlocked,
    MoveToSpot,
    MoveToZone,
    NewItem,
    NpcDestination,
    Resolution,
    ShuffleInZone,
    StayPut,
    TargetNpc,
    TimeSpan,
)
from modules.stats import CharacterStat, StatusEffect

GOAL_HORIZONS = ("short_term", "long_term")

# Statuses that block the player from taking a physical action. Free text, not
# an enum, because narrative status ("settled in") and simulated capability
# ("unconscious") share one field (`NarrativeState.player_status`) today.
INCAPACITATING_STATUSES = frozenset({"unconscious", "incapacitated", "restrained"})


def _with_article(name: str) -> str:
    """The name with "a" or "an"; plural names such as Jeans take none."""
    if name.endswith("s") and not name.endswith("ss"):
        return name
    return f"{'an' if name[0].lower() in 'aeiou' else 'a'} {name}"


@dataclass
class Accepted:
    action: AnyAction
    resolved: Resolution = None

    def expect[R](self, kind: type[R]) -> R:
        """`resolved` as a `kind`; anything else is a validator bug."""
        if not isinstance(self.resolved, kind):
            raise TypeError(
                f"{type(self.action).__name__} resolved to {self.resolved!r}, "
                f"expected {kind.__name__}"
            )
        return self.resolved


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
        if self.manager.narrative.game_over:
            # The one sanctioned exception to "MOVE_TO never fails" (and
            # every other action): once Orton is dead nothing more can
            # happen, so every action this turn and beyond is refused rather
            # than dispatched. SimulationCore._check_player_death is the only
            # place that sets this flag; the LLM cannot trigger it.
            return Rejected(action, "Orton is dead; nothing more can happen.")
        handler = self._VALIDATORS.get(type(action))
        if handler is None:
            return Rejected(action, f"No validator registered for {type(action).__name__}.")
        return handler(self, action)

    # === Movement ===

    def _validate_move(self, action: MoveAction) -> ValidationResult:
        """Decide what a MOVE_TO *means*. This never rejects.

        A named zone is reachable from anywhere by walking the connection
        graph (`GameManager.zone_path`); adjacency is not required. A locked
        door along that walk stops the player short of the target zone, but
        the move still resolves to a place (the door), not a refusal -- the
        walk is gated hop by hop so a lock can't be skipped, yet it never
        dead-ends in "you can't do that."

        Anything that isn't a recognized zone, connection, or bare direction
        becomes a free-text spot inside the zone the player is already in.
        The result is one of the five `MoveOutcome` types.
        """
        manager = self.manager
        current = manager.current_location
        raw = action.destination.strip().strip("\"'.,;:")
        if not raw:
            return Accepted(action, StayPut(current))

        folded = raw.casefold()

        # Order: (1) a direction synonym that names a real connection of
        # the current zone wins outright; (2) otherwise a bare direction with
        # no destination behind it is a shuffle, checked before the alias/
        # whole-word resolution below can accidentally claim it (e.g. a zone
        # whose alias list happens to contain a direction word); (3)
        # otherwise fall through to full resolution.
        target = connection_target(folded, current, manager.world.locations)
        if target is None:
            if folded in BARE_DIRECTIONS:
                return Accepted(action, ShuffleInZone(current, raw))
            target = manager.resolve_location(raw)

        if target is None:
            return Accepted(action, MoveToSpot(current, raw[:MAX_PLACE_LENGTH]))

        # "the pharmacy" and "the kitchen" resolve to a zone via an alias, but
        # the words themselves are the interesting part -- they are where in
        # the zone the player actually is. Keep them as the spot unless the
        # model named the zone itself, or just gave a direction.
        place = (
            ""
            if folded in (target.id.casefold(), target.name.casefold()) or folded in BARE_DIRECTIONS
            else raw[:MAX_PLACE_LENGTH]
        )

        if target.id == current.id:
            return Accepted(action, MoveToSpot(current, place))

        path = manager.zone_path(current.id, target.id)
        if path is None:
            # Disconnected map -- not possible with the shipped content, but
            # zone_path can express it, so this must not raise or refuse.
            return Accepted(action, MoveToSpot(current, place))

        hop_from = current
        for hop_id in path:
            door = self._door_blocking(hop_from, hop_id)
            if (
                door is not None
                and door.state == UnlockableEntityLockState.LOCKED
                and not self._has_key(door.key_id)
            ):
                hop_to = manager.world.locations[hop_id]
                return Accepted(
                    action,
                    MoveBlocked(
                        location=hop_from,
                        place=f"at the locked door to {hop_to.name}"[:MAX_PLACE_LENGTH],
                        hops=path.index(hop_id),
                        target=target,
                    ),
                )
            hop_from = manager.world.locations[hop_id]

        return Accepted(action, MoveToZone(target, place, hops=len(path)))

    @staticmethod
    def _door_blocking(location, target_id: str) -> DoorEntity | None:
        for entity in location.entities:
            if isinstance(entity, DoorEntity) and entity.leads_to == target_id:
                return entity
        return None

    def _has_key(self, key_id: str | None) -> bool:
        if key_id is None:
            return True
        return any(entity.item.id == key_id for entity in self.manager.player.inventory)

    # === Items ===

    def _validate_take(self, action: TakeAction) -> ValidationResult:
        manager = self.manager
        entity = manager._find_item_entity(manager._ground_items(), action.item_name)
        if entity is None:
            return Rejected(action, f"No '{action.item_name}' here to take.")
        if len(manager.player.inventory) >= manager.player.max_inventory_size:
            return Rejected(action, "Inventory is full.")
        return Accepted(action, HeldItem(entity))

    def _validate_drop(self, action: DropAction) -> ValidationResult:
        entity = self.manager._find_item_entity(self.manager.player.inventory, action.item_name)
        if entity is None:
            return Rejected(action, f"No '{action.item_name}' in inventory to drop.")
        if self._is_door_key(entity.item.id):
            return Rejected(action, "Orton keeps his keys on him.")
        return Accepted(action, HeldItem(entity))

    def _validate_wear(self, action: WearAction) -> ValidationResult:
        player = self.manager.player
        entity = self.manager._find_item_entity(player.inventory, action.item_name)
        if entity is None:
            return Rejected(action, f"No '{action.item_name}' in inventory to wear.")
        item = entity.item
        if not isinstance(item, ClothingItem):
            return Rejected(action, f"{item.name} cannot be worn.")
        occupant = player.worn.get(item.body_location)
        if occupant is not None:
            return Rejected(
                action, f"Orton is already wearing {_with_article(occupant.item.name)} there."
            )
        blocked = EXCLUSIVE_LOCATIONS.get(item.body_location, frozenset())
        for location, worn in player.worn.items():
            if location in blocked:
                return Rejected(
                    action, f"Orton cannot wear {item.name} while wearing {worn.item.name}."
                )
        return Accepted(action, HeldItem(entity))

    def _validate_take_off(self, action: TakeOffAction) -> ValidationResult:
        player = self.manager.player
        entity = self.manager._find_item_entity(list(player.worn.values()), action.item_name)
        if entity is None:
            return Rejected(action, f"Orton is not wearing '{action.item_name}'.")
        if len(player.inventory) >= player.max_inventory_size:
            return Rejected(action, "Inventory is full.")
        return Accepted(action, HeldItem(entity))

    def _is_door_key(self, item_id: str) -> bool:
        """Whether `item_id` is the `key_id` of any `DoorEntity` anywhere in
        the world -- engine-owned, not hard-coded to `item_apartment_key`.
        Dropping (or duplicating) the key could strand Orton outside his own
        apartment, since the door rebuilds LOCKED on every load (see
        data/locations.py)."""
        for location in self.manager.world.locations.values():
            for entity in location.entities:
                if isinstance(entity, DoorEntity) and entity.key_id == item_id:
                    return True
        return False

    def _validate_use_item(self, action: UseItemAction) -> ValidationResult:
        entity = self.manager._find_item_entity(self.manager.player.inventory, action.item_name)
        if entity is None:
            return Rejected(action, f"No '{action.item_name}' in inventory to use.")
        if not isinstance(entity.item, (ConsumableItem, AppliableItem)):
            return Rejected(action, f"{entity.item.name} cannot be used this way.")
        return Accepted(action, HeldItem(entity))

    def _validate_update_inventory(self, action: UpdateInventoryAction) -> ValidationResult:
        manager = self.manager
        if action.operation == "ADD":
            item = find_item_by_name(action.item_name)
            if item is None:
                return Rejected(action, f"Unknown item: '{action.item_name}'.")
            if self._is_door_key(item.id):
                return Rejected(action, "Orton can't conjure a key; it has to be found.")
            if len(manager.player.inventory) >= manager.player.max_inventory_size:
                return Rejected(action, "Inventory is full.")
            return Accepted(action, NewItem(item))

        entity = manager._find_item_entity(manager.player.inventory, action.item_name)
        if entity is None:
            return Rejected(action, f"No '{action.item_name}' in inventory.")
        if action.operation not in ("REMOVE", "UPDATE_CONDITION", "UPDATE_QUANTITY"):
            return Rejected(action, f"Unknown inventory operation: '{action.operation}'.")

        # REMOVE and UPDATE_QUANTITY are the other two ways an item can
        # leave (or multiply in) the inventory besides DROP/ADD -- REMOVE
        # deletes the entity outright (simulation.py), and UPDATE_QUANTITY 0
        # deletes it the same way while UPDATE_QUANTITY >1 duplicates it. A
        # door key must be as protected from these as it already is from
        # DROP/ADD. UPDATE_CONDITION never removes an item, so it stays
        # unprotected.
        if action.operation == "REMOVE" and self._is_door_key(entity.item.id):
            return Rejected(action, "Orton keeps his keys on him.")
        if action.operation in ("UPDATE_CONDITION", "UPDATE_QUANTITY"):
            try:
                value = int(action.value)
            except ValueError:
                return Rejected(action, f"'{action.value}' is not a number.")
            if action.operation == "UPDATE_QUANTITY" and self._is_door_key(entity.item.id):
                if value < 1:
                    return Rejected(action, "Orton keeps his keys on him.")
                if value > 1:
                    return Rejected(action, "Orton can't conjure a key; it has to be found.")
        return Accepted(action, HeldItem(entity))

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
        return Accepted(action, TargetNpc(npc))

    def _player_incapacitated(self) -> bool:
        statuses = {s.casefold() for s in self.manager.narrative.player_status}
        return bool(INCAPACITATING_STATUSES & statuses)

    # === Status / conditions ===

    def _validate_status_add(self, action: StatusAddAction) -> ValidationResult:
        return Accepted(action)

    def _validate_status_remove(self, action: StatusRemoveAction) -> ValidationResult:
        if action.status not in self.manager.narrative.player_status:
            return Rejected(action, f"Player did not have status '{action.status}'.")
        return Accepted(action)

    def _validate_update_condition(self, action: UpdateConditionAction) -> ValidationResult:
        return Rejected(
            action,
            f"'{action.field_name}' is not something the narrator can set; "
            "the engine moves survival stats with the clock.",
        )

    # === Time ===

    def _span(self, duration: Duration) -> int | None:
        """Minutes a duration covers from now, or None for an unknown time of day."""
        if duration.minutes is not None:
            return duration.minutes
        now = self.manager.narrative.minutes
        if duration.until_minute_of_day is not None:
            return minutes_until(now, duration.until_minute_of_day)
        start = TIME_OF_DAY_START.get(duration.until_time_of_day or "")
        return None if start is None else minutes_until(now, start)

    def _timed(self, action: WaitAction | SleepAction, duration: Duration, cap: int):
        span = self._span(duration)
        if span is None:
            return Rejected(action, f"Unknown time of day: '{duration.until_time_of_day}'.")
        return Accepted(action, TimeSpan(min(span, cap), clamped=span > cap))

    def _validate_wait(self, action: WaitAction) -> ValidationResult:
        return self._timed(action, action.duration, WAIT_CAP_MIN)

    def _validate_sleep(self, action: SleepAction) -> ValidationResult:
        refusal = self._sleep_refusal()
        if refusal:
            return Rejected(action, refusal)
        if action.duration is not None:
            return self._timed(action, action.duration, SLEEP_CAP_MIN)
        minutes = SLEEP_CAP_MIN
        now = self.manager.narrative.minutes
        if self.manager.narrative.time_of_day == "night":
            minutes = min(minutes, minutes_until(now, survival.SLEEP_DEFAULT_WAKE_MINUTE_OF_DAY))
        return Accepted(action, TimeSpan(minutes, clamped=False))

    def _sleep_refusal(self) -> str:
        stats = self.manager.player.stats
        panic = status_effect_level(StatusEffect.PANIC, stats.get(CharacterStat.PANIC))
        if panic >= survival.SLEEP_REFUSED_PANIC_LEVEL:
            return "Orton is too panicked to sleep."
        pain = status_effect_level(StatusEffect.PAIN, stats.get(CharacterStat.PAIN))
        if (
            pain >= survival.SLEEP_REFUSED_PAIN_LEVEL
            and stats.get(CharacterStat.FATIGUE) <= survival.SLEEP_PAIN_FATIGUE_EXCEPTION
        ):
            return "Orton is in too much pain to sleep."
        return ""

    # === Goals ===

    def _validate_add_goal(self, action: AddGoalAction) -> ValidationResult:
        if action.horizon not in GOAL_HORIZONS:
            return Rejected(action, f"Unknown goal horizon: '{action.horizon}'.")
        return Accepted(action)

    def _validate_remove_goal(self, action: RemoveGoalAction) -> ValidationResult:
        if action.horizon not in GOAL_HORIZONS:
            return Rejected(action, f"Unknown goal horizon: '{action.horizon}'.")
        if action.goal_text not in self.manager.narrative.goals.get(action.horizon, []):
            return Rejected(action, f"No such {action.horizon} goal: '{action.goal_text}'.")
        return Accepted(action)

    # === Relationships ===

    def _validate_update_relationship(self, action: UpdateRelationshipAction) -> ValidationResult:
        npc = self.manager.resolve_npc(action.npc_name)
        if npc is None:
            return Rejected(action, f"Unknown NPC: '{action.npc_name}'.")
        return Accepted(action, TargetNpc(npc))

    def _validate_add_relationship_note(
        self, action: AddRelationshipNoteAction
    ) -> ValidationResult:
        npc = self.manager.resolve_npc(action.npc_name)
        if npc is None:
            return Rejected(action, f"Unknown NPC: '{action.npc_name}'.")
        return Accepted(action, TargetNpc(npc))

    # === World flags ===

    def _validate_set_flag(self, action: SetFlagAction) -> ValidationResult:
        return Accepted(action)

    def _validate_discover_flag(self, action: DiscoverFlagAction) -> ValidationResult:
        return Accepted(action)

    # === NPCs ===

    def _validate_npc_move(self, action: NpcMoveAction) -> ValidationResult:
        manager = self.manager
        npc = manager.resolve_npc(action.npc_name)
        if npc is None:
            return Rejected(action, f"Unknown NPC: '{action.npc_name}'.")
        # Strict resolution only -- no connection directions, no
        # whole-word fallback. NPCs have no free-text spot for a vague phrase
        # to soft-land in, unlike the player's MOVE_TO.
        location = manager.resolve_zone_exact(action.destination)
        if location is None:
            return Rejected(action, f"Unknown location: '{action.destination}'.")
        # Orton's apartment door is locked from the building side (see
        # data/locations.py); nobody else has a key. An NPC can only be
        # placed there while Orton himself is home to let them in.
        if location.id == "zone_home" and manager.player.current_location_id != "zone_home":
            return Rejected(
                action,
                "Orton's apartment is locked; nobody gets in unless he's there to let them in.",
            )
        return Accepted(action, NpcDestination(npc, location))

    def _validate_npc_status(self, action: NpcStatusAction) -> ValidationResult:
        npc = self.manager.resolve_npc(action.npc_name)
        if npc is None:
            return Rejected(action, f"Unknown NPC: '{action.npc_name}'.")
        if action.operation not in ("ADD", "REMOVE"):
            return Rejected(action, f"Unknown NPC_STATUS operation: '{action.operation}'.")
        if action.operation == "REMOVE" and action.status not in npc.status:
            return Rejected(action, f"{npc.name} did not have status '{action.status}'.")
        return Accepted(action, TargetNpc(npc))

    _VALIDATORS = {
        MoveAction: _validate_move,
        TakeAction: _validate_take,
        DropAction: _validate_drop,
        WearAction: _validate_wear,
        TakeOffAction: _validate_take_off,
        AttackAction: _validate_attack,
        UseItemAction: _validate_use_item,
        WaitAction: _validate_wait,
        SleepAction: _validate_sleep,
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
