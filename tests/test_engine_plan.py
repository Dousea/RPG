"""llm-contract: The plan screen: unclear targets are settled before a plan runs, and a plan that meets one mid-run pauses."""

import json
import re
from pathlib import Path
from typing import cast
from unittest import mock

from adapters.save import files
from data.items import ITEMS
from data.story.mentions import DECIDED_ON_ARRIVAL
from managers.game import GameManager
from managers.validator import Accepted, ActionValidator, Rejected
from modules.action.pins import MENTION_MARK, pin_of
from modules.action.types import AnyAction, AttackAction, MoveAction
from modules.entity.item import ItemEntity
from modules.entity.zombie import ZombieState
from modules.resolution import TargetContainer, TargetCorpse, TargetZombie
from tests.support import FakeFactChecker
from tests.test_engine import EngineTestCase
from tests.test_plan import two_bodies
from tests.test_simulation import add_zombie, zombie_game

STORY = "STORY:\nIt happens.\n\nEVENT:\nSomething happened\n\nOPTIONS:\nNONE"
BAT = ITEMS["item_baseball_bat"]


def iter_strings(value):
    """Every string in a payload of dicts, lists and scalars."""
    if isinstance(value, str):
        yield value
    elif isinstance(value, dict):
        for each in value.values():
            yield from iter_strings(each)
    elif isinstance(value, list):
        for each in value:
            yield from iter_strings(each)


class PlanScreenTestCase(EngineTestCase):
    def setUp(self):
        super().setUp()
        self.llm.story = STORY

    def stage(self, zone: str) -> GameManager:
        gm = zombie_game(zone)
        self.engine.manager = gm
        return gm

    def script(self, *replies: str) -> None:
        self.llm.parser_script = [f"ACTIONS:\n{reply}" for reply in replies]

    def accepted(self) -> list[Accepted]:
        seen: list[Accepted] = []
        real = ActionValidator.validate

        def spy(validator: ActionValidator, action: AnyAction):
            result = real(validator, action)
            if isinstance(result, Accepted):
                seen.append(result)
            return result

        patch = mock.patch.object(ActionValidator, "validate", spy)
        patch.start()
        self.addCleanup(patch.stop)
        return seen

    def two_bats(self, gm: GameManager) -> None:
        gm.current_location.entities.extend(
            [ItemEntity(item=BAT, condition=0), ItemEntity(item=BAT)]
        )

    def choices(self, plan: dict, number: int = 0) -> list[str]:
        return [c["id"] for c in plan["choices"][number]["candidates"]]

    def candidate(self, plan: dict, word: str, number: int = 0) -> str:
        """The id of the candidate whose description has `word`."""
        (found,) = [
            c["id"] for c in plan["choices"][number]["candidates"] if word in c["description"]
        ]
        return found

    def assert_nothing_ran(self, gm: GameManager, minutes: int, result: dict) -> None:
        self.assertEqual(gm.narrative.minutes, minutes)
        self.assertEqual(self.llm.narrator_prompts, [])
        self.assertEqual(result["story_text"], "")


