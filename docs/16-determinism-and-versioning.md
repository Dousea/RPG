# Determinism, Randomness, and Versioning

> **Status: Partial.** No seeded randomness anywhere. `SCHEMA_VERSION` in `adapters/save/codec.py` is the only version — see [document 24](24-runtime-and-persistence.md). See [Implementation Status](00-status.md).

## Determinism and Randomness

Randomness should be explicit and reproducible where practical.

Use seeded randomness for:

- procedural generation;
- loot selection;
- encounter selection;
- combat rolls;
- procedural NPC traits;
- regional variation.

Example:

```text
world_seed
+
entity_seed
+
event_counter
→ deterministic random stream
```

This makes bugs reproducible.

A useful rule is:

> The same world state plus the same action should produce the same result unless the design intentionally includes an external/randomized input.

---

## Versioning

Version all deterministic systems that affect persistent worlds.

At minimum:

```text
world_schema_version
generator_version
rules_version
combat_version
loot_version
```

A save file should know which versions produced its state.

This prevents an engine update from accidentally rebuilding previously established content differently.

---

[← Full Turn Loop and Failure Handling](15-turn-loop.md) · [Index](README.md) · [Observability, Debugging, and the LLM Security Boundary →](17-observability-and-security.md)
