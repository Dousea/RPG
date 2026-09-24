"""Simulation Core: deterministic outcome resolution for accepted actions."""

import random
import unittest

from data.items import ITEMS
from data.perks import PERKS
from data.traits import TRAITS
from managers.game import GameManager
from managers.simulation import SimulationCore
from modules.action import (
    AddGoalAction,
    AttackAction,
    DropAction,
    MoveAction,
    NpcMoveAction,
    NpcStatusAction,
    SetFlagAction,
    TakeAction,
    TimeAdvanceAction,
    UpdateConditionAction,
    UpdateRelationshipAction,
    UseItemAction,
)
from modules.character.equipment import CharacterHoldableSlot
from modules.entity.item import ItemEntity


def _resolve(gm: GameManager, *actions, rng=None) -> list[str]:
    return SimulationCore(gm, rng=rng).resolve(list(actions))


class LiveWorldLockedDoorTests(unittest.TestCase):
    """The starting map's real locked door (data/locations.py) -- Orton's own
    apartment door, locked from the building side only -- not a manually
    constructed one, proves the exit-requirement wiring is actually live in
    the shipped game, not just exercised in isolation."""

    def test_leaving_and_returning_succeeds_with_the_key(self):
        gm = GameManager()  # starts holding item_apartment_key
        facts = _resolve(gm, MoveAction(destination="out"), MoveAction(destination="in"))
        self.assertFalse(any(f.startswith("Refused:") for f in facts))
        self.assertEqual(gm.player.current_location_id, "zone_home")

    def test_the_apartment_is_locked_without_the_key(self):
        # Rewritten: MOVE_TO never fails (Task 2) -- a locked door soft-lands
        # the player at it instead of refusing the move.
        gm = GameManager()
        _resolve(gm, MoveAction(destination="out"))
        gm.player.inventory.clear()  # drop the apartment key
        facts = _resolve(gm, MoveAction(destination="in"))
        self.assertFalse(facts[0].startswith("Refused:"))
        self.assertIn("blocked", facts[0])
        self.assertEqual(gm.player.current_location_id, "zone_building")
        self.assertEqual(gm.player.current_place, "at the locked door to Your Apartment")

    def test_leaving_the_apartment_needs_no_key(self):
        gm = GameManager()
        gm.player.inventory.clear()  # no apartment key
        facts = _resolve(gm, MoveAction(destination="out"))
        self.assertFalse(facts[0].startswith("Refused:"))
        self.assertEqual(gm.player.current_location_id, "zone_building")


