# Local LLM RPG

A text-based RPG powered by a local Large Language Model (LLM), with a typed
game model, persistent state and semantic memory retrieval. The game is set in a
slow-burn zombie apocalypse; the LLM acts as game master while the Python model
owns the rules.

## Architecture

The codebase is layered. Each layer only depends on the ones above it:

```
modules/     Pure game model -- entities, items, events, effects, modifiers.
             No I/O, no framework, no LLM.
data/        Static content -- the item catalog, the map, NPC roster,
             trait and perk definitions.
managers/    Game logic -- GameManager (state + action application + prompt
             assembly) and RelationshipManager (affinity, trust, reputation).
adapters/    Everything that touches the outside world.
app.py       HTTP only.
```

`modules/` and `managers/` know nothing about Flask, HTTP, JSON files or FAISS.
Every such dependency lives in `adapters/`:

| Module | Responsibility |
| --- | --- |
| `adapters/llm.py` | LM Studio chat completions, the game-master system prompt, response parsing |
| `adapters/memory.py` | FAISS semantic search over the full event log |
| `adapters/persistence.py` | Save/load a `GameManager` to `gamedata/engine_state.json` |
| `adapters/engine.py` | `GameEngine` -- orchestrates one turn end to end |

### A turn

```
POST /play
    |
    v
GameEngine.play()                        [adapters/engine.py]
    |
    +-- SemanticMemory.search()          recall relevant past events (FAISS)
    +-- GameManager.build_prompt()       assemble the full context
    +-- llm.query_game_master()          ask LM Studio what happens
    +-- llm.parse_response()             split into STORY / EVENT / ACTIONS
    +-- GameManager.apply_action() * N   apply each state change, keep refusals
    +-- GameManager.record_event()       push to short-term + full log
    +-- SemanticMemory.rebuild()         reindex
    +-- llm.query_summary()              fold old events into a summary
    +-- persistence.save()               write engine_state.json
    |
    v
JSON payload -> frontend
```

Turns are serialized behind a lock in `GameEngine`, because Flask's dev server
is threaded and two overlapping requests would otherwise interleave mutations of
the same `GameManager` and race on the save file.

### Memory

Three tiers, all assembled into the prompt:

- **Recent events** -- the last 5, verbatim, as immediate context.
- **Deep memory** -- the full event log, FAISS-indexed with `all-MiniLM-L6-v2`
  (384-dim, `IndexFlatIP` over L2-normalized vectors, i.e. cosine similarity).
  The top 2 matches for the player's input are recalled each turn.
- **Summaries** -- once 10 unsummarized events accumulate, the LLM condenses
  them into a narrative paragraph so long-term arcs survive without the prompt
  growing without bound.

### State

All dynamic state lives in one file, `gamedata/engine_state.json`, written
atomically (temp file + replace) after every turn.

Only *dynamic* state is saved. Static definitions -- item stats, location names
and connections, trait and perk effects -- stay in `data/` and are looked up by
id on load, so content can be rebalanced without invalidating saves. A save
whose `version` does not match `SCHEMA_VERSION` is discarded rather than loaded
half-understood, and unknown ids (a deleted item, a renamed location) are
dropped with a log line instead of crashing the load.

Persisted: player (position, condition, inventory, equipment, traits, perks),
NPCs (position, status, notes, condition), relationships (affinity, trust,
reputation), narrative state (day, time of day, goals, flags, apocalypse stage,
pending corrections) and all three memory tiers. The world clock (`World.time`,
`World.date`) is written too, but it is derived from the narrative day and time
of day and recomputed on load.

> The older per-file `gamedata/*.json` (`character.json`, `world.json`,
> `npcs.json`, ...) belonged to the previous engine and are no longer read or
> written. They are left in place so nothing is lost; delete them when you are
> confident you do not want the old save.

## Actions

The LLM returns state changes as one action per line. Every verb below maps to a
handler in `GameManager`. An unparseable or impossible action is logged and
skipped -- the narrative still stands, the state change just does not happen.
Because the prose is written before the deltas are applied, refusals are also
carried into the next prompt as a `[CONTINUITY]` section, so the story is told
what did not happen and can write around it one turn later.

