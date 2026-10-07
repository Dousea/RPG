# Melee Combat

> **Status: Implemented.**

The zombie mechanic gives the game zombies and what they do to the player. This
mechanic is the other direction: what the player does to a zombie with a melee
weapon, bare hands or a shove. It covers the damage chain, critical hits,
knockdowns, floor attacks and stomps, the knife jaw stab, hitting several
zombies with one swing, weapon wear, and the endurance a swing costs.

Two rules shape everything below:

- **A swing at a target in reach always connects.** Whether a swing hurts is
  decided by the damage chain, not by a to-hit roll.
- **The status effect penalties that earlier documents call "hit chance" are crit
  chance.** Endurance, Heavy Load and Panic lower the chance of a crit, and
  nothing else.

## What we port

| Piece | File |
| --- | --- |
| `MeleeWeaponItem` with its weapon stats; the runtime `condition` and `broken` live on the item entity | `modules/item.py`, `modules/entity/item.py` |
| `ZombieEntity.hits_taken`, `down_until`, `staggered`; `PlayerEntity.zombie_kills` | `modules/entity/zombie.py`, `modules/entity/player.py` |
| The verbs `SHOVE`, `EQUIP`, `UNEQUIP` | `modules/action/types.py`, `modules/action/parser.py`, `modules/action/words.py` |
| Every number below, bare hands, the fact wording, the condition words | `data/melee.py` |
| The crowbar, the kitchen knife, the bat, the pan, the axe | `data/items.py`, `data/locations.py` |
| The 1-minute costs | `data/time_costs.py` |
| Crits, the damage chain, knockdown and stagger, the knife jaw stab, endurance, wear, kills, XP, hit noise | `managers/melee.py` |
| Swing as step 0 of the minute loop, down and staggered zombies, the threat words | `managers/zombies.py` |
| `SHOVE`, `EQUIP`, `UNEQUIP` in the validator and the simulation | `managers/validator.py`, `managers/simulation.py` |
| Which item is in the hands | `managers/combat.py` |
| Hit XP | `managers/skills.py` |
| `[THREATS]`, `[INVENTORY]` and `[CONDITION]` | `managers/context.py` |
| `held` and `zombie_kills` in the page payload | `adapters/engine.py`, `static/app.js` |
| Saving weapon condition, zombie hits and the kill count | `adapters/save/codec.py` |

## Weapons

`MeleeWeaponItem` carries these fields. The condition a weapon is in right now
is saved per item, not on the shared definition.

| Field | Meaning |
| --- | --- |
| `categories` | `axe`, `blunt`, `smallblunt`, `longblade`, `smallblade` or `spear`; each trains a skill (Axe, Long Blunt, Short Blunt, Long Blade, Short Blade, Spear) |
| `min_damage`, `max_damage` | the damage roll |
| `max_range` | reach in tiles |
| `critical_chance`, `crit_dmg_multiplier` | base crit percent (default 0) and crit multiplier (default 2) |
| `max_hit_count` | zombies one swing can hit (default 1) |
| `knockback_on_no_death` | whether a hit that does not kill gives Strength XP |
| `condition_max`, `condition_lower_chance` | full condition, and the wear odds ("1 in N") |
| `weight` | kg |
| `endurance_mod` | default 1 |
| `base_speed` | default 1 (bare hands 0.9); unused until arm injuries |
| `is_stab` | a knife, for the jaw stab |
| `door_damage` | default 1 (bare hands 0); unused until doors |
| `no_criticals`, `no_maintenance_xp` | flags |
| `damage` | HP, used only in a fight with an NPC |

A two-handed weapon fills both hands.

**Bare hands:** damage 0.2 to 0.4, reach 1.1, hits up to 3, endurance modifier
1.7, weight 1, knockback on no kill, no category, no Maintenance XP.

**The catalogue:**

