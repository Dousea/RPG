from modules.character.player import PlayerAttribute, PlayerTrait
from modules.character.state import CharacterCondition
from modules.effect import (
    ItemAppliedEffect,
    OnceEffect,
    QuestCompletedEffect,
    WeaponDamageTakenEffect,
)
from modules.entity.player import PlayerEntity
from modules.modifier import (
    AttributesModifier,
    ConditionsModifier,
    DamageMultiplicativeModifier,
    XPMultiplicativeModifier,
)
from modules.quest import QuestStyle

TRAITS: dict[str, PlayerTrait] = {
    "TraitID_Hemophobia": PlayerTrait(
        id="TraitID_Hemophobia",
        name="Hemophobia",
        description="You are logical and excel in non-violent situations, but the sight of blood and gore can send you into a panic.",
        effects=[
            QuestCompletedEffect(
                condition=lambda event: QuestStyle.NON_VIOLENT in event.styles,
                effect=lambda _: XPMultiplicativeModifier(
                    multiplier=1.5
                ),  # Increase XP gain for non-violent quests,
            ),
            ItemAppliedEffect[PlayerEntity](
                condition=lambda event: "medical" in event.item.tags,
                effect=lambda event: (
                    ConditionsModifier(conditions={CharacterCondition.PANIC: True})
                    if event.source.attributes[PlayerAttribute.WILLPOWER] < 5
                    else None
                ),
            ),
        ],
    ),
    "TraitID_SmallFrame": PlayerTrait(
        id="TraitID_SmallFrame",
        name="Small Frame",
        description="You are smaller than average, making you more nimble but also more fragile.",
        effects=[
            OnceEffect(
                effect=lambda _: AttributesModifier(
                    attributes={
                        PlayerAttribute.AGILITY: 2,
                        PlayerAttribute.STRENGTH: -1,
                    }
                )  # Increase agility, decrease strength
            ),
            WeaponDamageTakenEffect[PlayerEntity](
                effect=lambda _: DamageMultiplicativeModifier(
                    multiplier=1.1
                ),  # Increase damage taken by 10%
            ),
        ],
    ),
    "TraitID_HeavyFrame": PlayerTrait(
        id="TraitID_HeavyFrame",
        name="Heavy Frame",
        description="You are larger than average, making you more resilient but also less agile.",
        effects=[
            OnceEffect(
                effect=lambda _: AttributesModifier(
                    attributes={
                        PlayerAttribute.STRENGTH: 2,
                        PlayerAttribute.AGILITY: -1,
                    }
                )  # Increase strength, decrease agility
            ),
            WeaponDamageTakenEffect[PlayerEntity](
                effect=lambda _: DamageMultiplicativeModifier(
                    multiplier=0.9
                ),  # Decrease damage taken by 10%
            ),
        ],
    ),
}
