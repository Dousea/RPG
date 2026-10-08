"""Display names for the generated zombie clothing (zombie-lifecycle).

The generated rows are named "<Noun> - <Variant>"; the rule puts the variant
first, and `OVERRIDES` (by item id) fixes what the rule reads badly.
"""

from dataclasses import replace

from data.zombies.clothing import ZOMBIE_CLOTHING
from modules.item import ClothingItem

_SEPARATOR = " - "

OVERRIDES: dict[str, str] = {
    "item_earring_dangly_sapphire": "Sapphire Dangly Earrings",
    "item_earring_loop_small_gold_top": "Small Looped Gold Earrings",
    "item_earring_loop_small_silver_top": "Small Looped Silver Earrings",
    "item_earring_stud_gold": "Gold Stud Earrings",
    "item_earring_stud_silver": "Silver Stud Earrings",
    "item_jacket_leather_biker_gang_a": "Leather Jacket",
    "item_jacket_leather_biker_gang_b": "Leather Jacket",
    "item_jacket_leather_biker_gang_c": "Leather Jacket",
    "item_vest_leather_biker_gang_a": "Leather Vest",
    "item_vest_leather_biker_gang_b": "Leather Vest",
    "item_vest_leather_biker_gang_c": "Leather Vest",
    "item_shirt_crop_top_tint": "Crop Top",
    "item_necklace_ying_yang": "Yin and Yang Necklace",
    "item_shorts_long_denim": "Long Denim Shorts",
    "item_shorts_long_sport": "Long Sport Shorts",
    "item_tshirt_polo_striped_tint": "Striped Polo Shirt",
    "item_tshirt_polo_tint": "Polo Shirt",
}


def display_name(item_id: str, name: str) -> str:
    """The name a narrator and the screen use for a generated clothing row."""
    if item_id in OVERRIDES:
        return OVERRIDES[item_id]
    noun, separator, variant = name.partition(_SEPARATOR)
    return f"{variant} {noun}" if separator else name


def _displayed(item: ClothingItem) -> ClothingItem:
    name = display_name(item.id, item.name)
    return replace(item, name=name, description=f"{name}.")


DISPLAY_CLOTHING: dict[str, ClothingItem] = {
    item_id: _displayed(item) for item_id, item in ZOMBIE_CLOTHING.items()
}
