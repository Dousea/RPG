"""Spec 12, Treatment: BANDAGE, REMOVE_BANDAGE, DISINFECT, painkillers and antibiotics."""

import random
import unittest

from data.items import ITEMS
from managers.body.first_aid import FirstAid, most_needed_part
from managers.character.skills import SkillEngine
from managers.game import GameManager
from managers.validator import Accepted, ActionValidator, Rejected
from modules.action.parser import ParseFailure, parse_action_line
from modules.action.types import (
    BandageAction,
    DisinfectAction,
    RemoveBandageAction,
    UseItemAction,
)
from modules.body.parts import BodyPart
from modules.body.stats import CharacterStat
from modules.character.skills import SkillState
from modules.entity.item import ItemEntity
from modules.entity.player import PlayerEntity
from modules.resolution import FirstAidTarget
from tests.support import simulate


def game_with(*item_ids: str) -> GameManager:
    gm = GameManager()
    gm.player.traits = []
    gm.player.inventory.clear()
    for item_id in item_ids:
        gm.player.inventory.append(ItemEntity(item=ITEMS[item_id]))
    return gm


class RecordingSkills(SkillEngine):
    """Records the XP handed out before the skill spec's multipliers."""

    def __init__(self) -> None:
        super().__init__()
        self.awarded: list[tuple[str, float]] = []

    def add_xp(
        self, player: PlayerEntity, skill_id: str, amount: float, *, chain: bool = True
    ) -> list[str]:
        self.awarded.append((skill_id, amount))
        return []


def first_aid(gm: GameManager, seed: int = 0, skills: SkillEngine | None = None) -> FirstAid:
    return FirstAid(random.Random(seed), skills or SkillEngine())


def set_first_aid(gm: GameManager, level: int) -> None:
    gm.player.skills["first_aid"] = SkillState(level=level, xp=0)


class ParseTests(unittest.TestCase):
    """Spec 12, Treatment: the three verbs' arguments."""

    def test_bandage_with_a_part_and_an_item(self):
        self.assertEqual(
            parse_action_line("BANDAGE left forearm with Sterilized Bandage"),
            BandageAction(part_name="left forearm", item_name="Sterilized Bandage"),
        )

    def test_bandage_with_only_a_part(self):
        self.assertEqual(
            parse_action_line("BANDAGE left forearm"), BandageAction(part_name="left forearm")
        )

    def test_bandage_with_no_part_picks_one_later(self):
        self.assertEqual(parse_action_line("BANDAGE"), BandageAction())

    def test_with_is_matched_whatever_its_case(self):
        self.assertEqual(
            parse_action_line("BANDAGE neck With Bandage"),
            BandageAction(part_name="neck", item_name="Bandage"),
        )

    def test_remove_bandage_needs_a_part(self):
        self.assertEqual(
            parse_action_line("REMOVE_BANDAGE right hand"),
            RemoveBandageAction(part_name="right hand"),
        )
        self.assertIsInstance(parse_action_line("REMOVE_BANDAGE"), ParseFailure)

    def test_disinfect_with_a_part_and_an_item(self):
        self.assertEqual(
            parse_action_line("DISINFECT head with Alcohol Wipes"),
            DisinfectAction(part_name="head", item_name="Alcohol Wipes"),
        )
        self.assertIsInstance(parse_action_line("DISINFECT"), ParseFailure)


