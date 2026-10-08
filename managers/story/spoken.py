"""The lines spoken in a story, each with the speaker its sentence names."""

import re
from collections.abc import Iterable
from dataclasses import dataclass

_QUOTE = re.compile(r"\"([^\"]+)\"|“([^”]+)”")
_SENTENCE_END = re.compile(r"[.!?\n]")


@dataclass(frozen=True)
class SpokenLine:
    speaker: str | None
    text: str


def _sentence_before(narration: str) -> str:
    """The unfinished sentence at the end of the narration before a quote."""
    ends = list(_SENTENCE_END.finditer(narration))
    return narration[ends[-1].end() :] if ends else narration


def _sentence_after(narration: str) -> str:
    """The first sentence of the narration after a quote."""
    end = _SENTENCE_END.search(narration)
    return narration[: end.start()] if end else narration


def _named(sentence: str, npc_names: Iterable[str], player_name: str) -> str | None:
    """The first speaker the sentence names; "you" is the character, as in "You ask Emma"."""
    forms = [(form, name) for name in npc_names for form in {name, name.split()[0]}]
    best: tuple[int, str] | None = None
    for form, name in [*forms, ("you", player_name)]:
        found = re.search(
            rf"\b{re.escape(form)}\b", sentence, re.IGNORECASE if form == "you" else 0
        )
        if found and (best is None or found.start() < best[0]):
            best = (found.start(), name)
    return best[1] if best else None


def _speaker(before: str, after: str, npc_names: list[str], player_name: str) -> str | None:
    """A name in the sentence before the quote wins over one in the sentence after it."""
    for sentence in (before, after):
        name = _named(sentence, npc_names, player_name)
        if name:
            return name
    return None


def spoken_lines(story: str, npc_names: Iterable[str], player_name: str) -> list[SpokenLine]:
    """Every double-quoted line of the story in order; the second person is the character."""
    names = list(npc_names)
    matches = list(_QUOTE.finditer(story))
    lines: list[SpokenLine] = []
    for index, match in enumerate(matches):
        text = (match.group(1) or match.group(2)).strip()
        before_start = matches[index - 1].end() if index else 0
        after_end = matches[index + 1].start() if index + 1 < len(matches) else len(story)
        before = _sentence_before(story[before_start : match.start()])
        after = _sentence_after(story[match.end() : after_end])
        lines.append(SpokenLine(_speaker(before, after, names, player_name), text))
    return lines
