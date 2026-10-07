"""Foods, drinks and melee weapons that loot tables can drop (spec 25)."""

from typing import NamedTuple

from data import barriers as barrier_k
from data import melee as melee_k
from modules.character.equipment import CharacterHoldableSlot
from modules.item import BaseItem, ConsumableItem, MeleeWeaponItem

FOOD_HIT_POINTS = 5  # spec 25: not in the spec's rows; any food's wear
WEAPON_HIT_POINTS = 20  # spec 25: not in the spec's rows; any new weapon's wear
BOTH_HANDS = [CharacterHoldableSlot.RIGHT_HAND, CharacterHoldableSlot.LEFT_HAND]
ONE_HAND = [CharacterHoldableSlot.RIGHT_HAND]


class FoodRow(NamedTuple):
    item_id: str
    name: str
    description: str
    weight: float  # kg, full
    hunger: float  # on the stats' 0-1 scale, negative lowers
    thirst: float
    unhappy: float  # points
    stress: float = 0.0
    drink: bool = False


FOOD_ROWS = (  # spec 25: New items
    FoodRow("item_canned_soup", "Canned Soup", "A tin of vegetable soup.", 0.8, -0.25, -0.04, 0),
    FoodRow("item_canned_tuna", "Canned Tuna", "A small tin of tuna.", 0.3, -0.18, 0, 0),
    FoodRow("item_canned_corn", "Canned Corn", "A tin of sweetcorn.", 0.8, -0.16, -0.04, 0),
    FoodRow("item_canned_peaches", "Canned Peaches", "A tin of peaches.", 0.8, -0.15, 0, -10),
    FoodRow("item_canned_chili", "Canned Chili", "A tin of chili.", 0.8, -0.16, 0, 0),
    FoodRow("item_canned_sardines", "Canned Sardines", "A flat tin of sardines.", 0.3, -0.14, 0, 0),
    FoodRow("item_canned_bolognese", "Canned Bolognese", "A tin of meat sauce.", 0.8, -0.24, 0, 0),
    FoodRow(
        "item_canned_carrots", "Canned Carrots", "A tin of sliced carrots.", 0.8, -0.12, -0.04, 0
    ),
    FoodRow(
        "item_canned_corned_beef", "Canned Corned Beef", "A tin of corned beef.", 0.8, -0.24, 0, 0
    ),
    FoodRow(
        "item_canned_fruit_cocktail",
        "Canned Fruit Cocktail",
        "A tin of mixed fruit in syrup.",
        0.8,
        -0.15,
        0,
        -10,
    ),
    FoodRow(
        "item_canned_fruit_beverage",
        "Canned Fruit Beverage",
        "A tin of fruit drink.",
        0.8,
        -0.15,
        -0.85,
        -10,
        drink=True,
    ),
    FoodRow(
        "item_canned_condensed_milk",
        "Canned Condensed Milk",
        "A tin of sweet condensed milk.",
        0.8,
        -0.10,
        -0.10,
        0,
    ),
    FoodRow(
        "item_canned_mushroom_soup",
        "Canned Mushroom Soup",
        "A tin of mushroom soup.",
        0.8,
        -0.10,
        -0.04,
        0,
    ),
    FoodRow("item_canned_peas", "Canned Peas", "A tin of peas.", 0.8, -0.16, -0.03, 0),
    FoodRow(
        "item_canned_pineapple", "Canned Pineapple", "A tin of pineapple rings.", 0.8, -0.15, 0, -10
    ),
    FoodRow(
        "item_canned_potatoes", "Canned Potatoes", "A tin of boiled potatoes.", 0.8, -0.18, -0.07, 0
    ),
    FoodRow(
        "item_canned_tomatoes",
        "Canned Tomatoes",
        "A tin of chopped tomatoes.",
        0.8,
        -0.12,
        -0.08,
        0,
    ),
    FoodRow("item_crackers", "Crackers", "A sleeve of dry crackers.", 0.1, -0.05, 0, 0),
    FoodRow("item_chocolate_bar", "Chocolate Bar", "A bar of milk chocolate.", 0.2, -0.20, 0, -10),
    FoodRow("item_crisps", "Crisps", "A bag of salted crisps.", 0.2, -0.15, 0, -5),
    FoodRow(
        "item_soda_can",
        "Soda Can",
        "A can of fizzy soda.",
        0.3 + 0.3,
        -0.036,
        -0.09,
        -3,
        drink=True,
    ),
    FoodRow(
        "item_juice_box",
        "Juice Box",
        "A carton of apple juice with a straw.",
        0.1 + 0.2,
        -0.02,
        -0.06,
        -10,
        stress=-0.04,
        drink=True,
    ),
)


