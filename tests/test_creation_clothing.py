"""Spec 07, Starting outfit: the default, occupation and trait clothing lists, row by row."""

import random
import unittest

from data.clothing_selection import DEFAULT_CLOTHING, OCCUPATION_CLOTHING, TRAIT_CLOTHING
from data.items import ITEMS
from data.occupations import OCCUPATIONS
from data.traits import TRAITS
from managers.creation import _random_outfit
from modules.body import BodyLocation
from modules.character.appearance import Gender
from modules.item import ClothingItem

# list -> gender -> location -> (chance percent, item ids)
EXPECTED_DEFAULT = {
    "Female": {
        "BELT": (100, ("item_belt",)),
        "HAT": (
            10,
            (
                "item_baseball_cap",
                "item_plain_baseball_cap",
                "item_bucket_hat",
                "item_golf_hat",
                "item_fedora",
                "item_visor",
            ),
        ),
        "EYES": (10, ("item_plain_lens_glasses", "item_reading_glasses")),
        "TANKTOP": (10, ("item_tank_top",)),
        "SHIRT": (10, ("item_formal_shirt", "item_short_sleeve_formal_shirt", "item_floral_shirt")),
        "TSHIRT": (
            100,
            (
                "item_tshirt",
                "item_white_long_sleeve_t_shirt",
                "item_striped_polo",
                "item_polo",
                "item_crop_top",
                "item_sleeveless_crop_top",
                "item_tube_top",
            ),
        ),
        "PANTS": (
            100,
            (
                "item_plain_trousers",
                "item_jeans",
                "item_long_denim_shorts",
                "item_short_denim_shorts",
                "item_short_formal_shorts",
            ),
        ),
        "SKIRT": (50, ("item_knee_skirt", "item_long_skirt", "item_mini_skirt", "item_skirt")),
        "DRESS": (
            10,
            (
                "item_dress",
                "item_knee_dress",
                "item_long_dress",
                "item_long_strappy_dress",
                "item_strapless_dress",
                "item_strappy_dress",
                "item_strappy_knee_dress",
                "item_short_strappy_dress",
            ),
        ),
        "SOCKS": (100, ("item_ankle_socks", "item_long_socks")),
        "SHOES": (100, ("item_everyday_shoes", "item_trainers", "item_strapped_shoes")),
        "NECKLACE": (0, ("item_crucifix_necklace",)),
    },
    "Male": {
        "BELT": (100, ("item_belt",)),
        "HAT": (
            10,
            (
                "item_baseball_cap",
                "item_plain_baseball_cap",
                "item_bucket_hat",
                "item_golf_hat",
                "item_fedora",
                "item_visor",
            ),
        ),
        "EYES": (10, ("item_plain_lens_glasses", "item_reading_glasses")),
        "TANKTOP": (30, ("item_tank_top",)),
        "SHIRT": (10, ("item_formal_shirt", "item_short_sleeve_formal_shirt", "item_floral_shirt")),
        "TSHIRT": (
            100,
            ("item_tshirt", "item_white_long_sleeve_t_shirt", "item_striped_polo", "item_polo"),
        ),
        "PANTS": (
            100,
            (
                "item_plain_trousers",
                "item_jeans",
                "item_long_denim_shorts",
                "item_short_denim_shorts",
                "item_short_formal_shorts",
            ),
        ),
        "SOCKS": (100, ("item_ankle_socks", "item_long_socks")),
        "SHOES": (100, ("item_everyday_shoes", "item_trainers")),
        "NECKLACE": (0, ("item_crucifix_necklace",)),
    },
}

