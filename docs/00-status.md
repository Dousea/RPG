# Implementation Status

This document maps every architecture document to the code that implements it,
and says plainly what does not exist yet.

Documents 01–21 were written as a **design target**. The code in this repository
is an earlier, simpler system that shares vocabulary with that target but not
its structure. Read those documents as intent, not as a description of the
running program. Documents 22–25 describe subsystems that exist in code and were
never part of the original design set.

## Status vocabulary

| Status | Meaning |
| --- | --- |
| **Implemented** | The document describes code that exists and runs. |
| **Partial** | Some of it exists; the document says where the code stops. |
| **Planned** | Design intent. No code. Preserved deliberately as a target. |
| **Superseded** | The document was overtaken by a different decision. |

## Mechanics

Each mechanic is described by a document in `docs/mechanics/`. These describe
what the game now does.

| # | Mechanic | Status | Code |
| --- | --- | --- | --- |
| 01 | [Game Clock and Action Time](mechanics/01-game-clock.md) | Implemented | `data/clock.py`, `data/time_costs.py`, `managers/game.py`, `managers/simulation.py`, `managers/validator.py`, `modules/action/parser.py` |
| 02 | [Survival Stats](mechanics/02-survival-stats.md) | Implemented | `modules/stats.py`, `modules/units.py`, `data/survival.py`, `data/status_effects.py`, `managers/stats/status_effects.py`, `managers/stats/drivers.py`, `managers/stats/engine.py`, `managers/simulation.py`, `managers/validator.py`, `adapters/save/codec.py` |
| 03 | [Status Effects and Consumption](mechanics/03-status-effects-and-consumption.md) | Implemented | `modules/stats.py`, `modules/item.py`, `data/status_effects.py`, `data/items.py`, `managers/stats/status_effects.py`, `managers/stats/engine.py`, `managers/simulation.py`, `managers/context.py`, `adapters/engine.py`, `adapters/save/codec.py` |
| 04 | [Weather](mechanics/04-weather.md) | Implemented | `modules/simplex.py`, `modules/weather.py`, `modules/location.py`, `data/climate.py`, `data/locations.py`, `managers/climate.py`, `managers/simulation.py`, `managers/context.py`, `adapters/engine.py`, `adapters/save/codec.py` |
| 05 | [Clothing](mechanics/05-clothing.md) | Implemented | `modules/body.py`, `modules/item.py`, `modules/entity/player.py`, `modules/entity/item.py`, `data/body_locations.py`, `data/clothing_coverage.py`, `data/items.py`, `data/time_costs.py`, `managers/validator.py`, `managers/simulation.py`, `managers/context.py`, `adapters/engine.py`, `adapters/save/codec.py` |
| 06 | [Body Temperature, Wetness and Colds](mechanics/06-body-temperature.md) | Implemented | `modules/thermal.py`, `modules/stats.py`, `modules/location.py`, `modules/entity/player.py`, `data/thermal.py`, `data/climate.py`, `data/status_effects.py`, `data/traits.py`, `data/locations.py`, `managers/thermoregulator.py`, `managers/wetness.py`, `managers/cold.py`, `managers/climate.py`, `managers/stats/engine.py`, `managers/stats/drivers.py`, `managers/stats/status_effects.py`, `managers/simulation.py`, `adapters/save/codec.py` |
| 07 | [Character Creation](mechanics/07-character-creation.md) | Implemented | `modules/character/appearance.py`, `modules/character/build.py`, `modules/character/definitions.py`, `modules/entity/player.py`, `data/occupations.py`, `data/traits.py`, `data/creation.py`, `data/clothing_selection.py`, `data/names.py`, `data/presets.py`, `managers/creation.py`, `managers/stats/drivers.py`, `managers/cold.py`, `managers/context.py`, `managers/game.py`, `adapters/creation_payload.py`, `adapters/engine.py`, `adapters/llm.py`, `adapters/save/codec.py`, `app.py`, `templates/index.html` |
| 08 | [Skills](mechanics/08-skills.md) | Implemented | `modules/character/skills.py`, `modules/character/exercise.py`, `modules/entity/player.py`, `modules/item.py`, `modules/resolution.py`, `modules/action/types.py`, `modules/action/parser.py`, `data/skills.py`, `data/exercises.py`, `data/items.py`, `data/time_costs.py`, `managers/skills.py`, `managers/exercise.py`, `managers/stats/drivers.py`, `managers/thermoregulator.py`, `managers/simulation.py`, `managers/validator.py`, `managers/creation.py`, `managers/game.py`, `managers/context.py`, `adapters/engine.py`, `adapters/llm.py`, `adapters/save/codec.py`, `templates/index.html` |
| 09 | [Zombies](mechanics/09-zombies.md) | Implemented | `modules/entity/zombie.py`, `modules/location.py`, `modules/pace.py`, `modules/story.py`, `modules/resolution.py`, `modules/action/types.py`, `modules/action/parser.py`, `data/zombie_lore.py`, `data/locations.py`, `data/time_costs.py`, `managers/zombies.py`, `managers/noise.py`, `managers/zombie_attack.py`, `managers/simulation.py`, `managers/validator.py`, `managers/context.py`, `adapters/engine.py`, `adapters/llm.py`, `adapters/save/codec.py`, `templates/index.html` |
| 10 | [LLM Contract](mechanics/10-llm-contract.md) | Implemented | `modules/action/parser.py`, `modules/action/types.py`, `modules/action/words.py`, `modules/entity/npc.py`, `modules/location.py`, `modules/resolution.py`, `modules/social.py`, `modules/story.py`, `data/social.py`, `data/topics.py`, `data/story_beats.py`, `data/time_costs.py`, `data/zombie_lore.py`, `data/quests.py`, `data/npcs.py`, `managers/social.py`, `managers/story.py`, `managers/game.py`, `managers/validator.py`, `managers/simulation.py`, `managers/context.py`, `adapters/llm.py`, `adapters/engine.py`, `adapters/save/codec.py`, `templates/index.html`, `evals/parser_cases.yaml`, `scripts/eval_parser.py` |

