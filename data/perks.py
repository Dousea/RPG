from modules import effect, event, item, modifier, perk, player, quest

PERKS: dict[str, perk.Perk] = {
    "PerkID_GunSlinger": perk.Perk(
        id="PerkID_GunSlinger",
        name="Gun Slinger",
        description="You have a natural affinity for firearms, increasing your accuracy and damage with ranged weapons.",
        effects=[
            effect.Once(
                effect=lambda _: modifier.Attributes(
                    attributes={
                        player.Attribute.AGILITY: 3,
                        player.Attribute.STRENGTH: 1,
                    }
                )
            ),  # Increase agility and strength for better firearm handling
            effect.Event[event.WeaponDealDamage](
                condition=lambda event: isinstance(event.weapon, item.RangedWeapon),
                effect=lambda _: modifier.DamageMultiplier(
                    multiplier=1.2
                ),  # Increase damage dealt with ranged weapons by 20%
            ),
            effect.Event[event.WeaponTakeDamage](
                condition=lambda event: isinstance(event.weapon, item.RangedWeapon),
                effect=lambda _: modifier.DamageMultiplier(
                    multiplier=0.9
                ),  # Reduce damage taken from ranged weapons by 10%
            ),
        ],
    ),
    "PerkID_Stealthy": perk.Perk(
        id="PerkID_Stealthy",
        name="Stealthy",
        description="You are adept at moving silently and avoiding detection, making you a master of stealth.",
        effects=[
            effect.Once(
                effect=lambda _: modifier.Attributes(
                    attributes={
                        player.Attribute.AGILITY: 4,
                        player.Attribute.STRENGTH: -1,
                    }
                )  # Increase agility, decrease strength for stealth
            ),
        ],
    ),
    "PerkID_Charismatic": perk.Perk(
        id="PerkID_Charismatic",
        name="Charismatic",
        description="Your charm and charisma make you a natural leader, improving your interactions with others.",
        effects=[
            effect.Once(
                effect=lambda _: modifier.Attributes(
                    attributes={
                        player.Attribute.CHARISMA: 5,
                        player.Attribute.INTELLIGENCE: 2,
                    }
                )  # Increase charisma and intelligence
            ),
            effect.Event[event.QuestCompletion](
                condition=lambda event: quest.QuestStyle.SOCIAL in event.styles,
                effect=lambda _: modifier.XPMultiplier(
                    multiplier=1.5
                ),  # Increase XP gain for social quests
            ),
        ],
    ),
}
