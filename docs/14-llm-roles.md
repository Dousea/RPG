# Local LLM Roles and Narrator Constraints

> **Status: Partial.** Two calls now, `query_parser` and `query_narrator` in `adapters/llm.py`, each with its own system prompt and response format — the narrator's no longer has an `ACTIONS:` section to fill at all. The constraints below are structurally reinforced (the narrator has nothing left to declare state through) but still not mechanically enforced against a model that ignores its prompt. See [Implementation Status](00-status.md).

## Local LLM Roles

### 1. Parser Model

Priorities:

- low latency;
- structured output;
- strict instruction following;
- small context;
- deterministic behavior.

Responsibilities:

```text
player language
    ↓
intent
    ↓
action plan
```

### 2. Narrator Model

Priorities:

- prose quality;
- dialogue quality;
- contextual consistency;
- atmosphere;
- style control.

Responsibilities:

```text
validated result
+
permitted context
    ↓
prose / dialogue
```

The Parser and Narrator can use different local models.

A larger model is not required for every task.

---

## Narrator Constraints

The narrator receives:

```text
validated state
+
visible entities
+
permitted knowledge
+
recent results
+
style instructions
```

The narrator must not:

- invent items;
- invent exits;
- invent NPCs that do not exist;
- change HP;
- change inventory;
- resolve a failed action as successful;
- reveal hidden facts;
- create quest outcomes;
- alter faction state;
- teleport the player.

Example engine result:

```json
{
  "result": "attack_failed",
  "reason": "target_out_of_range",
  "noise": 4
}
```

Narrator output can be:

> You lunge forward, but the infected is farther away than you expected. Your blade cuts through empty air.

The prose is flexible; the fact is not.

---

[← Context Construction and Memory Layers](13-context-and-memory.md) · [Index](README.md) · [Full Turn Loop and Failure Handling →](15-turn-loop.md)
