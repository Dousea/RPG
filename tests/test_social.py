"""Talking to people: TALK, GIVE and ASK (spec 10)."""

import random
import unittest

from data import social
from data.items import ITEMS
from managers.game import GameManager
from managers.simulation import SimulationCore
from managers.validator import ActionValidator, Rejected
from modules.action.parser import TALK_APPROACH_LABELS
from modules.action.types import (
    AskAction,
    Duration,
    GiveAction,
    MoveAction,
    TalkAction,
    WaitAction,
)
from modules.entity.item import ItemEntity
from tests.support import adjust_regard, load_pack, npc_of, simulate


class FixedRandom(random.Random):
    """A generator whose every roll is `value`."""

    def __init__(self, value: float):
        super().__init__(0)
        self.value = value

    def random(self) -> float:
        return self.value


def building_game() -> GameManager:
    """Orton in the building with Emma (trust 5) and Marcus (trust 3)."""
    gm = GameManager()
    gm.player.current_location_id = "zone_building"
    return gm


def affection(gm: GameManager, npc_id: str) -> int:
    return gm.relationship_manager.get_affinity(npc_id, "player")


def trust(gm: GameManager, npc_id: str) -> int:
    return gm.relationship_manager.get_trust(npc_id, "player")


def give_item(gm: GameManager, item_id: str) -> ItemEntity:
    entity = ItemEntity(item=ITEMS[item_id])
    gm.player.inventory.append(entity)
    return entity


class ApproachTableTests(unittest.TestCase):
    """Spec 10, Approaches: the table."""

    def test_the_table_is_keyed_on_the_parsers_eight_labels(self):
        self.assertEqual(set(social.TALK_APPROACHES), set(TALK_APPROACH_LABELS))
        self.assertEqual(len(TALK_APPROACH_LABELS), 8)

    def test_each_approach_applies_its_deltas_npc_to_player(self):
        table = {
            "chat": (2, 0),
            "compliment": (2, 0),
            "flirt": (3, 0),
            "confide": (1, 2),
            "comfort": (2, 1),
            "argue": (-2, -1),
            "insult": (-5, -3),
            "threaten": (-5, -8),
        }
        for approach, (d_affection, d_trust) in table.items():
            with self.subTest(approach=approach):
                gm = building_game()
                simulate(gm, TalkAction(npc_name="Emma", approach=approach))
                self.assertEqual(affection(gm, "npc_emma"), d_affection)
                self.assertEqual(trust(gm, "npc_emma"), 5 + d_trust)
                self.assertEqual(affection(gm, "player"), 0)

    def test_flirting_with_someone_not_romance_eligible_is_minus_one(self):
        gm = building_game()
        simulate(gm, TalkAction(npc_name="Marcus", approach="flirt"))
        self.assertEqual(affection(gm, "npc_marcus"), -1)
        self.assertEqual(trust(gm, "npc_marcus"), 3)

    def test_a_talk_costs_five_minutes(self):
        gm = building_game()
        facts = simulate(gm, TalkAction(npc_name="Emma", approach="chat"))
        self.assertEqual(gm.narrative.minutes, 5)
        self.assertEqual(facts[-1], "About 5 minutes pass.")


