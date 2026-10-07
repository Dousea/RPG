"""Combat: which weapon the player holds and how much damage one hit does to an NPC."""

import random

from managers.events.pipeline import broadcast_event
from modules.character.equipment import CharacterHoldableSlot
from modules.entity.item import ItemEntity
from modules.entity.npc import NpcEntity
from modules.entity.player import PlayerEntity
from modules.events.event import WeaponDealDamageEvent, WeaponTakeDamageEvent
from modules.events.modifier import AnyModifier, DamageMultiplicativeModifier
from modules.item import HoldableItem, MeleeWeaponItem, RangedWeaponItem

# +/-10% variance on damage rolls, just enough that combat doesn't read as a
# fixed calculator.
DAMAGE_JITTER = 0.10


def held_slots(item: HoldableItem) -> list[CharacterHoldableSlot]:
    """The hands an item takes: both if it is two-handed, otherwise the right."""
    if item.is_two_handed:
        return list(CharacterHoldableSlot)
    return [CharacterHoldableSlot.RIGHT_HAND]


def held_entity(player: PlayerEntity) -> ItemEntity | None:
    """The entity in the player's hands (a two-handed one fills both), or None."""
    for slot in CharacterHoldableSlot:
        entity = player.equipment[slot]
        if entity is not None:
            return entity
    return None


def equipped_weapon(player: PlayerEntity) -> MeleeWeaponItem | RangedWeaponItem | None:
    for entity in player.equipment.values():
        if entity is not None and isinstance(entity.item, (MeleeWeaponItem, RangedWeaponItem)):
            return entity.item
    return None


def roll_damage(
    attacker: PlayerEntity,
    weapon: MeleeWeaponItem | RangedWeaponItem,
    target: NpcEntity,
    rng: random.Random,
) -> tuple[int, list[AnyModifier]]:
    """The damage one hit deals (at least 1), and every modifier the hit's events produced.

    Two events for one hit: one for the attacker's "dealt" reactions (e.g. Gun
    Slinger's +20% with ranged weapons), one for the defender's "taken"
    reactions (e.g. Small Frame's +10% damage taken). Both feed a single
    combined multiplier so the hit is only ever subtracted once.
    """
    base_damage = weapon.damage
    dealt_event = WeaponDealDamageEvent(
        source=attacker, weapon=weapon, damage=base_damage, target=target
    )
    taken_event = WeaponTakeDamageEvent(
        source=attacker, weapon=weapon, damage=base_damage, target=target
    )
    modifiers = [*broadcast_event(dealt_event), *broadcast_event(taken_event)]

    multiplier = 1.0
    for modifier in modifiers:
        if isinstance(modifier, DamageMultiplicativeModifier):
            multiplier *= modifier.multiplier

    jitter = 1.0 + rng.uniform(-DAMAGE_JITTER, DAMAGE_JITTER)
    return max(1, int(base_damage * multiplier * jitter)), modifiers
