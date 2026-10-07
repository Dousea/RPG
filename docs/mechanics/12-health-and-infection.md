# Body-Part Health and Zombie Infection

> **Status: Implemented.**

The zombie mechanic records every scratch, laceration and bite a zombie lands.
This mechanic gives the player a body to land them on: 17 parts, each with its
own health and wounds. Wounds bleed, hurt, heal slowly or quickly depending on
whether they are bandaged, can become infected and, when a zombie passed on the
zombie infection, kill the player in two or three days. The player can fight back
with bandages, disinfectant, painkillers and antibiotics.

Three rules shape everything below:

- **Overall health is derived from the parts.** It is 100 less the weighted
  damage of every part, with the damage capped at 100. A part's weight runs from
  0.1 for a hand to 0.7 for the neck, so 10 damage on a hand costs 1 overall
  health, not 10.
- **An untreated wound keeps hurting.** Every open, unbandaged wound damages its
  part every minute, and bleeding drains overall health. A bandage stops both
  and speeds healing up many times over.
- **A zombie scratch doesn't bleed.** Lacerations and bites do.

## What we port

| Piece | File |
| --- | --- |
| `PartState`, the part weights, overall health, the general wound infection | `modules/body/parts.py` |
| `MedicalItem`, and `uses` on the item entity | `modules/item.py`, `modules/entity/item.py` |
| `PlayerEntity.body`, `zombie_infection_since`, `zombie_infection_hours`, `pain_effect_minutes`, `reduce_infection_power`; `hit_points` as a read-only view | `modules/entity/player.py` |
| The verbs `BANDAGE`, `REMOVE_BANDAGE`, `DISINFECT` and the part target | `modules/action/types.py`, `modules/action/parser.py`, `modules/action/words.py`, `modules/resolution.py` |
| Every number below and the fact wording | `data/body/health.py` |
| The 11 medical items; the first aid kit's fixed contents | `data/items.py`, `data/world/locations.py` |
| The 1-minute costs and the slowed actions | `data/time_costs.py` |
| `reduce_general`, `add_general`, wound landing, the body minute, pain, the limp, the action-time multiplier, the zombie infection | `managers/body/health.py` |
| The three treatments, painkillers, antibiotics, the choice of part and item | `managers/body/first_aid.py` |
| A zombie's wound going into a part | `managers/zombies/attack.py` |
| Wound infection joining the Sick status effect, the Bleeding level | `managers/body/stats/status_effects.py` |
| The body minute after the zombie minute, interruptions, the limp on hops, death causes | `managers/simulation.py` |
| The limp on the player's pace and the walk up to a zombie | `managers/zombies/population.py` |
| The refusals | `managers/validator.py` |
| `[CONDITION]` part lines, `[INVENTORY]` uses, the `hurt` scene key | `managers/context.py` |
| `body` in the page payload and the Health screen | `adapters/engine.py`, `static/app.js` |
| The saved body and zombie-infection fields | `adapters/save/codec.py` |

**Not built here.** Deep wounds, glass, bullets, burns, fractures, splints and
stitching wait for the other-injuries mechanic. Poultices, cauterising, sleeping
pills and the non-lethal fake infection are not part of this game. Ripped
sheets exist in the catalogue and nothing makes them yet. Dirty and bloody
clothing are always false, so the infection roll's clothing terms never apply.
Arm pain does not yet lower melee damage.

## The body

The player has `body: dict[BodyPart, PartState]`, in this order: left hand,
right hand, left forearm, right forearm, left upper arm, right upper arm, upper
torso, lower torso, head, neck, groin, left thigh, right thigh, left shin, right
shin, left foot, right foot.

| Part | Weight | Bleeding × | Pain × |
| --- | --- | --- | --- |
| Left hand, right hand | 0.1 | 0.2 | 0.5 |
| Left forearm, right forearm | 0.2 | 0.3 | 0.6 |
| Left upper arm, right upper arm | 0.3 | 0.4 | 0.6 |
| Upper torso | 0.35 | 0.5 | 0.7 |
| Lower torso | 0.4 | 0.9 | 0.78 |
| Head | 0.6 | 1.0 | 0.8 |
| Neck | 0.7 | 1.5 | 0.8 |
| Groin | 0.4 | 0.5 | 0.7 |
| Left thigh, right thigh | 0.3 | 0.4 | 0.7 |
| Left shin, right shin | 0.2 | 0.3 | 0.6 |
| Left foot, right foot | 0.2 | 0.2 | 0.5 |

