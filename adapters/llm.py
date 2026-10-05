"""LM Studio client and response parsing.

Two roles, two calls, in place of the old single game-master call: the parser
turns player input plus a minimal scene description into a proposed ACTIONS
block (no prose, and no authority -- the engine validates and simulates every
line before anything is narrated); the narrator then turns the engine's
already-decided outcome facts into STORY/EVENT prose. Per docs/01-engine-authority.md,
the LLM interprets intent and writes prose; it never decides state.
"""

import requests

import config
from data.quests import NPC_STATUSES, STORY_FLAGS

LM_STUDIO_URL = config.llm.base_url

# LM Studio serves whatever model is loaded; this value is ignored.
MODEL_NAME = config.llm.model_name


def _vocabulary_lines(vocabulary: dict[str, str]) -> str:
    return "".join(f"  {name} -- {when}\n" for name, when in sorted(vocabulary.items()))


# Built from data/quests.py rather than written out here, so a quest keyed on
# a story flag can't drift away from the name the parser was taught. These are
# static names, not game state -- no firewall concern (the parser learns that
# the flag *exists*, never whether it is set; see ContextBuilder).
STORY_VOCABULARY = (
    "STORY VOCABULARY: the game tracks these exact names. When the input "
    "clearly matches one, use the name spelled exactly as given -- a near "
    "miss is silently ignored by the engine. Any other name is fine for an "
    "incidental fact, but these are the ones that matter.\n"
    "DISCOVER_FLAG names:\n"
    f"{_vocabulary_lines(STORY_FLAGS)}"
    "NPC_STATUS names:\n"
    f"{_vocabulary_lines(NPC_STATUSES)}"
)

PARSER_SYSTEM_PROMPT = (
    "You are the intent parser for a text-based zombie apocalypse RPG. Orton, "
    "a software developer, is the player character. Your only job is to turn "
    "what Orton says he does into a list of game actions. You do not write "
    "prose, and you do not decide whether an action succeeds -- the game "
    "engine resolves that afterwards, before anything is narrated.\n\n"
    "CRITICAL: only propose actions Orton explicitly asked for. If he says "
    "'look around', propose NONE -- looking is not an action that changes "
    "anything. Never invent an action he did not ask for, and never propose "
    "an outcome (damage numbers, how an NPC reacts) -- only the action "
    "itself; the engine decides what happens.\n\n"
    "Respond with ONLY an actions block, in this exact format:\n\n"
    "ACTIONS:\n"
    "[List any game actions implied by the input, one per line. Available actions:]\n"
    "- TAKE item_name\n"
    "- DROP item_name\n"
    "- MOVE_TO zone_name, in/out, or a specific spot (e.g. 'the kitchen')\n"
    "- ATTACK target_name\n"
    "- USE_ITEM item_name\n"
    "- TIME_ADVANCE morning/afternoon/evening/night\n"
    "- STATUS_ADD status_name\n"
    "- STATUS_REMOVE status_name\n"
    "- UPDATE_CONDITION hunger/thirst/morale/sleep/infection_risk value\n"
    "- ADD_GOAL short_term/long_term goal_text\n"
    "- REMOVE_GOAL short_term/long_term goal_text\n"
    "- UPDATE_RELATIONSHIP npc_name affection/trust +/-number\n"
    "- ADD_RELATIONSHIP_NOTE npc_name note_text\n"
    "- SET_FLAG flag_name true/false\n"
    "- DISCOVER_FLAG flag_name (Orton has just learned this world fact)\n"
    "- UPDATE_INVENTORY item_name ADD/REMOVE/UPDATE_CONDITION/UPDATE_QUANTITY value\n"
    "- NPC_MOVE npc_name TO zone_name\n"
    "- NPC_STATUS npc_name ADD/REMOVE status_name\n"
    "[If no actions are implied, write: NONE]\n\n"
    "Note: there is no action for dealing or taking damage directly, and no "
    "way to set health -- ATTACK is how combat starts; the engine computes "
    "the result.\n\n"
    f"{STORY_VOCABULARY}\n"
    "Example:\n"
    "Input: 'I grab the water bottle and head out'\n"
    "ACTIONS:\n"
    "TAKE Water Bottle\n"
    "MOVE_TO out"
)

