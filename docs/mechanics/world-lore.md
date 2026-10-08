# World Lore

> **Status: Implemented.** The lorebook file and its loader, the `[WORLD]`
> block, the system entries, the stages, the secrets, the topics, the binder,
> sticky entries and similarity retrieval.

The narrator knows the tone of the game and, without this, nothing about its
world: the city's name, what the news says, what the player has found out, or
that the world gets worse each day. Lore gives it that inside a fixed budget,
and never tells it what the player hasn't learned.

The story itself, with its secrets, is written as prose in
[`docs/lore/`](../lore/README.md). That is the source: each lorebook entry
condenses a paragraph there, and a story change goes there first.

## What we build

| Piece | File |
| --- | --- |
| The entry, its `Position` and the JSON parsers | `modules/story/lore.py` |
| The lorebook's path, caps and limits | `data/story/lore.py` |
| The entries | `data/story/lorebook.json` |
| Loading and validation, `Lorebook`, `LorebookError` | `managers/story/lorebook.py` |
| `select_lore`, `drop_order`, `world_lines`, `system_text` | `managers/story/lore.py` |
| The `ItemHeld` condition | `modules/story/beats.py`, `managers/story/beats.py` |
| The stage beats and `trial_files` | `data/story/beats.py` |
| The topics | `data/story/topics.py` |
| The binder and its cabinet | `data/items.py`, `data/loot/containers.py` |
| `[WORLD]` in the narrator prompt | `managers/context.py` |
| The system entries and the `[WORLD]` rule in the system prompt | `adapters/llm.py` |
| Selecting after the turn resolves, scoring the input | `adapters/engine.py` |
| Similarity scores for the entries | `adapters/lore_index.py` |
| Embedding a text, the cached query vector | `adapters/memory.py` |

## The lorebook

Every piece of lore lives in one hand-written file, `data/story/lorebook.json`:
`{"entries": [...]}`. Its shape follows the lorebooks of roleplay front ends
where that fits, and adds our own fields for when the player could know an
entry, what replaces it, and which line is the stage line.

