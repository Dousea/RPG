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
    Duration,
    MoveAction,
    NpcMoveAction,
    NpcStatusAction,
    SetFlagAction,
    SleepAction,
    TakeAction,
    UpdateConditionAction,
    UpdateInventoryAction,
    UpdateRelationshipAction,
    UseItemAction,
    WaitAction,
)
from modules.character.equipment import CharacterHoldableSlot
from modules.entity.item import ItemEntity
from modules.item import ConsumableItem
from modules.modifier import HPModifier

# A test-local lethal item, not part of data/items.py: -500 HP guarantees
# Orton's hit points hit zero regardless of his current/max HP, without
# reaching into a real item's numbers that another test might change.
LETHAL_ITEM = ConsumableItem(
    id="item_test_poison",
    name="Suspicious Vial",
    description="Definitely not safe to drink.",
    max_hit_points=1,
    tags=["consumable"],
    slots=[CharacterHoldableSlot.RIGHT_HAND],
    is_two_handed=False,
    modifiers=[HPModifier(amount=-500)],
)


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
        # MOVE_TO never fails -- a locked door soft-lands the player at it.
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

    def test_move_to_unknown_becomes_a_spot_in_the_current_zone(self):
        # Rejecting an unmatched name would let the story and the state
        # diverge (MOVE_TO never fails). Location and clock are unchanged,
        # but the fact is not a refusal.
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
            "Atlantis",
            "north",
            "",
            "the roof",
            "???",
            "a place with a very long name that goes on well past any sensible limit for a spot",
            "Emma's kitchen table",
            "12345",
            "MOVE_TO",
            "back",
        ):
            facts = _resolve(gm, MoveAction(destination=junk))
            self.assertFalse(
                facts[0].startswith("Refused:"), f"MOVE_TO {junk!r} was refused: {facts[0]}"
            )
            # Whatever happened, the world must still be describable.
            self.assertIn("[SCENE]", gm.build_narrator_prompt("look"))
        self.assertLessEqual(len(gm.player.current_place), 80)

    def test_locked_door_soft_lands_at_the_door(self):
        gm = GameManager()
        gm.player.inventory.clear()  # drop the apartment key
        _resolve(gm, MoveAction(destination="zone_street"))  # no key needed to leave
        facts = _resolve(gm, MoveAction(destination="Your Apartment"))
        self.assertEqual(gm.player.current_location_id, "zone_building")
        self.assertEqual(gm.player.current_place, "at the locked door to Your Apartment")
        self.assertIn("blocked", facts[0])
        self.assertFalse(facts[0].startswith("Refused:"))


