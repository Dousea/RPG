"""Container sizes, the loot roll's numbers and the layout of the rooms (spec 25)."""

from typing import NamedTuple

from data.items import ITEMS
from modules.entity.item import ItemEntity
from modules.world.room import ContainerEntity, RoomEntity

ROLL_DENOMINATOR = 10000  # spec 25: a roll is a whole number below this
JUNK_CHANCE_MULT = 1.4  # spec 25: times the chance on a junk list
CHANCE_PERCENT_SCALE = 100  # spec 25: a table chance is a percent
RANDOM_CONDITION_PCT = 40  # spec 25: percent of non-shop spawns with a random condition
RANDOM_USES_PCT = 40  # spec 25: percent of non-shop spawns with random uses
PERCENT_DENOMINATOR = 100  # spec 25: a percent draw is a whole number below this

DEFAULT_CONTAINER_CAPACITY = 50  # spec 25: kg
FREEZER_CAPACITY = 15  # spec 25: kg
CORPSE_CAPACITY = 12  # spec 25: kg


class ContainerSpec(NamedTuple):
    """One container of a room layout: `fixed` items replace the table, otherwise `source` names its table."""

    container_id: str
    name: str
    kind: str
    aliases: tuple[str, ...]
    source: tuple[str, str] | None = None
    fixed: tuple[str, ...] = ()
    capacity: float = DEFAULT_CONTAINER_CAPACITY


class RoomSpec(NamedTuple):
    room_id: str
    name: str
    kind: str
    aliases: tuple[str, ...]
    containers: tuple[ContainerSpec, ...]


FIRST_AID_KIT_CONTENTS = (  # spec 25: the hallway's first-aid cabinet
    "item_bandage",
    "item_bandage",
    "item_adhesive_bandage",
    "item_alcohol_wipes",
    "item_painkillers",
)
BASEMENT_STORAGE_CONTENTS = (  # spec 25: the basement's storage shelves
    "item_hammer",
    "item_nails",
    "item_plank",
    "item_plank",
    "item_hand_axe",
)
KITCHEN_COUNTER_CONTENTS = (  # spec 25: the home kitchen counter
    "item_canned_beans",
    "item_water_bottle",
    "item_kitchen_knife",
    "item_frying_pan",
)
WARDROBE_CONTENTS = ("item_black_jacket", "item_schoolbag")  # spec 25: the home wardrobe