class RepetitionTests(unittest.TestCase):
    """Spec 10, Approaches: the repetition rule."""

    def test_three_chats_in_a_day_give_plus_two_one_and_nothing(self):
        gm = building_game()
        gains = []
        for _ in range(3):
            before = affection(gm, "npc_emma")
            simulate(gm, TalkAction(npc_name="Emma", approach="chat"))
            gains.append(affection(gm, "npc_emma") - before)
        self.assertEqual(gains, [2, 1, 0])

    def test_each_approach_has_its_own_count(self):
        gm = building_game()
        simulate(gm, TalkAction(npc_name="Emma", approach="chat"))
        simulate(gm, TalkAction(npc_name="Emma", approach="compliment"))
        self.assertEqual(affection(gm, "npc_emma"), 4)

    def test_the_count_is_per_npc(self):
        gm = building_game()
        simulate(gm, TalkAction(npc_name="Emma", approach="chat"))
        simulate(gm, TalkAction(npc_name="Marcus", approach="chat"))
        self.assertEqual(affection(gm, "npc_marcus"), 2)

    def test_the_count_resets_at_midnight(self):
        gm = building_game()
        simulate(gm, TalkAction(npc_name="Emma", approach="chat"))
        simulate(gm, TalkAction(npc_name="Emma", approach="chat"))
        gm.advance_clock(1440)
        before = affection(gm, "npc_emma")
        simulate(gm, TalkAction(npc_name="Emma", approach="chat"))
        self.assertEqual(affection(gm, "npc_emma") - before, 2)

    def test_the_day_is_the_calendar_day_not_the_last_24_hours(self):
        gm = building_game()
        gm.advance_clock(23 * 60 + 58 - 8 * 60)  # 23:58 on day 1
        simulate(gm, TalkAction(npc_name="Emma", approach="chat"))
        self.assertEqual(gm.narrative.day, 2)
        before = affection(gm, "npc_emma")
        simulate(gm, TalkAction(npc_name="Emma", approach="chat"))
        self.assertEqual(affection(gm, "npc_emma") - before, 2)

    def test_a_refused_talk_does_not_count(self):
        gm = building_game()
        simulate(
            gm,
            TalkAction(npc_name="Emma", approach="chat"),
            TalkAction(npc_name="Emma", approach="chat"),
        )
        before = affection(gm, "npc_emma")
        simulate(gm, TalkAction(npc_name="Emma", approach="chat"))
        self.assertEqual(affection(gm, "npc_emma") - before, 1)

    def test_negative_deltas_never_shrink(self):
        gm = building_game()
        for _ in range(3):
            simulate(gm, TalkAction(npc_name="Emma", approach="insult"))
        self.assertEqual(affection(gm, "npc_emma"), -15)
        self.assertEqual(trust(gm, "npc_emma"), 5 - 9)

    def test_positive_deltas_round_toward_zero(self):
        gm = building_game()
        for _ in range(2):
            simulate(gm, TalkAction(npc_name="Emma", approach="confide"))
        self.assertEqual(affection(gm, "npc_emma"), 1)
        self.assertEqual(trust(gm, "npc_emma"), 5 + 2 + 1)


class HostileTests(unittest.TestCase):
    """Spec 10, Approaches: hostile NPCs."""

    def test_a_hostile_npc_halves_positive_deltas_toward_zero(self):
        gm = building_game()
        adjust_regard(gm, "npc_emma", affection=-50)
        simulate(gm, TalkAction(npc_name="Emma", approach="confide"))
        self.assertEqual(affection(gm, "npc_emma"), -50)
        self.assertEqual(trust(gm, "npc_emma"), 5 + 1)

    def test_a_hated_npc_halves_them_too(self):
        gm = building_game()
        adjust_regard(gm, "npc_emma", affection=-80)
        simulate(gm, TalkAction(npc_name="Emma", approach="comfort"))
        self.assertEqual(affection(gm, "npc_emma"), -79)
        self.assertEqual(trust(gm, "npc_emma"), 5 + 0)

    def test_the_halving_comes_after_the_repetition_divisor(self):
        gm = building_game()
        adjust_regard(gm, "npc_emma", affection=-50)
        simulate(gm, TalkAction(npc_name="Emma", approach="chat"))
        simulate(gm, TalkAction(npc_name="Emma", approach="chat"))
        self.assertEqual(affection(gm, "npc_emma"), -50 + 1 + 0)

    def test_negative_deltas_are_not_halved(self):
        gm = building_game()
        adjust_regard(gm, "npc_emma", affection=-50)
        simulate(gm, TalkAction(npc_name="Emma", approach="insult"))
        self.assertEqual(affection(gm, "npc_emma"), -55)

    def test_a_guarded_trust_band_is_not_a_hostile_disposition(self):
        gm = building_game()
        adjust_regard(gm, "npc_emma", trust=-10)
        simulate(gm, TalkAction(npc_name="Emma", approach="chat"))
        self.assertEqual(affection(gm, "npc_emma"), 2)


