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

## The central divergence

The design target inverts the real control flow.

```text
DESIGNED (docs 01, 15, 21)            BUILT (adapters/engine.py)

player input                           player input
    ↓                                      ↓
LLM parser → action plan               semantic recall (FAISS)
    ↓                                      ↓
entity resolution                      build_prompt()  -- full world context
    ↓                                      ↓
validation (preconditions)             one LLM call: game master
    ↓                                      ↓
SIMULATION decides outcome             parse STORY / EVENT / ACTIONS
    ↓                                      ↓
events → bus → subsystems              apply_action() × N  -- reject the impossible
    ↓                                      ↓
knowledge firewall                     record event, reindex, summarize, save
    ↓                                      ↓
context builder                        return payload
    ↓
LLM narrator → prose
```

In the design, the engine decides what happens and the LLM describes it. In the
build, the LLM decides what happens and the engine vetoes deltas it can prove
impossible. Everything downstream follows from that inversion: there is no
parser stage, no action plan, no precondition validation, no event bus, and no
knowledge firewall, because the LLM is the simulation.

This is a coherent design for the game as it currently is — three rooms, three
NPCs, a slow-burn social story. It does not scale to what documents 05, 06 and
07 describe. Closing that gap is a rewrite of the turn loop, not an increment.

## Document map

| Doc | Status | Implemented by | Gap |
| --- | --- | --- | --- |
| [01 Engine Authority](01-engine-authority.md) | Partial | `managers/game.py` `apply_action` | Authority is exercised *after* narration, not before. The engine can reject a state delta but never determines an outcome. Prose is unchecked. |
| [02 System Boundaries](02-system-boundaries.md) | Planned | — | No event bus. `GameManager.event_queue` exists and is drained, but nothing enqueues. No simulation core. |
| [03 Intent Parsing](03-intent-parsing.md) | Planned | — | No parser model, no action plan. The 15 verbs in `_ACTION_HANDLERS` are *state deltas* the game master declares, not player intents it proposes — a different layer than the `LOOK/MOVE/ATTACK` vocabulary here. No grammar-constrained decoding. |
| [04 Entity Resolution](04-entity-resolution.md) | Partial | `resolve_npc`, `resolve_location`, `_find_item_entity` | Exact casefold matching on name or id only. No description-based resolution, no ambiguity state, no clarification round trip. |
| [05 World Generation](05-world-generation.md) | Planned | `data/locations.py` | Three hand-written rooms. No seed, no generator, no tiers, no travel nodes. `Location` is flat — no region/zone/location/room hierarchy. |
| [06 Simulation LOD](06-simulation-lod.md) | Planned | — | Every location and NPC is always live in memory. There are nine of them. |
| [07 Story Architecture](07-story-architecture.md) | Planned | `NarrativeState.goals`, `.flags` | Story state is two string lists and a `dict[str, bool]`. No arcs, objectives, conditions or director. `modules/quest.py` is a single enum. |
| [08 Time and Scheduling](08-time-and-scheduling.md) | Planned | `_action_time_advance` | Time advances only when the game master emits `TIME_ADVANCE`. No clock, no tick frequencies, nothing time-driven. See *Known issues* below. |
| [09 Zombie Survival](09-zombie-survival.md) | Planned | — | No noise, no light, no visibility, no scavenging model. |
| [10 Combat and Stealth](10-combat-and-stealth.md) | Planned | `modules/event.py`, `modules/modifier.py` | The damage event and modifier types exist and `_apply_modifiers` handles them. Nothing constructs them, so combat is defined and unreachable. |
| [11 Knowledge Firewall](11-knowledge-firewall.md) | Planned | — | `build_prompt` sends the game master every NPC's raw affinity and trust integers, their private `notes`, their full `status` list and every world flag, with no filter for what the player could know. See *Known issues*. |
| [12 Data Model and Persistence](12-data-model.md) | Partial | `modules/`, `adapters/persistence.py` | Real schemas are richer than the ones here in some places (equipment, attributes, durability) and absent in others (no exit requirements, no NPC goals or knowledge). Persistence is a full snapshot, not base + mutations. The document now carries an *As Implemented* section. |
| [13 Context and Memory](13-context-and-memory.md) | Partial | `build_prompt`, `adapters/memory.py` | The context builder exists but is not selective — it sends the whole local world every turn. Memory layers are compressive (recent / vector-recalled / summarized), not spatial (global / zone / location / scene). The document now carries an *As Implemented* section. |
| [14 LLM Roles](14-llm-roles.md) | Partial | `adapters/llm.py` | One model does both jobs in one call. The narrator constraints listed here are stated in the system prompt and enforced nowhere. |
| [15 Turn Loop](15-turn-loop.md) | Partial | `adapters/engine.py` `play()` | Steps 2–6 collapse into a single LLM call; steps 4, 5, 8, 9 and 12 do not occur. The failure taxonomy is partly real: `apply_action` returns `(bool, message)` and a failed action is logged and skipped. |
| [16 Determinism and Versioning](16-determinism-and-versioning.md) | Partial | `adapters/persistence.py` `SCHEMA_VERSION` | No seeded randomness anywhere — the only nondeterminism is the LLM itself, which is not seeded. `SCHEMA_VERSION` is the sole version; there is no generator, rules, combat or loot version. |
| [17 Observability and Security](17-observability-and-security.md) | Partial | `print()` calls in `engine.py`, `game.py` | Turn logging is unstructured stdout. No state diff, no context snapshot, no replayable trace. LLM output *is* validated before it mutates state, which is the security half of this document. |
| [18 Module Layout](18-module-layout.md) | Superseded | `modules/`, `data/`, `managers/`, `adapters/` | The real layout splits by *purity* (pure model → static data → logic → I/O), not by subsystem. See the layering table in the root `README.md`. |
| [19 End-to-End Example](19-end-to-end-example.md) | Planned | — | Traces a turn through stages that do not exist. |
| [20 Principles](20-principles.md) | Partial | — | Principles 1, 2, 7 and 10 are honoured in spirit. 3, 4, 5, 6, 8 and 9 are not implemented at all. |
| [21 Final Architecture](21-final-architecture.md) | Planned | — | The summary diagram of the design target. |
| [22 Relationships](22-relationships.md) | Implemented | `managers/relationship.py` | — |
| [23 Traits, Perks, Effects, Modifiers](23-traits-perks-modifiers.md) | Implemented | `modules/effect.py`, `modules/modifier.py`, `_broadcast_event` | Pipeline works; no event source feeds it. |
| [24 Runtime and Persistence](24-runtime-and-persistence.md) | Implemented | `config.py`, `adapters/persistence.py`, `adapters/engine.py` | — |