class MovementResolutionTests(unittest.TestCase):
    def test_move_mutates_player_location(self):
        gm = GameManager()
        facts = _resolve(gm, MoveAction(destination="out"))
        self.assertEqual(gm.player.current_location_id, "zone_building")
        self.assertIn("succeeded", facts[0])

    def test_move_advances_the_clock_by_one_tick(self):
        gm = GameManager()
        self.assertEqual(gm.narrative.time_of_day, "morning")
        _resolve(gm, MoveAction(destination="out"))
        self.assertEqual(gm.narrative.time_of_day, "afternoon")

    def test_move_to_unknown_becomes_a_spot_in_the_current_zone(self):
        # Replaces test_rejected_move_does_not_mutate_state_or_advance_time:
        # rejecting an unmatched name is what let the story and the state
        # diverge (MOVE_TO never fails, Task 2). Location and clock are
        # unchanged, but the fact is not a refusal.
        gm = GameManager()
        facts = _resolve(gm, MoveAction(destination="Atlantis"))
        self.assertEqual(gm.player.current_location_id, "zone_home")
        self.assertEqual(gm.player.current_place, "Atlantis")
        self.assertEqual(gm.narrative.time_of_day, "morning")
        self.assertFalse(facts[0].startswith("Refused:"))

    def test_move_by_connection_name_and_id(self):
        gm = GameManager()
        _resolve(gm, MoveAction(destination="out"))
        self.assertEqual(gm.player.current_location_id, "zone_building")
        _resolve(gm, MoveAction(destination="Your Apartment"))
        self.assertEqual(gm.player.current_location_id, "zone_home")
        # Walking through the building to the street, key still held.
        _resolve(gm, MoveAction(destination="zone_street"))
        self.assertEqual(gm.player.current_location_id, "zone_street")

    def test_move_by_alias_keeps_the_alias_as_the_spot(self):
        # "the pharmacy" is the neighborhood as far as the simulation cares,
        # but the words are where Orton actually is, so they are worth keeping.
        gm = GameManager()
        _resolve(gm, MoveAction(destination="the pharmacy"))
        self.assertEqual(gm.player.current_location_id, "zone_neighborhood")
        self.assertEqual(gm.player.current_place, "the pharmacy")

    def test_naming_the_zone_itself_clears_the_spot(self):
        gm = GameManager()
        _resolve(gm, MoveAction(destination="the kitchen"))
        self.assertEqual(gm.player.current_place, "the kitchen")
        _resolve(gm, MoveAction(destination="Your Apartment"))
        self.assertEqual(gm.player.current_place, "")

    def test_bare_directions_are_not_stored_as_a_place(self):
        # "north" with no exit behind it is a shuffle, not a destination.
        gm = GameManager()
        _resolve(gm, MoveAction(destination="north"))
        self.assertEqual(gm.player.current_place, "")

    def test_move_to_never_fails(self):
        gm = GameManager()
        for junk in (
            "Atlantis", "north", "", "the roof", "???",
            "a place with a very long name that goes on well past any "
            "sensible limit for a spot",
            "Emma's kitchen table", "12345", "MOVE_TO", "back",
        ):
            facts = _resolve(gm, MoveAction(destination=junk))
            self.assertFalse(
                facts[0].startswith("Refused:"), f"MOVE_TO {junk!r} was refused: {facts[0]}"
            )
            # Whatever happened, the world must still be describable.
            self.assertIn("[SCENE]", gm.build_narrator_prompt("look"))
        self.assertLessEqual(len(gm.player.current_place), 80)

    def test_spot_move_does_not_advance_the_clock(self):
        gm = GameManager()
        self.assertEqual(gm.narrative.time_of_day, "morning")
        _resolve(gm, MoveAction(destination="Atlantis"))
        self.assertEqual(gm.narrative.time_of_day, "morning")

    def test_zone_move_advances_one_tick_even_across_several_zones(self):
        gm = GameManager()
        self.assertEqual(gm.narrative.time_of_day, "morning")
        _resolve(gm, MoveAction(destination="The Neighborhood"))
        self.assertEqual(gm.player.current_location_id, "zone_neighborhood")
        self.assertEqual(gm.narrative.time_of_day, "afternoon")

    def test_locked_door_soft_lands_at_the_door(self):
        gm = GameManager()
        gm.player.inventory.clear()  # drop the apartment key
        _resolve(gm, MoveAction(destination="zone_street"))  # no key needed to leave
        facts = _resolve(gm, MoveAction(destination="Your Apartment"))
        self.assertEqual(gm.player.current_location_id, "zone_building")
        self.assertEqual(gm.player.current_place, "at the locked door to Your Apartment")
        self.assertIn("blocked", facts[0])
        self.assertFalse(facts[0].startswith("Refused:"))