EXPECTED_OCCUPATION = {
    "fireofficer": {
        "Female": {
            "HAT": (10, ("item_fire_dept_cap",)),
            "TSHIRT": (
                100,
                (
                    "item_blue_firefighter_t_shirt",
                    "item_red_firefighter_t_shirt",
                    "item_dark_red_firefighter_t_shirt",
                    "item_white_firefighter_t_shirt",
                ),
            ),
            "PANTS": (100, ("item_firefighter_trousers",)),
            "SHOES": (100, ("item_black_shoes", "item_army_boots")),
        },
    },
    "policeofficer": {
        "Female": {
            "HAT": (10, ("item_police_hat", "item_police_cap")),
            "EYES": (10, ("item_glasses", "item_aviator_glasses")),
            "SHIRT": (20, ("item_white_officer_shirt", "item_blue_police_shirt")),
            "TSHIRT": (
                100,
                (
                    "item_blue_police_t_shirt",
                    "item_navy_police_t_shirt",
                    "item_white_police_t_shirt",
                ),
            ),
            "PANTS": (100, ("item_police_trousers",)),
        },
    },
    "parkranger": {
        "Female": {
            "HAT": (10, ("item_ranger_hat",)),
            "SHIRT": (100, ("item_ranger_shirt",)),
            "TSHIRT": (
                100,
                ("item_ranger_t_shirt", "item_brown_ranger_t_shirt", "item_green_ranger_t_shirt"),
            ),
            "PANTS": (100, ("item_ranger_trousers",)),
        },
    },
    "constructionworker": {
        "Female": {
            "SHIRT": (100, ("item_denim_shirt",)),
            "TORSOEXTRA": (30, ("item_hi_vis_vest",)),
            "PANTS": (100, ("item_baggy_jeans",)),
        },
    },
    "securityguard": {
        "Female": {
            "SHIRT": (100, ("item_white_formal_shirt",)),
            "PANTS": (100, ("item_black_trousers",)),
        },
    },
    "carpenter": {
        "Female": {
            "MASK": (5, ("item_dust_mask",)),
            "EYES": (10, ("item_safety_goggles",)),
            "SHIRT": (100, ("item_denim_shirt", "item_flannel_shirt")),
            "PANTS": (100, ("item_baggy_jeans",)),
        },
    },
    "burglar": {
        "Female": {
            "HAT": (10, ("item_beanie",)),
            "MASK": (5, ("item_bandana_mask",)),
            "MASKFULL": (5, ("item_balaclava",)),
            "EYES": (10, ("item_sunglasses",)),
            "PANTS": (100, ("item_jeans",)),
        },
    },
    "chef": {
        "Female": {
            "HAT": (10, ("item_chef_hat",)),
            "JACKET": (50, ("item_chef_jacket",)),
            "PANTS": (100, ("item_chef_trousers",)),
        },
    },
    "repairman": {
        "Female": {
            "SHIRT": (100, ("item_denim_shirt",)),
            "PANTS": (100, ("item_jeans",)),
        },
    },
    "farmer": {
        "Female": {
            "HAT": (10, ("item_cowboy_hat", "item_sun_hat")),
            "SHIRT": (100, ("item_denim_shirt", "item_flannel_shirt")),
            "PANTS": (100, ("item_jeans",)),
            "SHOES": (20, ("item_wellies",)),
        },
        "Male": {
            "HAT": (10, ("item_cowboy_hat",)),
            "SHIRT": (100, ("item_denim_shirt", "item_flannel_shirt")),
            "PANTS": (100, ("item_jeans",)),
            "SHOES": (20, ("item_wellies",)),
        },
    },
    "fisherman": {
        "Female": {
            "HAT": (10, ("item_beanie", "item_green_camo_bonnie_hat")),
            "SHIRT": (100, ("item_denim_shirt", "item_flannel_shirt")),
            "PANTS": (100, ("item_baggy_jeans",)),
            "SHOES": (20, ("item_wellies",)),
        },
    },
    "doctor": {
        "Female": {
            "NECK": (70, ("item_tie",)),
            "MASK": (5, ("item_surgical_mask",)),
            "SHIRT": (100, ("item_formal_shirt",)),
            "HANDS": (5, ("item_surgical_gloves",)),
            "PANTS": (100, ("item_suit_trousers",)),
        },
    },
    "veteran": {
        "Female": {
            "HAT": (
                10,
                ("item_army_cap", "item_army_beret", "item_green_camo_bonnie_hat", "item_bandana"),
            ),
            "EYES": (10, ("item_left_eyepatch", "item_right_eyepatch", "item_shooting_glasses")),
            "SHIRT": (10, ("item_green_camo_shirt",)),
            "TSHIRT": (100, ("item_green_veteran_t_shirt", "item_red_veteran_t_shirt")),
            "PANTS": (100, ("item_green_camo_long_shorts",)),
            "SHOES": (100, ("item_trainers",)),
            "NECKLACE": (80, ("item_dog_tag_necklace",)),
        },
    },
    "nurse": {
        "Female": {
            "HAT": (10, ("item_surgical_cap",)),
            "MASK": (5, ("item_surgical_mask",)),
            "SHIRT": (100, ("item_scrubs_top",)),
            "HANDS": (5, ("item_surgical_gloves",)),
            "PANTS": (100, ("item_scrubs_trousers",)),
            "SHOES": (100, ("item_trainers",)),
        },
    },
    "lumberjack": {
        "Female": {
            "HAT": (10, ("item_beanie",)),
            "SHIRT": (100, ("item_denim_shirt", "item_flannel_shirt")),
            "TSHIRT": (100, ("item_diner_t_shirt",)),
            "PANTS": (100, ("item_baggy_jeans",)),
        },
    },
    "fitnessinstructor": {
        "Female": {
            "HAT": (10, ("item_sweatband",)),
            "TSHIRT": (100, ("item_sport_t_shirt",)),
            "HANDS": (20, ("item_fingerless_gloves",)),
            "PANTS": (
                100,
                ("item_long_sport_shorts", "item_short_sport_shorts", "item_track_trousers"),
            ),
            "SHOES": (100, ("item_trainers",)),
        },
    },
    "burgerflipper": {
        "Female": {
            "HAT": (10, ("item_fast_food_cap",)),
            "TSHIRT": (100, ("item_burger_bar_t_shirt",)),
            "SHOES": (100, ("item_trainers",)),
            "PANTS": (100, ("item_jeans",)),
        },
    },
    "electrician": {
        "Female": {
            "MASK": (5, ("item_dust_mask",)),
            "EYES": (10, ("item_safety_goggles",)),
            "SHIRT": (100, ("item_denim_shirt", "item_flannel_shirt")),
            "PANTS": (100, ("item_jeans",)),
            "TORSOEXTRA": (30, ("item_hi_vis_vest",)),
        },
    },
    "metalworker": {
        "Female": {
            "MASK": (5, ("item_dust_mask",)),
            "EYES": (10, ("item_safety_goggles",)),
            "SHIRT": (100, ("item_denim_shirt", "item_flannel_shirt")),
            "PANTS": (100, ("item_jeans",)),
            "TORSOEXTRA": (30, ("item_hi_vis_vest",)),
        },
    },
    "engineer": {
        "Female": {
            "MASK": (5, ("item_dust_mask",)),
            "NECK": (20, ("item_tie",)),
            "SHIRT": (100, ("item_formal_shirt",)),
            "PANTS": (100, ("item_suit_trousers",)),
            "TORSOEXTRA": (30, ("item_hi_vis_vest",)),
        },
    },
    "mechanics": {
        "Female": {
            "HAT": (10, ("item_bandana",)),
            "MASK": (5, ("item_dust_mask",)),
            "EYES": (10, ("item_safety_goggles",)),
            "SHIRT": (100, ("item_denim_shirt", "item_flannel_shirt")),
            "TSHIRT": (
                100,
                ("item_oil_company_t_shirt", "item_fuel_stop_t_shirt", "item_gas_station_t_shirt"),
            ),
            "PANTS": (100, ("item_jeans",)),
        },
    },
}