class TalkFactsTests(unittest.TestCase):
    """Spec 10, Approaches: the facts."""

    def test_the_fact_names_the_reaction_from_the_sign_of_the_change(self):
        cases = (
            ("compliment", "Emma responds warmly."),
            ("argue", "Emma bristles."),
        )
        for approach, expected in cases:
            with self.subTest(approach=approach):
                gm = building_game()
                facts = simulate(gm, TalkAction(npc_name="Emma", approach=approach))
                self.assertIn(expected, facts)

    def test_a_repeat_with_nothing_gained_seems_unmoved(self):
        gm = building_game()
        facts: list[str] = []
        for _ in range(3):
            facts = simulate(gm, TalkAction(npc_name="Emma", approach="chat"))
        self.assertIn("Emma seems unmoved.", facts)

    def test_a_disposition_change_produces_exactly_one_fact(self):
        gm = building_game()
        adjust_regard(gm, "npc_emma", affection=38)
        facts = simulate(gm, TalkAction(npc_name="Emma", approach="chat"))
        self.assertEqual(facts.count("Emma now regards Orton as friendly."), 1)
        again = simulate(gm, TalkAction(npc_name="Emma", approach="chat"))
        self.assertFalse(any("now regards" in fact for fact in again))

    def test_a_trust_band_change_produces_exactly_one_fact(self):
        gm = building_game()
        adjust_regard(gm, "npc_marcus", trust=5)
        facts = simulate(gm, TalkAction(npc_name="Marcus", approach="confide"))
        self.assertEqual(facts.count("Marcus's trust in Orton is now tentative."), 1)

    def test_no_fact_carries_a_score(self):
        gm = building_game()
        facts = simulate(gm, TalkAction(npc_name="Emma", approach="confide"))
        for fact in facts:
            self.assertFalse(any(ch.isdigit() for ch in fact.replace("5 minutes", "")), fact)


class TalkValidationTests(unittest.TestCase):
    """Spec 10, Approaches and Edge cases."""

    def test_a_second_talk_to_the_same_npc_in_one_turn_is_refused(self):
        gm = building_game()
        facts = simulate(
            gm,
            TalkAction(npc_name="Emma", approach="chat"),
            TalkAction(npc_name="Emma", approach="compliment"),
        )
        self.assertIn(
            "Refused: Orton can't talk: Orton has already spoken to Emma this turn.", facts
        )

    def test_two_different_npcs_in_one_turn_share_one_five_minutes(self):
        gm = building_game()
        simulate(
            gm,
            TalkAction(npc_name="Emma", approach="chat"),
            TalkAction(npc_name="Marcus", approach="chat"),
        )
        self.assertEqual(gm.narrative.minutes, 5)

    def test_talking_to_a_zombie_is_refused(self):
        gm = building_game()
        result = ActionValidator(gm).validate(TalkAction(npc_name="z3", approach="chat"))
        assert isinstance(result, Rejected)
        self.assertEqual(result.reason, "z3 isn't listening.")

    def test_talking_to_someone_absent_is_refused(self):
        gm = building_game()
        result = ActionValidator(gm).validate(TalkAction(npc_name="Jen", approach="chat"))
        assert isinstance(result, Rejected)
        self.assertEqual(result.reason, "Jen isn't here.")

    def test_a_refused_turn_costs_nothing(self):
        gm = building_game()
        simulate(gm, TalkAction(npc_name="Jen", approach="chat"))
        self.assertEqual(gm.narrative.minutes, 0)

    def test_an_unknown_approach_is_refused(self):
        gm = building_game()
        result = ActionValidator(gm).validate(TalkAction(npc_name="Emma", approach="gossip"))
        self.assertIsInstance(result, Rejected)


class TalkingMinutesTests(unittest.TestCase):
    """Spec 10, Verbs: talking minutes feed the stats."""

    def talking_flags(self, action) -> list[bool]:
        gm = building_game()
        give_item(gm, "item_canned_beans")
        core = SimulationCore(gm, rng=random.Random(1))
        seen: list[bool] = []

        class Spy:
            def apply(self, stats, hours, ctx):  # noqa: ANN001
                seen.append(ctx.talking)

        core.stats_engine.register(Spy())
        core.resolve([action])
        return seen

    def test_talk_ask_and_give_run_the_stats_as_talking(self):
        for action in (
            TalkAction(npc_name="Emma", approach="chat"),
            AskAction(npc_name="Emma", request="stay"),
            GiveAction(item_name="Canned Beans", npc_name="Emma"),
        ):
            with self.subTest(action=type(action).__name__):
                seen = self.talking_flags(action)
                self.assertTrue(seen and all(seen))

    def test_a_wait_is_not_talking(self):
        seen = self.talking_flags(WaitAction(duration=Duration(minutes=5)))
        self.assertFalse(any(seen))