class BandageTests(unittest.TestCase):
    """Spec 12, `BANDAGE`."""

    def bandage(self, level: int, seed: int = 0, item_id: str = "item_bandage"):
        gm = game_with(item_id)
        set_first_aid(gm, level)
        gm.player.body[BodyPart.FOREARM_L].scratch_time = 8.0
        entity = gm.player.inventory[0]
        facts = first_aid(gm, seed).bandage(gm.player, BodyPart.FOREARM_L, entity)
        return gm, facts

    def test_life_at_first_aid_zero_is_between_4_5_and_5(self):
        for seed in range(50):
            gm, _ = self.bandage(0, seed)
            life = gm.player.body[BodyPart.FOREARM_L].bandage_life
            self.assertTrue(4.5 <= life <= 5.0, life)

    def test_life_at_first_aid_five_is_between_7_and_10(self):
        for seed in range(50):
            gm, _ = self.bandage(5, seed)
            life = gm.player.body[BodyPart.FOREARM_L].bandage_life
            self.assertTrue(7.0 <= life <= 10.0, life)

    def test_the_bandage_goes_on_the_part_and_leaves_the_inventory(self):
        gm, facts = self.bandage(0)
        state = gm.player.body[BodyPart.FOREARM_L]
        self.assertEqual(state.bandage, "item_bandage")
        self.assertFalse(state.bandage_alcoholic)
        self.assertEqual(gm.player.inventory, [])
        self.assertEqual(facts[0], "Orton bandages the left forearm.")

    def test_a_sterilized_bandage_marks_the_part_alcoholic(self):
        gm, _ = self.bandage(0, item_id="item_sterilized_bandage")
        self.assertTrue(gm.player.body[BodyPart.FOREARM_L].bandage_alcoholic)

    def xp_after(self, level: int, bandages: int = 1) -> list[tuple[str, float]]:
        gm = game_with(*["item_bandage"] * bandages)
        set_first_aid(gm, level)
        gm.player.body[BodyPart.FOREARM_L].scratch_time = 8.0
        skills = RecordingSkills()
        engine = first_aid(gm, skills=skills)
        for _ in range(bandages):
            state = gm.player.body[BodyPart.FOREARM_L]
            state.bandage = None
            engine.bandage(gm.player, BodyPart.FOREARM_L, gm.player.inventory[0])
        return skills.awarded

    def test_first_aid_gains_five_xp_the_first_time(self):
        self.assertEqual(self.xp_after(0), [("first_aid", 5)])

    def test_first_aid_gains_five_xp_at_level_five_too(self):
        self.assertEqual(self.xp_after(5), [("first_aid", 5)])

    def test_the_same_wound_pays_xp_only_once(self):
        self.assertEqual(self.xp_after(0, bandages=2), [("first_aid", 5)])

    def test_the_xp_reaches_the_skill_through_the_skill_rules(self):
        gm, _ = self.bandage(0)
        self.assertGreater(gm.player.skills["first_aid"].xp, 0)
        self.assertFalse(gm.player.body[BodyPart.FOREARM_L].bandage_xp_ready)

    def test_a_dirty_bandage_has_no_life_and_pays_no_xp(self):
        gm, _ = self.bandage(0, item_id="item_dirty_bandage")
        state = gm.player.body[BodyPart.FOREARM_L]
        self.assertEqual(state.bandage_life, 0.0)
        self.assertEqual(state.bandage, "item_dirty_bandage")
        self.assertEqual(gm.player.skills.get("first_aid", SkillState()).xp, 0)
        self.assertTrue(state.bandage_xp_ready)

    def test_fear_of_blood_adds_fifty_panic_on_a_bleeding_part(self):
        gm = game_with("item_bandage")
        gm.player.traits = ["hemophobic"]
        gm.player.body[BodyPart.FOREARM_L].cut_time = 8.0
        gm.player.body[BodyPart.FOREARM_L].bleeding_time = 3.0
        first_aid(gm).bandage(gm.player, BodyPart.FOREARM_L, gm.player.inventory[0])
        self.assertEqual(gm.player.stats.get(CharacterStat.PANIC), 50)

    def test_fear_of_blood_adds_nothing_when_the_part_is_not_bleeding(self):
        gm = game_with("item_bandage")
        gm.player.traits = ["hemophobic"]
        gm.player.body[BodyPart.FOREARM_L].scratch_time = 8.0
        first_aid(gm).bandage(gm.player, BodyPart.FOREARM_L, gm.player.inventory[0])
        self.assertEqual(gm.player.stats.get(CharacterStat.PANIC), 0)

    def test_without_the_trait_there_is_no_panic(self):
        gm = game_with("item_bandage")
        gm.player.body[BodyPart.FOREARM_L].bleeding_time = 3.0
        first_aid(gm).bandage(gm.player, BodyPart.FOREARM_L, gm.player.inventory[0])
        self.assertEqual(gm.player.stats.get(CharacterStat.PANIC), 0)