EXPECTED_TRAIT = {
    "gardener": {
        "Female": {
            "HAT": (10, ("item_sun_hat", "item_flower_sun_hat")),
            "SHIRT": (10, ("item_denim_shirt",)),
        },
        "Male": {
            "SHIRT": (10, ("item_denim_shirt",)),
        },
    },
    "fishing": {
        "Female": {
            "HAT": (10, ("item_fishing_bucket_hat", "item_bonnie_hat")),
            "TORSOEXTRAVEST": (10, ("item_khaki_hunting_vest",)),
        },
    },
    "hiker": {
        "Female": {
            "HAT": (10, ("item_bonnie_hat",)),
        },
    },
    "hunter": {
        "Female": {
            "HAT": (10, ("item_army_cap", "item_camo_cap", "item_green_camo_bonnie_hat")),
            "EYES": (10, ("item_shooting_glasses",)),
            "TORSOEXTRAVEST": (
                10,
                (
                    "item_grey_hunting_vest",
                    "item_orange_hunting_vest",
                    "item_camo_hunting_vest",
                    "item_green_camo_hunting_vest",
                ),
            ),
            "SHIRT": (10, ("item_green_camo_shirt",)),
            "TSHIRT": (
                10,
                ("item_camo_long_sleeve_t_shirt", "item_green_camo_t_shirt", "item_camo_t_shirt"),
            ),
            "PANTS": (10, ("item_green_camo_long_shorts",)),
        },
    },
    "mechanics": {
        "Female": {
            "HAT": (10, ("item_bandana",)),
        },
    },
    "outdoorsman": {
        "Female": {
            "HAT": (10, ("item_bonnie_hat",)),
        },
    },
    "shortsighted": {
        "Female": {
            "EYES": (100, ("item_spectacles", "item_horn_rimmed_glasses", "item_cat_eye_glasses")),
        },
        "Male": {
            "EYES": (100, ("item_spectacles", "item_horn_rimmed_glasses")),
        },
    },
}


