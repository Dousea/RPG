# Traits, Perks, Effects, and Modifiers

> **Status: Implemented, live.** `modules/effect.py`, `modules/modifier.py`, `managers/events.py`. `managers/simulation.py`'s `SimulationCore` now constructs the events that drive it — every `ATTACK` and `USE_ITEM` action goes through this chain. See [Implementation Status](00-status.md).

The design documents mention traits only in passing, as something a world
generator might roll for an NPC. In the implementation they are a general
mechanism for **letting character definition change rules without the rules
knowing the characters exist**.

This is the one place the codebase already does what
[document 03, principle 3](20-principles.md) asks for: systems communicate
through typed events rather than direct calls.

## The chain

```text
EVENT                  a typed dataclass describing something that happened
  ↓
BROADCAST              to entities relevant to that event (source, target)
  ↓
EFFECT HANDLER         a trait's or perk's declared reaction to that event type
  ↓  condition(event)  → bool     does this reaction apply right now?
  ↓  effect(event)     → Modifier what it produces
  ↓
MODIFIER               a typed dataclass describing a change to make
  ↓
APPLY                  in a controlled order, by modifier type
```

Nothing in this chain names a specific trait. A new trait is data.

## Events

`modules/event.py`. Five types, all generic over the entity types involved:

```text
QuestCompletionEvent     source, experience_points_gained, styles[]
WeaponTakeDamageEvent    source, weapon, damage, target
WeaponDealDamageEvent    source, weapon, damage, target
ApplyItemEvent           source, item, target
ConsumeItemEvent         source, item
```

These are **not** the narrative events in `MemoryState.full_event_log`, which
are English sentences written by the game master. The two are unrelated, share
the word, and are easy to confuse. There is no bridge between them, and building
one is what [document 02](02-system-boundaries.md)'s event bus would require.

## Effects

`modules/effect.py`. An effect handler is a `condition`/`effect` pair of
callables, both taking the event:

```python
ItemAppliedEffect[PlayerEntity](
    condition=lambda event: "medical" in event.item.tags,
    effect=lambda event: (
        ConditionsModifier(conditions={CharacterCondition.PANIC: True})
        if event.source.attributes[PlayerAttribute.WILLPOWER] < 5
        else None
    ),
)
```

That is Hemophobia, from `data/traits.py`: using a medical item panics a
character whose willpower is below 5. The condition gates on the *event*, the
effect gates on the *actor's state*, and either may decline by returning `None`.

`OnceEffect` is the odd one out — it takes a `PlayerEntity` rather than an
event, for effects applied at character creation. Nothing dispatches it.

## Matching handlers to events

The event-to-handler matcher used to compare class names by prefix:

```text
WeaponTakeDamageEvent  ←  WeaponDamageTakenEffect ?
```

That comparison **failed unconditionally**. The handler name does not start
with the event name; the pairing is `WeaponTakeDamage` ↔ `WeaponDamageTaken`,
which is a rearrangement, not a prefix. It was never observed failing only
because nothing enqueued an event to dispatch.

It has been replaced with exactly the registry this document suggested:
`EVENT_TO_EFFECT_TYPES` in `managers/events.py` maps each event type to the
effect-handler types that react to it, checked with `isinstance`. A second
map, `EFFECT_REQUIRED_ROLE`, closes a related bug the string comparison could
never have caught even if fixed naively: `broadcast_event` visits both an
event's source and target, and without a role check, an attacker who happens
to also carry a "damage taken" trait would have it fire on their own
outgoing hit. Each effect type now declares which role (`"source"` or
`"target"`) an entity must occupy to be eligible to react at all.

## Modifiers

`modules/modifier.py`. Eight types, deliberately dumb — they describe a change
and carry no logic:

```text
XPModifier                    amount
XPMultiplicativeModifier      multiplier
HPModifier                    amount
DamageMultiplicativeModifier  multiplier
ConditionsModifier            {CharacterCondition: bool}
AttributesModifier            {PlayerAttribute: int}
AffinityModifier              source_id, target_id, amount
ReputationModifier            source_faction, target_faction, amount
```

Separating additive from multiplicative types is what lets `apply_event_modifiers`
impose an order — all multipliers compose before the result is applied — rather
than letting the order in which traits happened to fire decide the outcome.

## Application

`apply_event_modifiers` (`managers/events.py`) handles five of the eight:
`DamageMultiplicativeModifier` (composed, then applied to the event's target),
`AffinityModifier` and `ReputationModifier` (forwarded to the
[relationship manager](22-relationships.md)), and `HPModifier` and
`ConditionsModifier` (applied to the event's target, or its source for an
event with none). `XPModifier`, `AttributesModifier` and
`XPMultiplicativeModifier` are still collected and dropped — nothing on the
live path produces them yet (`OnceEffect`, which is how `AttributesModifier`
is meant to apply, runs at character creation, not per-event, and nothing
dispatches it still; see [document 00](00-status.md)'s open issues).

`managers/simulation.py`'s `SimulationCore` is the actual caller for combat
and item use — it calls `broadcast_event` directly rather than
`drain_event_queue`, because a single `ATTACK` needs to combine modifiers
from *two* events (a `WeaponDealDamageEvent` for the attacker's reactions and
a `WeaponTakeDamageEvent` for the defender's) before applying damage exactly
once, which `drain_event_queue`'s one-event-in, one-event-applied loop can't
express. `GameManager.drain_event_queue`/`event_queue`
remain as a simpler broadcast-and-apply convenience for a future event that
only needs one perspective, and `SimulationCore.resolve` uses it for item
use (`ConsumeItemEvent`/`ApplyItemEvent`), where there's no dealt/taken split.

## Why it used to be unreachable, and isn't now

`GameManager.event_queue` used to be drained by `drain_event_queue`, called by
`process_turn`, called by nothing — the live turn loop was `GameEngine.play`,
which never touched the queue. Both `process_turn` and its placeholder
`_generate_narrative_for_turn` (a hardcoded string) have been deleted; they
were the dead scaffold this section used to describe.

[Document 01](01-engine-authority.md)'s architecture answers the question
this document used to leave open: the engine decides whether a hit landed,
not the LLM. `managers/validator.py`'s `ActionValidator` accepts or rejects
an `ATTACK` (is the target here, are they already down, is the player
capable of attacking), and `SimulationCore._resolve_attack` is what actually
constructs the events above and lets this chain run.

---

[← Relationships](22-relationships.md) · [Index](README.md) · [Runtime, Configuration, and Persistence →](24-runtime-and-persistence.md)
