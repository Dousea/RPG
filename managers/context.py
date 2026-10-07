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

import logging
import re
from collections.abc import Iterable
from datetime import date

from data.clock import TIMES_OF_DAY
from data.exercises import (
    BARBELL_ID,
    DUMBBELL_ID,
    EXERCISE_MINUTES_MAX,
    EXERCISE_MINUTES_MIN,
    EXERCISE_MINUTES_STEP,
    EXERCISES,
)
from data.items import ITEMS, item_condition_word, wetness_word
from data.memory import LAST_SCENE_MAX_CHARS
from data.names import SKIN_TONE_WORDS
from data.occupations import OCCUPATIONS
from data.skills import SKILLS
from data.social import TALK_APPROACHES
from data.status_effects import STATUS_EFFECT_MAX_LEVEL
from data.time_costs import MAX_PLAN_ACTIONS
from data.traits import TRAITS
from managers.barriers import barriers_of, state_word
from managers.body import open_wounds
from managers.climate import describe_weather
from managers.combat import held_entity
from managers.first_aid import bandage_items, disinfectant_items, part_word
from managers.game import GameManager
from managers.loot import corpse_views, perceived_corpses
from managers.skills import level_word
from managers.stats.status_effects import active_status_effects
from managers.story import visible_topics
from managers.zombies import threat_views
from modules.action.parser import SceneKey, available_verbs
from modules.action.schema import JsonObject, SceneChoices, build_plan_schema
from modules.entity.barrier import BarrierEntity
from modules.entity.item import ItemEntity
from modules.item import ClothingItem, MedicalItem, StackItem
from modules.quest import QuestStatus

logger = logging.getLogger(__name__)

ZOMBIE_ID = re.compile(r"\bz\d+\b")
CORPSE_ID = re.compile(r"\bc\d+\b")

# Narrator-only: it names a prompt block, so the event log never stores it.
NOTHING_DONE_FACT = (
    "{name} only looks around and thinks. Nothing else in [SCENE] happens: no one is "
    "spoken to, and nothing is used, taken, opened or locked."
)


