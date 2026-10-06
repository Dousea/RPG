# LLM Contract

> **Status: Implemented.**

The engine decides what happens. The local language model does two jobs: it
reads what the player typed, and it describes what the engine decided. This
document is the one list of what the model may choose, every verb it may
propose, the blocks each call sees, and the rules the narrator follows.

Earlier mechanics each added a verb or a prompt block. Their registries meet
here: a later mechanic lands its verbs by adding rows, not by editing the
parser.

## What we port

| Piece | File |
| --- | --- |
| `Verb`, `VERBS`, the closed label sets, the removed verbs | `modules/action/parser.py` |
| `TalkAction`, `AskAction`, `GiveAction`, `ShoutAction` | `modules/action/types.py` |
| Words for an action that never ran | `modules/action/words.py` |
| `NpcEntity.following`, `World.fired_beats` | `modules/entity/npc.py`, `modules/location.py` |
| Beat conditions and effects | `modules/story.py` |
| `SocialLog` | `modules/social.py` |
| The approach table, `GIVE` deltas, `ASK` odds | `data/social.py` |
| Topics | `data/topics.py` |
| Story beats | `data/story_beats.py` |
| `MAX_PLAN_ACTIONS`, `TALK_TURN_MINUTES`, `NONE_TURN_MINUTES` | `data/time_costs.py` |
| Shout sizes | `data/zombie_lore.py` |
| `TALK`, `GIVE`, `ASK` resolution | `managers/social.py` |
| Reading beat conditions, visible topics | `managers/story.py` |
| Validators and resolvers keyed by verb name, beats, derived statuses | `managers/validator.py`, `managers/simulation.py` |
| `GameManager.move_npc`, `outbreak_day`, `NarrativeState.social_log` | `managers/game.py` |
| Both prompts' blocks | `managers/context.py` |
| The parser prompt built from `VERBS`, the narrator rules, the summarizer note | `adapters/llm.py` |
| The event-log entry written for a turn | `managers/event_log.py` |
| Parse-failure facts, the page payload | `adapters/engine.py` |
| Saving | `adapters/save/codec.py` |
| Hand-run parser quality check | `evals/parser_cases.yaml`, `scripts/eval_parser.py` |

## The rule

Three calls:

| Call | Temperature | Gets | Returns | Decides |
| --- | --- | --- | --- | --- |
| **Parser** | 0.2 | the scene, in the parser blocks below | a JSON plan `{"actions": [...]}`, or `ACTIONS:` lines as the fallback | which verb, which listed target, which listed label |
| **Narrator** | 0.7 | memory, state and this turn's `[OUTCOMES]` | `STORY`, `OPTIONS` | the words |
| **Summarizer** | 0.5 | older event-log entries | one paragraph | the words |

Each call carries a reply cap, `max_tokens`: narrator 800, parser 400, summarizer
300. The model's context is 8192 tokens (`llm.context_tokens`).

**The test for a lever:** could a player get a different result by rewording the
same action? If so, the model is deciding an outcome, and the verb has to change.

The model may choose:

- a verb from the verb list;
- a target from a list the prompt gave it (an item, a zone, an NPC, a zombie id, a
  topic);
- a label from a closed list (a pace, a stance, a `TALK` approach, an `ASK`
  request);
- free text that nothing mechanical reads (goal text, the player's notes on an NPC,
  and all prose).

The model may not choose a number, create an entity, set a flag, move an NPC,
change a relationship, or name an outcome.

## Parser

### Verbs

`modules/action/parser.py` keeps one registry, `VERBS`. Each `Verb` has a name, the
kinds of target it takes (in argument order), a parse function, a one-line gloss and
its fixed cost in minutes (none when the time is spent as the action runs). The
validator and the resolver for each verb live in `managers/validator.py` and
`managers/simulation.py`, in tables keyed by verb name. A test fails when a verb in
`VERBS` lacks either.

The parser's system prompt is built from `VERBS`, so the prompt and the parser can't
drift apart.

