from modules.character.equipment import CharacterArmorSlot, CharacterHoldableSlot
from modules.item import (
    AppliableItem,
    ArmorItem,
    BaseItem,
    ConsumableItem,
    HoldableItem,
    MeleeWeaponItem,
    RangedWeaponItem,
)
from modules.modifier import HPModifier
from modules.weapon import MeleeWeaponType, RangedWeaponType

ITEMS: dict[str, BaseItem] = {
    "item_crowbar": MeleeWeaponItem(
        id="item_crowbar",
        name="Crowbar",
        description="A sturdy piece of metal. Good for prying or hitting.",
        max_hit_points=50,
        tags=["tool", "weapon"],
        type=MeleeWeaponType.BLUNT,
        damage=5,
        slots=[
            CharacterHoldableSlot.RIGHT_HAND,
            CharacterHoldableSlot.LEFT_HAND,
        ],
        is_two_handed=True,
    ),
    "item_pistol": RangedWeaponItem(
        id="item_pistol",
        name="9mm Pistol",
        description="Standard issue, reliable.",
        max_hit_points=30,
        tags=["weapon", "firearm"],
        type=RangedWeaponType.PISTOL,
        damage=10,
        range=5,
        slots=[
            CharacterHoldableSlot.RIGHT_HAND,
            CharacterHoldableSlot.LEFT_HAND,
        ],
        is_two_handed=False,
    ),
    "item_apartment_key": HoldableItem(
        id="item_apartment_key",
        name="Apartment Key",
        description="A key to apartment 3B.",
        max_hit_points=10,
        slots=[
            CharacterHoldableSlot.RIGHT_HAND,
            CharacterHoldableSlot.LEFT_HAND,
        ],
        is_two_handed=False,
        tags=["key", "accessory"],
    ),
    "item_canned_beans": ConsumableItem(
        id="item_canned_beans",
        name="Canned Beans",
        description="A sad, but filling meal.",
        max_hit_points=5,
        tags=["food", "consumable"],
        slots=[
            CharacterHoldableSlot.RIGHT_HAND,
            CharacterHoldableSlot.LEFT_HAND,
        ],
        is_two_handed=False,
        modifiers=[
            HPModifier(
                amount=10,
            )
        ],
    ),
    "item_worn_tshirt": ArmorItem(
        id="item_worn_tshirt",
        name="Worn T-Shirt",
        description="Old and comfortable.",
        max_hit_points=15,
        tags=["clothing", "armor"],
        slots=[CharacterArmorSlot.TORSO],
        defense=2,
    ),
    "item_first_aid_kit": AppliableItem(
        id="item_first_aid_kit",
        name="First Aid Kit",
        description="Contains bandages and antiseptic.",
        max_hit_points=20,
        tags=["medical", "appliable"],
        slots=[
            CharacterHoldableSlot.RIGHT_HAND,
            CharacterHoldableSlot.LEFT_HAND,
        ],
        is_two_handed=False,
        modifiers=[
            HPModifier(
                amount=20,
            )
        ],
    ),
}
