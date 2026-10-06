"""Spec 07, Occupations and Traits: the static data is consistent and carries the spec's rows."""

import unittest

from data.creation import SKILLS
from data.names import FEMALE_FORENAMES, MALE_FORENAMES, SURNAMES
from data.occupations import OCCUPATIONS
from data.traits import TRAITS

EXPECTED_TRAITS = {
    "adrenalinejunkie": (
        "Adrenaline Junkie",
        4,
        False,
        {},
        ("agoraphobic", "claustrophobic", "cowardly", "desensitized"),
    ),
    "agoraphobic": (
        "Agoraphobic",
        -4,
        False,
        {},
        ("adrenalinejunkie", "brave", "claustrophobic", "desensitized"),
    ),
    "allthumbs": ("All Thumbs", -2, False, {}, ("dextrous",)),
    "artisan": ("Artisan", 2, False, {"glassmaking": 1, "pottery": 1}, ()),
    "asthmatic": ("Asthmatic", -5, False, {}, ()),
    "athletic": (
        "Athletic",
        10,
        False,
        {"fitness": 4},
        ("fit", "obese", "out_of_shape", "overweight", "smoker", "unfit", "very_underweight"),
    ),
    "axeman": ("Ax-pert", 0, True, {}, ()),
    "baseballplayer": ("Baseball Player", 4, False, {"long_blunt": 1}, ()),
    "blacksmith": (
        "Blacksmith Knowledge",
        6,
        False,
        {"blacksmithing": 2, "maintenance": 1},
        ("blacksmith2",),
    ),
    "blacksmith2": ("Blacksmith Knowledge", 0, True, {}, ("blacksmith",)),
    "brave": ("Brave", 4, False, {}, ("agoraphobic", "claustrophobic", "cowardly", "desensitized")),
    "brawler": ("Brawler", 6, False, {"axe": 1, "long_blunt": 1}, ()),
    "burglar": ("Burglar", 0, True, {}, ()),
    "claustrophobic": (
        "Claustrophobic",
        -4,
        False,
        {},
        ("adrenalinejunkie", "agoraphobic", "brave", "desensitized"),
    ),
    "clumsy": ("Clumsy", -2, False, {}, ("graceful",)),
    "conspicuous": ("Conspicuous", -4, False, {}, ("inconspicuous",)),
    "cook": ("Keen Cook", 3, False, {"cooking": 2, "butchering": 1}, ("cook2",)),
    "cook2": ("Keen Cook", 0, True, {}, ("cook",)),
    "cowardly": ("Cowardly", -2, False, {}, ("adrenalinejunkie", "brave", "desensitized")),
    "crafty": ("Crafty", 3, False, {}, ("fastlearner", "slowlearner")),
    "deaf": ("Deaf", -12, False, {}, ("hardofhearing", "keenhearing")),
    "desensitized": (
        "Desensitized",
        0,
        True,
        {},
        ("adrenalinejunkie", "agoraphobic", "brave", "claustrophobic", "cowardly", "hemophobic"),
    ),
    "dextrous": ("Dextrous", 2, False, {}, ("allthumbs",)),
    "disorganized": ("Disorganized", -6, False, {}, ("organized",)),
    "eagleeyed": ("Eagle Eyed", 4, False, {}, ("shortsighted",)),
    "emaciated": ("Emaciated", -10, True, {}, ("obese", "overweight")),
    "fasthealer": ("Fast Healer", 6, False, {}, ("slowhealer",)),
    "fastlearner": ("Fast Learner", 6, False, {}, ("crafty", "slowlearner")),
    "fastreader": ("Fast Reader", 2, False, {}, ("illiterate", "slowreader")),
    "feeble": ("Weak", -6, False, {"strength": -2}, ("stout", "strong", "weak")),
    "firstaid": ("First Aider", 2, False, {"first_aid": 1}, ()),
    "fishing": ("Angler", 4, False, {"fishing": 1}, ()),
    "fit": (
        "Fit",
        6,
        False,
        {"fitness": 2},
        ("athletic", "obese", "out_of_shape", "overweight", "unfit"),
    ),
    "gardener": ("Gardener", 2, False, {"agriculture": 1}, ()),
    "graceful": ("Graceful", 4, False, {}, ("clumsy",)),
    "gymnast": ("Gymnast", 5, False, {"lightfooted": 1, "nimble": 1}, ()),
    "handy": (
        "Handy",
        8,
        False,
        {"carving": 1, "maintenance": 1, "masonry": 1, "carpentry": 1},
        (),
    ),
    "hardofhearing": ("Hard of Hearing", -4, False, {}, ("deaf", "keenhearing")),
    "heartyappetite": ("Hearty Appetite", -4, False, {}, ("lighteater", "very_underweight")),
    "hemophobic": ("Fear of Blood", -5, False, {}, ("desensitized",)),
    "herbalist": ("Herbalist", 4, False, {"foraging": 1}, ("herbalist_prof",)),
    "herbalist_prof": ("Herbalist", 0, True, {"foraging": 1}, ("herbalist",)),
    "hiker": ("Hiker", 5, False, {"foraging": 1, "trapping": 1}, ()),
    "highthirst": ("High Thirst", -2, False, {}, ("lowthirst",)),
    "hunter": (
        "Hunter",
        8,
        False,
        {"aiming": 1, "tracking": 1, "sneaking": 1, "short_blade": 1, "butchering": 1},
        (),
    ),
    "tinkerer": ("Tinkerer", 4, False, {"maintenance": 1}, ()),
    "target_shooter": ("Target Shooter", 5, False, {"aiming": 1}, ()),
    "illiterate": ("Illiterate", -10, False, {}, ("fastreader", "slowreader")),
    "inconspicuous": ("Inconspicuous", 4, False, {}, ("conspicuous",)),
    "inventive": ("Inventive", 2, False, {}, ("inventive_prof",)),
    "inventive_prof": ("Inventive", 0, True, {}, ("inventive",)),
    "irongut": ("Iron Gut", 2, False, {}, ("weakstomach",)),
    "insomniac": ("Restless Sleeper", -6, False, {}, ()),
    "jogger": ("Jogger", 4, False, {"running": 1}, ()),
    "keenhearing": ("Keen Hearing", 6, False, {}, ("deaf", "hardofhearing")),
    "lighteater": ("Light Eater", 2, False, {}, ("heartyappetite", "obese")),
    "lowthirst": ("Low Thirst", 2, False, {}, ("highthirst",)),
    "marksman": ("Marksman", 0, True, {}, ()),
    "mason": ("Mason", 2, False, {"masonry": 2}, ()),
    "mechanics": ("Vehicle Knowledge", 3, False, {"mechanics": 1}, ("mechanics2",)),
    "mechanics2": ("Vehicle Knowledge", 0, True, {}, ("mechanics",)),
    "needslesssleep": ("Wakeful", 3, False, {}, ("needsmoresleep",)),
    "needsmoresleep": ("Sleepyhead", -4, False, {}, ("needslesssleep",)),
    "nightowl": ("Night Owl", 0, True, {}, ()),
    "nightvision": ("Cat's Eyes", 3, False, {}, ()),
    "nutritionist": ("Nutritionist", 2, False, {}, ("nutritionist2",)),
    "nutritionist2": ("Nutritionist", 0, True, {}, ("nutritionist",)),
    "obese": (
        "Very High Weight",
        0,
        True,
        {"fitness": -2},
        (
            "athletic",
            "emaciated",
            "fit",
            "lighteater",
            "overweight",
            "underweight",
            "very_underweight",
        ),
    ),
    "organized": ("Organized", 4, False, {}, ("disorganized",)),
    "outdoorsman": ("Outdoorsy", 2, False, {}, ()),
    "out_of_shape": ("Out of Shape", -6, False, {"fitness": -2}, ("athletic", "fit", "unfit")),
    "overweight": (
        "High Weight",
        0,
        True,
        {"fitness": -1},
        ("athletic", "emaciated", "fit", "underweight", "very_underweight"),
    ),
    "pacifist": ("Reluctant Fighter", -5, False, {}, ()),
    "pronetoillness": ("Prone to Illness", -4, False, {}, ("resilient",)),
    "resilient": ("Resilient", 4, False, {}, ("pronetoillness",)),
    "formerscout": ("Former Scout", 6, False, {"first_aid": 1, "foraging": 1, "fishing": 1}, ()),
    "shortsighted": ("Short Sighted", -2, False, {}, ("eagleeyed",)),
    "slowhealer": ("Slow Healer", -3, False, {}, ("fasthealer",)),
    "slowreader": ("Slow Reader", -2, False, {}, ("fastreader", "illiterate")),
    "slowlearner": ("Slow Learner", -6, False, {}, ("crafty", "fastlearner")),
    "smoker": ("Smoker", -3, False, {}, ("athletic",)),
    "speeddemon": ("Speed Demon", 1, False, {}, ("sundaydriver",)),
    "stout": ("Stout", 6, False, {"strength": 2}, ("feeble", "strong", "weak")),
    "strong": ("Strong", 10, False, {"strength": 4}, ("feeble", "stout", "weak")),
    "sundaydriver": ("Sunday Driver", -1, False, {}, ("speeddemon",)),
    "tailor": ("Sewer", 4, False, {"tailoring": 1}, ()),
    "thickskinned": ("Thick Skinned", 8, False, {}, ("thinskinned",)),
    "thinskinned": ("Thin Skinned", -8, False, {}, ("thickskinned",)),
    "underweight": (
        "Low Weight",
        0,
        True,
        {"fitness": -1},
        ("obese", "overweight", "very_underweight"),
    ),
    "unfit": ("Unfit", -10, False, {"fitness": -4}, ("athletic", "fit", "out_of_shape")),
    "very_underweight": (
        "Very Low Weight",
        0,
        True,
        {"fitness": -2},
        ("athletic", "heartyappetite", "obese", "overweight", "underweight"),
    ),
    "weak": ("Puny", -10, False, {"strength": -5}, ("feeble", "stout", "strong")),
    "weakstomach": ("Weak Stomach", -2, False, {}, ("irongut",)),
    "weightgain": ("Slow Metabolism", -2, False, {}, ("weightloss",)),
    "weightloss": ("Fast Metabolism", -2, False, {}, ("weightgain",)),
    "whittler": ("Whittler", 2, False, {"carving": 2}, ()),
    "wildernessknowledge": (
        "Bushcrafter",
        8,
        False,
        {"foraging": 1, "knapping": 1, "maintenance": 1, "carving": 1},
        (),
    ),
}  # id: (name, cost, profession_only, skill boosts, excluded ids)

