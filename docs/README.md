# Documentation

Three folders, one job each. A fact lives in one of them; the others point to it.

- **[`mechanics/`](mechanics/)**: the game rules as built, with their numbers.
  Code and tests cite a mechanic by its id, the file name
  (`# zombie-lifecycle`, `"""melee: Shoves."""`).
- **[`architecture/`](architecture/)**: how the running system is built: the
  turn, the layers, context, saves, the UI. A *Partial* banner says where a
  document's built part stops.
- **[`design/`](design/)**: intent that is not built, kept as a target.

**Start at [Implementation Status](status.md).** It maps every document to the
code that implements it, states where the built system diverges from the
design, and records known issues.

## The central principle

**Engine Authority**:

> The game engine owns truth, rules, simulation, persistence, and state transitions. The local LLM interprets player language and turns validated results into natural language. The LLM is a narrator and intent interface, not the database or simulation authority.

The running game follows this at its current scale: the parser proposes
actions, the engine validates and resolves them, and the narrator describes
the outcome. The scale the design aims at (50,000+ addressable locations,
simulation level of detail) is still intent.

## Mechanics

- **[Game Clock and Action Time](mechanics/clock.md)** (`clock`)
- **[Survival Stats](mechanics/survival-stats.md)** (`survival-stats`)
- **[Status Effects and Consumption](mechanics/status-effects.md)** (`status-effects`)
- **[Weather](mechanics/weather.md)** (`weather`)
- **[Clothing](mechanics/clothing.md)** (`clothing`)
- **[Body Temperature, Wetness and Colds](mechanics/body-temperature.md)** (`body-temperature`)
- **[Character Creation](mechanics/character-creation.md)** (`character-creation`)
- **[Skills](mechanics/skills.md)** (`skills`)
- **[Zombies](mechanics/zombies.md)** (`zombies`)
- **[LLM Contract](mechanics/llm-contract.md)** (`llm-contract`)
- **[Melee Combat](mechanics/melee.md)** (`melee`)
- **[Body-Part Health and Zombie Infection](mechanics/health.md)** (`health`)
- **[Doors, Thumping and Barricades](mechanics/doors.md)** (`doors`)
- **[The Zombie Lifecycle](mechanics/zombie-lifecycle.md)** (`zombie-lifecycle`)
- **[Carrying, Containers and Loot](mechanics/carrying-and-loot.md)** (`carrying-and-loot`)

## Architecture

- **[Engine Authority](architecture/engine-authority.md)** — *Implemented, at the game's current scale*
- **[Intent Parsing and Action Planning](architecture/intent-parsing.md)** — natural language is not game state, sequential action execution, action vocabulary — *Partial*
- **[Entity Resolution](architecture/entity-resolution.md)** — *Partial*
- **[Story and Narrative Architecture](architecture/story.md)** — story state is engine state, three types of story content, story director — *Partial*
- **[Knowledge, Visibility, and Information Security](architecture/knowledge-firewall.md)** — *Partial*
- **[Data Model and Persistence](architecture/data-model.md)** — data model, event-oriented persistence, exits are structured data, npc architecture, factions and world systems — *Partial, with an* As Implemented *section*
- **[Context Construction and Memory Layers](architecture/context-and-memory.md)** — context construction, memory layers — *Partial, with an* As Implemented *section*
- **[Local LLM Roles and Narrator Constraints](architecture/llm-roles.md)** — local llm roles, narrator constraints — *Partial*
- **[Full Turn Loop and Failure Handling](architecture/turn-loop.md)** — full turn loop, failure handling — *Partial*
- **[Determinism, Randomness, and Versioning](architecture/determinism-and-versioning.md)** — determinism and randomness, versioning — *Partial*
- **[Observability, Debugging, and the LLM Security Boundary](architecture/observability-and-security.md)** — observability and debugging, security boundary for local llms — *Partial*
- **[Architectural Principles](architecture/principles.md)** — *Partial*
- **[Relationships, Trust, and Disposition](architecture/relationships.md)** — directional affinity and trust, derived disposition, faction reputation — *Implemented*
- **[Traits, Perks, Effects, and Modifiers](architecture/traits-and-modifiers.md)** — the event → effect → modifier chain — *Implemented, live*
- **[Runtime, Configuration, and Persistence](architecture/runtime-and-persistence.md)** — turn serialization, config loading, save compatibility policy — *Implemented*
- **[UI Layout](architecture/ui-layout.md)** — read-only responsive screens, where each snapshot field is shown, words not numbers — *Implemented*

## Design

- **[System Boundaries](design/system-boundaries.md)** — simulation core, event bus — *Planned*
- **[World Generation, Topology and Travel](design/world-generation.md)** — location hierarchy, rooms are graph nodes, deterministic world generation, tiered content, separate topology from content, on-demand materialization, travel nodes — *Planned*
- **[Simulation Level of Detail](design/simulation-lod.md)** — *Planned*
- **[Time and Scheduling](design/time-and-scheduling.md)** — *Planned*
- **[Zombie Survival Simulation](design/zombie-survival.md)** — spatial threat and noise, light and visibility, time-decay scavenging, direct action validation — *Partial*
- **[Combat and Stealth Resolution](design/combat-and-stealth.md)** — combat, stealth — *Partial*
- **[End-to-End Example](design/end-to-end-example.md)** — *Planned*
- **[Final Architecture](design/final-architecture.md)** — final architecture, conclusion — *Planned*

For setup, the action verb reference and the test suite, see the root
[`README.md`](../README.md).