class GiveTests(unittest.TestCase):
    """Spec 10, Giving."""

    def test_give_moves_the_item_into_the_npcs_inventory(self):
        gm = building_game()
        give_item(gm, "item_crowbar")
        simulate(gm, GiveAction(item_name="Crowbar", npc_name="Emma"))
        self.assertNotIn("Crowbar", [e.item.name for e in gm.player.inventory])
        self.assertEqual([e.item.name for e in npc_of(gm, "Emma").inventory], ["Crowbar"])

    def test_food_is_worth_four_affection_and_three_trust(self):
        gm = building_game()
        give_item(gm, "item_canned_beans")
        simulate(gm, GiveAction(item_name="Canned Beans", npc_name="Emma"))
        self.assertEqual(affection(gm, "npc_emma"), 4)
        self.assertEqual(trust(gm, "npc_emma"), 5 + 3)

    def test_anything_else_is_worth_two_and_two(self):
        gm = building_game()
        give_item(gm, "item_crowbar")
        simulate(gm, GiveAction(item_name="Crowbar", npc_name="Emma"))
        self.assertEqual(affection(gm, "npc_emma"), 2)
        self.assertEqual(trust(gm, "npc_emma"), 5 + 2)

    def test_gives_count_as_one_key_whatever_the_item(self):
        gm = building_game()
        give_item(gm, "item_canned_beans")
        give_item(gm, "item_crowbar")
        simulate(gm, GiveAction(item_name="Canned Beans", npc_name="Emma"))
        simulate(gm, GiveAction(item_name="Crowbar", npc_name="Emma"))
        self.assertEqual(affection(gm, "npc_emma"), 4 + 1)
        self.assertEqual(trust(gm, "npc_emma"), 5 + 3 + 1)

    def test_a_give_does_not_count_as_a_chat(self):
        gm = building_game()
        give_item(gm, "item_crowbar")
        simulate(gm, GiveAction(item_name="Crowbar", npc_name="Emma"))
        before = affection(gm, "npc_emma")
        simulate(gm, TalkAction(npc_name="Emma", approach="chat"))
        self.assertEqual(affection(gm, "npc_emma") - before, 2)

    def test_a_door_key_is_refused(self):
        gm = building_game()
        facts = simulate(gm, GiveAction(item_name="Apartment Key", npc_name="Emma"))
        self.assertIn("Refused: Orton can't give: Orton keeps his keys on him.", facts)
        self.assertEqual([e.item.name for e in gm.player.inventory], ["Apartment Key"])

    def test_an_item_not_carried_is_refused(self):
        gm = building_game()
        result = ActionValidator(gm).validate(GiveAction(item_name="Crowbar", npc_name="Emma"))
        self.assertIsInstance(result, Rejected)

    def test_giving_to_someone_absent_is_refused(self):
        gm = building_game()
        give_item(gm, "item_crowbar")
        result = ActionValidator(gm).validate(GiveAction(item_name="Crowbar", npc_name="Jen"))
        self.assertIsInstance(result, Rejected)

    def test_a_give_shares_the_turns_five_minutes_with_a_talk(self):
        gm = building_game()
        give_item(gm, "item_crowbar")
        simulate(
            gm,
            TalkAction(npc_name="Emma", approach="chat"),
            GiveAction(item_name="Crowbar", npc_name="Emma"),
        )
        self.assertEqual(gm.narrative.minutes, 5)

    def test_a_give_to_a_hostile_npc_is_halved(self):
        gm = building_game()
        adjust_regard(gm, "npc_emma", affection=-50)
        give_item(gm, "item_canned_beans")
        simulate(gm, GiveAction(item_name="Canned Beans", npc_name="Emma"))
        self.assertEqual(affection(gm, "npc_emma"), -50 + 2)
        self.assertEqual(trust(gm, "npc_emma"), 5 + 1)


