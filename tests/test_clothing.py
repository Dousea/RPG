import unittest

from data.clothing.coverage import CLOTHING_COVERAGE, covered_parts
from data.clothing.locations import EXCLUSIVE_LOCATIONS
from data.items import ITEMS, ORTON_OUTFIT_IDS, find_item_by_name, wetness_word
from managers.context import ContextBuilder
from managers.game import GameManager
from modules.body.parts import LAYER_ORDER, BodyLocation, BodyPart
from modules.entity.item import ItemEntity
from modules.entity.player import PlayerEntity
from modules.item import ClothingItem


class BodyPartsAndLocationsTests(unittest.TestCase):
    """clothing: Body parts and locations."""

    def test_seventeen_body_parts_in_order(self):
        self.assertEqual(
            [part.value for part in BodyPart],
            [
                "hand_l", "hand_r", "forearm_l", "forearm_r", "upperarm_l", "upperarm_r",
                "torso_upper", "torso_lower", "head", "neck", "groin", "upperleg_l",
                "upperleg_r", "lowerleg_l", "lowerleg_r", "foot_l", "foot_r",
            ],
        )  # fmt: skip

    def test_114_locations_with_base_prefix(self):
        locations = list(BodyLocation)
        self.assertEqual(len(locations), 114)
        self.assertTrue(all(location.value.startswith("base:") for location in locations))

    def test_locations_in_declaration_order(self):
        values = [location.value for location in BodyLocation]
        self.assertEqual(
            values[:5],
            ["base:bandage", "base:wound", "base:beltextra", "base:belt", "base:bellybutton"],
        )
        self.assertEqual(
            values[-5:], ["base:lefteye", "base:righteye", "base:eyes", "base:scarf", "base:zeddmg"]
        )
        self.assertLess(values.index("base:underwear"), values.index("base:tshirt"))
        self.assertLess(values.index("base:tshirt"), values.index("base:sweater"))
        self.assertLess(values.index("base:sweater"), values.index("base:jacket"))
        self.assertLess(values.index("base:socks"), values.index("base:shoes"))
        self.assertLess(values.index("base:shoes"), values.index("base:pants"))

    def test_layer_order_follows_declaration(self):
        self.assertEqual(LAYER_ORDER[BodyLocation.BANDAGE], 0)
        self.assertEqual(LAYER_ORDER[BodyLocation.ZEDDMG], 113)
        self.assertLess(LAYER_ORDER[BodyLocation.TSHIRT], LAYER_ORDER[BodyLocation.JACKET])


class ExclusivityTests(unittest.TestCase):
    """clothing: Body parts and locations: exclusivity rules."""

    def test_skirt_excludes_pants_and_dress(self):
        blocked = EXCLUSIVE_LOCATIONS[BodyLocation.SKIRT]
        for location in (BodyLocation.PANTS, BodyLocation.DRESS, BodyLocation.SHORTPANTS):
            self.assertIn(location, blocked)

    def test_exclusivity_is_symmetric(self):
        for first, others in EXCLUSIVE_LOCATIONS.items():
            for second in others:
                self.assertIn(first, EXCLUSIVE_LOCATIONS[second])

    def test_full_suit_excludes_jacket_and_pants(self):
        blocked = EXCLUSIVE_LOCATIONS[BodyLocation.FULLSUIT]
        self.assertIn(BodyLocation.JACKET, blocked)
        self.assertIn(BodyLocation.PANTS, blocked)
        self.assertNotIn(BodyLocation.TSHIRT, blocked)

    def test_everyday_outfit_is_compatible(self):
        outfit = [
            BodyLocation.TSHIRT,
            BodyLocation.SWEATER,
            BodyLocation.JACKET,
            BodyLocation.PANTS,
            BodyLocation.SOCKS,
            BodyLocation.SHOES,
        ]
        for first in outfit:
            for second in outfit:
                self.assertNotIn(second, EXCLUSIVE_LOCATIONS.get(first, frozenset()))

    def test_eye_patches_exclude_each_other(self):
        self.assertIn(BodyLocation.RIGHTEYE, EXCLUSIVE_LOCATIONS[BodyLocation.LEFTEYE])

    def test_pair_count(self):
        pairs = sum(len(others) for others in EXCLUSIVE_LOCATIONS.values()) // 2
        self.assertEqual(pairs, 379)


