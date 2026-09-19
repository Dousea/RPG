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
    UseItemAction,
)
from modules.entity.object import DoorEntity, UnlockableEntityLockState


class MovementValidationTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()
        self.validator = ActionValidator(self.gm)

    def test_adjacent_move_by_direction_is_accepted(self):
        result = self.validator.validate(MoveAction(destination="north"))
        self.assertIsInstance(result, Accepted)
        self.assertEqual(result.resolved["location"].id, "location_id_office")

    def test_adjacent_move_by_name_is_accepted(self):
        result = self.validator.validate(MoveAction(destination="Office"))
        self.assertIsInstance(result, Accepted)

    def test_non_adjacent_real_location_is_rejected(self):
        # Office exists in the world but is not connected to the hallway's
        # south neighbor (the lobby) directly -- this is the reachability bug
        # `resolve_location`'s global name match used to let through.
        self.gm.player.current_location_id = "location_id_lobby"
        result = self.validator.validate(MoveAction(destination="Office"))
        self.assertIsInstance(result, Rejected)

    def test_nonexistent_location_is_rejected(self):
        result = self.validator.validate(MoveAction(destination="Atlantis"))
        self.assertIsInstance(result, Rejected)
        # State must not have moved -- validation never mutates.
        self.assertEqual(self.gm.player.current_location_id, "location_id_hallway")

    def test_locked_door_blocks_movement_without_the_key(self):
        door = DoorEntity(leads_to="location_id_office")
        door.state = UnlockableEntityLockState.LOCKED
        door.key_id = "item_apartment_key"
        self.gm.current_location.entities.append(door)

        result = self.validator.validate(MoveAction(destination="north"))
        self.assertIsInstance(result, Rejected)
        self.assertIn("locked", result.reason)

    def test_locked_door_opens_with_the_key_in_inventory(self):
        from data.items import ITEMS
        from modules.entity.item import ItemEntity

        door = DoorEntity(leads_to="location_id_office")
        door.state = UnlockableEntityLockState.LOCKED
        door.key_id = "item_apartment_key"
        self.gm.current_location.entities.append(door)
        self.gm.player.inventory.append(ItemEntity(item=ITEMS["item_apartment_key"]))

        result = self.validator.validate(MoveAction(destination="north"))
        self.assertIsInstance(result, Accepted)


class ItemValidationTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()
        self.validator = ActionValidator(self.gm)

    def test_take_missing_item_is_rejected(self):
        result = self.validator.validate(TakeAction(item_name="Nonexistent"))
        self.assertIsInstance(result, Rejected)

    def test_take_present_item_is_accepted(self):
        self.gm.player.current_location_id = "location_id_office"
        result = self.validator.validate(TakeAction(item_name="Crowbar"))
        self.assertIsInstance(result, Accepted)
        self.assertEqual(result.resolved["item_entity"].item.name, "Crowbar")

    def test_take_rejected_when_inventory_full(self):
        self.gm.player.current_location_id = "location_id_office"
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
        self.validator = ActionValidator(self.gm)

    def test_attack_present_npc_is_accepted(self):
        result = self.validator.validate(AttackAction(target_name="Emma"))
        self.assertIsInstance(result, Accepted)
        self.assertEqual(result.resolved["npc"].npc_id, "npc_emma")

    def test_attack_absent_npc_is_rejected(self):
        result = self.validator.validate(AttackAction(target_name="Marcus"))
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


if __name__ == "__main__":
    unittest.main()
