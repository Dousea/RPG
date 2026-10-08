"""Mentions: things the player picked from the `@` list, and their binding to parsed actions.

A mention is a stable reference the engine binds itself: the parser proposes actions as
usual, then `bind` puts each picked entity into the action's matching target field as a
`Pinned` text, so the validator resolves exactly that entity (llm-contract).
"""

from dataclasses import dataclass, replace
from typing import Literal

from modules.action.types import AnyAction

MentionKind = Literal[
    "zombie", "corpse", "npc", "barrier", "room", "container", "zone", "body_part", "item"
]

# Stands in the sent text where a picked entry sits; a typed "@" is never a pick.
MENTION_MARK = "￼"

# Zombies and corpses are aimed at by id in the parser's scene; everything else by name.
_WRITTEN_BY_ID: frozenset[MentionKind] = frozenset({"zombie", "corpse"})


@dataclass(frozen=True)
class Mention:
    """One entry of the `@` list: what it is, its id, the name the player sees and a short description."""

    kind: MentionKind
    id: str
    name: str
    description: str

    @property
    def written(self) -> str:
        """What the action line carries for this entity: its id for a zombie or body, else its name."""
        return self.id if self.kind in _WRITTEN_BY_ID else self.name


class Pinned(str):
    """A target text the player pinned: reads as the scene's own name, and carries the entity's id."""

    kind: MentionKind
    entity_id: str

    def __new__(cls, text: str, kind: MentionKind, entity_id: str) -> "Pinned":
        pinned = super().__new__(cls, text)
        pinned.kind = kind
        pinned.entity_id = entity_id
        return pinned


def pin_of(text: str | None, *kinds: MentionKind) -> Pinned | None:
    """`text` as a pin, when it is one (of one of `kinds`, if any are given)."""
    if isinstance(text, Pinned) and (not kinds or text.kind in kinds):
        return text
    return None


@dataclass(frozen=True)
class _Slot:
    """A target field of an action that a mention of one of `kinds` can fill.

    A `when_set` slot exists only once the parser filled it: an optional source is not
    invented for a pin that belongs to another action.
    """

    attr: str
    kinds: tuple[MentionKind, ...]
    when_set: bool = False


_ITEM_SLOT = (_Slot("item_name", ("item",)),)
_BARRIER_SLOT = (_Slot("barrier_name", ("barrier",)),)
_PART_SLOT = (_Slot("part_name", ("body_part",)),)
_NPC_SLOT = (_Slot("npc_name", ("npc",)),)

SLOTS: dict[str, tuple[_Slot, ...]] = {
    "MOVE_TO": (_Slot("destination", ("zone", "room")),),
    "TAKE": (
        _Slot("item_name", ("item",), when_set=True),
        _Slot("from_name", ("corpse", "container"), when_set=True),
    ),
    "PUT": (_Slot("item_name", ("item",)), _Slot("target_name", ("container",))),
    "CARRY": (_Slot("corpse_name", ("corpse",)),),
    "SEARCH": (_Slot("target_name", ("corpse", "room", "container")),),
    "ATTACK": (_Slot("target_name", ("npc", "zombie", "barrier")),),
    "SHOVE": (_Slot("target_name", ("zombie",)),),
    "DROP": _ITEM_SLOT,
    "WEAR": _ITEM_SLOT,
    "TAKE_OFF": _ITEM_SLOT,
    "EQUIP": _ITEM_SLOT,
    "UNEQUIP": _ITEM_SLOT,
    "USE_ITEM": _ITEM_SLOT,
    "OPEN": _BARRIER_SLOT,
    "CLOSE": _BARRIER_SLOT,
    "LOCK": _BARRIER_SLOT,
    "UNLOCK": _BARRIER_SLOT,
    "BARRICADE": _BARRIER_SLOT,
    "UNBARRICADE": _BARRIER_SLOT,
    "BANDAGE": (*_PART_SLOT, *_ITEM_SLOT),
    "REMOVE_BANDAGE": _PART_SLOT,
    "DISINFECT": (*_PART_SLOT, *_ITEM_SLOT),
    "TALK": _NPC_SLOT,
    "REQUEST": _NPC_SLOT,
    "GIVE": (*_NPC_SLOT, *_ITEM_SLOT),
    "ADD_RELATIONSHIP_NOTE": _NPC_SLOT,
}


def _folded(text: str) -> str:
    return text.strip().strip("\"'.,;:").casefold().removeprefix("the ").strip()


def _names(text: str | None, mention: Mention) -> bool:
    return text is not None and _folded(text) == _folded(mention.written)


def bind(actions: list[AnyAction], mentions: list[Mention]) -> list[AnyAction]:
    """The actions with each mention pinned into the target field it belongs to.

    A mention first takes the field that already writes it (its id or name as the scene lists it). One the parser
    dropped or swapped takes the first field of its kind that nothing claimed, in action
    order; the pin wins over what the parser wrote there.
    """
    fields = [
        (index, slot) for index, action in enumerate(actions) for slot in SLOTS.get(action.verb, ())
    ]
    claimed: dict[tuple[int, str], Mention] = {}

    def value(index: int, slot: _Slot) -> str | None:
        return getattr(actions[index], slot.attr)

    def free(index: int, slot: _Slot, mention: Mention) -> bool:
        return (index, slot.attr) not in claimed and mention.kind in slot.kinds

    unplaced: list[Mention] = []
    for mention in mentions:
        named = next(
            (
                (index, slot)
                for index, slot in fields
                if free(index, slot, mention) and _names(value(index, slot), mention)
            ),
            None,
        )
        if named is None:
            unplaced.append(mention)
        else:
            claimed[named[0], named[1].attr] = mention
    for mention in unplaced:
        open_field = next(
            (
                (index, slot)
                for index, slot in fields
                if free(index, slot, mention) and (not slot.when_set or value(index, slot))
            ),
            None,
        )
        if open_field is not None:
            claimed[open_field[0], open_field[1].attr] = mention
    bound = list(actions)
    for (index, attr), mention in claimed.items():
        pin = Pinned(mention.written, mention.kind, mention.id)
        bound[index] = replace(bound[index], **{attr: pin})
    return bound


def pinned_ids(actions: list[AnyAction]) -> set[str]:
    """The entity ids pinned into the target fields of `actions`."""
    return {
        pin.entity_id
        for action in actions
        for slot in SLOTS.get(action.verb, ())
        if (pin := pin_of(getattr(action, slot.attr))) is not None
    }


def render_input(text: str, mentions: list[Mention], *, for_parser: bool) -> str:
    """The player's text with each mark replaced by its mention.

    The parser reads `[pinned: z32]`, the id or name the scene lists; everything else (the
    narrator, the memory, the event log) reads the plain name, so no id leaves the engine.
    A mark with no mention left is dropped.
    """
    pieces = text.split(MENTION_MARK)
    out = [pieces[0]]
    for index, piece in enumerate(pieces[1:]):
        if index < len(mentions):
            mention = mentions[index]
            out.append(f"[pinned: {mention.written}]" if for_parser else mention.name)
        out.append(piece)
    return "".join(out)
