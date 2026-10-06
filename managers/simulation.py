"""Simulation Core: deterministic outcome resolution for accepted actions.

Validates each action (via `managers/validator.py`) and decides what actually
happens -- HP, inventory, position, the clock -- before any prose exists.
Movement, inventory, and world-state actions are direct field mutations;
combat and item use additionally build real events and run them through the
event/effect/modifier pipeline in `managers/events.py`, so trait reactions fire.

`resolve()` returns one outcome-fact string per action -- what the narrator
prompt describes. The narrator is never the source of truth for anything in
this list; it only puts prose around facts the engine already decided.
"""

import random
from dataclasses import dataclass

from data import exercises as ex_k
from data import skills as skill_k
from data import status_effects, survival
from data import thermal as thermal_k
from data.exercises import find_exercise
from data.items import item_condition_word
from data.thermal import Metabolic
from data.time_costs import (
    MULTIPLIED_ACTIONS,
    NONE_TURN_MIN,
    SWING_MIN,
    WALK_TO_BARRIER_MIN,
    action_minutes,
    zone_hop_minutes,
)
from managers.climate import weather_change_facts
from managers.combat import UNARMED_WEAPON, equipped_weapon, roll_damage
from managers.events import broadcast_event
from managers.exercise import ExerciseEngine, endurance_level, reps_per_minute
from managers.game import DEATH_CAUSE_MAX_LENGTH, GameManager
from managers.noise import Sound, cough_sound
from managers.skills import SkillEngine, skill_levels
from managers.stats.drivers import StatContext
from managers.stats.engine import StatsEngine
from managers.stats.status_effects import (
    alcohol_intoxication,
    injury_words,
    level_change_facts,
    player_status_effect_levels,
    status_effect_level,
)
from managers.thermoregulator import attack_metabolic
from managers.validator import Accepted, ActionValidator, Rejected
from managers.zombies import PlayerMinute, ZombieLoop, enter_zone, start_outbreak
from modules.action.types import (
    AddGoalAction,
    AddRelationshipNoteAction,
    AnyAction,
    AttackAction,
    DiscoverFlagAction,
    DropAction,
    ExerciseAction,
    MoveAction,
    NpcMoveAction,
    NpcStatusAction,
    RemoveGoalAction,
    SetFlagAction,
    SleepAction,
    StanceAction,
    StatusAddAction,
    StatusRemoveAction,
    TakeAction,
    TakeOffAction,
    UpdateInventoryAction,
    UpdateRelationshipAction,
    UseItemAction,
    WaitAction,
    WearAction,
)
from modules.effect import AnyStoryEffect, StartOutbreakEffect
from modules.entity.item import ItemEntity
from modules.event import (
    ApplyItemEvent,
    ConsumeItemEvent,
)
from modules.item import AppliableItem, ClothingItem, ConsumableItem, MeleeWeaponItem
from modules.modifier import (
    AffinityModifier,
    ConditionsModifier,
    HPModifier,
    ReputationModifier,
)
from modules.pace import Pace
from modules.quest import QuestStatus
from modules.resolution import (
    ExercisePlan,
    HeldItem,
    MoveBlocked,
    MoveToSpot,
    MoveToZone,
    NewItem,
    NpcDestination,
    ShuffleInZone,
    TargetNpc,
    TargetZombie,
    TimeSpan,
)
from modules.stats import CharacterStat, StatusEffect
from modules.weather import WeatherSample


def _span_words(minutes: int) -> str:
    hours, rest = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if rest:
        parts.append(f"{rest} minute{'s' if rest != 1 else ''}")
    return " ".join(parts)


INTERRUPTED_PLAN_FACT = "The rest of the plan is dropped."
INTERRUPTED_BY_ATTACK = "attacked"


@dataclass(frozen=True)
class Motion:
    """How the player moves during a span of minutes."""

    pace: Pace = Pace.STILL
    approach_target: str | None = None
    swing_target: str | None = None