class AskBeforeRunningTests(PlanScreenTestCase):
    def test_an_unclear_zone_runs_nothing_and_leaves_the_later_target_to_arrival(self):
        gm = self.stage("zone_home")
        add_zombie(gm, gap=3, state=ZombieState.CHASING)
        minutes = gm.narrative.minutes
        self.script("MOVE_TO the apartment\nATTACK zombie")
        result = self.engine.play("run to the apartment and hit the zombie")
        self.assert_nothing_ran(gm, minutes, result)
        plan = result["plan"]
        self.assertEqual(
            self.choices(plan),
            ["zone_home", "zone_building", "zone_flat_vacant", "zone_flat_tenant"],
        )
        move, attack = plan["steps"]
        self.assertEqual(move["choice"], 0)
        self.assertIsNone(attack["choice"])
        self.assertIsNone(attack["default"])
        self.assertIn(DECIDED_ON_ARRIVAL, attack["text"])
        words = [v for v in iter_strings(plan)]
        self.assertTrue(words)
        self.assertFalse([w for w in words if re.search(r"\d", w)])

    def test_go_runs_the_kept_plan_with_one_narrator_call_and_no_parser_call(self):
        gm = self.stage("zone_home")
        add_zombie(gm, gap=3, state=ZombieState.CHASING)
        self.script("MOVE_TO the apartment\nATTACK zombie")
        seen = self.accepted()
        self.engine.play("run to the apartment and hit the zombie")
        result = self.engine.go(["zone_home"])
        self.assertEqual(len(self.llm.prompts), 1)
        self.assertEqual(len(self.llm.narrator_prompts), 1)
        self.assertIsNone(result["plan"])
        self.assertTrue(any(isinstance(a.action, MoveAction) for a in seen))
        self.assertTrue(any(isinstance(a.resolved, TargetZombie) for a in seen))

    def test_an_unclear_item_is_picked_and_the_plan_heads_out_with_it(self):
        gm = self.stage("zone_street")
        self.two_bats(gm)
        self.script("TAKE Baseball Bat\nMOVE_TO out")
        result = self.engine.play("grab the bat and head out")
        self.assertEqual(len(self.choices(result["plan"])), 2)
        self.assertEqual(gm.player.current_location_id, "zone_street")
        self.engine.go([self.candidate(result["plan"], "broken")])
        self.assertEqual(gm.player.current_location_id, "zone_neighborhood")
        carried = [e for e in gm.player.inventory if e.item.id == BAT.id]
        self.assertEqual([e.broken for e in carried], [True])

    def test_two_packs_differing_in_uses_ask_and_go_drops_the_chosen_one(self):
        gm = self.stage("zone_street")
        wipes = ITEMS["item_alcohol_wipes"]
        few, many = ItemEntity(item=wipes, uses=3), ItemEntity(item=wipes, uses=5)
        gm.player.inventory.extend([few, many])
        self.script("DROP the alcohol wipes")
        result = self.engine.play("drop the alcohol wipes")
        self.assertEqual(len(self.choices(result["plan"])), 2)
        self.assertIn(few, gm.player.inventory)
        self.engine.go([self.candidate(result["plan"], "5 left")])
        self.assertIn(few, gm.player.inventory)
        self.assertNotIn(many, gm.player.inventory)

    def test_two_open_choices_share_one_screen_and_one_go_settles_both(self):
        gm = self.stage("zone_street")
        self.two_bats(gm)
        self.script("TAKE Baseball Bat\nMOVE_TO the store")
        result = self.engine.play("grab the bat and go to the store")
        self.assertEqual(len(result["plan"]["choices"]), 2)
        self.assertEqual([s["choice"] for s in result["plan"]["steps"]], [0, 1])
        self.engine.go([self.candidate(result["plan"], "good"), "zone_bodega"])
        self.assertEqual(gm.player.current_location_id, "zone_bodega")
        self.assertFalse([e for e in gm.player.inventory if e.item.id == BAT.id and e.broken])

    def test_a_zone_the_parser_picked_for_a_kind_word_asks_and_go_moves_to_the_pick(self):
        gm = self.stage("zone_building")
        self.script("MOVE_TO Your Apartment")
        minutes = gm.narrative.minutes
        result = self.engine.play("go to the apartment")
        self.assertEqual(
            set(self.choices(result["plan"])),
            {"zone_home", "zone_building", "zone_flat_vacant", "zone_flat_tenant"},
        )
        self.assert_nothing_ran(gm, minutes, result)
        self.engine.go(["zone_flat_vacant"])
        self.assertEqual(gm.player.current_location_id, "zone_flat_vacant")

        gm = self.stage("zone_home")
        self.script("MOVE_TO The Corner Store")
        result = self.engine.play("go to the store")
        self.assertEqual(len(self.choices(result["plan"])), 4)
        self.assertEqual(gm.player.current_location_id, "zone_home")

    def test_words_that_name_the_zone_move_without_a_question(self):
        for text, reply, start, end in (
            ("go to my apartment", "Your Apartment", "zone_building", "zone_home"),
            ("go to the supermarket", "The Supermarket", "zone_neighborhood", "zone_supermarket"),
            ("go to the stockroom", "The Corner Store", "zone_street", "zone_bodega"),
        ):
            with self.subTest(text):
                gm = self.stage(start)
                self.script(f"MOVE_TO {reply}")
                result = self.engine.play(text)
                self.assertIsNone(result["plan"])
                self.assertEqual(gm.player.current_location_id, end)

    def test_an_unclear_container_is_picked_and_searched(self):
        gm = self.stage("zone_home")
        gm.player.current_room = None
        seen = self.accepted()
        self.script("SEARCH counter")
        result = self.engine.play("search the counter")
        self.assertEqual(self.choices(result["plan"]), ["kitchen_counter", "bathroom_counter"])
        self.engine.go(["bathroom_counter"])
        (search,) = [a for a in seen if isinstance(a.resolved, TargetContainer)]
        self.assertEqual(search.expect(TargetContainer).container.container_id, "bathroom_counter")

    def test_two_bodies_ask_which_one_and_go_searches_the_pick(self):
        gm = two_bodies("item_jacket_police", "item_jeans")
        self.engine.manager = gm
        seen = self.accepted()
        for reply in ("SEARCH corpse", "SEARCH c1"):
            with self.subTest(reply):
                gm.world.corpses["c2"].searched = False
                self.llm.narrator_prompts.clear()
                self.script(reply)
                minutes = gm.narrative.minutes
                result = self.engine.play("search the body")
                self.assertEqual(self.choices(result["plan"]), ["c1", "c2"])
                self.assert_nothing_ran(gm, minutes, result)
                self.engine.go(["c2"])
                self.assertEqual(seen[-1].expect(TargetCorpse).corpse_id, "c2")
                self.assertTrue(gm.world.corpses["c2"].searched)
                self.assertFalse(gm.world.corpses["c1"].searched)

    def test_words_naming_one_body_or_one_body_ask_nothing(self):
        gm = two_bodies("item_jacket_police", "item_jeans")
        self.engine.manager = gm
        self.script("SEARCH c2")
        result = self.engine.play("search the man in jeans")
        self.assertIsNone(result["plan"])
        self.assertTrue(gm.world.corpses["c2"].searched)

        gm = two_bodies("item_jeans")
        self.engine.manager = gm
        self.script("SEARCH corpse")
        self.assertIsNone(self.engine.play("search the body")["plan"])

    def test_two_zombies_still_default_to_the_nearest_without_asking(self):
        gm = self.stage("zone_street")
        add_zombie(gm, gap=3, state=ZombieState.CHASING)
        add_zombie(gm, gap=9)
        self.script("ATTACK zombie")
        self.assertIsNone(self.engine.play("hit the zombie")["plan"])

    def test_a_clear_plan_runs_as_before(self):
        self.stage("zone_street")
        self.script("MOVE_TO out")
        result = self.engine.play("head out")
        self.assertIsNone(result["plan"])
        self.assertEqual(len(self.llm.narrator_prompts), 1)

    def test_the_screen_is_never_saved(self):
        gm = self.stage("zone_home")
        files.save(gm)
        saved = Path(self.save_path).read_text()
        self.script("MOVE_TO the apartment")
        self.engine.play("go to the apartment")
        self.assertTrue(self.engine.has_plan)
        self.assertEqual(Path(self.save_path).read_text(), saved)
        self.assertNotIn("plan", json.loads(saved))

    def test_a_dropped_off_request_action_still_reaches_the_narrator_after_go(self):
        self.stage("zone_home")
        cast(FakeFactChecker, self.engine.factcheck).plan_results = [[1]]
        self.script("MOVE_TO the apartment\nSHOUT")
        self.engine.play("go to the apartment")
        self.engine.go(["zone_home"])
        self.assertIn("Refused:", self.llm.narrator_prompts[0])


