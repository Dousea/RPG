from data import melee as melee_k
from data.clothing.coverage import covered_parts
from data.clothing.items import STARTING_CLOTHES
from data.loot.items import LOOT_ITEMS
from data.world import barriers as barrier_k
from data.zombies.clothing_names import DISPLAY_CLOTHING
from modules.body.parts import BodyLocation
from modules.character.equipment import (
    AnyCharacterEquipmentSlot,
    CharacterArmorSlot,
    CharacterHoldableSlot,
)
from modules.entity.item import ItemEntity
from modules.item import (
    BaseItem,
    ClothingItem,
    ConsumableItem,
    ContainerItem,
    HoldableItem,
    MedicalItem,
    MeleeWeaponItem,
    RangedWeaponItem,
    StackItem,
)
from modules.weapon import RangedWeaponType

# Our rule: below this share of its max hit points an item reads as damaged
# rather than worn, so the narrator gets a word, never the number.
ITEM_WORN_MIN_FRACTION = 0.5

WETNESS_MAX = 100  # clothing
WETNESS_WORD_MIN = 15  # clothing
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


CONDITION_WORDS = frozenset(
    {
        "intact",
        "worn",
        "damaged",
        "broken",
        *(word for _, word in melee_k.CONDITION_WORD_BANDS),
        melee_k.CONDITION_WORD_BADLY_WORN,
        melee_k.CONDITION_WORD_BROKEN,
    }
)
WETNESS_WORDS = frozenset({"damp", "wet", "soaked"})
DESCRIBING_WORDS = CONDITION_WORDS | WETNESS_WORDS