ROOM_LAYOUTS: dict[str, tuple[RoomSpec, ...]] = {  # spec 25
    "zone_home": (
        RoomSpec(
            "kitchen",
            "kitchen",
            "kitchen",
            ("kitchenette",),
            (
                ContainerSpec(
                    "kitchen_counter",
                    "kitchen counter",
                    "counter",
                    ("counter", "worktop"),
                    fixed=KITCHEN_COUNTER_CONTENTS,
                ),
                ContainerSpec(
                    "kitchen_cupboards",
                    "kitchen cupboards",
                    "cupboards",
                    ("cupboards", "cupboard"),
                    source=("kitchen", "overhead"),
                ),
                ContainerSpec(
                    "home_fridge", "fridge", "fridge", ("refrigerator",), source=("all", "fridge")
                ),
                ContainerSpec(
                    "home_freezer",
                    "freezer",
                    "freezer",
                    (),
                    source=("kitchen", "freezer"),
                    capacity=FREEZER_CAPACITY,
                ),
            ),
        ),
        RoomSpec(
            "bedroom",
            "bedroom",
            "bedroom",
            ("bed room",),
            (
                ContainerSpec(
                    "wardrobe",
                    "wardrobe",
                    "wardrobe",
                    ("closet",),
                    fixed=WARDROBE_CONTENTS,
                ),
                ContainerSpec(
                    "dresser",
                    "dresser",
                    "dresser",
                    ("drawers", "chest of drawers"),
                    source=("bedroom", "dresser"),
                ),
                ContainerSpec(
                    "bedside_table",
                    "bedside table",
                    "sidetable",
                    ("nightstand", "bedside"),
                    source=("bedroom", "sidetable"),
                ),
            ),
        ),
        RoomSpec(
            "bathroom",
            "bathroom",
            "bathroom",
            ("washroom",),
            (
                ContainerSpec(
                    "medicine_cabinet",
                    "medicine cabinet",
                    "medicine",
                    ("cabinet", "medicine chest"),
                    source=("bathroom", "medicine"),
                ),
                ContainerSpec(
                    "bathroom_counter",
                    "bathroom counter",
                    "counter",
                    ("counter", "vanity"),
                    source=("bathroom", "counter"),
                ),
            ),
        ),
        RoomSpec(
            "living_room",
            "living room",
            "livingroom",
            ("lounge", "sitting room"),
            (
                ContainerSpec(
                    "side_table",
                    "side table",
                    "sidetable",
                    ("table",),
                    source=("livingroom", "sidetable"),
                ),
                ContainerSpec(
                    "living_room_shelves",
                    "living room shelves",
                    "shelves",
                    ("shelves", "bookshelf"),
                    source=("livingroom", "shelves"),
                ),
            ),
        ),
    ),
    "zone_building": (
        RoomSpec(
            "hallway",
            "hallway",
            "hall",
            ("corridor",),
            (
                ContainerSpec(
                    "first_aid_cabinet",
                    "first-aid cabinet",
                    "medicine",
                    ("cabinet", "first aid cabinet", "first aid kit", "first-aid kit"),
                    fixed=FIRST_AID_KIT_CONTENTS,
                ),
            ),
        ),
        RoomSpec(
            "laundry_room",
            "laundry room",
            "laundry",
            ("laundry",),
            (
                ContainerSpec(
                    "laundry_counter",
                    "laundry counter",
                    "counter",
                    ("counter",),
                    source=("laundry", "counter"),
                ),
            ),
        ),
        RoomSpec(
            "basement",
            "basement",
            "storageunit",
            ("cellar",),
            (
                ContainerSpec(
                    "storage_shelves",
                    "storage shelves",
                    "shelves",
                    ("shelves",),
                    fixed=BASEMENT_STORAGE_CONTENTS,
                ),
                ContainerSpec(
                    "tool_cabinet",
                    "tool cabinet",
                    "toolcabinet",
                    ("cabinet",),
                    source=("storageunit", "toolcabinet"),
                ),
            ),
        ),
    ),
    "zone_bodega": (
        RoomSpec(
            "shop_floor",
            "shop floor",
            "cornerstore",
            ("shop", "shopfront"),
            (
                ContainerSpec(
                    "till_counter",
                    "till counter",
                    "counter",
                    ("counter", "till"),
                    source=("cornerstore", "counter"),
                ),
                ContainerSpec(
                    "store_fridge",
                    "store fridge",
                    "fridge",
                    ("fridge", "cooler"),
                    source=("cornerstore", "fridge"),
                ),
                ContainerSpec(
                    "snack_shelves",
                    "snack shelves",
                    "shelves",
                    ("shelves",),
                    source=("cornerstore", "shelves"),
                ),
                ContainerSpec(
                    "drinks_shelves",
                    "drinks shelves",
                    "shelves",
                    ("shelves",),
                    source=("cornerstore", "shelves"),
                ),
            ),
        ),
        RoomSpec(
            "storeroom",
            "storeroom",
            "cornerstorestorage",
            ("back room", "stockroom"),
            (
                ContainerSpec(
                    "stock_crates",
                    "stock crates",
                    "crate",
                    ("crates", "crate"),
                    source=("cornerstorestorage", "other"),
                ),
            ),
        ),
    ),
}


def _c(
    container_id: str,
    name: str,
    kind: str,
    aliases: tuple[str, ...],
    source: tuple[str, str],
    capacity: float = DEFAULT_CONTAINER_CAPACITY,
) -> ContainerSpec:
    return ContainerSpec(container_id, name, kind, aliases, source=source, capacity=capacity)