class CoverageTests(unittest.TestCase):
    """clothing: Body parts and locations: coverage by blood location."""

    def test_trousers_cover_legs_and_groin(self):
        self.assertEqual(
            CLOTHING_COVERAGE["trousers"],
            {
                BodyPart.GROIN,
                BodyPart.UPPERLEG_L,
                BodyPart.UPPERLEG_R,
                BodyPart.LOWERLEG_L,
                BodyPart.LOWERLEG_R,
            },
        )

    def test_jacket_covers_arms_torso_and_neck(self):
        self.assertEqual(
            CLOTHING_COVERAGE["jacket"],
            {
                BodyPart.TORSO_UPPER,
                BodyPart.TORSO_LOWER,
                BodyPart.UPPERARM_L,
                BodyPart.UPPERARM_R,
                BodyPart.FOREARM_L,
                BodyPart.FOREARM_R,
                BodyPart.NECK,
            },
        )

    def test_short_sleeve_shirt_stops_at_the_upper_arm(self):
        self.assertNotIn(BodyPart.FOREARM_L, CLOTHING_COVERAGE["shirt"])
        self.assertIn(BodyPart.UPPERARM_L, CLOTHING_COVERAGE["shirt"])

    def test_shoes_cover_both_feet(self):
        self.assertEqual(CLOTHING_COVERAGE["shoes"], {BodyPart.FOOT_L, BodyPart.FOOT_R})

    def test_bag_covers_nothing_after_back_folds_away(self):
        self.assertEqual(CLOTHING_COVERAGE["bag"], frozenset())

    def test_shirt_without_sleeves_folds_back_into_upper_torso(self):
        self.assertEqual(
            CLOTHING_COVERAGE["shirt_no_sleeves"], {BodyPart.TORSO_UPPER, BodyPart.TORSO_LOWER}
        )

    def test_long_jacket_adds_legs(self):
        parts = CLOTHING_COVERAGE["long_jacket"]
        self.assertIn(BodyPart.GROIN, parts)
        self.assertIn(BodyPart.NECK, parts)
        self.assertNotIn(BodyPart.LOWERLEG_L, parts)

    def test_several_coverages_union(self):
        self.assertEqual(
            covered_parts("shoes", "head"), {BodyPart.FOOT_L, BodyPart.FOOT_R, BodyPart.HEAD}
        )


class CatalogTests(unittest.TestCase):
    """clothing: Items: each entry carries its stats verbatim."""

    def clothing(self, item_id: str) -> ClothingItem:
        item = ITEMS[item_id]
        assert isinstance(item, ClothingItem)
        return item

    def test_tshirt(self):
        item = self.clothing("item_tshirt")
        self.assertEqual(item.body_location, BodyLocation.TSHIRT)
        self.assertEqual(item.covers, CLOTHING_COVERAGE["shirt"])
        self.assertEqual(
            (item.insulation, item.wind_resistance, item.water_resistance, item.weight),
            (0.2, 0.05, 0.0, 1.0),
        )

    def test_hoodie(self):
        item = self.clothing("item_hoodie")
        self.assertEqual(item.body_location, BodyLocation.SWEATER)
        self.assertEqual(item.covers, CLOTHING_COVERAGE["jumper"])
        self.assertEqual((item.insulation, item.wind_resistance), (0.6, 0.25))
        self.assertEqual((item.scratch_defense, item.neck_protection), (10, 0.5))

    def test_jeans(self):
        item = self.clothing("item_jeans")
        self.assertEqual(item.body_location, BodyLocation.PANTS)
        self.assertEqual(item.covers, CLOTHING_COVERAGE["trousers"])
        self.assertEqual((item.insulation, item.wind_resistance), (0.7, 0.55))
        self.assertEqual((item.scratch_defense, item.bite_defense), (20, 10))

    def test_ankle_socks(self):
        item = self.clothing("item_ankle_socks")
        self.assertEqual(item.body_location, BodyLocation.SOCKS)
        self.assertEqual(item.covers, CLOTHING_COVERAGE["shoes"])
        self.assertEqual((item.insulation, item.wind_resistance, item.weight), (0.15, 0.1, 0.1))

    def test_trainers(self):
        item = self.clothing("item_trainers")
        self.assertEqual(item.body_location, BodyLocation.SHOES)
        self.assertEqual((item.insulation, item.wind_resistance), (0.45, 0.3))
        self.assertEqual((item.scratch_defense, item.stomp_power), (10, 1.8))

    def test_black_jacket(self):
        item = self.clothing("item_black_jacket")
        self.assertEqual(item.body_location, BodyLocation.JACKET)
        self.assertEqual(item.covers, CLOTHING_COVERAGE["jacket"])
        self.assertEqual(
            (item.insulation, item.wind_resistance, item.water_resistance, item.weight),
            (0.4, 0.6, 0.4, 2.0),
        )
        self.assertEqual(
            (item.scratch_defense, item.bite_defense, item.neck_protection), (40, 20, 0.5)
        )

    def test_defaults(self):
        item = self.clothing("item_tshirt")
        self.assertEqual(
            (
                item.scratch_defense,
                item.bite_defense,
                item.neck_protection,
                item.stomp_power,
                item.hearing_modifier,
                item.corpse_sickness_defense,
            ),
            (0, 0, 1, 1, 1.0, 0),
        )

    def test_orton_outfit_is_the_five_pieces(self):
        self.assertEqual(
            list(ORTON_OUTFIT_IDS),
            ["item_tshirt", "item_hoodie", "item_jeans", "item_ankle_socks", "item_trainers"],
        )

    def test_old_worn_tshirt_is_gone(self):
        self.assertNotIn("item_worn_tshirt", ITEMS)
        self.assertIsNotNone(find_item_by_name("T-shirt"))