class MostNeededPartTests(unittest.TestCase):
    """Spec 12, `BANDAGE <part> [with <item>]`: no part given."""

    def test_a_bleeding_part_beats_a_scratch(self):
        gm = GameManager()
        gm.player.body[BodyPart.HAND_L].scratch_time = 5.0
        gm.player.body[BodyPart.FOREARM_R].cut_time = 5.0
        gm.player.body[BodyPart.FOREARM_R].bleeding_time = 3.0
        self.assertEqual(most_needed_part(gm.player), BodyPart.FOREARM_R)

    def test_bleeding_plus_a_bite_scores_one_fifty(self):
        gm = GameManager()
        gm.player.body[BodyPart.HAND_L].bleeding_time = 2.0
        gm.player.body[BodyPart.NECK].bleeding_time = 2.0
        gm.player.body[BodyPart.NECK].bite_time = 30.0
        self.assertEqual(most_needed_part(gm.player), BodyPart.NECK)

    def test_ties_go_to_the_first_part_in_body_order(self):
        gm = GameManager()
        gm.player.body[BodyPart.FOOT_R].scratch_time = 5.0
        gm.player.body[BodyPart.UPPERARM_L].scratch_time = 5.0
        self.assertEqual(most_needed_part(gm.player), BodyPart.UPPERARM_L)

    def test_bandaged_parts_do_not_count(self):
        gm = GameManager()
        gm.player.body[BodyPart.HAND_L].scratch_time = 5.0
        gm.player.body[BodyPart.HAND_L].bandage = "item_bandage"
        self.assertIsNone(most_needed_part(gm.player))

    def test_nothing_injured_gives_none(self):
        self.assertIsNone(most_needed_part(GameManager().player))


class RemoveBandageTests(unittest.TestCase):
    """Spec 12, `REMOVE_BANDAGE <part>`."""

    def wear(self, item_id: str, life: float):
        gm = game_with()
        state = gm.player.body[BodyPart.HAND_L]
        state.scratch_time = 5.0
        state.bandage = item_id
        state.bandage_life = life
        return gm, state

    def test_a_soaked_bandage_comes_back_as_its_dirty_version(self):
        gm, state = self.wear("item_bandage", 0.0)
        facts = first_aid(gm).remove_bandage(gm.player, BodyPart.HAND_L)
        self.assertEqual([e.item.id for e in gm.player.inventory], ["item_dirty_bandage"])
        self.assertIsNone(state.bandage)
        self.assertEqual(facts[0], "Orton takes the dirty bandage off the left hand.")

    def test_a_bandage_with_life_left_comes_back_as_it_was(self):
        gm, _ = self.wear("item_sterilized_bandage", 2.0)
        facts = first_aid(gm).remove_bandage(gm.player, BodyPart.HAND_L)
        self.assertEqual([e.item.id for e in gm.player.inventory], ["item_sterilized_bandage"])
        self.assertEqual(facts[0], "Orton takes the bandage off the left hand.")

    def test_an_adhesive_bandage_is_gone_once_spent(self):
        gm, _ = self.wear("item_adhesive_bandage", 0.0)
        first_aid(gm).remove_bandage(gm.player, BodyPart.HAND_L)
        self.assertEqual(gm.player.inventory, [])

    def test_an_already_dirty_reusable_item_comes_back_as_it_is(self):
        gm, _ = self.wear("item_dirty_bandage", 0.0)
        first_aid(gm).remove_bandage(gm.player, BodyPart.HAND_L)
        self.assertEqual([e.item.id for e in gm.player.inventory], ["item_dirty_bandage"])

    def test_the_part_loses_its_bandage_fields(self):
        gm, state = self.wear("item_sterilized_bandage", 2.0)
        state.bandage_alcoholic = True
        first_aid(gm).remove_bandage(gm.player, BodyPart.HAND_L)
        self.assertEqual(
            (state.bandage, state.bandage_life, state.bandage_alcoholic), (None, 0.0, False)
        )


