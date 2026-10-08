# Relationships, Trust, and Disposition

> **Status: Implemented.** `managers/story/relationship.py`. See [Implementation Status](../status.md).

The data-model doc sketches NPC relationships as a single number on the NPC record:

```json
{"id": "sarah", "relationships": {"player": 72}}
```

The implementation treats the social graph as its own subsystem instead, for
three reasons: relationships are between *any* two entities rather than between
an NPC and the player; liking someone and relying on them move independently;
and the graph has to survive a save round trip without being duplicated onto
every entity that participates in it.

`RelationshipManager` is the single source of truth. No entity stores its own
opinion of another.

## Three stores, all directional

```text
affinities   {source_entity_id: {target_entity_id: -100..100}}
trusts       {source_entity_id: {target_entity_id: -100..100}}
reputations  {source_faction:   {target_faction:   -100..100}}
```

All three are **directional**: `affinities["npc_emma"]["player"]` is what Emma
feels about Orton, and says nothing about what Orton feels about Emma. The
reverse edge is a separate entry that may not exist.

Every write clamps to `[-100, 100]`, so a runaway loop of modifiers cannot push
a score off the scale.

### The direction convention

> Everything that reads a relationship asks **how the NPC regards the player**.
> The NPC is therefore always the `source_id` and the player the `target_id`.

This holds in three places that must agree, and silently produces wrong output
if any one of them flips:

- the starting values in `data/story/npcs.py` (`STARTING_RELATIONSHIPS`), seeded in
  `GameManager.__init__`;
- the social resolvers in `managers/story/social.py`;
- the disposition line the prompt builder writes for each NPC present.

There is no enforcement of this convention in code. It is a convention.

### Identity keys

Relationship keys are **stable string ids** — `NpcEntity.npc_id`,
`PlayerEntity.entity_id` — never `BaseEntity.id`. `BaseEntity.id` is
`id(self)`, a memory address that changes on every process restart, so using it
as a key would scramble the entire social graph across a save and load.

## Affinity and trust are separate axes

Affinity is how much the source *likes* the target. Trust is how much the source
would *rely* on them. The narrative layer moves them independently, which is the
point: a survivor can be fond of Orton and still not hand him the keys, or
depend on him professionally while resenting him.

The model no longer chooses either value. `TALK`, `GIVE` and `REQUEST` move them, by
amounts the engine owns: see [Talking to people](../mechanics/llm-contract.md#talking-to-people).
Affection goes through an `AffinityModifier` (so it shares the path used by the
trait/perk pipeline, see [the traits-and-modifiers doc](traits-and-modifiers.md)); trust goes
through `adjust_trust` directly, because no modifier type carries trust yet.

## Disposition is derived, never stored

`CharacterDisposition` is computed from affinity on every read:

| Affinity | Disposition |
| --- | --- |
| ≥ 75 | `LOYAL` |
| ≥ 40 | `FRIENDLY` |
| 0 … 39 | `NEUTRAL` |
| < 0 | `WARY` |
| ≤ −40 | `HOSTILE` |
| ≤ −75 | `HATED` |

`CharacterDisposition` also defines `TERRIFIED`, which no threshold produces —
it is reserved for a fear system that does not exist.

Because disposition is derived, it is never persisted and can be rebalanced by
changing one function. Trust does not affect it.

## Faction reputation

`reputations` is faction-to-faction and `CharacterFaction`-keyed. The plumbing
is complete — `ReputationModifier`, `apply_reputation_modifier`,
`get_reputation`, and persistence — but nothing in the game writes to it.
`NpcEntity.faction` is set in `data/story/npcs.py` and read by nothing. This is the
seed of the data-model doc's *Factions and World Systems*, not an implementation of it.

## What the prompt exposes

The narrator and the parser see each present NPC's disposition and trust as
bands, never as scores; the `[NPCS PRESENT]` block is listed in
[the LLM contract](../mechanics/llm-contract.md#narrator).

---

[Index](../README.md)
