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

import logging
import random
from collections.abc import Callable
from dataclasses import dataclass

from data import body as body_k
from data import exercises as ex_k
from data import melee as melee_k
from data import skills as skill_k
from data import status_effects, survival
from data import thermal as thermal_k
from data import zombie_lore as lore_k
from data.exercises import find_exercise
from data.npcs import TRUSTS_PLAYER, TRUSTS_PLAYER_BANDS
from data.story_beats import STORY_BEATS, Beat
from data.thermal import Metabolic
from data.time_costs import (
    MAX_PLAN_ACTIONS,
    MULTIPLIED_ACTIONS,
    NONE_TURN_MINUTES,
    SWING_MIN,
    WALK_TO_BARRIER_MIN,
    action_minutes,
    zone_hop_minutes,
)
from data.topics import TOPICS
from managers.body import BodyEngine, action_time_multiplier, limp_factor
from managers.climate import weather_change_facts
from managers.combat import equipped_weapon, held_slots, roll_damage
from managers.events import broadcast_event
from managers.exercise import ExerciseEngine, endurance_level, reps_per_minute
from managers.first_aid import FirstAid
from managers.game import DEATH_CAUSE_MAX_LENGTH, GameManager
from managers.noise import Sound, cough_sound
from managers.skills import SkillEngine, skill_levels
from managers.social import SocialManager
from managers.stats.drivers import StatContext
from managers.stats.engine import StatsEngine
from managers.stats.status_effects import (
    alcohol_intoxication,
    injury_words,
    level_change_fact_texts,
    level_change_facts,
    player_status_effect_levels,
    status_effect_level,
)
from managers.story import clock_minutes, holds
from managers.thermoregulator import attack_metabolic
from managers.validator import Accepted, ActionValidator, Rejected
from managers.zombies import PlayerMinute, ZombieLoop, enter_zone, start_outbreak
from modules.action.types import (
    AddGoalAction,
    AddRelationshipNoteAction,
    AnyAction,
    AskAction,
    AttackAction,
    ExerciseAction,
    GiveAction,
    MoveAction,
    RemoveGoalAction,
    ShoveAction,
    SleepAction,
    StanceAction,
    TalkAction,
    WaitAction,
)
from modules.action.words import describe_action
from modules.character.equipment import CharacterHoldableSlot
from modules.entity.player import PlayerEntity
from modules.event import (
    ApplyItemEvent,
    ConsumeItemEvent,
)
from modules.item import (
    AppliableItem,
    ClothingItem,
    ConsumableItem,
    HoldableItem,
    MedicalItem,
    MeleeWeaponItem,
)
from modules.modifier import (
    AffinityModifier,
    ConditionsModifier,
    ReputationModifier,
)
from modules.pace import Pace
from modules.quest import QuestStatus
from modules.resolution import (
    ExercisePlan,
    FirstAidTarget,
    HeldItem,
    MoveBlocked,
    MoveToSpot,
    MoveToZone,
    NpcItem,
    NpcTopic,
    ShuffleInZone,
    TargetNpc,
    TargetZombie,
    TimeSpan,
)
from modules.stats import CharacterStat, StatusEffect
from modules.story import (
    AddNpcStatus,
    DiscoverFlag,
    Effect,
    MoveNpc,
    RemoveNpcStatus,
    SetFlag,
    StartOutbreak,
)
from modules.weather import WeatherSample


def _span_words(minutes: int) -> str:
    hours, rest = divmod(minutes, 60)
    parts = []
    if hours:
        parts.append(f"{hours} hour{'s' if hours != 1 else ''}")
    if rest:
        parts.append(f"{rest} minute{'s' if rest != 1 else ''}")
    return " ".join(parts)


logger = logging.getLogger(__name__)

SOCIAL_ACTIONS = (TalkAction, AskAction, GiveAction)
TOO_MANY_ACTIONS_FACT = "Too much at once; {name} does the first five things."
INTERRUPTED_BY_ATTACK = "attacked"
INTERRUPTED_BY_BEAT = "story beat"
INTERRUPTED_BY_WEAKENING = "weakening"