class DisinfectTests(unittest.TestCase):
    """Spec 12, `DISINFECT <part> [with <item>]`."""

    def disinfect(self, level: int, item_id: str = "item_alcohol_wipes"):
        gm = game_with(item_id)
        set_first_aid(gm, level)
        state = gm.player.body[BodyPart.HAND_L]
        state.scratch_time = 5.0
        facts = first_aid(gm).disinfect(gm.player, BodyPart.HAND_L, gm.player.inventory[0])
        return gm, state, facts

    def test_it_adds_four_alcohol_and_fifty_two_pain_at_first_aid_zero(self):
        _, state, _ = self.disinfect(0)
        self.assertEqual(state.alcohol, 4.0)
        self.assertAlmostEqual(state.extra_pain, 52.0)

    def test_the_pain_is_forty_nine_and_a_half_at_first_aid_five(self):
        _, state, _ = self.disinfect(5)
        self.assertAlmostEqual(state.extra_pain, 49.5)

    def test_it_spends_one_use(self):
        gm, _, facts = self.disinfect(0)
        self.assertEqual(gm.player.inventory[0].uses, 4)
        self.assertEqual(facts[0], "Orton dabs disinfectant on the left hand. It stings.")

    def test_the_last_use_uses_the_item_up(self):
        gm = game_with("item_alcohol_wipes")
        gm.player.inventory[0].uses = 1
        gm.player.body[BodyPart.HAND_L].scratch_time = 5.0
        first_aid(gm).disinfect(gm.player, BodyPart.HAND_L, gm.player.inventory[0])
        self.assertEqual(gm.player.inventory, [])

    def test_it_gives_no_xp(self):
        gm, _, _ = self.disinfect(0)
        self.assertEqual(gm.player.skills.get("first_aid", SkillState()).xp, 0)


class PillTests(unittest.TestCase):
    """Spec 12, Painkillers and Antibiotics."""

    def test_a_painkiller_starts_forty_eight_minutes_and_spends_a_pill(self):
        gm = game_with("item_painkillers")
        facts = first_aid(gm).take_pill(gm.player, gm.player.inventory[0])
        self.assertEqual(gm.player.pain_effect_minutes, 48)
        self.assertEqual(gm.player.inventory[0].uses, 9)
        self.assertEqual(facts, ["Orton takes a painkiller."])

    def test_a_second_pill_restarts_the_effect_without_stacking(self):
        gm = game_with("item_painkillers")
        engine = first_aid(gm)
        engine.take_pill(gm.player, gm.player.inventory[0])
        gm.player.pain_effect_minutes = 20
        engine.take_pill(gm.player, gm.player.inventory[0])
        self.assertEqual(gm.player.pain_effect_minutes, 48)

    def test_the_last_pill_uses_the_bottle_up(self):
        gm = game_with("item_painkillers")
        gm.player.inventory[0].uses = 1
        first_aid(gm).take_pill(gm.player, gm.player.inventory[0])
        self.assertEqual(gm.player.inventory, [])

    def test_antibiotics_set_the_power_to_fifty_and_are_consumed(self):
        gm = game_with("item_antibiotics")
        gm.player.reduce_infection_power = 12.0
        first_aid(gm).take_antibiotic(gm.player, gm.player.inventory[0])
        self.assertEqual(gm.player.reduce_infection_power, 50.0)
        self.assertEqual(gm.player.inventory, [])


