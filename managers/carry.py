"""What the player carries: weight, capacity and Heavy Load (carrying-and-loot)."""

import logging
import random
from collections.abc import Collection, Iterable, Mapping
from enum import StrEnum

from data import carry as carry_k
from data.character import skills as skill_k
from managers.character.skills import skill_levels
from modules import units
from modules.body.stats import StatusEffect
from modules.character.equipment import AnyCharacterEquipmentSlot, CharacterArmorSlot
from modules.entity.item import ItemEntity
from modules.entity.player import PlayerEntity
from modules.item import ContainerItem

logger = logging.getLogger(__name__)


class Place(StrEnum):
    """Where a moved item comes from or goes to, for its transfer time."""

    PACK = "pack"
    BAG = "bag"
    WORLD = "world"
    FLOOR = "floor"


def rounded(weight: float) -> float:
    """A weight to a hundredth of a kilo, the precision weights compare at."""
    return round(weight, carry_k.WEIGHT_DECIMALS)


def max_weight(strength: int, traits: Iterable[str], levels: Mapping[StatusEffect, int]) -> int:
    """The Strength-based capacity in kg, less what hunger, thirst, sickness, bleeding and wounds take."""
    level = min(max(strength, 0), len(carry_k.WEIGHT_MOD_BY_STRENGTH) - 1)
    base = int(carry_k.BASE_MAX_WEIGHT * carry_k.WEIGHT_MOD_BY_STRENGTH[level])
    reducers = 0
    for effect, losses in carry_k.STRENGTH_REDUCERS.items():
        effect_level = levels.get(effect, 0)
        if effect_level > 0:
            reducers += losses[effect_level - 1]
    capacity = max(0, base - reducers)
    delta = 1.0
    for trait in traits:
        delta *= carry_k.MAX_WEIGHT_TRAIT_MULT.get(trait, 1.0)
    return int(capacity * delta)


def player_max_weight(player: PlayerEntity, levels: Mapping[StatusEffect, int]) -> int:
    """`max_weight` for a player, given their status effect levels."""
    return max_weight(skill_levels(player)[skill_k.STRENGTH], player.traits, levels)


def heavy_load_level(weight: float, capacity: float) -> int:
    """The 0 to 4 Heavy Load level: above the first ratio is level 1, at or above the others."""
    weight = rounded(weight)
    if weight <= 0:
        return 0
    if capacity <= 0:
        return carry_k.HEAVY_LOAD_MAX_LEVEL
    ratio = weight / capacity
    first, *rest = carry_k.HEAVY_LOAD_THRESHOLDS
    level = 1 if ratio > first else 0
    for index, threshold in enumerate(rest, start=2):
        if ratio >= threshold:
            level = index
    return level


def load_ratio(weight: float, capacity: float) -> float:
    """Carried weight over capacity: 0 when nothing is carried, unbounded when capacity is 0."""
    weight = rounded(weight)
    if weight <= 0:
        return 0.0
    return weight / capacity if capacity > 0 else float("inf")


def walk_drain_per_hour(level: int, traits: Iterable[str]) -> float:
    """Endurance lost an hour walking at Heavy Load 3 or 4."""
    enddelta = carry_k.WALK_DRAIN_ENDDELTA
    if carry_k.OVERWEIGHT_ID in traits:
        enddelta = carry_k.WALK_DRAIN_ENDDELTA_OVERWEIGHT
    elif carry_k.ATHLETIC_ID in traits:
        enddelta = carry_k.WALK_DRAIN_ENDDELTA_ATHLETIC
    mod = (
        carry_k.WALK_DRAIN_MOD_ASTHMATIC
        if carry_k.ASTHMATIC_ID in traits
        else carry_k.WALK_DRAIN_MOD
    )
    return units.per_hour_from_frame(
        carry_k.WALK_DRAIN_FRAME_RATE
        * enddelta
        * carry_k.WALK_DRAIN_FACTOR
        * carry_k.WALK_DRAIN_HALF
        * mod
        * (carry_k.HEAVY_WALK_DRAIN_MULT[level] / carry_k.WALK_DRAIN_DIVISOR)
    )


def overload_loss(level: int) -> float:
    """HP lost a minute at Heavy Load 3 or 4 (the expected value of the per-frame hit)."""
    per_hit = carry_k.OVERLOAD_FRAME_LOSS / (
        (carry_k.OVERLOAD_LEVEL_SPAN - level) / carry_k.OVERLOAD_LEVEL_DIVISOR
    )
    return units.per_minute_from_frame(per_hit * carry_k.OVERLOAD_HIT_CHANCE)


def fitness_endurance_mult(level: int) -> int:
    """How many times a Fitness rep's endurance cost a Heavy Load level multiplies it: 1 below level 3."""
    return 1 + level // carry_k.HEAVY_FITNESS_DIVISOR


