"""The event pipeline: traits react to an event with modifiers."""

import logging

from managers.story.relationship import RelationshipManager
from modules.character.player import PlayerTrait
from modules.entity import BaseEntity
from modules.entity.player import PlayerEntity
from modules.events.effect import (
    AnyEffect,
    ItemAppliedEffect,
    ItemConsumedEffect,
    QuestCompletedEffect,
    WeaponDamageDealtEffect,
    WeaponDamageTakenEffect,
)
from modules.events.event import (
    AnyEvent,
    ApplyItemEvent,
    ConsumeItemEvent,
    QuestCompletionEvent,
    WeaponDealDamageEvent,
    WeaponTakeDamageEvent,
)
from modules.events.modifier import (
    AffinityModifier,
    AnyModifier,
    ConditionsModifier,
    DamageMultiplicativeModifier,
    ReputationModifier,
)

logger = logging.getLogger(__name__)

# Which effect-handler classes react to which event classes. Matched by type,
# not by class name: the names don't line up ("WeaponDamageTakenEffect" reacts
# to "WeaponTakeDamageEvent").
EVENT_TO_EFFECT_TYPES: dict[type, tuple[type, ...]] = {
    WeaponDealDamageEvent: (WeaponDamageDealtEffect,),
    WeaponTakeDamageEvent: (WeaponDamageTakenEffect,),
    ApplyItemEvent: (ItemAppliedEffect,),
    ConsumeItemEvent: (ItemConsumedEffect,),
    QuestCompletionEvent: (QuestCompletedEffect,),
}

# Which of an event's two roles ("source" or "target") an entity must occupy
# for a given effect type to be eligible to react at all. Without this, an
# attacker who happens to also carry a "damage taken" trait would have it
# fire off their own outgoing hit.
EFFECT_REQUIRED_ROLE: dict[type, str] = {
    WeaponDamageDealtEffect: "source",
    WeaponDamageTakenEffect: "target",
    ItemAppliedEffect: "target",
    ItemConsumedEffect: "source",
    QuestCompletedEffect: "source",
}


def broadcast_event(event: AnyEvent) -> list[AnyModifier]:
    """
    Sends an event to its source and target and collects their reactions.

    An entity's effect only reacts in the role it is written for: a
    `WeaponDamageTakenEffect` fires only for the entity that is this
    event's *target*, never for one that merely also appears as its
    source (e.g. the attacker's own Small Frame must not treat their own
    swing as damage they took). `EFFECT_REQUIRED_ROLE` encodes that.
    """
    collected_modifiers: list[AnyModifier] = []

    role_entities: dict[str, BaseEntity] = {}
    source = getattr(event, "source", None)
    target = getattr(event, "target", None)
    if isinstance(source, BaseEntity):
        role_entities["source"] = source
    if isinstance(target, BaseEntity):
        role_entities["target"] = target

    for role, entity in role_entities.items():
        reacting = [t for t in getattr(entity, "traits", []) if isinstance(t, PlayerTrait)]

        for trait in reacting:
            for effect_handler in trait.effects:
                if not effect_handler_matches(event, effect_handler, role):
                    continue

                condition = getattr(effect_handler, "condition", None)
                effect = getattr(effect_handler, "effect", None)

                if condition is None or not callable(condition):
                    continue

                if effect is None or not callable(effect):
                    continue

                if not condition(event):
                    continue

                mod = effect(event)

                if not isinstance(mod, AnyModifier):
                    continue

                logger.debug(
                    f"Effect '{trait.name}' on {type(entity).__name__} ({role}) generated modifier: {type(mod).__name__}"
                )
                collected_modifiers.append(mod)

    return collected_modifiers


def apply_event_modifiers(
    relationships: RelationshipManager, event: AnyEvent, modifiers: list[AnyModifier]
) -> None:
    """Applies the modifiers one event produced: damage first, then the rest."""
    if isinstance(event, (WeaponDealDamageEvent, WeaponTakeDamageEvent)):
        base_damage = event.damage
        damage_multiplier = 1.0

        for mod in modifiers:
            if isinstance(mod, DamageMultiplicativeModifier):
                damage_multiplier *= mod.multiplier

        final_damage = int(base_damage * damage_multiplier)

        if not isinstance(event.target, BaseEntity):
            logger.warning(f"Event target is not an Entity: {event.target}. Cannot apply damage.")
            return

        if isinstance(event.target, PlayerEntity):
            logger.warning("Event damage cannot land on the player's body; ignoring it.")
            return

        event.target.hit_points -= final_damage
        logger.debug(
            f"Applied {final_damage} damage to {type(event.target).__name__}. HP is now {event.target.hit_points}."
        )

    # Every other modifier type applies to the event's target (falling
    # back to its source for an event with no target), which is the
    # entity the reaction was about.
    target = getattr(event, "target", None)
    source = getattr(event, "source", None)
    recipient = target if isinstance(target, BaseEntity) else source

    for mod in modifiers:
        if isinstance(mod, AffinityModifier):
            relationships.apply_affinity_modifier(mod)
        elif isinstance(mod, ReputationModifier):
            relationships.apply_reputation_modifier(mod)
        elif isinstance(mod, ConditionsModifier) and isinstance(recipient, BaseEntity):
            for condition, active in mod.conditions.items():
                conditions = getattr(recipient, "conditions", None)
                if conditions is None:
                    continue
                if active and condition not in conditions:
                    conditions.append(condition)
                elif not active and condition in conditions:
                    conditions.remove(condition)
        # XPModifier has no current producer on this path (QuestCompletionEvent
        # has no emitter yet) and is left unhandled.


def effect_handler_matches(event: AnyEvent, handler: AnyEffect, role: str) -> bool:
    """Whether an effect handler (from a trait's `.effects`)
    reacts to this event's type when held by the entity occupying `role`
    ("source" or "target")."""
    if not isinstance(handler, EVENT_TO_EFFECT_TYPES.get(type(event), ())):
        return False
    required_role = EFFECT_REQUIRED_ROLE.get(type(handler))
    return required_role is None or required_role == role
