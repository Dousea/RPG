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

from collections.abc import Iterable

from data.exercises import BARBELL_ID, DUMBBELL_ID, EXERCISES
from data.items import ITEMS, item_condition_word, wetness_word
from data.names import SKIN_TONE_WORDS
from data.occupations import OCCUPATIONS
from data.skills import SKILLS
from data.status_effects import STATUS_EFFECT_MAX_LEVEL
from data.traits import TRAITS
from managers.climate import describe_weather
from managers.game import GameManager
from managers.skills import level_word
from managers.stats.status_effects import active_status_effects
from modules.entity.item import ItemEntity
from modules.quest import QuestStatus


class ContextBuilder:
    def __init__(self, manager: GameManager):
        self.manager = manager

    @property
    def _name(self) -> str:
        return self.manager.player.appearance.forename

    def _appearance_line(self) -> str:
        looks = self.manager.player.appearance
        parts = [
            f"{SKIN_TONE_WORDS.get(looks.skin_tone, 'unremarkable')} skin",
            "bald"
            if looks.hair_style == "bald"
            else f"{looks.hair_style} {looks.hair_colour} hair",
        ]
        if looks.beard_style:
            parts.append(f"a {looks.beard_style}")
        return ", ".join(parts)

    def _occupation_line(self) -> str:
        player = self.manager.player
        occupation = OCCUPATIONS.get(player.occupation_id)
        return player.job_title or (occupation.name if occupation else "None")

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
        """The whole zone roster, one line per zone with its aliases.

        The parser can only aim MOVE_TO at a zone it has been told exists --
        this is that roster. It lives on the parser prompt (not the
        narrator's) because the parser is what emits MOVE_TO. Aliases are
        listed too, since naming a landmark (not just the zone's own name)
        is how the model actually reaches a zone in practice.
        """
        lines = []
        for location in self.manager.world.locations.values():
            aliases = ", ".join(location.aliases) if location.aliases else "none"
            lines.append(f" - {location.name} (aliases: {aliases})")
        return "\n".join(lines)

    def _npcs_present_section(self) -> str:
        """NPCs present, with how each one currently regards the player.

        Affinity and trust go out as bands, never as the underlying integers
        -- the player can tell that Emma has warmed to them; they cannot read
        `affection +37` off her face, and a narrator given the number
        narrates to it. NPC goals are shown as visible intent (what the player
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
                f" - {npc.name}{f' ({npc.age})' if npc.age is not None else ''}: {npc.description}"
            )
            lines.append(f"   Disposition: {disposition} (trust: {trust_level})")
            if npc.status:
                lines.append(f"   Status: {', '.join(npc.status)}")
            if npc.personality:
                lines.append(f"   Personality: {', '.join(npc.personality)}")
            if npc.goals:
                lines.append(f"   Visible intent: {', '.join(npc.goals)}")
            if npc.notes:
                # ADD_RELATIONSHIP_NOTE writes the player's read on someone, not the
                # NPC's private thoughts, so this side of the firewall is where
                # it belongs -- but say whose impressions they are.
                lines.append(f"   {self._name}'s impressions: {npc.notes}")
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

    def _condition_section(self) -> str:
        """Every status effect at level 1 or above, by name and level; never a raw stat."""
        active = active_status_effects(self.manager.player)
        if not active:
            return "Fine"
        return ", ".join(f"{name} ({level}/{STATUS_EFFECT_MAX_LEVEL})" for _, level, name in active)

    def _weather_section(self) -> str:
        """The outdoor weather in words, and whether the player is sheltered from it."""
        manager = self.manager
        sample = manager.climate.sample(manager.narrative.minutes)
        return describe_weather(sample, manager.current_location.indoors)

    @staticmethod
    def _outcomes_section(outcome_facts: list[str] | None) -> str:
        if not outcome_facts:
            return "(No actions were taken this turn)"
        return "\n".join(f" - {fact}" for fact in outcome_facts)

    def _discovered_flags_section(self) -> str:
        """Only flags the player has actually discovered -- doc 11's complaint was
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
        what the player is working toward so it can weave it into prose. Only
        ACTIVE quests render; a quest that just completed this turn already
        shows up in [OUTCOMES], and there is no reason to keep prompting the
        narrator about one that's done.
        """
        active = [
            quest for quest in self.manager.quests.values() if quest.status == QuestStatus.ACTIVE
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

    def _character_section(self) -> str:
        player = self.manager.player
        narrative = self.manager.narrative
        equipment = (
            f" - {slot.name}: {_with_condition(entity) if entity else 'None'}"
            for slot, entity in player.equipment.items()
        )
        looks = player.appearance
        trait_lines = (
            f" - {TRAITS[t].name}: {TRAITS[t].description}" for t in player.traits if t in TRAITS
        )
        return f"""
