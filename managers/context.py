"""Context Builder: assembles what each LLM call is allowed to see.

This is the knowledge-firewall boundary doc 11 describes: raw simulation
state (relationship integers, undiscovered world flags) never crosses into a
prompt directly. Whoever reads world truth out to an LLM does it through here,
at the same read-out boundary the relationship bands already used
(`_npcs_present_section`) -- filter at the boundary, don't hide the field.

Two prompts, two audiences: the parser gets minimal scene facts (no prose
context, no memory) because it only proposes actions; the narrator gets full
prose context plus this turn's already-decided [OUTCOMES].
"""

from managers.game import GameManager
from modules.quest import QuestStatus


class ContextBuilder:
    def __init__(self, manager: GameManager):
        self.manager = manager

    # === Shared sections ===

    def _current_items_section(self) -> str:
        items = self.manager._ground_items()
        if not items:
            return "No items here."
        return "\n".join(f" - {item.item.name}" for item in items)

    def _nearby_locations_section(self) -> str:
        location = self.manager.current_location
        if not location.connections:
            return "No exits visible."
        return "\n".join(
            f" - {direction.capitalize()}: {self.manager.world.locations[loc_id].name}"
            for direction, loc_id in location.connections.items()
            if loc_id in self.manager.world.locations
        )

    def _zones_section(self) -> str:
        """The whole zone roster, one line per zone.

        The parser can only aim MOVE_TO at a zone it has been told exists --
        this is that roster. It lives on the parser prompt (not the
        narrator's) because the parser is what emits MOVE_TO.
        """
        return "\n".join(f" - {location.name}" for location in self.manager.world.locations.values())

    def _npcs_present_section(self) -> str:
        """NPCs present, with how each one currently regards the player.

        Affinity and trust go out as bands, never as the underlying integers
        -- Orton can tell that Emma has warmed to him; he cannot read
        `affection +37` off her face, and a narrator given the number
        narrates to it. NPC goals are shown as visible intent (what Orton
        could plausibly read from behavior); NPC `.knowledge` is deliberately
        never rendered here -- it exists for a future dialogue system to gate
        what an NPC can truthfully say, not to be handed to the narrator
        wholesale, which would defeat the firewall.
        """
        manager = self.manager
        npcs = manager.npcs_in_location(manager.player.current_location_id)
        if not npcs:
            return "No one else is here."

        lines: list[str] = []
        for npc in npcs:
            disposition = manager.relationship_manager.get_disposition(
                npc.npc_id, manager.player.entity_id
            )
            trust_level = manager.relationship_manager.get_trust_level(
                npc.npc_id, manager.player.entity_id
            )
            lines.append(
                f" - {npc.name}"
                f"{f' ({npc.age})' if npc.age is not None else ''}: {npc.description}"
            )
            lines.append(f"   Disposition: {disposition} (trust: {trust_level})")
            if npc.status:
                lines.append(f"   Status: {', '.join(npc.status)}")
            if npc.personality:
                lines.append(f"   Personality: {', '.join(npc.personality)}")
            if npc.goals:
                lines.append(f"   Visible intent: {', '.join(npc.goals)}")
            if npc.notes:
                # ADD_RELATIONSHIP_NOTE writes Orton's read on someone, not the
                # NPC's private thoughts, so this side of the firewall is where
                # it belongs -- but say whose impressions they are.
                lines.append(f"   Orton's impressions: {npc.notes}")
        return "\n".join(lines)

    def _summary_section(self) -> str:
        if not self.manager.memory.summaries:
            return "(No summary available yet)"
        return "\n\n".join(self.manager.memory.summaries)

    def _events_section(self) -> str:
        if not self.manager.memory.recent_events:
            return "(No recent events)"
        return "\n".join(f" - {event}" for event in self.manager.memory.recent_events)

    def _corrections_section(self) -> str:
        corrections = self.manager.narrative.pending_corrections
        if not corrections:
            return "(Nothing to correct)"
        return "\n".join(f" - {correction}" for correction in corrections)

    @staticmethod
    def _outcomes_section(outcome_facts: list[str] | None) -> str:
        if not outcome_facts:
            return "(No actions were taken this turn)"
        return "\n".join(f" - {fact}" for fact in outcome_facts)

    def _discovered_flags_section(self) -> str:
        """Only flags Orton has actually discovered -- doc 11's complaint was
        that every world flag went out unfiltered regardless of whether
        anything in the story had ever revealed it to the player. A flag
        becomes visible here only once a `DISCOVER_FLAG` action has marked it
        as such; setting a flag's value and discovering it are separate acts,
        so the engine can hold ground truth the player doesn't know yet."""
        narrative = self.manager.narrative
        visible = {
            name: value
            for name, value in narrative.flags.items()
            if name in narrative.discovered_flags
        }
        if not visible:
            return "None"
        return ", ".join(f"{k}={v}" for k, v in visible.items())

    def _quests_section(self) -> str:
        """Active quest objectives, in plain language.

        Quest completion is engine-decided (`SimulationCore._advance_quests`)
        -- there is no LLM verb for it -- but the narrator still needs to know
        what Orton is working toward so it can weave it into prose. Only
        ACTIVE quests render; a quest that just completed this turn already
        shows up in [OUTCOMES], and there is no reason to keep prompting the
        narrator about one that's done.
        """
        active = [
            quest
            for quest in self.manager.quests.values()
            if quest.status == QuestStatus.ACTIVE
        ]
        if not active:
            return "None"
        lines: list[str] = []
        for quest in active:
            lines.append(f" - {quest.title or quest.quest_id}")
            for objective in quest.objectives:
                label = quest.objective_labels.get(objective, objective)
                done = objective in quest.completed_objectives
                lines.append(f"   [{'x' if done else ' '}] {label}")
        return "\n".join(lines)

    # === Parser prompt ===

    def build_parser_prompt(self, player_input: str) -> str:
        """Assemble the minimal-context prompt for the intent parser call.

        The parser only needs to know what is reachable/visible right now to
        propose actions -- it does not narrate, so it gets none of the prose
        context (memory, summaries, disposition bands) the narrator needs.
        """
        manager = self.manager
        player = manager.player
        inventory_str = (
            "\n".join(f" - {entity.item.name}" for entity in player.inventory) or "Empty"
        )
        equipped = [
            entity.item.name for entity in player.equipment.values() if entity is not None
        ]
        equipped_str = ", ".join(equipped) if equipped else "Nothing"
        npc_names = ", ".join(
            npc.name for npc in manager.npcs_in_location(player.current_location_id)
        )

        return f"""[LOCATION]
{manager.current_location.name}: {manager.current_location.description}
Specific spot: {player.current_place or '(nowhere in particular)'}

[EXITS]
{self._nearby_locations_section().rstrip()}

[ZONES]
(The world is these four zones. MOVE_TO one of these names to change zone.
MOVE_TO anything else -- a room, a shop, a landmark -- moves Orton to a spot
inside the zone he is already in, which is normal and expected.)

{self._zones_section().rstrip()}

[ITEMS HERE]
{self._current_items_section().rstrip()}

[NPCS HERE]
{npc_names if npc_names else "No one else is here."}

[INVENTORY]
{inventory_str}

[EQUIPPED]
{equipped_str}

[PLAYER INPUT]
{player_input}"""

    # === Narrator prompt ===

    def build_narrator_prompt(
        self,
        player_input: str,
        outcome_facts: list[str] | None = None,
        deep_memories: list[str] | None = None,
    ) -> str:
        """Assemble the full LLM prompt for the narrator call.

        `outcome_facts` are what the Action Validator and Simulation Core
        already decided this turn -- movement, combat, item use, everything
        doc 01 says the engine must be authoritative over. The narrator
        describes them; it does not decide them. `deep_memories` are
        semantically retrieved past events supplied by the memory layer.
        """
        manager = self.manager
        player = manager.player
        narrative = manager.narrative

        inventory_str = "\n".join(
            f" - {entity.item.name} (condition: {entity.hit_points}/{entity.max_hit_points})"
            for entity in player.inventory
        )
        attributes_str = "\n".join(
            f" - {attr.name}: {value}" for attr, value in player.attributes.items()
        )
        equipment_str = "\n".join(
            f" - {slot.name}: {f'{entity.item.name} (condition: {entity.hit_points}/{entity.max_hit_points})' if entity else 'None'}"
            for slot, entity in player.equipment.items()
        )
        traits_str = "\n".join(
            f" - {trait.name}: {trait.description}" for trait in player.traits
        )
        perks_str = "\n".join(f" - {perk.name}: {perk.description}" for perk in player.perks)
        conditions_str = ", ".join(condition.name for condition in player.conditions)

        goals_str = ""
        if narrative.goals.get("short_term"):
            goals_str += f"Short-term: {', '.join(narrative.goals['short_term'])}. "
        if narrative.goals.get("long_term"):
            goals_str += f"Long-term: {', '.join(narrative.goals['long_term'])}."

        char_context = f"""
Name: {player.name}
Level: {player.level} (XP: {player.experience_points})
Health: {player.hit_points}/{player.max_hit_points}
Hunger: {player.hunger}%
Thirst: {player.thirst}%
Morale: {player.morale}%
Sleep: {narrative.conditions.get('sleep', 'Rested')}
Infection Risk: {narrative.conditions.get('infection_risk', 'No')}
Conditions: {conditions_str if conditions_str else 'None'}
Status: {', '.join(narrative.player_status) if narrative.player_status else 'None'}
Goals: {goals_str if goals_str else 'None'}
Inventory: {inventory_str if inventory_str else 'Empty'}
Attributes: {attributes_str if attributes_str else 'None'}
Equipment: {equipment_str if equipment_str else 'None'}
Traits: {traits_str if traits_str else 'None'}
Perks: {perks_str if perks_str else 'None'}
"""

        location_context = f"""
Current Location: {manager.current_location.name}
Specific spot: {player.current_place or '(nowhere in particular)'}
Description: {manager.current_location.description}
Day {narrative.day}, {narrative.time_of_day.capitalize()} -- {manager.world.time}, {manager.world.date}
Apocalypse Stage: {narrative.apocalypse_stage}
Flags: {self._discovered_flags_section()}
"""

        deep_memory_section = (
            "\n".join(f" - {memory}" for memory in deep_memories)
            if deep_memories
            else "(No relevant memories surfaced)"
        )

        return f"""[CHARACTER]
{char_context}

[DEEP MEMORY]
(Past events recalled as relevant to what the player just did)

{deep_memory_section}

[CURRENT LOCATION]
{location_context}

[ITEMS IN CURRENT LOCATION]

{self._current_items_section().rstrip()}

[NEARBY LOCATIONS]

{self._nearby_locations_section().rstrip()}

[NPCS PRESENT]

{self._npcs_present_section().rstrip()}

[QUESTS]
(What Orton is currently working toward, engine-tracked. [x] is complete.)

{self._quests_section().rstrip()}

[SUMMARY OF PAST EVENTS]
(A narrative overview of the long-term past)

{self._summary_section().rstrip()}

[RECENT EVENTS]
(What just happened)

{self._events_section().rstrip()}

[OUTCOMES]
(What actually happened this turn, already decided by the engine. Narrate
these -- do not contradict them, and do not invent HP/inventory/combat
results of your own. Anything marked "Refused" did not happen, no matter how
the player phrased their input.)

{self._outcomes_section(outcome_facts).rstrip()}

[CONTINUITY]
(This should normally be empty: outcomes are validated before you narrate
them, not after. Anything here is a defensive fallback for a state change the
engine could not decide at all -- treat it the same as [OUTCOMES].)

{self._corrections_section().rstrip()}

[SCENE]
{player_input}"""
