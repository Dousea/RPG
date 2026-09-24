"""Action Validator: precondition checks only, no state mutation."""

import unittest

from managers.game import GameManager
from managers.validator import Accepted, ActionValidator, Rejected
from modules.action import (
    AttackAction,
    DropAction,
    MoveAction,
    NpcStatusAction,
    StatusRemoveAction,
    TakeAction,
    UpdateConditionAction,
    UseItemAction,
)
from modules.entity.object import DoorEntity, UnlockableEntityLockState


class MovementValidationTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()
        self.validator = ActionValidator(self.gm)

    def test_adjacent_move_by_direction_is_accepted(self):
        result = self.validator.validate(MoveAction(destination="out"))
        self.assertIsInstance(result, Accepted)
        self.assertEqual(result.resolved["location"].id, "zone_building")

    def test_adjacent_move_by_name_is_accepted(self):
        result = self.validator.validate(MoveAction(destination="Your Building"))
        self.assertIsInstance(result, Accepted)

    def test_non_adjacent_zone_is_reached_by_walking(self):
        # Renamed and rewritten from test_non_adjacent_real_location_is_rejected:
        # zones replace adjacency gating (Task 2) -- The Street is reachable
        # from zone_home by walking the connection graph through the building,
        # not directly adjacent, and the validator now says so instead of
        # rejecting it.
        result = self.validator.validate(MoveAction(destination="The Street"))
        self.assertIsInstance(result, Accepted)
        self.assertEqual(result.resolved["kind"], "zone")
        self.assertEqual(result.resolved["location"].id, "zone_street")

    def test_nonexistent_location_becomes_a_spot(self):
        # Renamed and rewritten from test_nonexistent_location_is_rejected:
        # MOVE_TO never fails (Task 2) -- an unmatched name soft-lands as a
        # free-text spot in the current zone instead of being rejected.
        result = self.validator.validate(MoveAction(destination="Atlantis"))
        self.assertIsInstance(result, Accepted)
        self.assertEqual(result.resolved["kind"], "spot")
        self.assertEqual(result.resolved["place"], "Atlantis")
        # State must not have moved -- validation never mutates.
        self.assertEqual(self.gm.player.current_location_id, "zone_home")

    def test_locked_door_blocks_movement_without_the_key(self):
        # Rewritten: a locked door now soft-lands ("blocked") instead of
        # rejecting the move outright (Task 2).
        # A generic locked door, distinct from the real apartment_door in
        # data/locations.py (whose key the default player already carries).
        door = DoorEntity(leads_to="zone_building")
        door.state = UnlockableEntityLockState.LOCKED
        door.key_id = "item_storage_key"
        self.gm.current_location.entities.append(door)

        result = self.validator.validate(MoveAction(destination="out"))
        self.assertIsInstance(result, Accepted)
        self.assertEqual(result.resolved["kind"], "blocked")
        self.assertEqual(result.resolved["location"].id, "zone_home")

    def test_locked_door_opens_with_the_key_in_inventory(self):
        # Rewritten: Accepted now carries kind="zone" rather than just being
        # Accepted (Task 2 adds `resolved["kind"]` to every move outcome).
        from data.items import ITEMS
        from modules.entity.item import ItemEntity

        door = DoorEntity(leads_to="zone_building")
        door.state = UnlockableEntityLockState.LOCKED
        door.key_id = "item_storage_key"
        self.gm.current_location.entities.append(door)
        self.gm.player.inventory.append(ItemEntity(item=ITEMS["item_storage_key"]))

        result = self.validator.validate(MoveAction(destination="out"))
        self.assertIsInstance(result, Accepted)
        self.assertEqual(result.resolved["kind"], "zone")

    def test_validation_never_mutates(self):
        # The validator only decides what a move means; it never writes
        # state. A spot move resolved via the validator alone (SimulationCore
        # not invoked) must leave current_place untouched.
        result = self.validator.validate(MoveAction(destination="the pharmacy"))
        self.assertIsInstance(result, Accepted)
        self.assertEqual(result.resolved["place"], "the pharmacy")
        self.assertEqual(self.gm.player.current_place, "")
        self.assertEqual(self.gm.player.current_location_id, "zone_home")


class ItemValidationTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()
        self.validator = ActionValidator(self.gm)

    def test_take_missing_item_is_rejected(self):
        result = self.validator.validate(TakeAction(item_name="Nonexistent"))
        self.assertIsInstance(result, Rejected)

    def test_take_present_item_is_accepted(self):
        self.gm.player.current_location_id = "zone_street"
        result = self.validator.validate(TakeAction(item_name="Crowbar"))
        self.assertIsInstance(result, Accepted)
        self.assertEqual(result.resolved["item_entity"].item.name, "Crowbar")

    def test_take_rejected_when_inventory_full(self):
        self.gm.player.current_location_id = "zone_street"
        self.gm.player.max_inventory_size = 0
        result = self.validator.validate(TakeAction(item_name="Crowbar"))
        self.assertIsInstance(result, Rejected)

    def test_drop_missing_item_is_rejected(self):
        result = self.validator.validate(DropAction(item_name="Crowbar"))
        self.assertIsInstance(result, Rejected)

    def test_use_item_requires_a_usable_item(self):
        from data.items import ITEMS
        from modules.entity.item import ItemEntity

        self.gm.player.inventory.append(ItemEntity(item=ITEMS["item_first_aid_kit"]))
        result = self.validator.validate(UseItemAction(item_name="First Aid Kit"))
        self.assertIsInstance(result, Accepted)

    def test_use_item_rejects_non_usable_items(self):
        from data.items import ITEMS
        from modules.entity.item import ItemEntity

        self.gm.player.inventory.append(ItemEntity(item=ITEMS["item_crowbar"]))
        result = self.validator.validate(UseItemAction(item_name="Crowbar"))
        self.assertIsInstance(result, Rejected)

    def test_use_item_not_in_inventory_is_rejected(self):
        result = self.validator.validate(UseItemAction(item_name="First Aid Kit"))
        self.assertIsInstance(result, Rejected)


class CombatValidationTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()
        # Orton now starts alone in his apartment; Emma starts in zone_building.
        self.gm.player.current_location_id = "zone_building"
        self.validator = ActionValidator(self.gm)

    def test_attack_present_npc_is_accepted(self):
        result = self.validator.validate(AttackAction(target_name="Emma"))
        self.assertIsInstance(result, Accepted)
        self.assertEqual(result.resolved["npc"].npc_id, "npc_emma")

    def test_attack_absent_npc_is_rejected(self):
        # Jen is in zone_neighborhood, not zone_building -- Marcus moved
        # there too and would now be (wrongly) co-located with the player.
        result = self.validator.validate(AttackAction(target_name="Jen"))
        self.assertIsInstance(result, Rejected)

    def test_attack_downed_npc_is_rejected(self):
        emma = self.gm.resolve_npc("Emma")
        emma.hit_points = 0
        result = self.validator.validate(AttackAction(target_name="Emma"))
        self.assertIsInstance(result, Rejected)

    def test_incapacitated_player_cannot_attack(self):
        self.gm.narrative.player_status.append("unconscious")
        result = self.validator.validate(AttackAction(target_name="Emma"))
        self.assertIsInstance(result, Rejected)


class NpcStatusValidationTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()
        self.validator = ActionValidator(self.gm)

    def test_removing_a_status_the_npc_lacks_is_rejected(self):
        result = self.validator.validate(
            NpcStatusAction(npc_name="Emma", operation="REMOVE", status="frightened")
        )
        self.assertIsInstance(result, Rejected)

    def test_adding_a_status_is_accepted(self):
        result = self.validator.validate(
            NpcStatusAction(npc_name="Emma", operation="ADD", status="frightened")
        )
        self.assertIsInstance(result, Accepted)


class PlayerStatusValidationTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()
        self.validator = ActionValidator(self.gm)

    def test_removing_a_status_the_player_lacks_is_rejected(self):
        result = self.validator.validate(StatusRemoveAction(status="settled in"))
        self.assertIsInstance(result, Rejected)


class ConditionLadderValidationTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()
        self.validator = ActionValidator(self.gm)

    def test_a_rung_name_is_accepted_with_the_resolved_rung(self):
        result = self.validator.validate(
            UpdateConditionAction(field_name="sleep", raw_value="Exhausted")
        )
        self.assertIsInstance(result, Accepted)
        self.assertEqual(result.resolved["value"], "Exhausted")

    def test_a_value_off_the_ladder_is_rejected(self):
        result = self.validator.validate(
            UpdateConditionAction(field_name="infection_risk", raw_value="banana")
        )
        self.assertIsInstance(result, Rejected)
        self.assertIn("expected one of", result.reason)


if __name__ == "__main__":
    unittest.main()
