from modules.character.player import PlayerAttribute, PlayerPerk
from modules.effect import (
    OnceEffect,
    QuestCompletedEffect,
    WeaponDamageDealtEffect,
    WeaponDamageTakenEffect,
)
from modules.entity.player import PlayerEntity
from modules.item import RangedWeaponItem
from modules.modifier import (
    AttributesModifier,
    DamageMultiplicativeModifier,
    XPMultiplicativeModifier,
)
from modules.quest import QuestStyle

PERKS: dict[str, PlayerPerk] = {
    "PerkID_GunSlinger": PlayerPerk(
        id="PerkID_GunSlinger",
        name="Gun Slinger",
        description="You have a natural affinity for firearms, increasing your accuracy and damage with ranged weapons.",
        effects=[
            OnceEffect(
                effect=lambda _: AttributesModifier(
                    attributes={
                        PlayerAttribute.AGILITY: 3,
                        PlayerAttribute.STRENGTH: 1,
                    }
                )
            ),  # Increase agility and strength for better firearm handling
            WeaponDamageDealtEffect[PlayerEntity](
                condition=lambda event: isinstance(event.weapon, RangedWeaponItem),
                effect=lambda _: DamageMultiplicativeModifier(
                    multiplier=1.2
                ),  # Increase damage dealt with ranged weapons by 20%
            ),
            WeaponDamageTakenEffect[PlayerEntity](
                condition=lambda event: isinstance(event.weapon, RangedWeaponItem),
                effect=lambda _: DamageMultiplicativeModifier(
                    multiplier=0.9
                ),  # Reduce damage taken from ranged weapons by 10%
            ),
        ],
    ),
    "PerkID_Stealthy": PlayerPerk(
        id="PerkID_Stealthy",
        name="Stealthy",
        description="You are adept at moving silently and avoiding detection, making you a master of stealth.",
        effects=[
            OnceEffect(
                effect=lambda _: AttributesModifier(
                    attributes={
                        PlayerAttribute.AGILITY: 4,
                        PlayerAttribute.STRENGTH: -1,
                    }
                )  # Increase agility, decrease strength for stealth
            ),
        ],
    ),
    "PerkID_Charismatic": PlayerPerk(
        id="PerkID_Charismatic",
        name="Charismatic",
        description="Your charm and charisma make you a natural leader, improving your interactions with others.",
        effects=[
            OnceEffect(
                effect=lambda _: AttributesModifier(
                    attributes={
                        PlayerAttribute.CHARISMA: 5,
                        PlayerAttribute.INTELLIGENCE: 2,
                    }
                )  # Increase charisma and intelligence
            ),
            QuestCompletedEffect(
                condition=lambda event: QuestStyle.SOCIAL in event.styles,
                effect=lambda _: XPMultiplicativeModifier(
                    multiplier=1.5
                ),  # Increase XP gain for social quests
            ),
        ],
    ),
}