class ItemResolutionTests(unittest.TestCase):
    def test_take_and_drop(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_street"
        gm.player.inventory.clear()  # drop the starting apartment key
        _resolve(gm, TakeAction(item_name="Crowbar"))
        self.assertEqual([e.item.name for e in gm.player.inventory], ["Crowbar"])
        _resolve(gm, DropAction(item_name="Crowbar"))
        self.assertEqual(gm.player.inventory, [])

    def test_use_consumable_heals_and_is_consumed(self):
        gm = GameManager()
        gm.player.hit_points = 50
        gm.player.inventory.clear()  # drop the starting apartment key
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_canned_beans"]))
        facts = _resolve(gm, UseItemAction(item_name="Canned Beans"))
        self.assertEqual(gm.player.hit_points, 60)  # HPModifier(amount=10)
        self.assertEqual(gm.player.inventory, [])
        self.assertIn("succeeded", facts[0])

    def test_use_appliable_heals_and_is_kept(self):
        gm = GameManager()
        gm.player.hit_points = 50
        gm.player.inventory.clear()  # drop the starting apartment key
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_first_aid_kit"]))
        _resolve(gm, UseItemAction(item_name="First Aid Kit"))
        self.assertEqual(gm.player.hit_points, 70)  # HPModifier(amount=20)
        self.assertEqual(len(gm.player.inventory), 1)  # not consumed

    def test_healing_clamps_to_max_hit_points(self):
        gm = GameManager()
        gm.player.hit_points = 95
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_canned_beans"]))
        _resolve(gm, UseItemAction(item_name="Canned Beans"))
        self.assertEqual(gm.player.hit_points, gm.player.max_hit_points)

    def test_eating_refills_hunger_and_thirst(self):
        gm = GameManager()
        gm.player.hunger = 50
        gm.player.thirst = 50
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_granola_bar"]))
        facts = _resolve(gm, UseItemAction(item_name="Granola Bar"))
        self.assertEqual(gm.player.hunger, 70)
        self.assertEqual(gm.player.thirst, 45)
        self.assertIn("hunger 70, thirst 45", facts[0])


class CombatResolutionTests(unittest.TestCase):
    def _fixed_rng(self) -> random.Random:
        # A jitter-free RNG so damage numbers are exact in assertions.
        rng = random.Random()
        rng.uniform = lambda a, b: 0.0
        return rng

    def test_unarmed_attack_deals_damage_and_reports_it(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"  # Emma starts here
        emma = gm.resolve_npc("Emma")
        before = emma.hit_points
        facts = _resolve(gm, AttackAction(target_name="Emma"), rng=self._fixed_rng())
        self.assertLess(emma.hit_points, before)
        self.assertIn("Attack Emma", facts[0])

    def test_attack_advances_the_clock(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"  # Emma starts here
        _resolve(gm, AttackAction(target_name="Emma"), rng=self._fixed_rng())
        self.assertEqual(gm.narrative.time_of_day, "afternoon")

    def test_equipped_weapon_deals_its_damage(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"  # Emma starts here
        crowbar = ItemEntity(item=ITEMS["item_crowbar"])
        gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND] = crowbar
        emma = gm.resolve_npc("Emma")
        before = emma.hit_points
        _resolve(gm, AttackAction(target_name="Emma"), rng=self._fixed_rng())
        self.assertEqual(before - emma.hit_points, ITEMS["item_crowbar"].damage)

    def test_small_frame_takes_more_damage_than_an_unmodified_defender(self):
        # This is the regression test for the _event_matches_effect_handler
        # fix: TraitID_SmallFrame's WeaponDamageTakenEffect (+10% damage
        # taken) has never once fired before this stage, because the old
        # string-prefix matcher could never match any event to any handler.
        # The pistol's damage (10) is used rather than the crowbar's (5) so
        # the 10% bump survives int() truncation in the assertion below.
        gm = GameManager()
        gm.player.current_location_id = "zone_building"  # Emma starts here
        gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND] = ItemEntity(
            item=ITEMS["item_pistol"]
        )
        # Baseline: attack an NPC with no traits (Emma has none).
        baseline_npc = gm.resolve_npc("Emma")
        before = baseline_npc.hit_points
        _resolve(gm, AttackAction(target_name="Emma"), rng=self._fixed_rng())
        baseline_damage = before - baseline_npc.hit_points

        # Now attack a stand-in defender carrying Small Frame, whose
        # WeaponDamageTakenEffect multiplies incoming damage by 1.1.
        gm2 = GameManager()
        gm2.player.equipment[CharacterHoldableSlot.RIGHT_HAND] = ItemEntity(
            item=ITEMS["item_pistol"]
        )
        marcus = gm2.resolve_npc("Marcus")
        marcus.traits = [TRAITS["TraitID_SmallFrame"]]  # type: ignore[attr-defined]
        marcus.current_location_id = gm2.player.current_location_id
        before2 = marcus.hit_points
        _resolve(gm2, AttackAction(target_name="Marcus"), rng=self._fixed_rng())
        modified_damage = before2 - marcus.hit_points

        self.assertGreater(modified_damage, baseline_damage)

    def test_gun_slinger_deals_more_and_takes_less_ranged_damage(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"  # Emma starts here
        gm.player.perks = [PERKS["PerkID_GunSlinger"]]
        gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND] = ItemEntity(
            item=ITEMS["item_pistol"]
        )
        emma = gm.resolve_npc("Emma")
        before = emma.hit_points
        _resolve(gm, AttackAction(target_name="Emma"), rng=self._fixed_rng())
        dealt = before - emma.hit_points
        # Base pistol damage is 10; Gun Slinger's +20% dealt bonus applies.
        self.assertEqual(dealt, int(ITEMS["item_pistol"].damage * 1.2))

    def test_attack_on_absent_npc_is_rejected_before_any_damage(self):
        gm = GameManager()
        facts = _resolve(gm, AttackAction(target_name="Marcus"))
        self.assertTrue(facts[0].startswith("Refused:"))


class WorldStateResolutionTests(unittest.TestCase):
    def test_add_goal(self):
        gm = GameManager()
        _resolve(gm, AddGoalAction(horizon="short_term", goal_text="Find a weapon"))
        self.assertIn("Find a weapon", gm.narrative.goals["short_term"])

    def test_set_flag(self):
        gm = GameManager()
        _resolve(gm, SetFlagAction(flag_name="power_grid_stable", value=False))
        self.assertIs(gm.narrative.flags["power_grid_stable"], False)

    def test_update_relationship(self):
        gm = GameManager()
        _resolve(gm, UpdateRelationshipAction(npc_name="Emma", axis="affection", amount=12))
        self.assertEqual(gm.relationship_manager.get_affinity("npc_emma", "player"), 12)

    def test_npc_move(self):
        gm = GameManager()
        _resolve(gm, NpcMoveAction(npc_name="Emma", destination="Your Building"))
        self.assertEqual(gm.resolve_npc("Emma").current_location_id, "zone_building")

    def test_npc_move_accepts_an_alias(self):
        gm = GameManager()
        _resolve(gm, NpcMoveAction(npc_name="Emma", destination="Lobby"))
        self.assertEqual(gm.resolve_npc("Emma").current_location_id, "zone_building")

    def test_npc_move_still_rejects_unknown_zones(self):
        # MOVE_TO soft-lands an unknown name into the player's free-text
        # spot, but NPCs have no such field -- if resolution were relaxed for
        # them too, an invented zone would scatter them somewhere
        # unreachable. This is the regression test from the zones patch.
        gm = GameManager()
        before = gm.resolve_npc("Emma").current_location_id
        facts = _resolve(gm, NpcMoveAction(npc_name="Emma", destination="Atlantis"))
        self.assertTrue(facts[0].startswith("Refused:"))
        self.assertEqual(gm.resolve_npc("Emma").current_location_id, before)

    def test_npc_status(self):
        gm = GameManager()
        _resolve(gm, NpcStatusAction(npc_name="Emma", operation="ADD", status="frightened"))
        self.assertIn("frightened", gm.resolve_npc("Emma").status)

    def test_time_advance_rolls_the_day_over(self):
        gm = GameManager()
        _resolve(gm, TimeAdvanceAction(time_of_day="night"))
        _resolve(gm, TimeAdvanceAction(time_of_day="morning"))
        self.assertEqual(gm.narrative.day, 2)

    def test_update_condition_hunger(self):
        gm = GameManager()
        _resolve(gm, UpdateConditionAction(field_name="hunger", raw_value="-10"))
        self.assertEqual(gm.player.hunger, 90)


if __name__ == "__main__":
    unittest.main()