`PartState`:

| Field | Meaning |
| --- | --- |
| `health` | 0 to 100 |
| `scratch_time`, `cut_time`, `bite_time` | a wound is open while its time is above 0 |
| `bleeding_time` | the part bleeds while it is above 0 and the part has no bandage |
| `bandage` | the bandage's item id, or none |
| `bandage_life` | at 0 the bandage is dirty |
| `bandage_alcoholic` | an alcohol bandage with life left blocks wound infection |
| `bandage_xp_ready` | First Aid XP is given at most once per wound |
| `zombie_infected` | the part carries the zombie infection |
| `infected_wound` | the wound is infected (not the zombie infection) |
| `wound_infection` | −2 to 10 |
| `alcohol` | disinfectant still working |
| `extra_pain` | pain from disinfecting |
| `stiffness` | training stiffness, which now lives on the part |

A part is **bleeding** when `bleeding_time > 0` and it has no bandage. It is
**injured** when any wound time or `bleeding_time` is above 0.

### Overall health

```
health = 100 − min(100, Σ (100 − part.health) × weight)
```

`player.hit_points` is a read-only view that rounds the health up, so only a body
at 0 reads as dead. Nothing sets it. The player dies when health reaches 0.

Two helpers move health:

- **`reduce_general(v)`:** every part loses `v / 17 / weight`, down to 0. On a
  full body that lowers health by exactly `v`. A part already at 0 absorbs
  nothing, so the loss can be smaller. A sleeping player is woken first if
  health is 10 or less.
- **`add_general(v)`:** `v` is split evenly over the parts below 100, each capped
  at 100.

## The body minute

The body updates in **1-minute steps**. A neck bite can kill in under ten
minutes, so the 10-minute stat chunks are too coarse. The step runs for every
minute an action spends, before and after the outbreak, after the zombie minute
(so a wound bleeds from the minute it lands) and before the stat chunk that
covers it. Status effect levels are read as the stat chunk last left them.

Each minute, in this order:

0. **Thermal damage cap.** With a thermal damage stage above 0, health can't
   exceed `100 − 100 × stage`; if it does, `reduce_general` takes the difference.
   At stage 1 the player dies, and nothing else runs that minute. The minute's
   healing comes after the cap, so health can sit a fraction above it.
1. **Infection onset.**
2. **Regeneration.**
3. **Status effect damage:** starving, thirst and fever losses, and the Bleeding level-4
   loss, through `reduce_general`.
4. **The pain stat.**
5. **Infection progression.**
6. **Each part**, in body order: wound damage, timers, bandage wear, bleeding,
   wound infection.
7. **Stress** from wounds.
8. **Overall health** is checked; at 0 the player dies.

## Wounds

A zombie's attack picks the part, the kind and the damage. When the wound lands:

- `part.health −= damage`, down to 0.
- The part's bandage is lost.
- The wound's time is **set**; a second wound of the same kind replaces the first:

  | Kind | Time | Fast Healer | Slow Healer | Infection chance |
  | --- | --- | --- | --- | --- |
  | Scratch | U(7, 15) | U(4, 10) | U(15, 25) | 7% |
  | Laceration | U(10, 20) | U(5, 10) | U(20, 30) | 25% |
  | Bite | U(50, 80) | U(30, 50) | U(80, 150) | always |

- A bite also makes the wound infected.
- A laceration or bite sets `bleeding_time`, recomputed from everything open on
  the part:

  ```
  t  = U(0.3, 0.6) × scratch_time   if a scratch is open
     + U(0.7, 1.0) × cut_time       if a laceration is open
     + U(7.5, 15)                   if a bite is open
  bleeding_time = t × the part's bleeding ×
  ```

A scratch alone sets nothing. A forearm laceration bleeds for 2.1 to 6 units, a
neck bite for 11 to 22.

