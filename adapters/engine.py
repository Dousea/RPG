"""Orchestrates one game turn: recall -> parse -> validate -> simulate -> narrate -> persist.

Two LLM calls, not one: the parser proposes actions from player input before
anything is decided, the engine validates and simulates them, and only then
does the narrator describe what already happened. See
docs/architecture/engine-authority.md.
"""

import logging
import threading
from collections.abc import Callable, Sequence
from dataclasses import asdict, dataclass, field
from typing import Any

import config
from adapters import llm
from adapters.factcheck import FactChecker
from adapters.lore_index import LoreIndex
from adapters.memory import DEFAULT_RECALL, SemanticMemory
from adapters.save import codec, files
from data.character.occupations import OCCUPATIONS
from data.character.skills import SKILLS
from data.character.traits import TRAITS
from data.items import item_condition_word, wetness_word
from data.story import check as story_check_k
from data.story import mentions as mention_k
from data.story.memory import BUDGET_MARGIN_TOKENS
from managers import carry, naming
from managers.body.first_aid import part_word
from managers.body.health import open_wounds
from managers.body.stats.status_effects import active_status_effects, player_status_effect_levels
from managers.character import creation
from managers.character.skills import skill_progress
from managers.combat import weapons
from managers.combat.aim import aimed
from managers.context import NOTHING_DONE_FACT, ContextBuilder
from managers.corpses.search import corpse_views
from managers.events.log import build_event_entry, event_stamp
from managers.game import MAX_RECENT_EVENTS, GameManager
from managers.mentions import labels, mentionables, picked
from managers.plan import OpenChoice, bind_choices, open_choices, steps_in_this_scene, steps_of
from managers.simulation import SimulationCore, TurnRun
from managers.story.check import StateQuestion, build_questions, plan_questions, reach_question
from managers.story.lore import LoreHit, record_turn, select_lore
from managers.world import item_ids
from managers.world.barriers import barriers_of, state_word
from managers.world.climate import scene_weather, weather_summary
from managers.world.rooms import current_room
from managers.world.scenes import setting_word
from managers.zombies.population import threat_views
from modules.action.choices import Candidate
from modules.action.pins import Mention, bind, pinned_ids, render_input
from modules.action.types import AnyAction, UnsupportedAction
from modules.action.words import describe_action, refusal_in_words
from modules.body.stats import StatusEffect
from modules.character.build import CharacterBuild
from modules.character.equipment import CharacterHoldableSlot
from modules.character.skills import SkillState
from modules.entity.item import ItemEntity
from modules.entity.npc import NpcEntity
from modules.entity.player import PlayerEntity
from modules.item import MedicalItem, MeleeWeaponItem, StackItem
from modules.story.quest import QuestStatus
from modules.world.weather import WeatherSample

logger = logging.getLogger(__name__)

CORRECTION_BLOCK = (
    "\n\n[CORRECTION]\nYour last story got these facts wrong. "
    "Write the story again so it agrees with them and with every outcome:\n{facts}\n"
)
OPTIONS_BLOCK = (
    "\n\n[STORY WRITTEN]\nYou already wrote this turn's story, below. Reply with only "
    "its OPTIONS section.\n{story}\n"
)


# Called with each event of a turn as it happens: {"type": "step", "step": ...}
# for each stage, {"type": "thinking", "text": ...} for each piece of the
# narrator's thinking, {"type": "story", "text": ...} with the story so far.
TurnListener = Callable[[dict[str, Any]], None]


def _ignore(_event: dict[str, Any]) -> None:
    pass


@dataclass
class _Check:
    """What the plan check made of one parsed plan.

    `dropped` holds each flagged action with its place in the parsed plan and its refusal; `kept_at`
    the place of each kept action. `cut` says the plan's tail after a predicted zone change was left out.
    """

    kept: list[AnyAction]
    kept_at: list[int]
    dropped: list[tuple[int, AnyAction, str]]
    cut: bool


@dataclass
class _Round:
    """A `_Check` tied to the plan the core ran, so a refusal can be told from one that falls after the real zone change."""

    plan: list[AnyAction]
    check: _Check

    def refused_before(self, change: AnyAction | None) -> list[tuple[AnyAction, str]]:
        """The flagged actions parsed before `change`, the action that really changed zone (all of them when none did)."""
        at = next((i for i, action in enumerate(self.plan) if action is change), None)
        if change is None or at is None:
            return [(action, fact) for _, action, fact in self.check.dropped]
        limit = self.check.kept_at[at]
        return [(action, fact) for place, action, fact in self.check.dropped if place < limit]

    def _pending_at(self, pending: list[AnyAction]) -> int:
        start = next(i for i, action in enumerate(self.plan) if action is pending[0])
        return self.check.kept_at[start]

    def refused_before_pending(self, pending: list[AnyAction]) -> list[tuple[AnyAction, str]]:
        """The flagged actions parsed before the actions still to run; the later ones wait for the resumed run."""
        limit = self._pending_at(pending)
        return [(action, fact) for place, action, fact in self.check.dropped if place < limit]

    def resumed(self, pending: list[AnyAction]) -> _Check:
        """The check for the actions still to run, holding the flagged ones that come after them."""
        limit = self._pending_at(pending)
        start = self.check.kept_at.index(limit)
        return _Check(
            pending,
            self.check.kept_at[start : start + len(pending)],
            [entry for entry in self.check.dropped if entry[0] > limit],
            self.check.cut,
        )