def _flat_rooms(prefix: str, *, vacant: bool) -> tuple[RoomSpec, ...]:
    """The apartment's rooms stocked from tables; the vacant flat keeps only four of its containers."""
    kitchen = [
        _c(
            f"{prefix}_kitchen_counter",
            "kitchen counter",
            "counter",
            ("counter", "worktop"),
            ("kitchen", "counter"),
        ),
        _c(
            f"{prefix}_kitchen_cupboards",
            "kitchen cupboards",
            "cupboards",
            ("cupboards", "cupboard"),
            ("kitchen", "overhead"),
        ),
    ]
    bedroom = [
        _c(f"{prefix}_wardrobe", "wardrobe", "wardrobe", ("closet",), ("bedroom", "wardrobe"))
    ]
    bathroom = [
        _c(
            f"{prefix}_medicine_cabinet",
            "medicine cabinet",
            "medicine",
            ("cabinet", "medicine chest"),
            ("bathroom", "medicine"),
        )
    ]
    living: list[ContainerSpec] = []
    if not vacant:
        kitchen += [
            _c(f"{prefix}_fridge", "fridge", "fridge", ("refrigerator",), ("all", "fridge")),
            _c(
                f"{prefix}_freezer",
                "freezer",
                "freezer",
                (),
                ("kitchen", "freezer"),
                FREEZER_CAPACITY,
            ),
        ]
        bedroom += [
            _c(
                f"{prefix}_dresser",
                "dresser",
                "dresser",
                ("drawers", "chest of drawers"),
                ("bedroom", "dresser"),
            ),
            _c(
                f"{prefix}_bedside_table",
                "bedside table",
                "sidetable",
                ("nightstand", "bedside"),
                ("bedroom", "sidetable"),
            ),
        ]
        bathroom += [
            _c(
                f"{prefix}_bathroom_counter",
                "bathroom counter",
                "counter",
                ("counter", "vanity"),
                ("bathroom", "counter"),
            )
        ]
        living = [
            _c(
                f"{prefix}_side_table",
                "side table",
                "sidetable",
                ("table",),
                ("livingroom", "sidetable"),
            ),
            _c(
                f"{prefix}_living_room_shelves",
                "living room shelves",
                "shelves",
                ("shelves", "bookshelf"),
                ("livingroom", "shelves"),
            ),
        ]
    return (
        RoomSpec("kitchen", "kitchen", "kitchen", ("kitchenette",), tuple(kitchen)),
        RoomSpec("bedroom", "bedroom", "bedroom", ("bed room",), tuple(bedroom)),
        RoomSpec("bathroom", "bathroom", "bathroom", ("washroom",), tuple(bathroom)),
        RoomSpec(
            "living_room", "living room", "livingroom", ("lounge", "sitting room"), tuple(living)
        ),
    )


_COUNTER = ("counter",)
_SHELVES = ("shelves", "shelf unit")
_FRIDGE = ("fridge",)
_CRATES = ("crates", "crate")
_DESK = ("desk",)