ORTON_OUTFIT_IDS = (  # clothing
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


def _medical(
    item_id: str, name: str, description: str, weight: float, **fields
) -> tuple[str, MedicalItem]:
    return item_id, MedicalItem(
        id=item_id,
        name=name,
        description=description,
        max_hit_points=5,
        tags=["medical"],
        slots=[CharacterHoldableSlot.RIGHT_HAND, CharacterHoldableSlot.LEFT_HAND],
        is_two_handed=False,
        weight=weight,
        **fields,
    )


DIRTY_BANDAGE_ID = "item_dirty_bandage"  # health
DIRTY_RIPPED_SHEETS_ID = "item_dirty_ripped_sheets"  # health
BANDAGE_ID = "item_bandage"  # health
ADHESIVE_BANDAGE_ID = "item_adhesive_bandage"  # health
ALCOHOL_WIPES_ID = "item_alcohol_wipes"  # health
PAINKILLERS_ID = "item_painkillers"  # health

MEDICAL_ITEMS: dict[str, MedicalItem] = dict(  # health
    [
        _medical(
            BANDAGE_ID,
            "Bandage",
            "A clean cloth bandage.",
            0.1,
            bandage_power=4,
            dirty_version=DIRTY_BANDAGE_ID,
        ),
        _medical(
            DIRTY_BANDAGE_ID,
            "Dirty Bandage",
            "A used bandage, stained and stiff.",
            0.1,
            bandage_power=0.5,
            dirty=True,
            reusable_bandage=True,
        ),
        _medical(
            "item_sterilized_bandage",
            "Sterilized Bandage",
            "A bandage soaked in alcohol.",
            0.1,
            bandage_power=4,
            alcoholic=True,
            dirty_version=DIRTY_BANDAGE_ID,
        ),
        _medical(
            ADHESIVE_BANDAGE_ID,
            "Adhesive Bandage",
            "A small sticking plaster.",
            0.05,
            bandage_power=1.5,
        ),
        _medical(
            "item_ripped_sheets",
            "Ripped Sheets",
            "Strips of torn bedsheet.",
            0.1,
            bandage_power=2,
            dirty_version=DIRTY_RIPPED_SHEETS_ID,
        ),
        _medical(
            DIRTY_RIPPED_SHEETS_ID,
            "Dirty Ripped Sheets",
            "Strips of torn sheet, filthy.",
            0.1,
            bandage_power=0.5,
            dirty=True,
            reusable_bandage=True,
        ),
        _medical(
            "item_sterilized_ripped_sheets",
            "Sterilized Ripped Sheets",
            "Strips of torn sheet soaked in alcohol.",
            0.1,
            bandage_power=2,
            alcoholic=True,
            dirty_version=DIRTY_RIPPED_SHEETS_ID,
        ),
        _medical(
            ALCOHOL_WIPES_ID,
            "Alcohol Wipes",
            "Packets of alcohol wipes.",
            0.3,
            alcohol_power=4,
            uses=5,
        ),
        _medical(
            "item_disinfectant",
            "Disinfectant",
            "A bottle of rubbing alcohol.",
            0.7,
            alcohol_power=4,
            uses=3,
        ),
        _medical(
            PAINKILLERS_ID,
            "Painkillers",
            "A bottle of painkillers.",
            0.2,
            painkiller=True,
            uses=10,
        ),
        _medical(
            "item_antibiotics",
            "Antibiotics",
            "A course of antibiotics.",
            0.1,
            reduce_infection_power=50,
        ),
    ]
)

BAG_HIT_POINTS = 20  # carrying-and-loot: not in the spec's rows; any bag's wear
BACK_AND_HAND: list[AnyCharacterEquipmentSlot] = [
    CharacterArmorSlot.SHOULDERS,
    CharacterHoldableSlot.LEFT_HAND,
]
HAND_ONLY: list[AnyCharacterEquipmentSlot] = [CharacterHoldableSlot.LEFT_HAND]


def _bag(
    item_id: str,
    name: str,
    description: str,
    capacity: float,
    weight_reduction: int,
    weight: float,
    *,
    slots: list[AnyCharacterEquipmentSlot] | None = None,
    body_location: BodyLocation | None = None,
    max_item_size: float | None = None,
) -> tuple[str, ContainerItem]:
    return item_id, ContainerItem(
        id=item_id,
        name=name,
        description=description,
        max_hit_points=BAG_HIT_POINTS,
        tags=["bag"],
        weight=weight,
        slots=slots or [],
        capacity=capacity,
        weight_reduction=weight_reduction,
        max_item_size=max_item_size,
        body_location=body_location,
    )


SCHOOLBAG_ID = "item_schoolbag"  # carrying-and-loot

BAGS: dict[str, ContainerItem] = dict(  # carrying-and-loot
    [
        _bag(SCHOOLBAG_ID, "Schoolbag", "A canvas schoolbag.", 15, 70, 1.0, slots=BACK_AND_HAND),
        _bag(
            "item_duffel_bag",
            "Duffel Bag",
            "A zipped duffel bag.",
            18,
            65,
            1.0,
            slots=BACK_AND_HAND,
        ),
        _bag(
            "item_hiking_bag",
            "Hiking Bag",
            "A hiking pack with a frame.",
            20,
            75,
            1.2,
            slots=BACK_AND_HAND,
        ),
        _bag(
            "item_large_hiking_bag",
            "Large Hiking Bag",
            "A big hiking pack.",
            22,
            80,
            1.5,
            slots=BACK_AND_HAND,
        ),
        _bag(
            "item_satchel",
            "Satchel",
            "A shoulder satchel.",
            12,
            65,
            1.0,
            body_location=BodyLocation.SATCHEL,
        ),
        _bag(
            "item_fanny_pack",
            "Fanny Pack",
            "A small pack worn at the front.",
            1,
            85,
            0.2,
            body_location=BodyLocation.FANNYPACKFRONT,
        ),
        _bag("item_suitcase", "Suitcase", "A hard suitcase.", 16, 50, 3.0, slots=HAND_ONLY),
        _bag("item_garbage_bag", "Garbage Bag", "A black bin liner.", 20, 50, 0.1, slots=HAND_ONLY),
        _bag(
            "item_toolbox",
            "Toolbox",
            "A metal toolbox.",
            8,
            50,
            2.0,
            slots=HAND_ONLY,
            max_item_size=2,
        ),
        _bag(
            "item_briefcase",
            "Briefcase",
            "A leather briefcase.",
            8,
            50,
            1.5,
            slots=HAND_ONLY,
            max_item_size=2,
        ),
        _bag(
            "item_tote_bag",
            "Tote Bag",
            "A cloth tote bag.",
            6,
            50,
            0.5,
            slots=HAND_ONLY,
            max_item_size=2,
        ),
        _bag("item_handbag", "Handbag", "A handbag.", 6, 50, 1.0, slots=HAND_ONLY, max_item_size=2),
        _bag("item_plastic_bag", "Plastic Bag", "A carrier bag.", 8, 50, 0.1, slots=HAND_ONLY),
        _bag("item_paper_bag", "Paper Bag", "A paper bag.", 2, 50, 0.1, slots=HAND_ONLY),
    ]
)

STUDY_BINDER = BaseItem(  # world-lore: The binder
    id="item_study_binder",
    name="Study Binder",
    description="A ring binder with the clinic's logo on the cover.",
    max_hit_points=BAG_HIT_POINTS,
    tags=["paper"],
    weight=0.3,
)

ITEMS: dict[str, BaseItem] = {
    "item_crowbar": MeleeWeaponItem(
        id="item_crowbar",
        name="Crowbar",
        description="A sturdy piece of metal. Good for prying or hitting.",
        max_hit_points=50,
        tags=["tool", "weapon", barrier_k.REMOVE_BARRICADE_TAG],  # doors
        damage=5,  # melee: HP in a fight with an NPC
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
        damage=3,  # melee: HP in a fight with an NPC
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
    "item_baseball_bat": MeleeWeaponItem(
        id="item_baseball_bat",
        name="Baseball Bat",
        description="A wooden bat. It swings wide and hits hard, but it takes both hands.",
        max_hit_points=40,
        tags=[
            "tool",
            "weapon",
            melee_k.TAG_REPAIRABLE_WITH_GLUE,
            melee_k.TAG_REPAIRABLE_WITH_TAPE,
        ],  # melee
        damage=melee_k.NPC_BAT_DAMAGE,
        slots=[
            CharacterHoldableSlot.RIGHT_HAND,
            CharacterHoldableSlot.LEFT_HAND,
        ],
        is_two_handed=True,
        categories=(melee_k.CATEGORY_BLUNT,),
        min_damage=0.8,
        max_damage=1.1,
        max_range=1.25,
        critical_chance=40.0,
        crit_dmg_multiplier=2.0,
        max_hit_count=2,
        knockback_on_no_death=True,
        condition_max=15,
        condition_lower_chance=20,
        weight=2.0,
        door_damage=5,
    ),
    "item_frying_pan": MeleeWeaponItem(
        id="item_frying_pan",
        name="Frying Pan",
        description="A heavy iron pan. Light in one hand, but it tires the arm.",
        max_hit_points=30,
        tags=["tool", "weapon"],
        damage=melee_k.NPC_PAN_DAMAGE,
        slots=[CharacterHoldableSlot.RIGHT_HAND],
        is_two_handed=False,
        categories=(melee_k.CATEGORY_SMALL_BLUNT,),
        min_damage=0.3,
        max_damage=0.5,
        max_range=1.1,
        critical_chance=30.0,
        crit_dmg_multiplier=2.0,
        max_hit_count=1,
        knockback_on_no_death=True,
        condition_max=10,
        condition_lower_chance=12,
        weight=1.5,
        endurance_mod=1.3,
        door_damage=3,
        no_maintenance_xp=True,
    ),
    "item_hand_axe": MeleeWeaponItem(
        id="item_hand_axe",
        name="Hand Axe",
        description="A short axe. It crits hard and opens doors fast.",
        max_hit_points=30,
        tags=[
            "tool",
            "weapon",
            melee_k.TAG_SHARPENABLE,
            melee_k.TAG_REPAIRABLE_WITH_TAPE,
            melee_k.TAG_REPAIRABLE_WITH_GLUE,
        ],  # melee
        damage=melee_k.NPC_AXE_DAMAGE,
        slots=[CharacterHoldableSlot.RIGHT_HAND],
        is_two_handed=False,
        categories=(melee_k.CATEGORY_AXE,),
        min_damage=0.7,
        max_damage=1.5,
        max_range=1.1,
        critical_chance=15.0,
        crit_dmg_multiplier=5.0,
        max_hit_count=2,
        knockback_on_no_death=False,
        condition_max=10,
        condition_lower_chance=15,
        weight=1.5,
        door_damage=20,
        sharpness=1.0,
        head_condition=10,
        head_condition_max=10,
        head_condition_lower_chance_multiplier=1.5,
    ),
    "item_pistol": RangedWeaponItem(
        id="item_pistol",
        name="9mm Pistol",
        description="Standard issue, reliable.",
        max_hit_points=30,
        weight=1.5,
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
        weight=0.05,
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
        weight=0.05,
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
        weight=0.8,
        tags=["food", "consumable"],
        slots=[
            CharacterHoldableSlot.RIGHT_HAND,
            CharacterHoldableSlot.LEFT_HAND,
        ],
        is_two_handed=False,
        modifiers=[],
        hunger_change=-0.24,  # status-effects
        unhappy_change=10,  # status-effects
    ),
    "item_water_bottle": ConsumableItem(
        id="item_water_bottle",
        name="Water Bottle",
        description="A litre of tap water in a scratched plastic bottle.",
        max_hit_points=5,
        weight=1.1,
        tags=["drink", "consumable", "water"],
        slots=[
            CharacterHoldableSlot.RIGHT_HAND,
            CharacterHoldableSlot.LEFT_HAND,
        ],
        is_two_handed=False,
        modifiers=[],
        thirst_change=-0.50,  # status-effects
    ),
    "item_granola_bar": ConsumableItem(
        id="item_granola_bar",
        name="Granola Bar",
        description="Oats and syrup, flattened into a brick. Dry going down.",
        max_hit_points=3,
        weight=0.2,
        tags=["food", "consumable"],
        slots=[
            CharacterHoldableSlot.RIGHT_HAND,
            CharacterHoldableSlot.LEFT_HAND,
        ],
        is_two_handed=False,
        modifiers=[],
        hunger_change=-0.15,  # status-effects
    ),
    "item_instant_noodles": ConsumableItem(
        id="item_instant_noodles",
        name="Instant Noodles",
        description="A brick of noodles and a foil sachet of salt.",
        max_hit_points=4,
        weight=0.2,
        tags=["food", "consumable"],
        slots=[
            CharacterHoldableSlot.RIGHT_HAND,
            CharacterHoldableSlot.LEFT_HAND,
        ],
        is_two_handed=False,
        modifiers=[],
        hunger_change=-0.10,  # status-effects
        thirst_change=0.40,  # status-effects
        unhappy_change=20,  # status-effects
    ),
    "item_barbell": HoldableItem(
        id="item_barbell",
        name="Barbell",
        description="A loaded steel bar for lifting.",
        max_hit_points=15,  # skills
        weight=6.0,
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
        max_hit_points=10,  # skills
        weight=5.0,
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
    barrier_k.HAMMER_ITEM_ID: MeleeWeaponItem(
        id=barrier_k.HAMMER_ITEM_ID,
        name="Hammer",
        description="A claw hammer. It drives nails and pries planks off.",
        max_hit_points=20,
        tags=["tool", "weapon", barrier_k.HAMMER_TAG, barrier_k.REMOVE_BARRICADE_TAG],  # doors
        damage=3,
        slots=[CharacterHoldableSlot.RIGHT_HAND],
        is_two_handed=False,
        categories=(melee_k.CATEGORY_SMALL_BLUNT,),
        min_damage=0.5,
        max_damage=1.0,
        max_range=1.1,
        critical_chance=20.0,
        crit_dmg_multiplier=3.0,
        max_hit_count=1,
        knockback_on_no_death=True,
        condition_max=10,
        condition_lower_chance=30,
        weight=1.5,
        door_damage=9,
    ),
    barrier_k.PLANK_ITEM_ID: MeleeWeaponItem(
        id=barrier_k.PLANK_ITEM_ID,
        name="Plank",
        description="A rough length of wood. Nailed across a door, or swung as a club.",
        max_hit_points=10,
        tags=["material", "weapon"],  # doors
        damage=2,
        slots=[CharacterHoldableSlot.RIGHT_HAND, CharacterHoldableSlot.LEFT_HAND],
        is_two_handed=True,
        categories=(melee_k.CATEGORY_BLUNT,),
        min_damage=0.4,
        max_damage=0.6,
        max_range=1.3,
        critical_chance=30.0,
        crit_dmg_multiplier=2.0,
        max_hit_count=2,
        condition_max=10,
        condition_lower_chance=2,
        weight=3.0,
        base_speed=0.9,
        door_damage=5,
        no_maintenance_xp=True,
    ),
    barrier_k.NAILS_ITEM_ID: StackItem(
        id=barrier_k.NAILS_ITEM_ID,
        name="Nails",
        description="A handful of nails.",
        max_hit_points=5,
        tags=["material"],  # doors
        slots=[CharacterHoldableSlot.RIGHT_HAND, CharacterHoldableSlot.LEFT_HAND],
        is_two_handed=False,
        uses=5,
        weight=0.25,
        unit_weight=0.05,
    ),
    "item_study_binder": STUDY_BINDER,
    **MEDICAL_ITEMS,
    **BAGS,
    **LOOT_ITEMS,
    **DISPLAY_CLOTHING,
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
