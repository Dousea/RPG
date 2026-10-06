"""LM Studio client and response parsing.

Two roles, two calls, in place of the old single game-master call: the parser
turns player input plus a minimal scene description into a proposed ACTIONS
block (no prose, and no authority -- the engine validates and simulates every
line before anything is narrated); the narrator then turns the engine's
already-decided outcome facts into STORY/EVENT prose. Per docs/01-engine-authority.md,
the LLM interprets intent and writes prose; it never decides state.
"""

import json
import logging
import re
from dataclasses import dataclass
from typing import Any

import requests

import config
from data.time_costs import MAX_PLAN_ACTIONS
from modules.action.parser import ParseFailure, parse_action_plan
from modules.action.schema import parse_plan
from modules.action.types import AnyAction

logger = logging.getLogger(__name__)

LM_STUDIO_URL = config.llm.base_url

# LM Studio serves whatever model is loaded; this value is ignored.
MODEL_NAME = config.llm.model_name


_VERB_LINE = re.compile(r"^- ([A-Z_]+)\b", re.MULTILINE)


def listed_verbs(prompt: str) -> list[str]:
    """The verbs a parser prompt lists, in order."""
    return _VERB_LINE.findall(prompt)


_PARSER_INTRO = (
    "You are the intent parser for a text-based zombie apocalypse RPG. The "
    "player character is named in the [CHARACTER] block of each request. "
    "Your only job is to turn "
    "what the player says their character does into a list of game actions. You do not write "
    "prose, and you do not decide whether an action succeeds -- the game "
    "engine resolves that afterwards, before anything is narrated.\n\n"
    "CRITICAL: only propose actions the player explicitly asked for. If they say "
    "'look around', propose NONE -- looking is not an action that changes "
    "anything. Never invent an action they did not ask for, and never propose "
    "an outcome (damage numbers, how an NPC reacts) -- only the action "
    "itself; the engine decides what happens. Use only names the blocks list: "
    "items, zones, NPCs, zombie ids.\n\n"
)

_PARSER_TEXT_FORMAT = (
    "Respond with ONLY an actions block, in this exact format:\n\n"
    "ACTIONS:\n"
    "[List any game actions implied by the input, one per line, at most "
    f"{MAX_PLAN_ACTIONS}, each starting with a verb from [AVAILABLE ACTIONS]. "
    "If no actions are implied, write: NONE]\n\n"
)

_PARSER_JSON_FORMAT = (
    'Respond with ONLY a JSON object with one key, "actions": a list of the game '
    f"actions implied by the input, at most {MAX_PLAN_ACTIONS}, in order. Each "
    'action is an object whose "verb" is a verb from [AVAILABLE ACTIONS], plus '
    "that verb's own fields. If no actions are implied, the list is empty.\n\n"
)

_PARSER_RULES = (
    "Most inputs are one action; list more only when the player names more "
    "than one thing to do. What the character says to an NPC is one action, "
    "never two: ASK when it asks them to follow, stay, give an item or tell "
    "about a listed topic, and TALK for everything else. Pick the TALK approach "
    "that fits; the engine decides what it is worth. ASK 'give <item>' names an "
    "item the NPC holds; ASK 'about <topic>' names a topic listed under that NPC "
    "in [NPCS HERE].\n\n"
    "Note: there is no action for dealing or taking damage directly, for "
    "setting health, stats, flags or relationships, or for moving other "
    "characters -- the engine does all of that.\n\n"
)

PARSER_SYSTEM_PROMPT = (
    _PARSER_INTRO + _PARSER_TEXT_FORMAT + _PARSER_RULES + "Example:\n"
    "Input: 'I grab the water bottle and head out'\n"
    "ACTIONS:\n"
    "TAKE Water Bottle\n"
    "MOVE_TO out"
)

PARSER_JSON_SYSTEM_PROMPT = (
    _PARSER_INTRO + _PARSER_JSON_FORMAT + _PARSER_RULES + "Example:\n"
    "Input: 'I grab the water bottle and head out'\n"
    '{"actions": [{"verb": "TAKE", "item": "Water Bottle"}, '
    '{"verb": "MOVE_TO", "destination": "out"}]}\n'
    "Input: 'Emma, will you come with me?'\n"
    '{"actions": [{"verb": "ASK", "npc": "Emma", "request": "follow"}]}'
)