def _food(row: FoodRow) -> ConsumableItem:
    return ConsumableItem(
        id=row.item_id,
        name=row.name,
        description=row.description,
        max_hit_points=FOOD_HIT_POINTS,
        weight=row.weight,
        tags=["drink" if row.drink else "food", "consumable"],
        slots=list(BOTH_HANDS),
        is_two_handed=False,
        modifiers=[],
        hunger_change=row.hunger,
        thirst_change=row.thirst,
        unhappy_change=row.unhappy,
        stress_change=row.stress,
    )


NPC_ROLLING_PIN_DAMAGE = 2  # spec 25: max(1, round(5 x mean / 0.875))
NPC_CLEAVER_DAMAGE = 3  # spec 25
NPC_SCREWDRIVER_DAMAGE = 3  # spec 25
NPC_WRENCH_DAMAGE = 4  # spec 25
NPC_PIPE_WRENCH_DAMAGE = 4  # spec 25
NPC_TIRE_IRON_DAMAGE = 4  # spec 25
NPC_SHOVEL_DAMAGE = 8  # spec 25
NPC_SLEDGEHAMMER_DAMAGE = 14  # spec 25

_GLUE_AND_TAPE = [melee_k.TAG_REPAIRABLE_WITH_GLUE, melee_k.TAG_REPAIRABLE_WITH_TAPE]

