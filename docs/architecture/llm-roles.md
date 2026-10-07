# Local LLM Roles and Narrator Constraints

> **Status: Partial.** Two calls now, `query_parser` and `query_narrator` in `adapters/llm.py`, each with its own system prompt and response format (the parser's is a JSON schema built per turn, with a text fallback) — the narrator's no longer has an `ACTIONS:` section to fill at all. The constraints below are structurally reinforced (the narrator has nothing left to declare state through) but still not mechanically enforced against a model that ignores its prompt. See [Implementation Status](../status.md).

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
[the context-and-memory doc](context-and-memory.md).

### The plan check and the fact check

A decision model (`adapters/factcheck.py`), a small one beside the narrator
or the narrator's own, answers yes/no questions twice a turn. After the parser
replies, it is asked whether each action is something the player asked for;
one it rules out is never resolved and reaches the narrator as a refusal. After
the narrator replies, it answers state questions about the story; an answer
the engine's state rules out makes the engine ask the narrator once more. The
plan check can only take actions away, never add or change one, and the story
check only chooses which prose is shown. The questions, the
threshold and the retry rule are in the LLM contract's
[plan check](../mechanics/llm-contract.md#the-plan-check) and
[fact check](../mechanics/llm-contract.md#the-fact-check).

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

[Index](../README.md)