ROOM_LAYOUTS.update(  # spec 25: The rooms
    {
        "zone_flat_vacant": _flat_rooms("vacant", vacant=True),
        "zone_flat_tenant": _flat_rooms("tenant", vacant=False),
        "zone_pharmacy": (
            RoomSpec(
                "shop_floor",
                "shop floor",
                "pharmacy",
                ("shop", "shopfront"),
                (
                    _c(
                        "pharmacy_counter",
                        "pharmacy counter",
                        "counter",
                        _COUNTER,
                        ("pharmacy", "counter"),
                    ),
                    _c(
                        "pharmacy_left_shelves",
                        "left shelves",
                        "shelves",
                        _SHELVES,
                        ("pharmacy", "shelves"),
                    ),
                    _c(
                        "pharmacy_right_shelves",
                        "right shelves",
                        "shelves",
                        _SHELVES,
                        ("pharmacy", "shelves"),
                    ),
                    _c(
                        "pharmacy_shop_fridge",
                        "shop fridge",
                        "fridge",
                        _FRIDGE,
                        ("pharmacy", "fridge"),
                    ),
                ),
            ),
            RoomSpec(
                "back_room",
                "back room",
                "pharmacystorage",
                ("storeroom", "stockroom"),
                (
                    _c(
                        "pharmacy_dispensing_counter",
                        "dispensing counter",
                        "counter",
                        _COUNTER,
                        ("pharmacystorage", "counter"),
                    ),
                    _c(
                        "pharmacy_medicine_fridge",
                        "medicine fridge",
                        "fridge",
                        _FRIDGE,
                        ("pharmacystorage", "fridge"),
                    ),
                    _c(
                        "pharmacy_supply_crates",
                        "supply crates",
                        "crate",
                        _CRATES,
                        ("pharmacystorage", "other"),
                    ),
                ),
            ),
        ),
        "zone_clinic": (
            RoomSpec(
                "exam_room",
                "exam room",
                "medical",
                ("examination room", "consulting room"),
                (
                    _c(
                        "clinic_exam_counter",
                        "exam counter",
                        "counter",
                        _COUNTER,
                        ("medical", "counter"),
                    ),
                    _c("clinic_exam_desk", "exam desk", "desk", _DESK, ("medical", "desk")),
                    _c(
                        "clinic_side_table",
                        "side table",
                        "sidetable",
                        ("table",),
                        ("medical", "sidetable"),
                    ),
                ),
            ),
            RoomSpec(
                "office",
                "office",
                "medicaloffice",
                (),
                (
                    _c(
                        "clinic_office_desk",
                        "office desk",
                        "desk",
                        _DESK,
                        ("medicaloffice", "desk"),
                    ),
                    _c(
                        "clinic_office_counter",
                        "office counter",
                        "counter",
                        _COUNTER,
                        ("medicaloffice", "counter"),
                    ),
                ),
            ),
            RoomSpec(
                "supply_room",
                "supply room",
                "medicalstorage",
                ("storeroom", "stockroom"),
                (
                    _c(
                        "clinic_supply_counter",
                        "supply counter",
                        "counter",
                        _COUNTER,
                        ("medicalstorage", "counter"),
                    ),
                    _c(
                        "clinic_supply_shelves",
                        "supply shelves",
                        "shelves",
                        _SHELVES,
                        ("medicalstorage", "metal_shelves"),
                    ),
                    _c(
                        "clinic_supply_fridge",
                        "supply fridge",
                        "fridge",
                        _FRIDGE,
                        ("medicalstorage", "fridge"),
                    ),
                    _c(
                        "clinic_supply_crates",
                        "supply crates",
                        "crate",
                        _CRATES,
                        ("medicalstorage", "other"),
                    ),
                    _c(
                        "clinic_supply_desk",
                        "supply desk",
                        "desk",
                        _DESK,
                        ("medicalstorage", "desk"),
                    ),
                ),
            ),
        ),
        "zone_supermarket": (
            RoomSpec(
                "aisles",
                "aisles",
                "grocery",
                ("shop floor", "shop", "shopfront"),
                (
                    _c(
                        "supermarket_checkout_counter",
                        "checkout counter",
                        "counter",
                        ("counter", "checkout", "till"),
                        ("grocery", "counter"),
                    ),
                    _c(
                        "supermarket_aisle_shelves_1",
                        "first aisle shelves",
                        "shelves",
                        _SHELVES,
                        ("grocery", "shelves"),
                    ),
                    _c(
                        "supermarket_aisle_shelves_2",
                        "second aisle shelves",
                        "shelves",
                        _SHELVES,
                        ("grocery", "shelves"),
                    ),
                    _c(
                        "supermarket_aisle_shelves_3",
                        "third aisle shelves",
                        "shelves",
                        _SHELVES,
                        ("grocery", "shelves"),
                    ),
                    _c(
                        "supermarket_aisle_shelves_4",
                        "fourth aisle shelves",
                        "shelves",
                        _SHELVES,
                        ("grocery", "shelves"),
                    ),
                    _c(
                        "supermarket_drinks_fridge",
                        "drinks fridge",
                        "fridge",
                        _FRIDGE,
                        ("grocery", "fridge"),
                    ),
                ),
            ),
            RoomSpec(
                "stockroom",
                "stockroom",
                "grocerystorage",
                ("back room", "storeroom"),
                (
                    _c(
                        "supermarket_stockroom_fridge",
                        "stockroom fridge",
                        "fridge",
                        _FRIDGE,
                        ("grocerystorage", "fridge"),
                    ),
                    _c(
                        "supermarket_stock_crates_1",
                        "first stock crates",
                        "crate",
                        _CRATES,
                        ("grocerystorage", "other"),
                    ),
                    _c(
                        "supermarket_stock_crates_2",
                        "second stock crates",
                        "crate",
                        _CRATES,
                        ("grocerystorage", "other"),
                    ),
                ),
            ),
        ),
        "zone_hardware": (
            RoomSpec(
                "shop_floor",
                "shop floor",
                "toolstore",
                ("shop", "shopfront"),
                (
                    _c(
                        "hardware_tool_counter",
                        "tool counter",
                        "counter",
                        _COUNTER,
                        ("toolstore", "counter"),
                    ),
                    _c(
                        "hardware_shelves_1",
                        "first shelves",
                        "shelves",
                        _SHELVES,
                        ("toolstore", "shelves"),
                    ),
                    _c(
                        "hardware_shelves_2",
                        "second shelves",
                        "shelves",
                        _SHELVES,
                        ("toolstore", "shelves"),
                    ),
                    _c(
                        "hardware_shelves_3",
                        "third shelves",
                        "shelves",
                        _SHELVES,
                        ("toolstore", "shelves"),
                    ),
                    _c(
                        "hardware_shop_crates",
                        "shop crates",
                        "crate",
                        _CRATES,
                        ("toolstore", "other"),
                    ),
                ),
            ),
            RoomSpec(
                "storeroom",
                "storeroom",
                "toolstorestorage",
                ("back room", "stockroom"),
                (
                    _c(
                        "hardware_storeroom_crates_1",
                        "first storeroom crates",
                        "crate",
                        _CRATES,
                        ("toolstorestorage", "other"),
                    ),
                    _c(
                        "hardware_storeroom_crates_2",
                        "second storeroom crates",
                        "crate",
                        _CRATES,
                        ("toolstorestorage", "other"),
                    ),
                ),
            ),
        ),
    }
)