| Verb | Arguments | Minutes |
| --- | --- | --- |
| `MOVE_TO` | zone, alias, `in`/`out` or a spot; optional `run` | per hop |
| `STANCE` | `sneak` or `stand` | 0 |
| `WAIT` | duration | as spent |
| `SLEEP` | optional duration | as spent |
| `TAKE` / `DROP` | item | 1 |
| `USE_ITEM` | item (eating and drinking too) | 1, or the food's time |
| `WEAR` / `TAKE_OFF` | clothing item | 1 |
| `EXERCISE` | type, optional minutes | as done |
| `ATTACK` | NPC name, zombie id, or `zombie` | 1 per swing |
| `SHOVE` | zombie id, or `zombie` | 1 per swing |
| `EQUIP` / `UNEQUIP` | item | 1 |
| `BANDAGE` | body part, optional `with` item | 1 |
| `REMOVE_BANDAGE` | body part | 1 |
| `DISINFECT` | body part, optional `with` item | 1 |
| `SHOUT` | none | 0 |
| `TALK` | NPC, approach | 5 per turn |
| `ASK` | NPC, request | 5 per turn |
| `GIVE` | item, NPC | 5 per turn |
| `ADD_GOAL` / `REMOVE_GOAL` | horizon, free text | 0 |
| `ADD_RELATIONSHIP_NOTE` | NPC, free text | 0 |

A verb of a later mechanic is absent from `VERBS` until that mechanic lands. A line
that uses one is a `ParseFailure`.

`TALK`, `ASK` and `GIVE` share one 5-minute cost per turn. Those minutes count as
talking for the survival stats, so they lower boredom.

**Removed verbs.** Each is refused as "not an available action", before validation.

| Verb | Replaced by |
| --- | --- |
| `TIME_ADVANCE` | `WAIT` and `SLEEP` |
| `UPDATE_CONDITION` | the survival stats and status effects |
| `UPDATE_RELATIONSHIP` | `TALK`, `ASK` and `GIVE` |
| `SET_FLAG` / `DISCOVER_FLAG` | story beats and topics |
| `NPC_MOVE` | `ASK ... follow` and story beats |
| `NPC_STATUS` | derived statuses and story beats |
| `STATUS_ADD` / `STATUS_REMOVE` | status effects, `asleep`, `sneaking` |
| `UPDATE_INVENTORY` | `TAKE`, `DROP`, `USE_ITEM`, `GIVE` and `ASK ... give` |

With them go the story vocabulary lists, `narrative.player_status` and the
incapacitated-status check. `player.conditions` stays, written only by item effects.

### `SHOUT`

A shout is a world sound of radius 30 tiles and volume 30, or radius 6 and volume 6
while sneaking. A megaphone gives 90, or 18 while sneaking, once the catalogue has
one. The sound reaches the zombies in the next minute they run. A shout takes no
time of its own: the one-minute floor applies only when the whole turn would cost
no time, so `WAIT 10m` then `SHOUT` costs 10 minutes. A shout that ends a turn that
already spent time is heard in the first minute of the next turn. A shout
isn't talking, so it doesn't lower boredom.

### What the parser sees

The scene and the last turn: no memory, no narrator prose, no relationship bands. In order:

| Block | Contents |
| --- | --- |
| `[CHARACTER]` | name and pronouns only |
| `[LOCATION]` | zone, spot, description |
| `[EXITS]` / `[ZONES]` | the connections; every zone with its aliases |
| `[ITEMS HERE]` | item names |
| `[NPCS HERE]` | each NPC, "(following you)" when they follow, what they hold, and a line per available topic |
| `[THREATS]` | perceived zombie ids with distance words |
| `[INVENTORY]` | carried items |
| `[WORN]` | the worn outfit |
| `[CONDITION]` | status effects by name and level, `sneaking` |
| `[WEATHER]` | the weather in words |
| `[EXERCISES]` | exercise types, and whether a barbell or dumbbell is carried |
| `[AVAILABLE ACTIONS]` | the verbs the scene lists, each with its argument kinds and gloss; `TALK` carries its eight approaches |
| `[LAST TURN]` | the latest event-log entry (the attempt and its facts, zombie ids in words), so "again" and pronouns resolve; omitted with an empty log |
| `[PLAYER INPUT]` | what the player typed |

`[DOORS AND WINDOWS]` and `[CORPSES]` sit before and after `[ITEMS HERE]` once
those mechanics land. The system prompt uses the character's name and pronouns.

