"""Corpses in the player's view, going through them and taking from them (zombie-lifecycle)."""

import random
from collections.abc import Collection, Iterable
from dataclasses import dataclass

from data import carry as carry_k
from data.loot import containers as container_k
from data.loot.catalogue import LOOT_KIND_MODIFIERS
from data.loot.tables import LootTable
from data.zombies import lore as zombie_lore
from data.zombies.loot import DEFAULT_LOOT_TABLES, OUTFIT_LOOT_TABLES
from managers import naming
from managers.corpses.bodies import rot_stage
from managers.game import GameManager
from managers.world.containers import fill_bag, roll_table
from managers.zombies.population import distance_word, light_level
from modules.body.parts import LAYER_ORDER
from modules.entity.corpse import CorpseEntity
from modules.entity.item import ItemEntity
from modules.item import ClothingItem


def drop_chance(chance: float, kind: str) -> float:
    """The chance a pocket entry drops: its table chance times the multiplier for its kind of item."""
    return chance * LOOT_KIND_MODIFIERS[kind] / 100


def roll_pockets(corpse: CorpseEntity, rng: random.Random) -> list[ItemEntity]:
    """The pocket items of a body: its outfit's table first, then the default table for its sex.

    Entries with no catalogue item are skipped without a roll, a list ends when an item does not
    fit the body's 12 kg container, and bones hold nothing.
    """
    if corpse.skeleton:
        return []
    tables = [OUTFIT_LOOT_TABLES.get(corpse.outfit, ()), DEFAULT_LOOT_TABLES[_sex(corpse)]]
    found: list[ItemEntity] = []
    for entries in tables:
        held = sum(entity.weight for entity in [*corpse.contents, *found])
        found.extend(
            roll_table(
                rng,
                LootTable(1, tuple(entries), 1, (), False),
                capacity=container_k.CORPSE_CAPACITY,
                held=held,
                randomise=False,
            )
        )
    return found


def _sex(corpse: CorpseEntity) -> str:
    return "female" if corpse.female else "male"


def search(corpse: CorpseEntity, rng: random.Random) -> None:
    """Go through a body: its pockets are rolled once, its bags fill from their tables, and everything it holds can be taken."""
    if corpse.searched:
        return
    worn_and_carried = list(corpse.contents)
    corpse.contents.extend(roll_pockets(corpse, rng))
    for entity in worn_and_carried:
        fill_bag(rng, entity)
    corpse.searched = True


def with_article(name: str) -> str:
    """The name with "a" or "an"; plural names such as jeans take none."""
    if name.endswith("s") and not name.endswith("ss"):
        return name
    return f"{'an' if name[0].lower() in 'aeiou' else 'a'} {name}"


def _plural(name: str) -> str:
    if name.endswith("s"):
        return name
    if name.endswith(("sh", "ch", "x")):
        return f"{name}es"
    if name.endswith("fe"):
        return f"{name[:-2]}ves"
    if name.endswith("y") and name[-2:-1] not in "aeiou":
        return f"{name[:-1]}ies"
    return f"{name}s"


def _count_phrase(name: str, count: int) -> str:
    if count == 1:
        return with_article(name)
    number = (
        container_k.NUMBER_WORDS[count] if count < len(container_k.NUMBER_WORDS) else str(count)
    )
    return f"{number} {_plural(name)}"


def items_in_words(entities: Iterable[ItemEntity]) -> str:
    """Items by name with counts, in order of first appearance: "a hammer, nails and two planks"; empty for none."""
    counts: dict[str, int] = {}
    for entity in entities:
        name = entity.item.name.lower()
        counts[name] = counts.get(name, 0) + 1
    phrases = [_count_phrase(name, count) for name, count in counts.items()]
    if len(phrases) <= 1:
        return "".join(phrases)
    return f"{', '.join(phrases[:-1])} and {phrases[-1]}"


def contents_in_words(corpse: CorpseEntity) -> str:
    """What a body holds, by name, for a fact."""
    return items_in_words(corpse.contents) or zombie_lore.SEARCH_NOTHING


def find_content(corpse: CorpseEntity, name: str) -> ItemEntity | list[ItemEntity] | None:
    """What on a body `name` points at: `naming.find_named`, else the first name containing it."""
    found = naming.find_named(corpse.contents, name)
    if found is not None:
        return found
    needle = name.strip().casefold()
    for entity in corpse.contents:
        if needle and needle in entity.item.name.casefold():
            return entity
    return None