def _loose_weight(entity: ItemEntity, without: Collection[ItemEntity]) -> float:
    """Own weight and everything inside, in full, leaving out `without` wherever it is."""
    if any(entity is skipped for skipped in without):
        return 0.0
    return entity.actual_weight + sum(_loose_weight(inner, without) for inner in entity.contents)


def _on_body_weight(entity: ItemEntity, without: Collection[ItemEntity]) -> float:
    """A worn or held item: 0.3 of its weight, a bag's contents shaved by its reduction instead."""
    if any(entity is skipped for skipped in without):
        return 0.0
    item = entity.item
    if isinstance(item, ContainerItem):
        contents = sum(_loose_weight(inner, without) for inner in entity.contents)
        kept = 1 - item.weight_reduction / 100
        return entity.actual_weight * carry_k.EQUIPPED_WEIGHT_MULTIPLIER + contents * kept
    return _loose_weight(entity, without) * carry_k.EQUIPPED_WEIGHT_MULTIPLIER


def _distinct(entities: Iterable[ItemEntity | None]) -> list[ItemEntity]:
    found: list[ItemEntity] = []
    for entity in entities:
        if entity is not None and not any(entity is seen for seen in found):
            found.append(entity)
    return found


def held_things(player: PlayerEntity) -> list[ItemEntity]:
    """What is in the hands or on the shoulders, each once."""
    return _distinct(player.equipment.values())


def on_body(player: PlayerEntity) -> list[ItemEntity]:
    """Everything worn, in hand or on the shoulders, each once."""
    return _distinct([*player.worn.values(), *player.equipment.values()])


def carried_weight(
    player: PlayerEntity,
    *,
    without: Collection[ItemEntity] = (),
    extra: Collection[ItemEntity] = (),
) -> float:
    """Everything the player has, in kg: the pack, what is worn or held, and a body in their arms.

    `without` leaves items out wherever they are; `extra` adds items as if loose in the pack.
    """
    total = sum(_loose_weight(entity, without) for entity in player.inventory)
    total += sum(_loose_weight(entity, ()) for entity in extra)
    total += sum(_on_body_weight(entity, without) for entity in on_body(player))
    if player.carrying_corpse is not None:
        body = carry_k.SKELETON_WEIGHT if player.carrying_skeleton else carry_k.CORPSE_WEIGHT
        total += body * carry_k.EQUIPPED_WEIGHT_MULTIPLIER
    return rounded(total)


def over_the_limit(
    player: PlayerEntity,
    *,
    without: Collection[ItemEntity] = (),
    extra: Collection[ItemEntity] = (),
) -> bool:
    """Whether the player would carry more than the main inventory holds after the move."""
    would_carry = carried_weight(player, without=without, extra=extra)
    over = would_carry > carry_k.MAIN_INVENTORY_CAPACITY
    if over:
        logger.debug(
            "Over capacity: would carry %s kg of %s kg (adding %s kg)",
            would_carry,
            carry_k.MAIN_INVENTORY_CAPACITY,
            rounded(sum(entity.weight for entity in extra)),
        )
    return over


def _descendants(entity: ItemEntity) -> list[ItemEntity]:
    found: list[ItemEntity] = []
    for inner in entity.contents:
        found.append(inner)
        found.extend(_descendants(inner))
    return found


def carried_items(player: PlayerEntity) -> list[ItemEntity]:
    """The pack and what is in its bags, then what is in the worn and held bags.

    These are the items a verb can name as carried; the worn and held things themselves are not here.
    """
    found: list[ItemEntity] = []
    for entity in player.inventory:
        found.append(entity)
        found.extend(_descendants(entity))
    for entity in on_body(player):
        found.extend(_descendants(entity))
    return found


def carried_bags(player: PlayerEntity) -> list[ItemEntity]:
    """Every bag the player has with them: worn, held, in the pack or inside another bag."""
    everything = [*on_body(player), *carried_items(player)]
    return [entity for entity in everything if isinstance(entity.item, ContainerItem)]


def containing_list(player: PlayerEntity, entity: ItemEntity) -> list[ItemEntity] | None:
    """The list that holds `entity`: the pack or a bag's contents; None when it is worn or held."""
    if any(entity is each for each in player.inventory):
        return player.inventory
    for bag in carried_bags(player):
        if any(entity is each for each in bag.contents):
            return bag.contents
    return None


def holder_bag(player: PlayerEntity, entity: ItemEntity) -> ItemEntity | None:
    """The bag `entity` is directly inside, or None when it is loose, worn or held."""
    for bag in carried_bags(player):
        if any(entity is each for each in bag.contents):
            return bag
    return None


def take_out(player: PlayerEntity, entity: ItemEntity) -> None:
    """Remove an item the player has from wherever it is: the pack, a bag, a hand, the shoulders or the body."""
    holder = containing_list(player, entity)
    if holder is not None:
        holder[:] = [each for each in holder if each is not entity]
        return
    for slot, held in player.equipment.items():
        if held is entity:
            player.equipment[slot] = None
    for location in [loc for loc, worn in player.worn.items() if worn is entity]:
        del player.worn[location]