### Scene filtering

The parser is shown only the verbs the scene gives a target for. The system prompt holds the fixed rules and the output format and is identical every turn. The filtered list is the `[AVAILABLE ACTIONS]` block, after the scene.

Each verb has a `listed_when` tuple of scene keys. It is listed when any key is present, and always when the tuple is empty. `ContextBuilder` works the keys out from the same state it renders.

| Verb | Listed when | Key present when |
| --- | --- | --- |
| `MOVE_TO`, `STANCE`, `WAIT`, `SLEEP`, `EXERCISE`, `SHOUT`, `ADD_GOAL`, `ADD_RELATIONSHIP_NOTE` | always | n/a |
| `REMOVE_GOAL` | `goals` | the player has a goal |
| `TAKE` | `items_here` | an item lies here |
| `DROP`, `USE_ITEM` | `carried` | the player carries an item |
| `WEAR` | `wearable` | clothing is carried or lies here, so `TAKE` then `WEAR` can be planned |
| `TAKE_OFF` | `worn` | something is worn or in hand |
| `TALK`, `ASK`, `GIVE` | `npcs_here` | someone is here |
| `ATTACK` | `npcs_here`, `threats` | someone is here, or a zombie is perceived |
| `BANDAGE`, `REMOVE_BANDAGE`, `DISINFECT` | `hurt` | a body part is injured or bandaged ([health](12-health-and-infection.md)) |

With nothing present, the block lists the eight always-listed verbs. Filtering decides what the model sees, not what it may say: a verb that isn't listed still parses, and the validator refuses it as usual. `EAT` and `DRINK` parse as `USE_ITEM`. Closed labels inside a listed verb are printed in full.

### Plans

The parser returns a plan, resolved in order. It is a JSON object, `{"actions": [...]}`,
constrained by a schema built for the turn from the same scene the blocks show; an
empty list is `NONE`.

- **One branch per listed verb.** Each branch fixes the verb and names its fields. A
  field is a closed choice wherever the scene gives a closed set: `TAKE` takes an item
  lying here, `DROP`, `USE_ITEM`, `EQUIP` and `GIVE` a carried one, `UNEQUIP` the held
  item, `TAKE_OFF` a worn one, `WEAR` a garment carried or lying here (so a `TAKE` and a
  `WEAR` fit in one plan), `BANDAGE` and `DISINFECT` an injured part that has no bandage
  and optionally a carried bandage or alcohol item, `REMOVE_BANDAGE` a bandaged part,
  `ATTACK` an NPC here, a seen zombie's id or `zombie` (offered only while a zombie is
  seen), `SHOVE` a seen zombie's id, `TALK` an NPC here with the closed
  approach labels, `ASK` an NPC here to follow or stay, and, only when there is one to
  name, for an item an NPC here carries (`give`) or about a topic one of them can
  discuss (`about`); those two requests require the item or the topic. The `ASK` line in
  `[AVAILABLE ACTIONS]` lists the same requests and sends any other question to `TALK`
  `chat`. `WAIT` and `SLEEP` take a duration string the duration
  grammar accepts. `MOVE_TO` takes any destination text and an optional `run`. A verb
  whose closed set is empty has no branch.
- **The same path as the lines.** Each JSON action is turned into the action line the
  grammar accepts and parsed with it, so validation, refusals and facts do not depend
  on the format. A reply that is not JSON, or a shape the schema does not allow, is a
  `ParseFailure`, refused as a fact like a malformed line.
- **The schema lists only the scene's verbs.** The text format still parses a verb
  that is not listed, and a verb the schema leaves out cannot be emitted at all.
- **If the server rejects the request** (an HTTP 4xx, for a server without structured
  output), the parser call is made once more with the text prompt and its `ACTIONS:`
  lines are parsed as before. The narrator and summarizer calls never carry a schema.

- **At most 5 actions** per turn. The rest are refused: "Too much at once; Orton
  does the first five things."
- **A refused action doesn't stop the plan.** The next one is judged on the state as
  it stands.
- **An interrupted action stops the plan.** The actions after it are cancelled with
  one fact: "Orton never gets to: take the knife, drop the bag." A story beat that
  interrupts does the same.
