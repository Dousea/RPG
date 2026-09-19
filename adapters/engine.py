"""Orchestrates one game turn: recall -> prompt -> LLM -> apply -> persist."""

import threading
from typing import Any

from adapters import llm, persistence
from adapters.memory import SemanticMemory
from managers.game import GameManager


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

            # 1. Recall semantically relevant past events.
            indices = self.memory.search(player_input)
            deep_memories = [
                manager.memory.full_event_log[i]
                for i in indices
                if i < len(manager.memory.full_event_log)
            ]
            print(f"[Engine] Recalled {len(deep_memories)} deep memories.")

            # 2. Ask the game master what happens.
            prompt = manager.build_prompt(player_input, deep_memories)
            try:
                raw_response = llm.query_game_master(prompt)
            except llm.LLMError as exc:
                # The turn did not happen: no event recorded, nothing saved.
                return self._snapshot(story_text=f"--- SYSTEM ERROR ---\n{exc}")

            parsed = llm.parse_response(raw_response)
            story_text = str(parsed["story"])
            event_text = str(parsed["event"])
            actions: list[str] = list(parsed["actions"])  # type: ignore[arg-type]

            # 3. Apply the state changes it asked for.
            corrections: list[str] = []
            for action in actions:
                succeeded, message = manager.apply_action(action)
                print(f"[Engine] {'OK  ' if succeeded else 'FAIL'} {action} -- {message}")
                if not succeeded:
                    corrections.append(f"{action} -- {message}")
            # The prompt this turn already carried last turn's refusals, so they
            # are spent; replace them with whatever was refused just now. The
            # narration is already written and cannot be taken back -- the next
            # turn is the earliest the story can admit the delta never landed.
            manager.narrative.pending_corrections = corrections

            # 4. Record the event in both memory tiers and reindex.
            manager.record_event(event_text)
            self.memory.rebuild(manager.memory.full_event_log)

            # 5. Summarize if enough history has built up.
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