| Field | Default | Meaning |
| --- | --- | --- |
| `id` | required | Unique name; `replaced_by` and the tests refer to it. |
| `content` | required | What the narrator reads: one or two sentences, no numbers. |
| `comment` | `""` | A note for the editor; the engine never reads it. |
| `keys` | `[]` | What makes a keyed entry show: a zone id (`zone_...`), an NPC id (`npc_...`) or a word or phrase in the player's input. |
| `constant` | `false` | `true`: no key needed; shown whenever the entry is known. |
| `position` | required | `system` or `world`. |
| `order` | `0` | Lower first, and under the cap lower is kept longest. Ties by `id`. |
| `when` | none | A condition: the entry is known to the player while it holds. None means always. |
| `replaced_by` | none | Hidden once that entry's `when` holds. |
| `stage` | `false` | This is a stage line. |
| `sticky` | none | 1 to 10 turns a keyed entry stays after its trigger. See [Sticky](#sticky). |
| `semantic` | `true` | A keyed entry may also be chosen by similarity; `false` opts out. See [Similarity](#similarity). |

### Position and the prompt cache

The server reuses the already-processed start of a prompt up to the first
character that differs, and the system prompt comes first, so any change in it
costs the cache of everything after it. So:

- **`system`** entries never change during a game or between games: they are
  `constant`, with no `when`, keys, `sticky`, `replaced_by` or `stage`. They
  are joined into one paragraph by single spaces, in `order`, and sit in the
  narrator's system prompt after its style rules and before "The blocks run
  from memory to the present".
- **`world`** entries depend on the state of the game and are chosen each turn
  for the `[WORLD]` block.

### The canon

Seven `system` entries state what is true from the first minute to the last:
the city (Calder, on the Sallow River), the neighbourhood, its shops, the
hospital across the river, that no rescue is coming, that places in `[WORLD]`
that are not in `[NEARBY LOCATIONS]` can be heard of and never reached, and
that nobody knows why the dead rise unless `[WORLD]` says so. The truth behind
the outbreak is never canon.

### Conditions in JSON

`when` is one object holding one condition, turned into the conditions beats
already use by `parse_condition`. Anything else is an error.

| JSON | Holds when |
| --- | --- |
| `{"clock": 4260}` | the game clock is at or past that minute |
| `{"zone": "zone_clinic"}` | the player is in that zone |
| `{"flag": "cordon"}` | the player has discovered that flag |
| `{"outbreak": true}` | the dead have started walking |
| `{"beat": "cordon"}` or `{"beat": "cordon", "minutes": 30}` | that beat fired at least that many minutes ago |
| `{"item": "item_study_binder"}` | the player carries that item |
| `{"all": [...]}` | every listed condition holds (at least one; nests) |

### Loading and validation

`managers/story/lorebook.py` reads and checks the file; a bad file raises
`LorebookError` naming the entry, and `adapters/llm.py` loads it at import, so
a bad file stops the server at startup. It rejects:

- a file that isn't `{"entries": [...]}`, an unknown field, a missing `id`,
  `content` or `position`, a wrong type, a duplicate `id`;
- a `system` entry that isn't `constant`, or that has a `when`, keys, `sticky`,
  `replaced_by` or `stage`;
- `semantic` on an entry that isn't keyed;
- a `world` entry that is constant with keys, or keyed with none; a `stage`
  entry that isn't constant; a `sticky` on anything but a keyed entry or
  outside 1 to 10;
- an unknown flag, beat, item, zone or NPC id in a condition or key, or a
  blank key. The known flags are those a beat or a topic discovers;
- a `replaced_by` that names no entry, itself, or makes a cycle;
- a `content` over 300 characters, system `content` over 1200 in total, or a
  digit in `content` that touches no letter or hyphen ("VX-7" is a name, "day 3"
  is not). Keys may hold digits.

Validation is a function over a list of entries, so entries made some other way
can be checked the same way.

## The `[WORLD]` block

`[WORLD]` sits in `[CURRENT LOCATION]`, where the raw flags line used to be:
raw flag names mean nothing to the narrator, and a lore line says the same
thing in words. One line per shown entry, stage line first. The parser never
sees it. The system prompt gets one paragraph for it: it is background, to be
mentioned when it fits and never recited, and nothing beyond it is known about
why the dead rise.

### Known, not just true

`when` is when the player could know the entry, not when it became true. A
secret takes a `flag` condition, so the narrator never holds it before the
player does. A small model repeats what it's shown and an NPC would blurt out
a secret the prompt holds, so this is the rule that matters most.

### Selection and the cap

`select_lore` runs once a turn, after the plan has resolved, so beats fired
this turn, a new zone and flags discovered this turn are all in the state it
reads. It changes nothing. For each `world` entry:

1. Keep it if its `when` holds.
2. Drop it if the entry named by its `replaced_by` has its `when` holding (the
   replacer's keys are ignored, so a replaced entry stays hidden on turns when
   the replacer's keys don't match).
3. Keep a `constant` entry; keep a keyed one when a key matches: a zone key
   against the player's zone, an NPC key against the NPCs in that zone, any
   other key as a word or phrase in the player's input (whole words, case
   ignored: "ship" matches "the ship" and not "relationship"), or when it is
   sticky-active ([Sticky](#sticky)): no key matches now but it has turns left.
4. From the entries steps 1 to 3 left out, take the keyed ones that allow it
   (`semantic` not `false`) whose similarity score is at least 0.35, best first,
   ties by `id`, up to 2 ([Similarity](#similarity)).

Each hit is `(entry, reason, score, shown)`, and each is logged at debug with
its id, reason and score. The reasons are `constant`, `key`, `sticky` and
`semantic`.

**The cap.** While the shown lines total over 1800 characters, the next hit in
`drop_order` is marked not shown; the stage entry never is. `drop_order` is the
one drop rule: similarity hits first, worst score first, then the highest
`order`, ties by `entry_id` descending (the last line of `[WORLD]` first).
A similarity hit is always dropped before a key, constant or sticky one.

**The prompt budget.** When the narrator prompt is over its budget, the drops
go: deep memories, then lore lines in `drop_order` (on a copy; the turn's hits
are untouched), then summaries, the last scene and older events. The stage
line is current state and never goes. The warning counts "lore lines".

### Sticky

A keyed `world` entry may set `sticky` (1 to 10 turns). A key match is brief:
the player says "ship" once, and the next turn the narrator would have forgotten
what the city thinks of the ship. Sticky keeps the entry on for a few more
turns.

- **State.** `lore_sticky`, entry id to turns left, on the narrative state
  beside `discovered_flags`. An id is in it only while its turns left are above
  0. It is saved with the game.
- **Counting.** Once per turn, in `_run`, after the last narrator call (the
  reply, a retry and the options follow-up all share one `hits` list),
  `record_turn(manager, hits)` runs with the turn's hits from before the cap,
  `shown` or not. It sets the turns left of every `key` or `semantic` hit on an
  entry with a `sticky` to that `sticky`, and takes 1 off every other id in the
  state, removing it at 0. A turn that was refused or only narrated still
  counts. A turn with no narrator call doesn't, and neither does a turn whose
  first narrator call raised `LLMError`: the player got no prose, so
  `lore_sticky` stays as it was. A failed retry or options call keeps the first
  story, so that turn still counts. Building the prompt never changes the
  state, so the budget's drop loop can rebuild `[WORLD]` any number of times.
- **Shown.** A keyed entry shows when a key matches or its turns left are above
  0, so a `sticky` of 3 shows it on the trigger turn and the three turns after
  it. A new trigger inside the stay resets the count.
- **`replaced_by` and `when`.** An entry that is replaced, or whose `when` is
  false, is hidden whatever its turns left, and `record_turn` removes its
  state. So `ship_story` stops the moment `trial_truth` is found, even
  mid-stay. Sticky never lifts a secret's lock.
- **The cap.** A sticky entry competes under the cap like any other, by its
  `order`. If the cap drops it, its turns still count down: it was triggered.
- **On load.** An id in a saved `lore_sticky` that is no longer an entry is
  dropped with a warning.

### Stages

Five beats move the world on, each `ClockAtOrPast`, setting and discovering its
flag, and not interrupting. Its fact reaches `[OUTCOMES]` the turn it fires.
Minutes count from the start (day 1 at 08:00).

| Beat | Minute | When | Flag | Fact |
| --- | --- | --- | --- | --- |
| `evacuation_announced` | 4260 | day 4, 07:00 | `evacuation` | A radio somewhere nearby breaks into an announcement about an evacuation point. |
| `cordon` | 7020 | day 6, 05:00 | `cordon` | Low helicopters pass over the river, and the distant traffic noise stops all at once. |
| `broadcast_loop` | 11760 | day 9, 12:00 | `broadcast_loop` | The radio voice stops mid-sentence; a recording takes over. |
| `power_out` | 19380 | day 14, 19:00 | `power_out` | The lights die all at once, and the hum of the city goes with them. |
| `water_out` | 28920 | day 21, 10:00 | `water_out` | The pipes knock and gurgle; the taps give a last spit of air. |

Exactly one stage line shows at every minute: the news line from the start, the
broadcast line once the outbreak begins (day 3, 06:00), then the evacuation,
cordon and loop lines, each replacing the one before. `power_out` and `water_out`
are additive entries, not stages, so the radio line stays. Nothing in the
simulation reads those two flags yet; the player only hears of them. The
evacuation point, the bridges and the hospital are off the map: the player can
hear of them and can't go there ("the hospital" and "downtown" are not zone
aliases for that reason).

## The truth

The news blames a container ship held at the port; that is wrong, and it is
never canon. What happened, and how the player can find it out, is in
[the truth](../lore/the-truth.md). The engine reveals it in pieces, each a
flag.

| Flag | Found by | Entry |
| --- | --- | --- |
| `apocalypse_cause` | topic `outbreak_news` (Jen) | the "Ashby fever": bites spread it and the dead get back up |
| `clinic_odd` | topic `clinic_regulars` (Jen) | the paid study's volunteers came in on payday, arms bandaged |
| `trial_rumour` | topic `emma_brother` (Emma) | Emma's brother Danny took the paid study and stopped answering |
| `trial_truth` | beat `trial_files`: taking the study binder | the binder: the drug, the company, the first fevers |
| `roof_tank` | topic `roof_tank` (Marcus) | the roof tank holds water after the mains go |

`ship_story` (shown once `apocalypse_cause` is discovered) is replaced by
`ship_story_wrong` once `trial_truth` is. Lore says "Ashby fever", never the
engine's own name for the condition.

### Topics

A topic has a gloss for the parser, a fact for `[OUTCOMES]` when told, a minimum
trust and one flag it discovers; the shape is in [llm-contract](llm-contract.md#topics).
There are eight, listed with their facts in `data/story/topics.py`:

| Topic | NPC | Requires | Min trust | Discovers |
| --- | --- | --- | --- | --- |
| `outbreak_news` | Jen | the outbreak | Tentative | `apocalypse_cause` |
| `clinic_regulars` | Jen | none | Tentative | `clinic_odd` |
| `jen_mother` | Jen | the outbreak | Tentative | `hospital_texts` |
| `emma_brother` | Emma | the outbreak | Solid | `trial_rumour` |
| `emma_flyers` | Emma | `trial_rumour` discovered | Solid | `study_flyers` |
| `roof_tank` | Marcus | `cordon` discovered | Solid | `roof_tank` |
| `marcus_port` | Marcus | `apocalypse_cause` discovered | Tentative | `ship_doubt` |
| `marcus_tenants` | Marcus | none | Tentative | `novaks_left` |

### The binder

`item_study_binder` ("Study Binder", paper, 0.3 kg) is the only thing in the
Clinic office's filing cabinet (`clinic_filing_cabinet`, a fixed container, so
it is there every game and never rolled from a table). Its description names
nothing secret. Taking it, from the cabinet or from anywhere, fires the beat
`trial_files`, which discovers `trial_truth` and says the binder is a study
log. The beat's condition `ItemHeld` holds while any item the player has in the
pack, a bag, the hands or worn has that id, so a save that already holds the
binder satisfies it too. It fires once; dropping the binder later undoes
nothing.

`quest_where_it_started` ("Find Where It Started") completes through
`discover:trial_truth`. Its title and label name nothing the player doesn't
know.

### The wider lorebook

Around those pieces the file holds: the people behind the secret (what Jen's
mother saw at the hospital, the ship's crew, the flyers, the Novaks, and what
the binder adds for a player who has the other piece); the public places and
people (the shops and why they are shut, the doctor, the company); and the city
over time, as chains where each link is `replaced_by` the next, so one line per
topic shows: the river, the bridges (a link shown only once a beat has fired
long enough ago), the army, helicopters, the hospital, the stadium, the park,
the subway, the mayor, the police, the radio, TV, phones, and single lines.
Nothing says what happened at the stadium. All of it is in the file, which is
the source of the wording.

## Saves

The lorebook is data and is not saved. What it reads (`discovered_flags`,
`fired_beats`, the clock, the zone, where the NPCs are) is saved already. The
clinic's filing cabinet is part of the saved rooms. The one field this adds is
`lore_sticky`, saved with the narrative state and read back as `{}` when absent;
an id that is no longer an entry is dropped with a warning. Each addition
bumped the schema version; older saves are discarded.

## What the narrator and the player see

The narrator sees the `system` entries in its system prompt and `[WORLD]` in
`[CURRENT LOCATION]`. Its existing rule about people still holds: an NPC states
world facts only from the blocks, and a topic's fact only when `[OUTCOMES]`
says it was told. The player sees only what the narrator writes from it, the
stage facts in the story, and the quest. No lore line is shown raw.

## Similarity

Keys miss the player who asks "who made the sickness" and never says "study".
After the keys, up to 2 keyed `world` entries are added because their `content`
is close in meaning to the turn's input: the cosine similarity of the two
embeddings is at least 0.35 (a first guess, tuned in play).

- **Candidates.** Keyed `world` entries without `"semantic": false`; never a
  stage, constant or `system` entry. All of them are embedded, locked or not,
  because the lorebook is static. The knowledge rule runs after: an entry whose
  `when` is false, or that is replaced, is never shown whatever its score.
- **Rank.** A similarity hit never displaces a key, constant or sticky one:
  under the cap it is dropped first, lowest score first. A similarity hit with
  a `sticky` starts its stay like a key hit does.
- **One embedding per turn.** `LoreIndex` embeds the candidates' `content` once,
  on the first turn that asks, with the model deep memory already uses. The
  engine scores the input right after the deep-memory search, and
  `SemanticMemory.encode_query` keeps the last text's vector, so the input is
  embedded once for both. The scores are plain numbers handed to `select_lore`,
  so the selection runs with no embedder.
- **If the model fails** to load or encode, one warning is logged and every
  later turn scores nothing; the keys carry on.

## Testing

- `tests/story/test_lorebook.py`: the file, the conditions, each rejected case.
- `tests/story/test_lore.py`: public, replaced and locked entries; zone, NPC
  and word keys; the stage line at every minute; the cap and `drop_order`;
  similarity hits from scores passed in; no number in any entry.
- `tests/test_lore_index.py`: the lazy single embedding, the candidates, a
  failing model, one encoding of the input per turn. `tests/test_memory.py`:
  `encode` and `encode_query`.
- `tests/story/test_story_beats.py`, `tests/story/test_topics.py`,
  `tests/story/test_quests.py`: the stages, the binder, the eight topics, the
  quest.
- `tests/test_context.py`: `[WORLD]` and the drop order in the budget.
- `tests/test_llm.py`: the canon in the system prompt.
- `tests/test_engine.py`: `[WORLD]` after the turn resolves; an entry chosen by
  similarity with no key word; the same hits in the
  retry and options prompts; the stays counted once per turn.
- `tests/test_persistence.py`: the schema version, the cabinet, `lore_sticky`.
