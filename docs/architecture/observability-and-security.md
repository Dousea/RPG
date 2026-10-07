# Observability, Debugging, and the LLM Security Boundary

> **Status: Partial.** Turn logging is unstructured stdout; there is no state diff or replayable trace. The security half holds: LLM output is validated before it mutates state. See [Implementation Status](../status.md).

## Observability and Debugging

Because the LLM is only one component, the engine should expose a complete debug trace.

A useful turn log is:

```text
INPUT
↓
PARSED INTENT
↓
ENTITY RESOLUTION
↓
VALIDATION
↓
SIMULATION RESULT
↓
EVENTS
↓
STATE DIFF
↓
CONTEXT SNAPSHOT
↓
LLM OUTPUT
```

Example:

```text
INPUT:
"Shoot the big one."

PARSED:
shoot(target_description="the big one")

RESOLVED:
zombie_17

VALIDATION:
PASS

SIMULATION:
hit, damage=24, ammo=-1

EVENTS:
weapon_fired
zombie_damaged
noise_propagated

STATE DIFF:
player.ammo: 12 → 11
zombie_17.hp: 30 → 6

NARRATOR:
"The shot cracks through the room..."
```

This is essential for debugging hallucination-like behavior that is actually caused by incorrect engine state or context assembly.

---

## Security Boundary for Local LLMs

Treat the parser and narrator as untrusted software components from a correctness perspective.

The engine should validate all LLM-produced data before use.

```text
LLM OUTPUT
    ↓
SCHEMA VALIDATION
    ↓
ENTITY VALIDATION
    ↓
AUTHORITY CHECK
    ↓
GAME RULE VALIDATION
    ↓
EXECUTION
```

Never use raw model output directly to mutate persistent state.

---

[Index](../README.md)
