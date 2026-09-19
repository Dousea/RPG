# Architectural Principles

> **Status: Partial.** Principles 1, 2, 7 and 10 are honoured in spirit. 3, 4, 5, 6, 8 and 9 are not implemented. See [Implementation Status](00-status.md).

The system should follow these principles throughout development.

### Principle 1 — Truth lives in the engine

LLMs interpret and describe. They do not own game state.

### Principle 2 — Data beats prose

Important gameplay facts must exist as structured data.

### Principle 3 — Events connect systems

Use events and state transitions instead of tightly coupling unrelated subsystems.

### Principle 4 — Generate deterministically

Procedural content must be reproducible from versioned seeds and rules.

### Principle 5 — Simulate selectively

Use level-of-detail simulation instead of running every world entity at full fidelity.

### Principle 6 — Knowledge is scoped

Different actors can know different facts. Context must respect those boundaries.

### Principle 7 — Validate every LLM action

Never execute raw model output against persistent state.

### Principle 8 — Persist mutations, not redundant generated data

Store what changed from the deterministic baseline.

### Principle 9 — Time is a simulation system

World changes should be driven by clocks, schedules, and events.

### Principle 10 — Narration is presentation

The narrator may add style and detail, but it must not change the outcome.

---

[← End-to-End Example](19-end-to-end-example.md) · [Index](README.md) · [Final Architecture →](21-final-architecture.md)