| Item | Where | Stats |
| --- | --- | --- |
| Crowbar | `zone_street` | blunt, 0.6 to 1.15, reach 1.25, crit 20% x 2.5, hits 3, condition 15, wear 1 in 70, 2 kg, two-handed, NPC damage 5 |
| Kitchen knife | `zone_home` | small blade, stab, 0.3 to 0.7, reach 0.9, crit 25% x 4, hits 1, condition 10, wear 1 in 2, 0.7 kg, one-handed, NPC damage 3 |
| Baseball bat | `zone_neighborhood` | blunt, 0.8 to 1.1, reach 1.25, crit 40% x 2, hits 2, condition 15, wear 1 in 20, 2 kg, two-handed, knockback on no kill, door damage 5, NPC damage 5 |
| Frying pan | `zone_home` | small blunt, 0.3 to 0.5, reach 1.1, crit 30% x 2, hits 1, condition 10, wear 1 in 12, 1.5 kg, one-handed, endurance x1.3, no Maintenance XP, door damage 3, NPC damage 2 |
| Hand axe | `zone_building` (basement storage) | axe, 0.7 to 1.5, reach 1.1, crit 15% x 5, hits 2, condition 10, wear 1 in 15, 1.5 kg, one-handed, no Strength XP on a hit that doesn't kill, door damage 20, NPC damage 6 |

The bat swings wider and crits more than the crowbar but fills both hands. The
pan is a light club that tires the player faster. The axe hits hard, crits for
x5 and opens doors fast. The axe also stores a sharpness of 1.0, a head
condition of 10 (max 10), a head multiplier of 1.5 and its repair and sharpen
tags; nothing reads them yet, so sharpness counts as 1 and no head roll happens.
Loot comes from placement and from containers.

## Holding a weapon

- **`EQUIP <item>`** moves a carried holdable into the hands: both hands if it
  is two-handed, otherwise the right hand. It is refused if those hands are full
  ("<name> is already holding the Kitchen Knife."), if the item is not holdable,
  and for a broken weapon.
- **`UNEQUIP <item>`** moves the held item back to the inventory. It is refused
  if the player is not holding it or the inventory is full.
- Each costs 1 minute. A refusal costs nothing.

`ATTACK` and `SHOVE` swing whatever is in the hands, or bare hands. They never
equip anything.

## A swing

`ATTACK <zombie>` is one swing and costs 1 minute. A turn holds at most 5
actions, so "fight it until it drops" is up to 5 `ATTACK`s.

- **Reach.** The target must be at `gap <= 1`. If it is further away, the player
  first closes the gap at walking pace, as for any zombie `ATTACK`. Every weapon
  has the same one-tile reach here.
- **What kind of swing:**

  | Target | In hands | The swing is |
  | --- | --- | --- |
  | standing | a weapon | a weapon hit |
  | standing | nothing | a shove |
  | down | a weapon | a floor attack |
  | down | nothing | a stomp |