## The central divergence (resolved for engine authority; still open for scale)

The design target inverts the real control flow. That inversion is now real
for the axis document 01 cares about — outcomes are decided before they are
narrated — at the scale the game actually runs at (four zones, three NPCs).

```text
DESIGNED (docs 01, 15, 21)            BUILT (adapters/engine.py)

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
context builder                        LLM call #2: narrator → STORY / EVENT
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
to arbitrary world state (documents 05, 06, 07 — see below). The event/effect/
modifier pipeline (document 23) is real now for combat and item use, but only
for the two event families that exist; it is not a general-purpose bus other
subsystems publish to. Closing *that* gap — scaling past a handful of zones —
is still the rewrite documents 05/06/07 describe, not an increment on top of
this one.

## Document map

| Doc | Status | Implemented by | Gap |
| --- | --- | --- | --- |
| [01 Engine Authority](01-engine-authority.md) | Implemented (at current scale) | `managers/validator.py`, `managers/simulation.py`, `adapters/engine.py` `play()` | Player HP, inventory, movement, combat, time and quest completion are engine-decided before the narrator is called. Not implemented: hidden-info/faction-state depth beyond discovered flags, and everything documents 05–09 would add if the world grew past a handful of zones. |
| [02 System Boundaries](02-system-boundaries.md) | Partial | `managers/events.py` `broadcast_event`, `EVENT_TO_EFFECT_TYPES` | Combat and item-use events are constructed and dispatched, role-aware (a "damage taken" handler only fires for the actual target). This is direct dispatch to a fixed pair of event families, not a general publish/subscribe bus other subsystems can register against — the typed event taxonomy in this document is still aspirational. |
| [03 Intent Parsing](03-intent-parsing.md) | Partial | `modules/action/parser.py`, `adapters/llm.py` `query_parser` | A separate parser call proposes a typed `AnyAction` plan (`modules/action/parser.py`) before anything is decided, matching this document's intent. Still missing: grammar-constrained decoding (the model can still emit unparseable text, caught as a `ParseFailure`) and true entity-resolution ambiguity handling (04 is unchanged). |
| [04 Entity Resolution](04-entity-resolution.md) | Partial | `resolve_npc`, `resolve_location`, `_find_item_entity` | NPC resolution is still exact casefold matching on name or id only. Location resolution (`resolve_location`) now also matches connection direction, alias, and — as a last pass — whole words shared with a zone's name or aliases (a loose substring match is deliberately excluded). No description-based resolution, no ambiguity state, no clarification round trip. |
| [05 World Generation](05-world-generation.md) | Planned | `data/locations.py` | Four hand-written coarse zones (`zone_home`, `zone_building`, `zone_street`, `zone_neighborhood`), each with aliases and a free-text `PlayerEntity.current_place` for where within the zone the player narratively is. One locked door (the apartment, building → home). No seed, no generator, no tiers, no travel nodes. `Location` is flat — no region/zone/location/room hierarchy. Out of scope for the engine-authority work; see the note at the top of this document. |
| [06 Simulation LOD](06-simulation-lod.md) | Planned | — | Every location and NPC is always live in memory. There are seven of them (four zones, three NPCs). Out of scope for the engine-authority work. |
| [07 Story Architecture](07-story-architecture.md) | Partial | `modules/quest.py` `QuestState`, `data/quests.py`, `GameManager.quests` | Quest progress is now engine-tracked and engine-completed (`SimulationCore._advance_quests`, fired on a matching validated action, never on an LLM-declared verb) — but it is a flat objective-completion checklist, not the arc/objective/condition/event graph this document describes, and there is no Story Director reacting to world state. Deliberately thin; a real director is out of scope. One decided-but-unbuilt change is recorded in that document's *As Implemented* section: `discover:`/`npc_status:` objectives currently depend on names the *parser* invents, and need engine producers instead. |
| [08 Time and Scheduling](08-time-and-scheduling.md) | Planned | `data/clock.py`, `managers/game.py` `NarrativeState` | The player-facing minute clock is [mechanics 01](mechanics/01-game-clock.md). NPC and world scheduling, sub-tick frequencies and everything else in this document is not built. |
| [09 Zombie Survival](09-zombie-survival.md) | Partial | `managers/zombies.py`, `managers/noise.py` | Noise, light and visibility are [mechanics 09](mechanics/09-zombies.md). No scavenging model. |
| [10 Combat and Stealth](10-combat-and-stealth.md) | Partial | `managers/simulation.py` `_resolve_attack`, `modules/event.py`, `modules/modifier.py` | `ATTACK` is a real action: it resolves through the event/modifier pipeline, applies equipped-weapon damage with jitter, and both "dealt" and "taken" trait reactions actually fire for any entity carrying an effect-bearing trait (the player's traits are ids and carry none). No stealth, no ranged distance/line-of-sight, no armor mitigation yet — this is base damage resolution, not the full document. |
| [11 Knowledge Firewall](11-knowledge-firewall.md) | Partial | `managers/context.py`, `NarrativeState.discovered_flags`, `NpcEntity.knowledge`/`.goals` | Affinity/trust are still banded, and world flags are now filtered too: a flag only reaches the narrator prompt once the engine has marked it discovered (a topic told), separately from setting its value. `NpcEntity.knowledge` exists but is deliberately never rendered (no dialogue system consumes it yet); NPC `status` and `notes` still go out unfiltered. The document's *As Implemented* section should be read alongside this. |
| [12 Data Model and Persistence](12-data-model.md) | Partial | `modules/`, `adapters/save/codec.py`, `modules/quest.py` | Exit requirements now exist (`DoorEntity` wired into `data/locations.py`, checked by `ActionValidator`) — in practice the only one is the apartment door (building → home), locked, keyed to `item_apartment_key`. Door lock state is not persisted; it is part of the static map and always reloads locked. NPCs carry `goals`/`knowledge` fields. Persistence is still a full snapshot, not base + mutations, and quest state (see doc 07) is a flat checklist, not the model this document describes. |
| [13 Context and Memory](13-context-and-memory.md) | Partial | `managers/context.py` `ContextBuilder`, `adapters/memory.py` | The context builder is now its own module (`managers/context.py`), independently testable, and the parser gets a *separate, minimal* context from the narrator's full one — a step toward selectivity. It still sends the whole local world to the narrator every turn, and memory layers remain compressive (recent / vector-recalled / summarized), not spatial (global / zone / location / scene). |
| [14 LLM Roles](14-llm-roles.md) | Partial | `adapters/llm.py` `query_parser`/`query_narrator` | Two calls, two roles, two system prompts — parser proposes actions only, narrator only narrates and no longer has an `ACTIONS:` section to fill at all. The narrator's *constraints* (don't invent HP/inventory/combat results) are stated in its system prompt and structurally reinforced (it has nothing to declare state through), but still not mechanically enforced against a malicious or careless model. |
| [15 Turn Loop](15-turn-loop.md) | Partial | `adapters/engine.py` `play()` | Real steps now: parser call → `parse_action_plan` → `ActionValidator` → `SimulationCore` → narrator call → record/reindex/summarize/save. Missing relative to the 15-step design: no separate entity-resolution stage (folded into the validator), no world/story/NPC/faction *rules* layer beyond quest advancement, no structured failure taxonomy beyond `Rejected`/`ParseFailure`. |
| [16 Determinism and Versioning](16-determinism-and-versioning.md) | Partial | `adapters/save/codec.py` `SCHEMA_VERSION` | No seeded randomness anywhere — combat damage jitter (`managers/combat.py`) and the LLM itself are both unseeded. `SCHEMA_VERSION` is 4 and any other version is discarded with no migration; it remains the sole version, with no generator, rules, combat or loot version. Explicitly out of scope for the engine-authority work. |
| [17 Observability and Security](17-observability-and-security.md) | Partial | `print()` calls in `engine.py`, `game.py`, `simulation.py` | Turn logging is unstructured stdout. No state diff, no context snapshot, no replayable trace. LLM output *is* validated and simulated before it mutates state, which is the security half of this document, and now happens before narration too. Structured tracing is out of scope for the engine-authority work. |
| [18 Module Layout](18-module-layout.md) | Superseded | `modules/`, `data/`, `managers/`, `adapters/` | The real layout splits by *purity* (pure model → static data → logic → I/O), not by subsystem. `managers/validator.py`, `managers/simulation.py` and `managers/context.py` extend that split; see the layering table in the root `README.md`. |
| [19 End-to-End Example](19-end-to-end-example.md) | Planned | — | Traces a turn through stages that do not exist. |
| [20 Principles](20-principles.md) | Partial | — | Principles 1, 2, 7 and 10 are honoured in spirit, and 3 ("events connect systems") and 6 ("knowledge is scoped") are now partly true for combat/item-use and world flags respectively. 4, 5, 8 and 9 remain unimplemented. |
| [21 Final Architecture](21-final-architecture.md) | Planned | — | The summary diagram of the design target. |
| [22 Relationships](22-relationships.md) | Implemented | `managers/relationship.py` | — |
| [23 Traits, Perks, Effects, Modifiers](23-traits-perks-modifiers.md) | Implemented | `modules/effect.py`, `modules/modifier.py`, `managers/events.py` | Pipeline is live: `SimulationCore` constructs `WeaponDealDamageEvent`/`WeaponTakeDamageEvent`/`ConsumeItemEvent`/`ApplyItemEvent`, and the event-to-handler matcher (previously a always-false string comparison) correctly routes them, role-aware. |
| [24 Runtime and Persistence](24-runtime-and-persistence.md) | Implemented | `config.py`, `adapters/save/codec.py`, `adapters/save/files.py`, `adapters/engine.py` | Schema is v4 (see [mechanics 01](mechanics/01-game-clock.md#saves)); `current_place`, `game_over` and `death_cause` are saved. Any other version is discarded and a new game starts; there is no migration. |
| [25 UI Layout](25-ui-layout.md) | Partial | `templates/index.html`, `adapters/engine.py` `_snapshot`, `adapters/creation_payload.py` | The page, its three responsive layouts (8, 5 and 4 tabs) and the creation screen exist and are read-only. The Health and Nearby screens stay hidden until their mechanics send fields; hit points and item condition still show as numbers. |

## Known issues

Discrepancies found while reconciling these documents against the code. The
first three were fixable where they stood and are fixed; the rest are structural,
and are recorded here so they are not rediscovered.

### Fixed

**One clock, not two.** `World.time` and `World.date` are a rendering of the one minute clock; see [mechanics 01](mechanics/01-game-clock.md).

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
the normal error path. Document 14's narrator constraints are now
structurally reinforced (the narrator has no `ACTIONS:` section to declare
state through at all) though still not mechanically enforced against a
malicious or careless model.

**Combat is no longer dead code.** `SimulationCore._resolve_attack` builds a
`WeaponDealDamageEvent`/`WeaponTakeDamageEvent` pair for every `ATTACK`
action, and the event-to-handler matcher (`EVENT_TO_EFFECT_TYPES` in
`managers/events.py`) replaces the string-prefix comparison that used to make
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
is already standing in (`ActionValidator._validate_move`). See doc 05's row
above for the current map.

**Generic room nouns are spots, not zone aliases.** A word like "kitchen",
"bathroom", "office", or "upstairs" almost never names one particular zone,
so `data/locations.py`'s `aliases` lists no longer carry them at all —
naming one now lands Orton on a free-text spot in whatever zone he's already
in, instead of silently teleporting him to whichever zone happened to claim
that word globally. Only names that unambiguously mean one specific zone
(e.g. `"my apartment"`, `"Lobby"`, `"the pharmacy"`) remain real aliases.

**The apartment door stays locked to NPCs.** Only a follower enters `zone_home`, with
the player; see [the LLM contract](mechanics/10-llm-contract.md#asking). A door key
can be neither `DROP`ped nor `GIVE`n away, closing the soft-lock where discarding
his own key stranded Orton outside his apartment forever (the door rebuilds
`LOCKED` on every load).

**`ADD_GOAL short_term:`/`short-term` no longer get dropped.** The horizon
token arrived from the parser model as `short_term`, `Short Term`,
`short-term`, or with a trailing colon, and only the first form matched; the
rest silently failed to parse. `modules/action/parser.normalize_key` now folds all
of them to `short_term`/`long_term` before matching.

**`UPDATE_CONDITION` no longer sets any survival value.** The engine drives the
survival stats from the clock; see [survival stats](mechanics/02-survival-stats.md).

### Open

**The prompt still leaks some things.** NPC `status` and `notes` still go out
whole every turn — only relationship scores and world flags are filtered.
`NpcEntity.knowledge` exists but nothing consumes it yet (no dialogue system
to gate against it), so it's a real field with no read-side firewall
depending on it. See document 11's *As Implemented* section.

**Quest state is a checklist, not a director.** `QuestState`/`GameManager.quests`
let the engine track and complete objectives without any LLM verb able to
force completion, but there is no arc/objective/condition graph and nothing
reacts to world state on its own — a quest advances only when
`SimulationCore` notices a specific action matched a specific objective
string (`take:`, `reach:`, `discover:`, `defeat:`, `npc_status:`). A real
Story Director (document 07) is out of scope here. Content now exists:
`data/quests.py` seeds three starting quests on a new game (and backfills
them into any save written before this existed, the same way an empty NPC
roster falls back to `build_starting_npcs()`, reconciling the seeded roster
against what that save had already achieved), and `ContextBuilder` renders
active quests and their checked-off objectives to the narrator in a
`[QUESTS]` section, so the LLM has something to narrate progress against.

Every `discover:` and `npc_status:` objective has an engine producer: a topic an
NPC tells, or the derived `trusts_player` status (see
[the LLM contract](mechanics/10-llm-contract.md)). `tests/test_topics.py` checks that
the roster stays inside them.

**Scale is still unaddressed.** Everything above holds at the game's current
size — four zones, three NPCs. Documents 05 (world generation), 06
(simulation LOD) and 09 (zombie survival systems) describe what growing past
that would need, and none of it exists. That remains a separate, larger
rewrite, not an increment on the engine-authority work.

**Door lock state is not persisted.** `data/locations.py` builds the
apartment door LOCKED every time `build_starting_locations()` runs, and
nothing in `adapters/save/codec.py` saves or restores a door's state, so it
always reloads locked regardless of whether the player unlocked it in a
prior session. Harmless today — the only lock in the game is Orton's own
apartment door, and he starts holding its key — but it would misbehave the
moment a second, player-unlockable door existed.

**`game_over` is not reachable in normal play.** It is real and persisted
(`managers/simulation.py` `_check_player_death`), and it is checked every
turn, but nothing in the shipped content can actually drive Orton's HP to
zero: `ATTACK` only ever damages the *target* NPC, never the player who
issued it, and every item's `HPModifier` in `data/items.py` is positive
(healing). There is no NPC aggression, hazard, or environmental system that
damages Orton at all. The only ways to reach `game_over` today are a
test-local item (see `tests/test_simulation.py`'s `LETHAL_ITEM`, used only
to exercise the death path in isolation) or a hand-edited/malformed save
that sets HP to zero directly.

**`item_storage_key` is unplaced.** The item is still defined in
`data/items.py`, a holdover from the old storage-room map, but nothing in
`data/locations.py` puts it on the ground anywhere and no quest references
it (`quest_storage_room`, the quest that needed it, was replaced by
`quest_supply_run`). It exists only as dead catalog content, and a v2 save
that already held one keeps it, unremapped.

**A zone change costs one tick regardless of distance.** `SimulationCore._resolve_move`
advances the clock exactly once for a `"zone"`-kind move, whether the walk
crossed one connection or several (`GameManager.zone_path` can return a
multi-hop path). A spot move within the current zone costs nothing. This is
a coarser model than distance-scaled travel time; it was accepted as the
zones-era mapping of "movement costs time" onto a system that no longer has
per-room adjacency.

---

[Index](README.md) · [Engine Authority →](01-engine-authority.md)
