from modules import effect, entity, modifier, quest, trait
from modules.character import player, condition

TRAITS: dict[str, trait.Trait] = {
    "TraitID_Hemophobia": trait.Trait(
        id="TraitID_Hemophobia",
        name="Hemophobia",
        description="You are logical and excel in non-violent situations, but the sight of blood and gore can send you into a panic.",
        effects=[
            effect.QuestCompleted(
                condition=lambda event: quest.QuestStyle.NON_VIOLENT in event.styles,
                effect=lambda _: modifier.XPMultiplier(
                    multiplier=1.5
                ),  # Increase XP gain for non-violent quests,
            ),
            effect.ItemApplied[entity.Player](
                condition=lambda event: "medical" in event.item.tags,
                effect=lambda event: (
                    modifier.Conditions(conditions={condition.Condition.PANIC: True})
                    if event.source.attributes[player.Attribute.WILLPOWER] < 5
                    else None
                ),
            ),
        ],
    ),
    "TraitID_SmallFrame": trait.Trait(
        id="TraitID_SmallFrame",
        name="Small Frame",
        description="You are smaller than average, making you more nimble but also more fragile.",
        effects=[
            effect.Once(
                effect=lambda _: modifier.Attributes(
                    attributes={
                        player.Attribute.AGILITY: 2,
                        player.Attribute.STRENGTH: -1,
                    }
                )  # Increase agility, decrease strength
            ),
            effect.WeaponDamageTaken[entity.Player](
                effect=lambda _: modifier.DamageMultiplier(
                    multiplier=1.1
                ),  # Increase damage taken by 10%
            ),
        ],
    ),
    "TraitID_HeavyFrame": trait.Trait(
        id="TraitID_HeavyFrame",
        name="Heavy Frame",
        description="You are larger than average, making you more resilient but also less agile.",
        effects=[
            effect.Once(
                effect=lambda _: modifier.Attributes(
                    attributes={
                        player.Attribute.STRENGTH: 2,
                        player.Attribute.AGILITY: -1,
                    }
                )  # Increase strength, decrease agility
            ),
            effect.WeaponDamageTaken[entity.Player](
                effect=lambda _: modifier.DamageMultiplier(
                    multiplier=0.9
                ),  # Decrease damage taken by 10%
            ),
        ],
    ),
}