### Wound damage

While a wound is open and the part has **no bandage**, the part loses health every
minute:

| Wound | Part health per game hour | Neck |
| --- | --- | --- |
| Scratch | 57.9 | 289.5 |
| Laceration | 115.7 | 578.5 |
| Bite | 135.0 | 675 |

Open wounds add up. A bandage, even a dirty one, stops this damage.

### Wound times

| Timer | Per game hour, no bandage | With a bandage |
| --- | --- | --- |
| `scratch_time` | −0.108 | −1.62 |
| `cut_time` | −0.0108 | −0.54 |
| `bite_time` | −0.054 | −1.08 |
| `bleeding_time` | −0.216 | −2.16 |

A scratch heals in 3 to 6 days unbandaged or 4 to 9 hours bandaged; a laceration
in 39 to 77 days or 18 to 37 hours; a bite in 39 to 62 days or 46 to 74 hours.

- When `scratch_time` runs out, the part stops bleeding, even with a laceration
  still open.
- When `cut_time` runs out, the part stops bleeding.
- When a wound heals, `bandage_xp_ready` becomes true again.
- When a wound heals and every wound time on the part is 0, `wound_infection`
  becomes 0 and the wound is no longer infected.

### Bandage wear

While a part has a bandage with life left, `bandage_life` falls, down to 0. The
rows add up:

| While | Per game hour |
| --- | --- |
| a bite is open | −1.08 |
| the part has `bleeding_time > 0` | −3.24 |
| the wound is infected | −2.16 |
| a scratch is open | −0.864 |
| a laceration is open | −0.108 |

A standard bandage lasts about 5 units at First Aid 0, so a bandaged bite goes
dirty in under an hour. A dirty bandage stays on: it still stops wound damage and
bleeding and still speeds healing, but it raises the odds of infection and gives
no protection from an alcohol bandage. At 0, `bandage_xp_ready` becomes true.

## Bleeding

Each bleeding part drains overall health through `reduce_general`:

```
HP per game hour = 1.763 × bleeding_time      (neck: 8.82 × bleeding_time)
```

The **Bleeding status effect** is the number of bleeding parts, capped at 4, and 4
whenever the neck bleeds. Its levels are Minor Bleeding, Bleeding, Severe
Bleeding and Massive Blood Loss. At level 4 the player also loses **178.2 HP per
game hour**.

| Wound | No bandage | Bandaged by minute 2 |
| --- | --- | --- |
| Neck bite | dead in about 8 minutes | recovers within hours |
| Lower-torso laceration (cut time 15) | dead in about 5 hours | full health within the hour |
| Forearm laceration or bite | health bottoms out around 75 to 80 | full health within the hour |
| Forearm scratch | the forearm reaches 0: overall 80 until it heals | full health within the hour |

## Healing

Each minute, `add_general` gives back:

| State | Per game hour |
| --- | --- |
| Awake, no Hungry, Thirst or Sick at level 2 or 3 | 21.6 |
| Awake, any of them at level 2 | 14.04 |
| Awake, any of them at level 3 | 8.64 |
| Awake, Hungry or Thirst at level 4 | 0 |
| Asleep (replaces the rows above) | 216 |
| Plus, while the well-fed timer runs | 162 |

- Asleep with Hungry or Thirst at level 4, nothing is regained, food included.
- Sick at level 4 on its own doesn't slow healing; only levels 2 and 3 of Sick do.
- This is the only way health comes back. No item heals instantly: the canned
  beans and the first aid kit lost their direct healing.

## Pain

### Pain from each part

```
p  = 1.7 × scratch_time + 2.5 × cut_time
   + (bite open: 30 if bandaged, else 50)
p  = p ÷ 1.5                       if bandaged
p += wound_infection               if above 0
p += extra_pain + stiffness ÷ 3.5
```

`extra_pain` falls by 54 per game hour. `stiffness` falls by 21.6 per game hour
while no exercise region is still draining stored stiffness into the parts.

### The pain stat

The target is `Σ p × the part's pain ×`. Each minute:

- If the target is above `pain`, the gap shrinks to 0.7985 of itself:
  `pain = target − (target − pain) × 0.7985`. Pain reaches its target over about
  4 minutes.
