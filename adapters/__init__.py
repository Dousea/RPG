"""Adapters between the pure game model and the outside world.

`managers` and `modules` know nothing about HTTP, JSON files or FAISS. Every
such dependency lives here:

- `llm`         -- LM Studio chat completions, prompt framing, response parsing
- `memory`      -- FAISS semantic search over the full event log
- `save`        -- a GameManager as a JSON-ready dict (`save.codec`) and on
                   disk at gamedata/engine_state.json (`save.files`)
- `engine`      -- orchestrates one turn end to end
- `creation_payload` -- the creation screen's JSON and a submitted build

Nothing is re-exported here on purpose: `engine` imports `llm` and
`save`, so importing it from this module would make `adapters` a partly
initialized package while its own submodules are still loading. Import the
submodule you need directly (`from adapters.engine import GameEngine`).
"""
