from modules import item, modifier, weapon
from modules.character import equipment

ITEMS: dict[str, item.Item] = {
    "item_crowbar": item.MeleeWeapon(
        id="item_crowbar",
        name="Crowbar",
        description="A sturdy piece of metal. Good for prying or hitting.",
        max_hit_points=50,
        tags=["tool", "weapon"],
        type=weapon.MeleeType.BLUNT,
        damage=5,
        slots=[
            equipment.HoldableSlot.RIGHT_HAND,
            equipment.HoldableSlot.LEFT_HAND,
        ],
        is_two_handed=True,
    ),
    "item_pistol": item.RangedWeapon(
        id="item_pistol",
        name="9mm Pistol",
        description="Standard issue, reliable.",
        max_hit_points=30,
        tags=["weapon", "firearm"],
        type=weapon.RangedType.PISTOL,
        damage=10,
        range=5,
        slots=[
            equipment.HoldableSlot.RIGHT_HAND,
            equipment.HoldableSlot.LEFT_HAND,
        ],
        is_two_handed=False,
    ),
    "item_apartment_key": item.Holdable(
        id="item_apartment_key",
        name="Apartment Key",
        description="A key to apartment 3B.",
        max_hit_points=10,
        slots=[
            equipment.HoldableSlot.RIGHT_HAND,
            equipment.HoldableSlot.LEFT_HAND,
        ],
        is_two_handed=False,
        tags=["key", "accessory"],
    ),
    "item_canned_beans": item.Consumable(
        id="item_canned_beans",
        name="Canned Beans",
        description="A sad, but filling meal.",
        max_hit_points=5,
        tags=["food", "consumable"],
        slots=[
            equipment.HoldableSlot.RIGHT_HAND,
            equipment.HoldableSlot.LEFT_HAND,
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
        max_hit_points=15,
        tags=["clothing", "armor"],
        slots=[equipment.ArmorSlot.TORSO],
        defense=2,
    ),
    "item_first_aid_kit": item.Appliable(
        id="item_first_aid_kit",
        name="First Aid Kit",
        description="Contains bandages and antiseptic.",
        max_hit_points=20,
        tags=["medical", "appliable"],
        slots=[
            equipment.HoldableSlot.RIGHT_HAND,
            equipment.HoldableSlot.LEFT_HAND,
        ],
        is_two_handed=False,
        modifiers=[
            modifier.HPAdjustment(
                amount=20,
            )
        ],
    ),
}
