"""Dressing a zombie: its sex, outfit, worn items and the weapon stuck in it (zombie-lifecycle)."""

import random

from data.items import ITEMS
from data.loot.catalogue import LOOT_CATALOGUE
from data.zombies import lore as zombie_lore
from data.zombies.loot import ATTACHED_WEAPONS, CUSTOM_OUTFIT_WEAPONS, StuckWeaponEntry
from data.zombies.outfits import ZOMBIE_OUTFIT_POOL, ZOMBIE_OUTFIT_REFERENCES
from modules.body.parts import BodyLocation, BodyPart
from modules.entity.item import ItemEntity
from modules.entity.zombie import ZombieEntity
from modules.item import ClothingItem, ContainerItem, MeleeWeaponItem

_PERCENT = 100


def pick_outfit(rng: random.Random, female: bool) -> str:
    """One roll over the chance total of the outfits open to the sex."""
    sex = "female" if female else "male"
    pool = [(name, chance) for name, chance, only in ZOMBIE_OUTFIT_POOL if only in ("any", sex)]
    roll = rng.random() * sum(chance for _, chance in pool)
    running = 0.0
    for name, chance in pool:
        running += chance
        if roll < running:
            return name
    return pool[-1][0]


def dress_outfit(
    outfit: str, female: bool, rng: random.Random
) -> tuple[dict[BodyLocation, ItemEntity], list[ItemEntity]]:
    """The clothes an outfit puts on a zombie and the bags it carries, references in table order."""
    references = ZOMBIE_OUTFIT_REFERENCES[outfit]["female" if female else "male"]
    worn: dict[BodyLocation, ItemEntity] = {}
    bags: list[ItemEntity] = []
    for probability, choices in references:
        if rng.random() > probability:
            continue
        item_id = choices[rng.randrange(len(choices))]
        item = ITEMS.get(item_id) if item_id is not None else None
        if isinstance(item, ClothingItem) and item.body_location not in worn:
            worn[item.body_location] = ItemEntity(item=item)
        elif isinstance(item, ContainerItem):
            bags.append(ItemEntity(item=item, loot_pending=True))
    return worn, bags


def attached_pool(outfit: str, days: float) -> list[tuple[str, StuckWeaponEntry]]:
    """The definitions a zombie in `outfit` may be given `days` after the outbreak."""
    return [
        (name, definition)
        for name, definition in ATTACHED_WEAPONS.items()
        if _eligible(definition, outfit, days)
    ]


def _eligible(definition: StuckWeaponEntry, outfit: str, days: float) -> bool:
    if definition.day > 0:
        return days > definition.day
    return not definition.outfits or outfit in definition.outfits


def _pick_definition(names: list[str], outfit: str, days: float, rng: random.Random) -> str | None:
    possible = [n for n in names if _eligible(ATTACHED_WEAPONS[n], outfit, days)]
    total = sum(ATTACHED_WEAPONS[n].chance for n in possible)
    choice = rng.randrange(total) if total > 0 else 0
    running = 0
    for name in possible:
        running += ATTACHED_WEAPONS[name].chance
        if choice < running:
            return name
    return None


def _condition(maximum: int, rng: random.Random) -> int:
    low = max(zombie_lore.ATTACHED_CONDITION_FLOOR, maximum - zombie_lore.ATTACHED_CONDITION_SPREAD)
    return low + rng.randrange(maximum - low) if maximum > low else low


def add_holes(zombie: ZombieEntity, parts: tuple[BodyPart, ...]) -> None:
    """A hole at each part on every worn layer that covers it."""
    for part in parts:
        for entity in zombie.worn.values():
            if isinstance(entity.item, ClothingItem) and part in entity.item.covers:
                entity.holes.add(part)


def add_attached_weapon(
    zombie: ZombieEntity, definition: StuckWeaponEntry, rng: random.Random
) -> None:
    """Stick one of the definition's weapons in the zombie, if the catalogue has it."""
    name = definition.weapons[rng.randrange(len(definition.weapons))]
    entry = LOOT_CATALOGUE.get(name)
    item = ITEMS.get(entry[0]) if entry is not None else None
    if not isinstance(item, MeleeWeaponItem):
        return
    if zombie.attached is None:
        zombie.attached = ItemEntity(item=item, condition=_condition(item.condition_max, rng))
    add_holes(zombie, definition.holes)


def attach_weapon(zombie: ZombieEntity, rng: random.Random, days: float) -> list[str]:
    """Roll the outfit's own weapon entry, then the general chance; returns the definitions rolled."""
    names: list[str] = []
    repeats = 1
    custom = CUSTOM_OUTFIT_WEAPONS.get(zombie.outfit)
    if custom is not None:
        chance, most, entries = custom
        if rng.randrange(_PERCENT) < chance:
            names, repeats = list(entries), most
        else:
            custom = None
    if not names:
        if rng.randrange(_PERCENT) + 1 > zombie_lore.CHANCE_OF_ATTACHED_WEAPON:
            return []
        names = list(ATTACHED_WEAPONS)
    rolled: list[str] = []
    while repeats > 0:
        picked = _pick_definition(names, zombie.outfit, days, rng)
        if picked is None:
            return rolled
        names.remove(picked)
        repeats -= 1
        rolled.append(picked)
        add_attached_weapon(zombie, ATTACHED_WEAPONS[picked], rng)
        if custom is not None and rng.randrange(_PERCENT) >= custom[0]:
            return rolled
    return rolled


def make_crawler(zombie: ZombieEntity, rng: random.Random) -> None:
    """It drags itself along from now on, at a crawling pace."""
    zombie.crawling = True
    zombie.become_crawler = False
    zombie.lunger = False
    zombie.speed_mod = (
        zombie_lore.CRAWLER_SPEED_MOD_BASE
        + rng.randrange(zombie_lore.SPEED_MOD_STEPS) / zombie_lore.SPEED_MOD_DIVISOR
    )


def dress(zombie: ZombieEntity, rng: random.Random, days: float) -> None:
    """Give a new zombie a sex, an outfit, its clothes and perhaps a weapon."""
    zombie.female = rng.randrange(zombie_lore.FEMALE_ONE_IN) == 0
    zombie.outfit = pick_outfit(rng, zombie.female)
    zombie.worn, zombie.carried = dress_outfit(zombie.outfit, zombie.female, rng)
    attach_weapon(zombie, rng, days)
