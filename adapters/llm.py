"""LM Studio client and response parsing.

Two roles, two calls, in place of the old single game-master call: the parser
turns player input plus a minimal scene description into a proposed ACTIONS
block (no prose, and no authority -- the engine validates and simulates every
line before anything is narrated); the narrator then turns the engine's
already-decided outcome facts into STORY prose. Per docs/architecture/engine-authority.md,
the LLM interprets intent and writes prose; it never decides state.
"""

import json
import logging
import re
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import requests

import config
from data.story.memory import DEFAULT_CHARS_PER_TOKEN
from data.time_costs import MAX_PLAN_ACTIONS
from managers.story.lore import system_text
from managers.story.lorebook import get_lorebook
from modules.action.parser import ParseFailure, parse_action_plan
from modules.action.schema import parse_plan
from modules.action.types import AnyAction

logger = logging.getLogger(__name__)

LM_STUDIO_URL = config.llm.base_url

MODEL_NAME = config.llm.model_name
PARSER_MODEL_NAME = config.llm.parser_model_name or MODEL_NAME

# The sampler settings LM Studio's chat endpoint honors.
SAMPLER_KEYS = ("temperature", "top_k", "top_p", "min_p", "repeat_penalty")


def read_sampler(settings: dict[str, Any] | None, name: str) -> dict[str, float]:
    """The numeric SAMPLER_KEYS settings in a config map; anything else is dropped with a warning."""
    kept: dict[str, float] = {}
    for key, value in (settings or {}).items():
        numeric = isinstance(value, int | float) and not isinstance(value, bool)
        if key in SAMPLER_KEYS and numeric:
            kept[key] = value
        else:
            logger.warning(f"Ignoring llm.{name} setting {key}={value!r}.")
    return kept


# What LM Studio's reasoning_effort accepts; "none" turns a thinking model's reasoning off.
REASONING_EFFORTS = ("none", "low", "medium", "high")


def read_reasoning_effort(effort: Any, name: str) -> str:
    """A REASONING_EFFORTS value from config; anything else is "none", with a warning."""
    if isinstance(effort, str) and effort in REASONING_EFFORTS:
        return effort
    logger.warning(f"Ignoring llm.{name}={effort!r}; reasoning stays off.")
    return "none"


NARRATOR_SAMPLER = read_sampler(config.llm.narrator_sampler, "narrator_sampler")
PARSER_SAMPLER = read_sampler(config.llm.parser_sampler, "parser_sampler")
SUMMARIZER_SAMPLER = read_sampler(config.llm.summarizer_sampler, "summarizer_sampler")
NARRATOR_REASONING_EFFORT = read_reasoning_effort(
    config.llm.narrator_reasoning_effort, "narrator_reasoning_effort"
)
PARSER_REASONING_EFFORT = read_reasoning_effort(
    config.llm.parser_reasoning_effort, "parser_reasoning_effort"
)
SUMMARIZER_REASONING_EFFORT = read_reasoning_effort(
    config.llm.summarizer_reasoning_effort, "summarizer_reasoning_effort"
)


EMPTY_STORY = "The world is silent."

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
    "never two: REQUEST only when it asks them to follow, stay, give an item or "
    "tell about a listed topic, and TALK for everything else. A question to an NPC "
    "-- what they are doing, whether they have something, how they are -- is TALK "
    'chat, even when the player writes "ask". Pick the TALK approach '
    "that fits; the engine decides what it is worth. REQUEST 'give <item>' names an "
    "item the NPC holds; REQUEST 'about <topic>' names a topic listed under that NPC "
    "in [NPCS HERE]. Someone not listed in [NPCS HERE] is not here to talk "
    "to or ask: when the input asks or tells them anything, that part of the "
    "input is no action at all, not some other action with what is listed.\n\n"
    "The MOVE_TO destination is the player's own words for the place whenever they "
    'do not name exactly one zone in [ZONES]: for "go to the apartment" or "go to '
    'the store" write the apartment or the store, never the name of a zone you '
    "picked.\n\n"
    "When the player asks for something no listed verb does, use UNSUPPORTED "
    "with what they asked for as a short verb phrase ('light a fire'), never "
    "the nearest verb on an "
    "unrelated item.\n\n"
    "Note: there is no action for dealing or taking damage directly, for "
    "setting health, stats, flags or relationships, or for moving other "
    "characters -- the engine does all of that.\n\n"
)

