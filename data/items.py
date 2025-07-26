from modules import item, modifier, player, weapon

ITEMS: dict[str, item.Item] = {
    "item_crowbar": item.MeleeWeapon(
        id="item_crowbar",
        name="Crowbar",
        description="A sturdy piece of metal. Good for prying or hitting.",
        hit_points=50,
        max_hit_points=50,
        tags=["tool", "weapon"],
        type=weapon.MeleeType.BLUNT,
        damage=5,
        slots=[
            player.HoldableSlot.RIGHT_HAND,
            player.HoldableSlot.LEFT_HAND,
        ],
        is_two_handed=True,
    ),
    "item_pistol": item.RangedWeapon(
        id="item_pistol",
        name="9mm Pistol",
        description="Standard issue, reliable.",
        hit_points=30,
        max_hit_points=30,
        tags=["weapon", "firearm"],
        type=weapon.RangedType.PISTOL,
        damage=10,
        range=5,
        slots=[
            player.HoldableSlot.RIGHT_HAND,
            player.HoldableSlot.LEFT_HAND,
        ],
        is_two_handed=False,
    ),
    "item_apartment_key": item.Holdable(
        id="item_apartment_key",
        name="Apartment Key",
        description="A key to apartment 3B.",
        hit_points=10,
        max_hit_points=10,
        slots=[
            player.HoldableSlot.RIGHT_HAND,
            player.HoldableSlot.LEFT_HAND,
        ],
        is_two_handed=False,
        tags=["key", "accessory"],
    ),
    "item_canned_beans": item.Consumable(
        id="item_canned_beans",
        name="Canned Beans",
        description="A sad, but filling meal.",
        hit_points=5,
        max_hit_points=5,
        tags=["food", "consumable"],
        slots=[
            player.HoldableSlot.RIGHT_HAND,
            player.HoldableSlot.LEFT_HAND,
        ],
        is_two_handed=False,
        modifiers=[
            modifier.HPAdjustment(
                amount=10,
            )
        ],
    ),
    "item_worn_tshirt": item.Armor(
        id="item_worn_tshirt",
        name="Worn T-Shirt",
        description="Old and comfortable.",
        hit_points=15,
        max_hit_points=15,
        tags=["clothing", "armor"],
        slots=[player.ArmorSlot.TORSO],
        defense=2,
    ),
    "item_first_aid_kit": item.Appliable(
        id="item_first_aid_kit",
        name="First Aid Kit",
        description="Contains bandages and antiseptic.",
        hit_points=20,
        max_hit_points=20,
        tags=["medical", "appliable"],
        slots=[
            player.HoldableSlot.RIGHT_HAND,
            player.HoldableSlot.LEFT_HAND,
        ],
        is_two_handed=False,
        modifiers=[
            modifier.HPAdjustment(
                amount=20,
            )
        ],
    ),
}
