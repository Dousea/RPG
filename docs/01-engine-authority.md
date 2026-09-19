# Engine Authority

> **Status: Partial.** The engine can veto an impossible state change, but it never decides an outcome — the LLM narrates first and declares the deltas afterwards. Prose is unchecked; a veto is reported back to the narrator on the *next* turn (`[CONTINUITY]`), which is the earliest the story can admit a delta never landed. See [Implementation Status](00-status.md).

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
