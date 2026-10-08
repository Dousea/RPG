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

### Debug log

`server.debug: true` sets logging to DEBUG, and each module logs its decisions through its own `logging.getLogger(__name__)`. The log may hold numbers (HP, damage, odds) because it never reaches the narrator; the facts the narrator sees still hold none. By area:

- **Turn** (`adapters/engine.py`): the input, the `@` picks, the game minute and the zone; the parsed plan action by action, and any re-parse at a destination; actions rewritten (such as `aimed`) and those the plan check drops; the which-one questions with their options and the plan screen's picks; the outcome and narrated facts; the minutes the turn spent.
- **Resolution** (`managers/simulation.py`): each action with the target it resolved to, its minutes, the clock before and after and its facts, or the reason it was refused; the beats fired with their effects, flags set and discovered, quest objectives done, topics told, trust and affection changes with their reason (the approach, repeats, Guarded), status effect level changes once per turn, and sleep start and wake.
- **Combat and zombies** (`managers/combat/`, `managers/zombies/`, `managers/world/barriers.py`): a swing's weapon, reach, crit chance and roll and each hit's damage chain; a zombie's attack with its defence roll, body part, wound kind and infection chance; a zombie noticing the player or hearing a sound, spawns, moves between zones, a body rising, a zombie dying, and door and barricade damage. Each fires on an event, not on every minute of the loop.
- **Body** (`managers/body/health.py`): wounds landed, healed and infected, the zombie infection starting, and the cause of a death.
- **Loot and carry** (`managers/world/containers.py`, `managers/carry.py`): the table opened, each roll that makes an item with its draw, and a take or put refused for weight or capacity with the numbers.
- **Entity resolution** (`managers/naming.py`, `managers/world/`, `managers/validator.py`): for a name, the candidates found and the one chosen, or the which-one question asked instead.
- **Prompt budget** (`managers/context.py`): each prompt's size against its budget and each piece dropped to fit.

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
