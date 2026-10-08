"""llm-contract: Mentions in a turn: checked before the parser, bound after it, never shown to the narrator."""

import json
import re
from unittest import mock

from data.items import ITEMS
from managers.combat import weapons
from managers.game import GameManager
from managers.simulation import SimulationCore
from managers.validator import Accepted, ActionValidator, Rejected
from managers.world import item_ids
from modules.action.pins import MENTION_MARK, pin_of
from modules.action.types import AnyAction, AttackAction, BandageAction, MoveAction
from modules.body.parts import BodyPart
from modules.entity.item import ItemEntity
from modules.entity.zombie import ZombieState
from modules.resolution import TargetBarrier, TargetContainer, TargetZombie
from tests.test_engine import EngineTestCase
from tests.test_simulation import add_zombie, zombie_game

STORY = "STORY:\nIt happens.\n\nEVENT:\nSomething happened\n\nOPTIONS:\nNONE"
ZOMBIE_ID = re.compile(r"\bz\d+\b")
ITEM_ID = re.compile(r"\bi\d+\b")


class MentionTurnTests(EngineTestCase):
    def setUp(self):
        super().setUp()
        self.llm.story = STORY

    def stage(self, zone: str = "zone_street") -> GameManager:
        gm = zombie_game(zone)
        self.engine.manager = gm
        return gm

    def script(self, actions: str) -> None:
        self.llm.actions = f"ACTIONS:\n{actions}"

    def accepted(self) -> list[Accepted]:
        """Every action the validator accepted while `with` is open."""
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

    def refusing(self, zone_id: str):
        """A validator `validate` that refuses a move pinned to `zone_id` and rules normally on the rest."""
        real = ActionValidator.validate

        def validate(validator: ActionValidator, action: AnyAction):
            pin = pin_of(action.destination) if isinstance(action, MoveAction) else None
            if pin is not None and pin.entity_id == zone_id:
                return Rejected(action, "the way is blocked")
            return real(validator, action)

        return validate

    def checked(self) -> list[Accepted | Rejected]:
        """Every action the validator ruled on while the test runs, accepted or not."""
        seen: list[Accepted | Rejected] = []
        real = ActionValidator.validate

        def spy(validator: ActionValidator, action: AnyAction):
            result = real(validator, action)
            seen.append(result)
            return result

        patch = mock.patch.object(ActionValidator, "validate", spy)
        patch.start()
        self.addCleanup(patch.stop)
        return seen

    def test_a_pinned_zombie_is_attacked_not_the_nearest(self):
        gm = self.stage()
        add_zombie(gm, gap=2, state=ZombieState.CHASING)
        add_zombie(gm, gap=4, state=ZombieState.CHASING)
        far = add_zombie(gm, gap=6, state=ZombieState.CHASING)
        self.script("ATTACK zombie")
        seen = self.accepted()
        self.engine.play(f"hit {MENTION_MARK}", mentions=[far.zombie_id])
        self.assertEqual(seen[-1].expect(TargetZombie).zombie_id, far.zombie_id)

    def test_a_parsed_target_that_differs_from_the_pin_is_overridden(self):
        gm = self.stage()
        near = add_zombie(gm, gap=2, state=ZombieState.CHASING)
        far = add_zombie(gm, gap=6, state=ZombieState.CHASING)
        self.script(f"ATTACK {near.zombie_id}")
        seen = self.accepted()
        self.engine.play(f"hit {MENTION_MARK}", mentions=[far.zombie_id])
        self.assertEqual(seen[0].expect(TargetZombie).zombie_id, far.zombie_id)

    def test_the_parser_prompt_names_the_pin_and_the_narrator_prompt_has_no_ids(self):
        gm = self.stage()
        add_zombie(gm, gap=2, state=ZombieState.CHASING)
        far = add_zombie(gm, gap=6, state=ZombieState.CHASING)
        self.script("ATTACK zombie")
        self.engine.play(f"hit {MENTION_MARK} now", mentions=[far.zombie_id])
        self.assertIn(f"hit [pinned: {far.zombie_id}] now", self.llm.prompts[0])
        self.assertIn("[PINNED]", self.llm.prompts[0])
        narrator = self.llm.narrator_prompts[0]
        self.assertIn("hit man now", narrator)
        self.assertNotRegex(narrator, ZOMBIE_ID)
        self.assertNotIn("pinned", narrator.lower())
        self.assertNotIn(MENTION_MARK, narrator)

    def test_a_mention_no_longer_in_reach_refuses_the_turn_before_any_llm_call(self):
        gm = self.stage()
        zombie = add_zombie(gm, gap=2, state=ZombieState.CHASING)
        zombie.zone_id = "zone_building"
        minutes = gm.narrative.minutes
        result = self.engine.play(f"hit {MENTION_MARK}", mentions=[zombie.zombie_id])
        self.assertEqual(self.llm.prompts, [])
        self.assertEqual(self.llm.narrator_prompts, [])
        self.assertEqual(gm.narrative.minutes, minutes)
        self.assertIn("no longer within reach", result["story_text"])
        self.assertEqual(gm.memory.full_event_log, [])

    def test_a_turn_without_mentions_behaves_as_before(self):
        self.stage()
        self.script("NONE")
        self.engine.play("look around")
        self.assertIn("look around", self.llm.prompts[0])
        self.assertNotIn("[PINNED]", self.llm.prompts[0])
        self.assertNotIn("pinned", self.llm.prompts[0])

    def test_a_typed_at_id_with_no_pick_is_plain_prose(self):
        gm = self.stage()
        add_zombie(gm, gap=2, state=ZombieState.CHASING)
        self.script("ATTACK zombie")
        self.engine.play("hit @z1")
        self.assertIn("hit @z1", self.llm.prompts[0])
        self.assertNotIn("pinned", self.llm.prompts[0])

    def test_the_text_line_fallback_honours_a_pin(self):
        gm = self.stage()
        add_zombie(gm, gap=2, state=ZombieState.CHASING)
        far = add_zombie(gm, gap=6, state=ZombieState.CHASING)
        self.script("ATTACK zombie")
        seen = self.accepted()
        self.engine.play(f"hit {MENTION_MARK}", mentions=[far.zombie_id])
        self.assertFalse(self.llm.structured)
        self.assertEqual(seen[0].expect(TargetZombie).zombie_id, far.zombie_id)

    def test_the_json_form_honours_a_pin(self):
        gm = self.stage()
        add_zombie(gm, gap=2, state=ZombieState.CHASING)
        far = add_zombie(gm, gap=6, state=ZombieState.CHASING)
        self.llm.structured = True
        self.llm.actions = json.dumps({"actions": [{"verb": "ATTACK", "target": "zombie"}]})
        seen = self.accepted()
        self.engine.play(f"hit {MENTION_MARK}", mentions=[far.zombie_id])
        self.assertIsNotNone(self.llm.schemas[0])
        self.assertEqual(seen[0].expect(TargetZombie).zombie_id, far.zombie_id)

    def test_a_pinned_zone_is_the_destination_without_phrase_matching(self):
        gm = self.stage("zone_street")
        self.script("MOVE_TO somewhere unheard of")
        with mock.patch.object(GameManager, "resolve_places") as resolve:
            self.engine.play(f"go to {MENTION_MARK}", mentions=["zone_building"])
        resolve.assert_not_called()
        self.assertEqual(gm.player.current_location_id, "zone_building")

    def test_a_pinned_body_part_reaches_the_action(self):
        gm = self.stage()
        gm.player.body[BodyPart.HAND_L].scratch_time = 10.0
        self.script("BANDAGE")
        with mock.patch.object(SimulationCore, "resolve", autospec=True, return_value=[]) as run:
            self.engine.play(f"bandage {MENTION_MARK}", mentions=["hand_l"])
        (action,) = run.call_args.args[1]
        assert isinstance(action, BandageAction)
        self.assertEqual(action.part_name, "left hand")

    def test_a_pinned_container_is_opened_without_the_which_one_question(self):
        gm = GameManager()
        gm.player.current_room = None
        self.engine.manager = gm
        self.script("SEARCH counter")
        seen = self.accepted()
        self.engine.play(f"search {MENTION_MARK}", mentions=["bathroom_counter"])
        self.assertEqual(seen[0].expect(TargetContainer).container.container_id, "bathroom_counter")

    def test_a_pinned_window_of_a_neighbouring_zone_is_swung_at(self):
        gm = self.stage("zone_neighborhood")
        gm.world.barriers["window_supermarket"].open = False
        self.script("ATTACK window")
        seen = self.accepted()
        self.engine.play(f"smash {MENTION_MARK}", mentions=["window_supermarket"])
        self.assertEqual(seen[0].expect(TargetBarrier).barrier.barrier_id, "window_supermarket")

    def test_a_pinned_room_is_moved_into(self):
        gm = GameManager()
        gm.player.current_room = "kitchen"
        self.engine.manager = gm
        self.script("MOVE_TO nowhere")
        self.engine.play(f"go to {MENTION_MARK}", mentions=["bedroom"])
        self.assertEqual(gm.player.current_room, "bedroom")

    def test_mentions_carry_into_the_second_pass_after_a_zone_change(self):
        gm = self.stage("zone_neighborhood")
        gm.world.barriers["window_supermarket"].open = False
        gm.world.barriers["window_supermarket"].locked = False
        self.llm.parser_script = [
            "ACTIONS:\nMOVE_TO Supermarket\nATTACK window",
            "ACTIONS:\nATTACK window",
        ]
        seen = self.accepted()
        checked = self.checked()
        text = f"go to {MENTION_MARK} and smash {MENTION_MARK}"
        self.engine.play(text, mentions=["zone_supermarket", "window_supermarket"])
        self.assertEqual(gm.player.current_location_id, "zone_supermarket")
        self.assertEqual(len(self.llm.prompts), 2)
        self.assertIn("smash [pinned: supermarket window]", self.llm.prompts[1])
        self.assertTrue(any(isinstance(a.action, MoveAction) for a in seen))
        (swing,) = [r.action for r in checked if isinstance(r.action, AttackAction)]
        pin = pin_of(swing.target_name, "barrier")
        assert pin is not None
        self.assertEqual(pin.entity_id, "window_supermarket")

    def test_a_pick_bound_in_the_first_pass_is_not_bound_again_at_the_destination(self):
        gm = self.stage("zone_neighborhood")
        self.llm.parser_script = [
            "ACTIONS:\nMOVE_TO Supermarket\nMOVE_TO stockroom",
            "ACTIONS:\nMOVE_TO stockroom",
        ]
        text = f"go to {MENTION_MARK} and go into the stockroom"
        self.engine.play(text, mentions=["zone_supermarket"])
        self.assertEqual(gm.player.current_location_id, "zone_supermarket")
        self.assertEqual(gm.player.current_room, "stockroom")

    def test_a_refused_pick_is_not_bound_again_after_the_zone_change(self):
        gm = self.stage("zone_neighborhood")
        self.llm.parser_script = [
            "ACTIONS:\nMOVE_TO Pharmacy\nMOVE_TO Supermarket\nMOVE_TO stockroom",
            "ACTIONS:\nMOVE_TO stockroom",
        ]
        text = f"go to {MENTION_MARK}, go to {MENTION_MARK}, go into the stockroom"
        with mock.patch.object(ActionValidator, "validate", self.refusing("zone_pharmacy")):
            self.engine.play(text, mentions=["zone_pharmacy", "zone_supermarket"])
        self.assertEqual(gm.player.current_location_id, "zone_supermarket")
        self.assertEqual(gm.player.current_room, "stockroom")

    def test_a_mention_out_of_reach_at_the_destination_is_refused_there(self):
        gm = self.stage("zone_neighborhood")
        gm.world.barriers["window_supermarket"].open = True
        self.llm.parser_script = [
            "ACTIONS:\nMOVE_TO Supermarket\nATTACK door",
            "ACTIONS:\nATTACK door",
        ]
        text = f"go to {MENTION_MARK} and smash {MENTION_MARK}"
        self.engine.play(text, mentions=["zone_supermarket", "door_clinic"])
        self.assertEqual(gm.player.current_location_id, "zone_supermarket")
        self.assertIn("Refused", self.llm.narrator_prompts[0])
        self.assertFalse(gm.world.barriers["door_clinic"].broken)

    def test_a_pinned_item_is_held_and_no_prompt_carries_an_id_or_its_description(self):
        gm = self.stage("zone_street")
        bats = [ItemEntity(item=ITEMS["item_baseball_bat"]) for _ in range(2)]
        gm.player.inventory.extend(bats)
        item_ids.stamp_world(gm.world, gm.player)
        self.script("EQUIP Baseball Bat")
        self.engine.play(f"hold {MENTION_MARK}", mentions=[bats[1].instance_id])
        self.assertIs(weapons.held_entity(gm.player), bats[1])
        prompts = [*self.llm.prompts, *self.llm.narrator_prompts]
        self.assertEqual(len(prompts), 2)
        for prompt in prompts:
            self.assertNotRegex(prompt, ITEM_ID)
        self.assertNotIn("in your pack", self.llm.prompts[0])

    def test_the_payload_lists_the_mentionable_things(self):
        gm = self.stage("zone_neighborhood")
        add_zombie(gm, gap=3, state=ZombieState.CHASING)
        payload = self.engine.state()
        kinds = {entry["kind"] for entry in payload["mentions"]}
        self.assertEqual(kinds, {"zombie", "npc", "barrier", "zone", "item"})
        zombie = next(e for e in payload["mentions"] if e["kind"] == "zombie")
        self.assertEqual(
            zombie,
            {
                "kind": "zombie",
                "id": "z1",
                "name": "man",
                "description": "close, coming at you",
                "label": "man",
            },
        )
        for entry in payload["mentions"]:
            if entry["kind"] != "item":
                self.assertNotRegex(entry["description"], r"\d")