def bag_slot(player: PlayerEntity, bag: ItemEntity) -> AnyCharacterEquipmentSlot | None:
    """The first free place a bag can be carried (shoulders, then the left hand), or None."""
    item = bag.item
    assert isinstance(item, ContainerItem)
    return next((slot for slot in item.slots if player.equipment.get(slot) is None), None)


def contents_weight(bag: ItemEntity) -> float:
    """What is in a bag, in kg, each thing in full."""
    return sum(inner.weight for inner in bag.contents)


def effective_capacity(bag: ItemEntity) -> float:
    """A bag's room in kg, capped at what the main inventory could hold beside the bag itself."""
    item = bag.item
    assert isinstance(item, ContainerItem)
    return min(item.capacity, carry_k.MAIN_INVENTORY_CAPACITY - bag.actual_weight)


def bag_room(bag: ItemEntity, entities: Iterable[ItemEntity]) -> bool:
    """Whether `entities` fit in the bag: none too big for it, and the contents stay within its room."""
    item = bag.item
    assert isinstance(item, ContainerItem)
    added = list(entities)
    if item.max_item_size is not None and any(
        rounded(entity.weight) > item.max_item_size for entity in added
    ):
        logger.debug(
            "%s refuses an item over its size limit of %s kg", item.name, item.max_item_size
        )
        return False
    would_hold = rounded(contents_weight(bag) + sum(entity.weight for entity in added))
    room = rounded(effective_capacity(bag))
    if would_hold > room:
        logger.debug("%s would hold %s kg of %s kg", item.name, would_hold, room)
    return would_hold <= room


def inside(entity: ItemEntity, bag: ItemEntity) -> bool:
    """Whether `bag` is `entity` or somewhere inside it."""
    return bag is entity or any(bag is inner for inner in _descendants(entity))


def bag_place(player: PlayerEntity, bag: ItemEntity) -> str:
    """Where a carried bag is, in words: on the back, in a hand, worn, in the pack or inside another bag."""
    if player.equipment.get(CharacterArmorSlot.SHOULDERS) is bag:
        return carry_k.PLACE_BACK
    if any(held is bag for held in player.equipment.values()):
        return carry_k.PLACE_HAND
    if any(worn is bag for worn in player.worn.values()):
        return carry_k.PLACE_WORN
    outer = holder_bag(player, bag)
    if outer is not None:
        return carry_k.PLACE_INSIDE.format(bag=outer.item.name.lower())
    return carry_k.PLACE_PACK


def transfer_frames(
    entity: ItemEntity,
    source: Place,
    target: Place,
    *,
    bag: ItemEntity | None = None,
    traits: Iterable[str] = (),
) -> float:
    """Timed-action frames to move one item; `bag` is the target bag when it goes into one."""
    weight = min(entity.actual_weight, carry_k.TRANSFER_WEIGHT_CAP)
    if source is Place.BAG:
        frames = carry_k.TRANSFER_FRAMES_CARRIED * weight
    elif target is Place.BAG:
        assert bag is not None and isinstance(bag.item, ContainerItem)
        fill = max(contents_weight(bag) / bag.item.capacity, carry_k.TRANSFER_FILL_MIN)
        frames = carry_k.TRANSFER_FRAMES_CARRIED * weight * fill
    elif target is Place.FLOOR:
        frames = carry_k.TRANSFER_FRAMES_WORLD * weight * carry_k.TRANSFER_FLOOR_FACTOR
    else:
        frames = carry_k.TRANSFER_FRAMES_WORLD * weight
    if carry_k.DEXTROUS_ID in traits:
        frames *= carry_k.TRANSFER_DEXTROUS
    if carry_k.ALL_THUMBS_ID in traits:
        frames *= carry_k.TRANSFER_ALL_THUMBS
    return frames


def strength_xp_rolls(rng: random.Random, minutes: int) -> int:
    """How many Strength XP awards `minutes` of moving loaded earn: 3 or 4 checks a minute, each a small chance."""
    whole = int(carry_k.CARRY_XP_CHECKS_PER_MIN)
    extra = carry_k.CARRY_XP_CHECKS_PER_MIN - whole
    hits = 0
    for _ in range(minutes):
        checks = whole + (1 if rng.random() < extra else 0)
        hits += sum(1 for _ in range(checks) if rng.random() < carry_k.CARRY_XP_CHANCE)
    return hits


def loaded_for_xp(weight: float, capacity: float) -> bool:
    """Whether the load is above the share of capacity that trains Strength."""
    return weight > carry_k.CARRY_XP_WEIGHT_FRACTION * capacity


def grouped(labels: Iterable[str]) -> list[str]:
    """Equal labels once each, in order of first appearance, with " xN" when there are several (carrying-and-loot)."""
    counts: dict[str, int] = {}
    for label in labels:
        counts[label] = counts.get(label, 0) + 1
    return [f"{label} x{count}" if count > 1 else label for label, count in counts.items()]
