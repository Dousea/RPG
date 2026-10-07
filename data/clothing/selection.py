"""Which clothes a new character may start in (spec 07).

Each list maps a body location to the items offered there. `chance` (percent)
is used only when a character is dressed at random. A list with only a female
version serves both genders.
"""

from modules.body.parts import BodyLocation
from modules.character.appearance import Gender
from modules.character.definitions import ClothingChoice

ClothingList = dict[BodyLocation, ClothingChoice]
GenderedClothing = dict[Gender, ClothingList]

DEFAULT_CLOTHING: GenderedClothing = {
    Gender.FEMALE: {
        BodyLocation.BELT: ClothingChoice(100, ("item_belt",)),
        BodyLocation.HAT: ClothingChoice(
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
        BodyLocation.EYES: ClothingChoice(10, ("item_plain_lens_glasses", "item_reading_glasses")),
        BodyLocation.TANKTOP: ClothingChoice(10, ("item_tank_top",)),
        BodyLocation.SHIRT: ClothingChoice(
            10, ("item_formal_shirt", "item_short_sleeve_formal_shirt", "item_floral_shirt")
        ),
        BodyLocation.TSHIRT: ClothingChoice(
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
        BodyLocation.PANTS: ClothingChoice(
            100,
            (
                "item_plain_trousers",
                "item_jeans",
                "item_long_denim_shorts",
                "item_short_denim_shorts",
                "item_short_formal_shorts",
            ),
        ),
        BodyLocation.SKIRT: ClothingChoice(
            50, ("item_knee_skirt", "item_long_skirt", "item_mini_skirt", "item_skirt")
        ),
        BodyLocation.DRESS: ClothingChoice(
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
        BodyLocation.SOCKS: ClothingChoice(100, ("item_ankle_socks", "item_long_socks")),
        BodyLocation.SHOES: ClothingChoice(
            100, ("item_everyday_shoes", "item_trainers", "item_strapped_shoes")
        ),
        BodyLocation.NECKLACE: ClothingChoice(0, ("item_crucifix_necklace",)),
    },
    Gender.MALE: {
        BodyLocation.BELT: ClothingChoice(100, ("item_belt",)),
        BodyLocation.HAT: ClothingChoice(
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
        BodyLocation.EYES: ClothingChoice(10, ("item_plain_lens_glasses", "item_reading_glasses")),
        BodyLocation.TANKTOP: ClothingChoice(30, ("item_tank_top",)),
        BodyLocation.SHIRT: ClothingChoice(
            10, ("item_formal_shirt", "item_short_sleeve_formal_shirt", "item_floral_shirt")
        ),
        BodyLocation.TSHIRT: ClothingChoice(
            100, ("item_tshirt", "item_white_long_sleeve_t_shirt", "item_striped_polo", "item_polo")
        ),
        BodyLocation.PANTS: ClothingChoice(
            100,
            (
                "item_plain_trousers",
                "item_jeans",
                "item_long_denim_shorts",
                "item_short_denim_shorts",
                "item_short_formal_shorts",
            ),
        ),
        BodyLocation.SOCKS: ClothingChoice(100, ("item_ankle_socks", "item_long_socks")),
        BodyLocation.SHOES: ClothingChoice(100, ("item_everyday_shoes", "item_trainers")),
        BodyLocation.NECKLACE: ClothingChoice(0, ("item_crucifix_necklace",)),
    },
}  # spec 07

OCCUPATION_CLOTHING: dict[str, GenderedClothing] = {  # spec 07
    "fireofficer": {
        Gender.FEMALE: {
            BodyLocation.HAT: ClothingChoice(10, ("item_fire_dept_cap",)),
            BodyLocation.TSHIRT: ClothingChoice(
                100,
                (
                    "item_blue_firefighter_t_shirt",
                    "item_red_firefighter_t_shirt",
                    "item_dark_red_firefighter_t_shirt",
                    "item_white_firefighter_t_shirt",
                ),
            ),
            BodyLocation.PANTS: ClothingChoice(100, ("item_firefighter_trousers",)),
            BodyLocation.SHOES: ClothingChoice(100, ("item_black_shoes", "item_army_boots")),
        },
    },
    "policeofficer": {
        Gender.FEMALE: {
            BodyLocation.HAT: ClothingChoice(10, ("item_police_hat", "item_police_cap")),
            BodyLocation.EYES: ClothingChoice(10, ("item_glasses", "item_aviator_glasses")),
            BodyLocation.SHIRT: ClothingChoice(
                20, ("item_white_officer_shirt", "item_blue_police_shirt")
            ),
            BodyLocation.TSHIRT: ClothingChoice(
                100,
                (
                    "item_blue_police_t_shirt",
                    "item_navy_police_t_shirt",
                    "item_white_police_t_shirt",
                ),
            ),
            BodyLocation.PANTS: ClothingChoice(100, ("item_police_trousers",)),
        },
    },
    "parkranger": {
        Gender.FEMALE: {
            BodyLocation.HAT: ClothingChoice(10, ("item_ranger_hat",)),
            BodyLocation.SHIRT: ClothingChoice(100, ("item_ranger_shirt",)),
            BodyLocation.TSHIRT: ClothingChoice(
                100,
                ("item_ranger_t_shirt", "item_brown_ranger_t_shirt", "item_green_ranger_t_shirt"),
            ),
            BodyLocation.PANTS: ClothingChoice(100, ("item_ranger_trousers",)),
        },
    },
    "constructionworker": {
        Gender.FEMALE: {
            BodyLocation.SHIRT: ClothingChoice(100, ("item_denim_shirt",)),
            BodyLocation.TORSOEXTRA: ClothingChoice(30, ("item_hi_vis_vest",)),
            BodyLocation.PANTS: ClothingChoice(100, ("item_baggy_jeans",)),
        },
    },
    "securityguard": {
        Gender.FEMALE: {
            BodyLocation.SHIRT: ClothingChoice(100, ("item_white_formal_shirt",)),
            BodyLocation.PANTS: ClothingChoice(100, ("item_black_trousers",)),
        },
    },
    "carpenter": {
        Gender.FEMALE: {
            BodyLocation.MASK: ClothingChoice(5, ("item_dust_mask",)),
            BodyLocation.EYES: ClothingChoice(10, ("item_safety_goggles",)),
            BodyLocation.SHIRT: ClothingChoice(100, ("item_denim_shirt", "item_flannel_shirt")),
            BodyLocation.PANTS: ClothingChoice(100, ("item_baggy_jeans",)),
        },
    },
    "burglar": {
        Gender.FEMALE: {
            BodyLocation.HAT: ClothingChoice(10, ("item_beanie",)),
            BodyLocation.MASK: ClothingChoice(5, ("item_bandana_mask",)),
            BodyLocation.MASKFULL: ClothingChoice(5, ("item_balaclava",)),
            BodyLocation.EYES: ClothingChoice(10, ("item_sunglasses",)),
            BodyLocation.PANTS: ClothingChoice(100, ("item_jeans",)),
        },
    },
    "chef": {
        Gender.FEMALE: {
            BodyLocation.HAT: ClothingChoice(10, ("item_chef_hat",)),
            BodyLocation.JACKET: ClothingChoice(50, ("item_chef_jacket",)),
            BodyLocation.PANTS: ClothingChoice(100, ("item_chef_trousers",)),
        },
    },
    "repairman": {
        Gender.FEMALE: {
            BodyLocation.SHIRT: ClothingChoice(100, ("item_denim_shirt",)),
            BodyLocation.PANTS: ClothingChoice(100, ("item_jeans",)),
        },
    },
    "farmer": {
        Gender.FEMALE: {
            BodyLocation.HAT: ClothingChoice(10, ("item_cowboy_hat", "item_sun_hat")),
            BodyLocation.SHIRT: ClothingChoice(100, ("item_denim_shirt", "item_flannel_shirt")),
            BodyLocation.PANTS: ClothingChoice(100, ("item_jeans",)),
            BodyLocation.SHOES: ClothingChoice(20, ("item_wellies",)),
        },
        Gender.MALE: {
            BodyLocation.HAT: ClothingChoice(10, ("item_cowboy_hat",)),
            BodyLocation.SHIRT: ClothingChoice(100, ("item_denim_shirt", "item_flannel_shirt")),
            BodyLocation.PANTS: ClothingChoice(100, ("item_jeans",)),
            BodyLocation.SHOES: ClothingChoice(20, ("item_wellies",)),
        },
    },
    "fisherman": {
        Gender.FEMALE: {
            BodyLocation.HAT: ClothingChoice(10, ("item_beanie", "item_green_camo_bonnie_hat")),
            BodyLocation.SHIRT: ClothingChoice(100, ("item_denim_shirt", "item_flannel_shirt")),
            BodyLocation.PANTS: ClothingChoice(100, ("item_baggy_jeans",)),
            BodyLocation.SHOES: ClothingChoice(20, ("item_wellies",)),
        },
    },
    "doctor": {
        Gender.FEMALE: {
            BodyLocation.NECK: ClothingChoice(70, ("item_tie",)),
            BodyLocation.MASK: ClothingChoice(5, ("item_surgical_mask",)),
            BodyLocation.SHIRT: ClothingChoice(100, ("item_formal_shirt",)),
            BodyLocation.HANDS: ClothingChoice(5, ("item_surgical_gloves",)),
            BodyLocation.PANTS: ClothingChoice(100, ("item_suit_trousers",)),
        },
    },
    "veteran": {
        Gender.FEMALE: {
            BodyLocation.HAT: ClothingChoice(
                10,
                ("item_army_cap", "item_army_beret", "item_green_camo_bonnie_hat", "item_bandana"),
            ),
            BodyLocation.EYES: ClothingChoice(
                10, ("item_left_eyepatch", "item_right_eyepatch", "item_shooting_glasses")
            ),
            BodyLocation.SHIRT: ClothingChoice(10, ("item_green_camo_shirt",)),
            BodyLocation.TSHIRT: ClothingChoice(
                100, ("item_green_veteran_t_shirt", "item_red_veteran_t_shirt")
            ),
            BodyLocation.PANTS: ClothingChoice(100, ("item_green_camo_long_shorts",)),
            BodyLocation.SHOES: ClothingChoice(100, ("item_trainers",)),
            BodyLocation.NECKLACE: ClothingChoice(80, ("item_dog_tag_necklace",)),
        },
    },
    "nurse": {
        Gender.FEMALE: {
            BodyLocation.HAT: ClothingChoice(10, ("item_surgical_cap",)),
            BodyLocation.MASK: ClothingChoice(5, ("item_surgical_mask",)),
            BodyLocation.SHIRT: ClothingChoice(100, ("item_scrubs_top",)),
            BodyLocation.HANDS: ClothingChoice(5, ("item_surgical_gloves",)),
            BodyLocation.PANTS: ClothingChoice(100, ("item_scrubs_trousers",)),
            BodyLocation.SHOES: ClothingChoice(100, ("item_trainers",)),
        },
    },
    "lumberjack": {
        Gender.FEMALE: {
            BodyLocation.HAT: ClothingChoice(10, ("item_beanie",)),
            BodyLocation.SHIRT: ClothingChoice(100, ("item_denim_shirt", "item_flannel_shirt")),
            BodyLocation.TSHIRT: ClothingChoice(100, ("item_diner_t_shirt",)),
            BodyLocation.PANTS: ClothingChoice(100, ("item_baggy_jeans",)),
        },
    },
    "fitnessinstructor": {
        Gender.FEMALE: {
            BodyLocation.HAT: ClothingChoice(10, ("item_sweatband",)),
            BodyLocation.TSHIRT: ClothingChoice(100, ("item_sport_t_shirt",)),
            BodyLocation.HANDS: ClothingChoice(20, ("item_fingerless_gloves",)),
            BodyLocation.PANTS: ClothingChoice(
                100, ("item_long_sport_shorts", "item_short_sport_shorts", "item_track_trousers")
            ),
            BodyLocation.SHOES: ClothingChoice(100, ("item_trainers",)),
        },
    },
    "burgerflipper": {
        Gender.FEMALE: {
            BodyLocation.HAT: ClothingChoice(10, ("item_fast_food_cap",)),
            BodyLocation.TSHIRT: ClothingChoice(100, ("item_burger_bar_t_shirt",)),
            BodyLocation.SHOES: ClothingChoice(100, ("item_trainers",)),
            BodyLocation.PANTS: ClothingChoice(100, ("item_jeans",)),
        },
    },
    "electrician": {
        Gender.FEMALE: {
            BodyLocation.MASK: ClothingChoice(5, ("item_dust_mask",)),
            BodyLocation.EYES: ClothingChoice(10, ("item_safety_goggles",)),
            BodyLocation.SHIRT: ClothingChoice(100, ("item_denim_shirt", "item_flannel_shirt")),
            BodyLocation.PANTS: ClothingChoice(100, ("item_jeans",)),
            BodyLocation.TORSOEXTRA: ClothingChoice(30, ("item_hi_vis_vest",)),
        },
    },
    "metalworker": {
        Gender.FEMALE: {
            BodyLocation.MASK: ClothingChoice(5, ("item_dust_mask",)),
            BodyLocation.EYES: ClothingChoice(10, ("item_safety_goggles",)),
            BodyLocation.SHIRT: ClothingChoice(100, ("item_denim_shirt", "item_flannel_shirt")),
            BodyLocation.PANTS: ClothingChoice(100, ("item_jeans",)),
            BodyLocation.TORSOEXTRA: ClothingChoice(30, ("item_hi_vis_vest",)),
        },
    },
    "engineer": {
        Gender.FEMALE: {
            BodyLocation.MASK: ClothingChoice(5, ("item_dust_mask",)),
            BodyLocation.NECK: ClothingChoice(20, ("item_tie",)),
            BodyLocation.SHIRT: ClothingChoice(100, ("item_formal_shirt",)),
            BodyLocation.PANTS: ClothingChoice(100, ("item_suit_trousers",)),
            BodyLocation.TORSOEXTRA: ClothingChoice(30, ("item_hi_vis_vest",)),
        },
    },
    "mechanics": {
        Gender.FEMALE: {
            BodyLocation.HAT: ClothingChoice(10, ("item_bandana",)),
            BodyLocation.MASK: ClothingChoice(5, ("item_dust_mask",)),
            BodyLocation.EYES: ClothingChoice(10, ("item_safety_goggles",)),
            BodyLocation.SHIRT: ClothingChoice(100, ("item_denim_shirt", "item_flannel_shirt")),
            BodyLocation.TSHIRT: ClothingChoice(
                100,
                ("item_oil_company_t_shirt", "item_fuel_stop_t_shirt", "item_gas_station_t_shirt"),
            ),
            BodyLocation.PANTS: ClothingChoice(100, ("item_jeans",)),
        },
    },
}

TRAIT_CLOTHING: dict[str, GenderedClothing] = {  # spec 07
    "gardener": {
        Gender.FEMALE: {
            BodyLocation.HAT: ClothingChoice(10, ("item_sun_hat", "item_flower_sun_hat")),
            BodyLocation.SHIRT: ClothingChoice(10, ("item_denim_shirt",)),
        },
        Gender.MALE: {
            BodyLocation.SHIRT: ClothingChoice(10, ("item_denim_shirt",)),
        },
    },
    "fishing": {
        Gender.FEMALE: {
            BodyLocation.HAT: ClothingChoice(10, ("item_fishing_bucket_hat", "item_bonnie_hat")),
            BodyLocation.TORSOEXTRAVEST: ClothingChoice(10, ("item_khaki_hunting_vest",)),
        },
    },
    "hiker": {
        Gender.FEMALE: {
            BodyLocation.HAT: ClothingChoice(10, ("item_bonnie_hat",)),
        },
    },
    "hunter": {
        Gender.FEMALE: {
            BodyLocation.HAT: ClothingChoice(
                10, ("item_army_cap", "item_camo_cap", "item_green_camo_bonnie_hat")
            ),
            BodyLocation.EYES: ClothingChoice(10, ("item_shooting_glasses",)),
            BodyLocation.TORSOEXTRAVEST: ClothingChoice(
                10,
                (
                    "item_grey_hunting_vest",
                    "item_orange_hunting_vest",
                    "item_camo_hunting_vest",
                    "item_green_camo_hunting_vest",
                ),
            ),
            BodyLocation.SHIRT: ClothingChoice(10, ("item_green_camo_shirt",)),
            BodyLocation.TSHIRT: ClothingChoice(
                10,
                ("item_camo_long_sleeve_t_shirt", "item_green_camo_t_shirt", "item_camo_t_shirt"),
            ),
            BodyLocation.PANTS: ClothingChoice(10, ("item_green_camo_long_shorts",)),
        },
    },
    "mechanics": {
        Gender.FEMALE: {
            BodyLocation.HAT: ClothingChoice(10, ("item_bandana",)),
        },
    },
    "outdoorsman": {
        Gender.FEMALE: {
            BodyLocation.HAT: ClothingChoice(10, ("item_bonnie_hat",)),
        },
    },
    "shortsighted": {
        Gender.FEMALE: {
            BodyLocation.EYES: ClothingChoice(
                100, ("item_spectacles", "item_horn_rimmed_glasses", "item_cat_eye_glasses")
            ),
        },
        Gender.MALE: {
            BodyLocation.EYES: ClothingChoice(100, ("item_spectacles", "item_horn_rimmed_glasses")),
        },
    },
}
TRAIT_CLOTHING["wildernessknowledge"] = TRAIT_CLOTHING["hunter"]