class DroppingThePlanTests(PlanScreenTestCase):
    def kept(self) -> tuple[GameManager, int]:
        gm = self.stage("zone_home")
        self.script("MOVE_TO the apartment")
        self.engine.play("go to the apartment")
        return gm, gm.narrative.minutes

    def test_a_typed_turn_drops_the_plan(self):
        gm, _ = self.kept()
        self.script("ADD_GOAL short_term Find water")
        self.engine.play("think about water")
        self.assertFalse(self.engine.has_plan)
        narrators = len(self.llm.narrator_prompts)
        minutes = gm.narrative.minutes
        result = self.engine.go(["zone_home"])
        self.assertEqual(
            (len(self.llm.narrator_prompts), gm.narrative.minutes), (narrators, minutes)
        )
        self.assertTrue(result["story_text"])

    def test_cancel_drops_the_plan(self):
        gm, minutes = self.kept()
        result = self.engine.cancel_plan()
        self.assertIsNone(result["plan"])
        self.engine.go(["zone_home"])
        self.assertEqual(gm.narrative.minutes, minutes)
        self.assertEqual(self.llm.narrator_prompts, [])

    def test_a_choice_that_is_not_offered_is_refused_with_no_time_spent(self):
        gm, minutes = self.kept()
        for answer in (["zone_street"], [], ["zone_home", "zone_home"]):
            with self.subTest(answer):
                result = self.engine.go(answer)
                self.assertTrue(result["story_text"])
                self.assertIsNone(result["plan"])
                self.assertEqual(gm.narrative.minutes, minutes)
                self.script("MOVE_TO the apartment")
                self.engine.play("go to the apartment")
        self.assertEqual(self.llm.narrator_prompts, [])