class TreatmentRefusalTests(unittest.TestCase):
    """Spec 12, Treatment and Edge cases: every refusal costs 0 minutes."""

    def refusal(self, gm: GameManager, action) -> str:
        result = ActionValidator(gm).validate(action)
        assert isinstance(result, Rejected), result
        return result.reason

    def test_a_part_that_is_not_hurt_is_refused(self):
        gm = game_with("item_bandage")
        self.assertEqual(
            self.refusal(gm, BandageAction(part_name="left hand")), "The left hand isn't hurt."
        )

    def test_a_part_that_is_already_bandaged_is_refused(self):
        gm = game_with("item_bandage")
        gm.player.body[BodyPart.HAND_L].scratch_time = 3.0
        gm.player.body[BodyPart.HAND_L].bandage = "item_bandage"
        self.assertIn("Remove it first", self.refusal(gm, BandageAction(part_name="left hand")))

    def test_no_bandage_item_is_refused(self):
        gm = game_with()
        gm.player.body[BodyPart.HAND_L].scratch_time = 3.0
        self.assertIn(
            "nothing to bandage with", self.refusal(gm, BandageAction(part_name="left hand"))
        )

    def test_no_part_given_and_nothing_hurt_is_refused(self):
        gm = game_with("item_bandage")
        self.assertIn("nothing to bandage", self.refusal(gm, BandageAction()))

    def test_an_unknown_part_is_refused(self):
        gm = game_with("item_bandage")
        self.assertIn("tail", self.refusal(gm, BandageAction(part_name="tail")))

    def test_a_named_item_that_is_not_carried_is_refused(self):
        gm = game_with("item_bandage")
        gm.player.body[BodyPart.HAND_L].scratch_time = 3.0
        self.assertIn(
            "Sterilized",
            self.refusal(gm, BandageAction(part_name="left hand", item_name="Sterilized Bandage")),
        )

    def test_a_named_item_that_is_no_bandage_is_refused(self):
        gm = game_with("item_alcohol_wipes")
        gm.player.body[BodyPart.HAND_L].scratch_time = 3.0
        self.assertIn(
            "bandage",
            self.refusal(gm, BandageAction(part_name="left hand", item_name="Alcohol Wipes")),
        )

    def test_remove_bandage_with_none_on_is_refused(self):
        gm = game_with()
        self.assertEqual(
            self.refusal(gm, RemoveBandageAction(part_name="left hand")),
            "The left hand has no bandage.",
        )

    def test_disinfect_needs_an_unbandaged_hurt_part_and_alcohol_with_uses(self):
        gm = game_with()
        self.assertEqual(
            self.refusal(gm, DisinfectAction(part_name="left hand")), "The left hand isn't hurt."
        )
        gm.player.body[BodyPart.HAND_L].scratch_time = 3.0
        self.assertIn(
            "nothing to disinfect with", self.refusal(gm, DisinfectAction(part_name="left hand"))
        )
        gm.player.body[BodyPart.HAND_L].bandage = "item_bandage"
        self.assertIn("Remove it first", self.refusal(gm, DisinfectAction(part_name="left hand")))

    def test_each_verb_refuses_while_asleep(self):
        gm = game_with("item_bandage", "item_alcohol_wipes")
        gm.player.body[BodyPart.HAND_L].scratch_time = 3.0
        gm.player.asleep = True
        for action in (
            BandageAction(part_name="left hand"),
            DisinfectAction(part_name="left hand"),
            RemoveBandageAction(part_name="left hand"),
        ):
            self.assertIn("asleep", self.refusal(gm, action))

    def test_refusals_cost_no_minutes(self):
        gm = game_with("item_bandage")
        before = gm.narrative.minutes
        facts = simulate(
            gm,
            BandageAction(part_name="left hand"),
            RemoveBandageAction(part_name="left hand"),
            DisinfectAction(part_name="left hand"),
        )
        self.assertEqual(gm.narrative.minutes, before)
        self.assertEqual(sum(fact.startswith("Refused:") for fact in facts), 3)
        self.assertFalse(any("minute" in fact for fact in facts))

    def test_validation_never_mutates(self):
        gm = game_with("item_bandage")
        gm.player.body[BodyPart.HAND_L].scratch_time = 3.0
        result = ActionValidator(gm).validate(BandageAction(part_name="left hand"))
        self.assertIsInstance(result, Accepted)
        self.assertEqual(len(gm.player.inventory), 1)
        self.assertIsNone(gm.player.body[BodyPart.HAND_L].bandage)