class AskFollowTests(unittest.TestCase):
    """Spec 10, Asking."""

    def ask_follow(self, gm: GameManager, roll: float) -> list[str]:
        return simulate(gm, AskAction(npc_name="Emma", request="follow"), rng=FixedRandom(roll))

    def test_at_trust_twenty_the_chance_is_half(self):
        gm = building_game()
        adjust_regard(gm, "npc_emma", trust=15)
        self.ask_follow(gm, 0.49)
        self.assertTrue(npc_of(gm, "Emma").following)

    def test_a_roll_equal_to_the_chance_refuses(self):
        gm = building_game()
        adjust_regard(gm, "npc_emma", trust=15)
        facts = self.ask_follow(gm, 0.5)
        self.assertFalse(npc_of(gm, "Emma").following)
        self.assertIn("Emma refuses to follow Orton.", facts)

    def test_solid_trust_always_complies(self):
        gm = building_game()
        adjust_regard(gm, "npc_emma", trust=35)
        facts = self.ask_follow(gm, 0.999)
        self.assertTrue(npc_of(gm, "Emma").following)
        self.assertIn("Emma agrees to follow Orton.", facts)

    def test_zero_trust_never_complies(self):
        gm = building_game()
        adjust_regard(gm, "npc_emma", trust=-5)
        self.ask_follow(gm, 0.0)
        self.assertFalse(npc_of(gm, "Emma").following)

    def test_the_chance_is_trust_over_forty(self):
        gm = building_game()
        self.ask_follow(gm, 0.124)
        self.assertTrue(npc_of(gm, "Emma").following)
        gm2 = building_game()
        self.ask_follow(gm2, 0.126)
        self.assertFalse(npc_of(gm2, "Emma").following)

    def test_a_hostile_npc_always_refuses(self):
        gm = building_game()
        adjust_regard(gm, "npc_emma", affection=-50, trust=50)
        self.ask_follow(gm, 0.0)
        self.assertFalse(npc_of(gm, "Emma").following)

    def test_a_follower_asked_again_complies_with_no_roll(self):
        gm = building_game()
        npc_of(gm, "Emma").following = True

        class NoRolls(random.Random):
            def random(self) -> float:
                raise AssertionError("no roll expected")

        facts = simulate(gm, AskAction(npc_name="Emma", request="follow"), rng=NoRolls(0))
        self.assertTrue(npc_of(gm, "Emma").following)
        self.assertIn("Emma agrees to follow Orton.", facts)

    def test_a_refusal_cannot_be_asked_again_for_sixty_minutes(self):
        gm = building_game()
        self.ask_follow(gm, 0.99)
        validator = ActionValidator(gm)
        action = AskAction(npc_name="Emma", request="follow")
        gm.advance_clock(54)
        result = validator.validate(action)
        assert isinstance(result, Rejected)
        self.assertEqual(result.reason, "Emma has already said no.")
        gm.advance_clock(1)
        self.assertEqual(gm.narrative.minutes, 60)
        self.assertNotIsInstance(validator.validate(action), Rejected)

    def test_the_lockout_is_per_npc_and_per_request(self):
        gm = building_game()
        self.ask_follow(gm, 0.99)
        validator = ActionValidator(gm)
        self.assertNotIsInstance(
            validator.validate(AskAction(npc_name="Marcus", request="follow")), Rejected
        )
        self.assertNotIsInstance(
            validator.validate(AskAction(npc_name="Emma", request="stay")), Rejected
        )

    def test_a_success_sets_no_lockout(self):
        gm = building_game()
        adjust_regard(gm, "npc_emma", trust=35)
        self.ask_follow(gm, 0.0)
        npc_of(gm, "Emma").following = False
        result = ActionValidator(gm).validate(AskAction(npc_name="Emma", request="follow"))
        self.assertNotIsInstance(result, Rejected)

    def test_stay_always_works_and_stops_the_following(self):
        gm = building_game()
        npc_of(gm, "Emma").following = True
        facts = simulate(gm, AskAction(npc_name="Emma", request="stay"), rng=FixedRandom(0.99))
        self.assertFalse(npc_of(gm, "Emma").following)
        self.assertIn("Emma stops following Orton.", facts)

    def test_asking_someone_absent_is_refused(self):
        gm = building_game()
        result = ActionValidator(gm).validate(AskAction(npc_name="Jen", request="follow"))
        self.assertIsInstance(result, Rejected)

    def test_a_request_costs_five_minutes_and_changes_no_score(self):
        gm = building_game()
        self.ask_follow(gm, 0.99)
        self.assertEqual(gm.narrative.minutes, 5)
        self.assertEqual(affection(gm, "npc_emma"), 0)
        self.assertEqual(trust(gm, "npc_emma"), 5)


