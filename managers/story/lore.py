"""Choosing the lore a turn's narrator prompt carries (world-lore: Selection and the cap)."""

import logging
import re
from dataclasses import dataclass, replace
from typing import Literal

from data.story import lore as lore_k
from managers.game import GameManager
from managers.story.beats import holds
from managers.story.lorebook import (
    NPC_KEY_PREFIX,
    ZONE_KEY_PREFIX,
    Lorebook,
    get_lorebook,
)
from modules.story.lore import LoreEntry

logger = logging.getLogger(__name__)

LoreReason = Literal["constant", "key", "sticky", "semantic"]


@dataclass(frozen=True)
class LoreHit:
    """An entry that triggered this turn; `score` is 0.0 unless `semantic`, `shown` false once the cap drops it."""

    entry: LoreEntry
    reason: LoreReason
    score: float = 0.0
    shown: bool = True


def _known(entry: LoreEntry, manager: GameManager) -> bool:
    return entry.when is None or holds(entry.when, manager)


def _replaced(entry: LoreEntry, book: Lorebook, manager: GameManager) -> bool:
    if entry.replaced_by is None:
        return False
    return _known(book.entries[entry.replaced_by], manager)


def _key_matches(key: str, manager: GameManager, player_input: str) -> bool:
    place = manager.player.current_location_id
    if key.startswith(ZONE_KEY_PREFIX):
        return key == place
    if key.startswith(NPC_KEY_PREFIX):
        return any(npc.npc_id == key for npc in manager.npcs_in_location(place))
    return re.search(rf"(?<!\w){re.escape(key)}(?!\w)", player_input, re.IGNORECASE) is not None


def _trigger(entry: LoreEntry, manager: GameManager, player_input: str) -> LoreReason | None:
    if entry.constant:
        return "constant"
    if any(_key_matches(key, manager, player_input) for key in entry.keys):
        return "key"
    return None


def _sticky_active(entry: LoreEntry, manager: GameManager) -> bool:
    return bool(entry.keys) and manager.narrative.lore_sticky.get(entry.entry_id, 0) > 0


def drop_order(hits: list[LoreHit]) -> list[LoreHit]:
    """The shown hits in the order the cap and the prompt budget drop them.

    Semantic hits first, worst score first, then the highest `order`; ties by `entry_id`
    descending. The stage entry is never in it.
    """
    droppable = [hit for hit in hits if hit.shown and not hit.entry.stage]
    by_id_desc = sorted(droppable, key=lambda hit: hit.entry.entry_id, reverse=True)
    semantic = sorted(
        (hit for hit in by_id_desc if hit.reason == "semantic"), key=lambda hit: hit.score
    )
    others = sorted(
        (hit for hit in by_id_desc if hit.reason != "semantic"),
        key=lambda hit: hit.entry.order,
        reverse=True,
    )
    return [*semantic, *others]


def world_lines(hits: list[LoreHit]) -> list[str]:
    """The `content` of the shown hits, stage line first (`order`, then `entry_id`)."""
    shown = [hit.entry for hit in hits if hit.shown]
    return [entry.content for entry in sorted(shown, key=lambda e: (e.order, e.entry_id))]


def select_lore(manager: GameManager, player_input: str, scores: dict[str, float]) -> list[LoreHit]:
    """Every `world` entry that triggered this turn, with the cap applied; changes nothing.

    `scores` is for the semantic step, which is not built yet. A keyed entry with turns left
    in `lore_sticky` is a `sticky` hit.
    """
    book = get_lorebook()
    entries = sorted(book.world_entries(), key=lambda e: (e.order, e.entry_id))

    hits: list[LoreHit] = []
    for entry in entries:
        if not _known(entry, manager) or _replaced(entry, book, manager):
            continue
        reason = _trigger(entry, manager, player_input)
        if reason is None and _sticky_active(entry, manager):
            reason = "sticky"
        if reason is not None:
            hits.append(LoreHit(entry, reason))

    hits = _capped(hits)
    for hit in hits:
        logger.debug("Lore %s %s (shown: %s)", hit.entry.entry_id, hit.reason, hit.shown)

    return hits


def record_turn(manager: GameManager, hits: list[LoreHit]) -> None:
    """Count the sticky stays once for a turn: restart the triggered, age the rest, drop the gone."""
    book = get_lorebook()
    state = manager.narrative.lore_sticky

    triggered = {
        hit.entry.entry_id: hit.entry.sticky
        for hit in hits
        if hit.reason in ("key", "semantic") and hit.entry.sticky
    }
    for entry_id in list(state):
        entry = book.entries.get(entry_id)
        if entry is None or not _known(entry, manager) or _replaced(entry, book, manager):
            del state[entry_id]
        elif entry_id not in triggered:
            state[entry_id] -= 1
            if state[entry_id] <= 0:
                del state[entry_id]

    for entry_id, turns in triggered.items():
        entry = book.entries[entry_id]
        if _known(entry, manager) and not _replaced(entry, book, manager):
            state[entry_id] = turns


def _capped(hits: list[LoreHit]) -> list[LoreHit]:
    hits = list(hits)
    while sum(len(line) for line in world_lines(hits)) > lore_k.WORLD_MAX_CHARS:
        order = drop_order(hits)
        if not order:
            break
        hits[hits.index(order[0])] = replace(order[0], shown=False)
    return hits


def system_text(lorebook: Lorebook) -> str:
    """The `system` entries as one paragraph, in `order`."""
    entries = sorted(lorebook.system_entries(), key=lambda e: (e.order, e.entry_id))
    return " ".join(entry.content for entry in entries)