EXPECTED_OCCUPATIONS = {
    "unemployed": ("Custom Occupation", 8, (), {}),
    "burgerflipper": (
        "Burger Flipper",
        2,
        ("cook2",),
        {"cooking": 2, "maintenance": 1, "short_blade": 1},
    ),
    "tailor": ("Tailor", 2, (), {"tailoring": 4}),
    "doctor": ("Doctor", 0, (), {"first_aid": 6, "short_blade": 1}),
    "farmer": ("Farmer", 0, (), {"agriculture": 4, "animal_care": 1, "strength": 1}),
    "fireofficer": ("Firefighter", 0, (), {"running": 1, "strength": 1, "fitness": 1, "axe": 1}),
    "lumberjack": ("Lumberjack", 0, ("axeman",), {"axe": 2, "strength": 1, "maintenance": 1}),
    "nurse": ("Nurse", 0, ("nightowl",), {"first_aid": 3, "lightfooted": 1, "fitness": 1}),
    "rancher": ("Rancher", 0, (), {"animal_care": 4, "butchering": 3, "fitness": 1}),
    "carpenter": (
        "Carpenter",
        -2,
        (),
        {"carpentry": 4, "carving": 1, "short_blunt": 1, "masonry": 1, "maintenance": 1},
    ),
    "chef": (
        "Chef",
        -2,
        ("cook2",),
        {"cooking": 4, "maintenance": 1, "short_blade": 1, "butchering": 2},
    ),
    "constructionworker": (
        "Construction Worker",
        -2,
        (),
        {"short_blunt": 2, "long_blunt": 1, "masonry": 2, "carpentry": 1, "maintenance": 1},
    ),
    "electrician": ("Electrician", -2, (), {"electrical": 5}),
    "fisherman": ("Fishing Guide", -2, (), {"fishing": 3, "foraging": 1, "butchering": 1}),
    "repairman": (
        "DIY Expert",
        -2,
        ("inventive_prof",),
        {"carpentry": 1, "maintenance": 2, "short_blunt": 1, "masonry": 1},
    ),
    "securityguard": (
        "Security Guard",
        -2,
        ("nightowl",),
        {"running": 2, "lightfooted": 1, "short_blunt": 1},
    ),
    "engineer": ("Engineer", -4, (), {"electrical": 1, "carpentry": 1, "masonry": 1}),
    "mechanics": ("Mechanic", -4, ("mechanics2",), {"mechanics": 4, "welding": 1}),
    "metalworker": ("Welder", -4, (), {"welding": 4}),
    "parkranger": (
        "Park Ranger",
        -4,
        ("herbalist_prof",),
        {"trapping": 1, "first_aid": 1, "foraging": 1, "knapping": 1, "carving": 1},
    ),
    "policeofficer": ("Police Officer", -4, (), {"aiming": 4, "reloading": 1, "nimble": 1}),
    "burglar": ("Burglar", -6, ("burglar",), {"nimble": 2, "sneaking": 2, "lightfooted": 2}),
    "fitnessinstructor": (
        "Fitness Instructor",
        -6,
        ("nutritionist2",),
        {"fitness": 3, "running": 2, "strength": 1},
    ),
    "smither": (
        "Blacksmith",
        -6,
        ("blacksmith2",),
        {"blacksmithing": 4, "maintenance": 1, "short_blunt": 1},
    ),
    "veteran": ("Veteran", -8, ("desensitized",), {"aiming": 2, "reloading": 2}),
}  # id: (name, cost, granted traits, skill boosts)