@dataclass
class _Turn:
    """A turn's plan on its way to the run, kept in memory while the player settles an open choice (never saved).

    `typed` is the player's text with a mark where each pick stands, kept so the part after a zone change can
    be parsed again; `plan` is what is still to run, `done` what already ran; `spent` holds the ids of the picks
    the actions already placed or dropped.
    """

    typed: str
    player_input: str
    picks: list[Mention]
    plan: list[AnyAction]
    nothing_parsed: bool
    refused: int
    extra_facts: list[str]
    spent: set[str]
    check: _Check | None = None
    done: list[AnyAction] = field(default_factory=list[AnyAction])
    choices: list[OpenChoice] = field(default_factory=list[OpenChoice])


def _story_listener(emit: TurnListener) -> llm.DeltaCallback:
    """Turns the narrator's streamed pieces into thinking events and story-so-far events."""
    written: list[str] = []
    shown = [""]

    def on_delta(kind: str, text: str) -> None:
        if kind == "thinking":
            emit({"type": "thinking", "text": text})
            return
        written.append(text)
        preview = llm.story_preview("".join(written))
        if preview != shown[0]:
            shown[0] = preview
            emit({"type": "story", "text": preview})

    return on_delta


class GameEngine:
    """Owns the live GameManager and everything around it.

    Flask's dev server is threaded, so two overlapping requests would otherwise
    interleave mutations of the same GameManager and race on the save file. All
    state transitions are therefore serialized behind one lock.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.memory = SemanticMemory()
        self.lore_index = LoreIndex(self.memory)
        self.factcheck = FactChecker()
        self.manager: GameManager | None = files.load()
        self._kept: _Turn | None = None
        self.memory.rebuild(self.manager.memory.full_event_log if self.manager else [])

    @property
    def has_game(self) -> bool:
        return self.manager is not None

    @property
    def has_plan(self) -> bool:
        """Whether a plan waits for the player to settle its open choices."""
        return self._kept is not None

    @property
    def game(self) -> GameManager:
        """The running game; only for callers that know one exists."""
        if self.manager is None:
            raise RuntimeError("No game is running: create a character first.")
        return self.manager

    @staticmethod
    def _narrator_budget() -> int:
        """Characters the narrator's user prompt may take: the context less reply, margin and system prompt."""
        prompt_tokens = (
            config.llm.context_tokens - config.llm.narrator_max_tokens - BUDGET_MARGIN_TOKENS
        )
        return int(prompt_tokens * llm.chars_per_token()) - len(llm.NARRATOR_SYSTEM_PROMPT)

    # === Turn execution ===

    def play(
        self,
        player_input: str,
        on_event: TurnListener | None = None,
        mentions: Sequence[str] = (),
    ) -> dict[str, Any]:
        """Run a full turn and return the payload the frontend renders.

        `on_event` hears each step of the turn as it starts, and the narrator's
        thinking and story as they are written; the returned payload is the
        same either way. `mentions` are the ids the player picked from the `@`
        list, in the order their marks stand in `player_input`: one no longer
        in reach refuses the turn before any LLM call, and the rest are pinned
        into the parsed actions.
        """
        emit = on_event or _ignore
        with self._lock:
            manager = self.manager
            self._kept = None
            if manager is None:
                return self._snapshot(story_text="")

            if manager.narrative.game_over:
                # The character is already dead -- no parser, no narrator, no save.
                # The turn that killed them already recorded and persisted
                # everything there was to record; nothing after that is a
                # real turn anymore.
                return self._snapshot(
                    story_text=(
                        f"{manager.player.appearance.forename} is dead. "
                        f"{manager.narrative.death_cause}\n"
                        "Start a new game to play again."
                    )
                )

            picks, gone = picked(manager, mentions)
            if gone:
                return self._snapshot(story_text=mention_k.NO_LONGER_IN_REACH)
            typed = player_input
            player_input = render_input(typed, picks, for_parser=False)
            logger.debug(
                "Turn start: input=%r picks=%s minute=%s (%s %s) zone=%s",
                player_input,
                [pick.id for pick in picks],
                manager.narrative.minutes,
                manager.world.date,
                manager.world.time,
                manager.player.current_location_id,
            )

            # 1. Ask the parser what the player is trying to do. No prose exists yet.
            try:
                actions, parse_failures = self._parsed(manager, typed, picks, emit)
            except llm.LLMError as exc:
                return self._snapshot(story_text=f"--- SYSTEM ERROR ---\n{exc}")
            _trace_plan("Parsed plan", actions)
            aimed_actions = aimed(actions, player_input)
            _trace_rewrites(actions, aimed_actions)
            actions = aimed_actions
            checked = self._checked_plan(manager, player_input, actions, emit)
            looks = manager.player.appearance
            for failure in parse_failures:
                logger.warning(f"Unparseable action '{failure.raw}': {failure.reason}")
            turn = _Turn(
                typed=typed,
                player_input=player_input,
                picks=picks,
                plan=checked.kept,
                nothing_parsed=not actions and not parse_failures,
                refused=len(parse_failures) + len(checked.dropped),
                extra_facts=[
                    refusal_in_words(f, looks.forename, looks.subject) for f in parse_failures
                ],
                spent=set(),
                check=checked,
            )

            # 2. A target that fits several things is asked about before anything runs.
            turn.choices = open_choices(manager, checked.kept, player_input)
            if turn.choices:
                _trace_choices(turn.choices)
                self._kept = turn
                return self._snapshot(story_text="")
            return self._run(manager, turn, emit)

    def go(self, answers: Sequence[str], on_event: TurnListener | None = None) -> dict[str, Any]:
        """Run the kept plan with `answers` (one candidate id per open choice, in order), or refuse them in words.

        A refusal drops the plan and spends no time; the run is the plan's one narrator call.
        """
        emit = on_event or _ignore
        with self._lock:
            manager = self.manager
            turn, self._kept = self._kept, None
            if manager is None:
                return self._snapshot(story_text="")
            if turn is None or manager.narrative.game_over:
                return self._snapshot(story_text=mention_k.NO_PLAN_WAITING)
            now = open_choices(manager, turn.plan, turn.player_input)
            answered = self._answered(turn.choices, now, answers)
            if answered is None:
                return self._snapshot(story_text=mention_k.ANSWER_NOT_ON_OFFER)
            logger.debug(
                "Plan screen picks: %s",
                [
                    (choice.index, choice.attr, pick.id)
                    for choice, pick in zip(now, answered, strict=True)
                ],
            )
            turn.plan = bind_choices(turn.plan, now, answered)
            turn.choices = []
            return self._run(manager, turn, emit)

    def cancel_plan(self) -> dict[str, Any]:
        """Drop the plan that waits for an answer."""
        with self._lock:
            self._kept = None
            return self._snapshot(story_text="")

    @staticmethod
    def _answered(
        asked: list[OpenChoice], now: list[OpenChoice], answers: Sequence[str]
    ) -> list[Candidate] | None:
        """The candidate each answer names, or None when the choices changed or an answer is not among theirs."""
        if now != asked or len(answers) != len(now):
            return None
        found: list[Candidate] = []
        for choice, answer in zip(now, answers, strict=True):
            candidate = next((c for c in choice.candidates if c.id == answer), None)
            if candidate is None:
                return None
            found.append(candidate)
        return found

    def _run(self, manager: GameManager, turn: _Turn, emit: TurnListener) -> dict[str, Any]:
        """Validate and simulate `turn`'s plan, narrate it and record it; a plan that meets an unclear target pauses and is kept."""
        player_input = turn.player_input
        looks = manager.player.appearance

        # 1. Recall semantically relevant past events (for the narrator).
        indices = self.memory.search(player_input, DEFAULT_RECALL + MAX_RECENT_EVENTS)
        deep_memories = [
            entry
            for i in indices
            if i < len(manager.memory.full_event_log)
            and (entry := manager.memory.full_event_log[i]) not in manager.memory.recent_events
        ][:DEFAULT_RECALL]
        logger.debug(f"Recalled {len(deep_memories)} deep memories.")
        lore_scores = self.lore_index.scores(player_input)

        stamp = event_stamp(manager)
        minutes_before = manager.narrative.minutes

        # 2. Validate and simulate, one action at a time in order. This is
        # where the engine decides what happens -- before the narrator
        # writes a single word about it. A plan that changes zone is parsed
        # once more from the destination.
        core = SimulationCore(manager)
        later_failures: list[llm.ParseFailure] = []
        first = turn.check or _Check(turn.plan, list(range(len(turn.plan))), [], False)
        rounds = [_Round(turn.plan, first)]
        turn.check = None

        def reparse(done: list[str], tried: list[AnyAction]) -> list[AnyAction] | None:
            moved_by = tried[-1]
            bound = (
                turn.spent
                | pinned_ids(tried)
                | pinned_ids([action for action, _ in rounds[0].refused_before(moved_by)])
            )
            unbound = [pick for pick in turn.picks if pick.id not in bound]
            before = [describe_action(action) for action in turn.done]
            try:
                more, failures = self._parsed(
                    manager, turn.typed, turn.picks, emit, [*before, *done], unbound
                )
            except llm.LLMError as exc:
                logger.warning(f"Parser failed on the rest of the plan: {exc}")
                return None
            later_failures.extend(failures)
            _trace_plan("Re-parsed plan at the destination", more)
            aimed_more = aimed(more, player_input)
            _trace_rewrites(more, aimed_more)
            checked = self._checked_plan(manager, player_input, aimed_more, emit)
            rounds.append(_Round(checked.kept, checked))
            return checked.kept

        run = core.run_turn(turn.plan, refused=turn.refused, reparse=reparse)
        last = run.legs[-1]
        refused_actions = [action for action, _ in run.refused]
        outcome_facts = list(run.facts)
        for failure in later_failures:
            logger.warning(f"Unparseable action '{failure.raw}': {failure.reason}")
            outcome_facts.append(refusal_in_words(failure, looks.forename, looks.subject))
        paused = last.asked is not None and not manager.narrative.game_over
        refused_in_scene: list[tuple[AnyAction, str]] = []
        rest_unreached = run.rest_unreached
        for number, rnd in enumerate(rounds):
            change = run.legs[number].moved_by if number < len(run.legs) else None
            if paused and rnd is rounds[-1]:
                refused_in_scene.extend(rnd.refused_before_pending(list(last.pending)))
                turn.check = rnd.resumed(list(last.pending))
            else:
                refused_in_scene.extend(rnd.refused_before(change))
            if rnd.check.cut and change is None and last.asked is None:
                rest_unreached = not manager.narrative.game_over
        outcome_facts.extend([*turn.extra_facts, *(fact for _, fact in refused_in_scene)])
        logger.debug("Outcome facts: %s", outcome_facts)
        turn.done.extend(run.done)
        turn.spent |= pinned_ids(run.tried) | pinned_ids([a for a, _ in refused_in_scene])
        if paused:
            turn.plan, turn.extra_facts, turn.refused = list(last.pending), [], 0
            turn.nothing_parsed = False
            turn.choices = open_choices(manager, turn.plan, turn.player_input)
            _trace_choices(turn.choices)
            self._kept = turn

        # 3. Ask the narrator to describe what already happened. A turn the
        # parser found nothing in would otherwise be narrated as the input.
        narrated_facts = outcome_facts
        if turn.nothing_parsed:
            narrated_facts = [NOTHING_DONE_FACT.format(name=looks.forename), *outcome_facts]
        if rest_unreached:
            narrated_facts = [
                *narrated_facts,
                mention_k.REST_NOT_REACHED_FACT.format(name=looks.forename),
            ]
        context = ContextBuilder(manager)
        lore = select_lore(manager, player_input, lore_scores)
        narrator_prompt = context.build_narrator_prompt(
            player_input,
            narrated_facts,
            deep_memories,
            max_chars=self._narrator_budget(),
            refused=refused_actions,
            finds=run.finds,
            lore=lore,
        )
        logger.debug("Narrated facts: %s", narrated_facts)
        emit({"type": "step", "step": "narrating"})
        try:
            raw_response = llm.query_narrator(narrator_prompt, on_delta=_story_listener(emit))
        except llm.LLMError as exc:
            # Unlike a parser failure, real state changes may already
            # exist here -- the engine decided them before asking for
            # prose, and a rendering failure must not discard engine
            # truth. Record the same entry a narrated turn would and
            # persist, so state and disk agree even though nothing was
            # narrated.
            manager.record_event(build_event_entry(manager, stamp, player_input, outcome_facts))
            manager.memory.last_story = ""
            self.memory.rebuild(manager.memory.full_event_log)
            files.save(manager)
            return self._snapshot(story_text=f"--- SYSTEM ERROR ---\n{exc}")

        parsed = self._reply(raw_response)
        questions = build_questions(
            manager,
            narrated_facts,
            [(describe_action(action), reason) for action, reason in run.refused],
            bool(run.finds),
        )
        parsed = self._fact_checked(
            parsed,
            context,
            player_input,
            narrated_facts,
            deep_memories,
            questions,
            emit,
            run,
            lore,
        )
        parsed = self._with_options(
            parsed, context, player_input, narrated_facts, deep_memories, emit, run, lore
        )
        record_turn(manager, lore)
        story_text = str(parsed["story"])
        options = list(parsed["options"])
        entry = build_event_entry(manager, stamp, player_input, outcome_facts)

        # 4. Record the event in both memory tiers and reindex.
        emit({"type": "step", "step": "saving"})
        manager.record_event(entry)
        manager.memory.last_story = story_text
        self.memory.rebuild(manager.memory.full_event_log)

        # 5. Summarize if enough history has built up.
        self._run_summarization(manager)

        files.save(manager)
        logger.debug(
            "Turn end: minute %s -> %s, %s minutes spent, zone=%s",
            minutes_before,
            manager.narrative.minutes,
            manager.narrative.minutes - minutes_before,
            manager.player.current_location_id,
        )
        return self._snapshot(story_text=story_text, options=options)

    def _parsed(
        self,
        manager: GameManager,
        typed: str,
        picks: list[Mention],
        emit: TurnListener,
        done: list[str] | None = None,
        to_bind: list[Mention] | None = None,
    ) -> tuple[list[AnyAction], list[llm.ParseFailure]]:
        """Ask the parser for the plan in the scene as it stands, with the player's picks pinned into it.

        `typed` is the player's text with a mark where each pick stands; `done` is what this turn
        already did. `to_bind` is the part of `picks` still to pin (all of them by default).
        """
        context = ContextBuilder(manager)
        emit({"type": "step", "step": "parsing"})
        prompt = context.build_parser_prompt(
            render_input(typed, picks, for_parser=True), done or (), picks
        )
        logger.debug("Parser prompt is %d characters", len(prompt))
        actions, failures = llm.read_parser_reply(
            llm.query_parser(prompt, context.build_plan_schema())
        )
        return bind(actions, picks if to_bind is None else to_bind), failures

    def _checked_plan(
        self,
        manager: GameManager,
        player_input: str,
        actions: list[AnyAction],
        emit: TurnListener,
    ) -> _Check:
        """The actions the decision model doesn't rule out, the ones it does, and a refusal fact for each of those.

        Only the actions up to the plan's first predicted zone change are asked about and kept:
        the ones after it were parsed in the wrong scene. An `UNSUPPORTED` action is always kept,
        with the reason the model picks for refusing it.
        """
        steps = steps_in_this_scene(manager, actions)
        cut = steps < len(actions)
        actions = actions[:steps]
        if not actions or not self.factcheck.enabled:
            return _Check(actions, list(range(len(actions))), [], cut)
        emit({"type": "step", "step": "checking_plan"})
        self._give_reasons(manager, player_input, actions)
        asked = [i for i, action in enumerate(actions) if not isinstance(action, UnsupportedAction)]
        questions = plan_questions(manager, [actions[i] for i in asked])
        conflicts = self.factcheck.plan_conflicts(player_input, questions)
        flagged = {asked[i] for i in conflicts}
        correction = {asked[i]: questions[i].correction for i in conflicts}
        for index in sorted(flagged):
            logger.warning(f"Dropped {actions[index]!r}: not what the player asked for.")
        logger.debug("Plan check dropped %s of %s actions", len(flagged), len(actions))
        kept_at = [index for index in range(len(actions)) if index not in flagged]
        dropped = [(index, actions[index], correction[index]) for index in sorted(flagged)]
        return _Check([actions[index] for index in kept_at], kept_at, dropped, cut)

    def _give_reasons(
        self, manager: GameManager, player_input: str, actions: list[AnyAction]
    ) -> None:
        """Sets the reason each `UNSUPPORTED` action is refused for, from what the model picks."""
        verbs = ContextBuilder(manager).available_actions_section(without="UNSUPPORTED")
        for action in actions:
            if not isinstance(action, UnsupportedAction):
                continue
            answer = self.factcheck.plan_answer(
                player_input, reach_question(manager, action, verbs)
            )
            key = "none"
            if answer is not None and answer[1] >= config.factcheck.conflict_threshold:
                key = answer[0]
            action.reason = story_check_k.UNSUPPORTED_REASONS.get(
                key, story_check_k.UNSUPPORTED_DEFAULT_REASON
            )
            logger.debug(f"Refusing {action.text!r} as {key}: {action.reason}")

    def _fact_checked(
        self,
        parsed: dict[str, Any],
        context: ContextBuilder,
        player_input: str,
        outcome_facts: list[str],
        deep_memories: list[str],
        questions: list[StateQuestion],
        emit: TurnListener,
        run: TurnRun,
        lore: list[LoreHit],
    ) -> dict[str, Any]:
        """The narrator's reply, or its one retry when the story conflicts with the engine's state.

        The retry replaces the first reply only if it conflicts on no more
        questions; the facts themselves never change.
        """
        if not questions:
            return parsed
        if self.factcheck.enabled:
            emit({"type": "step", "step": "fact_checking"})
        name = context.manager.player.appearance.forename
        conflicts = self.factcheck.conflicts(str(parsed["story"]), questions, name)
        if not conflicts:
            return parsed
        logger.warning(f"Story conflicts with the engine: {conflicts}")
        block = CORRECTION_BLOCK.format(facts="\n".join(conflicts))
        retry_prompt = (
            context.build_narrator_prompt(
                player_input,
                outcome_facts,
                deep_memories,
                max_chars=self._narrator_budget() - len(block),
                refused=[action for action, _ in run.refused],
                finds=run.finds,
                lore=lore,
            )
            + block
        )
        emit({"type": "step", "step": "rewriting"})
        try:
            retry = self._reply(
                llm.query_narrator(
                    retry_prompt, on_delta=_story_listener(emit), purpose="narrator retry"
                )
            )
        except llm.LLMError as exc:
            logger.warning(f"Narrator retry failed, keeping the first story: {exc}")
            return parsed
        if retry["story"] == llm.EMPTY_STORY:
            logger.warning("Narrator retry has no story, keeping the first story.")
            return parsed
        retry_conflicts = self.factcheck.conflicts(str(retry["story"]), questions, name)
        return retry if len(retry_conflicts) <= len(conflicts) else parsed

    def _with_options(
        self,
        parsed: dict[str, Any],
        context: ContextBuilder,
        player_input: str,
        outcome_facts: list[str],
        deep_memories: list[str],
        emit: TurnListener,
        run: TurnRun,
        lore: list[LoreHit],
    ) -> dict[str, Any]:
        """The reply, with options from one follow-up call when it had no OPTIONS section.

        A turn that ended the game is left without options; the story never changes.
        """
        if parsed["has_options"] or context.manager.narrative.game_over:
            return parsed
        logger.warning("Narrator reply has no OPTIONS section; asking for the options alone.")
        emit({"type": "step", "step": "options"})
        block = OPTIONS_BLOCK.format(story=parsed["story"])
        prompt = (
            context.build_narrator_prompt(
                player_input,
                outcome_facts,
                deep_memories,
                max_chars=self._narrator_budget() - len(block),
                refused=[action for action, _ in run.refused],
                finds=run.finds,
                lore=lore,
            )
            + block
        )
        try:
            reply = llm.query_narrator(prompt, purpose="narrator options")
        except llm.LLMError as exc:
            logger.warning(f"Options follow-up failed, leaving the turn without options: {exc}")
            return parsed
        return {**parsed, "options": llm.parse_narrator_response(reply)["options"]}

    @staticmethod
    def _reply(raw_response: str) -> dict[str, Any]:
        """The narrator's parsed reply, noting whether it wrote an OPTIONS section."""
        return {
            **llm.parse_narrator_response(raw_response),
            "has_options": llm.has_options_section(raw_response),
        }

    def _run_summarization(self, manager: GameManager) -> None:
        """Fold the oldest unsummarized events into a narrative paragraph."""
        pending = manager.events_pending_summary()
        if not pending:
            return
        try:
            summary = llm.query_summary("\n".join(pending))
        except llm.LLMError as exc:
            # Not fatal: the turn stands, we just try again next turn.
            logger.warning(f"Summarization skipped: {exc}")
            return
        manager.memory.summaries.append(summary)
        logger.info(f"Added summary #{len(manager.memory.summaries)}.")

    # === Lifecycle ===

    def reset(self) -> dict[str, Any]:
        """Discard the save; no game runs until a character is created."""
        with self._lock:
            files.delete()
            self.manager = None
            self._kept = None
            self.memory.rebuild([])
            return self._snapshot(story_text="")

    def create_character(self, build: CharacterBuild) -> tuple[list[str], dict[str, Any] | None]:
        """Validate a build and start a new game from it.

        Returns the refusal messages (and no snapshot) for an invalid build, else
        no messages and the first snapshot. The server's check is the one that counts.
        """
        with self._lock:
            errors = creation.validate(build)
            if errors:
                return errors, None
            files.delete()
            self._kept = None
            self.manager = GameManager.from_build(build)
            self.memory.rebuild([])
            files.save(self.manager)
            return [], self._snapshot(story_text="")

    def state(self) -> dict[str, Any]:
        """Current state with the last scene's story, for the initial page load."""
        with self._lock:
            manager = self.manager
            return self._snapshot(story_text=manager.memory.last_story if manager else "")

    def export_save(self) -> dict[str, Any]:
        """The current game as a save-file dict, for the player to download."""
        with self._lock:
            return codec.to_dict(self.game)

    def import_save(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Replace the live game with an uploaded save, or reject a bad one.

        Same version/shape validation `files.load` (adapters/save/files.py) applies to the
        autosave on disk -- a rejected upload leaves the current game running
        untouched. A save that is accepted becomes the new autosave too, so
        the next turn continues from it rather than silently reverting.
        """
        with self._lock:
            manager = files.from_saved_data(data)
            if manager is None:
                return None
            self.manager = manager
            self._kept = None
            self.memory.rebuild(manager.memory.full_event_log)
            files.save(manager)
            return self._snapshot(story_text=manager.memory.last_story)

    # === Presentation ===

    def _snapshot(self, story_text: str, options: list[str] | None = None) -> dict[str, Any]:
        """Build the frontend payload. Caller must hold the lock.

        Mirrors what `managers/context.py` already tells the narrator about
        the character -- quests, conditions, equipment, traits, skills, and NPC
        disposition bands -- so the player can see in the panel what the
        narrator has been reacting to all along. NPC bands go out the same
        way `ContextBuilder._npcs_present_section` sends them to the LLM
        (disposition/trust bands, never the raw affinity integer): the
        boundary in the knowledge-firewall doc applies to the player's screen
        exactly as much as it applies to a prompt.

        `options` are the narrator's suggested next moves for this turn, if
        any -- always in addition to free text, never in place of it. Calls
        that aren't a fresh narrated turn (reset/state/import) pass none.
        """
        manager = self.manager
        if manager is None:
            return {"needs_creation": True, "story_text": story_text, "options": []}
        item_ids.stamp_world(manager.world, manager.player, manager.npcs.values())
        player = manager.player
        narrative = manager.narrative
        npcs_here = manager.npcs_in_location(player.current_location_id)
        mentioned = mentionables(manager)
        looks = {
            m.id: (m.name, label) for m, label in zip(mentioned, labels(mentioned), strict=True)
        }

        weather = manager.climate.sample(narrative.minutes)

        return {
            "needs_creation": False,
            "story_text": story_text,
            "options": options or [],
            "current_location": manager.current_location.name,
            "current_place": player.current_place,
            "game_over": narrative.game_over,
            "death_cause": narrative.death_cause,
            "location_description": manager.current_location.description,
            "day": narrative.day,
            "time_of_day": narrative.time_of_day,
            "outbreak_day": manager.outbreak_day(),
            "weather": _weather(manager, weather),
            "scene": _scene(manager, weather),
            "effects": _status_effects(player),
            "body": _body(player),
            "skills": _skills(player),
            "character": _character(player),
            "conditions": [condition.value for condition in player.conditions],
            "inventory": _inventory(player),
            "carry": _carry(player),
            "held": _held(player),
            "equipment": _equipment(player),
            "worn": _worn(player),
            "traits": _trait_entries(player),
            "goals": {
                "short_term": list(narrative.goals.get("short_term", [])),
                "long_term": list(narrative.goals.get("long_term", [])),
            },
            "quests": _active_quests(manager),
            # Plain names, kept for callers that only need the roster.
            "npcs_present": [npc.name for npc in npcs_here],
            "npcs": [_npc_regard(manager, npc) for npc in npcs_here],
            "threats": [
                {
                    "id": view.zombie_id,
                    "name": looks[view.zombie_id][0] if view.zombie_id else None,
                    "label": looks[view.zombie_id][1] if view.zombie_id else None,
                    "distance_word": view.distance_word,
                    "state_word": view.state_word,
                }
                for view in threat_views(manager)
            ],
            "corpses": _corpses(manager, looks),
            "rooms": _rooms(manager),
            "barriers": _barriers(manager),
            "mentions": [
                {**asdict(mention), "label": label}
                for mention, label in zip(mentioned, labels(mentioned), strict=True)
            ],
            "plan": self._plan_payload(manager),
            "sneaking": player.sneaking,
            "zombie_kills": player.zombie_kills,
        }

    def _plan_payload(self, manager: GameManager) -> dict[str, Any] | None:
        """The plan screen: each step in words with its default target or open choice, and each choice's candidates. None when no plan waits."""
        turn = self._kept
        if turn is None:
            return None
        return {
            "steps": [
                asdict(step) for step in steps_of(manager, turn.done, turn.plan, turn.choices)
            ],
            "choices": [
                {"candidates": [asdict(candidate) for candidate in choice.candidates]}
                for choice in turn.choices
            ],
        }


def _trace_plan(label: str, actions: Sequence[AnyAction]) -> None:
    for index, action in enumerate(actions):
        logger.debug("%s [%s]: %r", label, index, action)


def _trace_rewrites(before: Sequence[AnyAction], after: Sequence[AnyAction]) -> None:
    for index, (old, new) in enumerate(zip(before, after, strict=True)):
        if old != new:
            logger.debug("Rewrote action [%s]: %r -> %r", index, old, new)


def _trace_choices(choices: Sequence[OpenChoice]) -> None:
    for choice in choices:
        logger.debug(
            "Which-one asked for action [%s] %s: %s",
            choice.index,
            choice.attr,
            [(c.id, c.name) for c in choice.candidates],
        )


def _inventory(player: PlayerEntity) -> list[dict[str, Any]]:
    """The pack's items, equal name and condition grouped with a count (carrying-and-loot)."""
    counts: dict[tuple[str, str], int] = {}
    for entity in player.inventory:
        key = (entity.item.name, _condition(entity))
        counts[key] = counts.get(key, 0) + 1
    return [
        {"name": name, "condition": condition, "count": count}
        for (name, condition), count in counts.items()
    ]


def _carry(player: PlayerEntity) -> dict[str, Any]:
    """The load against what the player can carry (numbers are allowed here), and each bag with its contents."""
    levels = player_status_effect_levels(player)
    return {
        "weight": round(carry.carried_weight(player), 1),
        "max_weight": carry.player_max_weight(player, levels),
        "level": levels[StatusEffect.HEAVY_LOAD],
        "bags": [
            {
                "name": bag.item.name,
                "place": carry.bag_place(player, bag),
                "contents": carry.grouped(inner.item.name for inner in bag.contents),
            }
            for bag in carry.carried_bags(player)
        ],
    }


def _rooms(manager: GameManager) -> list[dict[str, Any]]:
    """The rooms of the player's zone and their containers; a container's items show only once it is opened."""
    zone = manager.current_location
    here = current_room(zone, manager.player)
    return [
        {
            "id": room.room_id,
            "name": room.name,
            "here": room is here,
            "containers": [
                {
                    "name": container.name,
                    "opened": container.opened,
                    "contents": [e.item.name for e in container.contents]
                    if container.opened
                    else [],
                }
                for container in room.containers
            ],
        }
        for room in zone.rooms.values()
    ]


def _corpses(manager: GameManager, looks: dict[str, tuple[str, str]]) -> list[dict[str, Any]]:
    """The bodies the player can see, in words and named as the `@` list names them; what a body holds shows only once it is searched."""
    return [
        {
            "id": view.corpse_id,
            "name": looks[view.corpse_id][0],
            "label": looks[view.corpse_id][1],
            "distance_word": view.distance_word,
            "rot_word": view.rot_word,
            "searched": view.searched,
            "carried": view.corpse_id == manager.player.carrying_corpse,
            "contents": list(view.contents) if view.searched else [],
        }
        for view in corpse_views(manager)
    ]


def _barriers(manager: GameManager) -> list[dict[str, Any]]:
    """The doors and windows of the player's zone in words, with plank counts on each side."""
    here = manager.player.current_location_id
    pounding = {view.barrier_id for view in threat_views(manager) if view.barrier_id is not None}
    return [
        {
            "id": barrier.barrier_id,
            "name": barrier.name,
            "state_word": state_word(barrier),
            "planks_here": barrier.plank_count(here),
            "planks_far": barrier.plank_count(barrier.far_side(here)),
            "thumping": barrier.barrier_id in pounding,
        }
        for barrier in barriers_of(manager.world, here)
    ]


def _trait_entries(player: PlayerEntity) -> list[dict[str, str]]:
    return [
        {"name": TRAITS[trait_id].name, "description": TRAITS[trait_id].description}
        for trait_id in player.traits
        if trait_id in TRAITS
    ]


def _occupation_name(player: PlayerEntity) -> str:
    occupation = OCCUPATIONS.get(player.occupation_id)
    return player.job_title or (occupation.name if occupation else "")


def _character(player: PlayerEntity) -> dict[str, Any]:
    return {
        "name": player.name,
        "occupation": _occupation_name(player),
        "traits": [entry["name"] for entry in _trait_entries(player)],
    }


def _skills(player: PlayerEntity) -> list[dict[str, Any]]:
    """Every skill with its level and progress toward the next, never the XP."""
    return [
        {
            "id": skill.id,
            "name": skill.name,
            "category": skill.category,
            "level": state.level,
            "progress": skill_progress(skill.id, state),
        }
        for skill in SKILLS.values()
        for state in [player.skills.get(skill.id, SkillState())]
    ]


def _weather(manager: GameManager, weather: WeatherSample) -> dict[str, Any]:
    return {
        "summary": weather_summary(weather),
        "temperature_c": round(weather.air_temperature),
        "sheltered": manager.current_location.indoors,
    }


def _scene(manager: GameManager, weather: WeatherSample) -> dict[str, str]:
    """What the page draws above the story: the outbreak stage, the zone's setting and the sky, in words."""
    return {
        "stage": manager.outbreak_stage(),
        "setting": setting_word(manager.current_location),
        **scene_weather(weather),
    }


def _status_effects(player: PlayerEntity) -> list[dict[str, Any]]:
    """Active status effects, strongest first."""
    return [
        {"type": status_effect.value, "level": level, "name": name}
        for status_effect, level, name in sorted(
            active_status_effects(player), key=lambda entry: -entry[1]
        )
    ]


def _body(player: PlayerEntity) -> list[dict[str, Any]]:
    """The injured and bandaged parts in words and flags; no health or pain number."""
    entries: list[dict[str, Any]] = []
    for part, state in player.body.items():
        if not (state.injured or state.bandaged):
            continue
        wounds = open_wounds(state)
        entries.append(
            {
                "part": part_word(part),
                "wounds": wounds,
                "bleeding": state.bleeding,
                "bandaged": state.bandaged,
                "dirty": state.bandaged and state.bandage_life <= 0,
                "infected": state.infected_wound and state.wounded,
            }
        )
    return entries


def _condition(entity: ItemEntity) -> str:
    if isinstance(entity.item, MeleeWeaponItem):
        return item_condition_word(entity)
    if isinstance(entity.item, MedicalItem | StackItem):
        return naming.uses_words(entity) or item_condition_word(entity)
    return f"{entity.hit_points}/{entity.max_hit_points}"


def _held(player: PlayerEntity) -> dict[str, str] | None:
    entity = weapons.held_entity(player)
    if entity is None:
        return None
    return {"name": entity.item.name, "condition_word": item_condition_word(entity)}


def _equipment(player: PlayerEntity) -> list[dict[str, Any]]:
    """The hand and shoulder slots; one entity filling both hands is a single `both_hands` entry."""
    right = player.equipment[CharacterHoldableSlot.RIGHT_HAND]
    left = player.equipment[CharacterHoldableSlot.LEFT_HAND]
    both = right is not None and right is left

    entries: list[dict[str, Any]] = []
    for slot, entity in player.equipment.items():
        if both and slot is CharacterHoldableSlot.LEFT_HAND:
            continue
        shared = both and slot is CharacterHoldableSlot.RIGHT_HAND
        entries.append(
            {
                "slot": "Both Hands" if shared else slot.value.replace("_", " ").title(),
                "both_hands": shared,
                "item": entity.item.name if entity is not None else None,
                "condition": _condition(entity) if entity is not None else None,
            }
        )

    return entries


def _worn(player: PlayerEntity) -> list[dict[str, Any]]:
    """Worn clothing outer to inner; wetness reaches the player as a word."""
    return [
        {
            "location": location.value,
            "name": entity.item.name,
            "wetness_word": wetness_word(entity.wetness),
        }
        for location, entity in player.worn_outer_to_inner()
    ]


def _active_quests(manager: GameManager) -> list[dict[str, Any]]:
    return [
        {
            "title": quest.title or quest.quest_id,
            "objectives": [
                {
                    "label": quest.objective_labels.get(objective, objective),
                    "done": objective in quest.completed_objectives,
                }
                for objective in quest.objectives
            ],
        }
        for quest in manager.quests.values()
        if quest.status == QuestStatus.ACTIVE
    ]


def _npc_regard(manager: GameManager, npc: NpcEntity) -> dict[str, Any]:
    """An NPC's name and how they regard the player, as bands, never the integers."""
    relationships = manager.relationship_manager
    player_id = manager.player.entity_id
    return {
        "id": npc.npc_id,
        "name": npc.name,
        "disposition": relationships.get_disposition(npc.npc_id, player_id).value,
        "trust": relationships.get_trust_level(npc.npc_id, player_id).value,
        "following": npc.following,
    }