Name: {player.name}
Pronouns: {looks.subject}/{looks.object}
Occupation: {self._occupation_line()}
Appearance: {self._appearance_line()}
Backstory: {looks.backstory or "None"}
Skills: {self._skills_line()}
Conditions: {", ".join(condition.name for condition in player.conditions) or "None"}
Status: {", ".join(narrative.player_status) or "None"}
Goals: {self._goals_line() or "None"}
Inventory: {_lines(f" - {_with_condition(entity)}" for entity in player.inventory) or "Empty"}
Equipment: {_lines(equipment) or "None"}
Wearing: {self._outfit_line()}
Traits: {_lines(trait_lines) or "None"}
"""

    def _skills_line(self) -> str:
        """Skills from level 1 up, each with a word for its level; never a number."""
        player = self.manager.player
        parts = [
            f"{skill.name} ({level_word(state.level)})"
            for skill in SKILLS.values()
            if (state := player.skills.get(skill.id)) is not None and state.level >= 1
        ]
        return ", ".join(parts) or "None"

    def _exercise_section(self) -> str:
        """The exercises the parser may propose, and which gym items are carried."""
        carried = {entity.item.id for entity in self.manager.player.inventory}
        items = [
            f"a {noun}"
            for item_id, noun in ((BARBELL_ID, "barbell"), (DUMBBELL_ID, "dumbbell"))
            if item_id in carried
        ]
        names = ", ".join(
            f"{e.name} (needs a {ITEMS[e.item_id].name.lower()})" if e.item_id else e.name
            for e in EXERCISES.values()
        )
        return f"{names}\nCarrying: {' and '.join(items) or 'nothing to lift'}"

    def _outfit_line(self) -> str:
        """Worn items outer to inner, with a wetness word for damp ones, never a number."""
        pieces = []
        for _, entity in self.manager.player.worn_outer_to_inner():
            word = wetness_word(entity.wetness)
            name = entity.item.name.lower()
            pieces.append(f"{word} {name}" if word else name)
        return ", ".join(pieces) or "Nothing"

    def _goals_line(self) -> str:
        goals = self.manager.narrative.goals
        line = ""
        if goals.get("short_term"):
            line += f"Short-term: {', '.join(goals['short_term'])}. "
        if goals.get("long_term"):
            line += f"Long-term: {', '.join(goals['long_term'])}."
        return line

    def _location_section(self) -> str:
        manager = self.manager
        narrative = manager.narrative
        return f"""
Current Location: {manager.current_location.name}
Specific spot: {manager.player.current_place or "(nowhere in particular)"}
Description: {manager.current_location.description}
Day {narrative.day}, {narrative.time_of_day.capitalize()} -- {manager.world.time}, {manager.world.date}
Apocalypse Stage: {narrative.apocalypse_stage}
Flags: {self._discovered_flags_section()}
"""

    @staticmethod
    def _deep_memory_section(deep_memories: list[str] | None) -> str:
        if not deep_memories:
            return "(No relevant memories surfaced)"
        return _lines(f" - {memory}" for memory in deep_memories)

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
        equipped = [entity.item.name for entity in player.equipment.values() if entity is not None]
        equipped += [entity.item.name for _, entity in player.worn_outer_to_inner()]
        equipped_str = ", ".join(equipped) if equipped else "Nothing"
        npc_names = ", ".join(
            npc.name for npc in manager.npcs_in_location(player.current_location_id)
        )

        looks = player.appearance
        return f"""[CHARACTER]
{player.name} ({looks.subject}/{looks.object}), {self._occupation_line()}. Say "{looks.subject}" and "{looks.object}", never "they", for this character.

[LOCATION]
{manager.current_location.name}: {manager.current_location.description}
Specific spot: {player.current_place or "(nowhere in particular)"}

[EXITS]
{self._nearby_locations_section().rstrip()}

[ZONES]
(The world is these {len(manager.world.locations)} zones, each listed below
with its aliases. Naming a zone or one of its listed aliases/landmarks moves
{self._name} there, walking through connecting zones as needed. `in`/`out` follow
the zone's own exits. Anything not listed here is a spot inside the zone {looks.subject}
is already in, which is normal and expected. A locked door stops {looks.object} at the
door rather than refusing the move.)

{self._zones_section().rstrip()}

[ITEMS HERE]
{self._current_items_section().rstrip()}

[NPCS HERE]
{npc_names if npc_names else "No one else is here."}

[INVENTORY]
{inventory_str}

[CONDITION]
{self._condition_section()}

[WEATHER]
{self._weather_section()}

[EQUIPPED]
{equipped_str}

[EXERCISES]
{self._exercise_section()}

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
        looks = self.manager.player.appearance
        return f"""[CHARACTER]
{self._character_section()}

[CONDITION]
({self._name}'s body and mood right now, as levels out of 4. Describe them; do not
give them numbers.)
{self._condition_section()}

[DEEP MEMORY]
(Past events recalled as relevant to what the player just did)

{self._deep_memory_section(deep_memories)}

[CURRENT LOCATION]
{self._location_section()}

[WEATHER]
(The weather outside, in words. When {self._name} is sheltered, rain and wind do not
reach {looks.object}, though {looks.subject} can still hear them.)
{self._weather_section()}

[ITEMS IN CURRENT LOCATION]

{self._current_items_section().rstrip()}

[NEARBY LOCATIONS]

{self._nearby_locations_section().rstrip()}

[NPCS PRESENT]

{self._npcs_present_section().rstrip()}

[QUESTS]
(What {self._name} is currently working toward, engine-tracked. [x] is complete.)

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


def _lines(lines: Iterable[str]) -> str:
    return "\n".join(lines)


def _with_condition(entity: ItemEntity) -> str:
    return f"{entity.item.name} ({item_condition_word(entity)})"