def _worn_player(*item_ids: str) -> PlayerEntity:
    player = PlayerEntity(name="Orton", current_location_id="zone_home")
    for item_id in item_ids:
        entity = ItemEntity(item=ITEMS[item_id])
        item = entity.item
        assert isinstance(item, ClothingItem)
        player.worn[item.body_location] = entity
    return player


class LayersTests(unittest.TestCase):
    """clothing: Model: layers for a body part, inner to outer."""

    def test_torso_layers_inner_to_outer(self):
        player = _worn_player("item_black_jacket", "item_tshirt", "item_hoodie")
        names = [entity.item.name for entity in player.layers_for(BodyPart.TORSO_UPPER)]
        self.assertEqual(names, ["T-shirt", "Hoodie", "Black jacket"])

    def test_only_items_covering_the_part(self):
        player = _worn_player("item_tshirt", "item_jeans", "item_trainers")
        self.assertEqual([e.item.name for e in player.layers_for(BodyPart.LOWERLEG_L)], ["Jeans"])
        self.assertEqual([e.item.name for e in player.layers_for(BodyPart.FOOT_R)], ["Trainers"])
        self.assertEqual(player.layers_for(BodyPart.HEAD), [])

    def test_socks_sit_under_trainers(self):
        player = _worn_player("item_trainers", "item_ankle_socks")
        names = [e.item.name for e in player.layers_for(BodyPart.FOOT_L)]
        self.assertEqual(names, ["Ankle socks", "Trainers"])

    def test_holes_start_empty(self):
        self.assertEqual(ItemEntity(item=ITEMS["item_tshirt"]).holes, set())

    def test_wetness_defaults_to_dry(self):
        self.assertEqual(ItemEntity(item=ITEMS["item_tshirt"]).wetness, 0.0)


class OutfitLineTests(unittest.TestCase):
    """clothing: What the narrator and the player see."""

    def setUp(self):
        self.gm = GameManager()
        self.builder = ContextBuilder(self.gm)

    def _wearing_line(self) -> str:
        prompt = self.builder.build_narrator_prompt("look")
        return next(line for line in prompt.splitlines() if line.startswith("Wearing:"))

    def test_orton_starts_in_the_five_piece_outfit(self):
        self.assertEqual(
            sorted(e.item.id for e in self.gm.player.worn.values()), sorted(ORTON_OUTFIT_IDS)
        )

    def test_outfit_line_lists_outer_to_inner(self):
        self.assertEqual(
            self._wearing_line(),
            "Wearing: hoodie, jeans, trainers, ankle socks, t-shirt",
        )

    def test_a_wet_item_gets_a_word(self):
        self.gm.player.worn[BodyLocation.PANTS].wetness = 90.0
        self.assertIn("soaked jeans", self._wearing_line())

    def test_wetness_just_below_the_floor_has_no_word(self):
        self.gm.player.worn[BodyLocation.PANTS].wetness = 14.9
        self.assertIn(" jeans,", self._wearing_line())
        self.assertEqual(wetness_word(14.9), "")

    def test_wetness_words_start_at_15(self):
        self.assertEqual(wetness_word(15), "damp")
        self.assertEqual(wetness_word(40), "wet")
        self.assertEqual(wetness_word(75), "soaked")

    def test_the_outfit_line_has_no_numbers(self):
        for entity in self.gm.player.worn.values():
            entity.wetness = 55.0
        line = self._wearing_line()
        self.assertFalse(any(ch.isdigit() for ch in line), line)

    def test_nothing_worn(self):
        self.gm.player.worn.clear()
        self.assertEqual(self._wearing_line(), "Wearing: Nothing")

    def test_the_parser_sees_worn_clothing(self):
        prompt = self.builder.build_parser_prompt("take off my jeans")
        equipped = prompt.split("[WORN]")[1].split("[CONDITION]")[0]
        self.assertIn("Jeans", equipped)
        self.assertIn("Hoodie", equipped)

    def test_the_parser_sees_carried_clothing(self):
        self.gm.player.inventory.append(ItemEntity(item=ITEMS["item_black_jacket"]))
        prompt = self.builder.build_parser_prompt("put on the jacket")
        self.assertIn("Black jacket", prompt.split("[INVENTORY]")[1].split("[WORN]")[0])


if __name__ == "__main__":
    unittest.main()