PARSER_SYSTEM_PROMPT = (
    _PARSER_INTRO + _PARSER_TEXT_FORMAT + _PARSER_RULES + "Example:\n"
    "Input: 'I grab the water bottle and head out'\n"
    "ACTIONS:\n"
    "TAKE Water Bottle\n"
    "MOVE_TO out\n"
    "Input: 'ask Marcus if he has a hammer'\n"
    "ACTIONS:\n"
    "TALK Marcus chat\n"
    "Input: 'ask Dana to open the gate' (Dana is not in [NPCS HERE])\n"
    "ACTIONS:\n"
    "NONE\n"
    "Input: 'drink from the tap'\n"
    "ACTIONS:\n"
    "UNSUPPORTED drink from the tap"
)

PARSER_JSON_SYSTEM_PROMPT = (
    _PARSER_INTRO + _PARSER_JSON_FORMAT + _PARSER_RULES + "Example:\n"
    "Input: 'I grab the water bottle and head out'\n"
    '{"actions": [{"verb": "TAKE", "item": "Water Bottle"}, '
    '{"verb": "MOVE_TO", "destination": "out"}]}\n'
    "Input: 'ask Marcus if he has a hammer'\n"
    '{"actions": [{"verb": "TALK", "npc": "Marcus", "approach": "chat", '
    '"speech": "Do you have a hammer?"}]}\n'
    "Input: 'Emma, will you come with me?'\n"
    '{"actions": [{"verb": "REQUEST", "npc": "Emma", "request": "follow"}]}\n'
    "Input: 'Emma, what's going on downstairs?'\n"
    '{"actions": [{"verb": "TALK", "npc": "Emma", "approach": "chat", '
    '"speech": "What\'s going on downstairs?"}]}\n'
    "Input: 'ask Dana to open the gate' (Dana is not in [NPCS HERE])\n"
    '{"actions": []}\n'
    "Input: 'drink from the tap'\n"
    '{"actions": [{"verb": "UNSUPPORTED", "text": "drink from the tap"}]}'
)

