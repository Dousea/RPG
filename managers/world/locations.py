"""Turning a place phrase from the LLM into a zone, and walking between zones.

Pure functions over the zone map: they read `Location`s and never change them.
`GameManager` wraps them with its own map and current zone.
"""

import re
from collections import deque

from data.world.locations import ZONE_EXIT_NOUNS, ZONE_KINDS
from modules.world.location import Location

# Words the model reaches for in place of a bare connection direction. Applied
# only when the mapped direction is a connection of the current zone, or
# "outside" said on the street would match the street's own alias instead of
# following the exit out.
DIRECTION_SYNONYMS = {"inside": "in", "outside": "out"}

# Direction words with no destination behind them. One that matches no
# connection is a shuffle inside the current zone, not the name of a place.
BARE_DIRECTIONS = frozenset(
    {
        "north",
        "south",
        "east",
        "west",
        "up",
        "down",
        "in",
        "out",
        "inside",
        "outside",
        "back",
        "forward",
        "left",
        "right",
        "upstairs",
        "downstairs",
        "onwards",
        "onward",
        "further",
    }
)

# Shorter names and aliases ("bar", "3b") collide with ordinary words too
# easily to be matched inside a longer phrase.
MIN_WHOLE_WORD_NAME_LENGTH = 4

_KIND_WORDS = frozenset(word for words in ZONE_KINDS.values() for word in words)
_EXIT_WORDS = r"outside(?: of)?|out of|leaving|leave|exiting|exit"
_EXIT_WORD = re.compile(rf"\b(?:{_EXIT_WORDS})\b")
WORD = re.compile(r"[a-z0-9']+")
_ARTICLES = frozenset({"the", "a", "an", "this", "that"})
_EXIT_PHRASE = re.compile(
    rf"^(?:{_EXIT_WORDS})\s+"
    r"(?:(?:the|my|your|this|orton's)\s+)?(.+)$"
)


def connection_target(
    folded: str, current: Location, locations: dict[str, Location]
) -> Location | None:
    """The zone `current` connects to in direction `folded` (casefolded),
    after `DIRECTION_SYNONYMS`, or None."""
    direction = DIRECTION_SYNONYMS.get(folded, folded)
    for name, loc_id in current.connections.items():
        if direction == name.casefold() and loc_id in locations:
            return locations[loc_id]
    return None


def resolve_location(
    phrase: str, current: Location, locations: dict[str, Location]
) -> Location | list[Location] | None:
    """Resolve a zone by connection direction, id, name, alias, exit phrase
    ("leave the building"), kind word ("the apartment") or a name inside a
    longer phrase ("back to my apartment"), in that order. None when nothing
    matches, and a list when the phrase fits several zones equally well.

    Adjacency is not checked: this says which zone a phrase means, and
    `ActionValidator._validate_move` decides whether the player gets there.
    """
    needle = phrase.strip().strip("\"'.,;:!?").casefold()
    if not needle:
        return None
    target = connection_target(needle, current, locations) or _match_exact(needle, locations)
    if target is not None:
        return target
    exit_match = _EXIT_PHRASE.match(needle)
    if exit_match:
        words = WORD.findall(exit_match.group(1))
        named = _exit_noun_prefix(words)
        if named is not None:
            return _walk_out(named, words, current, locations)
    return _match_kind(needle, current, locations) or _match_whole_words(needle, locations)


def resolve_zone_exact(phrase: str, locations: dict[str, Location]) -> Location | None:
    """Resolve a zone by id, name or alias only.

    For NPC placement: an NPC has no free-text spot to fall back on, so the
    forgiving matching `resolve_location` does for the player would scatter
    NPCs into zones nobody meant.
    """
    needle = phrase.strip().strip("\"'.,;:").casefold()
    if not needle:
        return None
    return _match_exact(needle, locations)


def zone_path(locations: dict[str, Location], start_id: str, target_id: str) -> list[str] | None:
    """The shortest hop list from `start_id` to `target_id`, excluding the
    start, or None when they are not connected.

    Callers walk it one connection at a time so a locked door on the way
    stops them.
    """
    if start_id == target_id:
        return []
    visited = {start_id}
    queue: deque[tuple[str, list[str]]] = deque([(start_id, [])])
    while queue:
        current_id, path = queue.popleft()
        location = locations.get(current_id)
        if location is None:
            continue
        for loc_id in location.connections.values():
            if loc_id in visited:
                continue
            new_path = path + [loc_id]
            if loc_id == target_id:
                return new_path
            visited.add(loc_id)
            queue.append((loc_id, new_path))
    return None


def _match_exact(needle: str, locations: dict[str, Location]) -> Location | None:
    for loc_id, location in locations.items():
        if needle in (loc_id.casefold(), location.name.casefold()):
            return location
        if any(needle == alias.casefold() for alias in location.aliases):
            return location
    return None


