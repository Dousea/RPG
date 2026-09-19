# Traits, Perks, Effects, and Modifiers

> **Status: Implemented, unreachable.** `modules/effect.py`, `modules/modifier.py`, `GameManager._broadcast_event`. Nothing constructs the events that drive it. See [Implementation Status](00-status.md).

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

`_event_matches_effect_handler` compares class names by prefix:

```text
WeaponTakeDamageEvent  ←  WeaponDamageTakenEffect ?
```

That comparison **fails**. The handler name does not start with the event name;
the pairing is `WeaponTakeDamage` ↔ `WeaponDamageTaken`, which is a
rearrangement, not a prefix. The code's own docstring raises this
(*"this logic might need to be more robust"*). It has never been observed
failing because nothing enqueues an event to dispatch.

A registry mapping event type to handler type would be both correct and
cheaper than introspection.

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

Separating additive from multiplicative types is what lets `_apply_modifiers`
impose an order — all multipliers compose before the result is applied — rather
than letting the order in which traits happened to fire decide the outcome.

## Application

`GameManager._apply_modifiers` currently handles three of the eight:
`DamageMultiplicativeModifier` (composed, then applied to the event's target),
`AffinityModifier` and `ReputationModifier` (forwarded to the
[relationship manager](22-relationships.md)). `XPModifier`,
`HPModifier`, `ConditionsModifier`, `AttributesModifier` and
`XPMultiplicativeModifier` are collected and dropped.

`AffinityModifier` is the only modifier reachable in a real game, because
`UPDATE_RELATIONSHIP` constructs one directly and hands it to the relationship
manager — bypassing the event pipeline entirely.

## Why it is unreachable

`GameManager.event_queue` is drained by `drain_event_queue`, which is called by
`process_turn`, which is called by nothing. The live turn loop is
`GameEngine.play`, which never touches the queue. `process_turn` still contains
the commented-out sketch of how an action was meant to become an event.

To make combat reachable, something must turn a player intent into a
`WeaponDealDamageEvent`. Under the current architecture that something would be
the game master emitting an action verb — which means the LLM would decide that
a hit landed, and the pipeline would only scale the damage. Under
[document 01](01-engine-authority.md)'s architecture the engine would decide,
and the pipeline would be the rules. The dead code is waiting on that choice,
not on an implementation.

---

[← Relationships](22-relationships.md) · [Index](README.md) · [Runtime, Configuration, and Persistence →](24-runtime-and-persistence.md)