NARRATOR_SYSTEM_PROMPT = (
    "You are the narrator for a serious, grounded, text-based zombie apocalypse RPG. "
    "Write in second-person ('you') addressing Orton, a software developer trying to survive societal collapse.\n\n"
    "ORTON'S CHARACTER:\n"
    "- Software developer, lives alone, just moved to new apartment\n"
    "- Cautious but occasionally impulsive, logical under stress\n"
    "- Ambivert: socially fluid but easily drained, people pleaser who clings to others\n"
    "- Fears: needles, blood, dentists\n"
    "- Interested in women, secretly craves connection despite trying to stay distant\n"
    "- Falls easily for women, conflicted about it\n"
    "- Survival philosophy: keep head down, avoid attachment (struggles to maintain this)\n\n"
    "NARRATIVE STYLE:\n"
    "- Emotionally grounded and character-driven\n"
    "- Start with slow-burn collapse, hint at unrest/disease/infrastructure failure\n"
    "- Focus on realistic human reactions and relationship dynamics\n"
    "- Allow downtime: conversations, bonding, vulnerability, arguments\n"
    "- Present choices but allow custom responses\n"
    "- Romance should evolve naturally based on character interactions\n\n"
    "[OUTCOMES] tells you exactly what happened this turn -- movement, combat, "
    "item use, everything the engine already decided before you were asked to "
    "write anything. Narrate what is there. Never contradict it, never invent "
    "your own HP/inventory/combat numbers, and never describe something "
    "labeled 'Refused' as having succeeded -- write around it instead. If "
    "[OUTCOMES] says Orton has died, narrate his death as final -- this is "
    "the end of the story, not a setback he recovers from -- and write "
    "OPTIONS: NONE\n\n"
    "[QUESTS] lists what Orton is currently working toward. Use it for "
    "motivation and flavor -- you may not declare a quest objective complete "
    "yourself; that only happens through [OUTCOMES].\n\n"
    "[CURRENT LOCATION]'s description is reference material, not a script to "
    "recite. Orton already knows what a space looks, sounds, and smells like "
    "once he's been standing in it -- do not re-describe the room, the "
    "lighting, the air, or the ambient noise again just because the block is "
    "there. Only bring physical surroundings back into the prose when "
    "something about them has actually changed (a new arrival, an action "
    "that disturbs the space, a shift in time or weather) or when the "
    "player's own action draws attention to a specific detail. Otherwise, "
    "spend the words on what's new this turn: the outcome, the dialogue, the "
    "character beat.\n\n"
    "After EVENT, add an OPTIONS section: 2-4 short, concrete things Orton "
    "could plausibly do next, each on its own line starting with '- '. These "
    "are only suggestions -- Orton can always ignore them and do something "
    "else entirely, so never phrase them as the only paths forward. If "
    "nothing sensible suggests itself (Orton is mid-action, or waiting on "
    "someone else mid-conversation), write NONE instead of forcing options.\n\n"
    "Your response must follow this EXACT format:\n\n"
    "STORY:\n"
    "[Write the narrative in second-person, addressing Orton directly]\n\n"
    "EVENT:\n"
    "[Brief summary for the event log]\n\n"
    "OPTIONS:\n"
    "[2-4 short suggestions, one per line, each starting with '- ', or NONE]\n\n"
    "Example:\n"
    "STORY:\n"
    "A woman about your age is wrestling with an armful of groceries outside the "
    "door next to yours. She catches you watching and gives an easy, curious "
    "smile, like she's sizing up the new neighbor.\n\n"
    "EVENT:\n"
    "Orton crossed paths with a neighbor in the hallway\n\n"
    "OPTIONS:\n"
    "- Offer to help her with the groceries\n"
    "- Introduce yourself\n"
    "- Give a polite nod and keep walking"
)

SUMMARIZER_SYSTEM_PROMPT = (
    "You are a story summarizer. Condense the following events into a single, "
    "concise narrative paragraph."
)