- Otherwise `pain = target`, at once.

This drives the Pain stat and the Pain status effect (10, 20, 50, 75). A bandaged
forearm bite gives pain 12 (Minor Pain); an unbandaged one, 30 (Pain).

### Painkillers

`USE_ITEM` on painkillers takes one pill (1 minute). For **48 game minutes** pain
falls by **157.5 per game hour** and doesn't move toward its target. Another pill
restarts the 48 minutes; they don't stack. Being drunk changes nothing.

### What pain does

- **Sleep:** `SLEEP` is refused at Pain level 2 or higher while fatigue is 0.85
  or below: "too much pain to sleep". It is refused at Panic level 1 or higher.
- **Slower actions.** A timed action's duration is multiplied by:

  ```
  × (1 + Unhappy level / 4)
  × (1 + Drunk level / 4)
  × (1 + (pain of both hands and both forearms, without the pain multiplier) / 300)
  × cold hands
  ```

  Cold hands is `1 + Σ k × 0.25 × s × skin surface` over the hands (k 0.3), forearms
  (0.15) and upper arms (0.1), with `s = (1 − (skin °C − 20) / 13)²` below 33 °C and
  0 otherwise. It never exceeds about ×1.006.

  It applies to the fixed-cost actions: `TAKE`, `DROP`, `USE_ITEM`, `WEAR`,
  `TAKE_OFF`, `EQUIP`, `UNEQUIP`, `BANDAGE`, `REMOVE_BANDAGE` and `DISINFECT`. The
  factor is read before the action's effect, and the result is rounded to the
  nearest minute, at least 1. It doesn't apply to `MOVE_TO`, `WAIT`, `SLEEP`,
  `EXERCISE`, swings or talking.
- **The limp** (below).

### The limp

For the groin, thighs, shins and feet, each part gives

```
foot only: 1 if a bite is open (× 0.7 if bandaged)
if scratch_time > 2 or cut_time > 5 or a bite is open:
    + scratch_time / s + cut_time / c + bite_time / 20    (÷ 2 if bandaged)
```

with `s, c` = 45, 55 for the groin, thighs and shins, and 35, 45 for the feet. `L` is
the sum over those parts.

When `L > 0.1`, every pace is × `max(0.25, 1 − L / 1.5)`. `MOVE_TO` minutes per hop
are divided by it and rounded, the gap the player opens on a chaser shrinks by it,
and the walk up to a zombie takes longer. A shin laceration (L about 0.27) is × 0.82;
a bitten thigh drops to × 0.25 until the bite heals.

## Wound infection

This is ordinary infection, not the zombie infection.

**Catching it.** Each minute, a part with an open scratch or laceration that is not
already infected, not zombie-infected, and not under an alcohol bandage with life left
rolls with a per-frame chance of `1/n`, over the 112.5 frames of a minute:

```
n = 40000
  − 10000 with no bandage, or − 35000 with a dirty bandage
  − 20000 if a scratch is open
  − 25000 if a laceration is open
n = max(n, 5000)
```

| Wound | `n` | Expected infections per game hour |
| --- | --- | --- |
| Scratch, no bandage | 10000 | 0.68 |
| Scratch, bandaged | 20000 | 0.34 |
| Laceration, no bandage | 5000 | 1.35 |
| Laceration, bandaged | 15000 | 0.45 |
| Either, dirty bandage | 5000 | 1.35 |
| Either, alcohol bandage with life left | — | 0 |

Disinfecting doesn't prevent infection. The alcohol only works on a wound that is
already infected. Each eligible part uses one random draw per minute, in body order.

**Once infected**, each minute:

- If `alcohol > 0`: `alcohol` and `wound_infection` each fall 2.16 per game hour.
- If the antibiotic power is above 0: `wound_infection` and the power each fall 2.16
  per game hour.
- If neither applied, `wound_infection` rises: 2.16 per game hour on a zombie-infected
  part, 0.108 otherwise.
- Under a bandage with life left, an alcohol bandage lowers `wound_infection` by
  6.48 per game hour.