## Known issues

Discrepancies found while reconciling these documents against the code. None are
fixed here; this section exists so they are not rediscovered.

**Two clocks, one frozen.** `World.time` (`"12:00 PM"`) and `World.date`
(`"2023-10-01"`) are injected into every prompt by `build_prompt` and persisted
by `to_dict`, but nothing in the codebase ever writes them. The game master is
told it is noon on 1 October 2023 for the entire game, while
`NarrativeState.day` and `.time_of_day` advance independently alongside.

**`TIME_ADVANCE` can skip a day.** `_action_time_advance` increments
`narrative.day` when the target index is `<=` the current one, so
`TIME_ADVANCE morning` while already in morning advances the day. The intent was
to detect wrapping past night; the comparison should be strict.

**Narration and state can disagree.** Because prose is written before the deltas
are applied, a rejected action leaves the player reading something that did not
happen — the story says the medkit went into the bag, `TAKE` failed, and nothing
reconciles the two. This is structural to the narrate-then-declare ordering, not
a bug in any one function. Document 14's narrator constraints cannot be enforced
under it.

**The prompt leaks.** See document 11 above.

**Combat is dead code.** Recorded in the root `README.md` under *Known gaps*, and
in documents 10 and 23.

---

[Index](README.md) · [Engine Authority →](01-engine-authority.md)
