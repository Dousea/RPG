# Full Turn Loop and Failure Handling

> **Status: Partial.** `GameEngine.play` now makes two LLM calls, not one — steps 2-3 are a real parser call and typed action plan (`modules/action.py`), steps 5-7 are `ActionValidator`/`SimulationCore`, and narration happens after, not before, with a refusal surfaced the *same* turn via `[OUTCOMES]` rather than next turn's `[CONTINUITY]`. Step 4 (entity resolution) is folded into the validator rather than a separate stage; there is still no distinct world/story/NPC/faction rules layer beyond quest advancement. See [Implementation Status](00-status.md).

## Full Turn Loop

```text
1. PLAYER INPUT
       ↓
2. LLM PARSER
       ↓
3. ACTION PLAN
       ↓
4. ENTITY RESOLUTION
       ↓
5. ACTION VALIDATION
       ↓
6. SIMULATION CORE
       ↓
7. EVENTS EMITTED
       ↓
8. EVENT BUS DISPATCH
       ↓
9. STORY / WORLD / NPC / FACTION RULES
       ↓
10. STATE UPDATED
       ↓
11. TIME ADVANCED
       ↓
12. KNOWLEDGE / VISIBILITY UPDATED
       ↓
13. CONTEXT BUILDER
       ↓
14. NARRATOR LLM
       ↓
15. PLAYER OUTPUT
```

This cycle is the authoritative unit of gameplay.

---

## Failure Handling

LLM systems need explicit failure states.

### Parser failure

```json
{
  "status": "unrecognized",
  "reason": "Could not map input to available actions"
}
```

### Ambiguity

```json
{
  "status": "ambiguous",
  "candidates": ["door_1", "door_2"]
}
```

### Validation failure

```json
{
  "status": "rejected",
  "reason": "Player does not have the required keycard"
}
```

### Simulation failure

```json
{
  "status": "failed",
  "reason": "Player was interrupted before completing the action"
}
```

The narrator should describe these outcomes naturally instead of fabricating success.

---

[← Local LLM Roles and Narrator Constraints](14-llm-roles.md) · [Index](README.md) · [Determinism, Randomness, and Versioning →](16-determinism-and-versioning.md)