NARRATOR_SYSTEM_PROMPT = (
    "You are the narrator for a serious, grounded, text-based zombie apocalypse RPG. "
    "Write in second-person ('you') addressing the player character, a survivor of societal collapse.\n\n"
    "[CHARACTER] gives the character's name, pronouns, occupation, looks, backstory "
    "and traits. Let the traits colour how they act and react; never contradict them "
    "and never show them as numbers.\n\n"
    "NARRATIVE STYLE:\n"
    "- Emotionally grounded and character-driven\n"
    "- Start with slow-burn collapse, hint at unrest/disease/infrastructure failure\n"
    "- Focus on realistic human reactions and relationship dynamics\n"
    "- Allow downtime: conversations, bonding, vulnerability, arguments\n"
    "- Present choices but allow custom responses\n"
    "- Romance should evolve naturally based on character interactions\n\n"
    "The blocks run from memory to the present. [DEEP MEMORY], [SUMMARY OF PAST EVENTS] "
    "and [RECENT EVENTS] are the past; everything after them is how things stand now. "
    "When memory and the current blocks disagree, the current blocks win. In memory, "
    "facts in parentheses are true; the rest of an entry is only someone's account.\n\n"
    "[OUTCOMES] tells you exactly what happened this turn -- movement, combat, "
    "item use, talk, everything the engine already decided before you were asked to "
    "write anything. Narrate what is there. Never contradict it and never invent "
    "your own HP, inventory or combat numbers. RULES:\n"
    "- Anything marked 'Refused' did not happen; write around it. An interrupted "
    "action stops where its fact says, and what the fact says was cancelled never "
    "happens.\n"
    "- Zombies: every zombie in the prose is in [THREATS]; never invent one and never "
    "give one a number. Before the outbreak nobody on screen is one of the walking "
    "dead; rumours and news are fine.\n"
    "- Corpses: every body in the prose is in [CORPSES] and is dead until an "
    "[OUTCOMES] fact says it rises.\n"
    "- People: every person present is in [NPCS PRESENT]. Others can be remembered or "
    "mentioned, never met.\n"
    "- Items: the character holds only what [CHARACTER]'s Inventory, Equipment and "
    "Wearing say. Nothing appears in anyone's hands that those lines do not put there.\n"
    "- NPC reactions follow the reaction fact and the bands: a talk that 'seems "
    "unmoved' is not a breakthrough, and one where someone 'bristles' is not a warm "
    "moment.\n"
    "- NPC knowledge: an NPC states facts about the world only from the blocks. A "
    "topic's fact is said only when [OUTCOMES] says it was told. Opinions, feelings and "
    "small talk are yours to write.\n"
    "- If [OUTCOMES] says the character has died, narrate their death as final -- "
    "this is the end of the story, not a setback -- and write OPTIONS: NONE\n\n"
    "[QUESTS] lists what the character is currently working toward. Use it for "
    "motivation and flavor -- you may not declare a quest objective complete "
    "yourself; that only happens through [OUTCOMES].\n\n"
    "[CURRENT LOCATION]'s description is reference material, not a script to "
    "recite. The character already knows what a space looks, sounds, and smells like "
    "once they've been standing in it -- do not re-describe the room, the "
    "lighting, the air, or the ambient noise again just because the block is "
    "there. Only bring physical surroundings back into the prose when "
    "something about them has actually changed (a new arrival, an action "
    "that disturbs the space, a shift in time or weather) or when the "
    "player's own action draws attention to a specific detail. Otherwise, "
    "spend the words on what's new this turn: the outcome, the dialogue, the "
    "character beat.\n\n"
    "After EVENT, add an OPTIONS section: 2-4 short, concrete things the character "
    "could plausibly do next, each on its own line starting with '- '. These "
    "are only suggestions -- the player can always ignore them and do something "
    "else entirely, so never phrase them as the only paths forward. If "
    "nothing sensible suggests itself (the character is mid-action, or waiting on "
    "someone else mid-conversation), write NONE instead of forcing options.\n\n"
    "Your response must follow this EXACT format:\n\n"
    "STORY:\n"
    "[Write the narrative in second-person, addressing the character directly]\n\n"
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
    "The character crossed paths with a neighbor in the hallway\n\n"
    "OPTIONS:\n"
    "- Offer to help her with the groceries\n"
    "- Introduce yourself\n"
    "- Give a polite nod and keep walking"
)

SUMMARIZER_SYSTEM_PROMPT = (
    "You are a story summarizer. Condense the following events into a single, "
    "concise narrative paragraph. Facts in parentheses, such as '(Facts: ...)', are "
    "true and win over the rest of an entry; keep them and never contradict them."
)


class LLMError(RuntimeError):
    """Raised when LM Studio is unreachable or answers in an unusable shape."""


class LLMRequestRejected(LLMError):
    """The server refused the request itself (an HTTP 4xx), e.g. a `response_format` it lacks."""