ENTRY_ROOMS = {  # spec 25: the room a zone is entered into
    "zone_home": "living_room",
    "zone_building": "hallway",
    "zone_bodega": "shop_floor",
    "zone_flat_vacant": "living_room",
    "zone_flat_tenant": "living_room",
    "zone_pharmacy": "shop_floor",
    "zone_clinic": "exam_room",
    "zone_supermarket": "aisles",
    "zone_hardware": "shop_floor",
}


def build_rooms(zone_id: str) -> dict[str, RoomEntity]:
    """The rooms of a zone, fresh: fixed containers hold their items and are not yet opened."""
    rooms: dict[str, RoomEntity] = {}
    for spec in ROOM_LAYOUTS.get(zone_id, ()):
        containers = [
            ContainerEntity(
                container_id=c.container_id,
                name=c.name,
                kind=c.kind,
                capacity=c.capacity,
                aliases=list(c.aliases),
                source=c.source,
                contents=[ItemEntity(item=ITEMS[item_id]) for item_id in c.fixed],
                fixed=bool(c.fixed),
            )
            for c in spec.containers
        ]
        rooms[spec.room_id] = RoomEntity(
            room_id=spec.room_id,
            name=spec.name,
            kind=spec.kind,
            aliases=list(spec.aliases),
            containers=containers,
        )
    return rooms


ALREADY_IN_ROOM = "{name} is already in the {room}."  # spec 25
MOVE_ROOM_FACT = "Move within {zone} to the {room}: succeeded."  # spec 25
SEARCH_CONTAINER_FACT = "{name} goes through the {container}: {items}."  # spec 25
SEARCH_EMPTY_FACT = "{name} goes through the {container} and finds nothing."  # spec 25
NEVER_SEARCHES = "{name} never gets to search."  # spec 25
GONE_THROUGH = "{name} has already been through the {target}."  # spec 25
NOT_OPENED = "The {container} hasn't been gone through."  # spec 25
NO_SUCH_SEARCH_TARGET = "There is no '{target}' to search here."  # spec 25
WHICH_ONE = "Which one: {choices}?"  # spec 25
NOT_IN_THIS_ROOM = "The {container} is in the {room}, not here."  # spec 25
CONTAINER_FULL = "The {container} is full."  # spec 25
NO_SUCH_IN_CONTAINER = "The {container} holds no '{item}'."  # spec 25
NO_SUCH_CONTAINER = "There is no '{target}' here to put things in."  # spec 25
PUT_IN_CONTAINER_FACT = "{name} puts the {item} in the {container}."  # spec 25
TAKE_FROM_CONTAINER_FACT = "{name} takes the {item} out of the {container}."  # spec 25
NUMBER_WORDS = (
    "no",
    "one",
    "two",
    "three",
    "four",
    "five",
    "six",
    "seven",
    "eight",
    "nine",
    "ten",
)  # spec 25
ROOM_HERE_MARK = " (you are here)"  # spec 25
CONTAINER_NOT_OPENED = "{name} (not opened)"  # spec 25
CONTAINER_OPENED = "{name} (opened: {items})"  # spec 25
EMPTY_WORD = "empty"  # spec 25
NO_ROOMS = "None"  # spec 25
