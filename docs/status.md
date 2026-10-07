# Implementation Status

This document maps every mechanic and every architecture and design document
to the code that implements it, and says plainly what does not exist yet.

`architecture/` describes how the running system is built; a Partial banner
says where a document's built part stops. `design/` holds intent that is not
built: read it as a target, not as a description of the running program.
`mechanics/` holds the game rules as built.

## Status vocabulary

| Status | Meaning |
| --- | --- |
| **Implemented** | The document describes code that exists and runs. |
| **Partial** | Some of it exists; the document says where the code stops. |
| **Planned** | Design intent. No code. Preserved deliberately as a target. |

## Mechanics

Each mechanic is described by a document in `docs/mechanics/`. These describe
what the game now does.

| Id | Mechanic | Status | Code |
| --- | --- | --- | --- |
| `clock` | [Game Clock and Action Time](mechanics/clock.md) | Implemented | `data/world/clock.py`, `data/time_costs.py`, `managers/game.py`, `managers/simulation.py`, `managers/validator.py`, `modules/action/parser.py` |
| `survival-stats` | [Survival Stats](mechanics/survival-stats.md) | Implemented | `modules/body/stats.py`, `modules/units.py`, `data/body/survival.py`, `data/body/status_effects.py`, `managers/body/stats/status_effects.py`, `managers/body/stats/drivers.py`, `managers/body/stats/engine.py`, `managers/simulation.py`, `managers/validator.py`, `adapters/save/codec.py` |
| `status-effects` | [Status Effects and Consumption](mechanics/status-effects.md) | Implemented | `modules/body/stats.py`, `modules/item.py`, `data/body/status_effects.py`, `data/items.py`, `managers/body/stats/status_effects.py`, `managers/body/stats/engine.py`, `managers/simulation.py`, `managers/context.py`, `adapters/engine.py`, `adapters/save/codec.py` |
| `weather` | [Weather](mechanics/weather.md) | Implemented | `modules/world/simplex.py`, `modules/world/weather.py`, `modules/world/location.py`, `data/world/climate.py`, `data/world/locations.py`, `managers/world/climate.py`, `managers/simulation.py`, `managers/context.py`, `adapters/engine.py`, `adapters/save/codec.py` |
| `clothing` | [Clothing](mechanics/clothing.md) | Implemented | `modules/body/parts.py`, `modules/item.py`, `modules/entity/player.py`, `modules/entity/item.py`, `data/clothing/locations.py`, `data/clothing/coverage.py`, `data/items.py`, `data/time_costs.py`, `managers/validator.py`, `managers/simulation.py`, `managers/context.py`, `adapters/engine.py`, `adapters/save/codec.py` |
| `body-temperature` | [Body Temperature, Wetness and Colds](mechanics/body-temperature.md) | Implemented | `modules/body/thermal.py`, `modules/body/stats.py`, `modules/world/location.py`, `modules/entity/player.py`, `data/body/thermal.py`, `data/world/climate.py`, `data/body/status_effects.py`, `data/character/traits.py`, `data/world/locations.py`, `managers/body/thermoregulator.py`, `managers/body/wetness.py`, `managers/body/cold.py`, `managers/world/climate.py`, `managers/body/stats/engine.py`, `managers/body/stats/drivers.py`, `managers/body/stats/status_effects.py`, `managers/simulation.py`, `adapters/save/codec.py` |
| `character-creation` | [Character Creation](mechanics/character-creation.md) | Implemented | `modules/character/appearance.py`, `modules/character/build.py`, `modules/character/definitions.py`, `modules/entity/player.py`, `data/character/occupations.py`, `data/character/traits.py`, `data/character/creation.py`, `data/clothing/selection.py`, `data/character/names.py`, `data/character/presets.py`, `managers/character/creation.py`, `managers/body/stats/drivers.py`, `managers/body/cold.py`, `managers/context.py`, `managers/game.py`, `adapters/creation_payload.py`, `adapters/engine.py`, `adapters/llm.py`, `adapters/save/codec.py`, `app.py`, `static/app.js` |
| `skills` | [Skills](mechanics/skills.md) | Implemented | `modules/character/skills.py`, `modules/character/exercise.py`, `modules/entity/player.py`, `modules/item.py`, `modules/resolution.py`, `modules/action/types.py`, `modules/action/parser.py`, `data/character/skills.py`, `data/character/exercises.py`, `data/items.py`, `data/time_costs.py`, `managers/character/skills.py`, `managers/character/exercise.py`, `managers/body/stats/drivers.py`, `managers/body/thermoregulator.py`, `managers/simulation.py`, `managers/validator.py`, `managers/character/creation.py`, `managers/game.py`, `managers/context.py`, `adapters/engine.py`, `adapters/llm.py`, `adapters/save/codec.py`, `static/app.js` |
| `zombies` | [Zombies](mechanics/zombies.md) | Implemented | `modules/entity/zombie.py`, `modules/world/location.py`, `modules/world/pace.py`, `modules/story/beats.py`, `modules/resolution.py`, `modules/action/types.py`, `modules/action/parser.py`, `data/zombies/lore.py`, `data/world/locations.py`, `data/time_costs.py`, `managers/zombies/population.py`, `managers/zombies/noise.py`, `managers/zombies/attack.py`, `managers/simulation.py`, `managers/validator.py`, `managers/context.py`, `adapters/engine.py`, `adapters/llm.py`, `adapters/save/codec.py`, `static/app.js` |
| `llm-contract` | [LLM Contract](mechanics/llm-contract.md) | Implemented | `modules/action/parser.py`, `modules/action/types.py`, `modules/action/words.py`, `modules/entity/npc.py`, `modules/world/location.py`, `modules/resolution.py`, `modules/story/social.py`, `modules/story/beats.py`, `data/story/social.py`, `data/story/topics.py`, `data/story/beats.py`, `data/time_costs.py`, `data/zombies/lore.py`, `data/story/quests.py`, `data/story/npcs.py`, `managers/story/social.py`, `managers/story/beats.py`, `managers/game.py`, `managers/validator.py`, `managers/simulation.py`, `managers/context.py`, `managers/story/check.py`, `data/story/check.py`, `adapters/llm.py`, `adapters/factcheck.py`, `adapters/engine.py`, `adapters/save/codec.py`, `static/app.js`, `evals/parser_cases.yaml`, `scripts/eval_parser.py` |
| `melee` | [Melee Combat](mechanics/melee.md) | Implemented | `modules/item.py`, `modules/entity/item.py`, `modules/entity/zombie.py`, `modules/entity/player.py`, `modules/action/parser.py`, `modules/action/types.py`, `modules/action/words.py`, `data/melee.py`, `data/items.py`, `data/time_costs.py`, `data/zombies/lore.py`, `managers/combat/melee.py`, `managers/combat/weapons.py`, `managers/zombies/population.py`, `managers/zombies/attack.py`, `managers/character/skills.py`, `managers/simulation.py`, `managers/validator.py`, `managers/context.py`, `adapters/engine.py`, `adapters/save/codec.py`, `static/app.js` |
| `health` | [Body-Part Health and Zombie Infection](mechanics/health.md) | Implemented | `modules/body/parts.py`, `modules/item.py`, `modules/entity/item.py`, `modules/entity/player.py`, `modules/events/modifier.py`, `modules/resolution.py`, `modules/action/types.py`, `modules/action/parser.py`, `modules/action/words.py`, `data/body/health.py`, `data/items.py`, `data/world/locations.py`, `data/time_costs.py`, `data/zombies/lore.py`, `managers/body/health.py`, `managers/body/first_aid.py`, `managers/zombies/attack.py`, `managers/zombies/population.py`, `managers/character/exercise.py`, `managers/events/pipeline.py`, `managers/body/stats/engine.py`, `managers/body/stats/status_effects.py`, `managers/simulation.py`, `managers/validator.py`, `managers/context.py`, `adapters/engine.py`, `adapters/save/codec.py`, `static/app.js` |
| `doors` | [Doors, Thumping and Barricades](mechanics/doors.md) | Implemented | `modules/entity/barrier.py`, `modules/world/location.py`, `modules/entity/zombie.py`, `modules/entity/player.py`, `modules/entity/object.py`, `modules/item.py`, `modules/entity/item.py`, `modules/resolution.py`, `modules/units.py`, `modules/action/types.py`, `modules/action/parser.py`, `modules/action/schema.py`, `modules/action/words.py`, `data/world/barriers.py`, `data/items.py`, `data/world/locations.py`, `data/time_costs.py`, `data/zombies/lore.py`, `data/character/skills.py`, `data/character/traits.py`, `managers/world/barriers.py`, `managers/world/barrier_use.py`, `managers/zombies/thumping.py`, `managers/zombies/population.py`, `managers/zombies/noise.py`, `managers/combat/melee.py`, `managers/character/skills.py`, `managers/body/stats/drivers.py`, `managers/body/stats/engine.py`, `managers/simulation.py`, `managers/validator.py`, `managers/context.py`, `adapters/engine.py`, `adapters/save/codec.py`, `static/app.js`, `templates/index.html` |
| `zombie-lifecycle` | [The Zombie Lifecycle](mechanics/zombie-lifecycle.md) | Implemented | `modules/entity/zombie.py`, `modules/entity/corpse.py`, `modules/world/location.py`, `modules/resolution.py`, `modules/action/types.py`, `modules/action/parser.py`, `modules/action/schema.py`, `modules/action/words.py`, `data/zombies/outfits.py`, `data/zombies/clothing.py`, `data/zombies/loot.py`, `data/zombies/lore.py`, `data/items.py`, `data/time_costs.py`, `managers/zombies/dress.py`, `managers/corpses/bodies.py`, `managers/corpses/search.py`, `managers/corpses/sickness.py`, `managers/combat/melee.py`, `managers/zombies/population.py`, `managers/zombies/attack.py`, `managers/body/stats/drivers.py`, `managers/simulation.py`, `managers/validator.py`, `managers/context.py`, `adapters/engine.py`, `adapters/save/codec.py`, `static/app.js`, `templates/index.html` |
| `carrying-and-loot` | [Carrying, Containers and Loot](mechanics/carrying-and-loot.md) | Implemented | `modules/world/room.py`, `modules/world/location.py`, `modules/item.py`, `modules/entity/item.py`, `modules/entity/player.py`, `modules/resolution.py`, `modules/action/types.py`, `modules/action/parser.py`, `modules/action/schema.py`, `modules/action/words.py`, `data/carry.py`, `data/items.py`, `data/body/status_effects.py`, `data/time_costs.py`, `data/loot/containers.py`, `data/loot/tables.py`, `data/loot/catalogue.py`, `data/world/locations.py`, `data/world/barriers.py`, `data/loot/items.py`, `data/zombies/outfits.py`, `data/zombies/lore.py`, `data/world/climate.py`, `managers/carry.py`, `managers/world/containers.py`, `managers/world/rooms.py`, `managers/corpses/search.py`, `managers/body/health.py`, `managers/character/exercise.py`, `managers/combat/melee.py`, `managers/zombies/attack.py`, `managers/body/stats/drivers.py`, `managers/body/stats/status_effects.py`, `managers/zombies/population.py`, `managers/simulation.py`, `managers/validator.py`, `managers/context.py`, `adapters/engine.py`, `adapters/save/codec.py`, `static/app.js`, `templates/index.html` |