WEAPONS: dict[str, MeleeWeaponItem] = {  # spec 25: New items
    "item_rolling_pin": MeleeWeaponItem(
        id="item_rolling_pin",
        name="Rolling Pin",
        description="A wooden rolling pin. Light, and a poor club.",
        max_hit_points=WEAPON_HIT_POINTS,
        tags=["tool", "weapon", melee_k.TAG_REPAIRABLE_WITH_GLUE],
        damage=NPC_ROLLING_PIN_DAMAGE,
        slots=list(ONE_HAND),
        is_two_handed=False,
        categories=(melee_k.CATEGORY_SMALL_BLUNT,),
        min_damage=0.2,
        max_damage=0.5,
        max_range=1.1,
        critical_chance=15.0,
        crit_dmg_multiplier=2.0,
        max_hit_count=2,
        knockback_on_no_death=True,
        condition_max=8,
        condition_lower_chance=14,
        weight=1.5,
        endurance_mod=1.4,
        door_damage=5,
        no_maintenance_xp=True,
    ),
    "item_meat_cleaver": MeleeWeaponItem(
        id="item_meat_cleaver",
        name="Meat Cleaver",
        description="A broad butcher's blade.",
        max_hit_points=WEAPON_HIT_POINTS,
        tags=["tool", "weapon", melee_k.TAG_SHARPENABLE],
        damage=NPC_CLEAVER_DAMAGE,
        slots=list(ONE_HAND),
        is_two_handed=False,
        categories=(melee_k.CATEGORY_AXE,),
        min_damage=0.4,
        max_damage=0.8,
        max_range=1.0,
        critical_chance=15.0,
        crit_dmg_multiplier=5.0,
        max_hit_count=2,
        knockback_on_no_death=False,
        condition_max=10,
        condition_lower_chance=15,
        weight=1.0,
        door_damage=5,
        sharpness=1.0,
    ),
    "item_screwdriver": MeleeWeaponItem(
        id="item_screwdriver",
        name="Screwdriver",
        description="A flat-head screwdriver. It stabs.",
        max_hit_points=WEAPON_HIT_POINTS,
        tags=["tool", "weapon"],
        damage=NPC_SCREWDRIVER_DAMAGE,
        slots=list(ONE_HAND),
        is_two_handed=False,
        categories=(melee_k.CATEGORY_SMALL_BLADE,),
        min_damage=0.3,
        max_damage=0.7,
        max_range=0.85,
        critical_chance=10.0,
        crit_dmg_multiplier=10.0,
        max_hit_count=1,
        knockback_on_no_death=False,
        condition_max=10,
        condition_lower_chance=6,
        weight=0.5,
        is_stab=True,
        door_damage=1,
    ),
    "item_wrench": MeleeWeaponItem(
        id="item_wrench",
        name="Wrench",
        description="A steel spanner.",
        max_hit_points=WEAPON_HIT_POINTS,
        tags=["tool", "weapon"],
        damage=NPC_WRENCH_DAMAGE,
        slots=list(ONE_HAND),
        is_two_handed=False,
        categories=(melee_k.CATEGORY_SMALL_BLUNT,),
        min_damage=0.5,
        max_damage=1.0,
        max_range=1.1,
        critical_chance=20.0,
        crit_dmg_multiplier=2.0,
        max_hit_count=2,
        knockback_on_no_death=False,
        condition_max=9,
        condition_lower_chance=15,
        weight=1.0,
        door_damage=10,
    ),
    "item_pipe_wrench": MeleeWeaponItem(
        id="item_pipe_wrench",
        name="Pipe Wrench",
        description="A heavy adjustable wrench.",
        max_hit_points=WEAPON_HIT_POINTS,
        tags=["tool", "weapon"],
        damage=NPC_PIPE_WRENCH_DAMAGE,
        slots=list(ONE_HAND),
        is_two_handed=False,
        categories=(melee_k.CATEGORY_SMALL_BLUNT,),
        min_damage=0.5,
        max_damage=1.0,
        max_range=1.1,
        critical_chance=25.0,
        crit_dmg_multiplier=2.0,
        max_hit_count=2,
        knockback_on_no_death=False,
        condition_max=10,
        condition_lower_chance=25,
        weight=1.5,
        door_damage=10,
    ),
    "item_tire_iron": MeleeWeaponItem(
        id="item_tire_iron",
        name="Tire Iron",
        description="An L-shaped iron bar. It pries as well as it hits.",
        max_hit_points=WEAPON_HIT_POINTS,
        tags=["tool", "weapon", barrier_k.REMOVE_BARRICADE_TAG],
        damage=NPC_TIRE_IRON_DAMAGE,
        slots=list(ONE_HAND),
        is_two_handed=False,
        categories=(melee_k.CATEGORY_SMALL_BLUNT,),
        min_damage=0.5,
        max_damage=1.0,
        max_range=1.2,
        critical_chance=30.0,
        crit_dmg_multiplier=2.0,
        max_hit_count=2,
        knockback_on_no_death=False,
        condition_max=10,
        condition_lower_chance=10,
        weight=1.5,
        base_speed=0.95,
        door_damage=1,
    ),
    "item_shovel": MeleeWeaponItem(
        id="item_shovel",
        name="Shovel",
        description="A long-handled spade. It takes both hands.",
        max_hit_points=WEAPON_HIT_POINTS,
        tags=["tool", "weapon", *_GLUE_AND_TAPE],
        damage=NPC_SHOVEL_DAMAGE,
        slots=list(BOTH_HANDS),
        is_two_handed=True,
        categories=(melee_k.CATEGORY_BLUNT,),
        min_damage=0.8,
        max_damage=1.9,
        max_range=1.6,
        critical_chance=40.0,
        crit_dmg_multiplier=2.0,
        max_hit_count=3,
        knockback_on_no_death=True,
        condition_max=10,
        condition_lower_chance=10,
        weight=2.0,
        base_speed=0.8,
        door_damage=10,
        head_condition=10,
        head_condition_max=10,
    ),
    "item_sledgehammer": MeleeWeaponItem(
        id="item_sledgehammer",
        name="Sledgehammer",
        description="A long iron-headed hammer. It wears out the swinger.",
        max_hit_points=WEAPON_HIT_POINTS,
        tags=["tool", "weapon", *_GLUE_AND_TAPE],
        damage=NPC_SLEDGEHAMMER_DAMAGE,
        slots=list(BOTH_HANDS),
        is_two_handed=True,
        categories=(melee_k.CATEGORY_BLUNT,),
        min_damage=2.0,
        max_damage=3.0,
        max_range=1.35,
        critical_chance=0.0,
        crit_dmg_multiplier=2.0,
        max_hit_count=3,
        knockback_on_no_death=True,
        condition_max=10,
        condition_lower_chance=40,
        weight=6.0,
        endurance_mod=4.0,
        base_speed=0.9,
        door_damage=40,
        head_condition=10,
        head_condition_max=10,
    ),
}

LOOT_ITEMS: dict[str, BaseItem] = {
    **{row.item_id: _food(row) for row in FOOD_ROWS},
    **WEAPONS,
}
