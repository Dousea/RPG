from modules.character.equipment import CharacterArmorSlot, CharacterHoldableSlot
from modules.entity.item import ItemEntity
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

# Our rule: below this share of its max hit points an item reads as damaged
# rather than worn, so the narrator gets a word, never the number.
ITEM_WORN_MIN_FRACTION = 0.5


def item_condition_word(entity: ItemEntity) -> str:
    """The item's hit points as intact, worn, damaged or broken."""
    if entity.hit_points >= entity.max_hit_points:
        return "intact"
    if entity.hit_points <= 0:
        return "broken"
    if entity.hit_points >= entity.max_hit_points * ITEM_WORN_MIN_FRACTION:
        return "worn"
    return "damaged"


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
    "item_storage_key": HoldableItem(
        id="item_storage_key",
        name="Storage Room Key",
        description="A worn brass key labeled 'STORAGE' in faded marker.",
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
        modifiers=[],
        hunger_change=-0.35,
        thirst_change=-0.05,
    ),
    "item_water_bottle": ConsumableItem(
        id="item_water_bottle",
        name="Water Bottle",
        description="Half a litre of tap water in a scratched plastic bottle.",
        max_hit_points=5,
        tags=["drink", "consumable", "water"],
        slots=[
            CharacterHoldableSlot.RIGHT_HAND,
            CharacterHoldableSlot.LEFT_HAND,
        ],
        is_two_handed=False,
        modifiers=[],
        thirst_change=-0.45,
    ),
    "item_granola_bar": ConsumableItem(
        id="item_granola_bar",
        name="Granola Bar",
        description="Oats and syrup, flattened into a brick. Dry going down.",
        max_hit_points=3,
        tags=["food", "consumable"],
        slots=[
            CharacterHoldableSlot.RIGHT_HAND,
            CharacterHoldableSlot.LEFT_HAND,
        ],
        is_two_handed=False,
        modifiers=[],
        hunger_change=-0.20,
        # Dry food costs water: it makes the water bottle worth carrying.
        thirst_change=0.05,
    ),
    "item_instant_noodles": ConsumableItem(
        id="item_instant_noodles",
        name="Instant Noodles",
        description="A brick of noodles and a foil sachet of salt.",
        max_hit_points=4,
        tags=["food", "consumable"],
        slots=[
            CharacterHoldableSlot.RIGHT_HAND,
            CharacterHoldableSlot.LEFT_HAND,
        ],
        is_two_handed=False,
        modifiers=[],
        hunger_change=-0.40,
        thirst_change=0.10,
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


def find_item_by_name(name: str) -> BaseItem | None:
    """Resolve a display name (or item id) to a catalog item, case-insensitively.

    The LLM writes item names as prose ("First Aid Kit"), not ids, so every
    action that names an item goes through here.
    """
    needle = name.strip().casefold()
    if not needle:
        return None
    for item_id, item in ITEMS.items():
        if needle in (item_id.casefold(), item.name.casefold()):
            return item
    return None