class RowDataTests(unittest.TestCase):
    """Spec 07, Occupations and Traits: every row, literally."""

    def test_trait_rows(self):
        self.assertEqual(set(TRAITS), set(EXPECTED_TRAITS))
        for trait_id, (name, cost, free, boosts, excludes) in EXPECTED_TRAITS.items():
            trait = TRAITS[trait_id]
            self.assertEqual(
                (trait.name, trait.cost, trait.profession_only, trait.boosts),
                (name, cost, free, boosts),
                trait_id,
            )
            self.assertEqual(tuple(sorted(trait.excludes)), excludes, trait_id)

    def test_trait_counts(self):
        self.assertEqual(len(TRAITS), 97)
        self.assertEqual(sum(not t.profession_only for t in TRAITS.values()), 81)
        self.assertEqual(sum(t.profession_only for t in TRAITS.values()), 16)

    def test_occupation_rows(self):
        self.assertEqual(set(OCCUPATIONS), set(EXPECTED_OCCUPATIONS))
        for occ_id, (name, cost, granted, boosts) in EXPECTED_OCCUPATIONS.items():
            occupation = OCCUPATIONS[occ_id]
            self.assertEqual(
                (occupation.name, occupation.cost, occupation.granted_traits, occupation.boosts),
                (name, cost, granted, boosts),
                occ_id,
            )

    def test_ids_have_no_prefix_or_spaces(self):
        for key in (*TRAITS, *OCCUPATIONS):
            self.assertRegex(key, r"^[a-z0-9_]+$")

    def test_every_boosted_skill_is_a_known_skill(self):
        for trait in TRAITS.values():
            self.assertLessEqual(set(trait.boosts), set(SKILLS), trait.id)
        for occupation in OCCUPATIONS.values():
            self.assertLessEqual(set(occupation.boosts), set(SKILLS), occupation.id)