class ItemPickTests(unittest.TestCase):
    """Spec 12, `BANDAGE`: no item given."""

    def pick(self, *item_ids: str) -> str:
        gm = game_with(*item_ids)
        gm.player.body[BodyPart.HAND_L].scratch_time = 3.0
        result = ActionValidator(gm).validate(BandageAction(part_name="left hand"))
        assert isinstance(result, Accepted)
        resolved = result.resolved
        assert isinstance(resolved, FirstAidTarget) and resolved.entity is not None
        return resolved.entity.item.id

    def test_an_alcohol_bandage_comes_first(self):
        self.assertEqual(
            self.pick("item_bandage", "item_sterilized_bandage", "item_adhesive_bandage"),
            "item_sterilized_bandage",
        )

    def test_then_the_most_powerful_bandage(self):
        self.assertEqual(
            self.pick("item_adhesive_bandage", "item_bandage", "item_ripped_sheets"), "item_bandage"
        )

    def test_dirty_items_come_last(self):
        self.assertEqual(
            self.pick("item_dirty_bandage", "item_adhesive_bandage"), "item_adhesive_bandage"
        )

    def test_disinfecting_prefers_wipes_over_a_bottle(self):
        gm = game_with("item_disinfectant", "item_alcohol_wipes")
        gm.player.body[BodyPart.HAND_L].scratch_time = 3.0
        result = ActionValidator(gm).validate(DisinfectAction(part_name="left hand"))
        assert isinstance(result, Accepted)
        resolved = result.resolved
        assert isinstance(resolved, FirstAidTarget) and resolved.entity is not None
        self.assertEqual(resolved.entity.item.id, "item_alcohol_wipes")


class TreatmentResolutionTests(unittest.TestCase):
    """Spec 12, Treatment: the verbs end to end, 1 minute each."""

    def test_bandage_costs_one_minute_and_stops_the_bleeding(self):
        gm = game_with("item_bandage")
        state = gm.player.body[BodyPart.FOREARM_L]
        state.cut_time = 10.0
        state.bleeding_time = 3.0
        before = gm.narrative.minutes
        facts = simulate(gm, BandageAction(part_name="left forearm"))
        self.assertEqual(gm.narrative.minutes - before, 1)
        self.assertEqual(facts[0], "Orton bandages the left forearm.")
        self.assertTrue(state.bandaged)
        self.assertFalse(state.bleeding)

    def test_the_most_needed_part_is_bandaged_when_none_is_named(self):
        gm = game_with("item_bandage")
        gm.player.body[BodyPart.HAND_L].scratch_time = 5.0
        gm.player.body[BodyPart.NECK].bleeding_time = 5.0
        simulate(gm, BandageAction())
        self.assertTrue(gm.player.body[BodyPart.NECK].bandaged)
        self.assertFalse(gm.player.body[BodyPart.HAND_L].bandaged)

    def test_remove_bandage_costs_one_minute(self):
        gm = game_with()
        state = gm.player.body[BodyPart.HAND_L]
        state.scratch_time = 5.0
        state.bandage = "item_bandage"
        state.bandage_life = 3.0
        before = gm.narrative.minutes
        simulate(gm, RemoveBandageAction(part_name="left hand"))
        self.assertEqual(gm.narrative.minutes - before, 1)
        self.assertEqual([e.item.id for e in gm.player.inventory], ["item_bandage"])

    def test_disinfect_costs_one_minute_and_stings(self):
        gm = game_with("item_alcohol_wipes")
        gm.player.body[BodyPart.HAND_L].scratch_time = 5.0
        before = gm.narrative.minutes
        facts = simulate(gm, DisinfectAction(part_name="left hand"))
        self.assertEqual(gm.narrative.minutes - before, 1)
        self.assertEqual(facts[0], "Orton dabs disinfectant on the left hand. It stings.")

    def test_use_item_on_painkillers_takes_a_pill_in_one_minute(self):
        gm = game_with("item_painkillers")
        before = gm.narrative.minutes
        facts = simulate(gm, UseItemAction(item_name="Painkillers"))
        self.assertEqual(gm.narrative.minutes - before, 1)
        self.assertIn("Orton takes a painkiller.", facts)
        self.assertGreater(gm.player.pain_effect_minutes, 40)

    def test_use_item_on_antibiotics_sets_the_power(self):
        gm = game_with("item_antibiotics")
        simulate(gm, UseItemAction(item_name="Antibiotics"))
        self.assertGreater(gm.player.reduce_infection_power, 49)
        self.assertEqual(gm.player.inventory, [])

    def test_use_item_on_a_bandage_or_disinfectant_is_refused_with_a_hint(self):
        gm = game_with("item_bandage", "item_disinfectant")
        for name in ("Bandage", "Disinfectant"):
            result = ActionValidator(gm).validate(UseItemAction(item_name=name))
            assert isinstance(result, Rejected)
            self.assertIn("Use BANDAGE or DISINFECT.", result.reason)


if __name__ == "__main__":
    unittest.main()
