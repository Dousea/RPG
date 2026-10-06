"""Spec 07, Character Creation: the point pool, starting skills, randomize and the Orton preset."""

import random
import unittest

from data.names import FEMALE_FORENAMES, MALE_FORENAMES, SURNAMES
from data.presets import ORTON, ORTON_POINTS_LEFT
from managers import creation
from modules.body import BodyLocation
from modules.character.appearance import Appearance, Gender
from modules.character.build import CharacterBuild

CUSTOM = "unemployed"


def build(occupation: str = CUSTOM, traits: tuple[str, ...] = (), **kwargs) -> CharacterBuild:
    return CharacterBuild(
        appearance=kwargs.pop("appearance", Appearance(forename="Sam")),
        occupation_id=occupation,
        traits=traits,
        **kwargs,
    )


class PointPoolTests(unittest.TestCase):
    """Spec 07, Point pool."""

    def test_custom_occupation_with_strong_is_minus_two_and_refused(self):
        b = build(traits=("strong",))
        self.assertEqual(creation.resolve(b).points_left, -2)
        errors = creation.validate(b)
        self.assertEqual(len(errors), 1)
        self.assertIn("points", errors[0])

    def test_adding_fear_of_blood_gives_three_and_is_accepted(self):
        b = build(traits=("strong", "hemophobic"))
        self.assertEqual(creation.resolve(b).points_left, 3)
        self.assertEqual(creation.validate(b), [])

    def test_exactly_zero_points_is_accepted(self):
        b = build(traits=("strong", "cowardly"))
        self.assertEqual(creation.resolve(b).points_left, 0)
        self.assertEqual(creation.validate(b), [])

    def test_veteran_needs_eight_points_of_bad_traits_before_any_good_trait(self):
        self.assertEqual(creation.resolve(build("veteran")).points_left, -8)
        self.assertNotEqual(creation.validate(build("veteran")), [])
        self.assertEqual(creation.resolve(build("veteran", ("unfit",))).points_left, 2)
        self.assertEqual(creation.validate(build("veteran", ("unfit",))), [])

    def test_granted_traits_cost_nothing(self):
        self.assertEqual(creation.resolve(build("chef")).points_left, -2)
        self.assertEqual(creation.resolve(build("chef")).granted_traits, ("cook2",))

    def test_choosing_veteran_while_brave_is_chosen_drops_brave_and_refunds_four(self):
        before = creation.resolve(build(CUSTOM, ("brave", "hemophobic")))
        kept = creation.change_occupation(CUSTOM, "veteran", ("brave", "shortsighted"))
        self.assertEqual(kept, ("shortsighted",))
        with_brave = creation.resolve(build("veteran", ("brave", "shortsighted")))
        without = creation.resolve(build("veteran", kept))
        self.assertEqual(without.points_left - with_brave.points_left, 4)
        self.assertEqual(before.points_left, 8 - 4 + 5)

    def test_changing_occupation_leaves_unrelated_traits(self):
        kept = creation.change_occupation("chef", CUSTOM, ("strong", "hemophobic"))
        self.assertEqual(kept, ("strong", "hemophobic"))


class ExclusionTests(unittest.TestCase):
    """Spec 07, Traits."""

    def test_excluded_pairs_are_refused_in_both_directions(self):
        for first, second in (("brave", "cowardly"), ("cowardly", "brave")):
            errors = creation.validate(build(traits=(first, second)))
            self.assertTrue(any("together" in e for e in errors), errors)

    def test_a_chosen_trait_excluded_by_a_granted_trait_is_refused(self):
        errors = creation.validate(build("veteran", ("brave", "hemophobic", "unfit")))
        self.assertTrue(any("brave" in e.lower() for e in errors), errors)

    def test_a_chef_cannot_also_buy_keen_cook(self):
        errors = creation.validate(build("chef", ("cook", "hemophobic")))
        self.assertTrue(any("together" in e for e in errors), errors)

    def test_profession_only_traits_cannot_be_chosen(self):
        errors = creation.validate(build(traits=("nightowl", "hemophobic")))
        self.assertTrue(any("occupation" in e for e in errors), errors)

    def test_unknown_ids_are_named(self):
        errors = creation.validate(build(traits=("nosuchtrait",)))
        self.assertTrue(any("nosuchtrait" in e for e in errors), errors)
        errors = creation.validate(build("nosuchjob"))
        self.assertTrue(any("nosuchjob" in e for e in errors), errors)

    def test_duplicate_traits_are_refused(self):
        errors = creation.validate(build(traits=("hemophobic", "hemophobic", "strong")))
        self.assertTrue(any("twice" in e for e in errors), errors)


