from data import melee as melee_k
from data.clothing_coverage import covered_parts
from data.clothing_items import STARTING_CLOTHES
from modules.body import BodyLocation
from modules.character.equipment import CharacterHoldableSlot
from modules.entity.item import ItemEntity
from modules.item import (
    BaseItem,
    ClothingItem,
    ConsumableItem,
    HoldableItem,
    MedicalItem,
    MeleeWeaponItem,
    RangedWeaponItem,
)
from modules.weapon import RangedWeaponType

# Our rule: below this share of its max hit points an item reads as damaged
# rather than worn, so the narrator gets a word, never the number.
ITEM_WORN_MIN_FRACTION = 0.5

WETNESS_MAX = 100  # spec 05
WETNESS_WORD_MIN = 15  # spec 05
WETNESS_WET_MIN = 40  # our band edge; the spec gives only the 15 floor
WETNESS_SOAKED_MIN = 75  # our band edge, as above


def item_condition_word(entity: ItemEntity) -> str:
    """The item's hit points as intact, worn, damaged or broken; a melee weapon by its wear."""
    if isinstance(entity.item, MeleeWeaponItem):
        return melee_k.condition_word(entity.condition, entity.item.condition_max)
    if entity.hit_points >= entity.max_hit_points:
        return "intact"
    if entity.hit_points <= 0:
        return "broken"
    if entity.hit_points >= entity.max_hit_points * ITEM_WORN_MIN_FRACTION:
        return "worn"
    return "damaged"


ORTON_OUTFIT_IDS = (  # spec 05
    "item_tshirt",
    "item_hoodie",
    "item_jeans",
    "item_ankle_socks",
    "item_trainers",
)


def wetness_word(wetness: float) -> str:
    """Empty when the garment is dry enough to ignore, else a word for how wet it is."""
    if wetness < WETNESS_WORD_MIN:
        return ""
    if wetness >= WETNESS_SOAKED_MIN:
        return "soaked"
    if wetness >= WETNESS_WET_MIN:
        return "wet"
    return "damp"


def _medical(item_id: str, name: str, description: str, **fields) -> tuple[str, MedicalItem]:
    return item_id, MedicalItem(
        id=item_id,
        name=name,
        description=description,
        max_hit_points=5,
        tags=["medical"],
        slots=[CharacterHoldableSlot.RIGHT_HAND, CharacterHoldableSlot.LEFT_HAND],
        is_two_handed=False,
        **fields,
    )


DIRTY_BANDAGE_ID = "item_dirty_bandage"  # spec 12
DIRTY_RIPPED_SHEETS_ID = "item_dirty_ripped_sheets"  # spec 12
BANDAGE_ID = "item_bandage"  # spec 12
ADHESIVE_BANDAGE_ID = "item_adhesive_bandage"  # spec 12
ALCOHOL_WIPES_ID = "item_alcohol_wipes"  # spec 12
PAINKILLERS_ID = "item_painkillers"  # spec 12

MEDICAL_ITEMS: dict[str, MedicalItem] = dict(  # spec 12
    [
        _medical(
            BANDAGE_ID,
            "Bandage",
            "A clean cloth bandage.",
            bandage_power=4,
            dirty_version=DIRTY_BANDAGE_ID,
        ),
        _medical(
            DIRTY_BANDAGE_ID,
            "Dirty Bandage",
            "A used bandage, stained and stiff.",
            bandage_power=0.5,
            dirty=True,
            reusable_bandage=True,
        ),
        _medical(
            "item_sterilized_bandage",
            "Sterilized Bandage",
            "A bandage soaked in alcohol.",
            bandage_power=4,
            alcoholic=True,
            dirty_version=DIRTY_BANDAGE_ID,
        ),
        _medical(
            ADHESIVE_BANDAGE_ID,
            "Adhesive Bandage",
            "A small sticking plaster.",
            bandage_power=1.5,
        ),
        _medical(
            "item_ripped_sheets",
            "Ripped Sheets",
            "Strips of torn bedsheet.",
            bandage_power=2,
            dirty_version=DIRTY_RIPPED_SHEETS_ID,
        ),
        _medical(
            DIRTY_RIPPED_SHEETS_ID,
            "Dirty Ripped Sheets",
            "Strips of torn sheet, filthy.",
            bandage_power=0.5,
            dirty=True,
            reusable_bandage=True,
        ),
        _medical(
            "item_sterilized_ripped_sheets",
            "Sterilized Ripped Sheets",
            "Strips of torn sheet soaked in alcohol.",
            bandage_power=2,
            alcoholic=True,
            dirty_version=DIRTY_RIPPED_SHEETS_ID,
        ),
        _medical(
            ALCOHOL_WIPES_ID,
            "Alcohol Wipes",
            "Packets of alcohol wipes.",
            alcohol_power=4,
            uses=5,
        ),
        _medical(
            "item_disinfectant",
            "Disinfectant",
            "A bottle of rubbing alcohol.",
            alcohol_power=4,
            uses=3,
        ),
        _medical(
            PAINKILLERS_ID,
            "Painkillers",
            "A bottle of painkillers.",
            painkiller=True,
            uses=10,
        ),
        _medical(
            "item_antibiotics",
            "Antibiotics",
            "A course of antibiotics.",
            reduce_infection_power=50,
        ),
    ]
)

