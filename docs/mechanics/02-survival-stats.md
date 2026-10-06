# Survival Stats

> **Status: Implemented.**

The player has survival stats: hunger, thirst, fatigue, endurance, stress,
panic and the rest. The engine moves them over game time. The narrator and the
parser never set them. Status effects are named bands over the stats; this doc covers
the bands the engine needs (see [Stats](#stats)).

## Layout

| Layer | File | What it holds |
| --- | --- | --- |
| modules | `modules/stats.py` | `CharacterStat` (range and default per stat), `Stats`, `StatusEffect` |
| modules | `modules/units.py` | the three rate conversions |
| data | `data/survival.py` | every rate and threshold, named, with its unit |
| data | `data/status_effects.py` | `STATUS_EFFECT_THRESHOLDS` and the level names |
| managers | `managers/stats/status_effects.py` | `status_effect_level` |
| managers | `managers/stats/drivers.py` | `StatContext`, the drivers |
| managers | `managers/stats/engine.py` | `StatsEngine` |
| managers | `managers/simulation.py` | builds the context, calls the engine, runs `SLEEP` |

`Stats` is a clamped mapping with `get`, `set`, `add`, `remove` and `reset`. It
round-trips through a plain dict. Every write clamps, so no driver can push a
stat out of range.

`StatsEngine.advance(player, minutes, ctx)` runs every registered driver over
the minutes in chunks of at most 10. Short chunks keep the feedback terms
honest: appetite shrinks as hunger rises, and fatigue gain follows endurance.
It returns facts for every status effect that changed level, plus any HP loss.

- Drivers run in registration order. Each reads and writes `Stats` only, with
  the signature `apply(stats, hours, ctx)`.
- Status effect levels are read from the stats when a driver needs them, so a driver
  after the boredom driver sees the new Bored level.
- `register(driver)` adds a driver after construction. Weather and body
  temperature use it.
- After a call, `minutes_advanced` is the time that really passed (less than
  asked if the player died), `health_lost` is the HP the status effects took, and
  `death_cause` is set if they took the last of it.
- The chunk split depends only on the total, so `advance(600)` and ten
  `advance(60)` calls give the same stats.

`StatContext` is a frozen dataclass built for each chunk.

| Field | Value now |
| --- | --- |
| `asleep` | the `SLEEP` span |
| `resting` | the action is `WAIT` |
| `exercising` | the action is `ATTACK` |
| `walking` | the action is `MOVE_TO` |
| `sneaking` | false until zombies land |
| `indoors` | false until weather defines it per zone |
| `talking` | false until `TALK`, `ASK` and `GIVE` land |
| `npcs_present` | any NPC shares the zone |
| `bed_type` | from the zone and the player's spot ([Sleep](#sleep)) |
| `hours_survived` | game minutes since the start, in hours |
| `new_zombies_seen` | 0 until zombies land |
| `weather` | none until weather lands |
| `body` | energy, fluids and fatigue multipliers, all 1 until body temperature lands |
| `skills` | each skill's level; Fitness reads 5 when none is recorded |
| `corpse_count`, `corpse_defence` | 0 until the zombie lifecycle lands |
| `traits` | empty until character creation lands |
| `food_eaten_level` | 0 until eating gives a well-fed timer |

Trait multipliers are all 1 for now. Pain, zombie infection and stress from
sounds are 0 until their specs land. Endurance regeneration is multiplied by a
recovery factor from the player's Fitness level
([skills](08-skills.md#effects-wired-now)).

## Turn flow

For each accepted action:

1. The resolver applies the action.
2. The action's minutes are handed to `StatsEngine.advance`, then the clock
   moves by the minutes that really passed.
3. Status-effect-change facts and any health-loss fact join the `[OUTCOMES]` block,
   before the "About N minutes pass." fact.
4. If the stats killed the player, the game ends the same way combat death
   ends it.

Because stats advance per action, a status effect that changes mid-turn affects the
actions after it. Refused actions cost no time and advance no stats. After
death the clock still moves but the stats stay where they fell.

## LLM authority

- `UPDATE_CONDITION` is still parsed, but the validator refuses every field
  (hunger, thirst, morale, sleep, infection risk): "the engine moves survival
  stats with the clock."
- `PlayerEntity.hunger`, `.thirst` and `.morale` are gone. The player has
  `stats` and `asleep`.
- Only drivers and eating change stats. What eating does is in
  [03 Status Effects and Consumption](03-status-effects-and-consumption.md).

## Stats

| Stat | Range | Default | Driven by |
| --- | --- | --- | --- |
| Hunger | 0–1 | 0 | this doc |
| Thirst | 0–1 | 0 | this doc |
| Fatigue | 0–1 | 0 | this doc |
| Endurance | 0–1 | 1 | this doc |
| Stress | 0–1 | 0 | decay only |
| Panic | 0–100 | 0 | this doc |
| Idleness | 0–1 | 0 | this doc |
| Boredom | 0–100 | 0 | this doc |
| Unhappiness | 0–100 | 0 | this doc |
| Pain | 0–100 | 0 | nothing yet |
| Intoxication | 0–100 | 0 | decay only |
| Food sickness | 0–100 | 0 | corpses, decay |
| Zombie infection | 0–100 | 0 | nothing yet |
| Body temperature | 20–40 | 37 | nothing yet |
| Wetness | 0–100 | 0 | nothing yet |
| Sickness | 0–1 | 0 | nothing |

Only the player has stats.

The status effect thresholds and level names are in [03 Status Effects and Consumption](03-status-effects-and-consumption.md#status-effects).

## Converting rates to game hours

`modules/units.py` holds the three rules. Every rate in `data/survival.py`
ends `_per_hour` and goes through one of them.

| Rule | Function | Factor |
| --- | --- | --- |
| Day-scaled rate | `per_hour_from_day_scaled` | 3600 |
| Frame rate | `per_hour_from_frame` | 10800 |
| Real-time frame rate | `per_hour_from_real_frame` | 6750 |

The factors assume a game day of 90 real minutes. Sandbox multipliers are 1.

## Drivers while awake

Rates are per game hour. `h` is the chunk length in hours.

### Hunger

appetite = 1 − hunger. Every branch is also times `ctx.body.energy`.

| Well-fed level | Exercising | Change |
| --- | --- | --- |
| 0 | no | +0.03456 × appetite × h |
| 0 | yes | +0.02304 × appetite × h |
| above 0 | no | 0 |
| above 0 | yes | +0.06912 × appetite × h |

An idle Orton turns Peckish after about 4.7 hours.

### Thirst

+0.0288 × h, times 1.2 while exercising, times `ctx.body.fluids`.

### Fatigue

+0.1242 × max(0.3, 1 − endurance) × h, divided by 1.5 while resting, times
`ctx.body.fatigue`. A rested Orton turns Drowsy (fatigue above 0.6) after
about 16 hours.

### Stress

Falls by 0.108 × h. Wound and infection stress and stress from sounds join
when those specs land.

### Endurance

| Situation | Change per hour |
| --- | --- |
| exercising (`ATTACK`) | −0.2808 |
| resting (`WAIT`) | +1.674 × (1 − 0.8 × fatigue) × 1.2 |
| standing still (any other action) | +0.3348 × (1 − 0.85 × fatigue) × 1.2 |
| walking, Endurance status effect below level 2 | +0.0837 × (1 − fatigue) × 1.2 |
| walking, Endurance status effect at level 2 or more | −0.0501, times 1.5 when sneaking |

### Idleness

- `WAIT`: +1.8 × h, and +0.6 × h more indoors.
- Combat: reset to 0.
- Any other action: −21.6 × h.

### Boredom

- Outdoors and not resting: −41.58 × h.
- Indoors or resting:
  - resting: +10.8 × idleness × h
  - busy: +1.08 × idleness × h, and −207.9 × h if idleness is below 0.1
  - talking: −415.8 × h
  - NPCs in the zone: −41.58 × h
- Intoxication above 20: −831.6 × h.
- Panic above 5: boredom resets to 0.

### Unhappiness

- Bored level 2 or more: +5.4 × level × h.
- Stress level 2 or more: +2.7 × level × h.

### Panic

- +7 for each zombie newly seen (always 0 until zombies land).
- Falls by (405 + 405 × min(5, months survived)) × h. A month is 30 game days.
  The decay is doubled while asleep.

### Intoxication

Falls by 45.36 × h.

### Food sickness

- With more than 5 corpses nearby: +1.134 × min(corpses − 5, 20) × h, times
  (1 − defence ÷ 100). No decay in that case.
- Otherwise: −16.2 × h.

## Sleep

`SLEEP` sets `player.asleep` for the span. While asleep these replace the awake
drivers for hunger, thirst, fatigue and endurance. Idleness and boredom do not
move. Stress, unhappiness, intoxication and food sickness run as usual.

- Hunger: +0.0036 × appetite × h, or 0 while the well-fed level is above 0.
- Thirst: +0.0036 × h.
- Endurance: +0.2232 × 1.2 × h.
- Fatigue: −(0.3 ÷ 7) × bed × h while fatigue is at or below 0.3, and
  −(0.7 ÷ 5) × bed × h above it.
- Panic decay is doubled.

From fatigue 0.8 in an average bed, fatigue reaches 0 after about 10.6 hours:
3.6 hours down to 0.3, then 7 hours more.

`bed` depends on the bed type.

| `bed_type` | Multiplier |
| --- | --- |
| `good_bed_pillow` | 1.15 |
| `good_bed` | 1.10 |
| `average_bed_pillow` | 1.05 |
| `average_bed` | 1.00 |
| `bad_bed_pillow` | 0.95 |
| `bad_bed` | 0.90 |
| `floor_pillow` | 0.75 |
| `floor` | 0.60 |

Each zone has a `bed_type` (default `floor`) and may map words in the player's
spot to another bed type. The apartment is `floor`, but a spot with "bed" in it
(the bedroom) is `average_bed`.

### Waking

The sleep runs chunk by chunk and ends at the first of these.

| Cause | Fact |
| --- | --- |
| the requested time is up | "Orton sleeps 2 hours." |
| open `SLEEP` at night reaches 09:00 | the time spent |
| open `SLEEP` reaches the 16 hour cap | the time spent |
| fatigue is 0 after at least 1 hour asleep | "Orton wakes fully rested." |
| a zombie interrupts (none can yet) | "A zombie wakes Orton in a panic." Panic rises by a random 30 to 60 from the injected `rng`. |
| Hunger or Thirst reaches level 4 | "Hunger wakes Orton." or "Thirst wakes Orton." |

An open `SLEEP` started at night (22:00 to 05:59) wants to run until 09:00. By
day it wants the 16 hour cap.

`SLEEP` is refused, costing no time, when:

- Panic is at level 1 or more: "Orton is too panicked to sleep."
- Pain is at level 2 or more and fatigue is 0.85 or below: "Orton is in too much
  pain to sleep."

## Health loss from status effects

| Status effect at level 4 | HP per hour |
| --- | --- |
| Hungry (Starving) | −3.564 |
| Thirst (Dying of Thirst) | −17.82 |
| Sick (Fever), when food sickness is above zombie infection | −178.2 |

Losses add up. The loss per chunk is fractional: whole points come off
`hit_points` and the rest is carried in `player.fractional_hp_loss`.

Each span that takes HP gives one fact per cause, without numbers: "Orton is
weakening from hunger.", "... from thirst." or "... from fever."

If hit points reach 0 inside a chunk, the span stops at the end of that chunk.
The fact is "Orton died of starvation.", "Orton died of thirst." or "Orton died
of fever.", followed by the usual death line. The same text becomes the death
cause, and later actions in the turn are refused.

## What the narrator and the player see

- The `[OUTCOMES]` block gets one fact per status effect change: "Orton is now
  Peckish." or "Orton is no longer Peckish." It never holds a stat value.
- The narrator and parser prompts carry a `[CONDITION]` block with the active
  status effects ([03](03-status-effects-and-consumption.md#what-the-narrator-and-the-player-see)).
- `/play` carries `effects: [{type, level, name}]` for status effects above level 0. The
  `vitals` object holds health only. The page shows each status effect as a tag.

## Saves

`SCHEMA_VERSION` is 6 (spec 03 adds the well-fed timer). The player saves `stats` (every stat by name), `asleep`
and `fractional_hp_loss`. The old `hunger`, `thirst` and `morale` fields and
the narrative `conditions` are gone. A save of any other version is discarded.

## Edge cases

- `WAIT` is capped at 24 hours and `SLEEP` at 16, so an action runs at most 144
  chunks.
- Sleeping while Starving or Dying of Thirst is allowed. The player wakes at the
  end of the first chunk, so a sleeper is never killed in one `SLEEP`.
- Death mid-span stops the clock at the chunk where it happened.
- Drivers use no randomness. The only random value is the interruption panic.

## Testing

- `tests/test_stats.py`: ranges, defaults, clamping, dict round-trip, and each
  constant's per-hour value.
- `tests/test_stats_engine.py`: one hand-computed hour (or chunk) per driver,
  Peckish at 4 to 5 hours, Drowsy at 15 to 17 hours, fatigue from 0.8 in bed,
  the three health-loss figures, chunk equivalence, a registered driver, and
  exactly one fact per status effect change.
- `tests/test_time_and_sleep.py`: stats advance per action, the sleep wake causes,
  death by thirst with its cause, and the clock stopping at the death chunk.
- `tests/test_validator.py`: every `UPDATE_CONDITION` field refused, `SLEEP`
  refused at Panic level 1 and at Pain level 2, the open-sleep span.
- `tests/test_persistence.py`: a round trip keeps `stats`, `asleep` and
  `fractional_hp_loss` exactly, and a v4 save is discarded.
