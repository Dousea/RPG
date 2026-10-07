"""Orchestrates one game turn: recall -> parse -> validate -> simulate -> narrate -> persist.

Two LLM calls, not one: the parser proposes actions from player input before
anything is decided, the engine validates and simulates them, and only then
does the narrator describe what already happened. See
docs/01-engine-authority.md.
"""

import logging
import threading
from collections.abc import Callable
from typing import Any

import config
from adapters import llm
from adapters.factcheck import StoryChecker
from adapters.memory import DEFAULT_RECALL, SemanticMemory
from adapters.save import codec, files
from data.items import item_condition_word, wetness_word
from data.memory import BUDGET_MARGIN_TOKENS
from data.occupations import OCCUPATIONS
from data.skills import SKILLS
from data.traits import TRAITS
from managers import creation
from managers.barriers import barriers_of, state_word
from managers.body import open_wounds
from managers.climate import weather_summary
from managers.combat import held_entity
from managers.context import NOTHING_DONE_FACT, ContextBuilder
from managers.event_log import build_event_entry, event_stamp
from managers.first_aid import part_word
from managers.game import MAX_RECENT_EVENTS, GameManager
from managers.loot import corpse_views
from managers.simulation import SimulationCore
from managers.skills import skill_progress
from managers.stats.status_effects import active_status_effects
from managers.story_check import build_questions
from managers.zombies import threat_views
from modules.action.words import refusal_in_words
from modules.character.build import CharacterBuild
from modules.character.skills import SkillState
from modules.entity.item import ItemEntity
from modules.entity.npc import NpcEntity
from modules.entity.player import PlayerEntity
from modules.item import MedicalItem, MeleeWeaponItem, StackItem
from modules.quest import QuestStatus

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
        self.factcheck = StoryChecker()
        self.manager: GameManager | None = files.load()
        self.memory.rebuild(self.manager.memory.full_event_log if self.manager else [])

    @property
    def has_game(self) -> bool:
        return self.manager is not None

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

    def play(self, player_input: str, on_event: TurnListener | None = None) -> dict[str, Any]:
        """Run a full turn and return the payload the frontend renders.

        `on_event` hears each step of the turn as it starts, and the narrator's
        thinking and story as they are written; the returned payload is the
        same either way.
        """
        emit = on_event or _ignore
        with self._lock:
            manager = self.manager
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

            # 1. Recall semantically relevant past events (for the narrator).
            indices = self.memory.search(player_input, DEFAULT_RECALL + MAX_RECENT_EVENTS)
            deep_memories = [
                entry
                for i in indices
                if i < len(manager.memory.full_event_log)
                and (entry := manager.memory.full_event_log[i]) not in manager.memory.recent_events
            ][:DEFAULT_RECALL]
            logger.debug(f"Recalled {len(deep_memories)} deep memories.")

            stamp = event_stamp(manager)

            # 2. Ask the parser what the player is trying to do. No prose exists yet.
            context = ContextBuilder(manager)
            parser_prompt = context.build_parser_prompt(player_input)
            emit({"type": "step", "step": "parsing"})
            try:
                reply = llm.query_parser(parser_prompt, context.build_plan_schema())
            except llm.LLMError as exc:
                return self._snapshot(story_text=f"--- SYSTEM ERROR ---\n{exc}")

            actions, parse_failures = llm.read_parser_reply(reply)

            # 3. Validate and simulate, one action at a time in order. This is
            # where the engine decides what happens -- before the narrator
            # writes a single word about it.
            outcome_facts = SimulationCore(manager).resolve(actions, refused=len(parse_failures))
            looks = manager.player.appearance
            for failure in parse_failures:
                logger.warning(f"Unparseable action '{failure.raw}': {failure.reason}")
                outcome_facts.append(refusal_in_words(failure, looks.forename, looks.subject))

            # 4. Ask the narrator to describe what already happened. A turn the
            # parser found nothing in would otherwise be narrated as the input.
            narrated_facts = outcome_facts
            if not actions and not parse_failures:
                narrated_facts = [NOTHING_DONE_FACT.format(name=looks.forename), *outcome_facts]
            context = ContextBuilder(manager)
            narrator_prompt = context.build_narrator_prompt(
                player_input, narrated_facts, deep_memories, max_chars=self._narrator_budget()
            )
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
            parsed = self._fact_checked(
                parsed, context, player_input, narrated_facts, deep_memories, emit
            )
            parsed = self._with_options(
                parsed, context, player_input, narrated_facts, deep_memories, emit
            )
            story_text = str(parsed["story"])
            options = list(parsed["options"])
            entry = build_event_entry(manager, stamp, player_input, outcome_facts)

            # 5. Record the event in both memory tiers and reindex.
            emit({"type": "step", "step": "saving"})
            manager.record_event(entry)
            manager.memory.last_story = story_text
            self.memory.rebuild(manager.memory.full_event_log)

            # 6. Summarize if enough history has built up.
            self._run_summarization(manager)

            files.save(manager)
            return self._snapshot(story_text=story_text, options=options)

    def _fact_checked(
        self,
        parsed: dict[str, Any],
        context: ContextBuilder,
        player_input: str,
        outcome_facts: list[str],
        deep_memories: list[str],
        emit: TurnListener,
    ) -> dict[str, Any]:
        """The narrator's reply, or its one retry when the story conflicts with the engine's state.

        The retry replaces the first reply only if it conflicts on no more
        questions; the facts themselves never change.
        """
        questions = build_questions(context.manager, outcome_facts)
        if not questions:
            return parsed
        if self.factcheck.enabled:
            emit({"type": "step", "step": "fact_checking"})
        conflicts = self.factcheck.conflicts(str(parsed["story"]), questions)
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
            )
            + block
        )
        emit({"type": "step", "step": "rewriting"})
        try:
            retry = self._reply(llm.query_narrator(retry_prompt, on_delta=_story_listener(emit)))
        except llm.LLMError as exc:
            logger.warning(f"Narrator retry failed, keeping the first story: {exc}")
            return parsed
        if retry["story"] == llm.EMPTY_STORY:
            logger.warning("Narrator retry has no story, keeping the first story.")
            return parsed
        retry_conflicts = self.factcheck.conflicts(str(retry["story"]), questions)
        return retry if len(retry_conflicts) <= len(conflicts) else parsed

    def _with_options(
        self,
        parsed: dict[str, Any],
        context: ContextBuilder,
        player_input: str,
        outcome_facts: list[str],
        deep_memories: list[str],
        emit: TurnListener,
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
            )
            + block
        )
        try:
            reply = llm.query_narrator(prompt)
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
            self.manager = GameManager.from_build(build)
            self.memory.rebuild([])
            files.save(self.manager)
            return [], self._snapshot(story_text="")

    def state(self) -> dict[str, Any]:
        """Current state with no story text, for the initial page load."""
        with self._lock:
            return self._snapshot(story_text="")

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
            self.memory.rebuild(manager.memory.full_event_log)
            files.save(manager)
            return self._snapshot(story_text="")

    # === Presentation ===

    def _snapshot(self, story_text: str, options: list[str] | None = None) -> dict[str, Any]:
        """Build the frontend payload. Caller must hold the lock.

        Mirrors what `managers/context.py` already tells the narrator about
        the character -- quests, conditions, equipment, traits, skills, and NPC
        disposition bands -- so the player can see in the panel what the
        narrator has been reacting to all along. NPC bands go out the same
        way `ContextBuilder._npcs_present_section` sends them to the LLM
        (disposition/trust bands, never the raw affinity integer): the
        knowledge-firewall boundary in doc 11 applies to the player's screen
        exactly as much as it applies to a prompt.

        `options` are the narrator's suggested next moves for this turn, if
        any -- always in addition to free text, never in place of it. Calls
        that aren't a fresh narrated turn (reset/state/import) pass none.
        """
        manager = self.manager
        if manager is None:
            return {"needs_creation": True, "story_text": story_text, "options": []}
        player = manager.player
        narrative = manager.narrative
        npcs_here = manager.npcs_in_location(player.current_location_id)

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
            "weather": _weather(manager),
            "effects": _status_effects(player),
            "body": _body(player),
            "skills": _skills(player),
            "character": _character(player),
            "conditions": [condition.value for condition in player.conditions],
            "inventory": [
                {"name": entity.item.name, "condition": _condition(entity)}
                for entity in player.inventory
            ],
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
                    "distance_word": view.distance_word,
                    "state_word": view.state_word,
                }
                for view in threat_views(manager)
            ],
            "corpses": _corpses(manager),
            "barriers": _barriers(manager),
            "sneaking": player.sneaking,
            "zombie_kills": player.zombie_kills,
        }