- **`NONE` still costs a minute.** A turn where the parser proposes nothing costs
  1 minute, so the zombies and the stats still run. A turn whose only lines were
  refused costs 0.

## Talking to people

Everything the player says to an NPC becomes one `TALK`, and the parser chooses the
approach. The engine owns what it is worth. The approach is the first label after the
NPC's name; anything after it, such as the line being said, is dropped
(`TALK Emma chat "Hi, I'm new here"` is a `chat`).

### Approaches

| Approach | Parser gloss | Affection | Trust |
| --- | --- | --- | --- |
| `chat` | small talk, jokes, asking how they are, anything else | +2 | 0 |
| `compliment` | praise, thanks, admiration | +2 | 0 |
| `flirt` | romantic interest | +3, or -1 if the NPC isn't romance eligible | 0 |
| `confide` | sharing something personal or vulnerable | +1 | +2 |
| `comfort` | reassurance, sympathy, support | +2 | +1 |
| `argue` | disagreeing, criticising, refusing | -2 | -1 |
| `insult` | mockery, rudeness | -5 | -3 |
| `threaten` | threats, intimidation | -5 | -8 |

The deltas apply to how the NPC regards the player.

- **Repetition.** A positive delta is divided by `n`, the number of times this
  approach has been used on this NPC in the current calendar day, counting this one,
  and rounded toward zero. Three chats in a day give +2, +1 and +0. Negative deltas
  never shrink. Each approach has its own count, so a chat then a compliment are both
  `n = 1`. A `TALK` that is refused doesn't count. The counts reset at 00:00.
- **Hostile NPCs.** When the NPC's disposition is Hostile or Hated, positive deltas
  are halved after the repetition rule, rounded toward zero. The Guarded trust band
  doesn't count.
- **One per NPC per turn.** A second `TALK` to the same NPC in one turn is refused:
  "Orton has already spoken to Emma this turn."

The fact names the reaction from the sign of the affection-plus-trust change: "Emma
responds warmly.", "Emma seems unmoved." or "Emma bristles." A change of disposition
or trust band adds one fact: "Emma now regards Orton as friendly." or "Marcus's
trust in Orton is now solid." Scores never appear in facts or prompts; bands do.

### Giving

`GIVE <item> <npc>` moves a carried item into the NPC's inventory. Door keys are
refused. Food and drink are worth +4 affection and +3 trust, anything else +2 and
+2. Gives to one NPC count as one approach (`give`) whatever the item, with the same
day window, divisor and Hostile rule; both deltas are divided.

### Asking

`ASK <npc> <request>` rolls with the simulation's random source.

| Request | Complies when |
| --- | --- |
| `follow` | the roll is below `clamp(trust / 40, 0, 1)`: never at trust 0 or below, half the time at 20, always from 40. Always refused when the disposition is Hostile or Hated. |
| `stay` | always; the NPC stops following |
| `give <item>` | the NPC holds the item, and the roll is below `clamp((trust - 10) / 40, 0, 1)`; the item moves to the player |
| `about <topic>` | see Topics; no roll |

- **No re-rolls.** A refused `follow` or `give` can't be asked of the same NPC again
  for 60 game minutes: "Emma has already said no."
- **Following.** When the player's `MOVE_TO` changes zone, every following NPC who
  was with them arrives at the same minute. A follower enters the apartment with the
  player; nobody else can. An NPC who is already following complies with `follow`
  and no roll.
- Zombies still ignore NPCs.

### Topics

