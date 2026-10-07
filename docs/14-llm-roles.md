# Local LLM Roles and Narrator Constraints

> **Status: Partial.** Two calls now, `query_parser` and `query_narrator` in `adapters/llm.py`, each with its own system prompt and response format (the parser's is a JSON schema built per turn, with a text fallback) — the narrator's no longer has an `ACTIONS:` section to fill at all. The constraints below are structurally reinforced (the narrator has nothing left to declare state through) but still not mechanically enforced against a model that ignores its prompt. See [Implementation Status](00-status.md).

## Local LLM Roles

### 1. Parser Model

Priorities:

- low latency;
- structured output;
- strict instruction following;
- small context;
- deterministic behavior.

Responsibilities:

```text
player language
    ↓
intent
    ↓
action plan
```

### 2. Narrator Model

Priorities:

- prose quality;
- dialogue quality;
- contextual consistency;
- atmosphere;
- style control.

Responsibilities:

```text
validated result
+
permitted context
    ↓
prose / dialogue
```

The Parser and Narrator can use different local models: `llm.parser_model_name` names
the parser's, and empty means it shares the narrator's `llm.model_name`. The summarizer
writes prose, so it asks the narrator's model.

A larger model is not required for every task.

### Reply caps and the prompt budget

Every call sends `max_tokens`: the narrator 800, the parser 400, the summarizer 300
(`llm.narrator_max_tokens`, `parser_max_tokens`, `summarizer_max_tokens`).
`llm.context_tokens` (8192) is the loaded model's window. The adapter learns the
characters-per-token ratio from each reply's `usage.prompt_tokens` (3.5 until one
arrives), and the engine cuts the narrator's user prompt to
`(context_tokens - narrator_max_tokens - 200) * ratio - len(system prompt)`
characters. What is cut, and in what order, is in
[document 13](13-context-and-memory.md).

### The fact check

After the narrator replies, a small decision model (`adapters/factcheck.py`), served by
LM Studio next to the narrator, answers one state question about the end of the story:
has the zombie the turn's facts are about been killed (yes, no or unclear). For now only a turn whose facts name exactly one zombie is checked. An
answer the engine's state does not allow, given with probability 0.9 or more
(`factcheck.conflict_threshold`), makes the engine ask the narrator once more with a
`[CORRECTION]` block stating the true state; "unclear" never conflicts. The retry is kept
unless it conflicts on more questions than the first story. The check only chooses
which prose is shown and never changes a fact. `factcheck.enabled: false` turns it off.
Details in [the LLM contract](mechanics/10-llm-contract.md).

---

## Narrator Constraints

The narrator receives:

```text
validated state
+
visible entities
+
permitted knowledge
+
recent results
+
style instructions
```

The narrator must not:

- invent items;
- invent exits;
- invent NPCs that do not exist;
- change HP;
- change inventory;
- resolve a failed action as successful;
- reveal hidden facts;
- create quest outcomes;
- alter faction state;
- teleport the player.

Example engine result:

```json
{
  "result": "attack_failed",
  "reason": "target_out_of_range",
  "noise": 4
}
```

Narrator output can be:

> You lunge forward, but the infected is farther away than you expected. Your blade cuts through empty air.

The prose is flexible; the fact is not.

---

[← Context Construction and Memory Layers](13-context-and-memory.md) · [Index](README.md) · [Full Turn Loop and Failure Handling →](15-turn-loop.md)