class StartingSkillTests(unittest.TestCase):
    """Spec 07, Starting skills."""

    def test_base_fitness_and_strength_are_five_and_the_rest_zero(self):
        resolved = creation.resolve(build())
        self.assertEqual(resolved.skills["fitness"], 5)
        self.assertEqual(resolved.skills["strength"], 5)
        self.assertEqual(resolved.skills["cooking"], 0)
        self.assertEqual(resolved.skill_boosts["cooking"], 0)

    def test_firefighter_with_strong_has_strength_ten_and_boost_three(self):
        resolved = creation.resolve(build("fireofficer", ("strong", "hemophobic")))
        self.assertEqual(resolved.skills["strength"], 10)
        self.assertEqual(resolved.skill_boosts["strength"], 3)
        self.assertEqual(resolved.skills["fitness"], 6)
        self.assertEqual(resolved.skill_boosts["fitness"], 3)
        self.assertEqual(resolved.skills["axe"], 1)
        self.assertEqual(resolved.skill_boosts["axe"], 1)

    def test_custom_occupation_with_unfit_has_fitness_one_and_boost_one(self):
        resolved = creation.resolve(build(CUSTOM, ("unfit",)))
        self.assertEqual(resolved.skills["fitness"], 1)
        self.assertEqual(resolved.skill_boosts["fitness"], 1)

    def test_levels_clamp_to_zero_and_ten(self):
        high = creation.resolve(build("fitnessinstructor", ("athletic",)))
        self.assertEqual(high.skills["fitness"], 10)
        low = creation.resolve(build(CUSTOM, ("weak", "unfit")))
        self.assertEqual(low.skills["strength"], 0)
        self.assertEqual(low.skill_boosts["strength"], 0)

    def test_boost_is_the_level_capped_at_three(self):
        resolved = creation.resolve(build("doctor"))
        self.assertEqual(resolved.skills["first_aid"], 6)
        self.assertEqual(resolved.skill_boosts["first_aid"], 3)
        self.assertEqual(resolved.skills["short_blade"], 1)
        self.assertEqual(resolved.skill_boosts["short_blade"], 1)
        self.assertEqual(creation.resolve(build("nurse")).skill_boosts["first_aid"], 3)
        self.assertEqual(creation.resolve(build("burglar")).skill_boosts["nimble"], 2)


class FieldValidationTests(unittest.TestCase):
    """Spec 07, Appearance and identity."""

    def test_name_lengths(self):
        self.assertNotEqual(creation.validate(build(appearance=Appearance(forename=""))), [])
        too_long = Appearance(forename="A" * 21)
        self.assertNotEqual(
            creation.validate(build(appearance=too_long, traits=("hemophobic",))), []
        )
        exact = Appearance(forename="A" * 20, surname="B" * 20)
        self.assertEqual(creation.validate(build(appearance=exact)), [])
        self.assertNotEqual(
            creation.validate(build(appearance=Appearance(forename="A", surname="B" * 21))), []
        )

    def test_backstory_job_title_and_skin_tone_limits(self):
        self.assertEqual(
            creation.validate(build(appearance=Appearance("A", backstory="x" * 200))), []
        )
        self.assertNotEqual(
            creation.validate(build(appearance=Appearance("A", backstory="x" * 201))), []
        )
        self.assertEqual(creation.validate(build(job_title="j" * 40)), [])
        self.assertNotEqual(creation.validate(build(job_title="j" * 41)), [])
        self.assertNotEqual(creation.validate(build(appearance=Appearance("A", skin_tone=0))), [])
        self.assertNotEqual(creation.validate(build(appearance=Appearance("A", skin_tone=6))), [])

    def test_beards_are_for_male_characters_only(self):
        female = Appearance("A", gender=Gender.FEMALE, beard_style="full beard")
        self.assertNotEqual(creation.validate(build(appearance=female)), [])
        male = Appearance("A", gender=Gender.MALE, beard_style="full beard")
        self.assertEqual(creation.validate(build(appearance=male)), [])

    def test_unknown_hair_is_refused(self):
        self.assertNotEqual(
            creation.validate(build(appearance=Appearance("A", hair_style="mohawk-xl"))), []
        )

    def test_outfit_must_be_allowed_one_item_per_location(self):
        self.assertEqual(creation.validate(build(outfit=("item_tshirt", "item_jeans"))), [])
        self.assertNotEqual(creation.validate(build(outfit=("item_crowbar",))), [])
        self.assertNotEqual(creation.validate(build(outfit=("item_nonexistent",))), [])