Things an NPC can tell the player live in `data/topics.py`, not in the model. A topic
has an id, an NPC, a gloss (the line the parser sees), an optional condition it
requires (it isn't listed until it holds), a minimum trust band, the fact the NPC
says, and the flag it reveals.

`ASK Jen about outbreak_news`:

- **At or above the minimum trust band:** `[OUTCOMES]` gets "Jen tells Orton: <fact>".
  The flag it reveals is marked discovered, which completes any `discover:`
  objective, and the topic is marked told.
- **Below it:** "Jen deflects the question."
- **Unknown topic, or one whose condition doesn't hold:** refused: "Jen has nothing
  to say about that."

| Topic | NPC | Requires | Min trust | Fact | Reveals |
| --- | --- | --- | --- | --- | --- |
| `outbreak_news` | Jen | the outbreak has started | Tentative | "The news is calling it the zombie infection. Bites spread it, and the ones who die from it get back up." | `apocalypse_cause` |

## Story beats

`data/story_beats.py` holds beats: an id, a condition, effects, a fact and whether it
interrupts. Each beat fires once, and `World.fired_beats` records the minute.

- **Conditions:** the clock at or past a minute; the player in a zone; a flag
  discovered; the outbreak started; a named beat fired at least N minutes ago; all of
  a list.
- **Effects:** start the outbreak; set a flag; discover a flag; move an NPC; add or
  remove an NPC status. Moving an NPC checks nothing: whoever calls it applies the
  rules about who may go where.
- **When they're checked:** a beat with a clock condition at every minute boundary
  the clock crosses, so a beat due during a long `WAIT` fires at its minute (a span
  is cut short to land on it). Every unfired beat is also checked after each
  resolved action.
- **Interrupting:** a beat that interrupts stops the current action like a zombie
  does, and cancels the rest of the plan. A sleeper wakes: "Orton is startled awake."
- **The fact** goes to `[OUTCOMES]`.

| Beat | When | Effects | Fact | Interrupts |
| --- | --- | --- | --- | --- |
| `outbreak_begins` | day 3, 06:00 (minute 2760) | start the outbreak | "Sirens start up across the city and don't stop." | yes |

The narrator's time block says "before the outbreak" or "outbreak day N" from the
world's outbreak start.

## Derived statuses

A status the engine can compute is never stored by hand. It's recomputed after each
action.

- **`trusts_player`** is on an NPC exactly while their trust band is Solid or
  Unwavering (trust 40 or more).
- When it appears, it completes any `npc_status:` objective, so
  `quest_marcus_trust` completes by earning Solid trust.
- It disappears if trust falls, but quest progress stays one-way.

The descriptive statuses in `data/npcs.py` ("friendly", "curious about new
neighbor") stay as they are. Only story beats change them.

## Narrator

### What the narrator sees

In this order. Memory comes first, so current state and this turn's outcomes win.

| Block | Contents |
| --- | --- |
| `[CHARACTER]` | name, pronouns, occupation, appearance, backstory, skills in words, goals, inventory, equipment, the outfit line, traits |
| `[DEEP MEMORY]` / `[SUMMARY OF PAST EVENTS]` / `[RECENT EVENTS]` | memory |
| `[LAST SCENE]` | the story the player last read, verbatim, with a note that the facts and current blocks win; omitted when there is none |
| `[TIME AND WEATHER]` | day and clock time, time of day, "before the outbreak" or "outbreak day N", the weather in words |
| `[CURRENT LOCATION]` | zone, spot, description, sheltered or not, discovered flags |
| `[ITEMS IN CURRENT LOCATION]` / `[NEARBY LOCATIONS]` | items and exits |
| `[NPCS PRESENT]` | each NPC with disposition and trust bands, status, personality, visible intent, and "Following Orton" |
| `[THREATS]` | perceived zombies |
| `[CONDITION]` | status effects by name and level, asleep, sneaking, conditions an item put on the character |
| `[QUESTS]` | active quests |
| `[OUTCOMES]` | this turn's facts, in order |
| `[CONTINUITY]` | the defensive fallback |
| `[SCENE]` | what the player typed |

`[CHARACTER]` has none of the old stat lines: no level, health, hunger, thirst,
morale, sleep, infection risk, status or conditions. They are in `[CONDITION]` as
status effects.

**Words, not numbers.** No block carries a stat, a score, an HP value, a skill
level, XP, a temperature or a zombie's health, speed or senses. The clock time and
counts of things are the only numbers the narrator gets.

### What the narrator must not do

The system prompt keeps its style section and states these rules:

- Anything marked "Refused" didn't happen. An interrupted action stops where its
  fact says.
- Every zombie in the prose is in `[THREATS]`. Before the outbreak nobody on screen
  is one of the walking dead; rumours and news are fine.
- Every body in the prose is in `[CORPSES]` and is dead until a fact says it rises.
- Every person present is in `[NPCS PRESENT]`. Others can be remembered or mentioned,
  not met.
- The character holds only what the inventory, equipment and outfit lines say.
- NPC reactions follow the reaction fact and the bands.
- An NPC states world facts only from the blocks. A topic's fact is said only when
  `[OUTCOMES]` says it was told.
- Death is final, and `OPTIONS` is `NONE`.

These are prompt rules. What is enforced is that nothing the narrator writes changes
state: `STORY` is shown to the player and `OPTIONS` is only a suggestion. The
narrator writes nothing into memory.

### What the narrator returns

`STORY:` and `OPTIONS:`. A stray `EVENT:` section is dropped, never shown as story. An option is something the player could type, and
clicking it sends it to the parser like typed text, so a suggestion is never a
shortcut past the engine. A reply with no headers at all is all story. A prompt block
the narrator echoes back (`[OUTCOMES]` and the lines under it) is dropped up to the
next header. A header written in brackets (`[OPTIONS]`) counts as the header, and an
option that reads `NONE`, bulleted or not, is no option.

## Memory

- The engine writes each event-log entry from the turn, never from narrator text:
  the game day, clock time and zone as the player acted, what the player tried
  (their input, quoted), then the turn's outcome facts with zombie ids read as "the
  zombie". "Day 3, 06:32 AM, Your Building. Orton tries: "I stab the zombie in the
  head." Orton hits the zombie with the kitchen knife and it staggers back. About 1
  minute passes." The recent buffer holds the same entry, and so does a turn whose
  narrator call failed.
- The narrator's prompt and the summarizer's say that what a character "tries" is
  only an attempt and the sentences after it say what happened.
- `[RECENT EVENTS]` renders oldest to newest, and its note says so.
- `[DEEP MEMORY]` never repeats an entry that is in `[RECENT EVENTS]`: the search
  looks wider than the recall count, drops the recent entries and keeps the first 2.
- The save keeps the last story: the prose shown after a narrated turn, replacing the
  previous one. A turn whose narrator call failed clears it, and a new game has none.
- `[LAST SCENE]` renders it between memory and state, cut to 1600 characters on a line
  or sentence boundary.
- The parser gets the latest event-log entry as `[LAST TURN]`, never any narrator prose;
  memory proper (`[DEEP MEMORY]`, summaries, recent events) goes to the narrator only.
- In the narrator's prompt, memory blocks come before state blocks, and the system
  prompt says the current blocks win.
- The narrator's user prompt has a character budget: `(context tokens - narrator
  reply cap - 200) x characters per token - the system prompt's length`. The ratio is
  the latest reply's characters sent over its reported prompt tokens, 3.5 before any
  reply has one, and unchanged by a reply without usage. Over budget, the prompt
  drops deep-memory entries (last recalled first), then summaries (oldest first),
  then `[LAST SCENE]`, then recent events (oldest first, never the newest), checking
  after each drop. Current-state blocks, `[OUTCOMES]` and the player's input are never
  dropped; an emptied section keeps its header and placeholder. One warning per
  prompt lists what was dropped, and another says when it still does not fit.
- `[WORN]` lists only worn clothing; what is held shows as "(in hands)" in
  `[INVENTORY]` and on the narrator's Equipment line.

## Failures

| Failure | Result |
| --- | --- |
| Parser call errors or times out | No state change, no time; a system error is shown |
| A line is malformed or uses a removed verb | `ParseFailure`, refused as a fact in words: "Refused: Orton tried to talk, but it wasn't clear how." (or, when the verb is unknown or the reply unreadable, "Refused: Orton's attempt isn't something he can do here."); the raw line and the grammar reason go to the log only, never into the fact; the rest of the plan runs |
| The validator refuses an action | Refused as a fact in words, 0 minutes: "Refused: Orton can't bandage the left hand: The left hand isn't hurt." No class name, no verb syntax |
| Narrator call errors after the engine acted | The same event entry is recorded and saved; a system error is shown |
| The summarizer fails | Skipped; retried next turn |

## Checking the models

Tests never call a model; every mechanic is tested from action lines or a JSON plan. The
parser's quality is measured separately. `evals/parser_cases.yaml` holds scenes, an
input and the expected plan ("I creep down to the lobby" gives `STANCE sneak` and
`MOVE_TO building`; "tell Emma she looks great" gives `TALK Emma compliment`; "I
scream for help" gives `SHOUT`). `scripts/eval_parser.py` runs them against the
configured model and prints a pass rate. It is run by hand when the prompt or the
model changes.

## Hooks into earlier specs

- **Game clock:** the time-cost table's talking row is `TALK`/`ASK`/`GIVE`, and a
  `NONE` turn costs 1 minute.
- **Survival stats:** `UPDATE_CONDITION` is gone, morale and infection risk
  included. Talking means the minutes of `TALK`, `ASK` or `GIVE`.
- **Character creation:** the parser and narrator blocks sit in the orders above.
- **Zombies:** `outbreak_begins` starts the outbreak. `SHOUT` is a noise source. An
  interruption cancels the rest of the plan. The narrator may not describe a zombie
  outside `[THREATS]`.

## What the player sees

- **Page:** the payload replaces `apocalypse_stage` with `outbreak_day` (`None`
  before the outbreak) and drops `status_effects`. Each NPC in the People list gains
  `following`. The header chip reads "Before the outbreak" or "Outbreak day N". The
  People list shows "following you" beside a follower. Bands are shown as before;
  scores never are.
- **Options:** unchanged. They are suggestions, always alongside free text.

## Saves

Schema version 14 adds `npc.following`, `world.fired_beats` and
`narrative.social_log`, and drops `narrative.player_status` and
`narrative.apocalypse_stage`. The social log is the day its counts belong to, the
counts keyed `"<npc_id>|<approach or give>"`, the refusals keyed
`"<npc_id>|<request>"` with the minute, and the told topics. The counts clear when
the clock's day differs from the saved one. Schema version 17 adds
`memory.last_story`, the previous turn's story, cut to `LAST_STORY_MAX_LENGTH`
characters on load and emptied when the narrator fails. Older saves are discarded.

## Edge cases

- **Talking to a zombie.** `TALK z3 ...` is refused: "z3 isn't listening." Shouting
  at it is `SHOUT`.
- **Talking to someone absent.** Refused; there are no phone calls.
- **`ASK follow` from a follower** complies with no roll.
- **A topic that needs the outbreak** isn't listed before it. Proposed anyway, it is
  refused as unknown.
- **A beat and an action in the same minute.** The action resolves first, then the
  beat fires.
- **The outbreak beat mid-`SLEEP`.** It interrupts, so the player wakes to the
  sirens. The apartment stays empty of zombies.
- **A plan of `ATTACK` then `TAKE`** where the attack is interrupted: the `TAKE` is
  cancelled.
- **A beat whose minute passed in a turn that spent no time** fires after the next
  action, at that later minute.
- **Repetition across midnight.** The per-day counts reset at 00:00.

## Testing

- `tests/test_action.py`: every verb parses, every removed verb is a `ParseFailure`,
  `TALK` accepts only the eight approaches and `ASK` only the four requests, the
  parser prompt lists exactly the registry, every verb has a validator and a resolver.
- `tests/test_simulation.py`: the five-action cap, an interrupted plan, a `NONE` turn
  and an all-refused turn, `SHOUT` at 30 and 6 tiles.
- `tests/test_social.py`: each approach's deltas, repetition and reset, the Hostile
  halving, band-change facts, `ASK` odds and lockout, followers, `GIVE`.
- `tests/test_topics.py`: deflecting, telling, the quest through the topic, a topic
  hidden before the outbreak.
- `tests/test_story_beats.py`: the outbreak beat at minute 2760 in the middle of a
  `WAIT` or `SLEEP`, each condition and effect, `trusts_player`.
- `tests/test_context.py`: both prompts' blocks in order, no numbers in the narrator's
  blocks, `[CHARACTER]` without the old lines.
- `tests/test_last_scene.py`: the stored story, `[LAST SCENE]`, `[LAST TURN]`, the save round trip.
- `tests/test_engine.py`: the event-log entry, its parity on a narrator failure, deep memory without repeats, refusal wording; the payload.
- `tests/test_persistence.py`: following, the social log, told topics and fired beats
  round-trip.
- `tests/test_eval_cases.py`: the hand-run cases still parse.
