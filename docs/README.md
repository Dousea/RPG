# Architecture Documentation

This directory holds two things, and it is important not to confuse them.

**Documents 01–21 are a design target.** They define a hybrid architecture for a
large-scale, text-based zombie action-adventure RPG powered by local LLMs. Most
of it is not built. Each document carries a status banner saying how much of it
exists.

**Documents 22–24 describe the code as it runs today**, covering subsystems the
design set never anticipated.

**Start at [00 — Implementation Status](00-status.md).** It maps every document
to the code that implements it, states plainly where the built system diverges
from the designed one, and records the known issues found while reconciling the
two.

## The design target

The central principle is **Engine Authority**:

> The game engine owns truth, rules, simulation, persistence, and state transitions. The local LLM interprets player language and turns validated results into natural language. The LLM is a narrator and intent interface, not the database or simulation authority.

The architecture is designed to support a world with 50,000+ addressable locations without requiring 50,000 simultaneously simulated rooms or a huge LLM context window.

The running game inverts this: the LLM decides what happens and the engine
rejects the deltas it can prove impossible. See
[00 — Implementation Status](00-status.md) for why that matters and what it
costs.

## Contents

### Status

0. **[Implementation Status](00-status.md)** — document-to-code map, the central divergence, known issues

### Design target (01–21)

1. **[Engine Authority](01-engine-authority.md)** — *Partial*
2. **[System Boundaries](02-system-boundaries.md)** — simulation core, event bus — *Planned*
3. **[Intent Parsing and Action Planning](03-intent-parsing.md)** — natural language is not game state, sequential action execution, action vocabulary — *Planned*
4. **[Entity Resolution](04-entity-resolution.md)** — *Partial*
5. **[World Generation, Topology and Travel](05-world-generation.md)** — location hierarchy, rooms are graph nodes, deterministic world generation, tiered content, separate topology from content, on-demand materialization, travel nodes — *Planned*
6. **[Simulation Level of Detail](06-simulation-lod.md)** — *Planned*
7. **[Story and Narrative Architecture](07-story-architecture.md)** — story state is engine state, three types of story content, story director — *Planned*
8. **[Time and Scheduling](08-time-and-scheduling.md)** — *Planned*
9. **[Zombie Survival Simulation](09-zombie-survival.md)** — spatial threat and noise, light and visibility, time-decay scavenging, direct action validation — *Planned*
10. **[Combat and Stealth Resolution](10-combat-and-stealth.md)** — combat, stealth — *Planned*
11. **[Knowledge, Visibility, and Information Security](11-knowledge-firewall.md)** — *Planned, and actively violated*
12. **[Data Model and Persistence](12-data-model.md)** — data model, event-oriented persistence, exits are structured data, npc architecture, factions and world systems — *Partial, with an* As Implemented *section*
13. **[Context Construction and Memory Layers](13-context-and-memory.md)** — context construction, memory layers — *Partial, with an* As Implemented *section*
14. **[Local LLM Roles and Narrator Constraints](14-llm-roles.md)** — local llm roles, narrator constraints — *Partial*
15. **[Full Turn Loop and Failure Handling](15-turn-loop.md)** — full turn loop, failure handling — *Partial*
16. **[Determinism, Randomness, and Versioning](16-determinism-and-versioning.md)** — determinism and randomness, versioning — *Partial*
17. **[Observability, Debugging, and the LLM Security Boundary](17-observability-and-security.md)** — observability and debugging, security boundary for local llms — *Partial*
18. **[Recommended Module Layout](18-module-layout.md)** — *Superseded*
19. **[End-to-End Example](19-end-to-end-example.md)** — *Planned*
20. **[Architectural Principles](20-principles.md)** — *Partial*
21. **[Final Architecture](21-final-architecture.md)** — final architecture, conclusion — *Planned*

### As built (22–24)

22. **[Relationships, Trust, and Disposition](22-relationships.md)** — directional affinity and trust, derived disposition, faction reputation — *Implemented*
23. **[Traits, Perks, Effects, and Modifiers](23-traits-perks-modifiers.md)** — the event → effect → modifier chain — *Implemented, unreachable*
24. **[Runtime, Configuration, and Persistence](24-runtime-and-persistence.md)** — turn serialization, config loading, save compatibility policy — *Implemented*

For setup, the action verb reference and the test suite, see the root
[`README.md`](../README.md).