def _plain(clothing):
    return {
        gender.name.title(): {
            loc.name: (choice.chance, choice.items) for loc, choice in lst.items()
        }
        for gender, lst in clothing.items()
    }


class ClothingListRowTests(unittest.TestCase):
    """Spec 07, Starting outfit."""

    def test_default_lists(self):
        self.assertEqual(_plain(DEFAULT_CLOTHING), EXPECTED_DEFAULT)

    def test_occupation_lists(self):
        self.assertEqual(
            {k: _plain(v) for k, v in OCCUPATION_CLOTHING.items()}, EXPECTED_OCCUPATION
        )

    def test_trait_lists(self):
        expected = {**EXPECTED_TRAIT, "wildernessknowledge": EXPECTED_TRAIT["hunter"]}
        self.assertEqual({k: _plain(v) for k, v in TRAIT_CLOTHING.items()}, expected)

    def test_list_keys_are_known_occupations_and_traits(self):
        self.assertLessEqual(set(OCCUPATION_CLOTHING), set(OCCUPATIONS))
        self.assertLessEqual(set(TRAIT_CLOTHING), set(TRAITS))

    def test_there_are_21_occupation_lists_and_8_trait_lists(self):
        self.assertEqual(len(OCCUPATION_CLOTHING), 21)
        self.assertEqual(len(TRAIT_CLOTHING), 8)

    def test_every_listed_item_is_clothing_at_the_listed_location(self):
        lists = [
            *DEFAULT_CLOTHING.values(),
            *(g for v in OCCUPATION_CLOTHING.values() for g in v.values()),
            *(g for v in TRAIT_CLOTHING.values() for g in v.values()),
        ]
        distinct = set()
        for by_location in lists:
            for location, choice in by_location.items():
                self.assertTrue(0 <= choice.chance <= 100)
                for item_id in choice.items:
                    item = ITEMS[item_id]
                    assert isinstance(item, ClothingItem)
                    self.assertEqual(item.body_location, location, item_id)
                    distinct.add(item_id)
        self.assertEqual(len(distinct), 131)

    def test_catalog_names_are_unique(self):
        names = [item.name.casefold() for item in ITEMS.values()]
        self.assertEqual(len(names), len(set(names)))

    def test_the_two_genders_exist_for_default(self):
        self.assertEqual(set(DEFAULT_CLOTHING), {Gender.FEMALE, Gender.MALE})