`wound_infection` is capped at 10. At 0 or below the wound is no longer infected, and
it floors at −2. `alcohol` also falls 2.16 per game hour on a wound that isn't
infected.

**Effects:** the level adds to the part's pain, and the general wound infection
(`min(100, 10 × Σ wound_infection over infected parts)`) feeds the Sick status effect. At
Sick level 4, if food sickness doesn't exceed the zombie infection but the general wound
infection does, the player loses 178.2 HP per game hour.

## Zombie Infection

- **Onset:** the first minute any part has `zombie_infected`, the player is infected:
  `zombie_infection_since` is the hours survived, and `zombie_infection_hours` is `U(2, 3) × 24`, × 1.25
  with Resilient, × 0.75 with Prone to Illness. It never ends: healing the wound
  doesn't matter, and nothing cures it.
- **Progression**, each minute:

  ```
  x = min((hours_survived − zombie_infection_since) / zombie_infection_hours, 1)
  zombie_infection = 100 × x
  cap = 100 × (1 − x⁴)
  if x == 1: health falls to 0
  elif cap ≤ 99 and health > cap: reduce_general(health − cap)
  ```

- `zombie_infection` feeds the Sick status effect, whose value is the worst of food
  sickness, the zombie infection and the general wound infection.

| Progress | Hours after a bite (48 to 72 h course) | Health cap |
| --- | --- | --- |
| 25% | 12 to 18 | none yet (the cap is above 99) |
| 50% | 24 to 36 | 93.75 |
| 75% | 36 to 54 | 68.4 |
| 90% | 43 to 65 | 34.4 |
| 100% | 48 to 72 | dead |

The Sick status effect names the stage: Queasy above 25%, Nauseous above 50%, Sick above
75%, Fever above 90%. The Sick-4 damage branch doesn't fire for the zombie infection; the health
cap does the killing.

## Stress

Each of these adds **0.18 stress per game hour** while it holds, once per source
however many parts have it:

- any part has an open, unbandaged bite;
- any part has an open, unbandaged scratch;
- the player has the zombie infection.

Bandaging stops the first two.

## Treatment

Three verbs, each **1 minute** before the action-time multiplier. Each refuses while
asleep, and a refusal costs 0 minutes.

### `BANDAGE <part> [with <item>]`

- **Allowed** when the part is injured and has no bandage, and the player carries an
  item with `bandage_power > 0`.
- **No part given:** the unbandaged injured part with the highest score: +100
  bleeding, +50 scratch open, +50 bite open; ties go to the first in body order.
- **No item given:** an alcohol bandage first, then the highest `bandage_power`,
  dirty items last.
- **Effect:**
  - With Fear of Blood, panic +50 if the part has `bleeding_time > 0`.
  - `bandage_life = U(0.5, 1.0) × (First Aid + 1) + bandage_power`, or 0 for a dirty
    item.
  - First Aid +5 XP if `bandage_xp_ready` and the life is above 0; then
    `bandage_xp_ready` becomes false. The skill's own XP multipliers apply.
  - The part's bandage is the item, `bandage_alcoholic` its `alcoholic`, and the item
    leaves the inventory.

### `REMOVE_BANDAGE <part>`

- **Allowed** when the part has a bandage and the inventory has room.
- **Effect:** the bandage comes back to the inventory. If its life is 0 and it isn't
  reusable, it comes back as its dirty version; an item with no dirty version (the
  adhesive bandage) is gone. A reusable (already dirty) item comes back as it is. A
  bandage with life left comes back as it was.

### `DISINFECT <part> [with <item>]`

- **Allowed** when the part is injured and has no bandage, and the player carries an
  item with `alcohol_power > 0` and uses left.
- **No item given:** alcohol wipes before a disinfectant bottle.
- **Effect:** `alcohol += 4`, `extra_pain += 52 − First Aid / 2`, and one use is
  spent. No XP.

### Antibiotics

`USE_ITEM` on antibiotics (1 minute) consumes the item and **sets** the player's
reduce-infection power to 50; a second dose resets it. The power falls 10.8 per game
hour on its own, and 2.16 per game hour for each infected wound it is treating.
Antibiotics do nothing for the zombie infection.

## Items

