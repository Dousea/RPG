# Entity Resolution

> **Status: Partial.** `resolve_npc`, `resolve_location` and `_find_item_entity` match names and ids case-insensitively. There is no description-based resolution and no ambiguity path. See [Implementation Status](../status.md).

A local LLM can identify language references, but the engine should resolve them to real entities.

Player input:

> "Shoot the big one near the door."

The parser may output:

```json
{
  "action": "shoot",
  "target_description": "big one near the door"
}
```

The Entity Resolution layer then searches currently valid entities and may resolve:

```text
"big one near the door"
        ↓
zombie_17
```

If multiple entities match:

```json
{
  "status": "ambiguous",
  "candidates": [
    "zombie_17",
    "zombie_21",
    "bandit_04"
  ],
  "needs_clarification": true
}
```

The system should prefer asking rather than silently making a consequential guess.

This is especially important for pronouns, objects with duplicate names, and spatial descriptions.

---

[Index](../README.md)