class FinalFixWaveMoveRoutingTests(unittest.TestCase):
    """R1-R7: routing cases from the final whole-branch code review,
    reproduced through SimulationCore (final-fix-wave.md)."""

    def test_r1_clinics_bathroom_stays_in_the_neighborhood_as_a_spot(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_neighborhood"
        before_tick = gm.narrative.time_of_day
        facts = _resolve(gm, MoveAction(destination="the clinic's bathroom"))
        self.assertEqual(gm.player.current_location_id, "zone_neighborhood")
        self.assertEqual(gm.player.current_place, "the clinic's bathroom")
        self.assertEqual(gm.narrative.time_of_day, before_tick)
        self.assertFalse(facts[0].startswith("Refused:"))

    def test_r2_emmas_kitchen_stays_in_the_building_as_a_spot(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        facts = _resolve(gm, MoveAction(destination="Emma's kitchen"))
        self.assertEqual(gm.player.current_location_id, "zone_building")
        self.assertEqual(gm.player.current_place, "Emma's kitchen")
        self.assertFalse(facts[0].startswith("Refused:"))

    def test_r3_the_street_outside_my_apartment_keeps_the_street(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_street"
        facts = _resolve(gm, MoveAction(destination="the street outside my apartment"))
        self.assertEqual(gm.player.current_location_id, "zone_street")
        self.assertFalse(facts[0].startswith("Refused:"))

    def test_r4_outside_the_building_reaches_the_street(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        facts = _resolve(gm, MoveAction(destination="outside the building"))
        self.assertEqual(gm.player.current_location_id, "zone_street")
        self.assertFalse(facts[0].startswith("Refused:"))

    def test_r5_upstairs_is_a_shuffle_that_keeps_the_place(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        gm.player.current_place = "the lobby"
        facts = _resolve(gm, MoveAction(destination="upstairs"))
        self.assertEqual(gm.player.current_location_id, "zone_building")
        self.assertEqual(gm.player.current_place, "the lobby")
        self.assertEqual(facts[0], "Moved upstairs within Your Building.")

    def test_r6_the_kitchen_from_home_is_a_spot_in_home(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_home"
        facts = _resolve(gm, MoveAction(destination="the kitchen"))
        self.assertEqual(gm.player.current_location_id, "zone_home")
        self.assertFalse(facts[0].startswith("Refused:"))

    def test_r7_naming_the_current_zone_clears_the_place(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        gm.player.current_place = "the lobby"
        facts = _resolve(gm, MoveAction(destination="Your Building"))
        self.assertEqual(facts[0], "Already in Your Building.")
        self.assertEqual(gm.player.current_place, "")


class ResidualFixExitPhraseTests(unittest.TestCase):
    """The exit rule fires only when the phrase's object names the zone
    itself, never a landmark inside it."""

    def test_outside_the_bodega_stays_on_the_street_as_a_spot(self):
        # bodega is a zone_street landmark, not the zone -- must not exit
        # into the neighborhood. A spot, not a zone change: no tick.
        gm = GameManager()
        gm.player.current_location_id = "zone_street"
        before_tick = gm.narrative.time_of_day
        facts = _resolve(gm, MoveAction(destination="outside the bodega"))
        self.assertEqual(gm.player.current_location_id, "zone_street")
        self.assertEqual(gm.narrative.time_of_day, before_tick)
        self.assertFalse(facts[0].startswith("Refused:"))

    def test_leave_the_apartment_reaches_the_building_unlocked_from_inside(self):
        gm = GameManager()  # starts holding item_apartment_key
        facts = _resolve(gm, MoveAction(destination="leave the apartment"))
        self.assertEqual(gm.player.current_location_id, "zone_building")
        self.assertFalse(facts[0].startswith("Refused:"))

    def test_exit_my_flat_reaches_the_building_even_without_the_key(self):
        # The apartment door is locked from the building side only -- leaving
        # needs no key.
        gm = GameManager()
        gm.player.inventory.clear()  # drop the apartment key
        facts = _resolve(gm, MoveAction(destination="exit my flat"))
        self.assertEqual(gm.player.current_location_id, "zone_building")
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

    def test_removing_or_reconjuring_the_apartment_key_is_refused(self):
        # REMOVE, UPDATE_QUANTITY 0 and UPDATE_QUANTITY 2 on a door key
        # must all be refused before SimulationCore ever mutates state --
        # the key count must stay exactly 1 throughout.
        gm = GameManager()  # starts holding item_apartment_key
        facts = _resolve(
            gm,
            UpdateInventoryAction(item_name="Apartment Key", operation="REMOVE", value=""),
            UpdateInventoryAction(
                item_name="Apartment Key", operation="UPDATE_QUANTITY", value="0"
            ),
            UpdateInventoryAction(
                item_name="Apartment Key", operation="UPDATE_QUANTITY", value="2"
            ),
        )
        self.assertTrue(all(f.startswith("Refused:") for f in facts))
        self.assertEqual([e.item.name for e in gm.player.inventory], ["Apartment Key"])


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
        # TraitID_SmallFrame's WeaponDamageTakenEffect (+10% damage taken)
        # must reach its handler through _event_matches_effect_handler.
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
        # unreachable.
        gm = GameManager()
        before = gm.resolve_npc("Emma").current_location_id
        facts = _resolve(gm, NpcMoveAction(npc_name="Emma", destination="Atlantis"))
        self.assertTrue(facts[0].startswith("Refused:"))
        self.assertEqual(gm.resolve_npc("Emma").current_location_id, before)

    def test_npc_move_rejects_her_apartment_as_an_unknown_location(self):
        # NPC_MOVE resolves strictly via resolve_zone_exact -- no
        # whole-word fallback -- so a phrase that only MOVE_TO could ever
        # soft-land is simply unknown here.
        gm = GameManager()
        facts = _resolve(gm, NpcMoveAction(npc_name="Emma", destination="her apartment"))
        self.assertTrue(facts[0].startswith("Refused:"))

    def test_npc_move_rejects_a_bare_out_direction(self):
        # resolve_zone_exact does no connection directions either --
        # NPC_MOVE is strict, not the player's forgiving MOVE_TO.
        gm = GameManager()
        facts = _resolve(gm, NpcMoveAction(npc_name="Jen", destination="out"))
        self.assertTrue(facts[0].startswith("Refused:"))

    def test_npc_move_into_home_is_refused_while_player_is_elsewhere(self):
        # Orton's apartment is locked; nobody gets in unless he's there
        # to let them in.
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        facts = _resolve(gm, NpcMoveAction(npc_name="Emma", destination="Your Apartment"))
        self.assertTrue(facts[0].startswith("Refused:"))
        self.assertIn(
            "Orton's apartment is locked; nobody gets in unless he's there to let them in.",
            facts[0],
        )

    def test_npc_move_into_home_is_accepted_while_player_is_there(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_home"
        facts = _resolve(gm, NpcMoveAction(npc_name="Emma", destination="Your Apartment"))
        self.assertFalse(facts[0].startswith("Refused:"))
        self.assertEqual(gm.resolve_npc("Emma").current_location_id, "zone_home")

    def test_npc_status(self):
        gm = GameManager()
        _resolve(gm, NpcStatusAction(npc_name="Emma", operation="ADD", status="frightened"))
        self.assertIn("frightened", gm.resolve_npc("Emma").status)

    def test_update_condition_hunger(self):
        gm = GameManager()
        _resolve(gm, UpdateConditionAction(field_name="hunger", raw_value="-10"))
        self.assertEqual(gm.player.hunger, 90)


class ConditionLadderResolutionTests(unittest.TestCase):
    """infection_risk starts at 'No', sleep starts at 'Rested' (NarrativeState
    defaults). A signed value steps the ladder; a rung name or synonym is
    matched case-insensitively; anything else is Refused and leaves the
    condition unchanged."""

    def test_signed_step_advances_one_rung(self):
        gm = GameManager()
        _resolve(gm, UpdateConditionAction(field_name="infection_risk", raw_value="+1"))
        self.assertEqual(gm.narrative.conditions["infection_risk"], "Low")

    def test_signed_step_clamps_at_the_top_rung(self):
        gm = GameManager()
        _resolve(gm, UpdateConditionAction(field_name="infection_risk", raw_value="+10"))
        self.assertEqual(gm.narrative.conditions["infection_risk"], "Infected")

    def test_signed_step_clamps_at_the_bottom_rung(self):
        gm = GameManager()
        _resolve(gm, UpdateConditionAction(field_name="infection_risk", raw_value="-1"))
        self.assertEqual(gm.narrative.conditions["infection_risk"], "No")

    def test_synonym_maps_to_its_rung(self):
        gm = GameManager()
        _resolve(gm, UpdateConditionAction(field_name="infection_risk", raw_value="severe"))
        self.assertEqual(gm.narrative.conditions["infection_risk"], "High")

    def test_sleep_synonym_maps_to_its_rung(self):
        gm = GameManager()
        _resolve(gm, UpdateConditionAction(field_name="sleep", raw_value="fatigued"))
        self.assertEqual(gm.narrative.conditions["sleep"], "Tired")

    def test_sleep_accepts_a_rung_name_case_insensitively(self):
        gm = GameManager()
        _resolve(gm, UpdateConditionAction(field_name="sleep", raw_value="Exhausted"))
        self.assertEqual(gm.narrative.conditions["sleep"], "Exhausted")

    def test_unrecognized_value_is_refused_and_leaves_the_condition_unchanged(self):
        gm = GameManager()
        facts = SimulationCore(gm).resolve(
            [UpdateConditionAction(field_name="infection_risk", raw_value="banana")]
        )
        self.assertTrue(facts[0].startswith("Refused:"))
        self.assertIn("expected one of", facts[0])
        self.assertEqual(gm.narrative.conditions["infection_risk"], "No")

    def test_the_raw_signed_string_is_never_stored(self):
        gm = GameManager()
        _resolve(gm, UpdateConditionAction(field_name="infection_risk", raw_value="+1"))
        self.assertNotEqual(gm.narrative.conditions["infection_risk"], "+1")


class PlayerDeathResolutionTests(unittest.TestCase):
    """SimulationCore._check_player_death is the only producer of
    NarrativeState.game_over/death_cause -- player HP only moves through
    combat and item effects, so the LLM can never kill Orton by declaration."""

    def test_lethal_item_ends_the_game(self):
        gm = GameManager()
        gm.player.inventory.clear()
        gm.player.inventory.append(ItemEntity(item=LETHAL_ITEM))
        facts = _resolve(gm, UseItemAction(item_name="Suspicious Vial"))
        self.assertTrue(gm.narrative.game_over)
        self.assertIn("Suspicious Vial", gm.narrative.death_cause)
        self.assertIn("Orton has died", facts[0])
        self.assertEqual(gm.player.hit_points, 0)

    def test_actions_after_death_are_refused(self):
        gm = GameManager()
        gm.player.inventory.clear()
        gm.player.inventory.append(ItemEntity(item=LETHAL_ITEM))
        facts = _resolve(
            gm,
            UseItemAction(item_name="Suspicious Vial"),
            AddGoalAction(horizon="short_term", goal_text="Survive"),
        )
        self.assertIn("Orton has died", facts[0])
        self.assertTrue(facts[1].startswith("Refused:"))
        self.assertNotIn("Survive", gm.narrative.goals["short_term"])

    def test_surviving_hp_does_not_end_the_game(self):
        gm = GameManager()
        gm.player.hit_points = 50
        gm.player.inventory.clear()  # drop the starting apartment key
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_canned_beans"]))
        facts = _resolve(gm, UseItemAction(item_name="Canned Beans"))
        self.assertFalse(gm.narrative.game_over)
        self.assertEqual(gm.narrative.death_cause, "")
        self.assertNotIn("Orton has died", facts[0])


if __name__ == "__main__":
    unittest.main()


def _spent(gm: GameManager, *actions) -> int:
    before = gm.narrative.minutes
    _resolve(gm, *actions)
    return gm.narrative.minutes - before


class TimeCostTests(unittest.TestCase):
    """Spec 01, Time costs."""

    def test_a_swing_costs_one_minute(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        self.assertEqual(_spent(gm, AttackAction(target_name="Emma")), 1)

    def test_take_and_drop_cost_one_minute(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_street"
        self.assertEqual(_spent(gm, TakeAction(item_name="Crowbar")), 1)
        self.assertEqual(_spent(gm, DropAction(item_name="Crowbar")), 1)

    def test_using_a_non_food_item_costs_one_minute(self):
        gm = GameManager()
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_first_aid_kit"]))
        self.assertEqual(_spent(gm, UseItemAction(item_name="First Aid Kit")), 1)

    def test_eating_costs_the_default_five_minutes(self):
        gm = GameManager()
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_canned_beans"]))
        self.assertEqual(_spent(gm, UseItemAction(item_name="Canned Beans")), 5)

    def test_the_action_time_multiplier_scales_only_the_timed_verbs(self):
        def spent_with_double(gm: GameManager, action) -> int:
            core = SimulationCore(gm)
            core._action_time_multiplier = lambda: 2.0  # pyright: ignore[reportPrivateUsage]
            before = gm.narrative.minutes
            core.resolve([action])
            return gm.narrative.minutes - before

        gm = GameManager()
        gm.player.current_location_id = "zone_street"
        self.assertEqual(spent_with_double(gm, TakeAction(item_name="Crowbar")), 2)
        self.assertEqual(spent_with_double(gm, DropAction(item_name="Crowbar")), 2)
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_canned_beans"]))
        self.assertEqual(spent_with_double(gm, UseItemAction(item_name="Canned Beans")), 10)
        self.assertEqual(spent_with_double(gm, WaitAction(duration=Duration(minutes=7))), 7)
        self.assertEqual(spent_with_double(gm, MoveAction(destination="zone_building")), 10)
        gm.player.current_location_id = "zone_building"
        self.assertEqual(spent_with_double(gm, AttackAction(target_name="Emma")), 1)

    def test_a_zone_hop_costs_ten_minutes_per_hop(self):
        gm = GameManager()
        self.assertEqual(_spent(gm, MoveAction(destination="out")), 10)
        self.assertEqual(_spent(gm, MoveAction(destination="zone_street")), 10)

    def test_a_walk_over_several_hops_costs_ten_per_hop(self):
        gm = GameManager()
        self.assertEqual(_spent(gm, MoveAction(destination="zone_street")), 20)
        self.assertEqual(_spent(gm, MoveAction(destination="The Neighborhood")), 10)

    def test_a_move_within_a_zone_costs_one_minute(self):
        gm = GameManager()
        self.assertEqual(_spent(gm, MoveAction(destination="the kitchen")), 1)
        self.assertEqual(_spent(gm, MoveAction(destination="north")), 1)

    def test_a_locked_door_stop_costs_the_walk_to_it(self):
        gm = GameManager()
        _resolve(gm, MoveAction(destination="out"))
        gm.player.inventory.clear()
        self.assertEqual(_spent(gm, MoveAction(destination="Your Apartment")), 1)

    def test_zero_minute_verbs_cost_nothing(self):
        gm = GameManager()
        spent = _spent(
            gm,
            AddGoalAction(horizon="short_term", goal_text="Find water"),
            SetFlagAction(flag_name="x", value=True),
            UpdateConditionAction(field_name="hunger", raw_value="-10"),
        )
        self.assertEqual(spent, 0)

    def test_a_refused_action_costs_nothing(self):
        gm = GameManager()
        facts = _resolve(gm, TakeAction(item_name="Unicorn"))
        self.assertTrue(facts[0].startswith("Refused:"))
        self.assertEqual(gm.narrative.minutes, 0)
        self.assertEqual(len(facts), 1)

    def test_a_none_turn_costs_one_minute(self):
        gm = GameManager()
        facts = _resolve(gm)
        self.assertEqual(gm.narrative.minutes, 1)
        self.assertEqual(facts, ["About 1 minute passes."])

    def test_world_clock_follows_each_action(self):
        gm = GameManager()
        _resolve(gm, WaitAction(duration=Duration(minutes=75)))
        self.assertEqual(gm.world.time, "09:15 AM")

    def test_the_turn_fact_reports_the_summed_minutes(self):
        gm = GameManager()
        facts = _resolve(
            gm,
            MoveAction(destination="out"),
            WaitAction(duration=Duration(minutes=30)),
        )
        self.assertEqual(gm.narrative.minutes, 40)
        self.assertEqual(facts[-1], "About 40 minutes pass.")
        self.assertEqual(len(facts), 3)

    def test_the_minutes_fact_is_absent_when_nothing_took_time(self):
        gm = GameManager()
        facts = _resolve(gm, AddGoalAction(horizon="short_term", goal_text="Find water"))
        self.assertFalse(any("pass" in fact for fact in facts))

    def test_the_stat_engine_hand_off_receives_each_actions_minutes(self):
        gm = GameManager()
        core = SimulationCore(gm)
        handed: list[int] = []
        core._advance_stats = lambda minutes: handed.append(minutes)  # pyright: ignore[reportPrivateUsage]
        core.resolve([MoveAction(destination="out"), WaitAction(duration=Duration(minutes=5))])
        self.assertEqual(handed, [10, 5])


class ClockEdgeCaseTests(unittest.TestCase):
    """Spec 01, Edge cases."""

    def test_wait_until_night_from_0800_lands_on_2200(self):
        gm = GameManager()
        _resolve(gm, WaitAction(duration=Duration(until_time_of_day="night")))
        self.assertEqual((gm.narrative.day, gm.narrative.hour, gm.narrative.minute), (1, 22, 0))

    def test_wait_until_morning_at_0700_lands_on_0600_next_day(self):
        gm = GameManager()
        gm.advance_clock(1440 - 480 + 7 * 60)  # 07:00 on day 2
        _resolve(gm, WaitAction(duration=Duration(until_time_of_day="morning")))
        self.assertEqual((gm.narrative.day, gm.narrative.hour, gm.narrative.minute), (3, 6, 0))

    def test_wait_until_morning_while_in_the_morning_never_waits_zero(self):
        gm = GameManager()
        self.assertEqual(
            _spent(gm, WaitAction(duration=Duration(until_time_of_day="morning"))), 22 * 60
        )

    def test_wait_until_a_clock_time_already_past_is_tomorrow(self):
        gm = GameManager()
        _resolve(gm, WaitAction(duration=Duration(until_minute_of_day=7 * 60)))
        self.assertEqual((gm.narrative.day, gm.narrative.hour), (2, 7))

    def test_a_wait_over_24_hours_is_clamped_and_says_so(self):
        gm = GameManager()
        facts = _resolve(gm, WaitAction(duration=Duration(minutes=30 * 60)))
        self.assertEqual(gm.narrative.minutes, 1440)
        self.assertEqual(facts[0], "Orton waits 24 hours, the most he can at once.")

    def test_a_sleep_over_16_hours_is_clamped_and_says_so(self):
        gm = GameManager()
        facts = _resolve(gm, SleepAction(duration=Duration(minutes=20 * 60)))
        self.assertEqual(gm.narrative.minutes, 960)
        self.assertEqual(facts[0], "Orton sleeps 16 hours, the most he can at once.")

    def test_a_short_sleep_runs_its_duration(self):
        gm = GameManager()
        _resolve(gm, SleepAction(duration=Duration(minutes=90)))
        self.assertEqual(gm.narrative.minutes, 90)