def _walk_out(
    named: tuple[str, int], words: list[str], current: Location, locations: dict[str, Location]
) -> Location | list[Location] | None:
    """Where an exit phrase whose object starts with a zone's exit noun goes.

    Only the current zone's noun walks out of it; "outside the bus stop" names
    no zone and lands on the landmark through the whole-word match instead.
    An exit phrase naming another zone can't be walked out of from here, so
    whatever follows its noun decides, and nothing following means nowhere.
    """
    zone_id, noun_length = named
    if zone_id == current.id:
        out_id = current.connections.get("out")
        if out_id is not None and out_id in locations:
            return locations[out_id]
        return current
    remainder = " ".join(words[noun_length:])
    return resolve_location(remainder, current, locations) if remainder else None


def _exit_noun_prefix(words: list[str]) -> tuple[str, int] | None:
    """The zone whose exit noun starts `words`, and that noun's word count.

    The longest noun wins, so "apartment building" is the building rather
    than "apartment" (home) followed by a stray word.
    """
    best: tuple[str, int] | None = None
    for zone_id, nouns in ZONE_EXIT_NOUNS.items():
        for noun in nouns:
            noun_words = noun.split()
            if words[: len(noun_words)] == noun_words and (
                best is None or len(noun_words) > best[1]
            ):
                best = (zone_id, len(noun_words))
    return best


def kind_word(needle: str) -> str:
    """`needle` without its leading articles: the word that may name a kind of place."""
    words = WORD.findall(needle)
    while words and words[0] in _ARTICLES:
        words = words[1:]
    return " ".join(words)


def kind_choice(
    text: str, target: Location, current: Location, locations: dict[str, Location]
) -> list[Location] | None:
    """The zones the player's `text` leaves open when the parser wrote the one zone `target`, or None.

    Open means `text` holds a kind word ("the apartment") that fits several zones
    `current` reaches, `target` among them, and nothing in `text` names `target`:
    its name, an alias, an exit phrase or a connection direction.
    """
    words = _words(text.casefold())
    if _names_zone(text.casefold(), words, target, current):
        return None
    for word in words:
        if word not in _KIND_WORDS:
            continue
        zones = _match_kind(word, current, locations)
        if isinstance(zones, list) and target in zones:
            return zones
    return None


def _names_zone(text: str, words: list[str], target: Location, current: Location) -> bool:
    if _EXIT_WORD.search(text):
        return True

    directed = [DIRECTION_SYNONYMS.get(word, word) for word in words]
    for name, loc_id in current.connections.items():
        if (
            loc_id == target.id
            and _first_contiguous_match(directed, _words(name.casefold())) is not None
        ):
            return True

    for candidate in (target.name, *target.aliases):
        named = _words(candidate.casefold())
        if named[:1] == ["the"]:
            named = named[1:]
        if named and _first_contiguous_match(words, named) is not None:
            return True
    return False


def _match_kind(
    needle: str, current: Location, locations: dict[str, Location]
) -> Location | list[Location] | None:
    """The zones of the kind `needle` names ("the apartment") that `zone_path` reaches from `current`, the current zone included."""
    kind = kind_word(needle)
    zones = [
        zone
        for zone in locations.values()
        if kind in zone.kinds and zone_path(locations, current.id, zone.id) is not None
    ]
    if not zones:
        return None
    return zones[0] if len(zones) == 1 else zones


def _match_whole_words(
    needle: str, locations: dict[str, Location]
) -> Location | list[Location] | None:
    """The zone whose name or alias appears earliest in `needle` as a run of
    whole words; ties go to the longer name, and zones still tied are all
    returned for the player to choose from.

    Earliest wins because the head of the phrase is the destination: "the
    street outside my apartment" is the street. A leading "the" on a name
    is ignored, or every name starting with "the" would match at word 0.
    """
    phrase_words = _words(needle)
    best: tuple[int, int] | None = None
    tied: list[Location] = []

    for location in locations.values():
        for candidate in (location.name, *location.aliases):
            folded = candidate.casefold()
            if len(folded) < MIN_WHOLE_WORD_NAME_LENGTH:
                continue

            candidate_words = _words(folded)
            if candidate_words[:1] == ["the"]:
                candidate_words = candidate_words[1:]
            if not candidate_words:
                continue

            position = _first_contiguous_match(phrase_words, candidate_words)
            if position is None:
                continue

            score = (position, -len(candidate_words))
            if best is None or score < best:
                best, tied = score, [location]
            elif score == best and location not in tied:
                tied.append(location)

    if not tied:
        return None

    return tied[0] if len(tied) == 1 else tied


def _words(text: str) -> list[str]:
    """`text`'s words with any trailing possessive 's removed."""
    return [word.removesuffix("'s") for word in WORD.findall(text)]


def _first_contiguous_match(haystack: list[str], needle: list[str]) -> int | None:
    span = len(needle)
    for start in range(len(haystack) - span + 1):
        if haystack[start : start + span] == needle:
            return start
    return None
