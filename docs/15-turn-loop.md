# Full Turn Loop and Failure Handling

> **Status: Partial.** In `GameEngine.play`, steps 2-6 collapse into a single LLM call and steps 4, 5, 8, 9 and 12 do not occur. The failure taxonomy is partly real: a failed action is logged, skipped, and carried into the next prompt as a `[CONTINUITY]` note, and the turn stands. See [Implementation Status](00-status.md).

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