## The central divergence (resolved for engine authority; still open for scale)

The design target inverts the real control flow. That inversion is now real
for the axis the engine-authority doc cares about — outcomes are decided before they are
narrated — at the scale the game actually runs at (eleven zones, three NPCs).

```text
DESIGNED (target docs)                BUILT (adapters/engine.py)

player input                           player input
    ↓                                      ↓
LLM parser → action plan               semantic recall (FAISS, for the narrator)
    ↓                                      ↓
entity resolution                      LLM call #1: parser → ACTIONS block
    ↓                                      ↓
validation (preconditions)             modules/action/parser.parse_action_plan
    ↓                                      ↓
SIMULATION decides outcome             managers/validator.ActionValidator
    ↓                                      ↓
events → bus → subsystems              managers/simulation.SimulationCore
    ↓                                      ↓
knowledge firewall                     managers/context.ContextBuilder
    ↓                                      ↓
context builder                        LLM call #2: narrator → STORY / OPTIONS
    ↓                                      ↓
LLM narrator → prose                   record event, reindex, summarize, save
```

Validation and simulation happen between the two LLM calls, not after the
second one — the narrator is handed an `[OUTCOMES]` block of already-decided
facts (movement, combat, item use, quest progress) and writes prose around
it. It cannot invent a different HP total, a different combat result, or an
NPC's location, because those were never its decision to begin with.
`[CONTINUITY]`/`NarrativeState.pending_corrections` still exist but are no
longer the normal path: `GameEngine.play` never writes to them. They are a
defensive fallback for the one case pre-narration validation can't catch —
an exception inside the Simulation Core itself.

