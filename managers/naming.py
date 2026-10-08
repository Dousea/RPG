"""Naming an item: the lookup by name, id or describing words, and the labels that tell items apart (carrying-and-loot)."""

import re
from collections.abc import Collection, Iterable

from data.items import DESCRIBING_WORDS, item_condition_word, wetness_word
from data.loot import containers as container_k
from modules.entity.item import ItemEntity

BRACKETED_WORD = re.compile(r"(.+?)\s*\(([^()]+)\)")

_WORDS_LONGEST_FIRST = sorted(DESCRIBING_WORDS, key=len, reverse=True)


def clean_name(name: str) -> str:
    """A name as the model writes it: no quotes or trailing marks, no leading article."""
    needle = name.strip().strip("\"'.,;:").casefold()
    for article in ("the ", "my ", "your "):
        needle = needle.removeprefix(article)
    return needle.strip()


def describing_words(entity: ItemEntity) -> tuple[str, ...]:
    """What sets an item apart, in words: its condition, then its wetness when it has one.

    Never a number, so uses left do not count; two items "look the same" when these are equal.
    """
    wet = wetness_word(entity.wetness)
    condition = item_condition_word(entity)
    return (condition, wet) if wet else (condition,)


def _matching(entities: Iterable[ItemEntity], needle: str) -> list[ItemEntity]:
    return [
        entity
        for entity in entities
        if needle in (entity.item.name.casefold(), entity.item.id.casefold())
    ]


def _leading_words(text: str) -> tuple[tuple[str, ...], str]:
    """The describing words at the start of `text` (commas allowed between), and what is left."""
    rest = text.replace(",", " ").strip()
    words: list[str] = []
    while True:
        word = next(
            (w for w in _WORDS_LONGEST_FIRST if rest == w or rest.startswith(f"{w} ")), None
        )
        if word is None:
            return tuple(words), rest
        words.append(word)
        rest = rest.removeprefix(word).strip()


def _qualified(needle: str) -> tuple[tuple[str, ...], str] | None:
    """A name split into its describing words and the bare name; words before it or in brackets after."""
    bracketed = BRACKETED_WORD.fullmatch(needle)
    if bracketed is not None:
        words, rest = _leading_words(bracketed[2])
        return (words, bracketed[1].strip()) if words and not rest else None
    words, rest = _leading_words(needle)
    return (words, rest) if words and rest else None


def _distinct_looks(entities: Iterable[ItemEntity]) -> dict[tuple[str, ...], ItemEntity]:
    looks: dict[tuple[str, ...], ItemEntity] = {}
    for entity in entities:
        looks.setdefault(describing_words(entity), entity)
    return looks


def differing_names(entities: Iterable[ItemEntity]) -> set[str]:
    """Names (as shown) held by items that don't all look the same."""
    by_name: dict[str, list[ItemEntity]] = {}
    for entity in entities:
        by_name.setdefault(entity.item.name, []).append(entity)
    return {name for name, held in by_name.items() if len(_distinct_looks(held)) > 1}


def find_named(entities: Iterable[ItemEntity], name: str) -> ItemEntity | list[ItemEntity] | None:
    """The entity `name` points at, ignoring case and a leading article.

    A name is an item's name or id, alone or with describing words before it or in brackets
    after it; only items with all of them match, and of those the ones with the fewest describing
    words are kept. Several matches that look the same give the first; ones that differ give the
    list. None when nothing matches.
    """
    pool = list(entities)
    needle = clean_name(name)
    matches = _matching(pool, needle)
    if not matches:
        split = _qualified(needle)
        if split is None:
            return None
        words, bare = split
        matches = [
            e for e in _matching(pool, bare) if all(word in describing_words(e) for word in words)
        ]
        if matches:
            fewest = min(len(describing_words(e)) for e in matches)
            matches = [e for e in matches if len(describing_words(e)) == fewest]
    if not matches:
        return None
    if len(_distinct_looks(matches)) > 1:
        return matches
    return matches[0]


def first_named(entities: Iterable[ItemEntity], name: str) -> ItemEntity | None:
    """The first entity `name` points at, for callers that only describe it."""
    found = find_named(entities, name)
    return found[0] if isinstance(found, list) else found


def _labels(looks: Collection[tuple[str, ...]]) -> dict[tuple[str, ...], str]:
    """One word per look that no other look has, else all the look's words."""
    labels: dict[tuple[str, ...], str] = {}
    for look in looks:
        others = {word for other in looks if other != look for word in other}
        labels[look] = next((word for word in look if word not in others), " ".join(look))
    return labels


def qualified_names(entities: Iterable[ItemEntity]) -> list[str]:
    """Each distinct look of `entities` once, as a qualified name ("broken Baseball Bat")."""
    looks = _distinct_looks(entities)
    labels = _labels(list(looks))
    return [f"{labels[look]} {entity.item.name}" for look, entity in looks.items()]


def which_one(candidates: Iterable[ItemEntity]) -> str:
    """The question for several candidates that look different (carrying-and-loot)."""
    return container_k.WHICH_ONE.format(choices=" or ".join(qualified_names(candidates)))


def scene_names(entities: Iterable[ItemEntity]) -> tuple[str, ...]:
    """Distinct names for a scene choice list: a name held by items that differ is also offered qualified."""
    by_name: dict[str, list[ItemEntity]] = {}
    for entity in entities:
        by_name.setdefault(entity.item.name, []).append(entity)
    names: list[str] = []
    for name, held in by_name.items():
        names.append(name)
        if len(_distinct_looks(held)) > 1:
            names.extend(qualified_names(held))
    return tuple(dict.fromkeys(names))


def tagged_name(entity: ItemEntity, ambiguous: Collection[str]) -> str:
    """The item's name, with its describing words in brackets when its name is one in `ambiguous`."""
    if entity.item.name not in ambiguous:
        return entity.item.name
    return f"{entity.item.name} ({', '.join(describing_words(entity))})"