class RandomizeTests(unittest.TestCase):
    """Spec 07, Components."""

    def test_randomize_is_valid_with_zero_to_three_points_left_for_1000_seeds(self):
        for seed in range(1000):
            b = creation.randomize(random.Random(seed))
            self.assertEqual(creation.validate(b), [], f"seed {seed}")
            self.assertTrue(0 <= creation.resolve(b).points_left <= 3, f"seed {seed}")

    def test_randomize_draws_names_from_the_lists_by_gender(self):
        for seed in range(100):
            appearance = creation.randomize(random.Random(seed)).appearance
            forenames = FEMALE_FORENAMES if appearance.gender == Gender.FEMALE else MALE_FORENAMES
            self.assertIn(appearance.forename, forenames)
            self.assertIn(appearance.surname, SURNAMES)

    def test_randomize_is_deterministic_for_a_seed(self):
        self.assertEqual(creation.randomize(random.Random(7)), creation.randomize(random.Random(7)))

    def test_randomize_varies_across_seeds(self):
        builds = {creation.randomize(random.Random(seed)) for seed in range(20)}
        self.assertGreater(len(builds), 10)


class PresetTests(unittest.TestCase):
    """Spec 07, Presets."""

    def test_orton_resolves_to_seven_points_left(self):
        self.assertEqual(creation.resolve(ORTON).points_left, 7)
        self.assertEqual(ORTON_POINTS_LEFT, 7)

    def test_orton_is_a_valid_build_matching_the_table(self):
        self.assertEqual(creation.validate(ORTON), [])
        self.assertEqual(ORTON.appearance.forename, "Orton")
        self.assertEqual(ORTON.appearance.surname, "")
        self.assertEqual(ORTON.appearance.gender, Gender.MALE)
        self.assertEqual(ORTON.occupation_id, CUSTOM)
        self.assertEqual(ORTON.job_title, "Software Developer")
        self.assertEqual(
            sorted(ORTON.traits),
            sorted(["hemophobic", "shortsighted", "fastreader", "fastlearner"]),
        )
        self.assertEqual(
            ORTON.outfit,
            ("item_tshirt", "item_hoodie", "item_jeans", "item_ankle_socks", "item_trainers"),
        )
        self.assertEqual(ORTON.appearance.backstory, "Just moved into apartment 3B in Portland.")


class NewPlayerTests(unittest.TestCase):
    """Spec 07, Components."""

    def test_new_player_carries_the_build_and_resolved_values(self):
        b = build(
            "fireofficer",
            ("strong", "hemophobic"),
            appearance=Appearance(forename="Jo", surname="Reyes", gender=Gender.FEMALE),
            outfit=("item_tshirt", "item_trainers"),
        )
        player = creation.new_player(b)
        self.assertEqual(player.name, "Jo Reyes")
        self.assertEqual(player.appearance.forename, "Jo")
        self.assertEqual(player.occupation_id, "fireofficer")
        self.assertEqual(player.traits, ["strong", "hemophobic"])
        self.assertEqual(player.skills["strength"], 10)
        self.assertEqual(player.skill_boosts["strength"], 3)
        self.assertEqual(
            sorted(e.item.id for e in player.worn.values()), ["item_trainers", "item_tshirt"]
        )
        self.assertEqual([e.item.id for e in player.inventory], ["item_apartment_key"])
        self.assertEqual(player.current_location_id, "zone_home")

    def test_granted_traits_come_first_on_the_player(self):
        player = creation.new_player(build("veteran", ("unfit",)))
        self.assertEqual(player.traits, ["desensitized", "unfit"])