class ClothingStatRowTests(unittest.TestCase):
    """Spec 07, Starting outfit: new clothes carry their own stats (spec 05)."""

    def _stats(self, item_id):
        item = ITEMS[item_id]
        assert isinstance(item, ClothingItem)
        return (
            item.max_hit_points,
            item.insulation,
            item.wind_resistance,
            item.water_resistance,
            item.weight,
            item.scratch_defense,
            item.bite_defense,
            item.neck_protection,
            item.stomp_power,
        )

    def test_army_boots(self):
        self.assertEqual(
            self._stats("item_army_boots"), (30, 1.0, 1.0, 0.8, 1.0, 100, 100, 1.0, 2.5)
        )

    def test_firefighter_trousers(self):
        self.assertEqual(
            self._stats("item_firefighter_trousers"), (10, 0.85, 0.85, 0.8, 4.0, 30, 20, 1.0, 1.0)
        )

    def test_wellies(self):
        self.assertEqual(self._stats("item_wellies")[3], 1.0)
        self.assertEqual(self._stats("item_wellies")[5:7], (100, 100))

    def test_belt_and_glasses_cover_nothing(self):
        for item_id in ("item_belt", "item_glasses"):
            item = ITEMS[item_id]
            assert isinstance(item, ClothingItem)
            self.assertEqual(item.covers, frozenset())

    def test_belt_weight(self):
        self.assertEqual(self._stats("item_belt")[4], 0.2)

    def test_plain_trousers(self):
        self.assertEqual(self._stats("item_plain_trousers")[1:5], (0.5, 0.25, 0.0, 1.0))


STARTING_LOCATION = {
    i: item.body_location for i, item in ITEMS.items() if isinstance(item, ClothingItem)
}


class RandomOutfitRollTests(unittest.TestCase):
    """Spec 07, Starting outfit: random dressing rolls each list in turn, later wins."""

    def test_occupation_list_at_100_always_replaces_the_default_pick(self):
        firefighter_tops = set(
            OCCUPATION_CLOTHING["fireofficer"][Gender.FEMALE][BodyLocation.TSHIRT].items
        )
        for seed in range(100):
            outfit = _random_outfit(random.Random(seed), Gender.FEMALE, "fireofficer", ())
            tops = [i for i in outfit if STARTING_LOCATION[i] == BodyLocation.TSHIRT]
            self.assertEqual(len(tops), 1)
            self.assertIn(tops[0], firefighter_tops)
            self.assertIn("item_firefighter_trousers", outfit)

    def test_a_later_lists_failed_roll_keeps_the_earlier_pick(self):
        default_count = len(DEFAULT_CLOTHING[Gender.FEMALE])

        class Stub(random.Random):
            calls = 0

            def randrange(self, *args, **kwargs):
                self.calls += 1
                return 0 if self.calls <= default_count else 99

            def choice(self, seq):
                return seq[0]

        outfit = _random_outfit(Stub(), Gender.FEMALE, "fireofficer", ())
        default_hat = DEFAULT_CLOTHING[Gender.FEMALE][BodyLocation.HAT].items[0]
        self.assertIn(default_hat, outfit)
        self.assertNotIn(
            OCCUPATION_CLOTHING["fireofficer"][Gender.FEMALE][BodyLocation.HAT].items[0], outfit
        )

    def test_a_zero_chance_default_item_is_never_worn(self):
        for seed in range(200):
            outfit = _random_outfit(random.Random(seed), Gender.FEMALE, "unemployed", ())
            self.assertNotIn("item_crucifix_necklace", outfit)

    def test_each_list_rolls_against_its_own_chance(self):
        hats = 0
        for seed in range(400):
            outfit = _random_outfit(random.Random(seed), Gender.FEMALE, "fireofficer", ())
            hats += any(STARTING_LOCATION[i] == BodyLocation.HAT for i in outfit)
        self.assertLess(hats, 120)