class OccupationDataTests(unittest.TestCase):
    """Spec 07, Occupations."""

    def test_there_are_25_occupations(self):
        self.assertEqual(len(OCCUPATIONS), 25)

    def test_costs_and_boosts_of_the_rows_the_spec_names(self):
        custom = OCCUPATIONS["unemployed"]
        self.assertEqual(
            (custom.name, custom.cost, custom.granted_traits), ("Custom Occupation", 8, ())
        )
        veteran = OCCUPATIONS["veteran"]
        self.assertEqual(veteran.cost, -8)
        self.assertEqual(veteran.granted_traits, ("desensitized",))
        self.assertEqual(veteran.boosts, {"aiming": 2, "reloading": 2})
        fire = OCCUPATIONS["fireofficer"]
        self.assertEqual(fire.cost, 0)
        self.assertEqual(fire.boosts, {"running": 1, "strength": 1, "fitness": 1, "axe": 1})
        self.assertEqual(OCCUPATIONS["chef"].granted_traits, ("cook2",))
        self.assertEqual(OCCUPATIONS["burgerflipper"].cost, 2)

    def test_every_granted_trait_exists_and_is_profession_only(self):
        for occupation in OCCUPATIONS.values():
            for trait_id in occupation.granted_traits:
                self.assertTrue(TRAITS[trait_id].profession_only, trait_id)