def _chat(
    system_prompt: str,
    user_content: str,
    temperature: float,
    response_format: dict[str, Any] | None = None,
) -> str:
    payload: dict[str, Any] = {
        "model": MODEL_NAME,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": temperature,
    }
    if response_format is not None:
        payload["response_format"] = response_format

    try:
        response = requests.post(
            LM_STUDIO_URL,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=config.llm.request_timeout,
        )
        if response_format is not None and 400 <= response.status_code < 500:
            raise LLMRequestRejected(
                f"LM Studio refused the request with HTTP {response.status_code}."
            )
        response.raise_for_status()
        return response.json()["choices"][0]["message"]["content"]
    except requests.exceptions.RequestException as exc:
        raise LLMError(
            f"Could not reach LM Studio at {LM_STUDIO_URL}. Is it running? ({exc})"
        ) from exc
    except (KeyError, IndexError, ValueError) as exc:
        raise LLMError(f"LM Studio returned an unexpected response shape: {exc}") from exc


@dataclass
class ParserReply:
    """The parser call's raw answer and which format it is in: a JSON plan or ACTIONS: text."""

    text: str
    structured: bool


def query_parser(prompt_text: str, schema: dict[str, Any] | None = None) -> ParserReply:
    """Ask the intent parser what actions player input implies. Raises LLMError on failure.

    With a `schema` the reply is constrained to it; a server that rejects the
    request gets the text prompt once instead.
    """
    temperature = config.llm.parser_temperature
    if schema is not None:
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": "action_plan", "strict": True, "schema": schema},
        }
        try:
            raw = _chat(PARSER_JSON_SYSTEM_PROMPT, prompt_text, temperature, response_format)
        except LLMRequestRejected as exc:
            logger.warning("Structured parser output refused, using the text prompt: %s", exc)
        else:
            logger.debug("Parser raw response:\n%s", raw)
            return ParserReply(raw, structured=True)
    raw = _chat(PARSER_SYSTEM_PROMPT, prompt_text, temperature)
    logger.debug("Parser raw response:\n%s", raw)
    return ParserReply(raw, structured=False)


def parse_plan_response(llm_response_text: str) -> tuple[list[AnyAction], list[ParseFailure]]:
    """Read a structured parser reply; text that is not a plan is one failure, never an exception."""
    try:
        payload = json.loads(llm_response_text)
    except ValueError:
        return [], [ParseFailure(raw=llm_response_text.strip(), reason="The reply was not JSON.")]
    return parse_plan(payload)


def read_parser_reply(reply: ParserReply) -> tuple[list[AnyAction], list[ParseFailure]]:
    """The proposed actions and the failures in a parser reply, whichever format it is in."""
    if reply.structured:
        return parse_plan_response(reply.text)
    return parse_action_plan(parse_action_response(reply.text))


def query_narrator(prompt_text: str) -> str:
    """Ask the narrator to describe outcomes the engine already decided. Raises LLMError on failure."""
    raw = _chat(NARRATOR_SYSTEM_PROMPT, prompt_text, temperature=config.llm.narrator_temperature)
    logger.debug("Narrator raw response:\n%s", raw)
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
    `modules.action.parser.parse_action_plan` would have received anyway.
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


# A prompt block such as [OUTCOMES] echoed back into the reply; it is never prose.
_PROMPT_BLOCK_HEADER = re.compile(r"\[[A-Z][A-Z ]*\]")


def parse_narrator_response(llm_response_text: str) -> dict[str, str | list[str]]:
    """Split a STORY/EVENT/OPTIONS narrator response into its parts.

    Section headers are matched line by line rather than by splitting on
    blank lines, so a story containing blank lines survives intact. A reply
    with no headers is all story. An echoed prompt block (`[OUTCOMES]` and
    the lines under it) is dropped up to the next header. OPTIONS is
    optional: none (or NONE) yields an empty list.
    """
    sections: dict[str, list[str]] = {"story": [], "event": [], "options": []}
    headers = {"STORY:": "story", "EVENT:": "event", "OPTIONS:": "options"}
    lines = llm_response_text.splitlines()

    def header_of(stripped: str) -> str | None:
        return next((key for key in headers if stripped.upper().startswith(key)), None)

    # A reply with no headers at all is still prose; keep it as the story.
    has_headers = any(header_of(line.strip()) for line in lines)
    current: str | None = None if has_headers else "story"

    for line in lines:
        stripped = line.strip()
        if _PROMPT_BLOCK_HEADER.fullmatch(stripped):
            current = None
            continue
        matched_header = header_of(stripped)
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
    # The model sometimes punctuates "NONE" (a period, an exclamation
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
