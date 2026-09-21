# Implementation Status

This document maps every architecture document to the code that implements it,
and says plainly what does not exist yet.

Documents 01–21 were written as a **design target**. The code in this repository
is an earlier, simpler system that shares vocabulary with that target but not
its structure. Read those documents as intent, not as a description of the
running program. Documents 22–24 describe subsystems that exist in code and were
never part of the original design set.

## Status vocabulary

| Status | Meaning |
| --- | --- |
| **Implemented** | The document describes code that exists and runs. |
| **Partial** | Some of it exists; the document says where the code stops. |
| **Planned** | Design intent. No code. Preserved deliberately as a target. |
| **Superseded** | The document was overtaken by a different decision. |

## The central divergence (resolved for engine authority; still open for scale)

The design target inverts the real control flow. That inversion is now real
for the axis document 01 cares about — outcomes are decided before they are
narrated — at the scale the game actually runs at (four rooms, three NPCs).

```text
DESIGNED (docs 01, 15, 21)            BUILT (adapters/engine.py)

player input                           player input
    ↓                                      ↓
LLM parser → action plan               semantic recall (FAISS, for the narrator)
    ↓                                      ↓
entity resolution                      LLM call #1: parser → ACTIONS block
    ↓                                      ↓
validation (preconditions)             modules/action.parse_action_plan
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
subsystems publish to. Closing *that* gap — scaling past a handful of rooms —
is still the rewrite documents 05/06/07 describe, not an increment on top of
this one.

## Document map

| Doc | Status | Implemented by | Gap |
| --- | --- | --- | --- |
| [01 Engine Authority](01-engine-authority.md) | Implemented (at current scale) | `managers/validator.py`, `managers/simulation.py`, `adapters/engine.py` `play()` | Player HP, inventory, movement, combat, time and quest completion are engine-decided before the narrator is called. Not implemented: hidden-info/faction-state depth beyond discovered flags, and everything documents 05–09 would add if the world grew past a handful of rooms. |
| [02 System Boundaries](02-system-boundaries.md) | Partial | `managers/game.py` `_broadcast_event`, `EVENT_TO_EFFECT_TYPES` | Combat and item-use events are constructed and dispatched, role-aware (a "damage taken" handler only fires for the actual target). This is direct dispatch to a fixed pair of event families, not a general publish/subscribe bus other subsystems can register against — the typed event taxonomy in this document is still aspirational. |
| [03 Intent Parsing](03-intent-parsing.md) | Partial | `modules/action.py`, `adapters/llm.py` `query_parser` | A separate parser call proposes a typed `AnyAction` plan (`modules/action.py`) before anything is decided, matching this document's intent. Still missing: grammar-constrained decoding (the model can still emit unparseable text, caught as a `ParseFailure`) and true entity-resolution ambiguity handling (04 is unchanged). |
| [04 Entity Resolution](04-entity-resolution.md) | Partial | `resolve_npc`, `resolve_location`, `_find_item_entity` | Exact casefold matching on name or id only. No description-based resolution, no ambiguity state, no clarification round trip. |
| [05 World Generation](05-world-generation.md) | Planned | `data/locations.py` | Four hand-written rooms (one behind a locked door). No seed, no generator, no tiers, no travel nodes. `Location` is flat — no region/zone/location/room hierarchy. Out of scope for the engine-authority work; see the note at the top of this document. |
| [06 Simulation LOD](06-simulation-lod.md) | Planned | — | Every location and NPC is always live in memory. There are nine of them. Out of scope for the engine-authority work. |
| [07 Story Architecture](07-story-architecture.md) | Partial | `modules/quest.py` `QuestState`, `data/quests.py`, `GameManager.quests` | Quest progress is now engine-tracked and engine-completed (`SimulationCore._advance_quests`, fired on a matching validated action, never on an LLM-declared verb) — but it is a flat objective-completion checklist, not the arc/objective/condition/event graph this document describes, and there is no Story Director reacting to world state. Deliberately thin; a real director is out of scope. |
| [08 Time and Scheduling](08-time-and-scheduling.md) | Partial | `SimulationCore._advance_one_tick`, `_action_time_advance`, `_sync_world_clock` | Ordinary actions (move, attack) now advance the clock themselves — the engine owns time progression instead of depending on the LLM to remember `TIME_ADVANCE`. Still one coarse clock (four parts of a day), no sub-tick frequencies, no hunger/stamina/weather driven by it. Deeper scheduling is out of scope. |
| [09 Zombie Survival](09-zombie-survival.md) | Planned | — | No noise, no light, no visibility, no scavenging model. Out of scope for the engine-authority work. |
| [10 Combat and Stealth](10-combat-and-stealth.md) | Partial | `managers/simulation.py` `_resolve_attack`, `modules/event.py`, `modules/modifier.py` | `ATTACK` is a real action: it resolves through the event/modifier pipeline, applies equipped-weapon damage with jitter, and both "dealt" and "taken" trait/perk reactions actually fire (Small Frame, Gun Slinger). No stealth, no ranged distance/line-of-sight, no armor mitigation yet — this is base damage resolution, not the full document. |
| [11 Knowledge Firewall](11-knowledge-firewall.md) | Partial | `managers/context.py`, `NarrativeState.discovered_flags`, `NpcEntity.knowledge`/`.goals` | Affinity/trust are still banded, and world flags are now filtered too: a flag only reaches the narrator prompt once a `DISCOVER_FLAG` action has marked it discovered, separately from the engine setting its value. `NpcEntity.knowledge` exists but is deliberately never rendered (no dialogue system consumes it yet); NPC `status` and `notes` still go out unfiltered. The document's *As Implemented* section should be read alongside this. |
| [12 Data Model and Persistence](12-data-model.md) | Partial | `modules/`, `adapters/persistence.py`, `modules/quest.py` | Exit requirements now exist (`DoorEntity` wired into `data/locations.py`, checked by `ActionValidator`), and NPCs carry `goals`/`knowledge` fields. Persistence is still a full snapshot, not base + mutations, and quest state (see doc 07) is a flat checklist, not the model this document describes. |
| [13 Context and Memory](13-context-and-memory.md) | Partial | `managers/context.py` `ContextBuilder`, `adapters/memory.py` | The context builder is now its own module (`managers/context.py`), independently testable, and the parser gets a *separate, minimal* context from the narrator's full one — a step toward selectivity. It still sends the whole local world to the narrator every turn, and memory layers remain compressive (recent / vector-recalled / summarized), not spatial (global / zone / location / scene). |
| [14 LLM Roles](14-llm-roles.md) | Partial | `adapters/llm.py` `query_parser`/`query_narrator` | Two calls, two roles, two system prompts — parser proposes actions only, narrator only narrates and no longer has an `ACTIONS:` section to fill at all. The narrator's *constraints* (don't invent HP/inventory/combat results) are stated in its system prompt and structurally reinforced (it has nothing to declare state through), but still not mechanically enforced against a malicious or careless model. |
| [15 Turn Loop](15-turn-loop.md) | Partial | `adapters/engine.py` `play()` | Real steps now: parser call → `parse_action_plan` → `ActionValidator` → `SimulationCore` → narrator call → record/reindex/summarize/save. Missing relative to the 15-step design: no separate entity-resolution stage (folded into the validator), no world/story/NPC/faction *rules* layer beyond quest advancement, no structured failure taxonomy beyond `Rejected`/`ParseFailure`. |
| [16 Determinism and Versioning](16-determinism-and-versioning.md) | Partial | `adapters/persistence.py` `SCHEMA_VERSION` | No seeded randomness anywhere — combat damage jitter (`managers/simulation.py`) and the LLM itself are both unseeded. `SCHEMA_VERSION` (now 2) is the sole version; there is no generator, rules, combat or loot version. Explicitly out of scope for the engine-authority work. |
| [17 Observability and Security](17-observability-and-security.md) | Partial | `print()` calls in `engine.py`, `game.py`, `simulation.py` | Turn logging is unstructured stdout. No state diff, no context snapshot, no replayable trace. LLM output *is* validated and simulated before it mutates state, which is the security half of this document, and now happens before narration too. Structured tracing is out of scope for the engine-authority work. |
| [18 Module Layout](18-module-layout.md) | Superseded | `modules/`, `data/`, `managers/`, `adapters/` | The real layout splits by *purity* (pure model → static data → logic → I/O), not by subsystem. `managers/validator.py`, `managers/simulation.py` and `managers/context.py` extend that split; see the layering table in the root `README.md`. |
| [19 End-to-End Example](19-end-to-end-example.md) | Planned | — | Traces a turn through stages that do not exist. |
| [20 Principles](20-principles.md) | Partial | — | Principles 1, 2, 7 and 10 are honoured in spirit, and 3 ("events connect systems") and 6 ("knowledge is scoped") are now partly true for combat/item-use and world flags respectively. 4, 5, 8 and 9 remain unimplemented. |
| [21 Final Architecture](21-final-architecture.md) | Planned | — | The summary diagram of the design target. |
| [22 Relationships](22-relationships.md) | Implemented | `managers/relationship.py` | — |
| [23 Traits, Perks, Effects, Modifiers](23-traits-perks-modifiers.md) | Implemented | `modules/effect.py`, `modules/modifier.py`, `GameManager._broadcast_event` | Pipeline is live: `SimulationCore` constructs `WeaponDealDamageEvent`/`WeaponTakeDamageEvent`/`ConsumeItemEvent`/`ApplyItemEvent`, and the event-to-handler matcher (previously a always-false string comparison) correctly routes them, role-aware. |
| [24 Runtime and Persistence](24-runtime-and-persistence.md) | Implemented | `config.py`, `adapters/persistence.py`, `adapters/engine.py` | Schema bumped to v2 for `NpcEntity.goals`/`.knowledge`, `discovered_flags`, and quest state; the existing "mismatched version → discard, start fresh" policy handled it with no migration code. |

## Known issues

Discrepancies found while reconciling these documents against the code. The
first three were fixable where they stood and are fixed; the rest are structural,
and are recorded here so they are not rediscovered.

### Fixed

**One clock, not two.** `World.time` (`"12:00 PM"`) and `World.date`
(`"2023-10-01"`) were injected into every prompt and persisted, but nothing ever
wrote them: the game master was told it was noon on 1 October 2023 for the whole
game while `NarrativeState.day` and `.time_of_day` advanced alongside. The
narrative clock is now the only clock, and the two world fields are a rendering
of it — `GameManager._sync_world_clock` derives them (`morning` → `08:00 AM`,
day *n* → `WORLD_START_DATE + n-1`) on construction and on every time advance.
Construction-time sync means a save written while the two could drift is repaired
when it loads. Nothing else may write those fields; `modules/location.py` says so.

**`TIME_ADVANCE` no longer skips a day.** `_action_time_advance` incremented
`narrative.day` when the target index was `<=` the current one, so
`TIME_ADVANCE morning` while already in morning pushed the calendar forward. The
check is for rolling *backwards* past night, so the comparison is now strict.
The existing test only covered `evening → morning`, which is strictly backwards;
the equal case is now covered too.

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
`managers/game.py`) replaces the string-prefix comparison that used to make
`_event_matches_effect_handler` return `False` unconditionally — every trait
and perk effect in `data/traits.py`/`data/perks.py` fires now, and only for
the correct side of the hit (a "damage taken" effect no longer fires for the
attacker just because they're also part of the event).

**The prompt leaks less.** World flags are now filtered the same way
relationship scores are: a flag only reaches the narrator once a
`DISCOVER_FLAG` action has marked it discovered, separate from the engine
setting its value. `NpcEntity.knowledge`/`.goals` exist as real fields.

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
roster falls back to `build_starting_npcs()`), and `ContextBuilder` renders
active quests and their checked-off objectives to the narrator in a
`[QUESTS]` section, so the LLM has something to narrate progress against.

**Scale is still unaddressed.** Everything above holds at the game's current
size — four rooms, three NPCs. Documents 05 (world generation), 06
(simulation LOD) and 09 (zombie survival systems) describe what growing past
that would need, and none of it exists. That remains a separate, larger
rewrite, not an increment on the engine-authority work.

---

[Index](README.md) · [Engine Authority →](01-engine-authority.md)