def _corpses(manager: GameManager) -> list[dict[str, Any]]:
    """The bodies the player can see, in words; what a body holds shows only once it is searched."""
    return [
        {
            "id": view.corpse_id,
            "distance_word": view.distance_word,
            "rot_word": view.rot_word,
            "searched": view.searched,
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


def _weather(manager: GameManager) -> dict[str, Any]:
    weather = manager.climate.sample(manager.narrative.minutes)
    return {
        "summary": weather_summary(weather),
        "temperature_c": round(weather.air_temperature),
        "sheltered": manager.current_location.indoors,
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
                "infected": state.infected_wound and state.wounded and not state.bandaged,
            }
        )
    return entries


def _condition(entity: ItemEntity) -> str:
    if isinstance(entity.item, MeleeWeaponItem):
        return item_condition_word(entity)
    if isinstance(entity.item, MedicalItem | StackItem):
        return f"{entity.uses} left" if entity.item.uses > 1 else item_condition_word(entity)
    return f"{entity.hit_points}/{entity.max_hit_points}"


def _held(player: PlayerEntity) -> dict[str, str] | None:
    entity = held_entity(player)
    if entity is None:
        return None
    return {"name": entity.item.name, "condition_word": item_condition_word(entity)}


def _equipment(player: PlayerEntity) -> list[dict[str, Any]]:
    return [
        {
            "slot": slot.value.replace("_", " ").title(),
            "item": entity.item.name if entity is not None else None,
            "condition": _condition(entity) if entity is not None else None,
        }
        for slot, entity in player.equipment.items()
    ]


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
        "name": npc.name,
        "disposition": relationships.get_disposition(npc.npc_id, player_id).value,
        "trust": relationships.get_trust_level(npc.npc_id, player_id).value,
        "following": npc.following,
    }
