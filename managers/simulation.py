"""Simulation Core: deterministic outcome resolution for accepted actions.

Validates each action (via `managers/validator.py`) and decides what actually
happens -- HP, inventory, position, the clock -- before any prose exists.
Movement, inventory, and world-state actions are direct field mutations;
combat and item use additionally build real events and run them through the
event/effect/modifier pipeline in `managers/game.py` (see
`GameManager._broadcast_event`), so trait/perk reactions in `data/traits.py`
and `data/perks.py` fire.

`resolve()` returns one outcome-fact string per action -- what the narrator
prompt describes. The narrator is never the source of truth for anything in
this list; it only puts prose around facts the engine already decided.
"""

import random

from data import status_effects, survival
from data.items import item_condition_word
from data.time_costs import MULTIPLIED_ACTIONS, NONE_TURN_MIN, action_minutes
from managers.climate import weather_change_facts
from managers.game import DEATH_CAUSE_MAX_LENGTH, GameManager
from managers.stats import (
    StatContext,
    StatsEngine,
    injury_words,
    level_change_facts,
    player_status_effect_levels,
    status_effect_level,
)
from managers.validator import Accepted, ActionValidator, Rejected
from modules.action import (
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
    SleepAction,
    StatusAddAction,
    StatusRemoveAction,
    TakeAction,
    UpdateInventoryAction,
    UpdateRelationshipAction,
    UseItemAction,
    WaitAction,
)
from modules.character.equipment import CharacterHoldableSlot
from modules.entity.item import ItemEntity
from modules.event import (
    ApplyItemEvent,
    ConsumeItemEvent,
    WeaponDealDamageEvent,
    WeaponTakeDamageEvent,
)
from modules.item import AppliableItem, ConsumableItem, MeleeWeaponItem, RangedWeaponItem
from modules.modifier import (
    AffinityModifier,
    ConditionsModifier,
    DamageMultiplicativeModifier,
    HPModifier,
    ReputationModifier,
)
from modules.quest import QuestStatus
from modules.resolution import (
    HeldItem,
    MoveBlocked,
    MoveToSpot,
    MoveToZone,
    NewItem,
    NpcDestination,
    ShuffleInZone,
    TargetNpc,
    TimeSpan,
)
from modules.stats import CharacterStat, StatusEffect
from modules.weapon import MeleeWeaponType
from modules.weather import WeatherSample

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


def _span_words(minutes: int) -> str:
    hours, rest = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if rest:
        parts.append(f"{rest} minute{'s' if rest != 1 else ''}")
    return " ".join(parts)


def _minutes_fact(minutes: int) -> str:
    if minutes == 1:
        return "About 1 minute passes."
    return f"About {minutes} minutes pass."


