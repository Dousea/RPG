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
from modules.quest import QuestStatus


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
            options = list(parsed["options"])

            # 5. Record the event in both memory tiers and reindex.
            manager.record_event(event_text)
            self.memory.rebuild(manager.memory.full_event_log)

            # 6. Summarize if enough history has built up.
            self._run_summarization()

            persistence.save(manager)
            return self._snapshot(story_text=story_text, options=options)

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

    def export_save(self) -> dict[str, Any]:
        """The current game as a save-file dict, for the player to download."""
        with self._lock:
            return persistence.to_dict(self.manager)

    def import_save(self, data: dict[str, Any]) -> dict[str, Any] | None:
        """Replace the live game with an uploaded save, or reject a bad one.

        Same version/shape validation `persistence.load` applies to the
        autosave on disk -- a rejected upload leaves the current game running
        untouched. A save that is accepted becomes the new autosave too, so
        the next turn continues from it rather than silently reverting.
        """
        with self._lock:
            manager = persistence.from_saved_data(data)
            if manager is None:
                return None
            self.manager = manager
            self.memory.rebuild(manager.memory.full_event_log)
            persistence.save(manager)
            return self._snapshot(story_text="")

    # === Presentation ===

    def _snapshot(
        self, story_text: str, options: list[str] | None = None
    ) -> dict[str, Any]:
        """Build the frontend payload. Caller must hold the lock.

        Mirrors what `managers/context.py` already tells the narrator about
        Orton -- quests, conditions, equipment, traits/perks, level, and NPC
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
        player = manager.player
        narrative = manager.narrative

        npcs_here = manager.npcs_in_location(player.current_location_id)

        return {
            "story_text": story_text,
            "options": options or [],
            "current_location": manager.current_location.name,
            "current_place": player.current_place,
            "location_description": manager.current_location.description,
            "day": narrative.day,
            "time_of_day": narrative.time_of_day,
            "apocalypse_stage": narrative.apocalypse_stage,
            "vitals": {
                "health": player.hit_points,
                "max_health": player.max_hit_points,
                "hunger": player.hunger,
                "thirst": player.thirst,
                "morale": player.morale,
                "sleep": narrative.conditions.get("sleep", "Rested"),
                "infection_risk": narrative.conditions.get("infection_risk", "No"),
            },
            "level": player.level,
            "experience_points": player.experience_points,
            "attributes": {
                attr.value: value for attr, value in player.attributes.items()
            },
            "conditions": [condition.value for condition in player.conditions],
            "status_effects": list(narrative.player_status),
            # A list, not a string: the frontend iterates this.
            "inventory": [
                {
                    "name": entity.item.name,
                    "condition": f"{entity.hit_points}/{entity.max_hit_points}",
                }
                for entity in player.inventory
            ],
            "equipment": [
                {
                    "slot": slot.value.replace("_", " ").title(),
                    "item": entity.item.name if entity is not None else None,
                    "condition": (
                        f"{entity.hit_points}/{entity.max_hit_points}"
                        if entity is not None
                        else None
                    ),
                }
                for slot, entity in player.equipment.items()
            ],
            "traits": [
                {"name": trait.name, "description": trait.description}
                for trait in player.traits
            ],
            "perks": [
                {"name": perk.name, "description": perk.description}
                for perk in player.perks
            ],
            "goals": {
                "short_term": list(narrative.goals.get("short_term", [])),
                "long_term": list(narrative.goals.get("long_term", [])),
            },
            "quests": [
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
            ],
            # Plain names, kept for callers that only need the roster.
            "npcs_present": [npc.name for npc in npcs_here],
            # Same names alongside how each NPC currently regards Orton, as a
            # disposition/trust band rather than the underlying integer.
            "npcs": [
                {
                    "name": npc.name,
                    "disposition": manager.relationship_manager.get_disposition(
                        npc.npc_id, player.entity_id
                    ).value,
                    "trust": manager.relationship_manager.get_trust_level(
                        npc.npc_id, player.entity_id
                    ).value,
                }
                for npc in npcs_here
            ],
        }