What did **not** change: there is still no procedural world generation, no
simulation level-of-detail for distant NPCs, and no Story Director reacting
to arbitrary world state (the world-generation, simulation-lod and story docs — see below). The event/effect/
modifier pipeline (the traits-and-modifiers doc) is real now for combat and item use, but only
for the two event families that exist; it is not a general-purpose bus other
subsystems publish to. Closing *that* gap — scaling past a handful of zones —
is still the rewrite the world-generation, simulation-lod and story docs describe, not an increment on top of
this one.

## Document map

| Doc | Status | Implemented by | Gap |
| --- | --- | --- | --- |
| [Engine Authority](architecture/engine-authority.md) | Implemented (at current scale) | `managers/validator.py`, `managers/simulation.py`, `adapters/engine.py` `play()` | Player HP, inventory, movement, combat, time and quest completion are engine-decided before the narrator is called. Not implemented: hidden-info/faction-state depth beyond discovered flags, and everything the world-generation, simulation-lod, story, time-and-scheduling and zombie-survival docs would add if the world grew past a handful of zones. |
| [System Boundaries](design/system-boundaries.md) | Partial | `managers/events/pipeline.py` `broadcast_event`, `EVENT_TO_EFFECT_TYPES` | Combat and item-use events are constructed and dispatched, role-aware (a "damage taken" handler only fires for the actual target). This is direct dispatch to a fixed pair of event families, not a general publish/subscribe bus other subsystems can register against — the typed event taxonomy in this document is still aspirational. |
| [Intent Parsing](architecture/intent-parsing.md) | Partial | `modules/action/parser.py`, `adapters/llm.py` `query_parser` | A separate parser call proposes a typed `AnyAction` plan (`modules/action/parser.py`) before anything is decided, matching this document's intent. The reply is constrained to a per-turn JSON schema (`modules/action/schema.py`) with the text lines as a fallback when the server rejects it. Still missing: true entity-resolution ambiguity handling (04 is unchanged). |
| [Entity Resolution](architecture/entity-resolution.md) | Partial | `resolve_npc`, `resolve_location`, `_find_item_entity` | NPC resolution is still exact casefold matching on name or id only. Location resolution (`resolve_location`) now also matches connection direction, alias, and — as a last pass — whole words shared with a zone's name or aliases (a loose substring match is deliberately excluded). No description-based resolution, no ambiguity state, no clarification round trip, and items have no instance ids ([limitation](architecture/entity-resolution.md#limitation-items-have-no-instance-identity)). |
| [World Generation](design/world-generation.md) | Planned | `data/world/locations.py` | Eleven hand-written coarse zones (`zone_home`, `zone_building`, `zone_street`, `zone_bodega`, `zone_neighborhood`, two flats, a pharmacy, a clinic, a supermarket and a hardware store), each with aliases and a free-text `PlayerEntity.current_place` for where within the zone the player narratively is. Doors and windows between the zones, described by [`doors`](mechanics/doors.md) and [`carrying-and-loot`](mechanics/carrying-and-loot.md). No seed, no generator, no tiers, no travel nodes. A zone holds rooms and their containers ([`carrying-and-loot`](mechanics/carrying-and-loot.md)); there is no region or location hierarchy above the zone. Out of scope for the engine-authority work; see the note at the top of this document. |
| [Simulation LOD](design/simulation-lod.md) | Planned | — | Every location and NPC is always live in memory. There are fourteen of them (eleven zones, three NPCs). Out of scope for the engine-authority work. |
| [Story Architecture](architecture/story.md) | Partial | `modules/story/quest.py` `QuestState`, `data/story/quests.py`, `GameManager.quests` | Quest progress is now engine-tracked and engine-completed (`SimulationCore._advance_quests`, fired on a matching validated action, never on an LLM-declared verb) — but it is a flat objective-completion checklist, not the arc/objective/condition/event graph this document describes, and there is no Story Director reacting to world state. Deliberately thin; a real director is out of scope. One decided-but-unbuilt change is recorded in that document's *As Implemented* section: `discover:`/`npc_status:` objectives currently depend on names the *parser* invents, and need engine producers instead. |
| [Time and Scheduling](design/time-and-scheduling.md) | Planned | `data/world/clock.py`, `managers/game.py` `NarrativeState` | The player-facing minute clock is [`clock`](mechanics/clock.md). NPC and world scheduling, sub-tick frequencies and everything else in this document is not built. |
| [Zombie Survival](design/zombie-survival.md) | Partial | `managers/zombies/population.py`, `managers/zombies/noise.py` | Noise, light and visibility are [`zombies`](mechanics/zombies.md). No scavenging model. |
| [Combat and Stealth](design/combat-and-stealth.md) | Partial | `managers/combat/melee.py`, `managers/combat/weapons.py`, `managers/simulation.py`, `modules/events/event.py`, `modules/events/modifier.py` | Melee against zombies follows [`melee`](mechanics/melee.md), with clothing armour from [`zombie-lifecycle`](mechanics/zombie-lifecycle.md). `ATTACK` on an NPC resolves through the event/modifier pipeline with equipped-weapon damage, and "dealt" and "taken" trait reactions fire for any entity carrying an effect-bearing trait (the player's traits are ids and carry none). No stealth, no ranged distance or line of sight. |
| [Knowledge Firewall](architecture/knowledge-firewall.md) | Partial | `managers/context.py`, `NarrativeState.discovered_flags`, `NpcEntity.knowledge`/`.goals` | Affinity/trust are still banded, and world flags are now filtered too: a flag only reaches the narrator prompt once the engine has marked it discovered (a topic told), separately from setting its value. `NpcEntity.knowledge` exists but is deliberately never rendered (no dialogue system consumes it yet); NPC `status` and `notes` still go out unfiltered. The document's *As Implemented* section should be read alongside this. |
| [Data Model and Persistence](architecture/data-model.md) | Partial | `modules/`, `adapters/save/codec.py`, `modules/story/quest.py` | Exit requirements now exist as barriers (doors and windows on the connections between zones, [`doors`](mechanics/doors.md)), checked by `ActionValidator`; their state is saved. Persistence is still a full snapshot, not base + mutations, and quest state (see the story doc) is a flat checklist, not the model this document describes. |
| [Context and Memory](architecture/context-and-memory.md) | Partial | `managers/context.py` `ContextBuilder`, `adapters/memory.py` | The context builder is now its own module (`managers/context.py`), independently testable, and the parser gets a *separate, minimal* context from the narrator's full one — a step toward selectivity. It still sends the whole local world to the narrator every turn, and memory layers remain compressive (recent / vector-recalled / summarized), not spatial (global / zone / location / scene). The narrator prompt is held to a token budget by dropping memory (deep memory, summaries, last scene, older recent events, in that order). The semantic index re-embeds the whole log every turn; see [Semantic recall](architecture/context-and-memory.md#semantic-recall) for the fix. |
| [LLM Roles](architecture/llm-roles.md) | Partial | `adapters/llm.py` `query_parser`/`query_narrator` | Two calls, two roles, two system prompts — parser proposes actions only, narrator only narrates and no longer has an `ACTIONS:` section to fill at all. The narrator's *constraints* (don't invent HP/inventory/combat results) are stated in its system prompt and structurally reinforced (it has nothing to declare state through), but still not mechanically enforced against a malicious or careless model. |
| [Turn Loop](architecture/turn-loop.md) | Partial | `adapters/engine.py` `play()` | Real steps now: parser call → `parse_action_plan` → `ActionValidator` → `SimulationCore` → narrator call → record/reindex/summarize/save. Missing relative to the 15-step design: no separate entity-resolution stage (folded into the validator), no world/story/NPC/faction *rules* layer beyond quest advancement, no structured failure taxonomy beyond `Rejected`/`ParseFailure`. |
| [Determinism and Versioning](architecture/determinism-and-versioning.md) | Partial | `adapters/save/codec.py` `SCHEMA_VERSION` | No seeded randomness anywhere — combat damage jitter (`managers/combat/weapons.py`) and the LLM itself are both unseeded. `SCHEMA_VERSION` is 17 and any other version is discarded with no migration; it remains the sole version, with no generator, rules, combat or loot version. Explicitly out of scope for the engine-authority work. |
| [Observability and Security](architecture/observability-and-security.md) | Partial | `print()` calls in `engine.py`, `game.py`, `simulation.py` | Turn logging is unstructured stdout. No state diff, no context snapshot, no replayable trace. LLM output *is* validated and simulated before it mutates state, which is the security half of this document, and now happens before narration too. Structured tracing is out of scope for the engine-authority work. |
| [End-to-End Example](design/end-to-end-example.md) | Planned | — | Traces a turn through stages that do not exist. |
| [Principles](architecture/principles.md) | Partial | — | Principles 1, 2, 7 and 10 are honoured in spirit, and 3 ("events connect systems") and 6 ("knowledge is scoped") are now partly true for combat/item-use and world flags respectively. 4, 5, 8 and 9 remain unimplemented. |
| [Final Architecture](design/final-architecture.md) | Planned | — | The summary diagram of the design target. |
| [Relationships](architecture/relationships.md) | Implemented | `managers/story/relationship.py` | — |
| [Traits, Perks, Effects, Modifiers](architecture/traits-and-modifiers.md) | Implemented | `modules/events/effect.py`, `modules/events/modifier.py`, `managers/events/pipeline.py` | Pipeline is live: `SimulationCore` constructs `WeaponDealDamageEvent`/`WeaponTakeDamageEvent`/`ConsumeItemEvent`/`ApplyItemEvent`, and the event-to-handler matcher (previously a always-false string comparison) correctly routes them, role-aware. |
| [Runtime and Persistence](architecture/runtime-and-persistence.md) | Implemented | `config.py`, `adapters/save/codec.py`, `adapters/save/files.py`, `adapters/engine.py` | Schema is v17 (see [`clock`](mechanics/clock.md#saves)); `current_place`, `game_over` and `death_cause` are saved. Any other version is discarded and a new game starts; there is no migration. |
| [UI Layout](architecture/ui-layout.md) | Implemented | `templates/index.html`, `static/app.js`, `static/style.css`, `adapters/engine.py` `_snapshot`, `adapters/creation_payload.py` | The page, its three responsive layouts (8, 5 and 4 tabs) and the creation screen exist and are read-only. All eight screens show; item condition is a word, and the Health screen lists wounded parts in words. Fields of mechanics not built yet arrive with them. |

## Known issues

Discrepancies found while reconciling these documents against the code. The
first three were fixable where they stood and are fixed; the rest are structural,
and are recorded here so they are not rediscovered.

### Fixed

**One clock, not two.** `World.time` and `World.date` are a rendering of the one minute clock; see [`clock`](mechanics/clock.md).

**Relationship scores no longer reach the prompt as numbers.** Affinity goes out
as a `CharacterDisposition` and trust as a `CharacterTrust`, banded by
`RelationshipManager` — `Disposition: friendly (trust: solid)`, not
`affection +37, trust +42`. Orton can see that someone has warmed to him; he
cannot read an integer off their face, and a game master given the integer
narrates to it. `NpcEntity.notes` stay in the prompt but are now labelled
`Orton's impressions:`, which is what `ADD_RELATIONSHIP_NOTE` actually writes —
the old `Notes:` label was what made them look like NPC-private data.

### Fixed (engine authority)

**Narration and state no longer disagree in the normal case.** The turn loop
now makes two LLM calls: a parser proposes actions before any prose exists,
`ActionValidator`/`SimulationCore` decide what actually happens, and only then
is the narrator called — with an `[OUTCOMES]` block telling it exactly what
was decided, including any refusals. `[CONTINUITY]`/`pending_corrections`
still exist but `GameEngine.play` never writes to them anymore; they are a
defensive fallback for an exception inside the Simulation Core itself, not
the normal error path. The llm-roles doc's narrator constraints are now
structurally reinforced (the narrator has no `ACTIONS:` section to declare
state through at all) though still not mechanically enforced against a
malicious or careless model.

**Combat is no longer dead code.** `SimulationCore._resolve_attack` builds a
`WeaponDealDamageEvent`/`WeaponTakeDamageEvent` pair for every `ATTACK`
action, and the event-to-handler matcher (`EVENT_TO_EFFECT_TYPES` in
`managers/events/pipeline.py`) replaces the string-prefix comparison that used to make
`_event_matches_effect_handler` return `False` unconditionally — every effect-bearing
trait fires now, and only for
the correct side of the hit (a "damage taken" effect no longer fires for the
attacker just because they're also part of the event).

**The prompt leaks less.** World flags are now filtered the same way
relationship scores are: a flag only reaches the narrator once a
the engine has marked it discovered (a topic told), separate from the engine
setting its value. `NpcEntity.knowledge`/`.goals` exist as real fields.

### Fixed (zones)

**`MOVE_TO` no longer narrates the game into rooms that do not exist.**
The old three-room map couldn't back every place the game master's prose
reached, so a `MOVE_TO` for a room outside that set failed and the narrated
story silently diverged from the simulated state. `MOVE_TO` now resolves a
zone by id, display name, alias, or `in`/`out` connection (`resolve_location`),
walks the connection graph to reach a zone that isn't directly adjacent
(`GameManager.zone_path`), and — critically — never refuses: anything it
can't resolve to a zone becomes a free-text spot inside the zone the player
is already standing in (`ActionValidator._validate_move`). See the world-generation doc's row
above for the current map.

**Generic room nouns are spots, not zone aliases.** A word like "kitchen",
"bathroom", "office", or "upstairs" almost never names one particular zone,
so `data/world/locations.py`'s `aliases` lists no longer carry them at all —
naming one now lands Orton on a free-text spot in whatever zone he's already
in, instead of silently teleporting him to whichever zone happened to claim
that word globally. Only names that unambiguously mean one specific zone
(e.g. `"my apartment"`, `"Lobby"`, `"the pharmacy"`) remain real aliases.

**The apartment door stays locked to NPCs.** Only a follower enters `zone_home`, with
the player; see [the LLM contract](mechanics/llm-contract.md#asking). A door key
can be neither `DROP`ped nor `GIVE`n away, closing the soft-lock where discarding
his own key stranded Orton outside his apartment forever (the apartment door
starts locked from the building side; opening it from inside unlocks it).

**`ADD_GOAL short_term:`/`short-term` no longer get dropped.** The horizon
token arrived from the parser model as `short_term`, `Short Term`,
`short-term`, or with a trailing colon, and only the first form matched; the
rest silently failed to parse. `modules/action/parser.normalize_key` now folds all
of them to `short_term`/`long_term` before matching.

**`UPDATE_CONDITION` no longer sets any survival value.** The engine drives the
survival stats from the clock; see [survival stats](mechanics/survival-stats.md).

### Open

**The prompt still leaks some things.** NPC `status` and `notes` still go out
whole every turn — only relationship scores and world flags are filtered.
`NpcEntity.knowledge` exists but nothing consumes it yet (no dialogue system
to gate against it), so it's a real field with no read-side firewall
depending on it. See the knowledge-firewall doc's *As Implemented* section.

**Quest state is a checklist, not a director.** `QuestState`/`GameManager.quests`
let the engine track and complete objectives without any LLM verb able to
force completion, but there is no arc/objective/condition graph and nothing
reacts to world state on its own — a quest advances only when
`SimulationCore` notices a specific action matched a specific objective
string (`take:`, `reach:`, `discover:`, `defeat:`, `npc_status:`). A real
Story Director (the story doc) is out of scope here. Content now exists:
`data/story/quests.py` seeds three starting quests on a new game (and backfills
them into any save written before this existed, the same way an empty NPC
roster falls back to `build_starting_npcs()`, reconciling the seeded roster
against what that save had already achieved), and `ContextBuilder` renders
active quests and their checked-off objectives to the narrator in a
`[QUESTS]` section, so the LLM has something to narrate progress against.

Every `discover:` and `npc_status:` objective has an engine producer: a topic an
NPC tells, or the derived `trusts_player` status (see
[the LLM contract](mechanics/llm-contract.md)). `tests/story/test_topics.py` checks that
the roster stays inside them.

**Scale is still unaddressed.** Everything above holds at the game's current
size — eleven zones, three NPCs. The world-generation doc (world generation), 06
(simulation LOD) and 09 (zombie survival systems) describe what growing past
that would need, and none of it exists. That remains a separate, larger
rewrite, not an increment on the engine-authority work.

**`game_over` is reachable.** It is real and persisted
(`managers/simulation.py` `_check_player_death`) and is checked every turn.
Zombie wounds, bleeding, the zombie infection, starvation, thirst and deep cold or
heat all take the player's health to zero; see
[`health`](mechanics/health.md).

**`item_storage_key` is unplaced.** The item is still defined in
`data/items.py`, a holdover from the old storage-room map, but nothing in
`data/world/locations.py` puts it on the ground anywhere and no quest references
it (`quest_storage_room`, the quest that needed it, was replaced by
`quest_supply_run`). It exists only as dead catalog content, and a v2 save
that already held one keeps it, unremapped.

**Playtest findings (2026-10-08).** A full run from a new game to the third day
found parser, narrator and rule gaps. Each is recorded, with a suggested fix, in
the Known limitations section of the doc that owns it:
[LLM contract](mechanics/llm-contract.md#known-limitations) (plans constrained by
the starting scene, empty optional fields, the server ignoring `pattern`, questions
parsed as requests, forced wrong verbs, refused actions narrated as done, finds
denied, repeated paragraphs, quest ids in facts, bystanders who don't react),
[doors](mechanics/doors.md#known-limitations) (one swing per turn, no lock verb),
[carrying and loot](mechanics/carrying-and-loot.md#known-limitations),
[status effects](mechanics/status-effects.md#known-limitations),
[survival stats](mechanics/survival-stats.md#known-limitations),
[clock](mechanics/clock.md#known-limitations) (a flat 10 minutes per zone hop) and
[zombie lifecycle](mechanics/zombie-lifecycle.md#known-limitations).

---

[Index](README.md) · [Engine Authority →](architecture/engine-authority.md)