def alcohol_intoxication(item: ConsumableItem, hunger: float) -> float:
    """Intoxication one alcoholic item adds when drunk at the given hunger."""
    portion = (
        status_effects.ALCOHOL_WHOLE_ITEM_PORTION
        if item.hunger_change
        else status_effects.ALCOHOL_PARTIAL_PORTION
    )
    amount = status_effects.ALCOHOL_INTOXICATION_PER_PORTION * portion
    if item.low_alcohol:
        amount *= status_effects.ALCOHOL_LOW_MULT
    if hunger > status_effects.ALCOHOL_HUNGER_HIGH:
        amount *= status_effects.ALCOHOL_HUNGER_HIGH_MULT
    elif hunger > status_effects.ALCOHOL_HUNGER_MID:
        amount *= status_effects.ALCOHOL_HUNGER_MID_MULT
    return amount


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
        self.stats_engine = StatsEngine()
        self._zombies_seen_this_chunk = 0
        self._weather_facts: list[str] = []

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
        total_minutes = 0
        if not actions:
            spent, stat_facts = self._spend(NONE_TURN_MIN)
            total_minutes += spent
            facts.extend(stat_facts)
        for action in actions:
            result = self.validator.validate(action)
            if isinstance(result, Rejected):
                facts.append(f"Refused: {type(result.action).__name__} -- {result.reason}")
            else:
                action_facts, minutes = self._resolve_one(result)
                facts.extend(action_facts)
                total_minutes += minutes
        if total_minutes:
            facts.append(_minutes_fact(total_minutes))
        return facts

    def _action_time_multiplier(self) -> float:
        """Pain, mood and cold slow timed actions; 1 until the health spec lands."""
        return 1.0

    def _new_zombies_seen(self) -> int:
        """Zombies newly in view this chunk; none until zombies exist."""
        return 0

    def _stat_context(
        self, action: AnyAction | None, *, asleep: bool = False, bed_type: str | None = None
    ) -> StatContext:
        manager = self.manager
        player = manager.player
        location = manager.current_location
        self._zombies_seen_this_chunk = self._new_zombies_seen()
        return StatContext(
            asleep=asleep,
            resting=isinstance(action, WaitAction),
            exercising=isinstance(action, AttackAction),
            walking=isinstance(action, MoveAction),
            indoors=location.indoors,
            npcs_present=bool(manager.npcs_in_location(player.current_location_id)),
            bed_type=bed_type or location.bed_type_at(player.current_place),
            hours_survived=manager.narrative.minutes / 60,
            new_zombies_seen=self._zombies_seen_this_chunk,
        )

    def _weather_for_chunk(self, offset: int, chunk: int) -> WeatherSample:
        """Advance the climate across a chunk; returns the weather at its midpoint.

        Facts for what changed over the chunk collect in `_weather_facts`.
        """
        climate = self.manager.climate
        start = self.manager.narrative.minutes + offset
        before = climate.sample(start)
        climate.advance_to(start + chunk)
        self._weather_facts.extend(weather_change_facts(before, climate.sample(start + chunk)))
        return climate.sample(start + chunk / 2)

    def _spend(
        self,
        minutes: int,
        action: AnyAction | None = None,
        *,
        asleep: bool = False,
    ) -> tuple[int, list[str]]:
        """Advance the stats, then the clock by the minutes that really passed.

        Returns those minutes and the facts the stats produced. Once Orton is
        dead the clock still moves but the stats stay where they fell.
        """
        manager = self.manager
        if manager.narrative.game_over:
            manager.climate.advance_to(manager.narrative.minutes + minutes)
            manager.advance_clock(minutes)
            return minutes, []
        self._weather_facts = []
        stat_facts = self.stats_engine.advance(
            manager.player,
            minutes,
            self._stat_context(action, asleep=asleep),
            self._weather_for_chunk,
        )
        facts = self._weather_facts + stat_facts
        spent = self.stats_engine.minutes_advanced
        manager.advance_clock(spent)
        if self.stats_engine.death_cause:
            facts[-1] = self._check_player_death(self.stats_engine.death_cause)
        return spent, facts

    def _resolve_one(self, accepted: Accepted) -> tuple[list[str], int]:
        """Resolve one accepted action; returns its facts and the minutes it took."""
        if isinstance(accepted.action, SleepAction):
            return self._resolve_sleep(accepted)
        handler = self._RESOLVERS.get(type(accepted.action))
        if handler is None:
            return [f"No resolver registered for {type(accepted.action).__name__}."], 0
        minutes = action_minutes(accepted.action, accepted.resolved)
        if isinstance(accepted.action, MULTIPLIED_ACTIONS):
            minutes = round(minutes * self._action_time_multiplier())
        facts = [self._check_player_death(handler(self, accepted))]
        spent = 0
        if minutes:
            spent, stat_facts = self._spend(minutes, accepted.action)
            facts.extend(stat_facts)
        return facts, spent

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

    # === Movement ===

    def _resolve_move(self, accepted: Accepted) -> str:
        """Apply the `MoveOutcome` `_validate_move` chose; MOVE_TO never fails.

        Outcomes with a `place` replace `current_place` (an empty one clears
        it); a stay or a shuffle leaves it as it was.
        """
        player = self.manager.player
        match accepted.resolved:
            case MoveToZone(location=location, place=place):
                player.current_place = place
                player.current_location_id = location.id
                where = f" ({place})" if place else ""
                return self._with_quest_note(
                    f"Move to {location.name}{where}: succeeded.", f"reach:{location.id}"
                )
            case MoveBlocked(location=stop, place=place, target=target):
                player.current_place = place
                fact = (
                    f"Move to {target.name}: blocked -- the door to {target.name} is "
                    f"locked and Orton has no key. Orton is in {stop.name}, {place}."
                )
                if stop.id != player.current_location_id:
                    player.current_location_id = stop.id
                    fact = self._with_quest_note(fact, f"reach:{stop.id}")
                return fact
            case MoveToSpot(location=zone, place=place):
                player.current_place = place
                if place:
                    return f"Move within {zone.name} to {place}: succeeded."
                return f"Already in {zone.name}."
            case ShuffleInZone(location=zone, direction=direction):
                return f"Moved {direction} within {zone.name}."
            case _:
                return "MOVE_TO had no destination; Orton stayed put."

    # === Items ===

    def _resolve_take(self, accepted: Accepted) -> str:
        entity = accepted.expect(HeldItem).entity
        manager = self.manager
        manager.current_location.entities.remove(entity)
        manager.player.inventory.append(entity)
        return self._with_quest_note(
            f"Take {entity.item.name}: succeeded.", f"take:{entity.item.id}"
        )

    def _resolve_drop(self, accepted: Accepted) -> str:
        entity = accepted.expect(HeldItem).entity
        manager = self.manager
        manager.player.inventory.remove(entity)
        manager.current_location.entities.append(entity)
        return f"Drop {entity.item.name}: succeeded."

    def _resolve_use_item(self, accepted: Accepted) -> str:
        manager = self.manager
        entity = accepted.expect(HeldItem).entity
        item = entity.item
        assert isinstance(item, ConsumableItem | AppliableItem), "_validate_use_item checks this"
        player = manager.player

        # The item's own effect (e.g. a medkit's HPModifier) is not a trait/
        # perk reaction -- it applies unconditionally whenever the item is
        # used, so it is applied directly rather than through the broadcast.
        for modifier in item.modifiers:
            self._apply_modifier(player, modifier)

        if isinstance(item, ConsumableItem):
            event = ConsumeItemEvent(source=player, item=item)
            manager.player.inventory.remove(entity)
            consume_facts = self._consume(item)
        else:
            consume_facts = []
            event = ApplyItemEvent(source=player, item=item, target=player)

        for modifier in manager._broadcast_event(event):
            self._apply_modifier(player, modifier)

        return " ".join(
            [
                f"Use {item.name}: succeeded, "
                f"Orton is {injury_words(player.hit_points, player.max_hit_points)}.",
                *consume_facts,
            ]
        )

    def _consume(self, item: ConsumableItem) -> list[str]:
        """Apply every food field once, feed the well-fed timer and add alcohol.

        Returns the facts for status effects whose level the meal changed.
        """
        player = self.manager.player
        stats = player.stats
        before = player_status_effect_levels(player)
        if item.alcoholic:
            stats.add(
                CharacterStat.INTOXICATION,
                alcohol_intoxication(item, stats.get(CharacterStat.HUNGER)),
            )
        stats.add(CharacterStat.HUNGER, item.hunger_change)
        stats.add(CharacterStat.THIRST, item.thirst_change)
        stats.add(CharacterStat.UNHAPPINESS, item.unhappy_change)
        stats.add(CharacterStat.BOREDOM, item.boredom_change)
        stats.add(CharacterStat.STRESS, item.stress_change)
        fed = abs(item.hunger_change) * status_effects.FOOD_EATEN_PER_HUNGER
        if item.cooked:
            fed *= status_effects.FOOD_EATEN_COOKED_MULT
        player.food_eaten_timer = min(status_effects.FOOD_EATEN_CAP, player.food_eaten_timer + fed)
        return level_change_facts(before, player_status_effect_levels(player))

    def _resolve_update_inventory(self, accepted: Accepted) -> str:
        manager = self.manager
        action: UpdateInventoryAction = accepted.action

        if action.operation == "ADD":
            item = accepted.expect(NewItem).item
            manager.player.inventory.append(ItemEntity(item=item))
            return f"Added {item.name} to inventory."

        entity = accepted.expect(HeldItem).entity
        if action.operation == "REMOVE":
            manager.player.inventory.remove(entity)
            return f"Removed {entity.item.name} from inventory."
        if action.operation == "UPDATE_CONDITION":
            entity.hit_points = int(action.value)
            return f"{entity.item.name} is now {item_condition_word(entity)}."

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
        npc = accepted.expect(TargetNpc).npc
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

        npc.hit_points -= final_damage

        self._apply_relationship_modifiers(dealt_modifiers)
        self._apply_relationship_modifiers(taken_modifiers)

        if npc.hit_points <= 0:
            fact = f"Attack {npc.name} with {weapon.name}: hit, {npc.name} is down."
            return self._with_quest_note(fact, f"defeat:{npc.npc_id}")
        hurt = injury_words(npc.hit_points, npc.max_hit_points)
        return f"Attack {npc.name} with {weapon.name}: hit, {npc.name} is {hurt}."

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
        npc = accepted.expect(TargetNpc).npc
        manager = self.manager
        relationships = manager.relationship_manager
        player_id = manager.player.entity_id
        if action.axis == "affection":
            relationships.apply_affinity_modifier(
                AffinityModifier(source_id=npc.npc_id, target_id=player_id, amount=action.amount)
            )
            disposition = relationships.get_disposition(npc.npc_id, player_id)
            return f"{npc.name} now feels {disposition} toward Orton."
        relationships.adjust_trust(npc.npc_id, player_id, action.amount)
        trust = relationships.get_trust_level(npc.npc_id, player_id)
        return f"{npc.name}'s trust in Orton is now {trust}."

    def _resolve_add_relationship_note(self, accepted: Accepted) -> str:
        action: AddRelationshipNoteAction = accepted.action
        npc = accepted.expect(TargetNpc).npc
        npc.notes = f"{npc.notes}; {action.note}" if npc.notes else action.note
        return f"Noted about {npc.name}: {action.note}"

    def _resolve_npc_move(self, accepted: Accepted) -> str:
        destination = accepted.expect(NpcDestination)
        npc, location = destination.npc, destination.location
        npc.current_location_id = location.id
        return f"{npc.name} moved to {location.name}."

    def _resolve_npc_status(self, accepted: Accepted) -> str:
        action: NpcStatusAction = accepted.action
        npc = accepted.expect(TargetNpc).npc
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

    def _resolve_wait(self, accepted: Accepted) -> str:
        span = accepted.expect(TimeSpan)
        spent = _span_words(span.minutes)
        if span.clamped:
            return f"Orton waits {spent}, the most he can at once."
        return f"Orton waits {spent}."

    def _resolve_sleep(self, accepted: Accepted) -> tuple[list[str], int]:
        """Sleep chunk by chunk until the time is up or something wakes Orton."""
        span = accepted.expect(TimeSpan)
        player = self.manager.player
        wanted = span.minutes
        player.asleep = True
        spent = 0
        facts: list[str] = []
        wake_fact = ""
        while spent < wanted and not self.manager.narrative.game_over:
            chunk = min(survival.MAX_CHUNK_MINUTES, wanted - spent)
            advanced, stat_facts = self._spend(chunk, accepted.action, asleep=True)
            spent += advanced
            facts.extend(stat_facts)
            wake_fact = self._waking(spent)
            if wake_fact:
                break
        player.asleep = False
        words = _span_words(spent)
        if span.clamped:
            lead = f"Orton sleeps {words}, the most he can at once."
        else:
            lead = f"Orton sleeps {words}."
        return [lead, *facts, *([wake_fact] if wake_fact else [])], spent

    def _waking(self, slept_minutes: int) -> str:
        """The fact for what wakes Orton after this chunk, or "" if nothing does."""
        if self.manager.narrative.game_over:
            return ""
        player = self.manager.player
        if self._zombies_seen_this_chunk > 0:
            panic = self._rng.uniform(
                survival.SLEEP_INTERRUPTION_PANIC_MIN, survival.SLEEP_INTERRUPTION_PANIC_MAX
            )
            player.stats.add(CharacterStat.PANIC, panic)
            return "A zombie wakes Orton in a panic."
        stats = player.stats
        if status_effect_level(StatusEffect.HUNGRY, stats.get(CharacterStat.HUNGER)) >= (
            survival.SLEEP_WAKE_STATUS_EFFECT_LEVEL
        ):
            return "Hunger wakes Orton."
        if status_effect_level(StatusEffect.THIRST, stats.get(CharacterStat.THIRST)) >= (
            survival.SLEEP_WAKE_STATUS_EFFECT_LEVEL
        ):
            return "Thirst wakes Orton."
        if (
            stats.get(CharacterStat.FATIGUE) <= 0
            and slept_minutes >= survival.SLEEP_FATIGUE_WAKE_MIN_HOURS * 60
        ):
            return "Orton wakes fully rested."
        return ""

    _RESOLVERS = {
        MoveAction: _resolve_move,
        TakeAction: _resolve_take,
        DropAction: _resolve_drop,
        AttackAction: _resolve_attack,
        UseItemAction: _resolve_use_item,
        WaitAction: _resolve_wait,
        SleepAction: _resolve_sleep,
        StatusAddAction: _resolve_status_add,
        StatusRemoveAction: _resolve_status_remove,
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
