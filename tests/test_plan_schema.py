"""The parser's JSON plan schema and the plan read back into actions (spec 10, Plans)."""

import re
import unittest

from data.items import ITEMS
from managers.context import ContextBuilder
from managers.game import GameManager
from modules.action.parser import (
    TALK_APPROACH_LABELS,
    VERBS,
    ParseFailure,
    available_verbs,
    parse_action_plan,
)
from modules.action.schema import SceneChoices, build_plan_schema, parse_plan
from modules.body import BodyPart
from modules.entity.item import ItemEntity
from modules.entity.zombie import ZombieState
from tests.test_context import add_zombie

MAX_ACTIONS = 5


def branches(schema: dict) -> dict[str, dict]:
    return {
        b["properties"]["verb"]["const"]: b
        for b in schema["properties"]["actions"]["items"]["anyOf"]
    }


def ask_branches(schema: dict) -> list[dict]:
    return [
        b
        for b in schema["properties"]["actions"]["items"]["anyOf"]
        if b["properties"]["verb"]["const"] == "ASK"
    ]


def fits(branch: dict, entry: dict) -> bool:
    properties = branch["properties"]
    if not set(branch["required"]) <= set(entry) <= set(properties):
        return False
    for field, value in entry.items():
        spec = properties[field]
        if "const" in spec and value != spec["const"]:
            return False
        if "enum" in spec and value not in spec["enum"]:
            return False
        if "pattern" in spec and not re.search(spec["pattern"], value):
            return False
    return True


def enum_of(branch: dict, field: str) -> list:
    return branch["properties"][field]["enum"]


def give(gm: GameManager, *item_ids: str) -> None:
    gm.player.inventory.extend(ItemEntity(item=ITEMS[item_id]) for item_id in item_ids)


def building_scene() -> GameManager:
    gm = GameManager()
    gm.player.current_location_id = "zone_building"
    return gm