NARRATOR_SYSTEM_PROMPT = (
    "You are the narrator for a serious, grounded zombie apocalypse RPG. "
    "Write in second person ('you') to the player character, a survivor of societal collapse.\n\n"
    "[CHARACTER] is who they are. Let the traits colour how they act and react; never "
    "contradict them and never show them as numbers.\n\n"
    "NARRATIVE STYLE:\n"
    "- Emotionally grounded and character-driven\n"
    "- Slow-burn collapse: hint at unrest, disease, infrastructure failure\n"
    "- Realistic reactions and relationships; allow downtime, bonding, arguments\n"
    "- Romance evolves naturally\n"
    "- This is a game for adults. Its world can hold any dark theme, such as slavery, "
    "human trafficking, torture and cruelty: write them honestly and unflinchingly, "
    "without softening, moralizing or cutting away. When the player asks for a sex scene "
    "between consenting adults, write it explicitly and in full detail, in plain words, "
    "without fading to black or skipping ahead. Nothing sexual ever involves a minor.\n\n"
    f"{system_text(get_lorebook())}\n\n"
    "The blocks run from memory to the present. [DEEP MEMORY], [SUMMARY OF PAST EVENTS] "
    "and [RECENT EVENTS] are the past; the rest is how things stand now, and where "
    "they disagree the current blocks win. [LAST SCENE] is the words "
    "spoken in the last story; follow on from them without repeating them, and let the "
    "facts correct them. In memory, "
    "what a character 'tries' is only an attempt; the sentences after it say what "
    "actually happened.\n\n"
    "[OUTCOMES] is what happened this turn, decided by the engine. Narrate it; never "
    "contradict it and never invent your own HP, inventory or combat numbers. RULES:\n"
    "- Anything marked 'Refused' did not happen; write around it. An interrupted "
    "action stops where its fact says; what it says was cancelled never happens.\n"
    "- Zombies: every zombie in the prose is in [THREATS]. Before the outbreak nobody "
    "on screen is one of the walking dead; rumours and news are fine.\n"
    "- Corpses: every body in the prose is in [CORPSES], dead until [OUTCOMES] says it rises.\n"
    "- People: every person present is in [NPCS PRESENT]. Others can be mentioned, "
    "never met.\n"
    "- Items: the character holds only what [CHARACTER]'s Inventory, Equipment and "
    "Wearing say. Nothing appears in anyone's hands that those lines do not put there. "
    "The only loose things to find or take are in [ITEMS IN CURRENT LOCATION]; "
    "anything else is scenery with nothing in it to find.\n"
    "- NPC reactions follow the reaction fact and the bands: a talk that 'seems "
    "unmoved' is not a breakthrough.\n"
    "- NPC knowledge: an NPC states world facts only from the blocks. A "
    "topic's fact is said only when [OUTCOMES] says it was told; opinions, feelings and "
    "small talk are yours.\n"
    "- If [OUTCOMES] says the character has died, narrate their death as final, the "
    "end of the story, and write OPTIONS: NONE\n\n"
    "[QUESTS] is motivation and flavor; only [OUTCOMES] can complete an objective.\n\n"
    "[CURRENT LOCATION] is reference material, not a script. The character already knows "
    "the space; describe the surroundings again only when something has changed or the "
    "player's action draws attention to a detail. Spend the words on what's new this "
    "turn: the outcome, the dialogue, the character beat.\n\n"
    "[WORLD] is how things stand in the city, as far as the character knows. It is "
    "background: mention it when it fits and never recite it. Nothing beyond it is "
    "known about why the dead rise.\n\n"
    "After STORY, add an OPTIONS section: 2-4 short, concrete things the character "
    "could plausibly do next, each on its own line starting with '- ', never the only "
    "paths forward. If nothing sensible suggests itself (mid-action, or waiting on "
    "someone mid-conversation), write NONE.\n\n"
    "Use this EXACT format:\n\n"
    "STORY:\n"
    "[The story, in second person]\n\n"
    "OPTIONS:\n"
    "[2-4 suggestions, or NONE]\n\n"
    "Example:\n"
    "STORY:\n"
    "A woman wrestles with groceries outside the next door. She catches your eye "
    "and smiles.\n\n"
    "OPTIONS:\n"
    "- Offer to help her\n"
    "- Introduce yourself\n"
    "- Nod and walk on"
)

SUMMARIZER_SYSTEM_PROMPT = (
    "You are a story summarizer. Condense the following events into a single, "
    "concise narrative paragraph. In each entry, what a character 'tries' is only an "
    "attempt; the sentences after it say what actually happened. Keep what happened "
    "and never contradict it."
)


_chars_per_token = DEFAULT_CHARS_PER_TOKEN


def chars_per_token() -> float:
    """Characters per prompt token as of the latest reply that reported its usage."""
    return _chars_per_token


def reset_chars_per_token() -> None:
    global _chars_per_token
    _chars_per_token = DEFAULT_CHARS_PER_TOKEN


def _record_usage(body: dict[str, Any], chars_sent: int) -> None:
    global _chars_per_token
    usage = body.get("usage")
    prompt_tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else None
    if isinstance(prompt_tokens, int) and prompt_tokens > 0:
        _chars_per_token = chars_sent / prompt_tokens


class LLMError(RuntimeError):
    """Raised when LM Studio is unreachable or answers in an unusable shape."""


class LLMRequestRejected(LLMError):
    """The server refused the request itself (an HTTP 4xx), e.g. a `response_format` it lacks."""