class LLMError(RuntimeError):
    """Raised when LM Studio is unreachable or answers in an unusable shape."""


def _chat(system_prompt: str, user_content: str, temperature: float) -> str:
    payload = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
    }

    try:
        response = requests.post(
            LM_STUDIO_URL,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=config.llm.request_timeout,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as exc:
        raise LLMError(
            f"Could not reach LM Studio at {LM_STUDIO_URL}. Is it running? ({exc})"
        ) from exc
    except (KeyError, IndexError, ValueError) as exc:
        raise LLMError(f"LM Studio returned an unexpected response shape: {exc}") from exc


def query_parser(prompt_text: str) -> str:
    """Ask the intent parser what actions player input implies. Raises LLMError on failure."""
    raw = _chat(PARSER_SYSTEM_PROMPT, prompt_text, temperature=config.llm.parser_temperature)
    print("--- Parser Raw Response ---")
    print(raw)
    print("---------------------------")
    return raw


def query_narrator(prompt_text: str) -> str:
    """Ask the narrator to describe outcomes the engine already decided. Raises LLMError on failure."""
    raw = _chat(NARRATOR_SYSTEM_PROMPT, prompt_text, temperature=config.llm.narrator_temperature)
    print("--- Narrator Raw Response ---")
    print(raw)
    print("-----------------------------")
    return raw


def query_summary(text_to_summarize: str) -> str:
    """Condense events into a narrative paragraph. Raises LLMError on failure."""
    return _chat(
        SUMMARIZER_SYSTEM_PROMPT,
        text_to_summarize,
        temperature=config.llm.summarizer_temperature,
    ).strip()


def parse_action_response(llm_response_text: str) -> list[str]:
    """Extract raw action lines from a parser-call response.

    Tolerant of the model dropping the `ACTIONS:` header: with only one
    section to write, a small local model sometimes skips the header it used
    to need to distinguish ACTIONS from STORY/EVENT. If no header is found,
    every non-blank line is treated as a candidate action line, which is what
    `modules.action.parse_action_plan` would have received anyway.
    """
    lines = llm_response_text.splitlines()
    header_index = next(
        (i for i, line in enumerate(lines) if line.strip().upper().startswith("ACTIONS:")),
        None,
    )
    if header_index is not None:
        remainder = lines[header_index].strip()[len("ACTIONS:") :].strip()
        lines = ([remainder] if remainder else []) + lines[header_index + 1 :]
    return [line for line in lines if line.strip()]


def parse_narrator_response(llm_response_text: str) -> dict[str, str | list[str]]:
    """Split a STORY/EVENT/OPTIONS narrator response into its parts.

    Section headers are matched line by line rather than by splitting on
    blank lines, so a story containing blank lines survives intact. OPTIONS
    is new and optional: a response with no OPTIONS section (or NONE) simply
    yields an empty list, so older-style responses still parse cleanly.
    """
    sections: dict[str, list[str]] = {"story": [], "event": [], "options": []}
    headers = {"STORY:": "story", "EVENT:": "event", "OPTIONS:": "options"}
    current: str | None = None

    for line in llm_response_text.splitlines():
        stripped = line.strip()
        matched_header = next((key for key in headers if stripped.upper().startswith(key)), None)
        if matched_header:
            current = headers[matched_header]
            remainder = stripped[len(matched_header) :].strip()
            if remainder:
                sections[current].append(remainder)
            continue
        if current:
            sections[current].append(line)

    story = "\n".join(sections["story"]).strip()
    event = "\n".join(sections["event"]).strip()
    # FW8: the model sometimes punctuates "NONE" (a period, an exclamation
    # mark, a semicolon, a colon) -- strip that before comparing, or it reads
    # as a stray one-item options list instead of "no options".
    options = [
        stripped.lstrip("-").strip()
        for raw_line in sections["options"]
        if (stripped := raw_line.strip()) and stripped.upper().rstrip(".!;:") != "NONE"
    ]

    return {
        "story": story or "The world is silent.",
        "event": event or "Nothing happened.",
        "options": options,
    }
