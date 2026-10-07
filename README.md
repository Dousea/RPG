# Local LLM RPG

A text-based RPG powered by a local Large Language Model (LLM), with a typed
game model, persistent state and semantic memory retrieval. The game is set in a
slow-burn zombie apocalypse; the LLM acts as game master while the Python model
owns the rules.

## Architecture

The codebase is layered. Each layer only depends on the ones above it:

```
modules/     Pure game model -- entities, items, events, effects, modifiers,
             the typed action plan (modules/action/parser.py). No I/O, no framework, no LLM.
data/        Static content -- the item catalog, the map, NPC roster,
             trait and perk definitions.
managers/    Game logic -- GameManager (state + prompt delegation),
             ActionValidator (preconditions), SimulationCore (outcomes),
             ContextBuilder (prompt assembly), RelationshipManager.
adapters/    Everything that touches the outside world.
app.py       HTTP only.
```

`modules/` and `managers/` know nothing about Flask, HTTP, JSON files or FAISS.
Every such dependency lives in `adapters/`:

| Module | Responsibility |
| --- | --- |
| `adapters/llm.py` | LM Studio chat completions, the parser/narrator system prompts, response parsing |
| `adapters/factcheck.py` | State questions to a decision model about the narrator's story; its confident conflicts with the engine |
| `adapters/memory.py` | FAISS semantic search over the full event log |
| `adapters/save/codec.py` | A `GameManager` as a JSON-ready dict and back; `SCHEMA_VERSION` |
| `adapters/save/files.py` | Save/load that dict to `gamedata/engine_state.json` |
| `adapters/engine.py` | `GameEngine` -- orchestrates one turn end to end |

See [docs/01-engine-authority.md](docs/01-engine-authority.md) for why the turn
is shaped this way: the engine decides every outcome doc 01 lists as
authoritative (HP, inventory, movement, combat, quest completion, time) before
the LLM is ever asked to narrate it, instead of narrating first and vetoing
afterward.

### A turn

```
POST /play
    |
    v
GameEngine.play()                             [adapters/engine.py]
    |
    +-- SemanticMemory.search()               recall relevant past events (FAISS)
    +-- ContextBuilder.build_parser_prompt()  minimal scene context, no prose
    +-- llm.query_parser()                    ask LM Studio what Orton is trying to do
    +-- llm.parse_action_response()           extract ACTIONS lines
    +-- modules.action.parser.parse_action_plan()    turn lines into typed AnyAction
    +-- ActionValidator(manager).validate     is each action legal? (no mutation)
    +-- SimulationCore(manager).resolve       decide outcomes, mutate state, one at
    |                                         a time so an earlier action (move) can
    |                                         unlock a later one (take) in the same turn
    +-- ContextBuilder.build_narrator_prompt() full context + [OUTCOMES] facts
    +-- llm.query_narrator()                  ask LM Studio to describe what happened
    +-- llm.parse_narrator_response()         split into STORY / OPTIONS
    +-- StoryChecker.conflicts()              story vs the engine's zombie state; one narrator retry
    +-- build_event_entry() + record_event()  engine-written entry to short-term + full log
    +-- SemanticMemory.rebuild()              reindex
    +-- llm.query_summary()                   fold old events into a summary
    +-- persistence.save()                    write engine_state.json
    |
    v
JSON payload -> frontend
```

Two LLM calls per turn, not one: the parser proposes, the engine decides, the
narrator describes. A refused action is surfaced to the narrator the *same*
turn via `[OUTCOMES]` -- there is no next-turn `[CONTINUITY]` correction for
anything the validator or simulation core could catch.

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
id on load, so content can be rebalanced without invalidating saves. `SCHEMA_VERSION`
is 4. A save whose `version` is anything else is discarded and a new game
starts, rather than being loaded half-understood, and unknown ids (a deleted item, a renamed
location) are dropped with a log line instead of crashing the load.

Persisted: player (position, `current_place`, condition, inventory, equipment,
traits, perks), NPCs (position, status, notes, condition, goals, knowledge),
relationships (affinity, trust, reputation), narrative state (the minute clock,
goals, flags, discovered flags, apocalypse stage, pending corrections,
`game_over`, `death_cause`), quest state (`GameManager.quests`) and all three
memory tiers. The world clock (`World.time`, `World.date`) is written too, but
it is derived from the narrative clock and recomputed on load.
Door lock state (e.g. the apartment door) is *not* persisted -- doors are
part of the static map and always rebuild locked.

## Actions

The parser proposes state changes as one action per line (`modules/action/parser.py`
parses each into a typed `AnyAction`); the Action Validator
(`managers/validator.py`) checks legality with no side effects, and the
Simulation Core (`managers/simulation.py`) is the only thing that mutates
state. An unparseable or illegal action is refused before narration and
surfaced to the narrator this same turn via `[OUTCOMES]` -- the narrative
never gets ahead of what the engine actually decided.