class AskGiveTests(unittest.TestCase):
    """Spec 10, Asking: give."""

    def setUp(self):
        self.gm = building_game()
        self.emma = npc_of(self.gm, "Emma")
        self.emma.inventory.append(ItemEntity(item=ITEMS["item_water_bottle"]))

    def ask(self, roll: float, item: str = "Water Bottle") -> list[str]:
        return simulate(
            self.gm,
            AskAction(npc_name="Emma", request="give", argument=item),
            rng=FixedRandom(roll),
        )

    def test_the_item_moves_to_the_player_when_the_roll_passes(self):
        adjust_regard(self.gm, "npc_emma", trust=25)  # trust 30: chance 0.5
        facts = self.ask(0.49)
        self.assertEqual(self.emma.inventory, [])
        self.assertIn("Water Bottle", [e.item.name for e in self.gm.player.inventory])
        self.assertIn("Emma hands Orton the Water Bottle.", facts)

    def test_the_chance_is_trust_minus_ten_over_forty(self):
        adjust_regard(self.gm, "npc_emma", trust=25)
        self.ask(0.5)
        self.assertEqual(len(self.emma.inventory), 1)

    def test_a_refusal_keeps_the_item_and_locks_the_request_out(self):
        facts = self.ask(0.99)
        self.assertEqual(len(self.emma.inventory), 1)
        self.assertIn("Emma won't hand over the Water Bottle.", facts)
        result = ActionValidator(self.gm).validate(
            AskAction(npc_name="Emma", request="give", argument="Water Bottle")
        )
        assert isinstance(result, Rejected)
        self.assertEqual(result.reason, "Emma has already said no.")

    def test_trust_ten_or_less_never_complies(self):
        adjust_regard(self.gm, "npc_emma", trust=5)  # trust 10
        self.ask(0.0)
        self.assertEqual(len(self.emma.inventory), 1)

    def test_an_item_the_npc_lacks_is_refused(self):
        result = ActionValidator(self.gm).validate(
            AskAction(npc_name="Emma", request="give", argument="Crowbar")
        )
        assert isinstance(result, Rejected)
        self.assertEqual(result.reason, "Emma has no Crowbar to give.")

    def test_a_give_then_ask_give_moves_it_back(self):
        adjust_regard(self.gm, "npc_emma", trust=45)
        give_item(self.gm, "item_crowbar")
        simulate(self.gm, GiveAction(item_name="Crowbar", npc_name="Emma"))
        self.assertIn("Crowbar", [e.item.name for e in self.emma.inventory])
        simulate(
            self.gm,
            AskAction(npc_name="Emma", request="give", argument="Crowbar"),
            rng=FixedRandom(0.0),
        )
        self.assertIn("Crowbar", [e.item.name for e in self.gm.player.inventory])

    def test_a_full_inventory_is_refused(self):
        adjust_regard(self.gm, "npc_emma", trust=45)
        load_pack(self.gm.player, 49.9)
        result = ActionValidator(self.gm).validate(
            AskAction(npc_name="Emma", request="give", argument="Water Bottle")
        )
        self.assertIsInstance(result, Rejected)


class FollowerTests(unittest.TestCase):
    """Spec 10, Asking: following."""

    def test_a_follower_arrives_with_the_player_at_the_same_minute(self):
        gm = building_game()
        npc_of(gm, "Emma").following = True
        simulate(gm, MoveAction(destination="out"))
        self.assertEqual(gm.player.current_location_id, "zone_street")
        self.assertEqual(npc_of(gm, "Emma").current_location_id, "zone_street")

    def test_a_follower_enters_the_apartment_with_the_player(self):
        gm = building_game()
        npc_of(gm, "Emma").following = True
        simulate(gm, MoveAction(destination="Your Apartment"))
        self.assertEqual(gm.player.current_location_id, "zone_home")
        self.assertEqual(npc_of(gm, "Emma").current_location_id, "zone_home")

    def test_one_who_is_not_following_stays_behind(self):
        gm = building_game()
        npc_of(gm, "Emma").following = True
        simulate(gm, MoveAction(destination="out"))
        self.assertEqual(npc_of(gm, "Marcus").current_location_id, "zone_building")

    def test_a_follower_covers_every_hop_of_a_long_walk(self):
        gm = building_game()
        npc_of(gm, "Emma").following = True
        simulate(gm, MoveAction(destination="The Neighborhood"))
        self.assertEqual(npc_of(gm, "Emma").current_location_id, gm.player.current_location_id)

    def test_a_follower_left_in_another_zone_does_not_teleport(self):
        gm = building_game()
        emma = npc_of(gm, "Emma")
        emma.following = True
        emma.current_location_id = "zone_street"
        simulate(gm, MoveAction(destination="Your Apartment"))
        self.assertEqual(emma.current_location_id, "zone_street")

    def test_move_npc_sets_the_zone(self):
        gm = building_game()
        gm.move_npc(npc_of(gm, "Emma"), gm.world.locations["zone_street"])
        self.assertEqual(npc_of(gm, "Emma").current_location_id, "zone_street")