class PausedPlanTests(PlanScreenTestCase):
    def pause(self) -> tuple[GameManager, dict]:
        gm = self.stage("zone_street")
        gm.player.inventory.append(ItemEntity(item=BAT, condition=0))
        gm.current_location.entities.append(ItemEntity(item=BAT))
        self.script("DROP broken Baseball Bat\nTAKE Baseball Bat\nADD_GOAL short_term Find water")
        return gm, self.engine.play("swap bats and plan")

    def test_a_question_that_appears_mid_run_pauses_with_the_done_steps_ticked(self):
        gm, result = self.pause()
        self.assertEqual(len(self.llm.narrator_prompts), 1)
        self.assertIn("hasn't yet", self.llm.narrator_prompts[0])
        self.assertEqual(gm.narrative.goals["short_term"], [])
        steps = result["plan"]["steps"]
        self.assertEqual([s["done"] for s in steps], [True, False, False])
        self.assertEqual([s["choice"] for s in steps], [None, 0, None])
        self.assertEqual(len(set(self.choices(result["plan"]))), 2)

    def test_go_resumes_without_running_the_done_steps_again(self):
        gm, paused = self.pause()
        result = self.engine.go([self.candidate(paused["plan"], "good")])
        self.assertEqual(len(self.llm.prompts), 1)
        self.assertEqual(len(self.llm.narrator_prompts), 2)
        self.assertNotIn("Refused:", self.llm.narrator_prompts[1])
        self.assertEqual(gm.narrative.goals["short_term"], ["Find water"])
        carried = [e for e in gm.player.inventory if e.item.id == BAT.id]
        self.assertEqual([e.broken for e in carried], [False])
        self.assertIsNone(result["plan"])

    def test_a_question_in_the_part_parsed_again_after_a_zone_change_pauses_too(self):
        gm = self.stage("zone_street")
        gm.world.locations["zone_neighborhood"].entities.extend(
            [ItemEntity(item=BAT, condition=0), ItemEntity(item=BAT)]
        )
        self.script("MOVE_TO out\nTAKE Baseball Bat", "TAKE Baseball Bat")
        result = self.engine.play("go out and take the bat")
        self.assertEqual(len(self.llm.prompts), 2)
        self.assertEqual(gm.player.current_location_id, "zone_neighborhood")
        steps = result["plan"]["steps"]
        self.assertEqual([(s["done"], s["choice"]) for s in steps], [(True, None), (False, 0)])


class SpentPickTests(PlanScreenTestCase):
    def test_a_dropped_action_spends_its_pick_for_the_part_parsed_again(self):
        gm = self.stage("zone_neighborhood")
        zombie = add_zombie(gm, gap=3, state=ZombieState.CHASING)
        cast(FakeFactChecker, self.engine.factcheck).plan_results = [[0]]
        self.script(
            "ATTACK zombie\nMOVE_TO Supermarket\nSHOUT",
            "ATTACK zombie",
        )
        checked: list[Accepted | Rejected] = []
        real = ActionValidator.validate

        def spy(validator: ActionValidator, action: AnyAction):
            result = real(validator, action)
            checked.append(result)
            return result

        with mock.patch.object(ActionValidator, "validate", spy):
            self.engine.play(f"hit {MENTION_MARK} then go on", mentions=[zombie.zombie_id])
        later = [r.action for r in checked if isinstance(r.action, AttackAction)]
        self.assertTrue(later)
        self.assertTrue(all(pin_of(a.target_name) is None for a in later))