ITEMS: dict[str, BaseItem] = {
    "item_crowbar": MeleeWeaponItem(
        id="item_crowbar",
        name="Crowbar",
        description="A sturdy piece of metal. Good for prying or hitting.",
        max_hit_points=50,
        tags=["tool", "weapon"],
        damage=5,  # spec 11: HP in a fight with an NPC
        slots=[
            CharacterHoldableSlot.RIGHT_HAND,
            CharacterHoldableSlot.LEFT_HAND,
        ],
        is_two_handed=True,
        categories=(melee_k.CATEGORY_BLUNT,),
        min_damage=0.6,
        max_damage=1.15,
        max_range=1.25,
        critical_chance=20.0,
        crit_dmg_multiplier=2.5,
        max_hit_count=3,
        knockback_on_no_death=True,
        condition_max=15,
        condition_lower_chance=70,
        weight=2.0,
        door_damage=8,
    ),
    "item_kitchen_knife": MeleeWeaponItem(
        id="item_kitchen_knife",
        name="Kitchen Knife",
        description="A sharp chef's knife. Quick, and it ends a fight if it finds the jaw.",
        max_hit_points=20,
        tags=["tool", "weapon"],
        damage=3,  # spec 11: HP in a fight with an NPC
        slots=[CharacterHoldableSlot.RIGHT_HAND],
        is_two_handed=False,
        categories=(melee_k.CATEGORY_SMALL_BLADE,),
        min_damage=0.3,
        max_damage=0.7,
        max_range=0.9,
        critical_chance=25.0,
        crit_dmg_multiplier=4.0,
        max_hit_count=1,
        condition_max=10,
        condition_lower_chance=2,
        weight=0.7,
        is_stab=True,
        door_damage=1,
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
    "item_barbell": HoldableItem(
        id="item_barbell",
        name="Barbell",
        description="A loaded steel bar for lifting.",
        max_hit_points=15,  # spec 08
        tags=["exercise"],
        slots=[
            CharacterHoldableSlot.RIGHT_HAND,
            CharacterHoldableSlot.LEFT_HAND,
        ],
        is_two_handed=True,
    ),
    "item_dumbbell": HoldableItem(
        id="item_dumbbell",
        name="Dumbbell",
        description="A cast-iron hand weight.",
        max_hit_points=10,  # spec 08
        tags=["exercise"],
        slots=[
            CharacterHoldableSlot.RIGHT_HAND,
            CharacterHoldableSlot.LEFT_HAND,
        ],
        is_two_handed=False,
    ),
    "item_tshirt": ClothingItem(
        id="item_tshirt",
        name="T-shirt",
        description="A plain cotton T-shirt.",
        max_hit_points=15,
        tags=["clothing"],
        body_location=BodyLocation.TSHIRT,
        covers=covered_parts("shirt"),
        insulation=0.2,
        wind_resistance=0.05,
        water_resistance=0.0,
        weight=1.0,
    ),
    "item_hoodie": ClothingItem(
        id="item_hoodie",
        name="Hoodie",
        description="A white hoodie, hood down.",
        max_hit_points=15,
        tags=["clothing"],
        body_location=BodyLocation.SWEATER,
        covers=covered_parts("jumper"),
        insulation=0.6,
        wind_resistance=0.25,
        water_resistance=0.0,
        weight=1.0,
        scratch_defense=10,
        neck_protection=0.5,
    ),
    "item_jeans": ClothingItem(
        id="item_jeans",
        name="Jeans",
        description="Faded denim jeans.",
        max_hit_points=15,
        tags=["clothing"],
        body_location=BodyLocation.PANTS,
        covers=covered_parts("trousers"),
        insulation=0.7,
        wind_resistance=0.55,
        water_resistance=0.0,
        weight=1.0,
        scratch_defense=20,
        bite_defense=10,
    ),
    "item_ankle_socks": ClothingItem(
        id="item_ankle_socks",
        name="Ankle socks",
        description="A pair of short cotton socks.",
        max_hit_points=5,
        tags=["clothing"],
        body_location=BodyLocation.SOCKS,
        covers=covered_parts("shoes"),
        insulation=0.15,
        wind_resistance=0.1,
        water_resistance=0.0,
        weight=0.1,
    ),
    "item_trainers": ClothingItem(
        id="item_trainers",
        name="Trainers",
        description="Worn running shoes.",
        max_hit_points=24,
        tags=["clothing"],
        body_location=BodyLocation.SHOES,
        covers=covered_parts("shoes"),
        insulation=0.45,
        wind_resistance=0.3,
        water_resistance=0.0,
        weight=1.0,
        scratch_defense=10,
        stomp_power=1.8,
    ),
    "item_black_jacket": ClothingItem(
        id="item_black_jacket",
        name="Black jacket",
        description="A black leather jacket.",
        max_hit_points=20,
        tags=["clothing"],
        body_location=BodyLocation.JACKET,
        covers=covered_parts("jacket"),
        insulation=0.4,
        wind_resistance=0.6,
        water_resistance=0.4,
        weight=2.0,
        scratch_defense=40,
        bite_defense=20,
        neck_protection=0.5,
    ),
    **MEDICAL_ITEMS,
    **STARTING_CLOTHES,
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
