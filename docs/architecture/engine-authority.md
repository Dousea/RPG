# Engine Authority

> **Status: Implemented, at the game's current scale.** A parser call proposes actions; `managers/validator.py` and `managers/simulation.py` decide every outcome on the engine-authority doc's authoritative list — HP, inventory, movement, combat, quest completion, discovered world state, time — before the narrator is ever called. The narrator receives an `[OUTCOMES]` block of already-decided facts and has no `ACTIONS:` section left to declare state through. `[CONTINUITY]` still exists but only as a defensive fallback for an exception inside the Simulation Core, not the normal path. What this does *not* cover: procedural world generation, simulation level-of-detail, and a Story Director (the world-generation, simulation-lod, story and zombie-survival docs) remain unbuilt — this holds at eleven zones and three NPCs, not at scale. The parser has no verb that sets a number, a flag, a relationship or an NPC's state; see [the LLM contract](../mechanics/llm-contract.md). See [Implementation Status](../status.md).

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

A turn's plan runs in legs, each a run of actions in one zone. `managers/turn.py`
owns the turn: it runs a checked first leg through the Simulation Core, ends the leg
at its first zone change, and for the destination asks the leg planner, the one seam
back to the LLM (`adapters/engine.py` builds it: parse, then the plan check). The
turn module imports nothing from `adapters/`; it returns one frozen outcome with the
facts, the refusals and the finds. See the
[LLM contract](../mechanics/llm-contract.md#plans).

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

[Index](../README.md)
