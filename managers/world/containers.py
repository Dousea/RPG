"""Filling a container from its table when it is first opened (spec 25)."""

import random

from data.items import ITEMS
from data.loot import containers as container_k
from data.loot.catalogue import LOOT_CATALOGUE, LOOT_KIND_MODIFIERS
from data.loot.tables import (
    BAG_TABLES,
    PROCEDURAL_TABLES,
    ROOM_TABLES,
    LootTable,
    ProcedureEntry,
)
from managers import carry
from modules.entity.item import ItemEntity
from modules.item import ContainerItem, MedicalItem, MeleeWeaponItem, StackItem
from modules.world.room import ContainerEntity, RoomEntity

__all__ = ["fill_bag", "open_container", "pick_procedural", "roll_table"]


def pick_procedural(
    rng: random.Random, room: RoomEntity, procedures: tuple[ProcedureEntry, ...]
) -> ProcedureEntry | None:
    """Pick one procedural table for a container of `room`, and count it as used there.

    A table with `min_picks` 1 that the room has not used yet is forced; otherwise any table below its
    `max_picks` can be picked. The weighted walk takes the first table whose running sum reaches the draw.
    """
    used = room.proc_spawned
    forced = [e for e in procedures if e.min_picks == 1 and used.get(e.table, 0) == 0]
    pool = forced or [e for e in procedures if used.get(e.table, 0) < e.max_picks]
    if not pool:
        return None
    draw = rng.randrange(sum(e.weight for e in pool))
    running = 0
    picked = pool[-1]
    for entry in pool:
        running += entry.weight
        if running >= draw:
            picked = entry
            break
    used[picked.table] = used.get(picked.table, 0) + 1
    return picked


def _randomise(rng: random.Random, entity: ItemEntity) -> None:
    """A spawn outside a shop is sometimes worn, or part used."""
    item = entity.item
    if isinstance(item, MeleeWeaponItem):
        if rng.randrange(container_k.PERCENT_DENOMINATOR) < container_k.RANDOM_CONDITION_PCT:
            entity.condition = max(1, rng.randint(0, item.condition_max))
    elif (
        isinstance(item, MedicalItem | StackItem)
        and item.uses > 1
        and rng.randrange(container_k.PERCENT_DENOMINATOR) < container_k.RANDOM_USES_PCT
    ):
        entity.uses = rng.randint(1, item.uses)


def _roll_list(
    rng: random.Random,
    entries: tuple[tuple[str, float], ...],
    rolls: int,
    *,
    junk: bool,
    shop: bool,
    randomise: bool,
    capacity: float,
    found: list[ItemEntity],
    held: float,
    bag_tables: dict[str, LootTable],
) -> None:
    """Roll one list into `found`; the first spawn that does not fit ends the list.

    Entries with no catalogue item are skipped without a roll.
    """
    for _ in range(max(1, rolls)):
        for name, chance in entries:
            catalogue = LOOT_CATALOGUE.get(name)
            item = ITEMS.get(catalogue[0]) if catalogue is not None else None
            if catalogue is None or item is None:
                continue
            modifier = 1.0 if junk else LOOT_KIND_MODIFIERS[catalogue[1]]
            mult = container_k.JUNK_CHANCE_MULT if junk else 1.0
            if modifier <= 0:
                continue
            if (
                rng.randrange(container_k.ROLL_DENOMINATOR)
                >= chance * mult * container_k.CHANCE_PERCENT_SCALE * modifier
            ):
                continue
            entity = ItemEntity(item=item)
            if carry.rounded(held + sum(e.weight for e in found) + entity.weight) > carry.rounded(
                capacity
            ):
                return
            if randomise and not shop:
                _randomise(rng, entity)
            found.append(entity)
            if isinstance(item, ContainerItem) and not shop and name in bag_tables:
                entity.contents = roll_table(
                    rng,
                    bag_tables[name],
                    capacity=item.capacity,
                    bag_tables=bag_tables,
                    randomise=randomise,
                )


def roll_table(
    rng: random.Random,
    table: LootTable,
    *,
    capacity: float,
    held: float = 0.0,
    bag_tables: dict[str, LootTable] = BAG_TABLES,
    randomise: bool = True,
) -> list[ItemEntity]:
    """The items a table spawns into a container of `capacity` kg that already holds `held` kg.

    The junk list rolls first, then the main list; each stops on its own when an item does not fit.
    """
    found: list[ItemEntity] = []
    shared = {
        "shop": table.shop,
        "randomise": randomise,
        "capacity": capacity,
        "found": found,
        "held": held,
    }
    _roll_list(rng, table.junk_items, table.junk_rolls, junk=True, bag_tables=bag_tables, **shared)
    _roll_list(rng, table.items, table.rolls, junk=False, bag_tables=bag_tables, **shared)
    return found


def open_container(rng: random.Random, room: RoomEntity, container: ContainerEntity) -> None:
    """Open a container: it fills from its source table the first time, and a fixed one is never rolled."""
    if container.opened:
        return
    container.opened = True
    if container.fixed or container.source is None:
        return
    source = ROOM_TABLES[container.source[0]][container.source[1]]
    table = source.table
    if source.procedures:
        picked = pick_procedural(rng, room, source.procedures)
        table = PROCEDURAL_TABLES[picked.table] if picked is not None else None
    if table is not None:
        held = sum(e.weight for e in container.contents)
        container.contents.extend(roll_table(rng, table, capacity=container.capacity, held=held))


def fill_bag(rng: random.Random, entity: ItemEntity) -> None:
    """Fill an outfit's bag from its own table, once; any other bag, or one that holds things, is left."""
    item = entity.item
    if not isinstance(item, ContainerItem) or not entity.loot_pending:
        return
    entity.loot_pending = False
    if entity.contents:
        return
    for name, (item_id, _kind) in LOOT_CATALOGUE.items():
        if item_id == item.id and name in BAG_TABLES:
            entity.contents = roll_table(
                rng, BAG_TABLES[name], capacity=item.capacity, randomise=False
            )
            return


def unopened(room: RoomEntity) -> tuple[ContainerEntity, ...]:
    """The containers of a room that have not been gone through, in layout order."""
    return tuple(container for container in room.containers if not container.opened)


def container_weight(container: ContainerEntity) -> float:
    """What the container holds, in kg."""
    return sum(entity.weight for entity in container.contents)


def has_room_for(container: ContainerEntity, entity: ItemEntity) -> bool:
    """Whether `entity` fits in the container beside what it already holds."""
    return carry.rounded(container_weight(container) + entity.weight) <= carry.rounded(
        container.capacity
    )
