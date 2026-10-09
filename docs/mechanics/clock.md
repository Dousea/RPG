# Game Clock and Action Time

> **Status: Implemented.**

The game runs on a minute clock. Every action is made of phases, each costing a
stated number of in-game minutes, and the clock moves by exactly that much. Only
a few actions have a total that depends on what happens: hitting a barrier until
it gives, sleep until waking, and exercise until exhausted. The player-facing
clock is all this covers. NPC and world scheduling are not built; see
[architecture the time-and-scheduling doc](../design/time-and-scheduling.md).

## The clock

`NarrativeState.minutes` counts in-game minutes since the game started. It is
the only clock. The game starts on day 1 at 08:00, so `minutes = 0` is 08:00 on
day 1.

Everything else is derived and never stored.

| Derived value | Rule |
| --- | --- |
| `day` | `1 + (480 + minutes) // 1440` |
| `hour`, `minute` | `(480 + minutes) % 1440`, split into hours and minutes |
| `time_of_day` | morning 06:00–11:59, afternoon 12:00–17:59, evening 18:00–21:59, night 22:00–05:59 |
| `World.time` | `hh:mm AM/PM`, to the minute (`08:00 AM`, `12:05 AM`) |
| `World.date` | the start date plus `day - 1` days, as `YYYY-MM-DD` |

`day` and `time_of_day` are read-only properties. `World.time` and `World.date`
are a rendering of the same instant: `GameManager.advance_clock` moves the
clock and re-renders them, and nothing else writes them.

| Constant | Value | Unit |
| --- | --- | --- |
| `WORLD_START_MINUTE_OF_DAY` | 480 (08:00) | minutes after midnight |
| `MINUTES_PER_DAY` | 1440 | minutes |
| `TIME_OF_DAY_BANDS` | morning 06:00, afternoon 12:00, evening 18:00, night 22:00 | band starts |

They live in `data/world/clock.py`, with the arithmetic over them.

## Actions

`TIME_ADVANCE` is gone. The parser refuses it as not an available action. Two
verbs replace it.

