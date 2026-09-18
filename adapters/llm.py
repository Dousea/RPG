"""LM Studio client and response parsing.

The system prompt and the STORY/EVENT/ACTIONS response contract are carried over
from the original app.py loop unchanged -- the model is tuned for that format,
and the action verbs match GameManager's handlers one for one.
"""

import requests

LM_STUDIO_URL = "http://localhost:1234/v1/chat/completions"

# LM Studio serves whatever model is loaded; this value is ignored.
MODEL_NAME = "local-model"

GAME_MASTER_SYSTEM_PROMPT = (
    "You are the game master for a serious, grounded, text-based zombie apocalypse RPG. "
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
    "- Romance should evolve naturally based on character interactions\n"
    "- CRITICAL: Only perform actions Orton explicitly requests\n"
    "- If he says 'look around', only DESCRIBE - don't auto-interact with objects\n\n"
    "Your response must follow this EXACT format:\n\n"
    "STORY:\n"
    "[Write the narrative in second-person, addressing Orton directly]\n\n"
    "EVENT:\n"
    "[Brief summary for the event log]\n\n"
    "ACTIONS:\n"
    "[List any game state changes needed, one per line. Available actions:]\n"
    "- TAKE item_name\n"
    "- DROP item_name\n"
    "- MOVE_TO location_name\n"
    "- TIME_ADVANCE morning/afternoon/evening/night\n"
    "- STATUS_ADD status_name\n"
    "- STATUS_REMOVE status_name\n"
    "- UPDATE_CONDITION health/hunger/thirst/morale/sleep/infection_risk value\n"
    "- ADD_GOAL short_term/long_term goal_text\n"
    "- REMOVE_GOAL short_term/long_term goal_text\n"
    "- UPDATE_RELATIONSHIP npc_name affection/trust +/-number\n"
    "- ADD_RELATIONSHIP_NOTE npc_name note_text\n"
    "- SET_FLAG flag_name true/false\n"
    "- UPDATE_INVENTORY item_name ADD/REMOVE/UPDATE_CONDITION/UPDATE_QUANTITY value\n"
    "- NPC_MOVE npc_name TO location_name\n"
    "- NPC_STATUS npc_name ADD/REMOVE status_name\n"
    "[If no actions needed, write: NONE]\n\n"
    "Example:\n"
    "STORY:\n"
    "You glance at your neighbor Emma as she struggles with groceries. Her smile seems genuine as she notices you watching.\n\n"
    "EVENT:\n"
    "Orton observed Emma in the hallway\n\n"
    "ACTIONS:\n"
    "UPDATE_RELATIONSHIP Emma affection +1\n"
    "ADD_RELATIONSHIP_NOTE Emma Seemed friendly, might be worth getting to know"
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
            timeout=300,
        )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as exc:
        raise LLMError(
            f"Could not reach LM Studio at {LM_STUDIO_URL}. Is it running? ({exc})"
        ) from exc
    except (KeyError, IndexError, ValueError) as exc:
        raise LLMError(f"LM Studio returned an unexpected response shape: {exc}") from exc


def query_game_master(prompt_text: str) -> str:
    """Run one game-master turn. Raises LLMError on failure."""
    raw = _chat(GAME_MASTER_SYSTEM_PROMPT, prompt_text, temperature=0.7)
    print("--- LLM Raw Response ---")
    print(raw)
    print("------------------------")
    return raw


def query_summary(text_to_summarize: str) -> str:
    """Condense events into a narrative paragraph. Raises LLMError on failure."""
    return _chat(
        SUMMARIZER_SYSTEM_PROMPT, text_to_summarize, temperature=0.5
    ).strip()


def parse_response(llm_response_text: str) -> dict[str, object]:
    """Split a STORY/EVENT/ACTIONS response into its three parts.

    Section headers are matched line by line rather than by splitting on blank
    lines, so a story containing blank lines survives intact.
    """
    sections: dict[str, list[str]] = {"story": [], "event": [], "actions": []}
    headers = {"STORY:": "story", "EVENT:": "event", "ACTIONS:": "actions"}
    current: str | None = None

    for line in llm_response_text.splitlines():
        stripped = line.strip()
        matched_header = next(
            (key for key in headers if stripped.upper().startswith(key)), None
        )
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
    actions = [
        action.strip().lstrip("-").strip()
        for action in sections["actions"]
        if action.strip() and action.strip().upper() != "NONE"
    ]

    return {
        "story": story or "The world is silent.",
        "event": event or "Nothing happened.",
        "actions": actions,
    }
