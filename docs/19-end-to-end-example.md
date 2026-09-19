# End-to-End Example

> **Status: Planned.** Traces a turn through stages that do not exist. See [Implementation Status](00-status.md).

Player input:

> "I strike a match, sneak over to Sarah, and ask what caused the noise."

## Step 1 — Parser

```json
{
  "actions": [
    {"type": "use", "target": "match_01"},
    {"type": "move", "target": "sarah", "approach": "stealth"},
    {"type": "talk", "target": "sarah", "intent": "ask", "topic": "noise"}
  ]
}
```

## Step 2 — Entity Resolution

```text
match_01 → valid
sarah → valid
```

## Step 3 — Validation

```text
match exists → PASS
Sarah in reachable area → PASS
stealth movement possible → PASS
```

## Step 4 — Simulation

```text
match consumed
light_level = dim
movement noise = low
Sarah remains alive/injured
```

## Step 5 — Events

```text
item_used
light_changed
player_moved
conversation_started
```

## Step 6 — State Changes

```text
inventory.match_01 -= 1
scene.light = dim
player.position = sarah's room
```

## Step 7 — Knowledge Filtering

Only facts known by the player are exposed to the narrator.

## Step 8 — Context Builder

```json
{
  "scene": "pharmacy_backroom",
  "light": "dim",
  "player_condition": "exhausted",
  "sarah": {
    "visible_condition": "injured"
  },
  "recent_events": [
    "Player lit a match.",
    "Player moved quietly toward Sarah."
  ]
}
```

## Step 9 — Narrator

The narrator produces prose based only on that validated context.

---

[← Recommended Module Layout](18-module-layout.md) · [Index](README.md) · [Architectural Principles →](20-principles.md)