def strip_unhappiness(traits: list[str], minutes: int) -> float:
    """The unhappiness taking items off a body costs: 1.8 a minute, changed by how hardened the player is."""
    amount = zombie_lore.CORPSE_STRIP_UNHAPPINESS_PER_MIN * minutes
    for trait, factor in zombie_lore.STRIP_UNHAPPINESS_TRAIT_MULT.items():
        if trait in traits:
            amount *= factor
    return amount


def perceived_corpses(manager: GameManager) -> list[CorpseEntity]:
    """The bodies in the player's zone that the player can see, in id order."""
    world = manager.world
    if not world.corpses:
        return []
    sample = manager.climate.sample(manager.narrative.minutes)
    light = light_level(manager.current_location.indoors, world.power_on, sample.daylight)
    sight = zombie_lore.SIGHT_RANGE * max(zombie_lore.SIGHT_RANGE_MIN_LIGHT, light)
    here = manager.player.current_location_id
    return sorted(
        (c for c in world.corpses.values() if c.zone_id == here and c.gap <= sight),
        key=lambda c: int(c.corpse_id[1:]),
    )


@dataclass(frozen=True)
class CorpseView:
    """A perceived body in words."""

    corpse_id: str
    distance_word: str  # "carried" for a body in the arms
    rot_word: str
    searched: bool
    skeleton: bool
    looks: str
    contents: tuple[str, ...]
    sex_word: str  # empty for bare bones

    def words(self) -> str:
        """The body in a few words for a list: how far, how rotten, whether searched."""
        parts = [self.distance_word, self.rot_word]
        parts.append("searched" if self.searched else "not searched")
        return ", ".join(parts)

    def line(self, *, with_id: bool) -> str:
        """One line for a prompt: a body is only ever dead, never fake-dead or crawling."""
        parts = [self.corpse_id] if with_id else []
        parts.append(self.distance_word)
        if self.skeleton:
            parts.append(self.looks if with_id else self.rot_word)
        elif self.searched:
            parts.extend([self.looks] if with_id else [])
            parts.append(self.rot_word)
            parts.append(f"searched: {', '.join(self.contents) or zombie_lore.SEARCH_NOTHING}")
        else:
            parts.extend([self.looks, self.rot_word, "not searched"])
        return " - " + ", ".join(parts)


def _layer(entity: ItemEntity) -> int:
    item = entity.item
    assert isinstance(item, ClothingItem)
    return LAYER_ORDER[item.body_location]


def person_word(female: bool) -> str:
    return zombie_lore.WOMAN_WORD if female else zombie_lore.MAN_WORD


def looks_words(
    person: str, things: Iterable[ItemEntity], limit: int = zombie_lore.CORPSE_LOOK_ITEMS
) -> str:
    """A body or a zombie by sight: `person` and the `limit` outermost garments among `things`."""
    clothes = [e for e in things if isinstance(e.item, ClothingItem)]
    garments = sorted(clothes, key=_layer, reverse=True)[:limit]
    names = [with_article(e.item.name.lower()) for e in garments]
    if not names:
        return person
    worn = names[0] if len(names) == 1 else f"{', '.join(names[:-1])} and {names[-1]}"
    return f"{person} in {worn}"


def corpse_person(corpse: CorpseEntity) -> str:
    """What a body is called by sight: bare bones leave the sex out."""
    return zombie_lore.SKELETON_WORD if corpse.skeleton else person_word(corpse.female)


def _looks(corpse: CorpseEntity) -> str:
    return looks_words(corpse_person(corpse), corpse.contents)


def corpse_views(
    manager: GameManager, ambiguous: Collection[str] = frozenset()
) -> list[CorpseView]:
    """The perceived bodies in words: no numbers, and nothing that says one may get up.

    Items whose names are in `ambiguous` carry their describing words.
    """
    now = manager.narrative.minutes
    return [
        CorpseView(
            corpse_id=c.corpse_id,
            distance_word=carry_k.CARRIED_WORD
            if c.corpse_id == manager.player.carrying_corpse
            else distance_word(c.gap),
            rot_word=zombie_lore.SKELETON_WORD
            if c.skeleton
            else zombie_lore.ROT_WORDS[rot_stage(c, now)],
            searched=c.searched,
            skeleton=c.skeleton,
            looks=_looks(c),
            contents=tuple(naming.tagged_name(e, ambiguous).lower() for e in c.contents),
            sex_word="" if c.skeleton else person_word(c.female),
        )
        for c in perceived_corpses(manager)
    ]