class TraitGrantedTraitTests(unittest.TestCase):
    """Spec 07, Traits that grant traits."""

    def test_slow_metabolism_grants_high_weight(self):
        b = build(traits=("weightgain",))
        resolved = creation.resolve(b)
        self.assertEqual(resolved.granted_traits, ("overweight",))
        self.assertEqual(resolved.traits, ("overweight", "weightgain"))
        self.assertEqual(resolved.skills["fitness"], 4)
        self.assertEqual(resolved.skill_boosts["fitness"], 3)
        self.assertEqual(resolved.points_left, 10)
        self.assertEqual(creation.validate(b), [])

    def test_fast_metabolism_grants_low_weight(self):
        resolved = creation.resolve(build(traits=("weightloss",)))
        self.assertEqual(resolved.granted_traits, ("underweight",))
        self.assertEqual(resolved.skills["fitness"], 4)
        self.assertEqual(resolved.points_left, 10)

    def test_dropping_slow_metabolism_drops_high_weight(self):
        resolved = creation.resolve(build())
        self.assertEqual(resolved.granted_traits, ())
        self.assertNotIn("overweight", resolved.traits)
        self.assertEqual(resolved.skills["fitness"], 5)

    def test_player_holds_the_granted_trait(self):
        player = creation.new_player(build(traits=("weightgain",)))
        self.assertEqual(player.traits, ["overweight", "weightgain"])

    def test_slow_metabolism_with_fit_is_refused_in_either_order(self):
        for traits in (("weightgain", "fit"), ("fit", "weightgain")):
            with self.subTest(traits=traits):
                self.assertEqual(len(creation.validate(build(traits=traits))), 1)

    def test_slow_metabolism_with_athletic_is_refused(self):
        self.assertTrue(creation.validate(build(traits=("athletic", "weightgain"))))

    def test_a_granted_weight_trait_cannot_be_chosen_by_hand(self):
        self.assertTrue(creation.validate(build(traits=("overweight",))))

    def test_swapping_occupation_keeps_slow_metabolism_unless_clashing(self):
        self.assertEqual(
            creation.change_occupation(CUSTOM, "fitnessinstructor", ("weightgain",)),
            ("weightgain",),
        )

    def test_randomize_never_pairs_a_metabolism_trait_with_a_clash(self):
        for seed in range(1000):
            b = creation.randomize(random.Random(seed))
            self.assertEqual(creation.validate(b), [], seed)


class FixRoundTests(unittest.TestCase):
    """Spec 07, Point pool, Occupations, Starting skills and Starting outfit."""

    def test_one_point_over_is_refused(self):
        b = build(traits=("handy", "speeddemon"))
        self.assertEqual(creation.resolve(b).points_left, -1)
        self.assertTrue(any("1 points over" in e for e in creation.validate(b)))

    def test_swapping_occupation_drops_the_old_granted_traits(self):
        kept = creation.change_occupation("chef", CUSTOM, ("cook2", "strong"))
        self.assertEqual(kept, ("strong",))

    def test_two_starting_items_at_one_location_are_refused(self):
        b = build(outfit=("item_tshirt", "item_polo"))
        errors = creation.validate(b)
        self.assertEqual(errors, ["Only one item can be worn at base:tshirt."])

    def test_granted_trait_boosts_add_to_the_occupation_boosts(self):
        resolved = creation.resolve(build("parkranger"))
        self.assertEqual(resolved.granted_traits, ("herbalist_prof",))
        self.assertEqual(resolved.skills["foraging"], 2)

    def test_chosen_trait_boosts_add_to_skills(self):
        self.assertEqual(creation.resolve(build(traits=("hunter",))).skills["tracking"], 1)

    def test_a_female_only_list_serves_male_characters(self):
        lists = creation.clothing_lists(Gender.MALE, "nurse", ())
        self.assertIn("item_scrubs_top", lists[BodyLocation.SHIRT].items)
