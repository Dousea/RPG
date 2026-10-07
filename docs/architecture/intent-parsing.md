# Intent Parsing and Action Planning

> **Status: Partial.** A real parser stage and typed action plan now exist: `adapters/llm.py`'s `query_parser` proposes an ACTIONS block from player input *before* anything is decided, and `modules/action/parser.py` parses each line into a typed `AnyAction` (or a `ParseFailure`) that `managers/validator.py`/`managers/simulation.py` decide on. The parser reply is constrained to a per-turn JSON schema (`modules/action/schema.py`), with the text lines as a fallback when the server rejects it. Still missing relative to this document: multi-action turns are resolved sequentially with each action validated against state as it stood after the previous one resolved, but there is no explicit "later actions can be invalidated by earlier ones" reporting beyond the per-action `Refused:` fact. See [Implementation Status](../status.md).

## Natural Language Is Not Game State

### 1. Natural Language Is Not Game State

The player can speak freely:

> "I strike a match to look around, then quietly move over to Sarah and ask what caused the noise."

The parser should convert that into a structured **Action Plan**.

```json
{
  "intent_id": "turn_18472",
  "actions": [
    {
      "type": "use",
      "target": "match_01"
    },
    {
      "type": "move",
      "target": "sarah",
      "approach": "stealth"
    },
    {
      "type": "talk",
      "target": "sarah",
      "intent": "ask",
      "topic": "noise"
    }
  ]
}
```

The LLM proposes the plan. The engine executes it.

---

## Sequential Action Execution

### 2. Sequential Action Execution

Multi-action commands must execute sequentially rather than atomically.

```text
Action 1: light match
    ↓
match consumed
    ↓
visibility changes
    ↓
Action 2: move toward Sarah
    ↓
engine checks current conditions
    ↓
Action 3: talk to Sarah
```

If the world changes during the sequence, later actions may become invalid.

Example:

```text
Player: "Open the door and run outside."

1. open door
2. zombies detected
3. door is damaged by attack
4. run action evaluated
5. movement may fail or produce consequences
```

The parser does not guarantee that the entire sentence will succeed.

---

## Action Vocabulary

### 3. Action Vocabulary

Use a controlled action vocabulary rather than allowing arbitrary action names.

```text
LOOK
MOVE
SEARCH
TAKE
DROP
USE
EQUIP
UNEQUIP
OPEN
CLOSE
LOCK
UNLOCK
ATTACK
AIM
SHOOT
DODGE
BLOCK
SNEAK
RUN
CLIMB
TALK
ASK
THREATEN
TRADE
GIVE
CRAFT
REST
WAIT
TRAVEL
```

Every action has a typed schema and explicit engine validation.

The LLM should also be constrained to valid structured output through a schema or grammar-constrained decoding mechanism where available.

---

[Index](../README.md)