```
TAKE <item>                          DROP <item>
MOVE_TO <location|direction>         TIME_ADVANCE morning|afternoon|evening|night
STATUS_ADD <status>                  STATUS_REMOVE <status>
UPDATE_CONDITION <field> <value>     SET_FLAG <flag> true|false
ADD_GOAL short_term|long_term <t>    REMOVE_GOAL short_term|long_term <t>
UPDATE_RELATIONSHIP <npc> affection|trust <+/-N>
ADD_RELATIONSHIP_NOTE <npc> <text>
UPDATE_INVENTORY <item> ADD|REMOVE|UPDATE_CONDITION|UPDATE_QUANTITY <value>
NPC_MOVE <npc> TO <location>         NPC_STATUS <npc> ADD|REMOVE <status>
```

`UPDATE_CONDITION` accepts `health`, `hunger`, `thirst`, `morale` (numeric; a
leading `+`/`-` adjusts, a bare number sets) and `sleep`, `infection_risk`
(free text). `MOVE_TO` accepts a location id, a display name, or a compass
direction out of the current room.

Relationships are directional and stored source -> target. Everything that reads
them asks how the **NPC** regards the **player**, so that is the direction
`UPDATE_RELATIONSHIP` and the starting values in `data/npcs.py` write.

The scores themselves never reach the prompt. `build_prompt` sends banded labels
-- `Disposition: friendly (trust: solid)` -- because the player has no way to
read an integer off someone's face, and a game master given the number narrates
to the number. The bands live in `RelationshipManager`.

## Requirements

**Python 3.13 or newer.** The game model uses PEP 696 type-parameter defaults
(`class WeaponTakeDamageEvent[T: BaseEntity = BaseEntity, ...]`), which 3.12
rejects with a bare `SyntaxError`.

Plus [LM Studio](https://lmstudio.ai/) running a chat model on port 1234 with
its OpenAI-compatible API enabled.

## Setup

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

`.venv` is gitignored. To skip activation, call the interpreter directly:
`.venv\Scripts\python -m pip install -r requirements.txt`, then
`.venv\Scripts\python app.py`.

Then open <http://localhost:5000>.

`/reset` deletes the save and starts a fresh game.

## Tests

```powershell
.venv\Scripts\python -m unittest discover -s tests -t . -b
```

`-b` buffers stdout so the engine's per-turn logging only appears for failing
tests. The suite is offline and takes a few seconds: the LLM and the embedding
model are stubbed, and every test that persists writes to a temp directory
rather than your real save.

| File | Covers |
| --- | --- |
| `tests/test_game_manager.py` | Starting state, prompt assembly, all 15 action verbs, memory tiers |
| `tests/test_persistence.py` | Save/load round trip, schema guarding, corrupt and stale saves |
| `tests/test_llm.py` | STORY/EVENT/ACTIONS parsing |
| `tests/test_engine.py` | Turn orchestration, summarization, LLM failure, reset |
| `tests/test_routes.py` | All four routes through Flask's test client |
| `tests/test_memory.py` | FAISS recall (opt-in, see below) |

`tests/test_memory.py` exercises real FAISS and a real embedding model, so it is
skipped unless you opt in — the first run downloads `all-MiniLM-L6-v2`:

```powershell
$env:RPG_TEST_EMBEDDINGS="1"; .venv\Scripts\python -m unittest discover -s tests -t . -b
```

## Endpoints

| Route | Method | Purpose |
| --- | --- | --- |
| `/` | GET | The game interface |
| `/state` | GET | Current state, so a reloaded page shows the real world |
| `/play` | POST | `{"input": "..."}` -> runs a turn |
| `/reset` | POST | Deletes the save, starts a new game |

## Configuration

| Setting | Location |
| --- | --- |
| `MAX_RECENT_EVENTS` (5) | `managers/game.py` |
| `SUMMARY_THRESHOLD` (10) | `managers/game.py` |
| `DEFAULT_RECALL` (2) | `adapters/memory.py` |
| `EMBEDDING_MODEL_NAME` | `adapters/memory.py` |
| `LM_STUDIO_URL`, temperature, system prompt | `adapters/llm.py` |
| `SCHEMA_VERSION`, `SAVE_FILE` | `adapters/persistence.py` |

## Known gaps

- The event/effect pipeline (`GameManager.drain_event_queue`, traits and perks
  producing modifiers) is implemented but nothing enqueues events yet -- the LLM
  action verbs do not create `WeaponDealDamageEvent` and friends. Combat is
  therefore defined but unreachable.
- `NpcEntity` has hit points and an inventory, but no action verb uses them.
- `adapters/memory.py` imports `sentence_transformers` at module scope, which
  contacts the Hugging Face Hub on import even when no embedding is needed.