class TraitDataTests(unittest.TestCase):
    """Spec 07, Traits."""

    def test_costs_the_spec_gives(self):
        self.assertEqual(TRAITS["strong"].cost, 10)
        self.assertEqual(TRAITS["hemophobic"].cost, -5)
        self.assertEqual(TRAITS["shortsighted"].cost, -2)
        self.assertEqual(TRAITS["fastreader"].cost, 2)
        self.assertEqual(TRAITS["fastlearner"].cost, 6)
        self.assertEqual(TRAITS["brave"].cost, 4)

    def test_boosts_the_spec_gives(self):
        self.assertEqual(TRAITS["strong"].boosts, {"strength": 4})
        self.assertEqual(TRAITS["unfit"].boosts, {"fitness": -4})
        self.assertEqual(TRAITS["weak"].boosts, {"strength": -5})

    def test_names_of_the_effect_traits(self):
        names = {
            "heartyappetite": "Hearty Appetite",
            "lighteater": "Light Eater",
            "highthirst": "High Thirst",
            "lowthirst": "Low Thirst",
            "needslesssleep": "Wakeful",
            "needsmoresleep": "Sleepyhead",
            "insomniac": "Restless Sleeper",
            "nightowl": "Night Owl",
            "cowardly": "Cowardly",
            "brave": "Brave",
            "desensitized": "Desensitized",
            "pronetoillness": "Prone to Illness",
            "resilient": "Resilient",
            "outdoorsman": "Outdoorsy",
        }
        for trait_id, name in names.items():
            self.assertEqual(TRAITS[trait_id].name, name)

    def test_the_two_traits_that_grant_traits(self):
        granting = {t.id: t.granted_traits for t in TRAITS.values() if t.granted_traits}
        self.assertEqual(granting, {"weightgain": ("overweight",), "weightloss": ("underweight",)})
        self.assertEqual(TRAITS["overweight"].boosts, {"fitness": -1})
        self.assertEqual(TRAITS["underweight"].boosts, {"fitness": -1})

    def test_every_exclusion_names_a_trait(self):
        for trait in TRAITS.values():
            for other in trait.excludes:
                self.assertIn(other, TRAITS, f"{trait.id} excludes unknown {other}")

    def test_keen_cook_chosen_and_granted_exclude_each_other(self):
        self.assertIn("cook2", TRAITS["cook"].excludes)

    def test_weight_traits_are_profession_only_and_granted_by_nobody(self):
        weight = ["emaciated", "very_underweight", "underweight", "overweight", "obese"]
        granted = {t for o in OCCUPATIONS.values() for t in o.granted_traits}
        for trait_id in weight:
            self.assertTrue(TRAITS[trait_id].profession_only)
            self.assertNotIn(trait_id, granted)


class NameAndClothingDataTests(unittest.TestCase):
    """Spec 07, Appearance and identity and Starting outfit."""

    def test_name_lists_have_30_entries_each_under_20_characters(self):
        for names in (FEMALE_FORENAMES, MALE_FORENAMES, SURNAMES):
            self.assertEqual(len(names), 30)
            self.assertEqual(len(set(names)), 30)
            self.assertTrue(all(0 < len(name) < 20 for name in names))