- **More than one zombie.** A swing hits the target, then other zombies at
  `gap <= 1` in the same posture (all standing, or all down), nearest first, until
  the weapon's `max_hit_count` is reached. It never hits a zombie on the side
  opposite the target's (front and behind, left and right). The `n`th zombie hit
  takes the split in [Damage](#damage).
- **An idle or alerted target** that is hit starts chasing and faces the player.
  So does every other zombie the swing hits and does not kill.

### Where the swing sits in the minute

The swing is step 0 of the zombie minute loop, before sounds, movement and
attacks. Its sounds are heard by the zombies in the same minute.

## Crits

A swing rolls its crit once, as a percent chance, and the result applies to every
zombie it hits.

**A weapon:**

```
chance = critical_chance + 3 x crit_skill - 5 x Endurance status effect - 5 x Heavy Load status effect - 1.3 x Panic status effect
chance = clamp(chance, 10, 90), truncated
```

`crit_skill` starts as the Long Blunt level. It is replaced in turn by Axe, Long
Blade, Spear, Short Blade and Short Blunt when the weapon has that category, so
the last one listed wins. Heavy Load is 0 until carrying weight exists. Sharpness
is 1 until weapon upkeep exists.

**A shove or stomp:** `35 - 5 x Endurance - 5 x Heavy Load - 1.3 x Panic + 2 x
Strength`, with no clamp.

**Then:**

- **From behind:** +5 if the target's `facing_cos` is below -0.6. For a
  bare-handed swing (a shove or stomp) against an idle or alerted zombie, +30
  instead.
- **`no_criticals`:** the chance is 0.
- **Knives** crit only on a [close kill](#the-knife-jaw-stab), and then
  automatically from behind against an idle or alerted zombie.

A crit multiplies damage by the larger of 2 and the weapon's crit multiplier, and
knocks the zombie down. A shove does no damage, so its crit only knocks down.

## Damage

For each zombie a swing hits, in this order:

```
roll    = uniform(min_damage, max_damage)
damage  = roll x skill_mod x strength_mod
damage  = damage / arms_pain_divisor x arm_speed_factor      # both 1 for now; not for stomps
split   = damage / (0.5 x n)                    # n = 1, 2, 3 for the 1st, 2nd, 3rd zombie hit
split  -= 0.1 x Panic level,  if Panic >= 2
split  -= 0.1 x Stress level, if Stress >= 2
split   = 0.1, if split < 0
stomp only: split = (uniform(0.7, 1.0) + 0.2 x Strength) x shoe_power
split  x= tired_factor[Endurance status effect] x tired_factor[Tired status effect]
split  x= 3, if the head is hit                 # floor attacks and stomps
split  x= 1 - defence / 100                     # the struck part's clothing, see the zombie lifecycle

hits_taken += 1                                  # not for a shove
split  x= 1.5 x (hits_taken - 2), if hits_taken >= 4
dealt   = split x reach_factor
dealt  x= 1.5, if not a stomp and facing_cos < 0.3
dealt  x= 1.5
dealt  x= 0.3 + 0.1 x weapon_level
dealt  x= max(5, crit_multiplier), if a floor attack with a weapon
dealt  x= max(2, crit_multiplier), if a crit

health -= dealt x 0.15
```

| Term | Rule |
| --- | --- |
| `skill_mod` | 1.1 at level 3 to 6 and 1.2 at 7 and up of the weapon's Long Blunt, Axe or Spear skill; otherwise 1 |
| `strength_mod` | by Strength level 0 to 10: 0.75, 0.8, 0.85, 0.9, 0.95, 1.0, 1.05, 1.1, 1.15, 1.2, 1.25 |
| `n` | the first zombie takes x2, the second x1, the third x0.67 |
| `tired_factor` | by status effect level 0 to 4: 1, 0.5, 0.2, 0.1, 0.05 |
| `shoe_power` | the worn shoes' stomp power (trainers 1.8, default 1); 0.5 barefoot |
| `hits_taken` | per zombie, saved, never resets: hits 1 to 3 x1, hit 4 x3, hit 5 x4.5 |
| `reach_factor` | `2 x min(1, max_range) / max_range`: a crowbar gets 1.6, a knife 2.0, bare hands about 1.82 |
| `weapon_level` | the zombie-attack mechanic's weapon level; bare hands give 0 |
| `crit_multiplier` | the weapon's crit multiplier (sharpness is 1 for now) |

A shove does no damage and does not raise `hits_taken`. It still counts as a hit
for the split numbering, XP and sounds. A zombie whose health reaches 0 is
killed ([Kills](#kills)). The arm-pain divisor, arm speed factor and sharpness are
stubs fixed at 1 until their mechanics land. Zombie armour is live: see
[The Zombie Lifecycle](14-zombie-lifecycle.md#armour-against-melee).

A crowbar at Blunt 0 takes about 4 swings to kill a typical zombie, at Blunt 5
about 3, and a kitchen knife about 6 without a jaw stab.

## Knockdowns and staggers

- **Staggered.** A zombie hit or shoved this minute and not knocked down skips
  its attack this minute only.
- **Down.** A knocked-down zombie skips its attack and does not move this minute
  and the next. It gets up at the end of the next minute. Each hit on it while
  it is down keeps it down until the end of the minute after the latest hit.
- A down zombie keeps its side and gap, and its memory still runs.
- A lone zombie is little threat to a survivor who keeps swinging. Three at once
  are a real threat, because one swing reaches at most `max_hit_count` of them.

## Floor attacks and stomps

A swing at a down zombie lands on the head or the neck (see zombie armour in spec 14); the head takes x3, the neck does not.

- **With a weapon:** x the larger of 5 and the crit multiplier on top, and a crit
  is rolled as usual.
- **Bare-handed, a stomp:** the split is the stomp term, crits use the shove
  chance, and there is no x5. A stomp costs double the hit's endurance.

Either one keeps the zombie down.

## Shoves

`SHOVE <zombie>` is one shove, 1 minute, target at `gap <= 1` (closed first like
`ATTACK`). It is what bare-handed `ATTACK` on a standing zombie already is,
available with a weapon in hand too.

- Bare hands for everything (reach, hit count 3, endurance), whatever is held. The
  held weapon takes no wear.
- No damage, and `hits_taken` does not increase.
- Rolls the shove crit chance. A crit knocks the zombie down, otherwise it is
  staggered.
- Refused on a down zombie ("It's already down."); `ATTACK` stomps it instead.
- Refused on an NPC.

## The knife jaw stab

A **close kill** happens when the weapon is a stab weapon and at most one zombie
in the zone is chasing or attacking the player. A stab at `gap <= 1` is always
close.

- Knives crit only on a close kill. Against an idle or alerted zombie from behind
  (`facing_cos` below -0.6) the crit is automatic.
- **A close kill that crits is the jaw stab:** the reach factor is x1000, which
  kills any zombie.
- **The knife may get stuck**, with chance `1 / (r + 2 x (Short Blade + 1))`,
  where `r` is 3 if the zombie was attacking and 8 otherwise. At Short Blade 0
  against an attacker that is 1 in 5. A stuck knife goes into the corpse the kill
  leaves, and `TAKE <knife> from <corpse>` gets it back once the body is searched.
- A close kill costs a fifth of the hit's endurance.

## Endurance

Two drains on the 0 to 1 endurance stat.

**Every swing**, shoves included:

```
max(weight, 1) x 0.18 x weapon_fatigue x fitness_fatigue x endurance_mod x 0.012
```

x1.2 with **Asthmatic**.

**Every zombie hit:**

```
weight x 0.28 x weapon_fatigue x fitness_fatigue x endurance_mod x 0.012 x hit_mod
```

- x2 for a stomp.
- `hit_mod` is 1 for a shove, 0.2 on a close kill, otherwise
  `min(1, min(dealt, health) / max_damage)`, with `dealt` taken before the x0.15
  and `health` the zombie's health before the hit.
- `weapon_fatigue` is 0.8 at level 8 and up of Long Blunt, Axe or Spear for a
  weapon in that category, otherwise 1.
- `fitness_fatigue` by Fitness level 0 to 10: 1.0, 0.95, 0.92, 0.89, 0.87, 0.85,
  0.83, 0.81, 0.79, 0.77, 0.75.

A crowbar swing that connects costs about 0.011 at Fitness 0 and about 0.009 at
Fitness 5. The rest of a fight's cost is the exercise minutes the zombie
mechanic already counts.

## Weapon condition

Each zombie hit with a weapon (not bare hands, not a shove) rolls wear once:

```
lose 1 condition with chance 1 / (condition_lower_chance + Maintenance + weapon_level // 2)
```

A crowbar lasts about 1,000 hits and a kitchen knife about 20.

**At 0 the weapon breaks.** It leaves the hands for the inventory, marked
broken, and `EQUIP` refuses it. The fact says so: "The kitchen knife snaps."
A weapon that breaks partway through a swing finishes that swing: the zombies
still to be hit take its damage, but it neither wears again nor sticks. The
next swing is bare-handed.

## Kills

At health 0 the zombie is killed and removed.

- Stress falls by 0.02.
- `player.zombie_kills` rises by 1.
- The fact: "z3 goes still."

## XP

| Source | Rule |
| --- | --- |
| Each zombie hit | Fitness +1 if endurance is above 0.5; Strength + the swing's hit count; each of the weapon's category skills + `min(3, 0.9 x split)` with the real split. Shoves and bare hands have no category |
| Each zombie hit with a weapon | Maintenance: 50% chance of +2, or of +20 / `condition_lower_chance` when that wear chance is above 10. Not for weapons that give none |
| A hit that does not kill, with a knockback weapon | Strength +2 (shoves count, because bare hands have it) |

A hit on an NPC trains Fitness and Strength only.

## Noise

A swing has no sound of its own. Each hit makes the noise:

| Sound | Radius = volume |
| --- | --- |
| Any hit | 5, volume 1 |
| A hit or shove | 8; then with chance 1 in 3 also 10, else with chance 1 in 7 also 16 |
| A stomp | 8 and 10 |
| A jaw stab | 4 in place of 8, 10 and 16 |

The zombies' hearing takes the loudest sound of the minute, so a quiet knife kill
stays at 5.

## Interruptions during a fight

While the action is `ATTACK` or `SHOVE`, an attack from a zombie that was
already in reach interrupts only if it wounds or drags the player down. A
defended attack or a thump does not. These still interrupt:

- a zombie newly spotting the player;
- a new zombie reaching `gap <= 1`;
- any interruption during the approach minutes: an attack by any zombie other
  than the target stops the plan even when it is defended. The target's own
  attack as the player reaches it stops the plan only if it wounds.

A planned `ATTACK` on a zombie that is already dead is refused and costs 0.

## Fighting NPCs

`ATTACK` on an NPC keeps the older resolution: the trait modifier events, a +/-10%
jitter, and the held weapon's `damage` (2 bare-handed) as HP,
`final = max(1, int(damage x multiplier x jitter))`. An unmodified crowbar hit
takes 4 or 5 HP, a knife 2 or 3, a bat 4 or 5, a pan 1 or 2, an axe 5 or 6, bare hands 1 or 2. `SHOVE` on an NPC is refused.

## Hooks into earlier specs

- **Game clock:** `ATTACK` and `SHOVE` cost 1 minute per swing; `EQUIP` and
  `UNEQUIP` 1 minute.
- **Survival stats:** stress falls by 0.02 per kill, and the endurance drains
  above.
- **Status effects:** the Endurance, Panic and Heavy Load penalties lower crit chance.
  Panic and Stress are subtracted from the split, not multiplied.
- **Clothing:** shoes carry a stomp power.
- **Character creation:** Asthmatic takes effect.
- **Skills:** Maintenance and knockback XP are live, category XP uses the real
  split, and Strength, Fitness and the weapon skills feed damage, crits and
  endurance.
- **Zombies:** the swing is step 0 of the loop; down and staggered zombies skip
  step 6; hits replace the swing noise.

## What the narrator and the player see

- **Facts** name what happened in words, never damage or health: "<name> hits z3
  with the crowbar and it staggers back." "A crushing blow: z3 goes down."
  "<name> stomps on z3's head." "The knife goes in under z3's jaw." "z3 goes
  still." "The crowbar is getting worn." The narrator and the event log read
  each id as "the zombie" ("The zombie goes still.").
- **`[THREATS]`:** a down zombie reads "a zombie, on you, down". A stagger ends with
  its minute, before the player sees the panel, so it has no word; the hit fact
  tells it.
- **`[CONDITION]`:** a hands line, "Holding: crowbar (worn)". The words come from
  the share of full condition:

  | Condition | Word |
  | --- | --- |
  | 0.75 or more | good |
  | 0.4 or more | worn |
  | above 0 | badly worn |
  | 0 | broken |

- **Parser:** `[INVENTORY]` marks the held item "(in hands)" and broken items
  "(broken)". `[THREATS]` shows which zombies are down, so it can propose `ATTACK`
  on one or `SHOVE` on a standing one. `EQUIP` is listed when something is
  carried, `UNEQUIP` when something is held, `SHOVE` when a zombie is in view.
- **Page:** the payload gains `held: {name, condition_word}` (null when the hands
  are empty) and `zombie_kills`. The Inventory screen lists the held item with its
  condition word, and the Character screen shows the kill count. A melee weapon's
  condition in the inventory and equipment lists is a word.

## Saves

Schema version 15 adds each weapon item's `condition`, each zombie's `hits_taken`,
`down_until` and `staggered`, and `player.zombie_kills`. A broken weapon is one
at condition 0.

## Edge cases

- **Two zombies on you, a crowbar.** One swing hits both: the target takes x2 and
  the other x1, and both are staggered, so neither attacks that minute.
- **Four on you, a knife.** The knife hits one, no close kill is possible, and the
  other three attack. With four attackers there is no defence.
- **Exhausted.** A swing is still allowed; its damage is x0.05.
- **The target dies mid-plan.** The next planned `ATTACK` on it is refused and
  costs 0; `ATTACK zombie` picks the nearest remaining one.
- **The weapon breaks mid-plan.** The next `ATTACK` is bare-handed: a shove, or a
  stomp on a down zombie.
- **A knife stuck in the last zombie.** It is on the zone floor; `TAKE` it and
  `EQUIP` holds it again.
- **Asleep.** The first attack on the player wakes them.
- **Determinism.** Every roll uses the simulation's own random source, in the
  order written above, so a seeded test replays exactly.

## Testing

`tests/test_melee.py` covers crit chance, the damage chain, targets, floor
attacks, stomps, shoves, knockdowns, the knife, endurance, wear, XP and noise.
`tests/test_melee_simulation.py` covers `EQUIP`, `UNEQUIP`, `SHOVE`, the loop's
down and staggered zombies, fights through `ATTACK`, NPC damage and fight
interruptions. `tests/test_items.py` pins the weapon catalogue,
`tests/test_context.py` the prompt blocks, `tests/test_engine.py` the payload and
`tests/test_persistence.py` the save fields.