```
TAKE <item>                          DROP <item>
WEAR <item>                          TAKE_OFF <item>
MOVE_TO <zone|in|out|spot>           ATTACK <target>
USE_ITEM <item>                      WAIT <10m|2h|1h30m|until night|until HH:MM>
SLEEP [duration]                     EXERCISE <type> [10-60 minutes]
STATUS_ADD <status>                  STATUS_REMOVE <status>
UPDATE_CONDITION <field> <value>     SET_FLAG <flag> true|false
DISCOVER_FLAG <flag>
ADD_GOAL short_term|long_term <t>    REMOVE_GOAL short_term|long_term <t>
UPDATE_RELATIONSHIP <npc> affection|trust <+/-N>
ADD_RELATIONSHIP_NOTE <npc> <text>
UPDATE_INVENTORY <item> ADD|REMOVE|UPDATE_CONDITION|UPDATE_QUANTITY <value>
NPC_MOVE <npc> TO <zone>             NPC_STATUS <npc> ADD|REMOVE <status>
```

`UPDATE_CONDITION` is always refused: the engine moves hunger, thirst, fatigue and
the other survival stats with the clock (see
[docs/mechanics/02-survival-stats.md](docs/mechanics/02-survival-stats.md)), and
player health is never LLM-declarable (see docs/01-engine-authority.md). Player
health is derived from the body parts and only changes through zombie wounds,
bleeding, infection and the other body effects described in
[docs/mechanics/12-health-and-infection.md](docs/mechanics/12-health-and-infection.md);
`_check_player_death` (`managers/simulation.py`) is the only producer of
`game_over`. `MOVE_TO` resolves its
destination against a zone id, display name, alias, or `in`/`out` connection
out of the current zone (`GameManager.resolve_location`); a zone that isn't
directly adjacent is reached by walking the connection graph
(`GameManager.zone_path`). Generic room nouns ("kitchen", "bathroom",
"office", "upstairs", ...) are deliberately *not* global aliases -- only
names that unambiguously mean one particular zone are (see
`data/locations.py`'s `aliases` lists); anything else, including a
now-unaliased room word, becomes a free-text spot inside the zone the player
is already in rather than teleporting him. `MOVE_TO` never refuses. A locked
door (`DoorEntity`) along the walk stops the player at the door rather than
refusing the move outright, unless the matching key is in inventory. A spot
move is free; a zone change costs one tick regardless of how many hops it
took. `NPC_MOVE` is unaffected by any of this and resolves strictly, via
`GameManager.resolve_zone_exact` (id, display name, or an exact alias only --
no connection directions, no whole-word fallback, so a phrase that would
soft-land for `MOVE_TO` is simply unknown here): it can fail, and it fails
in particular for `zone_home` unless Orton is already there himself (his
apartment door is locked from the building side and nobody else has a key).
Separately, any item that is the `key_id` of a `DoorEntity` anywhere in the
world -- not just the apartment key, whichever it is -- can neither be
`DROP`ped, `UPDATE_INVENTORY ... REMOVE`d, `UPDATE_INVENTORY ... ADD`ed back
into existence, nor `UPDATE_QUANTITY`'d away from exactly one: all are
rejected, so Orton can't lock himself out of his own home by discarding,
deleting, or duplicating his key (the door rebuilds `LOCKED` on every load).
`UPDATE_CONDITION` is unaffected, since it never removes an item. `SET_FLAG`
sets the engine's ground truth for a world fact; `DISCOVER_FLAG` separately
marks that the player has learned it, which is what makes it visible in the
narrator's prompt (doc 11's knowledge firewall applied to world flags, not
just relationship scores).

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

The project uses [mise](https://mise.jdx.dev/) on every OS. `mise.toml` pins
Python 3.13 and uv, creates `.venv` with uv, and activates it whenever you are
inside the project directory.

```bash
mise trust
mise install
mise run install    # uv pip install -r requirements.txt -r requirements-dev.txt
mise run dev        # python app.py
```

Auto-activation needs mise's shell hook (`mise activate zsh`/`bash`, or
`mise activate pwsh | Out-String | Invoke-Expression` in your PowerShell
`$PROFILE` on Windows). Without it, `mise run` and `mise exec -- python ...`
still use `.venv`.

On Linux, `sentence-transformers` pulls in the multi-GB CUDA build of PyTorch
by default. The embedding model runs fine on CPU; install the CPU-only build
first to skip that download:

```bash
uv pip install torch --index-url https://download.pytorch.org/whl/cpu
mise run install
```

A second, small decision model checks the narrator's story against the engine's
state: load the Tev1-4B GGUF (about 2.8 GB at Q4_K_M) in LM Studio beside the
narrator, under the key in `factcheck.model_name`. Set `factcheck.enabled: false` in
`config.yml` to skip the check; if the model is not loaded the check logs a warning
and the game plays on.

The parser and the narrator can be different models: `llm.model_name` names the
narrator's (needed once more than one model is loaded) and `llm.parser_model_name` the
parser's; left empty, the narrator's model parses too. LM Studio loads the parser's
model on its first request without unloading the others, so load the narrator and the
decision model first: they keep the GPU, and the parser runs partly from system memory,
which slows only the parse.

`.venv` is gitignored.

### Without mise

Windows:

```powershell
py -3.13 -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python app.py
```

Linux / macOS:

```bash
python3.13 -m venv .venv
source .venv/bin/activate
python -m pip install -r requirements.txt
python app.py
```

Then open <http://localhost:5000>.

If LM Studio runs on another machine, point `llm.base_url` in `config.yml` at
it (e.g. `http://192.168.0.231:1234/v1/chat/completions`) and enable *Serve on
Local Network* in LM Studio's server settings.

`/reset` deletes the save and starts a fresh game.

## Tests

```bash
mise run test
```

Without mise, run `python -m unittest discover -s tests -t . -b` from the
activated venv.

Code checks, configured in `pyproject.toml`:

```bash
mise run fmt        # ruff format + autofix
mise run lint       # ruff, format check, import-linter layer contracts
mise run typecheck  # basedpyright; errors already in .basedpyright/baseline.json are tolerated
mise run check      # lint + typecheck + test
```

`import-linter` enforces the [layering](#architecture): `modules/` and `data/`
import nothing from the layers above them, and no game-logic package imports
Flask, requests, FAISS or YAML. Project conventions for the code (randomness,
time, constants, logging) are in [AGENTS.md](AGENTS.md).

`-b` buffers output so the engine's log lines only appear for failing tests. The suite is offline and takes a few seconds: the LLM and the embedding
model are stubbed, and every test that persists writes to a temp directory
rather than your real save.

| File | Covers |
| --- | --- |
| `tests/test_action.py` | ACTIONS-line parsing into typed `AnyAction`/`ParseFailure` |
| `tests/test_validator.py` | Action Validator: preconditions only, no mutation |
| `tests/test_simulation.py` | Simulation Core: item effects, world-state actions, player death, outcome facts, weather |
| `tests/test_movement.py` | `MOVE_TO` resolution: zones, spots, the apartment door, exits |
| `tests/test_combat.py` | `ATTACK` resolution: weapons, damage, trait and perk reactions |
| `tests/test_time_and_sleep.py` | Action time costs, the clock, stats per turn, sleep, stat deaths |
| `tests/test_consumption.py` | Eating and drinking: consumable fields, status effect facts, alcohol |
| `tests/test_context.py` | ContextBuilder: the knowledge firewall (world flags, NPC goals vs. knowledge) |
| `tests/test_quests.py` | Quest state: engine-only completion |
| `tests/test_game_manager.py` | Starting state, prompt assembly, memory tiers |
| `tests/test_persistence.py` | Save/load round trip, schema guarding, corrupt and stale saves |
| `tests/test_llm.py` | Parser ACTIONS extraction and narrator STORY/OPTIONS parsing |
| `tests/test_engine.py` | Turn orchestration (two LLM calls), summarization, LLM failure, reset |
| `tests/test_routes.py` | All four routes through Flask's test client |
| `tests/test_memory.py` | FAISS recall (opt-in, see below) |

`tests/test_memory.py` exercises real FAISS and a real embedding model, so it is
skipped unless you opt in — the first run downloads `all-MiniLM-L6-v2`:

```bash
RPG_TEST_EMBEDDINGS=1 mise run test
```

```powershell
$env:RPG_TEST_EMBEDDINGS="1"; mise run test
```

## Endpoints

| Route | Method | Purpose |
| --- | --- | --- |
| `/` | GET | The game interface |
| `/state` | GET | Current state, so a reloaded page shows the real world |
| `/play` | POST | `{"input": "..."}` -> runs a turn |
| `/play/stream` | POST | The same turn, streamed as JSON lines: each step, the narrator's thinking and story as written, then the turn |
| `/reset` | POST | Deletes the save, starts a new game |

## Configuration

| Setting | Location |
| --- | --- |
| `MAX_RECENT_EVENTS` (5) | `managers/game.py` |
| `SUMMARY_THRESHOLD` (10) | `managers/game.py` |
| `DEFAULT_RECALL` (2) | `adapters/memory.py` |
| `EMBEDDING_MODEL_NAME` | `adapters/memory.py` |
| `LM_STUDIO_URL`, parser/narrator temperatures, system prompts | `adapters/llm.py` |
| `SCHEMA_VERSION` | `adapters/save/codec.py` |
| `SAVE_FILE` | `adapters/save/files.py` |

## Known gaps

- `NpcEntity.knowledge` exists as a field but nothing reads it yet -- there is
  no dialogue system to gate what an NPC can truthfully say against it, so it
  currently does nothing beyond persisting.
- NPC `status` and `notes` still reach the narrator prompt unfiltered; only
  relationship scores and world flags go through the knowledge firewall.
- Quest state (`GameManager.quests`) is a flat objective-completion checklist
  advanced by the Simulation Core noticing a matching action -- there is no
  Story Director reacting to arbitrary world state (docs/07-story-architecture.md).
- No seeded randomness: combat damage jitter and the LLM itself are both
  unseeded (docs/16-determinism-and-versioning.md is out of scope).
- The map is four hand-written zones. No procedural generation, no
  simulation level-of-detail for distant NPCs (docs/05, 06 are out of scope).
- `adapters/memory.py` imports `sentence_transformers` at module scope, which
  contacts the Hugging Face Hub on import even when no embedding is needed.