def zombie_ids_to_words(fact: str) -> str:
    """The fact with every zombie id read as "the zombie" and every corpse id as "the body"."""
    worded = CORPSE_ID.sub("the body", ZOMBIE_ID.sub("the zombie", fact))
    return "T" + worded[1:] if ZOMBIE_ID.match(fact) or CORPSE_ID.match(fact) else worded


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
            if npc.following:
                lines.append(f"   Following {self._name}")
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

    @staticmethod
    def _summary_section(summaries: list[str]) -> str:
        if not summaries:
            return "(No summary available yet)"
        return "\n\n".join(summaries)

    @staticmethod
    def _events_section(events_newest_first: list[str]) -> str:
        if not events_newest_first:
            return "(No recent events)"
        return "\n".join(f" - {event}" for event in reversed(events_newest_first))

    def _last_scene_section(self) -> str:
        """The stored story's last paragraph, cut to the limit on a line or sentence boundary.

        Empty without a story. Only the last paragraph, because a narrator handed the
        whole story copies it, contradictions included, instead of narrating this turn.
        """
        story = self.manager.memory.last_story.strip().split("\n\n")[-1].strip()
        if len(story) > LAST_SCENE_MAX_CHARS:
            window = story[: LAST_SCENE_MAX_CHARS + 1]
            ends = [m.end() for m in re.finditer(r"[.!?][\"')]*(?=\s)", window)]
            ends += [i for i, char in enumerate(window) if char == "\n"]
            story = story[: max(ends, default=LAST_SCENE_MAX_CHARS)].rstrip()
        if not story:
            return ""
        return (
            "[LAST SCENE]\n"
            "(Where the story the player last read left off. The outcomes and the current "
            "blocks win where it disagrees.)\n\n"
            f"{story}\n\n"
        )

    def _last_turn_section(self) -> str:
        log = self.manager.memory.full_event_log
        if not log:
            return ""
        return f"[LAST TURN]\n{zombie_ids_to_words(log[-1])}\n\n"

    def _corrections_section(self) -> str:
        corrections = self.manager.narrative.pending_corrections
        if not corrections:
            return "(Nothing to correct)"
        return "\n".join(f" - {correction}" for correction in corrections)

    def _condition_section(self, *, narrator: bool = False) -> str:
        """Every status effect at level 1 or above, by name and level, and what the body is doing.

        Never a raw stat. The narrator also hears whether the character sleeps and any
        condition an item put on them.
        """
        player = self.manager.player
        parts = [
            f"{name} ({level}/{STATUS_EFFECT_MAX_LEVEL})"
            for _, level, name in active_status_effects(player)
        ]
        if narrator and player.asleep:
            parts.append("asleep")
        if player.sneaking:
            parts.append("sneaking")
        if narrator:
            parts.extend(condition.value for condition in player.conditions)
        line = ", ".join(parts) or "Fine"
        line += "".join(f"\n{part_line}" for part_line in self._part_lines())
        held = held_entity(player)
        if held is not None:
            line += f"\nHolding: {held.item.name.lower()} ({item_condition_word(held)})"
        return line

    def _part_lines(self) -> list[str]:
        """One line per injured or bandaged part, in words: wounds, bleeding, bandage, infection."""
        lines: list[str] = []
        for part, state in self.manager.player.body.items():
            if not (state.injured or state.bandaged):
                continue
            words = open_wounds(state)
            if state.bleeding:
                words.append("bleeding")
            if state.bandaged:
                words.append("bandaged (dirty)" if state.bandage_life <= 0 else "bandaged")
            elif state.infected_wound and state.wounded:
                words.append("infected")
            lines.append(f"{part_word(part)}: {', '.join(words)}")
        return lines

    def _threats_section(self) -> str:
        """The zombies the player perceives, by distance and what they are doing; no ids."""
        lines: list[str] = []
        for view in threat_views(self.manager):
            if view.zombie_id is None:
                lines.append(f" - {view.state_word}")
            else:
                lines.append(f" - a zombie, {view.distance_word}, {view.state_word}")
        return "\n".join(lines) or "None"

    def _barrier_line(self, barrier: BarrierEntity, pounding: set[str]) -> str:
        """One barrier of the player's zone in words: its state, its planks and what pounds on it."""
        manager = self.manager
        here = manager.player.current_location_id
        beyond = manager.world.locations[barrier.far_side(here)].name
        parts = [state_word(barrier)]
        for side, where in ((here, "on this side"), (barrier.far_side(here), "on the far side")):
            count = barrier.plank_count(side)
            if count:
                parts.append(f"{count} plank{'s' if count != 1 else ''} {where}")
        if barrier.barrier_id in pounding:
            parts.append("something pounding on the other side")
        return f" - {barrier.name} (to {beyond}): {'; '.join(parts)}"

    def _barriers_section(self) -> str:
        """[DOORS AND WINDOWS]: one line per barrier of the player's zone, in words and counts only."""
        manager = self.manager
        barriers = barriers_of(manager.world, manager.player.current_location_id)
        if not barriers:
            return "None"
        pounding = {
            view.barrier_id for view in threat_views(manager) if view.barrier_id is not None
        }
        return "\n".join(self._barrier_line(barrier, pounding) for barrier in barriers)

    def _in_view_section(self) -> str:
        """[IN VIEW] after the outcomes: every perceived zombie, then everyone present.

        Placed last so a small narrator that skims the scene blocks still shows them.
        """
        manager = self.manager
        threats = self._threats_section().splitlines() if threat_views(manager) else []
        people = [
            f" - {npc.name}" for npc in manager.npcs_in_location(manager.player.current_location_id)
        ]
        if not threats and not people:
            return ""
        lines = "\n".join(threats + people)
        return f"[IN VIEW]\n(Who and what the story must show this turn, however briefly.)\n{lines}\n\n"

    def _corpses_section(self, *, with_id: bool) -> str:
        """The bodies the player can see, in words: the parser gets ids to aim SEARCH at."""
        lines = [view.line(with_id=with_id) for view in corpse_views(self.manager)]
        return "\n".join(lines) or "None"

    def _parser_threats_section(self) -> str:
        """Seen zombies by id and distance only, so the parser can aim ATTACK at one."""
        lines = [
            f" - {view.zombie_id} ({view.distance_word})"
            for view in threat_views(self.manager)
            if view.zombie_id is not None
        ]
        return "\n".join(lines) or "None"

    def _weather_section(self) -> str:
        """The outdoor weather in words, and whether the player is sheltered from it."""
        manager = self.manager
        sample = manager.climate.sample(manager.narrative.minutes)
        return describe_weather(sample, manager.current_location.indoors)

    @staticmethod
    def _outcomes_section(outcome_facts: list[str] | None) -> str:
        if not outcome_facts:
            return "(No actions were taken this turn)"
        return "\n".join(f" - {zombie_ids_to_words(fact)}" for fact in outcome_facts)

    def _discovered_flags_section(self) -> str:
        """Only flags the player has discovered, so the engine can hold ground truth the
        player doesn't know yet: setting a flag and discovering it are separate acts."""
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

    def scene_keys(self) -> frozenset[SceneKey]:
        """The kinds of thing the scene holds, from the same state the blocks render."""
        manager = self.manager
        player = manager.player
        keys: set[SceneKey] = set()
        goals = manager.narrative.goals
        if any(goals.values()):
            keys.add("goals")
        if manager._ground_items():
            keys.add("items_here")
        reachable = [*player.inventory, *manager._ground_items()]
        if reachable:
            keys.add("carried")
        if held_entity(player) is not None:
            keys.add("held")
        if any(isinstance(entity.item, ClothingItem) for entity in reachable):
            keys.add("wearable")
        if self._worn_section() != "Nothing":
            keys.add("worn")
        if manager.npcs_in_location(player.current_location_id):
            keys.add("npcs_here")
        if any(view.zombie_id is not None for view in threat_views(manager)):
            keys.add("threats")
        bodies = perceived_corpses(manager)
        if bodies:
            keys.add("corpses")
        if any(body.searched and body.contents for body in bodies):
            keys.add("loot")
        if any(state.injured or state.bandaged for state in player.body.values()):
            keys.add("hurt")
        if barriers_of(manager.world, player.current_location_id):
            keys.add("barriers")
        return frozenset(keys)

    def scene_choices(self) -> SceneChoices:
        """The closed sets of names the scene offers, as the validator would accept them.

        Carried and wearable names include the floor's, since a plan may take an item first.
        """
        manager = self.manager
        player = manager.player
        ground = manager._ground_items()
        npcs = manager.npcs_in_location(player.current_location_id)
        held = held_entity(player)
        bodies = perceived_corpses(manager)
        return SceneChoices(
            items_here=_names(ground),
            carried=tuple(dict.fromkeys(_names([*player.inventory, *ground]))),
            held=_names([held] if held is not None else []),
            wearable=_names(
                entity
                for entity in [*player.inventory, *ground]
                if isinstance(entity.item, ClothingItem)
            ),
            worn=_names(entity for _, entity in player.worn_outer_to_inner()),
            npcs=tuple(npc.name for npc in npcs),
            zombie_ids=tuple(
                view.zombie_id for view in threat_views(manager) if view.zombie_id is not None
            ),
            corpse_ids=tuple(body.corpse_id for body in bodies),
            corpse_items=tuple(
                entity.item.name for body in bodies if body.searched for entity in body.contents
            ),
            hurt_parts=tuple(
                part_word(part)
                for part, state in player.body.items()
                if state.injured and not state.bandaged
            ),
            bandaged_parts=tuple(
                part_word(part) for part, state in player.body.items() if state.bandaged
            ),
            bandages=_names(bandage_items(player)),
            disinfectants=_names(disinfectant_items(player)),
            npc_items=_names(entity for npc in npcs for entity in npc.inventory),
            topics=tuple(topic.topic_id for npc in npcs for topic in visible_topics(manager, npc)),
            barriers=tuple(
                barrier.name for barrier in barriers_of(manager.world, player.current_location_id)
            ),
            exercises=tuple(exercise.name for exercise in EXERCISES.values()),
            exercise_minutes=tuple(
                range(EXERCISE_MINUTES_MIN, EXERCISE_MINUTES_MAX + 1, EXERCISE_MINUTES_STEP)
            ),
            times_of_day=TIMES_OF_DAY,
        )

    def build_plan_schema(self) -> JsonObject:
        """The JSON schema the parser's reply is constrained to, for the scene the prompt shows."""
        return build_plan_schema(
            available_verbs(self.scene_keys()), self.scene_choices(), MAX_PLAN_ACTIONS
        )

    def _available_actions_section(self) -> str:
        """The verbs the scene lists, each with its argument kinds, gloss and closed labels."""
        lines: list[str] = []
        for verb in available_verbs(self.scene_keys()):
            kinds = "".join(f" <{kind}>" for kind in verb.target_kinds)
            gloss = self._ask_gloss() if verb.name == "ASK" else verb.gloss
            lines.append(f"- {verb.name}{kinds} -- {gloss}")
            if verb.name == "TALK":
                lines.extend(f"  {label}: {row.gloss}" for label, row in TALK_APPROACHES.items())
        return "\n".join(lines)

    def _ask_gloss(self) -> str:
        """The ASK requests this scene can fill, so the model never picks one it can't complete."""
        choices = self.scene_choices()
        requests = ["follow", "stay"]
        if choices.npc_items:
            requests.append("give <item> (an item the NPC carries)")
        if choices.topics:
            requests.append("about <topic> (a topic listed under the NPC)")
        return f"ask an NPC to: {', '.join(requests)}; any other question is TALK chat"

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
        return f"""
Current Location: {manager.current_location.name}
Specific spot: {manager.player.current_place or "(nowhere in particular)"}
Description: {manager.current_location.description}
Sheltered: {"yes" if manager.current_location.indoors else "no"}
Flags: {self._discovered_flags_section()}
"""

    @staticmethod
    def _deep_memory_section(deep_memories: list[str] | None) -> str:
        if not deep_memories:
            return "(No relevant memories surfaced)"
        return _lines(f" - {memory}" for memory in deep_memories)

    def _outbreak_line(self) -> str:
        day = self.manager.outbreak_day()
        return "before the outbreak" if day is None else f"outbreak day {day}"

    def _time_and_weather_section(self) -> str:
        manager = self.manager
        narrative = manager.narrative
        looks = manager.player.appearance
        weekday = date.fromisoformat(manager.world.date).strftime("%A")
        return f"""Day {narrative.day}, {narrative.time_of_day.capitalize()} -- {manager.world.time}, {weekday} {manager.world.date}
It is {self._outbreak_line()}.
(The weather outside, in words. When {self._name} is sheltered, rain and wind do not
reach {looks.object}, though {looks.subject} can still hear them.)
{self._weather_section()}"""

    def _parser_npcs_section(self) -> str:
        """NPC names, whether each follows the player, and what each can be asked about."""
        manager = self.manager
        npcs = manager.npcs_in_location(manager.player.current_location_id)
        if not npcs:
            return "No one else is here."
        lines: list[str] = []
        for npc in npcs:
            lines.append(f" - {npc.name}{' (following you)' if npc.following else ''}")
            held = ", ".join(entity.item.name for entity in npc.inventory)
            if held:
                lines.append(f"   Holds: {held}")
            for topic in visible_topics(manager, npc):
                lines.append(f"   Topic {topic.topic_id}: {topic.gloss}")
        return "\n".join(lines)

    def _worn_section(self) -> str:
        worn = [entity.item.name for _, entity in self.manager.player.worn_outer_to_inner()]
        return ", ".join(worn) if worn else "Nothing"

    # === Parser prompt ===

    def build_parser_prompt(self, player_input: str) -> str:
        """Assemble the minimal-context prompt for the intent parser call.

        The parser only needs to know what is reachable/visible right now to
        propose actions -- it does not narrate, so it gets none of the prose
        context (memory, summaries, relationship bands) the narrator needs.
        """
        manager = self.manager
        player = manager.player
        held = held_entity(player)
        carried = [f" - {entity.item.name}{_marks(entity)}" for entity in player.inventory]
        if held is not None:
            carried.insert(0, f" - {held.item.name} (in hands)")
        inventory_str = "\n".join(carried) or "Empty"
        looks = player.appearance
        return f"""[CHARACTER]
{player.name} ({looks.subject}/{looks.object}). Say "{looks.subject}" and "{looks.object}", never "they", for this character.

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
{self._parser_npcs_section()}

[THREATS]
{self._parser_threats_section()}

[CORPSES]
{self._corpses_section(with_id=True)}

[DOORS AND WINDOWS]
{self._barriers_section()}

[INVENTORY]
{inventory_str}

[WORN]
{self._worn_section()}

[CONDITION]
{self._condition_section()}

[WEATHER]
{self._weather_section()}

[EXERCISES]
{self._exercise_section()}

[AVAILABLE ACTIONS]
{self._available_actions_section()}

{self._last_turn_section()}[PLAYER INPUT]
{player_input}"""

    # === Narrator prompt ===

    def build_narrator_prompt(
        self,
        player_input: str,
        outcome_facts: list[str] | None = None,
        deep_memories: list[str] | None = None,
        max_chars: int | None = None,
    ) -> str:
        """Assemble the full LLM prompt for the narrator call.

        Memory comes first, so current state and this turn's outcomes, which come
        later, win. `outcome_facts` are what the Action Validator and Simulation Core
        already decided this turn; the narrator describes them and decides nothing.
        `deep_memories` are semantically retrieved past events supplied by the memory layer.
        Over `max_chars`, memory is dropped until it fits: deep memories (last first),
        summaries (oldest first), [LAST SCENE], then recent events (oldest first, never
        the newest). Current state, [OUTCOMES] and the player's input are never dropped.
        """
        deep = list(deep_memories or [])
        summaries = list(self.manager.memory.summaries)
        events = list(self.manager.memory.recent_events)
        show_scene = True
        dropped: dict[str, int] = {}
        character = self._character_section()
        last_scene = self._last_scene_section()
        current = self._narrator_current_state(player_input, outcome_facts)

        def render() -> str:
            return self._render_narrator(
                character, deep, summaries, events, last_scene if show_scene else "", current
            )

        prompt = render()
        while max_chars is not None and len(prompt) > max_chars:
            if deep:
                deep.pop()
                kind = "deep memory entries"
            elif summaries:
                summaries.pop(0)
                kind = "summaries"
            elif show_scene and last_scene:
                show_scene = False
                kind = "last scene"
            elif len(events) > 1:
                events.pop()
                kind = "recent events"
            else:
                logger.warning(
                    "Narrator prompt is still %d characters over its %d budget with all "
                    "memory dropped.",
                    len(prompt) - max_chars,
                    max_chars,
                )
                break
            dropped[kind] = dropped.get(kind, 0) + 1
            prompt = render()
        if dropped:
            logger.warning(
                "Narrator prompt over budget; dropped %s.",
                ", ".join(f"{count} {kind}" for kind, count in dropped.items()),
            )
        return prompt

    def _render_narrator(
        self,
        character: str,
        deep_memories: list[str],
        summaries: list[str],
        events_newest_first: list[str],
        last_scene: str,
        current: str,
    ) -> str:
        return f"""[CHARACTER]
{character}

[DEEP MEMORY]
(Past events recalled as relevant to what the player just did)

{self._deep_memory_section(deep_memories)}

[SUMMARY OF PAST EVENTS]
(A narrative overview of the long-term past)

{self._summary_section(summaries).rstrip()}

[RECENT EVENTS]
(What just happened, oldest first; the last entry is the most recent)

{self._events_section(events_newest_first).rstrip()}

{last_scene}{current}"""

    def _narrator_current_state(self, player_input: str, outcome_facts: list[str] | None) -> str:
        """The narrator prompt from [TIME AND WEATHER] to the player's input."""
        return f"""[TIME AND WEATHER]
{self._time_and_weather_section()}

[CURRENT LOCATION]
{self._location_section()}

[ITEMS IN CURRENT LOCATION]

{self._current_items_section().rstrip()}

[NEARBY LOCATIONS]

{self._nearby_locations_section().rstrip()}

[DOORS AND WINDOWS]
(The doors and windows here and what is happening at them. Describe only what is listed.)
{self._barriers_section()}

[CONDITION]
({self._name}'s body and mood right now, as levels out of 4. Describe them; do not
give them numbers.)
{self._condition_section(narrator=True)}

[QUESTS]
(What {self._name} is currently working toward, engine-tracked. [x] is complete.)

{self._quests_section().rstrip()}

[NPCS PRESENT]

{self._npcs_present_section().rstrip()}

[THREATS]
(The zombies {self._name} can see or hear, and what each is doing. Describe only
these; never invent a zombie that is not listed, and never give a zombie a
number.)
{self._threats_section()}

[CORPSES]
(The dead {self._name} can see, and whether {self.manager.player.appearance.subject} has been through them. Describe
only these; a body is only ever dead.)
{self._corpses_section(with_id=False)}

[OUTCOMES]
(What actually happened this turn, already decided by the engine. Narrate
these -- do not contradict them, and do not invent HP/inventory/combat
results of your own. Anything marked "Refused" did not happen, no matter how
the player phrased their input.)

{self._outcomes_section(outcome_facts).rstrip()}

{self._in_view_section()}[CONTINUITY]
(This should normally be empty: outcomes are validated before you narrate
them, not after. Anything here is a defensive fallback for a state change the
engine could not decide at all -- treat it the same as [OUTCOMES].)

{self._corrections_section().rstrip()}

[SCENE]
{player_input}"""


def _names(entities: Iterable[ItemEntity]) -> tuple[str, ...]:
    return tuple(entity.item.name for entity in entities)


def _lines(lines: Iterable[str]) -> str:
    return "\n".join(lines)


def _uses_left(entity: ItemEntity) -> str:
    """How many uses a multi-use medical item has left; empty for any other item."""
    if isinstance(entity.item, MedicalItem | StackItem) and entity.item.uses > 1:
        return f" ({entity.uses} left)"
    return ""


def _marks(entity: ItemEntity) -> str:
    return " (broken)" if entity.broken else _uses_left(entity)


def _with_condition(entity: ItemEntity) -> str:
    if isinstance(entity.item, MedicalItem):
        return f"{entity.item.name}{_uses_left(entity)}"
    return f"{entity.item.name} ({item_condition_word(entity)})"
