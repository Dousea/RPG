# Knowledge, Visibility, and Information Security

> **Status: Planned, and actively violated.** `build_prompt` sends the game master every NPC's raw affinity and trust scores, private notes and full status list, plus every world flag, with no filter for what the player could know. See [Implementation Status](00-status.md).

Separate world truth from knowledge.

```text
WORLD TRUTH
     │
     ├── PLAYER KNOWLEDGE
     ├── NPC KNOWLEDGE
     ├── FACTION KNOWLEDGE
     └── HIDDEN INFORMATION
```

Example:

```json
{
  "world_truth": {
    "traveler_is_heir": true
  },
  "player_knowledge": {
    "traveler_is_heir": true
  },
  "crown_knowledge": {
    "traveler_is_heir": false
  },
  "guild_knowledge": {
    "traveler_is_heir": true
  }
}
```

The Context Builder must never expose hidden data merely because it exists in the world state.

This makes the Context Builder an **information firewall**.

---

[← Combat and Stealth Resolution](10-combat-and-stealth.md) · [Index](README.md) · [Data Model and Persistence →](12-data-model.md)