def _minutes_fact(minutes: int) -> str:
    if minutes == 1:
        return "About 1 minute passes."
    return f"About {minutes} minutes pass."


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
        self.stats_engine = StatsEngine(rng=self._rng)
        self.skill_engine = SkillEngine()
        self.exercise_engine = ExerciseEngine(self.skill_engine)
        self._skill_facts: list[str] = []
        self._zombies_seen_this_chunk = 0
        self._weather_facts: list[str] = []
        self._loop = ZombieLoop(manager, self._rng, self.skill_engine)
        self._interruption = ""
        self._pending_sounds: list[Sound] = []

    @property
    def _name(self) -> str:
        return self.manager.player.appearance.forename

    @property
    def _subject(self) -> str:
        return self.manager.player.appearance.subject

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
        for index, action in enumerate(actions):
            result = self.validator.validate(action)
            if isinstance(result, Rejected):
                facts.append(f"Refused: {type(result.action).__name__} -- {result.reason}")
                continue
            self._interruption = ""
            action_facts, minutes = self._resolve_one(result)
            facts.extend(action_facts)
            total_minutes += minutes
            if self._interruption:
                if index + 1 < len(actions):
                    facts.append(INTERRUPTED_PLAN_FACT)
                break
        if total_minutes:
            facts.append(_minutes_fact(total_minutes))
        return facts

    def apply_story_effect(self, effect: AnyStoryEffect) -> None:
        """Apply an effect a story beat fires."""
        if isinstance(effect, StartOutbreakEffect):
            manager = self.manager
            start_outbreak(
                manager.world,
                manager.narrative.minutes,
                manager.player.current_location_id,
                self._rng,
            )
            self._loop.forget_visible()

    def _action_time_multiplier(self) -> float:
        """Pain, mood and cold slow timed actions; 1 until the health spec lands."""
        return 1.0

    def _stat_context(
        self,
        action: AnyAction | None,
        *,
        asleep: bool = False,
        bed_type: str | None = None,
        seen: int = 0,
        exerting: bool = False,
        pace: Pace = Pace.STILL,
    ) -> StatContext:
        manager = self.manager
        player = manager.player
        location = manager.current_location
        return StatContext(
            asleep=asleep,
            resting=isinstance(action, WaitAction),
            exercising=isinstance(action, AttackAction) or exerting or pace == Pace.RUN,
            walking=isinstance(action, MoveAction),
            sneaking=player.sneaking,
            indoors=location.indoors,
            npcs_present=bool(manager.npcs_in_location(player.current_location_id)),
            bed_type=bed_type or location.bed_type_at(player.current_place),
            hours_survived=manager.narrative.minutes / 60,
            new_zombies_seen=seen,
            floor=location.floor,
            power_on=manager.world.power_on,
            metabolic=self._metabolic_target(action),
            traits=frozenset(player.traits),
            skills=skill_levels(player),
        )

    def _metabolic_target(self, action: AnyAction | None) -> Metabolic:
        if isinstance(action, MoveAction):
            return Metabolic.WALKING_5KMH
        if isinstance(action, AttackAction):
            return attack_metabolic(equipped_weapon(self.manager.player))
        if isinstance(action, ExerciseAction):
            exercise = find_exercise(action.exercise_name)
            if exercise is not None:
                return Metabolic.FITNESS_HEAVY if exercise.heavy else Metabolic.FITNESS
        return Metabolic.DEFAULT

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
        motion: Motion | None = None,
    ) -> tuple[int, list[str]]:
        """Run the zombies and the stats over `minutes`, then advance the clock.

        Each block of at most 10 minutes runs the zombie loop minute by minute, then
        the stats over the minutes that passed; an interruption ends the span early.
        Returns those minutes and the facts they produced. Once the player is dead
        the clock still moves but the stats stay where they fell.
        """
        manager = self.manager
        if manager.narrative.game_over:
            manager.climate.advance_to(manager.narrative.minutes + minutes)
            manager.advance_clock(minutes)
            return minutes, []
        motion = motion or Motion()
        facts: list[str] = []
        spent = 0
        started = manager.narrative.minutes
        self._zombies_seen_this_chunk = 0
        while spent < minutes and not self._interruption:
            block = min(survival.MAX_CHUNK_MINUTES, minutes - spent)
            ran, seen, exerting, loop_facts = self._zombie_minutes(block, asleep, motion)
            facts.extend(loop_facts)
            self._zombies_seen_this_chunk += seen
            if manager.narrative.game_over:
                manager.climate.advance_to(manager.narrative.minutes + ran)
                manager.advance_clock(ran)
                return spent + ran, facts
            self._weather_facts = []
            stat_facts = self.stats_engine.advance(
                manager.player,
                ran,
                self._stat_context(
                    action, asleep=asleep, seen=seen, exerting=exerting, pace=motion.pace
                ),
                self._weather_for_chunk,
            )
            facts.extend(self._weather_facts + stat_facts)
            advanced = self.stats_engine.minutes_advanced
            manager.advance_clock(advanced)
            spent += advanced
            self._pending_sounds.extend(self._coughs(stat_facts))
            if self.stats_engine.death_cause:
                facts[-1] = self._check_player_death(self.stats_engine.death_cause)
                break
        if not manager.narrative.game_over:
            facts.extend(self._run_ticks(started, spent, walking=isinstance(action, MoveAction)))
        return spent, facts

    def _coughs(self, stat_facts: list[str]) -> list[Sound]:
        words = {
            thermal_k.COUGH_FACT.format(name=self._name),
            thermal_k.SNEEZE_FACT.format(name=self._name),
        }
        return [cough_sound() for fact in stat_facts if fact in words]

    def _zombie_minutes(
        self, block: int, asleep: bool, motion: Motion
    ) -> tuple[int, int, bool, list[str]]:
        """Run up to `block` minutes of the zombie loop; stops at an interruption or a death.

        Returns the minutes run, the zombies newly seen, whether a zombie attacked and the facts.
        """
        manager = self.manager
        seen = 0
        exerting = False
        facts: list[str] = []
        ran = 0
        while ran < block:
            minute = PlayerMinute(
                pace=Pace.STILL if asleep else motion.pace,
                asleep=asleep,
                approach_target=motion.approach_target,
                swing_target=motion.swing_target,
            )
            sounds, self._pending_sounds = self._pending_sounds, []
            report = self._loop.run_minute(manager.narrative.minutes + ran, minute, sounds)
            ran += 1
            seen += report.new_seen
            exerting = exerting or report.attacked
            facts.extend(report.facts)
            if report.death_fact:
                facts.append(self._check_player_death(report.death_fact))
                break
            if report.interrupted:
                self._interruption = report.interruption_fact or INTERRUPTED_BY_ATTACK
                if report.interruption_fact:
                    facts.append(
                        report.interruption_fact.format(
                            name=self._name, object=manager.player.appearance.object
                        )
                    )
                break
        return ran, seen, exerting, facts

    def _run_ticks(self, started: int, spent: int, *, walking: bool) -> list[str]:
        """Run the 10-minute boundary hooks for each boundary the span crossed."""
        first = started // skill_k.TICK_MINUTES + 1
        last = (started + spent) // skill_k.TICK_MINUTES
        facts: list[str] = []
        for boundary in range(first, last + 1):
            player = self.manager.player
            facts.extend(self.skill_engine.tick(player, walking=walking))
            self.exercise_engine.tick(player, boundary * skill_k.TICK_MINUTES)
        return facts

    def _resolve_one(self, accepted: Accepted) -> tuple[list[str], int]:
        """Resolve one accepted action; returns its facts and the minutes it took."""
        if isinstance(accepted.action, SleepAction):
            return self._resolve_sleep(accepted)
        if isinstance(accepted.action, ExerciseAction):
            return self._resolve_exercise(accepted)
        if isinstance(accepted.resolved, TargetZombie):
            return self._resolve_zombie_attack(accepted)
        if isinstance(accepted.action, MoveAction):
            if accepted.action.run:
                self.manager.player.sneaking = False
            if isinstance(accepted.resolved, MoveToZone | MoveBlocked):
                return self._resolve_walk(accepted)
        handler = self._RESOLVERS.get(type(accepted.action))
        if handler is None:
            return [f"No resolver registered for {type(accepted.action).__name__}."], 0
        minutes = action_minutes(accepted.action, accepted.resolved)
        if isinstance(accepted.action, MULTIPLIED_ACTIONS):
            minutes = round(minutes * self._action_time_multiplier())
        self._skill_facts = []
        facts = [self._check_player_death(handler(self, accepted)), *self._skill_facts]
        spent = 0
        if minutes:
            spent, stat_facts = self._spend(minutes, accepted.action)
            facts.extend(stat_facts)
        return facts, spent

    def _check_player_death(self, fact: str) -> str:
        """End the game the moment the player's HP reaches zero.

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
        return f"{fact} {self._name} has died. The game is over."

    # === Movement ===

    def _resolve_move(self, accepted: Accepted) -> str:
        """Apply a `MoveOutcome` that stays in the zone; MOVE_TO never fails.

        A spot replaces `current_place` (an empty one clears it); a stay or a
        shuffle leaves it as it was. Zone changes go through `_resolve_walk`.
        """
        player = self.manager.player
        match accepted.resolved:
            case MoveToSpot(location=zone, place=place):
                player.current_place = place
                if place:
                    return f"Move within {zone.name} to {place}: succeeded."
                return f"Already in {zone.name}."
            case ShuffleInZone(location=zone, direction=direction):
                return f"Moved {direction} within {zone.name}."
            case _:
                return f"MOVE_TO had no destination; {self._name} stayed put."

    def _resolve_walk(self, accepted: Accepted) -> tuple[list[str], int]:
        """Walk the route one hop at a time; an interruption stops the player where they are.

        The player enters each zone for the last minute of its hop.
        """
        manager = self.manager
        player = manager.player
        resolved = accepted.resolved
        assert isinstance(resolved, MoveToZone | MoveBlocked)
        origin_id = player.current_location_id
        route = manager.zone_path(origin_id, resolved.location.id) or []
        spent = 0
        spend_facts: list[str] = []
        if not route:
            spent, spend_facts = self._spend(WALK_TO_BARRIER_MIN, accepted.action)
        for zone_id in route:
            hop_spent, hop_facts = self._walk_hop(zone_id, accepted.action, resolved.pace)
            spent += hop_spent
            spend_facts.extend(hop_facts)
            if self._interruption or manager.narrative.game_over:
                break
        interrupted = bool(self._interruption) or manager.narrative.game_over
        fact = self._walk_fact(resolved, origin_id, interrupted)
        return [self._check_player_death(fact), *spend_facts], spent

    def _walk_hop(self, zone_id: str, action: AnyAction, pace: Pace) -> tuple[int, list[str]]:
        """One hop: the first minutes in the zone being left, the last one in the new zone.

        Before the outbreak nobody can tell, so the whole hop is spent in the new zone.
        """
        manager = self.manager
        player = manager.player
        motion = Motion(pace)
        if not self._loop.active():
            player.current_location_id = zone_id
            player.current_place = ""
            return self._spend(zone_hop_minutes(pace), action, motion=motion)
        spent, facts = self._spend(zone_hop_minutes(pace) - 1, action, motion=motion)
        if self._interruption or manager.narrative.game_over:
            return spent, facts
        previous_id = player.current_location_id
        player.current_location_id = zone_id
        player.current_place = ""
        enter_zone(manager.world, zone_id, previous_id, self._rng)
        last, last_facts = self._spend(1, action, motion=motion)
        return spent + last, [*facts, *last_facts]

    def _walk_fact(
        self, resolved: MoveToZone | MoveBlocked, origin_id: str, interrupted: bool
    ) -> str:
        player = self.manager.player
        here = self.manager.current_location
        changed = here.id != origin_id
        if interrupted:
            fact = (
                f"Move to {resolved.location.name}: interrupted -- {self._name} is in {here.name}."
            )
            if resolved.location.id == here.id and isinstance(resolved, MoveToZone):
                fact = f"Move to {here.name}: interrupted on arrival."
            return self._with_quest_note(fact, f"reach:{here.id}") if changed else fact
        player.current_place = resolved.place
        if isinstance(resolved, MoveToZone):
            where = f" ({resolved.place})" if resolved.place else ""
            return self._with_quest_note(
                f"Move to {resolved.location.name}{where}: succeeded.",
                f"reach:{resolved.location.id}",
            )
        fact = (
            f"Move to {resolved.target.name}: blocked -- the door to {resolved.target.name} is "
            f"locked and {self._name} has no key. {self._name} is in {here.name}, {resolved.place}."
        )
        return self._with_quest_note(fact, f"reach:{here.id}") if changed else fact

    def _resolve_stance(self, accepted: Accepted) -> str:
        action = accepted.action
        assert isinstance(action, StanceAction), "only STANCE is routed here"
        self.manager.player.sneaking = action.sneaking
        if action.sneaking:
            return f"{self._name} starts moving quietly."
        return f"{self._name} stops sneaking."

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

    def _resolve_wear(self, accepted: Accepted) -> str:
        entity = accepted.expect(HeldItem).entity
        item = entity.item
        assert isinstance(item, ClothingItem), "_validate_wear checks this"
        self.manager.player.inventory.remove(entity)
        self.manager.player.worn[item.body_location] = entity
        return f"Wear {item.name}: succeeded."

    def _resolve_take_off(self, accepted: Accepted) -> str:
        entity = accepted.expect(HeldItem).entity
        item = entity.item
        assert isinstance(item, ClothingItem), "only clothing is ever worn"
        del self.manager.player.worn[item.body_location]
        self.manager.player.inventory.append(entity)
        return f"Take off {item.name}: succeeded."

    def _resolve_use_item(self, accepted: Accepted) -> str:
        manager = self.manager
        entity = accepted.expect(HeldItem).entity
        item = entity.item
        assert isinstance(item, ConsumableItem | AppliableItem), "_validate_use_item checks this"
        player = manager.player

        # The item's own effect (e.g. a medkit's HPModifier) is not a trait
        # reaction -- it applies unconditionally whenever the item is
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

        for modifier in broadcast_event(event):
            self._apply_modifier(player, modifier)

        return " ".join(
            [
                f"Use {item.name}: succeeded, "
                f"{self._name} is {injury_words(player.hit_points, player.max_hit_points)}.",
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
        return level_change_facts(self._name, before, player_status_effect_levels(player))

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

    def _resolve_zombie_attack(self, accepted: Accepted) -> tuple[list[str], int]:
        """Walk up to the zombie, then swing: the approach minutes come before the one swing."""
        target = accepted.expect(TargetZombie)
        facts: list[str] = []
        spent = 0
        if target.approach_minutes:
            motion = Motion(Pace.WALK, approach_target=target.zombie_id)
            spent, facts = self._spend(target.approach_minutes, accepted.action, motion=motion)
        if self._interruption or self.manager.narrative.game_over:
            return facts, spent
        swing = Motion(Pace.STILL, swing_target=target.zombie_id)
        swing_spent, swing_facts = self._spend(SWING_MIN, accepted.action, motion=swing)
        return [*facts, *swing_facts], spent + swing_spent

    def _resolve_attack(self, accepted: Accepted) -> str:
        npc = accepted.expect(TargetNpc).npc
        attacker = self.manager.player
        weapon = equipped_weapon(attacker) or UNARMED_WEAPON
        damage, modifiers = roll_damage(attacker, weapon, npc, self._rng)
        npc.hit_points -= damage
        self._apply_relationship_modifiers(modifiers)
        if isinstance(weapon, MeleeWeaponItem):
            self._skill_facts.extend(self.skill_engine.hit_xp(attacker, weapon))

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
            return f"{npc.name} now feels {disposition} toward {self._name}."
        relationships.adjust_trust(npc.npc_id, player_id, action.amount)
        trust = relationships.get_trust_level(npc.npc_id, player_id)
        return f"{npc.name}'s trust in {self._name} is now {trust}."

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
            return f"{self._name} waits {spent}, the most {self._subject} can at once."
        return f"{self._name} waits {spent}."

    def _resolve_sleep(self, accepted: Accepted) -> tuple[list[str], int]:
        """Sleep chunk by chunk until the time is up or something wakes the player."""
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
            lead = f"{self._name} sleeps {words}, the most {self._subject} can at once."
        else:
            lead = f"{self._name} sleeps {words}."
        return [lead, *facts, *([wake_fact] if wake_fact else [])], spent

    def _resolve_exercise(self, accepted: Accepted) -> tuple[list[str], int]:
        """Exercise minute by minute: the stats advance, then the minute's reps fire."""
        plan = accepted.expect(ExercisePlan)
        exercise = plan.exercise
        player = self.manager.player
        facts: list[str] = []
        spent = 0
        carry = 0.0
        done = 0
        stopped = False
        planned = action_minutes(accepted.action, plan)
        while spent < planned and not self.manager.narrative.game_over:
            advanced, stat_facts = self._spend(1, accepted.action)
            spent += advanced
            facts.extend(stat_facts)
            if self.manager.narrative.game_over:
                break
            carry += reps_per_minute(
                exercise, skill_levels(player)[skill_k.FITNESS], endurance_level(player)
            )
            reps = int(carry)
            carry -= reps
            done += reps
            for _ in range(reps):
                facts.extend(
                    self.exercise_engine.do_rep(player, exercise, self.manager.narrative.minutes)
                )
            if self._interruption:
                break
            if endurance_level(player) > ex_k.EXERCISE_ENDURANCE_STOP_LEVEL and spent < planned:
                stopped = True
                break
        if self.manager.narrative.game_over:
            return facts, spent
        if self._interruption:
            lead = f"You break off after {spent} minutes of {exercise.name.lower()}."
        elif stopped:
            lead = "You stop, too exhausted to go on."
        else:
            lead = f"You finish {spent} minutes of {exercise.name.lower()}."
        return [lead, f"{done} reps in all.", *facts], action_minutes(
            accepted.action, TimeSpan(spent, False)
        )

    def _waking(self, slept_minutes: int) -> str:
        """The fact for what wakes the player after this chunk, or "" if nothing does."""
        if self.manager.narrative.game_over:
            return ""
        player = self.manager.player
        if self._zombies_seen_this_chunk > 0 or self._interruption:
            panic = self._rng.uniform(
                survival.SLEEP_INTERRUPTION_PANIC_MIN, survival.SLEEP_INTERRUPTION_PANIC_MAX
            )
            player.stats.add(CharacterStat.PANIC, panic)
            return f"A zombie wakes {self._name} in a panic."
        stats = player.stats
        if status_effect_level(StatusEffect.HUNGRY, stats.get(CharacterStat.HUNGER)) >= (
            survival.SLEEP_WAKE_STATUS_EFFECT_LEVEL
        ):
            return f"Hunger wakes {self._name}."
        if status_effect_level(StatusEffect.THIRST, stats.get(CharacterStat.THIRST)) >= (
            survival.SLEEP_WAKE_STATUS_EFFECT_LEVEL
        ):
            return f"Thirst wakes {self._name}."
        if (
            stats.get(CharacterStat.FATIGUE) <= 0
            and slept_minutes >= survival.SLEEP_FATIGUE_WAKE_MIN_HOURS * 60
        ):
            return f"{self._name} wakes fully rested."
        return ""

    _RESOLVERS = {
        MoveAction: _resolve_move,
        StanceAction: _resolve_stance,
        TakeAction: _resolve_take,
        DropAction: _resolve_drop,
        WearAction: _resolve_wear,
        TakeOffAction: _resolve_take_off,
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