`MedicalItem` is a holdable item type with these fields:

| Field | Meaning | Default |
| --- | --- | --- |
| `bandage_power` | how much life a bandage gives | 0 |
| `alcoholic` | an alcohol bandage | false |
| `dirty_version` | the item a spent bandage becomes | none |
| `reusable_bandage` | an already-dirty bandage that comes back as it is | false |
| `dirty` | gives no life | false |
| `alcohol_power` | works as disinfectant | 0 |
| `uses` | uses before the item is gone | 1 |
| `reduce_infection_power` | antibiotic power | 0 |
| `painkiller` | a pill | false |

| Item | Values |
| --- | --- |
| Bandage | power 4; dirty version Dirty Bandage |
| Dirty Bandage | power 0.5; dirty; reusable |
| Sterilized Bandage | power 4; alcoholic; dirty version Dirty Bandage |
| Adhesive Bandage | power 1.5; no dirty version |
| Ripped Sheets | power 2; dirty version Dirty Ripped Sheets |
| Dirty Ripped Sheets | power 0.5; dirty; reusable |
| Sterilized Ripped Sheets | power 2; alcoholic; dirty version Dirty Ripped Sheets |
| Alcohol Wipes | alcohol power 4; 5 uses |
| Disinfectant | alcohol power 4; 3 uses |
| Painkillers | painkiller; 10 uses |
| Antibiotics | reduce-infection power 50; 1 use |

**The first aid kit.** The game has no loot rolls, so the kit item and its direct
healing are gone, and the building zone holds fixed contents instead: **2 Bandages,
1 Adhesive Bandage, Alcohol Wipes and Painkillers**.

`USE_ITEM` on a bandage or disinfectant is refused with "Use BANDAGE or DISINFECT."

## Death

The game ends when overall health reaches 0. The cause is the largest health loss in
the final minute:

| Cause | Fact |
| --- | --- |
| bleeding | "Orton bled to death." |
| wound damage | "Orton died of the wounds." |
| Infection progression | "Orton died of the zombie infection." |
| a status effect | "Orton died of starvation." (also thirst, fever, infection) |
| the thermal damage cap | "Orton died of the cold." or "Orton died of the heat." |

A zombie's drag-down or a killing wound ends the game with its own fact.

