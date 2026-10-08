"""The true state [IN VIEW] repeats for the narrator: what each refused action left as it was (llm-contract)."""

from collections.abc import Iterable

from managers import carry, naming
from managers.game import GameManager
from managers.world.barriers import find_barrier, state_word
from managers.world.rooms import current_room
from modules.action.types import (
    AnyAction,
    BarricadeAction,
    CloseAction,
    DropAction,
    EquipAction,
    GiveAction,
    LockAction,
    MoveAction,
    OpenAction,
    PutAction,
    TakeAction,
    TakeOffAction,
    UnbarricadeAction,
    UnequipAction,
    UnlockAction,
    UseItemAction,
    WearAction,
)
from modules.entity.item import ItemEntity


def _item_name(action: AnyAction) -> str | None:
    match action:
        case TakeAction(all_items=True):
            return None
        case DropAction(corpse=True):
            return None
        case (
            TakeAction(item_name=name)
            | PutAction(item_name=name)
            | DropAction(item_name=name)
            | WearAction(item_name=name)
            | TakeOffAction(item_name=name)
            | EquipAction(item_name=name)
            | UnequipAction(item_name=name)
            | UseItemAction(item_name=name)
            | GiveAction(item_name=name)
        ):
            return name
    return None


def _where(manager: GameManager, name: str) -> tuple[ItemEntity, str] | None:
    """The item `name` points at and where it is now, in words; None when it is nowhere in reach."""
    player = manager.player
    owner = player.appearance.forename
    for entity in player.equipment.values():
        if entity is not None and naming.first_named([entity], name):
            return entity, f"in {owner}'s hand"
    for entity in player.worn.values():
        if entity is not None and naming.first_named([entity], name):
            return entity, f"worn by {owner}"
    entity = naming.first_named(carry.carried_items(player), name)
    if entity is not None:
        bag = carry.holder_bag(player, entity)
        return entity, f"in the {bag.item.name.lower()}" if bag else f"in {owner}'s pack"
    ground = [e for e in manager.current_location.entities if isinstance(e, ItemEntity)]
    entity = naming.first_named(ground, name)
    if entity is not None:
        return entity, "on the floor"
    zone = manager.current_location
    here = current_room(zone, player)
    rooms = sorted(zone.rooms.values(), key=lambda room: room is not here)
    for room in rooms:
        for container in room.containers:
            entity = naming.first_named(container.contents, name)
            if entity is not None:
                return entity, f"in the {container.name}"
    for npc in manager.npcs_in_location(player.current_location_id):
        entity = naming.first_named(npc.inventory, name)
        if entity is not None:
            return entity, f"with {npc.name}"
    return None


def _item_line(manager: GameManager, name: str) -> str | None:
    found = _where(manager, name)
    if found is None:
        return None
    entity, place = found
    return f"The {entity.item.name.lower()}: {place}."


def _barrier_line(manager: GameManager, name: str) -> str | None:
    barrier = find_barrier(manager.world, manager.player.current_location_id, name)
    if barrier is None:
        return None
    words = state_word(barrier)
    if barrier.total_planks:
        words += ", barricaded"
    return f"The {barrier.name} is {words}."


def _move_line(manager: GameManager) -> str:
    zone = manager.current_location
    room = current_room(zone, manager.player)
    where = f"the {room.name}, {zone.name}" if room else zone.name
    return f"{manager.player.appearance.forename} is still in {where}."


def touched_lines(manager: GameManager, refused: Iterable[AnyAction]) -> list[str]:
    """One line per thing the refused actions touched, in the order first touched: where it is now."""
    lines: list[str] = []
    for action in refused:
        line: str | None = None
        if isinstance(action, MoveAction):
            line = _move_line(manager)
        elif isinstance(
            action,
            OpenAction
            | CloseAction
            | LockAction
            | UnlockAction
            | BarricadeAction
            | UnbarricadeAction,
        ):
            line = _barrier_line(manager, action.barrier_name)
        elif (name := _item_name(action)) is not None:
            line = _item_line(manager, name)
        if line is not None and line not in lines:
            lines.append(line)
    return lines