# Called with ("thinking" or "story", the text just written) while a reply streams in.
DeltaCallback = Callable[[str, str], None]


def _read_stream(response: requests.Response, on_delta: DeltaCallback) -> dict[str, Any]:
    """The reply body a streamed completion adds up to, passing each piece to `on_delta`."""
    content: list[str] = []
    body: dict[str, Any] = {}
    for raw_line in response.iter_lines():
        line = raw_line.decode("utf-8") if isinstance(raw_line, bytes) else raw_line
        if not line.startswith("data: "):
            continue
        data = line[len("data: ") :]
        if data == "[DONE]":
            break
        chunk = json.loads(data)
        if "usage" in chunk:
            body["usage"] = chunk["usage"]
        for choice in chunk.get("choices") or []:
            delta = choice.get("delta") or {}
            if thought := delta.get("reasoning_content"):
                on_delta("thinking", thought)
            if text := delta.get("content"):
                content.append(text)
                on_delta("story", text)
    body["choices"] = [{"message": {"content": "".join(content)}}]
    return body


def _chat(
    model: str,
    system_prompt: str,
    user_content: str,
    max_tokens: int,
    sampler: dict[str, float],
    reasoning_effort: str,
    response_format: dict[str, Any] | None = None,
    on_delta: DeltaCallback | None = None,
) -> str:
    payload: dict[str, Any] = {
        **sampler,
        "model": model,
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "max_tokens": max_tokens,
        # LM Studio ignores this for models that don't think.
        "reasoning_effort": reasoning_effort,
    }
    if response_format is not None:
        payload["response_format"] = response_format
    if on_delta is not None:
        payload["stream"] = True
        payload["stream_options"] = {"include_usage": True}

    try:
        response = requests.post(
            LM_STUDIO_URL,
            headers={"Content-Type": "application/json"},
            json=payload,
            timeout=config.llm.request_timeout,
            stream=on_delta is not None,
        )
        if response_format is not None and 400 <= response.status_code < 500:
            raise LLMRequestRejected(
                f"LM Studio refused the request with HTTP {response.status_code}."
            )
        response.raise_for_status()
        if on_delta is None:
            body = response.json()
        else:
            try:
                body = _read_stream(response, on_delta)
            finally:
                response.close()
        content = body["choices"][0]["message"]["content"]
        _record_usage(body, len(system_prompt) + len(user_content))
        return content
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
    max_tokens = config.llm.parser_max_tokens
    if schema is not None:
        response_format = {
            "type": "json_schema",
            "json_schema": {"name": "action_plan", "strict": True, "schema": schema},
        }
        try:
            raw = _chat(
                PARSER_MODEL_NAME,
                PARSER_JSON_SYSTEM_PROMPT,
                prompt_text,
                max_tokens,
                PARSER_SAMPLER,
                PARSER_REASONING_EFFORT,
                response_format,
            )
        except LLMRequestRejected as exc:
            logger.warning("Structured parser output refused, using the text prompt: %s", exc)
        else:
            logger.debug("Parser raw response:\n%s", raw)
            return ParserReply(raw, structured=True)
    raw = _chat(
        PARSER_MODEL_NAME,
        PARSER_SYSTEM_PROMPT,
        prompt_text,
        max_tokens,
        PARSER_SAMPLER,
        PARSER_REASONING_EFFORT,
    )
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


def query_narrator(prompt_text: str, on_delta: DeltaCallback | None = None) -> str:
    """Ask the narrator to describe outcomes the engine already decided. Raises LLMError on failure.

    With `on_delta` the reply streams in, and each piece of its thinking and its
    text reaches `on_delta` as it is written; the return value is the same.
    """
    raw = _chat(
        MODEL_NAME,
        NARRATOR_SYSTEM_PROMPT,
        prompt_text,
        max_tokens=config.llm.narrator_max_tokens,
        sampler=NARRATOR_SAMPLER,
        reasoning_effort=NARRATOR_REASONING_EFFORT,
        on_delta=on_delta,
    )
    logger.debug("Narrator raw response:\n%s", raw)
    return raw