**Rising.** Anyone who dies with `zombie_infection` of 0.001 or more rises. Any death
while infected, whatever its cause, ends the final fact with "...and rose again."
The player's body becomes a zombie where they fell
([The Zombie Lifecycle](14-zombie-lifecycle.md#the-player-who-rises)).

## Interruptions

A `WAIT`, `SLEEP` or `EXERCISE` stops when the **Injured** or **Bleeding** status effect
rises a level, so a player never bleeds out inside one long action without a chance
to react. The fact says why: "Orton is getting weaker." A sleeper wakes ("Orton wakes,
badly hurt."). A sleeper is also woken when overall health is 10 or less.

## Traits

| Trait | Effect |
| --- | --- |
| Fast Healer | shorter wound times |
| Slow Healer | longer wound times |
| Resilient | The zombie infection takes × 1.25 as long |
| Prone to Illness | The zombie infection takes × 0.75 as long |
| Fear of Blood | panic +50 when bandaging a part that is bleeding |

## Hooks into earlier specs

- **Clock:** `BANDAGE`, `REMOVE_BANDAGE` and `DISINFECT` cost 1 minute; the fixed
  costs go through the action-time multiplier.
- **Survival stats:** `hit_points` is derived from the body; the status effect health losses
  run in the body minute; Sick level 4 gains the wound-infection branch; Pain and
  `zombie_infection` are driven here; stress gains the wound and zombie-infection sources.
- **Status effects:** the Bleeding level counts bleeding parts; the Injured level reads the
  derived health; the canned beans no longer heal.
- **Clothing:** unchanged; its dirt and blood, when added, feed the infection roll.
- **Body temperature:** the skin temperatures feed the cold-hands factor, and the
  thermal damage stage caps health.
- **Character creation:** Fast Healer, Slow Healer, Fear of Blood, Resilient and Prone
  to Illness take effect.
- **Skills:** First Aid gains its first XP source; part stiffness now hurts, slows
  actions through hand pain, and decays.
- **Zombies:** a wound's damage goes into its part; the infection roll sets `zombie_infected` on the
  part; the limp slows every pace and the walk up to a zombie.
- **LLM contract:** the three verbs join the parser's list when any part is injured or
  bandaged; `[CONDITION]` lists the wounded parts; `[INVENTORY]` shows uses left.

## What the narrator and the player see

- **Facts:**
  - "Orton bandages the left forearm."
  - "Orton takes the dirty bandage off the left forearm."
  - "Orton dabs disinfectant on the left hand. It stings."
  - "The left forearm has stopped bleeding."
  - "The bandage on the left forearm is soaked through."
  - "The scratch on the left hand has healed."
  - "Orton takes a painkiller."
  - "Orton is getting weaker."
  - "Orton is weakening from hunger." (also thirst, fever, infection), once per cause
    per turn however many actions in it spend time
- **`[CONDITION]`:** the status effects, now with Bleeding and Pain, then a line per injured
  or bandaged part: "left forearm: bite, bleeding", "left forearm: bite, bandaged
  (dirty)", "right hand: scratch, infected". *Infected* appears only on an unbandaged
  wound. A healed part drops off the list.
- **The zombie infection is never named.** No block says the player is infected, and no fact does,
  until the death fact. The narrator sees the bite and, later, the Sick status effect.
- **Parser:** the part lines let it propose `BANDAGE left forearm`; `[INVENTORY]`
  shows "Painkillers (7 left)" and "Dirty Bandage".
- **Page:** the `/play` payload carries
  `body: [{part, wounds: [kind], bleeding, bandaged, dirty, infected}]`, and the Health
  screen lists each part in words. No health or pain number is sent; the old health bar
  and its `vitals` field are gone.

## Saves

Schema version 16 adds `player.body` (every `PartState` field, including stiffness,
which moved here from the exercise state), `zombie_infection_since`, `zombie_infection_hours`,
`pain_effect_minutes`, `reduce_infection_power`, and each medical item's `uses`. The
player's `hit_points` and `fractional_hp_loss` are no longer saved. Older saves are
discarded.

## Edge cases

- **Two wounds on one part.** The new wound's time replaces any open wound of that
  kind; bleeding is recomputed from everything open; the bandage is lost.
- **A neck bite.** Bleeding status effect 4 at once. The next turn's `BANDAGE neck` saves the
  player from bleeding out, but not from the zombie infection.
- **Bandaging a part with no wound.** Refused ("The left hand isn't hurt.").
- **Bandaging over a bandage.** Refused; `REMOVE_BANDAGE` first.
- **A dirty bandage left on.** It keeps stopping bleeding and damage, and healing
  continues at the bandaged rate, but infection odds are the worst.
- **Everything healed on an infected part.** The wound infection resets to 0.
- **Asleep and bleeding.** Allowed; the interruption rule and the wake at health 10
  both apply.
- **Infected, then killed by a zombie.** Rises: the death fact ends "...and rose
  again."
- **Painkillers twice.** The second pill restarts the 48 minutes; it doesn't stack.
- **Determinism.** Wound times, bleeding and bandage life use the simulation's own
  random source in the order written above; the infection roll is one draw per
  eligible part per minute, in body order.

## Testing

`tests/body/test_body.py` covers the part table, overall health, the two helpers, wound
landing, part pain, the pain stat, the limp and the action-time multiplier.
`tests/body/test_body_minute.py` covers bleeding, wound damage, timers, bandage wear,
healing, status effect damage, death causes, pain over minutes, infection, stress, the zombie infection and
the thermal cap. `tests/body/test_first_aid.py` covers the parser forms, the three verbs,
the choice of part and item, pills, antibiotics and every refusal.
`tests/test_simulation.py` covers the sleep refusals, the slowed actions, the limp on
hops and chases, the weakening interruption, a wound landing in a part and rising.
`tests/test_items.py` pins the medical catalogue and the kit's contents,
`tests/test_context.py` the prompt lines, `tests/test_engine.py` the payload and
`tests/test_persistence.py` the save fields.
