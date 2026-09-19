"""Orchestrates one game turn: recall -> parse -> validate -> simulate -> narrate -> persist.

Two LLM calls, not one: the parser proposes actions from player input before
anything is decided, the engine validates and simulates them, and only then
does the narrator describe what already happened. See
docs/01-engine-authority.md.
"""

import threading
from typing import Any

from adapters import llm, persistence
from adapters.memory import SemanticMemory
from managers.game import GameManager
from managers.simulation import SimulationCore
from modules.action import parse_action_plan


class GameEngine:
    """Owns the live GameManager and everything around it.

    Flask's dev server is threaded, so two overlapping requests would otherwise
    interleave mutations of the same GameManager and race on the save file. All
    state transitions are therefore serialized behind one lock.
    """

    def __init__(self):
        self._lock = threading.Lock()
        self.memory = SemanticMemory()
        self.manager = persistence.load() or GameManager()
        self.memory.rebuild(self.manager.memory.full_event_log)

    # === Turn execution ===

    def play(self, player_input: str) -> dict[str, Any]:
        """Run a full turn and return the payload the frontend renders."""
        with self._lock:
            manager = self.manager

            # 1. Recall semantically relevant past events (for the narrator).
            indices = self.memory.search(player_input)
            deep_memories = [
                manager.memory.full_event_log[i]
                for i in indices
                if i < len(manager.memory.full_event_log)
            ]
            print(f"[Engine] Recalled {len(deep_memories)} deep memories.")

            # 2. Ask the parser what Orton is trying to do. No prose exists yet.
            parser_prompt = manager.build_parser_prompt(player_input)
            try:
                raw_actions = llm.query_parser(parser_prompt)
            except llm.LLMError as exc:
                return self._snapshot(story_text=f"--- SYSTEM ERROR ---\n{exc}")

            action_lines = llm.parse_action_response(raw_actions)
            actions, parse_failures = parse_action_plan(action_lines)

            # 3. Validate and simulate, one action at a time in order. This is
            # where the engine decides what happens -- before the narrator
            # writes a single word about it.
            outcome_facts = SimulationCore(manager).resolve(actions)
            for failure in parse_failures:
                print(f"[Engine] Unparseable action '{failure.raw}': {failure.reason}")
                outcome_facts.append(f"Refused: '{failure.raw}' -- {failure.reason}")

            # 4. Ask the narrator to describe what already happened.
            narrator_prompt = manager.build_narrator_prompt(
                player_input, outcome_facts, deep_memories
            )
            try:
                raw_response = llm.query_narrator(narrator_prompt)
            except llm.LLMError as exc:
                # Unlike a parser failure, real state changes may already
                # exist here -- the engine decided them before asking for
                # prose, and a rendering failure must not discard engine
                # truth. Record the outcome facts as this turn's event
                # verbatim and persist, so state and disk agree even though
                # nothing was narrated.
                fallback_event = "; ".join(outcome_facts) if outcome_facts else "Nothing happened."
                manager.record_event(fallback_event)
                self.memory.rebuild(manager.memory.full_event_log)
                persistence.save(manager)
                return self._snapshot(story_text=f"--- SYSTEM ERROR ---\n{exc}")

            parsed = llm.parse_narrator_response(raw_response)
            story_text = str(parsed["story"])
            event_text = str(parsed["event"])

            # 5. Record the event in both memory tiers and reindex.
            manager.record_event(event_text)
            self.memory.rebuild(manager.memory.full_event_log)

            # 6. Summarize if enough history has built up.
            self._run_summarization()

            persistence.save(manager)
            return self._snapshot(story_text=story_text)

    def _run_summarization(self) -> None:
        """Fold the oldest unsummarized events into a narrative paragraph."""
        pending = self.manager.events_pending_summary()
        if not pending:
            return
        try:
            summary = llm.query_summary("\n".join(pending))
        except llm.LLMError as exc:
            # Not fatal: the turn stands, we just try again next turn.
            print(f"[Engine] Summarization skipped: {exc}")
            return
        self.manager.memory.summaries.append(summary)
        print(f"[Engine] Added summary #{len(self.manager.memory.summaries)}.")

    # === Lifecycle ===

    def reset(self) -> dict[str, Any]:
        """Discard the save and start a brand new game."""
        with self._lock:
            persistence.delete()
            self.manager = GameManager()
            self.memory.rebuild(self.manager.memory.full_event_log)
            persistence.save(self.manager)
            return self._snapshot(story_text="")

    def state(self) -> dict[str, Any]:
        """Current state with no story text, for the initial page load."""
        with self._lock:
            return self._snapshot(story_text="")

    # === Presentation ===

    def _snapshot(self, story_text: str) -> dict[str, Any]:
        """Build the frontend payload. Caller must hold the lock."""
        manager = self.manager
        player = manager.player
        narrative = manager.narrative

        return {
            "story_text": story_text,
            "current_location": manager.current_location.name,
            # A list, not a string: the frontend iterates this.
            "inventory": [
                f"{entity.item.name}"
                f" ({entity.hit_points}/{entity.max_hit_points})"
                for entity in player.inventory
            ],
            "condition": (
                f"Health: {player.hit_points}/{player.max_hit_points}, "
                f"Hunger: {player.hunger}%, "
                f"Thirst: {player.thirst}%, "
                f"Morale: {player.morale}%, "
                f"Sleep: {narrative.conditions.get('sleep', 'Rested')}, "
                f"Infection Risk: {narrative.conditions.get('infection_risk', 'No')}"
            ),
            "goals": {
                "short_term": list(narrative.goals.get("short_term", [])),
                "long_term": list(narrative.goals.get("long_term", [])),
            },
            "npcs_present": [
                npc.name
                for npc in manager.npcs_in_location(player.current_location_id)
            ],
            "day": narrative.day,
            "time_of_day": narrative.time_of_day,
            "apocalypse_stage": narrative.apocalypse_stage,
        }