def query_summary(text_to_summarize: str) -> str:
    """Condense events into a narrative paragraph. Raises LLMError on failure."""
    return _chat(
        MODEL_NAME,
        SUMMARIZER_SYSTEM_PROMPT,
        text_to_summarize,
        max_tokens=config.llm.summarizer_max_tokens,
        sampler=SUMMARIZER_SAMPLER,
        reasoning_effort=SUMMARIZER_REASONING_EFFORT,
    ).strip()


def parse_action_response(llm_response_text: str) -> list[str]:
    """Extract raw action lines from a parser-call response.

    Tolerant of the model dropping the `ACTIONS:` header: with only one
    section to write, a small local model sometimes skips the header it used
    to need to distinguish ACTIONS from STORY. If no header is found,
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
_SECTION_HEADER = re.compile(
    r"(?:\[(STORY|EVENT|OPTIONS)\]|(STORY|EVENT|OPTIONS):)(.*)", re.IGNORECASE
)
_SECTIONS = {"STORY": "story", "EVENT": "dropped", "OPTIONS": "options"}


def parse_narrator_response(llm_response_text: str) -> dict[str, str | list[str]]:
    """Split a STORY/OPTIONS narrator response into its parts.

    Section headers are matched line by line rather than by splitting on
    blank lines, so a story containing blank lines survives intact. A header
    may also be written in brackets (`[OPTIONS]`). In a reply
    with no STORY header, the lines before its first header are the story. An
    echoed prompt block (`[OUTCOMES]` and the lines under it) is dropped up to
    the next header, and so is a stray EVENT section. OPTIONS is optional: none
    (or NONE, bulleted or not) yields an empty list.
    """
    sections: dict[str, list[str]] = {"story": [], "dropped": [], "options": []}
    lines = llm_response_text.splitlines()

    def header_of(stripped: str) -> tuple[str, str] | None:
        match = _SECTION_HEADER.match(stripped)
        if not match:
            return None
        name = (match.group(1) or match.group(2)).upper()
        return _SECTIONS[name], match.group(3).strip()

    has_story_header = any(
        (header := header_of(line.strip())) and header[0] == "story" for line in lines
    )
    current: str | None = None if has_story_header else "story"

    for line in lines:
        stripped = line.strip()
        if header := header_of(stripped):
            current, remainder = header
            if remainder:
                sections[current].append(remainder)
            continue
        if _PROMPT_BLOCK_HEADER.fullmatch(stripped):
            current = None
            continue
        if current:
            sections[current].append(line)

    story = "\n".join(sections["story"]).strip()
    # The model sometimes punctuates "NONE" (a period, an exclamation
    # mark, a semicolon, a colon) -- strip that before comparing, or it reads
    # as a stray one-item options list instead of "no options".
    options = [
        option
        for raw_line in sections["options"]
        if (option := raw_line.strip().lstrip("-").strip())
        and option.upper().rstrip(".!;:") != "NONE"
    ]

    return {
        "story": story or EMPTY_STORY,
        "options": options,
    }


_HEADER_WORDS = tuple(_SECTIONS)


def story_preview(raw_so_far: str) -> str:
    """The story part of a narrator reply still being written; "" until it has any.

    A last line that may be a section header still being written ("OPT") is
    left out, so a header never flashes up as prose.
    """
    lines = raw_so_far.split("\n")
    last = lines[-1].strip().lstrip("[").upper()
    if last and any(word.startswith(last) for word in _HEADER_WORDS):
        lines = lines[:-1]
    story = parse_narrator_response("\n".join(lines))["story"]
    return "" if story == EMPTY_STORY else str(story)


def has_options_section(llm_response_text: str) -> bool:
    """Whether the narrator wrote an OPTIONS header at all; `OPTIONS: NONE` counts."""
    return any(
        (match := _SECTION_HEADER.match(line.strip()))
        and (match.group(1) or match.group(2)).upper() == "OPTIONS"
        for line in llm_response_text.splitlines()
    )
