# Engine Authority

> **Status: Implemented, at the game's current scale.** A parser call proposes actions; `managers/validator.py` and `managers/simulation.py` decide every outcome on doc 01's authoritative list — HP, inventory, movement, combat, quest completion, discovered world state, time — before the narrator is ever called. The narrator receives an `[OUTCOMES]` block of already-decided facts and has no `ACTIONS:` section left to declare state through. `[CONTINUITY]` still exists but only as a defensive fallback for an exception inside the Simulation Core, not the normal path. What this does *not* cover: procedural world generation, simulation level-of-detail, and a Story Director (docs 05–07, 09) remain unbuilt — this holds at four zones and three NPCs, not at scale. One residual exception to the rule below sits in `DISCOVER_FLAG`/`NPC_STATUS`: the engine is the only *writer*, but the parser still chooses *which* flag or status, which is the model naming hidden information. [Document 07](07-story-architecture.md)'s *As Implemented* section records the decision to give those engine producers. See [Implementation Status](00-status.md).

## 1. Core Principle: Engine Authority

The system is divided into deterministic game systems and local-LLM systems.

```text
PLAYER INPUT
     │
     ▼
┌──────────────────────────────┐
│       LOCAL LLM PARSER       │
│ Natural language → intent    │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│   ENTITY RESOLUTION LAYER    │
│ Pronouns, references, targets│
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│     ACTION VALIDATOR         │
│ Preconditions / legality     │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│       SIMULATION CORE        │
│ Movement / combat / survival │
│ inventory / stealth / time   │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│       EVENT BUS + RULES      │
│ Events → state transitions   │
└──────────────┬───────────────┘
               │
       ┌───────┼────────┐
       ▼       ▼        ▼
     World   Story     NPC/
     Rules   Director  Factions
       │       │        │
       └───────┼────────┘
               ▼
          STATE STORE
               │
               ▼
┌──────────────────────────────┐
│      KNOWLEDGE FIREWALL      │
│ Who is allowed to know what? │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│       CONTEXT BUILDER        │
│ Small, localized worldview   │
└──────────────┬───────────────┘
               │
               ▼
┌──────────────────────────────┐
│       LOCAL LLM NARRATOR     │
│ Prose / dialogue / atmosphere│
└──────────────┬───────────────┘
               ▼
         PLAYER OUTPUT
```

### Rules of authority

The local LLM may:

- interpret natural-language intent;
- identify likely targets and approaches;
- generate dialogue and prose;
- vary wording and presentation;
- suggest a structured action plan.

The local LLM may **not** be authoritative for:

- player HP or stamina;
- inventory contents;
- movement or exits;
- combat results;
- item creation;
- NPC existence;
- quest state;
- world geography;
- hidden information;
- faction state;
- time progression;
- resource quantities;
- persistent consequences.

The engine is always authoritative.

---

[← Implementation Status](00-status.md) · [Index](README.md) · [System Boundaries →](02-system-boundaries.md)
