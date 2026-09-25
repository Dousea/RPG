"""Simulation Core: deterministic outcome resolution for accepted actions.

Validates each action (via `managers/validator.py`) and decides what actually
happens -- HP, inventory, position, the clock -- before any prose exists.
Movement, inventory, and world-state actions are direct field mutations;
combat and item use additionally build real events and run them through the
event/effect/modifier pipeline in `managers/game.py` (already built,
previously never invoked -- see `GameManager._broadcast_event`), so trait/perk
reactions in `data/traits.py`/`data/perks.py` actually fire.

`resolve()` returns one outcome-fact string per action -- what the narrator
prompt describes. The narrator is never the source of truth for anything in
this list; it only puts prose around facts the engine already decided.
"""

import random

from managers.game import DEATH_CAUSE_MAX_LENGTH, GameManager
from managers.validator import Accepted, ActionValidator, Rejected
from modules.action import (
    NARRATIVE_CONDITION_FIELDS,
    AddGoalAction,
    AddRelationshipNoteAction,
    AnyAction,
    AttackAction,
    DiscoverFlagAction,
    DropAction,
    MoveAction,
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
from modules.character.equipment import CharacterHoldableSlot
from modules.entity.item import ItemEntity
from modules.event import ApplyItemEvent, ConsumeItemEvent, WeaponDealDamageEvent, WeaponTakeDamageEvent
from modules.item import ConsumableItem, MeleeWeaponItem, RangedWeaponItem
from modules.modifier import (
    AffinityModifier,
    ConditionsModifier,
    DamageMultiplicativeModifier,
    HPModifier,
    ReputationModifier,
)
from modules.quest import QuestStatus
from modules.weapon import MeleeWeaponType

# Fists deal a token amount of damage so an unarmed ATTACK still resolves
# through the same event/modifier pipeline as an armed one, instead of being a
# special case.
UNARMED_WEAPON = MeleeWeaponItem(
    id="unarmed",
    name="bare hands",
    description="No weapon -- just hands.",
    max_hit_points=1,
    tags=["unarmed"],
    type=MeleeWeaponType.BLUNT,
    damage=2,
    slots=[CharacterHoldableSlot.RIGHT_HAND],
    is_two_handed=False,
)

# +/-10% variance on damage rolls. Building seeded/versioned RNG (doc 16) is
# explicitly out of scope; this is just enough randomness that combat doesn't
# read as a fixed calculator.
DAMAGE_JITTER = 0.10

# Action types whose resolution costs the next tick of the coarse clock
# (morning/afternoon/evening/night). Ordinary actions no longer depend on the
# LLM remembering to emit TIME_ADVANCE -- the engine owns the clock outright.
# A dedicated sub-tick clock is doc 08 territory and out of scope here.
# MoveAction is not here: a zone change costs exactly one tick regardless of
# how many hops the walk covered, and a spot/shuffle/stay move costs none at
# all, so `_resolve_move` ticks for itself instead of a blanket per-action rule.
_TICK_COSTING_ACTIONS = (AttackAction,)


class SimulationCore:
    def __init__(
        self,
        manager: GameManager,
        validator: ActionValidator | None = None,
        rng: random.Random | None = None,
    ):
        self.manager = manager
        self.validator = validator if validator is not None else ActionValidator(manager)
        self._rng = rng if rng is not None else random.Random()

    def resolve(self, actions: list[AnyAction]) -> list[str]:
        """Validate and resolve each action in order, one at a time.

        Order matters within a turn: an earlier action can change whether a
        later one is legal (move into a room, then take something only
        reachable from there). Every action is therefore validated against
        state as it stands *after* every prior action in this same turn has
        already resolved -- never against one upfront snapshot of the whole
        list, which would reject "move north, take crowbar" because the
        crowbar wasn't reachable before the move happened.
        """
        facts: list[str] = []
        for action in actions:
            result = self.validator.validate(action)
            if isinstance(result, Rejected):
                facts.append(f"Refused: {type(result.action).__name__} -- {result.reason}")
            else:
                facts.append(self._resolve_one(result))
        return facts

    def _resolve_one(self, accepted: Accepted) -> str:
        handler = self._RESOLVERS.get(type(accepted.action))
        if handler is None:
            return f"No resolver registered for {type(accepted.action).__name__}."
        fact = handler(self, accepted)
        if type(accepted.action) in _TICK_COSTING_ACTIONS:
            self._advance_one_tick()
        return self._check_player_death(fact)

    def _check_player_death(self, fact: str) -> str:
        """End the game the moment Orton's HP reaches zero.

        Player HP only ever moves through combat and item effects (main's
        rule, unchanged here), so this is the only producer of `game_over` --
        the LLM narrating a death never makes it real, only this check does.
        Sticky within the session: once set, later turns leave it alone
        rather than re-triggering off a fact that already carries "died".
        """
        narrative = self.manager.narrative
        if narrative.game_over or self.manager.player.hit_points > 0:
            return fact
        narrative.game_over = True
        narrative.death_cause = fact[:DEATH_CAUSE_MAX_LENGTH]
        return f"{fact} Orton has died. The game is over."

    def _advance_one_tick(self) -> None:
        from managers.game import TIMES_OF_DAY

        current = TIMES_OF_DAY.index(self.manager.narrative.time_of_day)
        self.manager._action_time_advance(TIMES_OF_DAY[(current + 1) % len(TIMES_OF_DAY)])

    # === Movement ===

    def _resolve_move(self, accepted: Accepted) -> str:
        """Apply whatever `_validate_move` decided MOVE_TO means.

        MOVE_TO never fails (doc 01's inversion applied to movement): the
        validator has already turned every possible destination into one of
        five kinds, and this only applies it. `current_place` is set from
        `resolved["place"]` whenever the validator produced one -- "" clears
        it (the model named the zone itself), text sets it -- and is left
        untouched for "shuffle"/"stay", which carry no `place` at all.
        """
        resolved = accepted.resolved
        kind = resolved["kind"]
        manager = self.manager

        if "place" in resolved:
            manager.player.current_place = resolved["place"]
        place = resolved.get("place", "")

        if kind == "zone":
            location = resolved["location"]
            manager.player.current_location_id = location.id
            where = f" ({place})" if place else ""
            fact = self._with_quest_note(
                f"Move to {location.name}{where}: succeeded.", f"reach:{location.id}"
            )
            self._advance_one_tick()  # one tick per zone change, however many hops
            return fact

        if kind == "blocked":
            stop = resolved["location"]
            target = resolved["target"]
            fact = (
                f"Move to {target.name}: blocked -- the door to {target.name} is "
                f"locked and Orton has no key. Orton is in {stop.name}, {place}."
            )
            if stop.id != manager.player.current_location_id:
                manager.player.current_location_id = stop.id
                fact = self._with_quest_note(fact, f"reach:{stop.id}")
                self._advance_one_tick()
            return fact

        if kind == "spot":
            zone = resolved["location"]
            if place:
                return f"Move within {zone.name} to {place}: succeeded."
            return f"Already in {zone.name}."

        if kind == "shuffle":
            zone = resolved["location"]
            return f"Moved {resolved['raw']} within {zone.name}."

        # kind == "stay"
        return "MOVE_TO had no destination; Orton stayed put."

    # === Items ===

    def _resolve_take(self, accepted: Accepted) -> str:
        entity = accepted.resolved["item_entity"]
        manager = self.manager
        manager.current_location.entities.remove(entity)
        manager.player.inventory.append(entity)
        return self._with_quest_note(
            f"Take {entity.item.name}: succeeded.", f"take:{entity.item.id}"
        )

    def _resolve_drop(self, accepted: Accepted) -> str:
        entity = accepted.resolved["item_entity"]
        manager = self.manager
        manager.player.inventory.remove(entity)
        manager.current_location.entities.append(entity)
        return f"Drop {entity.item.name}: succeeded."

    def _resolve_use_item(self, accepted: Accepted) -> str:
        manager = self.manager
        entity = accepted.resolved["item_entity"]
        item = entity.item
        player = manager.player

        # The item's own effect (e.g. a medkit's HPModifier) is not a trait/
        # perk reaction -- it applies unconditionally whenever the item is
        # used, so it is applied directly rather than through the broadcast.
        for modifier in item.modifiers:
            self._apply_modifier(player, modifier)

        survival_note = ""
        if isinstance(item, ConsumableItem):
            event = ConsumeItemEvent(source=player, item=item)
            manager.player.inventory.remove(entity)
            if item.nutrition or item.hydration:
                player.hunger = max(0, min(player.hunger + item.nutrition, 100))
                player.thirst = max(0, min(player.thirst + item.hydration, 100))
                survival_note = f", hunger {player.hunger}, thirst {player.thirst}"
        else:
            event = ApplyItemEvent(source=player, item=item, target=player)

        for modifier in manager._broadcast_event(event):
            self._apply_modifier(player, modifier)

        return (
            f"Use {item.name}: succeeded, "
            f"Orton now at {player.hit_points}/{player.max_hit_points} HP{survival_note}."
        )

    def _resolve_update_inventory(self, accepted: Accepted) -> str:
        manager = self.manager
        action: UpdateInventoryAction = accepted.action

        if action.operation == "ADD":
            item = accepted.resolved["item"]
            manager.player.inventory.append(ItemEntity(item=item))
            return f"Added {item.name} to inventory."

        entity = accepted.resolved["item_entity"]
        if action.operation == "REMOVE":
            manager.player.inventory.remove(entity)
            return f"Removed {entity.item.name} from inventory."
        if action.operation == "UPDATE_CONDITION":
            entity.hit_points = int(action.value)
            return f"{entity.item.name} condition is now {entity.hit_points}."

        # UPDATE_QUANTITY: N copies of an item are N entities; adjust the
        # count to match the target, capped by remaining inventory room.
        target_quantity = int(action.value)
        matching = [e for e in manager.player.inventory if e.item.id == entity.item.id]
        while len(matching) > target_quantity:
            manager.player.inventory.remove(matching.pop())
        room = manager.player.max_inventory_size - len(manager.player.inventory)
        for _ in range(min(target_quantity - len(matching), room)):
            manager.player.inventory.append(ItemEntity(item=entity.item))
        return f"{entity.item.name} quantity is now {target_quantity}."

    # === Combat ===

    def _resolve_attack(self, accepted: Accepted) -> str:
        manager = self.manager
        npc = accepted.resolved["npc"]
        attacker = manager.player
        weapon = self._equipped_weapon(attacker) or UNARMED_WEAPON
        base_damage = weapon.damage

        # Two events for one hit: one for the attacker's "dealt" reactions
        # (e.g. Gun Slinger's +20% with ranged weapons), one for the
        # defender's "taken" reactions (e.g. Small Frame's +10% damage
        # taken). Both contribute to a single combined multiplier so the hit
        # is only ever subtracted once.
        dealt_event = WeaponDealDamageEvent(
            source=attacker, weapon=weapon, damage=base_damage, target=npc
        )
        taken_event = WeaponTakeDamageEvent(
            source=attacker, weapon=weapon, damage=base_damage, target=npc
        )
        dealt_modifiers = manager._broadcast_event(dealt_event)
        taken_modifiers = manager._broadcast_event(taken_event)

        multiplier = 1.0
        for modifier in (*dealt_modifiers, *taken_modifiers):
            if isinstance(modifier, DamageMultiplicativeModifier):
                multiplier *= modifier.multiplier

        jitter = 1.0 + self._rng.uniform(-DAMAGE_JITTER, DAMAGE_JITTER)
        final_damage = max(1, int(base_damage * multiplier * jitter))

        before = npc.hit_points
        npc.hit_points -= final_damage
        dealt = before - npc.hit_points

        self._apply_relationship_modifiers(dealt_modifiers)
        self._apply_relationship_modifiers(taken_modifiers)

        if npc.hit_points <= 0:
            fact = (
                f"Attack {npc.name} with {weapon.name}: hit for {dealt} damage, "
                f"{npc.name} is down."
            )
            return self._with_quest_note(fact, f"defeat:{npc.npc_id}")
        return (
            f"Attack {npc.name} with {weapon.name}: hit for {dealt} damage, "
            f"{npc.name} now at {npc.hit_points}/{npc.max_hit_points} HP."
        )

    def _with_quest_note(self, fact: str, objective_key: str) -> str:
        """Append any quest progress `objective_key` caused to `fact`.

        Called from inside the `_resolve_*` methods, after the state change
        has actually landed -- a validator rejection never reaches them, so a
        refused action can't tick an objective.
        """
        note = self._advance_quests(objective_key)
        return f"{fact} {note}" if note else fact

    def _advance_quests(self, objective_key: str) -> str:
        """Mark `objective_key` complete on every active quest that has it.

        The only way a quest advances -- there is no LLM verb for it. Every
        producer of an objective key lives in this class: taking an item,
        reaching a location, discovering a flag, defeating an NPC, and adding
        an NPC status. Removing a status deliberately does not un-complete an
        objective; quest progress only moves forward.
        """
        notes: list[str] = []
        for quest in self.manager.quests.values():
            if quest.status != QuestStatus.ACTIVE:
                continue
            if objective_key not in quest.objectives:
                continue
            if objective_key in quest.completed_objectives:
                continue
            quest.completed_objectives.append(objective_key)
            notes.append(f"Quest '{quest.quest_id}' objective complete: {objective_key}.")
            if quest.is_complete():
                quest.status = QuestStatus.COMPLETED
                notes.append(f"Quest '{quest.quest_id}' completed!")
        return " ".join(notes)

    @staticmethod
    def _equipped_weapon(player) -> MeleeWeaponItem | RangedWeaponItem | None:
        for entity in player.equipment.values():
            if entity is not None and isinstance(entity.item, (MeleeWeaponItem, RangedWeaponItem)):
                return entity.item
        return None

    def _apply_relationship_modifiers(self, modifiers) -> None:
        for modifier in modifiers:
            if isinstance(modifier, AffinityModifier):
                self.manager.relationship_manager.apply_affinity_modifier(modifier)
            elif isinstance(modifier, ReputationModifier):
                self.manager.relationship_manager.apply_reputation_modifier(modifier)

    def _apply_modifier(self, entity, modifier) -> None:
        """Apply one modifier directly to an entity (item effects, item-use
        trait reactions). Attribute/XP modifiers have no current producer on
        this path and are intentionally left unhandled rather than guessed
        at; see docs/00-status.md for the note."""
        if isinstance(modifier, HPModifier):
            entity.hit_points += modifier.amount
        elif isinstance(modifier, ConditionsModifier):
            for condition, active in modifier.conditions.items():
                if active and condition not in entity.conditions:
                    entity.conditions.append(condition)
                elif not active and condition in entity.conditions:
                    entity.conditions.remove(condition)
        elif isinstance(modifier, AffinityModifier):
            self.manager.relationship_manager.apply_affinity_modifier(modifier)
        elif isinstance(modifier, ReputationModifier):
            self.manager.relationship_manager.apply_reputation_modifier(modifier)

    # === World state (goals / flags / relationships / NPCs / status / time) ===

    def _resolve_add_goal(self, accepted: Accepted) -> str:
        action: AddGoalAction = accepted.action
        goals = self.manager.narrative.goals[action.horizon]
        if action.goal_text not in goals:
            goals.append(action.goal_text)
        return f"Added {action.horizon} goal: {action.goal_text}."

    def _resolve_remove_goal(self, accepted: Accepted) -> str:
        action: RemoveGoalAction = accepted.action
        self.manager.narrative.goals[action.horizon].remove(action.goal_text)
        return f"Removed {action.horizon} goal: {action.goal_text}."

    def _resolve_set_flag(self, accepted: Accepted) -> str:
        action: SetFlagAction = accepted.action
        self.manager.narrative.flags[action.flag_name] = action.value
        return f"Flag '{action.flag_name}' is now {action.value}."

    def _resolve_discover_flag(self, accepted: Accepted) -> str:
        action: DiscoverFlagAction = accepted.action
        self.manager.narrative.discovered_flags.add(action.flag_name)
        value = self.manager.narrative.flags.get(action.flag_name)
        return self._with_quest_note(
            f"Discovered flag '{action.flag_name}' (currently {value}).",
            f"discover:{action.flag_name}",
        )

    def _resolve_update_relationship(self, accepted: Accepted) -> str:
        action: UpdateRelationshipAction = accepted.action
        npc = accepted.resolved["npc"]
        manager = self.manager
        if action.axis == "affection":
            manager.relationship_manager.apply_affinity_modifier(
                AffinityModifier(
                    source_id=npc.npc_id,
                    target_id=manager.player.entity_id,
                    amount=action.amount,
                )
            )
            score = manager.relationship_manager.get_affinity(
                npc.npc_id, manager.player.entity_id
            )
        else:
            score = manager.relationship_manager.adjust_trust(
                npc.npc_id, manager.player.entity_id, action.amount
            )
        return f"{npc.name} {action.axis} is now {score}."

    def _resolve_add_relationship_note(self, accepted: Accepted) -> str:
        action: AddRelationshipNoteAction = accepted.action
        npc = accepted.resolved["npc"]
        npc.notes = f"{npc.notes}; {action.note}" if npc.notes else action.note
        return f"Noted about {npc.name}: {action.note}"

    def _resolve_npc_move(self, accepted: Accepted) -> str:
        npc = accepted.resolved["npc"]
        location = accepted.resolved["location"]
        npc.current_location_id = location.id
        return f"{npc.name} moved to {location.name}."

    def _resolve_npc_status(self, accepted: Accepted) -> str:
        action: NpcStatusAction = accepted.action
        npc = accepted.resolved["npc"]
        if action.operation == "ADD":
            if action.status not in npc.status:
                npc.status.append(action.status)
            return self._with_quest_note(
                f"{npc.name} is now '{action.status}'.",
                f"npc_status:{npc.npc_id}:{action.status}",
            )
        # No quest note on REMOVE: see _advance_quests -- progress is one-way.
        npc.status.remove(action.status)
        return f"{npc.name} is no longer '{action.status}'."

    def _resolve_status_add(self, accepted: Accepted) -> str:
        action: StatusAddAction = accepted.action
        manager = self.manager
        condition = manager._as_condition(action.status)
        if condition is not None and condition not in manager.player.conditions:
            manager.player.conditions.append(condition)
        if action.status not in manager.narrative.player_status:
            manager.narrative.player_status.append(action.status)
        return f"Added status '{action.status}'."

    def _resolve_status_remove(self, accepted: Accepted) -> str:
        action: StatusRemoveAction = accepted.action
        manager = self.manager
        condition = manager._as_condition(action.status)
        if condition is not None and condition in manager.player.conditions:
            manager.player.conditions.remove(condition)
        manager.narrative.player_status.remove(action.status)
        return f"Removed status '{action.status}'."

    def _resolve_update_condition(self, accepted: Accepted) -> str:
        action: UpdateConditionAction = accepted.action
        manager = self.manager
        if action.field_name in NARRATIVE_CONDITION_FIELDS:
            value = accepted.resolved["value"]
            manager.narrative.conditions[action.field_name] = value
            return f"{action.field_name} is now {value}."

        attribute = action.field_name  # hunger / thirst / morale
        if action.raw_value[0] in "+-":
            new_value = getattr(manager.player, attribute) + int(action.raw_value)
        else:
            new_value = int(action.raw_value)
        setattr(manager.player, attribute, max(0, min(new_value, 100)))
        return f"{action.field_name} is now {getattr(manager.player, attribute)}."

    def _resolve_time_advance(self, accepted: Accepted) -> str:
        action: TimeAdvanceAction = accepted.action
        manager = self.manager
        manager._action_time_advance(action.time_of_day)
        return f"Time is now {action.time_of_day} (day {manager.narrative.day})."

    _RESOLVERS = {
        MoveAction: _resolve_move,
        TakeAction: _resolve_take,
        DropAction: _resolve_drop,
        AttackAction: _resolve_attack,
        UseItemAction: _resolve_use_item,
        TimeAdvanceAction: _resolve_time_advance,
        StatusAddAction: _resolve_status_add,
        StatusRemoveAction: _resolve_status_remove,
        UpdateConditionAction: _resolve_update_condition,
        AddGoalAction: _resolve_add_goal,
        RemoveGoalAction: _resolve_remove_goal,
        UpdateRelationshipAction: _resolve_update_relationship,
        AddRelationshipNoteAction: _resolve_add_relationship_note,
        SetFlagAction: _resolve_set_flag,
        DiscoverFlagAction: _resolve_discover_flag,
        UpdateInventoryAction: _resolve_update_inventory,
        NpcMoveAction: _resolve_npc_move,
        NpcStatusAction: _resolve_npc_status,
    }