- `WAIT <duration>` passes time. It is capped at 24 hours per action.
- `SLEEP [duration]` sleeps for at most the given duration, or with no duration
  until woken. It is capped at 16 hours per action. What wakes the player is in
  [survival stats](survival-stats.md#waking).

A duration takes one of these forms. Case and spaces between parts do not
matter.

| Form | Example | Meaning |
| --- | --- | --- |
| minutes | `10m` | 10 minutes |
| hours | `2h` | 120 minutes |
| both | `1h30m` | 90 minutes |
| spelled out | `18 hours`, `1 hour 30 minutes`, `45 mins` | the same, with `h`/`hr`/`hrs`/`hour`/`hours` and `m`/`min`/`mins`/`minute`/`minutes` |
| time of day | `until night` | the next 22:00 |
| time word | `until dawn` | the next 06:00 (`dawn` and `sunrise`), 12:00 (`noon`, `midday`), 18:00 (`dusk`, `sunset`) or 00:00 (`midnight`) |
| clock time | `until 14:30` | the next 14:30 |
| bare time | `morning`, `dusk`, `07:00`, `7:05` | the same as `until` it; the model sometimes leaves the `until` out |

A malformed duration (`soon`, `0m`, `5`, `1h30`, `until 25:00`, a missing
duration on `WAIT`) is a `ParseFailure`, never a zero-minute wait. A time of
day that is not a band name or a time word is refused by the validator, in
words that name what the player asked and what works; no time passes.

| Constant | Value | Unit |
| --- | --- | --- |
| `WAIT_CAP_MIN` | 1440 | minutes per action |
| `SLEEP_CAP_MIN` | 960 | minutes per action |

## Time costs

`data/time_costs.py` holds one row per action type. A row is a fixed number of
minutes or a function of the resolved action. A function receives the action and
the validator's resolved data and returns whole minutes. An action's own phase
is charged its row; getting there is costed apart.

| Action | Minutes |
| --- | --- |
| `ATTACK`, `SHOVE` | 1 per swing |
| `EQUIP`, `UNEQUIP` | 1 |
| `TAKE`, `DROP` | 1 |
| `USE_ITEM` on food or drink | the item's `eat_minutes` (default 5) |
| `USE_ITEM` on anything else | 1 |
| `OPEN`, `CLOSE`, `LOCK`, `UNLOCK` | 0 |
| `BARRICADE`, `UNBARRICADE` | 1 |
| `ATTACK` on a door, window or plank | 1 per swing, up to the count asked (see [doors](doors.md#breaking-through)) |
| walking to a door or window the player isn't at | 1, before the action |
| `MOVE_TO` another zone | the walking minutes of each connection crossed (below), +1 through a window |
| `MOVE_TO` stopped at a locked door | the same for each hop walked, at least 1 |
| `MOVE_TO` within a zone to a named spot, or a bare direction | 1 |
| `MOVE_TO` with no destination, or to the spot the player is already at | 0 |
| `WAIT`, `SLEEP` | the time actually spent |
| `EXERCISE` | the minutes chosen (10 to 60 in steps of 10, default 10), or the minutes run when it stops early |
| `UNSUPPORTED`, goals, notes, flags, relationships, NPC verbs, condition and status edits | 0 |

Further rules.

- A refused action costs 0 minutes.
- A turn where the parser proposes nothing costs 1 minute.
- Time passes phase by phase: getting there (the walk to a barrier, the
  approach to a body or zombie, the hops of a walk) and then the act itself. An
  interruption stops the action between phases, so the clock and `World.time`
  are current for the next action in the plan.
- The action-time multiplier (pain, mood, cold hands) only scales the fixed costs
  of the timed verbs (`TAKE`, `DROP`, `USE_ITEM` and eating, `WEAR`, `TAKE_OFF`,
  `EQUIP`, `UNEQUIP`, `PUT`, `BARRICADE`, `UNBARRICADE`, `BANDAGE`,
  `REMOVE_BANDAGE` and `DISINFECT`), and only the act's own phase, never the
  getting there. Walking, `ATTACK`, `WAIT` and `SLEEP` never take it; see
  [health](health.md#what-pain-does).
- Every spent minute is also handed to the survival stat engine
  ([survival stats](survival-stats.md#turn-flow)). If the player dies part
  way through, only the minutes up to that point pass.
- Each connection between zones has its own walking minutes, the same both ways
  (`WALK_MINUTES_BY_CONNECTION`): home to building 1, building to a flat 1,
  building to street 2, street to bodega 1, street to neighborhood 5, and
  neighborhood to each shop 10. Running takes half of them and sneaking double,
  rounded up and never under 1 minute; see [Zombies](zombies.md#pace).

Other rows named in `data/time_costs.py` (`SWING_MIN`, `QUICK_ACTION_MIN`,
`WALK_TO_BARRIER_MIN`, `WINDOW_CLIMB_MIN`, `WEAR_MINUTES`, `TAKE_OFF_MINUTES`,
`TALK_TURN_MINUTES`, `NONE_TURN_MINUTES`) are constants; each verb joins the table when its
mechanic lands.

The turn's total becomes the last fact in the `[OUTCOMES]` block, so the
narrator can pace its prose: "About 40 minutes pass." A single minute reads
"About 1 minute passes.", and an hour or more reads in hours and minutes ("About 2
hours 10 minutes pass."). The fact is absent when the turn took no time, and when
the turn's wait and sleep facts already state all of its time (a turn that only
waits). Other facts the clock adds:

- "Orton waits 3 hours." and "Orton sleeps 8 hours." for the time spent.
- "Orton waits 24 hours, the most he can at once." when a wait is clamped, and
  the same with "sleeps 16 hours" for sleep.
- "Orton waits 27 minutes, then is interrupted." when a story beat, a zombie or
  a worsening wound cuts a wait short. The time is what actually passed.

## Saves

`SCHEMA_VERSION` is 5 (see [survival stats](survival-stats.md#saves) for the other fields).

- The save holds `narrative.minutes`.
- `narrative.day` and `narrative.time_of_day` are not saved.
- `World.time` and `World.date` are written for readability, but a load
  recomputes them from `minutes`.

There is no migration. Any save whose version is not 5 is discarded and a new
game starts.

## Edge cases

- `WAIT until morning` while already in the morning waits until 06:00 tomorrow,
  never zero minutes.
- `WAIT until <time>` for a time that has already passed today waits until that
  time tomorrow. The same time as now is a full day, 24 hours.
- Durations over the cap are clamped, and the fact says so.
- `WAIT until night` from 08:00 lands on 22:00 the same day. `WAIT until morning`
  at 07:00 lands on 06:00 the next day.

## Testing

- `tests/test_game_manager.py`: every band boundary, the midnight roll, and
  `World.time` / `World.date`.
- `tests/test_action.py` and `tests/test_validator.py`: every duration form,
  malformed durations, the caps, `until` landing times, and `TIME_ADVANCE` as a
  refused verb.
- `tests/test_time_and_sleep.py`: each table cost, refused actions, the `NONE` turn,
  the summed-minutes fact and the edge cases.
- `tests/test_persistence.py`: a round trip keeps `minutes`, and a v3 or v4 save
  is discarded.