class SchemaShapeTests(unittest.TestCase):
    def test_the_schema_is_a_list_of_at_most_the_plan_limit(self):
        schema = ContextBuilder(GameManager()).build_plan_schema()
        actions = schema["properties"]["actions"]
        self.assertEqual(schema["required"], ["actions"])
        self.assertFalse(schema["additionalProperties"])
        self.assertEqual(actions["type"], "array")
        self.assertEqual((actions["minItems"], actions["maxItems"]), (0, MAX_ACTIONS))

    def test_it_lists_exactly_the_verbs_the_prompt_lists(self):
        builder = ContextBuilder(building_scene())
        listed = [v.name for v in available_verbs(builder.scene_keys())]
        self.assertEqual(list(branches(builder.build_plan_schema())), listed)

    def test_a_listed_verb_with_no_one_to_aim_at_is_left_out_of_the_schema(self):
        builder = ContextBuilder(GameManager())
        listed = [v.name for v in available_verbs(builder.scene_keys())]
        self.assertIn("ADD_RELATIONSHIP_NOTE", listed)
        self.assertNotIn("ADD_RELATIONSHIP_NOTE", branches(builder.build_plan_schema()))

    def test_every_branch_is_closed_and_requires_its_verb(self):
        gm = building_scene()
        give(gm, "item_bandage")
        gm.player.body[BodyPart.HAND_L].scratch_time = 5.0
        for name, branch in branches(ContextBuilder(gm).build_plan_schema()).items():
            self.assertFalse(branch["additionalProperties"], name)
            self.assertIn("verb", branch["required"], name)
            self.assertEqual(branch["properties"]["verb"], {"const": name})

    def test_a_verb_with_nothing_to_choose_from_is_left_out(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_street"
        gm.player.inventory.clear()
        gm.world.barriers.clear()
        gm.current_location.entities[:] = [
            entity for entity in gm.current_location.entities if not isinstance(entity, ItemEntity)
        ]
        names = branches(ContextBuilder(gm).build_plan_schema())
        for verb in ("DROP", "TALK", "ASK", "GIVE", "UNEQUIP", "BANDAGE", "ATTACK", "SHOVE"):
            self.assertNotIn(verb, names)

    def test_a_scene_with_no_verb_at_all_allows_only_an_empty_list(self):
        schema = build_plan_schema([], SceneChoices(), MAX_ACTIONS)
        self.assertEqual(schema["properties"]["actions"]["maxItems"], 0)


class ClosedFieldTests(unittest.TestCase):
    """Each closed field holds exactly what the scene offers."""

    def test_take_is_the_items_here_and_wear_adds_the_jacket_on_the_floor(self):
        gm = GameManager()
        names = branches(ContextBuilder(gm).build_plan_schema())
        self.assertEqual(
            enum_of(names["TAKE"], "item"),
            ["Canned Beans", "Water Bottle", "Black jacket", "Kitchen Knife", "Frying Pan"],
        )
        self.assertEqual(enum_of(names["WEAR"], "item"), ["Black jacket"])

    def test_wear_lists_clothing_carried_and_on_the_floor_once_each(self):
        gm = GameManager()
        give(gm, "item_black_jacket")
        names = branches(ContextBuilder(gm).build_plan_schema())
        self.assertEqual(enum_of(names["WEAR"], "item"), ["Black jacket"])

    def test_carried_worn_and_held_sets(self):
        gm = GameManager()
        give(gm, "item_bandage", "item_bandage")
        names = branches(ContextBuilder(gm).build_plan_schema())
        for verb in ("DROP", "USE_ITEM", "EQUIP"):
            self.assertEqual(
                enum_of(names[verb], "item"),
                ["Apartment Key", "Bandage", "Canned Beans", "Water Bottle", "Black jacket"]
                + ["Kitchen Knife", "Frying Pan"],
            )
        self.assertEqual(
            enum_of(names["TAKE_OFF"], "item"),
            ["Hoodie", "Jeans", "Trainers", "Ankle socks", "T-shirt"],
        )
        self.assertNotIn("UNEQUIP", names)

    def test_bandage_takes_hurt_unbandaged_parts_and_the_carried_bandages(self):
        gm = GameManager()
        give(gm, "item_bandage", "item_adhesive_bandage", "item_alcohol_wipes")
        gm.player.body[BodyPart.FOREARM_L].scratch_time = 5.0
        gm.player.body[BodyPart.HAND_R].cut_time = 5.0
        gm.player.body[BodyPart.HAND_L].scratch_time = 5.0
        gm.player.body[BodyPart.HAND_L].bandage = "item_bandage"
        gm.player.body[BodyPart.HAND_L].bandage_life = 5.0
        names = branches(ContextBuilder(gm).build_plan_schema())
        self.assertEqual(
            sorted(enum_of(names["BANDAGE"], "body_part")), ["left forearm", "right hand"]
        )
        self.assertEqual(
            sorted(enum_of(names["DISINFECT"], "body_part")), ["left forearm", "right hand"]
        )
        self.assertEqual(enum_of(names["REMOVE_BANDAGE"], "body_part"), ["left hand"])
        self.assertEqual(sorted(enum_of(names["BANDAGE"], "item")), ["Adhesive Bandage", "Bandage"])
        self.assertEqual(enum_of(names["DISINFECT"], "item"), ["Alcohol Wipes"])
        self.assertEqual(names["BANDAGE"]["required"], ["verb", "body_part"])

    def test_bandage_without_a_carried_bandage_has_no_item_field(self):
        gm = GameManager()
        gm.player.body[BodyPart.HAND_L].scratch_time = 5.0
        branch = branches(ContextBuilder(gm).build_plan_schema())["BANDAGE"]
        self.assertNotIn("item", branch["properties"])

    def test_combat_targets(self):
        gm = building_scene()
        gm.world.outbreak_started_at = 0
        zombie = add_zombie(gm, 5.0, ZombieState.IDLE)
        names = branches(ContextBuilder(gm).build_plan_schema())
        self.assertEqual(
            enum_of(names["ATTACK"], "target"),
            ["Emma", "Marcus", zombie.zombie_id, "zombie", "apartment door", "lobby door"],
        )
        self.assertEqual(enum_of(names["SHOVE"], "target"), [zombie.zombie_id])

    def test_attack_offers_no_nearest_zombie_when_none_is_seen(self):
        names = branches(ContextBuilder(building_scene()).build_plan_schema())
        self.assertEqual(
            enum_of(names["ATTACK"], "target"), ["Emma", "Marcus", "apartment door", "lobby door"]
        )

    def test_the_door_verbs_offer_the_barriers_of_the_zone(self):
        names = branches(ContextBuilder(building_scene()).build_plan_schema())
        for verb in ("OPEN", "CLOSE", "BARRICADE", "UNBARRICADE"):
            with self.subTest(verb=verb):
                self.assertEqual(enum_of(names[verb], "target"), ["apartment door", "lobby door"])

    def test_talk_ask_and_give(self):
        gm = building_scene()
        names = branches(ContextBuilder(gm).build_plan_schema())
        self.assertEqual(enum_of(names["TALK"], "npc"), ["Emma", "Marcus"])
        self.assertEqual(enum_of(names["TALK"], "approach"), list(TALK_APPROACH_LABELS))
        self.assertEqual(names["TALK"]["required"], ["verb", "npc", "approach"])
        self.assertEqual(names["TALK"]["properties"]["speech"], {"type": "string"})
        self.assertEqual(enum_of(names["GIVE"], "npc"), ["Emma", "Marcus"])
        self.assertEqual(
            enum_of(names["GIVE"], "item"),
            [
                "Apartment Key",
                "Bandage",
                "Adhesive Bandage",
                "Alcohol Wipes",
                "Painkillers",
                "Hammer",
                "Nails",
                "Plank",
                "Hand Axe",
            ],
        )

    def test_ask_offers_only_the_requests_the_scene_can_fill(self):
        asks = ask_branches(ContextBuilder(building_scene()).build_plan_schema())
        self.assertEqual(len(asks), 1)
        self.assertEqual(enum_of(asks[0], "request"), ["follow", "stay"])
        self.assertEqual(asks[0]["required"], ["verb", "npc", "request"])

    def test_ask_for_an_item_or_a_topic_requires_one(self):
        choices = SceneChoices(npcs=("Emma",), npc_items=("Bandage",), topics=("the_pharmacy",))
        ask = VERBS["ASK"]
        asks = ask_branches(build_plan_schema([ask], choices, MAX_ACTIONS))
        by_request = {tuple(enum_of(b, "request")): b for b in asks}
        self.assertEqual(list(by_request), [("follow", "stay"), ("give",), ("about",)])
        self.assertEqual(by_request[("give",)]["required"], ["verb", "npc", "request", "item"])
        self.assertEqual(enum_of(by_request[("give",)], "item"), ["Bandage"])
        self.assertEqual(by_request[("about",)]["required"], ["verb", "npc", "request", "topic"])
        self.assertEqual(enum_of(by_request[("about",)], "topic"), ["the_pharmacy"])

    def test_the_rest(self):
        names = branches(ContextBuilder(GameManager()).build_plan_schema())
        self.assertEqual(enum_of(names["STANCE"], "stance"), ["sneak", "stand"])
        self.assertEqual(
            names["EXERCISE"]["properties"]["minutes"]["enum"], [10, 20, 30, 40, 50, 60]
        )
        self.assertIn("Push-ups", enum_of(names["EXERCISE"], "exercise"))
        self.assertEqual(enum_of(names["ADD_GOAL"], "horizon"), ["short_term", "long_term"])
        self.assertEqual(names["MOVE_TO"]["required"], ["verb", "destination"])
        self.assertEqual(names["MOVE_TO"]["properties"]["run"], {"type": "boolean"})
        self.assertEqual(names["SLEEP"]["required"], ["verb"])
        self.assertEqual(names["WAIT"]["required"], ["verb", "duration"])


class DurationPatternTests(unittest.TestCase):
    def pattern(self) -> str:
        names = branches(ContextBuilder(GameManager()).build_plan_schema())
        return names["WAIT"]["properties"]["duration"]["pattern"]

    def test_the_pattern_accepts_what_the_grammar_accepts(self):
        for text in ("10m", "2h", "1h30m", "90m", "until night", "until 14:30", "until 6:05"):
            self.assertTrue(re.search(self.pattern(), text), text)
            actions, failures = parse_action_plan([f"WAIT {text}"])
            self.assertEqual((len(actions), failures), (1, []), text)

    def test_the_pattern_refuses_what_the_grammar_refuses(self):
        for text in ("0m", "soon", "until", "until 25:00", "18 hours", "until lunchtime", "h"):
            self.assertFalse(re.search(self.pattern(), text), text)


# One JSON action and the line the grammar reads for it.
EQUIVALENTS = [
    ({"verb": "MOVE_TO", "destination": "the kitchen", "run": True}, "MOVE_TO the kitchen run"),
    ({"verb": "MOVE_TO", "destination": "out"}, "MOVE_TO out"),
    ({"verb": "STANCE", "stance": "sneak"}, "STANCE sneak"),
    ({"verb": "WAIT", "duration": "1h30m"}, "WAIT 1h30m"),
    ({"verb": "SLEEP", "duration": "until morning"}, "SLEEP until morning"),
    ({"verb": "SLEEP"}, "SLEEP"),
    ({"verb": "TAKE", "item": "Water Bottle"}, "TAKE Water Bottle"),
    ({"verb": "DROP", "item": "Bandage"}, "DROP Bandage"),
    ({"verb": "USE_ITEM", "item": "Canned Beans"}, "USE_ITEM Canned Beans"),
    ({"verb": "EQUIP", "item": "Crowbar"}, "EQUIP Crowbar"),
    ({"verb": "UNEQUIP", "item": "Crowbar"}, "UNEQUIP Crowbar"),
    ({"verb": "WEAR", "item": "Black jacket"}, "WEAR Black jacket"),
    ({"verb": "TAKE_OFF", "item": "Hoodie"}, "TAKE_OFF Hoodie"),
    (
        {"verb": "BANDAGE", "body_part": "left hand", "item": "Adhesive Bandage"},
        "BANDAGE left hand with Adhesive Bandage",
    ),
    ({"verb": "BANDAGE", "body_part": "left hand"}, "BANDAGE left hand"),
    ({"verb": "REMOVE_BANDAGE", "body_part": "left hand"}, "REMOVE_BANDAGE left hand"),
    (
        {"verb": "DISINFECT", "body_part": "right hand", "item": "Alcohol Wipes"},
        "DISINFECT right hand with Alcohol Wipes",
    ),
    ({"verb": "EXERCISE", "exercise": "Push-ups", "minutes": 30}, "EXERCISE Push-ups 30"),
    ({"verb": "EXERCISE", "exercise": "Squats"}, "EXERCISE Squats"),
    ({"verb": "ATTACK", "target": "z3"}, "ATTACK z3"),
    ({"verb": "SHOVE", "target": "z3"}, "SHOVE z3"),
    ({"verb": "ATTACK", "target": "lobby door"}, "ATTACK lobby door"),
    ({"verb": "OPEN", "target": "lobby door"}, "OPEN lobby door"),
    ({"verb": "CLOSE", "target": "lobby door"}, "CLOSE lobby door"),
    ({"verb": "BARRICADE", "target": "lobby door"}, "BARRICADE lobby door"),
    ({"verb": "UNBARRICADE", "target": "lobby door"}, "UNBARRICADE lobby door"),
    ({"verb": "SHOUT"}, "SHOUT"),
    (
        {"verb": "TALK", "npc": "Emma", "approach": "chat", "speech": "Hi there, how are you?"},
        "TALK Emma chat",
    ),
    ({"verb": "ASK", "npc": "Emma", "request": "follow"}, "ASK Emma follow"),
    ({"verb": "ASK", "npc": "Emma", "request": "give", "item": "Bandage"}, "ASK Emma give Bandage"),
    (
        {"verb": "ASK", "npc": "Emma", "request": "about", "topic": "the_pharmacy"},
        "ASK Emma about the_pharmacy",
    ),
    ({"verb": "GIVE", "item": "Bandage", "npc": "Emma"}, "GIVE Bandage to Emma"),
    (
        {"verb": "ADD_GOAL", "horizon": "short_term", "text": "Find a weapon"},
        "ADD_GOAL short_term Find a weapon",
    ),
    (
        {"verb": "REMOVE_GOAL", "horizon": "long_term", "text": "Reach the coast"},
        "REMOVE_GOAL long_term Reach the coast",
    ),
    (
        {"verb": "ADD_RELATIONSHIP_NOTE", "npc": "Emma", "note": "Seems kind"},
        "ADD_RELATIONSHIP_NOTE Emma Seems kind",
    ),
]


class PlanReadingTests(unittest.TestCase):
    def test_every_verb_has_an_equivalence_case(self):
        self.assertEqual({entry["verb"] for entry, _ in EQUIVALENTS}, set(VERBS))

    def test_each_verbs_json_becomes_the_action_its_line_does(self):
        for entry, line in EQUIVALENTS:
            want, want_failures = parse_action_plan([line])
            self.assertEqual(want_failures, [], line)
            self.assertEqual(parse_plan({"actions": [entry]}), (want, []), line)

    def test_a_plan_keeps_its_order(self):
        actions, failures = parse_plan(
            {"actions": [{"verb": "TAKE", "item": "Crowbar"}, {"verb": "SHOUT"}]}
        )
        self.assertEqual([a.verb for a in actions], ["TAKE", "SHOUT"])
        self.assertEqual(failures, [])

    def test_an_empty_list_is_none(self):
        self.assertEqual(parse_plan({"actions": []}), ([], []))

    def test_a_shape_the_schema_forbids_is_a_failure_not_an_exception(self):
        for payload in (None, [], "NONE", {}, {"actions": "TAKE x"}, {"actions": [5]}):
            actions, failures = parse_plan(payload)
            self.assertEqual(actions, [], payload)
            self.assertEqual(len(failures), 1, payload)
            self.assertIsInstance(failures[0], ParseFailure)

    def test_an_unknown_verb_or_wrong_field_type_is_a_failure(self):
        for entry in (
            {"verb": "KNOCK"},
            {"item": "Crowbar"},
            {"verb": "TAKE", "item": 4},
            {"verb": "MOVE_TO", "destination": "out", "run": "yes"},
            {"verb": "EXERCISE", "exercise": "Squats", "minutes": "30"},
        ):
            actions, failures = parse_plan({"actions": [entry]})
            self.assertEqual((actions, len(failures)), ([], 1), entry)

    def test_a_missing_argument_is_refused_by_the_grammar(self):
        actions, failures = parse_plan({"actions": [{"verb": "TAKE"}]})
        self.assertEqual(actions, [])
        self.assertEqual(failures[0].reason, "TAKE needs an item name.")

    def test_one_bad_action_does_not_drop_the_good_ones(self):
        actions, failures = parse_plan({"actions": [{"verb": "KNOCK"}, {"verb": "SHOUT"}]})
        self.assertEqual([a.verb for a in actions], ["SHOUT"])
        self.assertEqual(len(failures), 1)

    def test_every_equivalence_entry_fits_the_schema_of_a_full_scene(self):
        full = SceneChoices(
            items_here=("Water Bottle",),
            carried=("Bandage", "Canned Beans", "Crowbar"),
            held=("Crowbar",),
            wearable=("Black jacket",),
            worn=("Hoodie",),
            npcs=("Emma",),
            zombie_ids=("z3",),
            hurt_parts=("left hand", "right hand"),
            bandaged_parts=("left hand",),
            bandages=("Adhesive Bandage",),
            disinfectants=("Alcohol Wipes",),
            npc_items=("Bandage",),
            topics=("the_pharmacy",),
            barriers=("lobby door",),
            exercises=("Push-ups", "Squats"),
            exercise_minutes=(10, 20, 30),
            times_of_day=("morning", "night"),
        )
        schema = build_plan_schema(list(VERBS.values()), full, MAX_ACTIONS)
        all_branches = schema["properties"]["actions"]["items"]["anyOf"]
        self.assertEqual({b["properties"]["verb"]["const"] for b in all_branches}, set(VERBS))
        for entry, _ in EQUIVALENTS:
            self.assertTrue(any(fits(b, entry) for b in all_branches), entry)