@dataclass(frozen=True)
class Motion:
    """How the player moves during a span of minutes."""

    pace: Pace = Pace.STILL
    approach_target: str | None = None
    swing_target: str | None = None
    shove: bool = False


def _hurt_levels(player: PlayerEntity) -> tuple[int, int]:
    """The Injured and Bleeding status effect levels."""
    levels = player_status_effect_levels(player)
    return levels[StatusEffect.INJURED], levels[StatusEffect.BLEEDING]


def _got_worse(after: tuple[int, int], before: tuple[int, int]) -> bool:
    """True when either level rose, whatever the other one did."""
    return any(now > then for now, then in zip(after, before, strict=True))


def _minutes_fact(minutes: int) -> str:
    if minutes == 1:
        return "About 1 minute passes."
    return f"About {_span_words(minutes)} pass."


class SimulationCore:
    def __init__(
        self,
        manager: GameManager,
        validator: ActionValidator | None = None,
        rng: random.Random | None = None,
        beats: dict[str, Beat] | None = None,
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
        self._beats = beats if beats is not None else STORY_BEATS
        self._shouted = False
        self._spoke = False
        self._stated_minutes = 0
        self._social = SocialManager(manager, self._rng)
        self._body = BodyEngine(self._rng)
        self._first_aid = FirstAid(self._rng, self.skill_engine)

    @property
    def _name(self) -> str:
        return self.manager.player.appearance.forename

    @property
    def _subject(self) -> str:
        return self.manager.player.appearance.subject

    def resolve(self, actions: list[AnyAction], *, refused: int = 0) -> list[str]:
        """Validate and resolve each action in order, one at a time.

        Order matters within a turn: an earlier action can change whether a
        later one is legal (move into a room, then take something only
        reachable from there). Every action is therefore validated against
        state as it stands *after* every prior action in this same turn has
        already resolved -- never against one upfront snapshot of the whole
        list, which would reject "move north, take crowbar" because the
        crowbar wasn't reachable before the move happened.

        `refused` counts the lines the parser already refused: a turn with no
        actions and none of those is a `NONE` turn and costs a minute.
        """
        facts: list[str] = []
        total_minutes = 0
        self._shouted = False
        self._spoke = False
        self._stated_minutes = 0
        self._body.begin_turn()
        self.validator.begin_turn()
        if not actions and not refused:
            spent, stat_facts = self._spend(NONE_TURN_MINUTES)
            total_minutes += spent
            facts.extend(stat_facts)
        if len(actions) > MAX_PLAN_ACTIONS:
            facts.append(f"Refused: {TOO_MANY_ACTIONS_FACT.format(name=self._name)}")
        for index, action in enumerate(actions[:MAX_PLAN_ACTIONS]):
            result = self.validator.validate(action)
            if isinstance(result, Rejected):
                facts.append(
                    f"Refused: {self._name} can't {describe_action(result.action)}: {result.reason}"
                )
                continue
            self._interruption = ""
            action_facts, minutes = self._resolve_one(result)
            facts.extend(action_facts)
            total_minutes += minutes
            if not self.manager.narrative.game_over:
                facts.extend(self._after_action())
            if self._interruption:
                cancelled = [describe_action(a) for a in actions[index + 1 : MAX_PLAN_ACTIONS]]
                if cancelled:
                    facts.append(f"{self._name} never gets to: {', '.join(cancelled)}.")
                break
        if self._shouted and not total_minutes and not self.manager.narrative.game_over:
            spent, stat_facts = self._spend(NONE_TURN_MINUTES)
            total_minutes += spent
            facts.extend(stat_facts)
        if total_minutes and total_minutes != self._stated_minutes:
            facts.append(_minutes_fact(total_minutes))
        return facts

    def discover_flag(self, flag: str) -> str:
        """Mark a world flag as known to the player; returns any quest progress it caused."""
        narrative = self.manager.narrative
        narrative.flags.setdefault(flag, True)
        narrative.discovered_flags.add(flag)
        return self._advance_quests(f"discover:{flag}")

    def apply_story_effect(self, effect: Effect) -> str:
        """Apply an effect a story beat fires; returns any quest progress it caused."""
        manager = self.manager
        match effect:
            case StartOutbreak():
                start_outbreak(
                    manager.world,
                    manager.narrative.minutes,
                    manager.player.current_location_id,
                    self._rng,
                )
                self._loop.forget_visible()
            case SetFlag(flag=flag):
                manager.narrative.flags[flag] = True
            case DiscoverFlag(flag=flag):
                return self.discover_flag(flag)
            case MoveNpc(npc_id=npc_id, zone_id=zone_id):
                npc = manager.npcs.get(npc_id)
                zone = manager.world.locations.get(zone_id)
                if npc is None or zone is None:
                    logger.warning(f"Beat effect moves unknown NPC or zone: {npc_id}, {zone_id}.")
                else:
                    manager.move_npc(npc, zone)
            case AddNpcStatus(npc_id=npc_id, status=status):
                npc = manager.npcs.get(npc_id)
                if npc is not None and status not in npc.status:
                    npc.status.append(status)
                    return self._advance_quests(f"npc_status:{npc_id}:{status}")
            case RemoveNpcStatus(npc_id=npc_id, status=status):
                npc = manager.npcs.get(npc_id)
                if npc is not None and status in npc.status:
                    npc.status.remove(status)
        return ""

    def _fire_beats(self, *, clock_only: bool) -> list[str]:
        """Fire every unfired beat whose condition now holds.

        Beats with a clock condition are checked at minute boundaries (`clock_only`);
        after each resolved action every unfired beat is, which also catches a clock
        beat whose minute passed in a turn that spent no time.
        """
        manager = self.manager
        facts: list[str] = []
        for beat in self._beats.values():
            if beat.beat_id in manager.world.fired_beats:
                continue
            if (clock_only and not clock_minutes(beat.when)) or not holds(beat.when, manager):
                continue
            manager.world.fired_beats[beat.beat_id] = manager.narrative.minutes
            facts.append(beat.fact)
            for effect in beat.effects:
                note = self.apply_story_effect(effect)
                if note:
                    facts.append(note)
            if beat.interrupts:
                self._interruption = INTERRUPTED_BY_BEAT
        return facts

    def _next_clock_beat_in(self) -> int | None:
        """Minutes until the nearest unfired clock beat, or None."""
        now = self.manager.narrative.minutes
        due = [
            minute - now
            for beat in self._beats.values()
            if beat.beat_id not in self.manager.world.fired_beats
            for minute in clock_minutes(beat.when)
            if minute > now
        ]
        return min(due, default=None)

    def _derive_statuses(self) -> list[str]:
        """Recompute `trusts_player` from each NPC's trust band; returns quest progress facts."""
        facts: list[str] = []
        relationships = self.manager.relationship_manager
        player_id = self.manager.player.entity_id
        for npc in self.manager.npcs.values():
            band = relationships.get_trust_level(npc.npc_id, player_id)
            earned = band in TRUSTS_PLAYER_BANDS
            if earned and TRUSTS_PLAYER not in npc.status:
                npc.status.append(TRUSTS_PLAYER)
                note = self._advance_quests(f"npc_status:{npc.npc_id}:{TRUSTS_PLAYER}")
                if note:
                    facts.append(note)
            elif not earned and TRUSTS_PLAYER in npc.status:
                npc.status.remove(TRUSTS_PLAYER)
        return facts

    def _after_action(self) -> list[str]:
        return [*self._derive_statuses(), *self._fire_beats(clock_only=False)]

    def _action_time_multiplier(self) -> float:
        """Pain, mood and cold slow timed actions (spec 12)."""
        return action_time_multiplier(self.manager.player)

    def _hop_minutes(self, pace: Pace) -> int:
        """Minutes one zone hop takes at a pace, stretched by a limp (spec 12)."""
        factor = limp_factor(self.manager.player)
        return max(1, round(zone_hop_minutes(pace) / factor))

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
            talking=isinstance(action, SOCIAL_ACTIONS),
            resting=isinstance(action, WaitAction),
            exercising=isinstance(action, AttackAction | ShoveAction)
            or exerting
            or pace == Pace.RUN,
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
        if isinstance(action, ShoveAction):
            return attack_metabolic(None)
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
        span_levels = player_status_effect_levels(manager.player)
        self._zombies_seen_this_chunk = 0
        weakens = isinstance(action, WaitAction | SleepAction | ExerciseAction)
        while spent < minutes and not self._interruption:
            block = min(survival.MAX_CHUNK_MINUTES, minutes - spent)
            beat_in = self._next_clock_beat_in()
            if beat_in is not None:
                block = min(block, beat_in)
            before = player_status_effect_levels(manager.player)
            ran, seen, exerting, loop_facts = self._zombie_minutes(block, asleep, motion, weakens)
            facts.extend(loop_facts)
            self._zombies_seen_this_chunk += seen
            if manager.narrative.game_over:
                manager.climate.advance_to(manager.narrative.minutes + ran)
                manager.advance_clock(ran)
                return spent + ran, facts
            facts.extend(
                level_change_facts(self._name, before, player_status_effect_levels(manager.player))
            )
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
            facts.extend(self._fire_beats(clock_only=True))
            self._pending_sounds.extend(self._coughs(stat_facts))
        if not manager.narrative.game_over:
            facts.extend(self._run_ticks(started, spent, walking=isinstance(action, MoveAction)))
        return spent, self._net_level_facts(facts, span_levels)

    def _net_level_facts(self, facts: list[str], before: dict[StatusEffect, int]) -> list[str]:
        """The span's facts with its status-effect changes reported once each, at their final level."""
        level_facts = level_change_fact_texts(self._name)
        kept = [fact for fact in facts if fact not in level_facts]
        after = player_status_effect_levels(self.manager.player)
        return [*kept, *level_change_facts(self._name, before, after)]

    def _coughs(self, stat_facts: list[str]) -> list[Sound]:
        words = {
            thermal_k.COUGH_FACT.format(name=self._name),
            thermal_k.SNEEZE_FACT.format(name=self._name),
        }
        return [cough_sound() for fact in stat_facts if fact in words]

    def _zombie_minutes(
        self, block: int, asleep: bool, motion: Motion, weakens: bool
    ) -> tuple[int, int, bool, list[str]]:
        """Run up to `block` minutes of the zombie loop and the body; stops at an interruption or a death.

        `weakens` ends the span when the Injured or Bleeding level rises. Returns the minutes
        run, the zombies newly seen, whether a zombie attacked and the facts.
        """
        manager = self.manager
        player = manager.player
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
                shove=motion.shove,
            )
            sounds, self._pending_sounds = self._pending_sounds, []
            self._shouted = False
            worse = _hurt_levels(player)
            report = self._loop.run_minute(manager.narrative.minutes + ran, minute, sounds)
            ran += 1
            seen += report.new_seen
            exerting = exerting or report.attacked
            facts.extend(report.facts)
            if report.death_fact:
                facts.append(self._check_player_death(report.death_fact))
                break
            facts.extend(self._body.minute(player, (manager.narrative.minutes + ran) / 60))
            if self._body.death_fact:
                facts.append(self._check_player_death(self._body.death_fact))
                break
            if weakens and not report.interrupted and _got_worse(_hurt_levels(player), worse):
                self._interruption = INTERRUPTED_BY_WEAKENING
                facts.append(body_k.WEAKER_FACT.format(name=self._name))
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
        if isinstance(accepted.action, MoveAction):
            if accepted.action.run:
                self.manager.player.sneaking = False
            if isinstance(accepted.resolved, MoveToZone | MoveBlocked):
                return self._resolve_walk(accepted)
        handler = self._RESOLVERS.get(accepted.action.verb)
        if handler is None:
            return [f"No resolver registered for {accepted.action.verb}."], 0
        self._skill_facts = []
        slowdown = (
            self._action_time_multiplier()
            if isinstance(accepted.action, MULTIPLIED_ACTIONS)
            else 1.0
        )
        result = handler(self, accepted)
        if isinstance(result, tuple):
            return result
        lines = [result] if isinstance(result, str) else result
        minutes = action_minutes(accepted.action, accepted.resolved)
        if isinstance(accepted.action, MULTIPLIED_ACTIONS):
            minutes = max(1, round(minutes * slowdown))
        if isinstance(accepted.action, SOCIAL_ACTIONS):
            minutes = 0 if self._spoke else minutes
            self._spoke = True
        facts = [self._check_player_death(lines[0]), *lines[1:], *self._skill_facts]
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
        player = self.manager.player
        if narrative.game_over or player.hit_points > 0:
            return fact
        narrative.game_over = True
        if player.stats.get(CharacterStat.ZOMBIE_INFECTION) >= body_k.RISE_INFECTION_MIN:
            fact = f"{fact.removesuffix('.')}{body_k.ROSE_AGAIN_SUFFIX}"
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

    def _enter_zone(self, zone_id: str) -> None:
        """Put the player in a zone; every follower who was with them arrives at once."""
        manager = self.manager
        player = manager.player
        followers = [
            npc
            for npc in manager.npcs.values()
            if npc.following and npc.current_location_id == player.current_location_id
        ]
        player.current_location_id = zone_id
        player.current_place = ""
        for npc in followers:
            manager.move_npc(npc, manager.world.locations[zone_id])

    def _walk_hop(self, zone_id: str, action: AnyAction, pace: Pace) -> tuple[int, list[str]]:
        """One hop: the first minutes in the zone being left, the last one in the new zone.

        Before the outbreak nobody can tell, so the whole hop is spent in the new zone.
        """
        manager = self.manager
        player = manager.player
        motion = Motion(pace)
        hop = self._hop_minutes(pace)
        if not self._loop.active():
            self._enter_zone(zone_id)
            return self._spend(hop, action, motion=motion)
        spent, facts = self._spend(hop - 1, action, motion=motion)
        if self._interruption or manager.narrative.game_over:
            return spent, facts
        previous_id = player.current_location_id
        self._enter_zone(zone_id)
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
        fact = f"Take {entity.item.name}: succeeded."
        if isinstance(entity.item, ClothingItem):
            fact += f" {self._name} carries it; {self._subject} is not wearing it."
        return self._with_quest_note(fact, f"take:{entity.item.id}")

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

    def _resolve_use_item(self, accepted: Accepted) -> str | list[str]:
        manager = self.manager
        entity = accepted.expect(HeldItem).entity
        item = entity.item
        player = manager.player
        if isinstance(item, MedicalItem):
            if item.painkiller:
                return self._first_aid.take_pill(player, entity)
            return self._first_aid.take_antibiotic(player, entity)
        assert isinstance(item, ConsumableItem | AppliableItem), "_validate_use_item checks this"

        # The item's own effect is not a trait reaction -- it applies
        # unconditionally whenever the item is used, so it is applied
        # directly rather than through the broadcast.
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

        if isinstance(item, ConsumableItem):
            lead = f"Use {item.name}: succeeded."
        else:
            hurt = injury_words(player.hit_points, player.max_hit_points)
            lead = f"Use {item.name}: succeeded, {self._name} is {hurt}."
        return " ".join([lead, *consume_facts])

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

    # === Combat ===

    def _resolve_zombie_attack(self, accepted: Accepted) -> tuple[list[str], int]:
        """Walk up to the zombie, then swing: the approach minutes come before the one swing."""
        target = accepted.expect(TargetZombie)
        facts: list[str] = []
        spent = 0
        if target.approach_minutes:
            motion = Motion(Pace.WALK, approach_target=target.zombie_id)
            spent, facts = self._spend(target.approach_minutes, accepted.action, motion=motion)
        if self.manager.narrative.game_over:
            return facts, spent
        if self._interruption:
            return [*facts, f"{self._name} never gets to swing."], spent
        swing = Motion(
            Pace.STILL,
            swing_target=target.zombie_id,
            shove=isinstance(accepted.action, ShoveAction),
        )
        swing_spent, swing_facts = self._spend(SWING_MIN, accepted.action, motion=swing)
        return [*facts, *swing_facts], spent + swing_spent

    # === First aid ===

    def _resolve_bandage(self, accepted: Accepted) -> list[str]:
        target = accepted.expect(FirstAidTarget)
        assert target.entity is not None, "_validate_bandage checks this"
        return self._first_aid.bandage(self.manager.player, target.part, target.entity)

    def _resolve_remove_bandage(self, accepted: Accepted) -> list[str]:
        target = accepted.expect(FirstAidTarget)
        return self._first_aid.remove_bandage(self.manager.player, target.part)

    def _resolve_disinfect(self, accepted: Accepted) -> list[str]:
        target = accepted.expect(FirstAidTarget)
        assert target.entity is not None, "_validate_disinfect checks this"
        return self._first_aid.disinfect(self.manager.player, target.part, target.entity)

    def _resolve_equip(self, accepted: Accepted) -> str:
        player = self.manager.player
        entity = accepted.expect(HeldItem).entity
        item = entity.item
        assert isinstance(item, HoldableItem), "_validate_equip checks this"
        player.inventory.remove(entity)
        for slot in held_slots(item):
            player.equipment[slot] = entity
        return melee_k.EQUIP_FACT.format(name=self._name, item=item.name.lower())

    def _resolve_unequip(self, accepted: Accepted) -> str:
        player = self.manager.player
        entity = accepted.expect(HeldItem).entity
        for slot in CharacterHoldableSlot:
            if player.equipment[slot] is entity:
                player.equipment[slot] = None
        player.inventory.append(entity)
        return melee_k.UNEQUIP_FACT.format(name=self._name, item=entity.item.name.lower())

    def _resolve_attack(self, accepted: Accepted) -> str | tuple[list[str], int]:
        if isinstance(accepted.resolved, TargetZombie):
            return self._resolve_zombie_attack(accepted)
        npc = accepted.expect(TargetNpc).npc
        attacker = self.manager.player
        weapon = equipped_weapon(attacker) or melee_k.BARE_HANDS
        damage, modifiers = roll_damage(attacker, weapon, npc, self._rng)
        npc.hit_points -= damage
        self._apply_relationship_modifiers(modifiers)
        if isinstance(weapon, MeleeWeaponItem):
            self._skill_facts.extend(self.skill_engine.hit_xp(attacker, weapon, 0.0, 1))

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
        if isinstance(modifier, ConditionsModifier):
            for condition, active in modifier.conditions.items():
                if active and condition not in entity.conditions:
                    entity.conditions.append(condition)
                elif not active and condition in entity.conditions:
                    entity.conditions.remove(condition)
        elif isinstance(modifier, AffinityModifier):
            self.manager.relationship_manager.apply_affinity_modifier(modifier)
        elif isinstance(modifier, ReputationModifier):
            self.manager.relationship_manager.apply_reputation_modifier(modifier)

    # === Talking to people ===

    def _resolve_talk(self, accepted: Accepted) -> list[str]:
        action = accepted.action
        assert isinstance(action, TalkAction)
        npc = accepted.expect(TargetNpc).npc
        self.validator.note_talked(npc.npc_id)
        return self._social.talk(npc, action.approach)

    def _resolve_give(self, accepted: Accepted) -> list[str]:
        gift = accepted.expect(NpcItem)
        return self._social.give(gift.entity, gift.npc)

    def _resolve_ask(self, accepted: Accepted) -> list[str]:
        action = accepted.action
        assert isinstance(action, AskAction)
        match action.request:
            case "follow":
                return self._social.ask_follow(accepted.expect(TargetNpc).npc)
            case "stay":
                return self._social.ask_stay(accepted.expect(TargetNpc).npc)
            case "give":
                request = accepted.expect(NpcItem)
                return self._social.ask_give(request.npc, request.entity)
            case "about":
                asked = accepted.expect(NpcTopic)
                facts, flag = self._social.ask_about(asked.npc, TOPICS[asked.topic_id])
                note = self.discover_flag(flag) if flag else ""
                return [*facts, *([note] if note else [])]
        return [f"{self._name} asks about something, and nothing comes of it."]

    # === Noise ===

    def _resolve_shout(self, accepted: Accepted) -> str:
        """A shout is a world sound; the zombie loop hears it in the next minute it runs."""
        radius, volume = (
            (lore_k.SHOUT_SNEAK_RADIUS, lore_k.SHOUT_SNEAK_VOLUME)
            if self.manager.player.sneaking
            else (lore_k.SHOUT_RADIUS, lore_k.SHOUT_VOLUME)
        )
        self._pending_sounds.append(Sound(radius=radius, volume=volume))
        self._shouted = True
        return f"{self._name} shouts."

    # === World state (goals / relationships) ===

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

    def _resolve_add_relationship_note(self, accepted: Accepted) -> str:
        action: AddRelationshipNoteAction = accepted.action
        npc = accepted.expect(TargetNpc).npc
        npc.notes = f"{npc.notes}; {action.note}" if npc.notes else action.note
        return f"Noted about {npc.name}: {action.note}"

    def _resolve_wait(self, accepted: Accepted) -> tuple[list[str], int]:
        """Wait out the span; the lead fact gives the minutes that actually passed."""
        span = accepted.expect(TimeSpan)
        spent, facts = self._spend(span.minutes, accepted.action)
        words = _span_words(spent)
        if spent < span.minutes and (self._interruption or self.manager.narrative.game_over):
            lead = f"{self._name} waits {words}, then is interrupted."
        elif span.clamped:
            lead = f"{self._name} waits {words}, the most {self._subject} can at once."
        else:
            lead = f"{self._name} waits {words}."
        self._stated_minutes += spent
        return [lead, *facts], spent

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
        self._stated_minutes += spent
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
        if self._interruption == INTERRUPTED_BY_BEAT:
            return f"{self._name} is startled awake."
        zombie_woke = self._interruption not in ("", INTERRUPTED_BY_WEAKENING)
        if self._zombies_seen_this_chunk > 0 or zombie_woke:
            panic = self._rng.uniform(
                survival.SLEEP_INTERRUPTION_PANIC_MIN, survival.SLEEP_INTERRUPTION_PANIC_MAX
            )
            player.stats.add(CharacterStat.PANIC, panic)
            return f"A zombie wakes {self._name} in a panic."
        if self._interruption == INTERRUPTED_BY_WEAKENING or not player.asleep:
            return f"{self._name} wakes, badly hurt."
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

    _RESOLVERS: dict[
        str, Callable[["SimulationCore", Accepted], str | list[str] | tuple[list[str], int]]
    ] = {
        "MOVE_TO": _resolve_move,
        "STANCE": _resolve_stance,
        "TAKE": _resolve_take,
        "DROP": _resolve_drop,
        "WEAR": _resolve_wear,
        "TAKE_OFF": _resolve_take_off,
        "ATTACK": _resolve_attack,
        "SHOVE": _resolve_zombie_attack,
        "EQUIP": _resolve_equip,
        "UNEQUIP": _resolve_unequip,
        "USE_ITEM": _resolve_use_item,
        "BANDAGE": _resolve_bandage,
        "REMOVE_BANDAGE": _resolve_remove_bandage,
        "DISINFECT": _resolve_disinfect,
        "WAIT": _resolve_wait,
        "SLEEP": _resolve_sleep,
        "EXERCISE": _resolve_exercise,
        "SHOUT": _resolve_shout,
        "TALK": _resolve_talk,
        "ASK": _resolve_ask,
        "GIVE": _resolve_give,
        "ADD_GOAL": _resolve_add_goal,
        "REMOVE_GOAL": _resolve_remove_goal,
        "ADD_RELATIONSHIP_NOTE": _resolve_add_relationship_note,
    }
