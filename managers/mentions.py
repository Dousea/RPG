"""The things the player can pin to a turn with `@`, and whether they are still in reach (llm-contract).

Only what has a stable id or a closed name is listed: seen zombies, perceived bodies, the
NPCs and rooms and containers of the zone, the barriers on its connections, every zone
`zone_path` reaches and the player's hurt or bandaged parts. Items have no instance id yet,
and topics would show what an NPC knows before it is asked.
"""

from collections.abc import Sequence
from typing import Literal

from data.story import mentions as mention_k
from data.zombies import lore as zombie_lore
from managers.body.first_aid import part_state_words, part_word
from managers.corpses.search import corpse_person, corpse_views, looks_words, person_word
from managers.game import GameManager
from managers.world.barriers import barriers_of, blocks, state_word
from managers.world.rooms import current_room
from managers.zombies.population import threat_views
from modules.action.pins import Mention
from modules.entity.item import ItemEntity


def _named_by_looks(
    entries: list[tuple[str, str, list[ItemEntity], str]],
) -> list[tuple[str, str]]:
    """(name, description) for each (id, person, garments, description), named by looks.

    A name starts with the outermost garment; entries that share one get another garment each,
    up to the scene's limit, and the description tells the rest apart.
    """
    limit = zombie_lore.CORPSE_LOOK_ITEMS
    names = [looks_words(person, things, 1) for _, person, things, _ in entries]
    for size in range(2, limit + 1):
        names = [
            looks_words(person, things, size) if names.count(name) > 1 else name
            for name, (_, person, things, _) in zip(names, entries, strict=True)
        ]
    return [(name.removeprefix("a "), entry[3]) for name, entry in zip(names, entries, strict=True)]


def _by_looks(
    kind: Literal["zombie", "corpse"], entries: list[tuple[str, str, list[ItemEntity], str]]
) -> list[Mention]:
    named = _named_by_looks(entries)
    return [
        Mention(kind, entry[0], name, description)
        for entry, (name, description) in zip(entries, named, strict=True)
    ]


def _zombies(manager: GameManager) -> list[Mention]:
    zombies = manager.world.zombies
    return _by_looks(
        "zombie",
        [
            (
                view.zombie_id,
                person_word(zombies[view.zombie_id].female),
                list(zombies[view.zombie_id].worn.values()),
                f"{view.distance_word}, {view.state_word}",
            )
            for view in threat_views(manager)
            if view.zombie_id is not None
        ],
    )


def _corpses(manager: GameManager) -> list[Mention]:
    corpses = manager.world.corpses
    return _by_looks(
        "corpse",
        [
            (
                view.corpse_id,
                corpse_person(corpses[view.corpse_id]),
                corpses[view.corpse_id].contents,
                view.words(),
            )
            for view in corpse_views(manager)
        ],
    )


def _npcs(manager: GameManager) -> list[Mention]:
    mentions: list[Mention] = []
    for npc in manager.npcs_in_location(manager.player.current_location_id):
        words = [mention_k.NPC_FOLLOWING] if npc.following else []
        words.extend(npc.status)
        mentions.append(
            Mention("npc", npc.npc_id, npc.name, ", ".join(words) or mention_k.NPC_HERE)
        )
    return mentions


def _barriers(manager: GameManager) -> list[Mention]:
    world = manager.world
    return [
        Mention(
            "barrier",
            barrier.barrier_id,
            barrier.name,
            mention_k.BARRIER_BETWEEN.format(
                state=state_word(barrier),
                a=world.locations[barrier.zones[0]].name,
                b=world.locations[barrier.zones[1]].name,
            ),
        )
        for barrier in barriers_of(world, manager.player.current_location_id)
    ]


def _rooms(manager: GameManager) -> list[Mention]:
    zone = manager.current_location
    here = current_room(zone, manager.player)
    mentions: list[Mention] = []
    for room in zone.rooms.values():
        words = mention_k.ROOM_HERE if room is here else mention_k.ROOM_ELSEWHERE
        mentions.append(Mention("room", room.room_id, room.name, words))
    for room in zone.rooms.values():
        for container in room.containers:
            state = mention_k.CONTAINER_OPENED if container.opened else mention_k.CONTAINER_CLOSED
            words = mention_k.CONTAINER_IN_ROOM.format(room=room.name, state=state)
            mentions.append(Mention("container", container.container_id, container.name, words))
    return mentions


def _zone_words(manager: GameManager, path: list[str]) -> str:
    """How a zone connects to here: the direction of an adjacent one, else the next zone on the way, and what blocks it."""
    world = manager.world
    here = world.locations[manager.player.current_location_id]
    first = path[0]
    if len(path) == 1:
        way = next(direction for direction, zone_id in here.connections.items() if zone_id == first)
    else:
        way = mention_k.ZONE_VIA.format(zone=world.locations[first].name)
    hop_from = here.id
    for hop in path:
        for barrier in barriers_of(world, hop_from):
            if hop in barrier.zones and blocks(barrier):
                return mention_k.ZONE_BLOCKED.format(
                    way=way, barrier=barrier.name, state=state_word(barrier)
                )
        hop_from = hop
    return way


def _zones(manager: GameManager) -> list[Mention]:
    here = manager.player.current_location_id
    mentions: list[Mention] = []
    for zone in manager.world.locations.values():
        if zone.id == here:
            continue
        path = manager.zone_path(here, zone.id)
        if path:
            mentions.append(Mention("zone", zone.id, zone.name, _zone_words(manager, path)))
    return mentions


def _body_parts(manager: GameManager) -> list[Mention]:
    return [
        Mention("body_part", part.value, part_word(part), ", ".join(part_state_words(state)))
        for part, state in manager.player.body.items()
        if state.injured or state.bandaged
    ]


def mentionables(manager: GameManager) -> list[Mention]:
    """What the player can mention now, grouped by kind in the order the list shows them."""
    return [
        *_zombies(manager),
        *_corpses(manager),
        *_npcs(manager),
        *_barriers(manager),
        *_rooms(manager),
        *_zones(manager),
        *_body_parts(manager),
    ]


def labels(mentions: Sequence[Mention]) -> list[str]:
    """The text each entry shows and its pick carries: its name, numbered where another entry has the same."""
    names = [mention.name for mention in mentions]
    seen: dict[str, int] = {}
    out: list[str] = []
    for name in names:
        if names.count(name) > 1:
            seen[name] = seen.get(name, 0) + 1
            out.append(f"{name} #{seen[name]}")
        else:
            out.append(name)
    return out


def picked(manager: GameManager, ids: Sequence[str]) -> tuple[list[Mention], list[str]]:
    """The mentions the ids name, in the order given, and the ids that are no longer in reach."""
    listed = mentionables(manager)
    found: list[Mention] = []
    gone: list[str] = []
    for mention_id in ids:
        mention = next((m for m in listed if m.id == mention_id), None)
        if mention is None:
            gone.append(mention_id)
        else:
            found.append(mention)
    return found, gone
