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
from modules.stats import CharacterStat

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

    def test_use_consumable_is_consumed(self):
        gm = GameManager()
        gm.player.hit_points = 50
        gm.player.inventory.clear()  # drop the starting apartment key
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_canned_beans"]))
        facts = _resolve(gm, UseItemAction(item_name="Canned Beans"))
        self.assertEqual(gm.player.hit_points, 50)
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
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_first_aid_kit"]))
        _resolve(gm, UseItemAction(item_name="First Aid Kit"))
        self.assertEqual(gm.player.hit_points, gm.player.max_hit_points)

    def test_eating_refills_hunger_and_thirst(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.HUNGER, 0.5)
        gm.player.stats.set(CharacterStat.THIRST, 0.5)
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_granola_bar"]))
        _resolve(gm, UseItemAction(item_name="Granola Bar"))
        self.assertAlmostEqual(gm.player.stats.get(CharacterStat.HUNGER), 0.30, delta=0.01)
        self.assertAlmostEqual(gm.player.stats.get(CharacterStat.THIRST), 0.55, delta=0.01)

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

    def test_the_stat_engine_receives_each_actions_minutes(self):
        gm = GameManager()
        core = SimulationCore(gm)
        handed: list[int] = []
        advance = core.stats_engine.advance

        def spy(player, minutes, ctx, weather_for_chunk=None):
            handed.append(minutes)
            return advance(player, minutes, ctx, weather_for_chunk)

        core.stats_engine.advance = spy
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
        gm.player.stats.set(CharacterStat.FATIGUE, 1)
        facts = _resolve(gm, SleepAction(duration=Duration(minutes=20 * 60)))
        self.assertEqual(gm.narrative.minutes, 960)
        self.assertEqual(facts[0], "Orton sleeps 16 hours, the most he can at once.")

    def test_a_short_sleep_runs_its_duration(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.FATIGUE, 1)
        _resolve(gm, SleepAction(duration=Duration(minutes=90)))
        self.assertEqual(gm.narrative.minutes, 90)


class StatTurnTests(unittest.TestCase):
    """Spec 02, Turn flow."""

    def test_a_wait_moves_the_stats_and_reports_a_threshold_crossing(self):
        gm = GameManager()
        facts = _resolve(gm, WaitAction(duration=Duration(minutes=5 * 60)))
        self.assertIn("Orton is now Peckish.", facts)
        self.assertGreater(gm.player.stats.get(CharacterStat.HUNGER), 0.15)

    def test_stat_facts_come_before_the_time_fact(self):
        gm = GameManager()
        facts = _resolve(gm, WaitAction(duration=Duration(minutes=5 * 60)))
        self.assertTrue(facts[-1].startswith("About"))
        self.assertLess(facts.index("Orton is now Peckish."), len(facts) - 1)

    def test_a_refused_action_advances_no_stats(self):
        gm = GameManager()
        facts = SimulationCore(gm).resolve(
            [UpdateConditionAction(field_name="hunger", raw_value="0")]
        )
        self.assertTrue(facts[0].startswith("Refused:"))
        self.assertEqual(gm.player.stats.get(CharacterStat.HUNGER), 0)

    def test_combat_minutes_are_exercise(self):
        gm = GameManager()
        _resolve(gm, MoveAction(destination="out"), MoveAction(destination="out"))
        endurance_before = gm.player.stats.get(CharacterStat.ENDURANCE)
        self.assertEqual(endurance_before, 1)
        core = SimulationCore(gm)
        context = core._stat_context(AttackAction(target_name="Emma"))  # pyright: ignore[reportPrivateUsage]
        self.assertTrue(context.exercising)


class SleepSpanTests(unittest.TestCase):
    """Spec 02, Waking."""

    def test_sleep_ends_when_fatigue_reaches_zero_after_an_hour(self):
        gm = GameManager()
        gm.player.current_place = "the bedroom"
        gm.player.stats.set(CharacterStat.FATIGUE, 0.2)
        facts = _resolve(gm, SleepAction())
        self.assertIn("Orton wakes fully rested.", facts)
        self.assertEqual(gm.player.stats.get(CharacterStat.FATIGUE), 0)
        self.assertGreaterEqual(gm.narrative.minutes, 60)
        self.assertLess(gm.narrative.minutes, 6 * 60)
        self.assertFalse(gm.player.asleep)

    def test_a_rested_sleeper_still_sleeps_the_first_hour(self):
        gm = GameManager()
        _resolve(gm, SleepAction())
        self.assertEqual(gm.narrative.minutes, 60)

    def test_a_timed_sleep_stops_when_the_time_is_up(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.FATIGUE, 1)
        facts = _resolve(gm, SleepAction(duration=Duration(minutes=120)))
        self.assertEqual(gm.narrative.minutes, 120)
        self.assertEqual(facts[0], "Orton sleeps 2 hours.")

    def test_open_sleep_at_night_wakes_at_nine(self):
        gm = GameManager()
        gm.advance_clock(14 * 60)  # 22:00
        gm.player.stats.set(CharacterStat.FATIGUE, 1)
        _resolve(gm, SleepAction())
        self.assertEqual((gm.narrative.hour, gm.narrative.minute), (9, 0))

    def test_the_bedroom_bed_beats_the_floor(self):
        floor, bed = GameManager(), GameManager()
        bed.player.current_place = "the bedroom"
        for gm in (floor, bed):
            gm.player.stats.set(CharacterStat.FATIGUE, 0.8)
            _resolve(gm, SleepAction(duration=Duration(minutes=120)))
        self.assertLess(
            bed.player.stats.get(CharacterStat.FATIGUE),
            floor.player.stats.get(CharacterStat.FATIGUE),
        )
        self.assertAlmostEqual(bed.player.stats.get(CharacterStat.FATIGUE), 0.8 - 0.28, delta=0.01)

    def test_a_zombie_wakes_the_sleeper_and_raises_panic_by_30_to_60(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.FATIGUE, 1)
        core = SimulationCore(gm, rng=random.Random(7))
        calls = {"n": 0}

        def zombie_on_third_chunk() -> int:
            calls["n"] += 1
            return 1 if calls["n"] == 3 else 0

        core._new_zombies_seen = zombie_on_third_chunk  # pyright: ignore[reportPrivateUsage]
        facts = core.resolve([SleepAction()])
        self.assertIn("A zombie wakes Orton in a panic.", facts)
        self.assertEqual(gm.narrative.minutes, 30)
        self.assertFalse(gm.player.asleep)
        panic = gm.player.stats.get(CharacterStat.PANIC)
        # The sighting's panic decays away within the chunk; the draw is what is left.
        self.assertAlmostEqual(panic, random.Random(7).uniform(30, 60))
        self.assertGreaterEqual(panic, 30)
        self.assertLessEqual(panic, 60)

    def test_the_interruption_panic_is_drawn_from_the_injected_rng(self):
        outcomes = []
        for seed in (1, 2):
            gm = GameManager()
            gm.player.stats.set(CharacterStat.FATIGUE, 1)
            core = SimulationCore(gm, rng=random.Random(seed))
            core._new_zombies_seen = lambda: 1  # pyright: ignore[reportPrivateUsage]
            core.resolve([SleepAction()])
            outcomes.append(gm.player.stats.get(CharacterStat.PANIC))
        self.assertNotEqual(outcomes[0], outcomes[1])
        for panic in outcomes:
            self.assertGreaterEqual(panic, 30)
            self.assertLessEqual(panic, 60)

    def test_starving_wakes_a_sleeper(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.FATIGUE, 1)
        gm.player.stats.set(CharacterStat.HUNGER, 0.699)
        gm.player.stats.set(CharacterStat.THIRST, 0)
        facts = _resolve(gm, SleepAction(duration=Duration(minutes=6 * 60)))
        self.assertIn("Hunger wakes Orton.", facts)
        self.assertLess(gm.narrative.minutes, 6 * 60)

    def test_dying_of_thirst_wakes_a_sleeper_before_it_can_kill(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.FATIGUE, 1)
        gm.player.stats.set(CharacterStat.THIRST, 0.9)
        facts = _resolve(gm, SleepAction(duration=Duration(minutes=16 * 60)))
        self.assertIn("Thirst wakes Orton.", facts)
        self.assertFalse(gm.narrative.game_over)
        self.assertGreater(gm.player.hit_points, 0)


class StatDeathTests(unittest.TestCase):
    """Spec 02, Edge cases."""

    def test_death_by_thirst_ends_the_game_with_the_cause(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.THIRST, 0.9)
        facts = _resolve(gm, WaitAction(duration=Duration(minutes=12 * 60)))
        self.assertTrue(gm.narrative.game_over)
        self.assertEqual(gm.narrative.death_cause, "Orton died of thirst.")
        self.assertTrue(any("Orton has died" in fact for fact in facts))
        self.assertEqual(gm.player.hit_points, 0)

    def test_the_clock_stops_at_the_chunk_where_orton_died(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.THIRST, 0.9)
        _resolve(gm, WaitAction(duration=Duration(minutes=12 * 60)))
        self.assertLess(gm.narrative.minutes, 6 * 60)
        self.assertEqual(gm.narrative.minutes % 10, 0)

    def test_later_actions_in_the_turn_are_refused(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.THIRST, 0.9)
        facts = _resolve(
            gm,
            WaitAction(duration=Duration(minutes=12 * 60)),
            WaitAction(duration=Duration(minutes=5)),
        )
        self.assertTrue(any(f.startswith("Refused:") and "dead" in f for f in facts))

    def test_death_while_asleep_is_not_possible_by_a_single_sleep_from_fine_health(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.FATIGUE, 1)
        _resolve(gm, SleepAction(duration=Duration(minutes=16 * 60)))
        self.assertFalse(gm.narrative.game_over)


def _food(name="Apple", **fields) -> ConsumableItem:
    return ConsumableItem(
        id=f"item_test_{name.lower()}",
        name=name,
        description="A test item.",
        max_hit_points=1,
        tags=["food", "consumable"],
        slots=[CharacterHoldableSlot.RIGHT_HAND],
        is_two_handed=False,
        modifiers=[],
        **fields,
    )


def _eat(item: ConsumableItem, **stats) -> tuple[GameManager, list[str]]:
    gm = GameManager()
    gm.player.inventory.clear()
    gm.player.inventory.append(ItemEntity(item=item))
    for stat, value in stats.items():
        gm.player.stats.set(CharacterStat[stat.upper()], value)
    return gm, _resolve(gm, UseItemAction(item_name=item.name))


def _consumable(item_id: str) -> ConsumableItem:
    item = ITEMS[item_id]
    assert isinstance(item, ConsumableItem)
    return item


class ConsumableItemFieldTests(unittest.TestCase):
    """Spec 03, Item fields."""

    def test_the_shipped_foods_carry_the_food_fields(self):
        beans = _consumable("item_canned_beans")
        self.assertAlmostEqual(beans.hunger_change, -0.35)
        self.assertAlmostEqual(beans.thirst_change, -0.05)
        water = _consumable("item_water_bottle")
        self.assertAlmostEqual(water.thirst_change, -0.45)
        self.assertEqual(water.hunger_change, 0)
        granola = _consumable("item_granola_bar")
        self.assertAlmostEqual(granola.hunger_change, -0.20)
        self.assertAlmostEqual(granola.thirst_change, 0.05)
        noodles = _consumable("item_instant_noodles")
        self.assertAlmostEqual(noodles.hunger_change, -0.40)
        self.assertAlmostEqual(noodles.thirst_change, 0.10)

    def test_no_shipped_item_is_alcoholic_and_each_takes_five_minutes_to_eat(self):
        for item in ITEMS.values():
            if isinstance(item, ConsumableItem):
                self.assertFalse(item.alcoholic)
                self.assertFalse(item.low_alcohol)
                self.assertEqual(item.eat_minutes, 5)

    def test_the_canned_beans_carry_no_hp_modifier(self):
        self.assertEqual(_consumable("item_canned_beans").modifiers, [])


class ConsumingTests(unittest.TestCase):
    """Spec 03, Consuming."""

    def test_the_beans_no_longer_heal_directly(self):
        gm = GameManager()
        gm.player.hit_points = 50
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_canned_beans"]))
        _resolve(gm, UseItemAction(item_name="Canned Beans"))
        self.assertEqual(gm.player.hit_points, 50)

    def test_each_field_applies_once(self):
        item = _food(
            hunger_change=-0.2,
            thirst_change=-0.1,
            unhappy_change=-5,
            boredom_change=-10,
            stress_change=-0.05,
        )
        gm = GameManager()
        stats = gm.player.stats
        for stat, value in (
            (CharacterStat.HUNGER, 0.5),
            (CharacterStat.THIRST, 0.5),
            (CharacterStat.UNHAPPINESS, 20),
            (CharacterStat.BOREDOM, 30),
            (CharacterStat.STRESS, 0.5),
        ):
            stats.set(stat, value)
        SimulationCore(gm)._consume(item)
        self.assertAlmostEqual(stats.get(CharacterStat.HUNGER), 0.3)
        self.assertAlmostEqual(stats.get(CharacterStat.THIRST), 0.4)
        self.assertAlmostEqual(stats.get(CharacterStat.UNHAPPINESS), 15)
        self.assertAlmostEqual(stats.get(CharacterStat.BOREDOM), 20)
        self.assertAlmostEqual(stats.get(CharacterStat.STRESS), 0.45)

    def test_bad_food_raises_unhappiness_and_clamps(self):
        gm, _ = _eat(_food(unhappy_change=30), unhappiness=90)
        self.assertGreater(gm.player.stats.get(CharacterStat.UNHAPPINESS), 99)

    def test_an_apple_adds_2080_to_the_timer(self):
        # The 5 minutes of eating then drain 900 (10800 per hour).
        gm, _ = _eat(_food(hunger_change=-0.16))
        self.assertAlmostEqual(gm.player.food_eaten_timer, 2080 - 900, delta=1)

    def test_cooked_food_doubles_the_timer(self):
        gm, _ = _eat(_food(hunger_change=-0.16, cooked=True))
        self.assertAlmostEqual(gm.player.food_eaten_timer, 4160 - 900, delta=1)

    def test_the_timer_caps_at_11000(self):
        gm = GameManager()
        gm.player.food_eaten_timer = 10500
        gm.player.inventory.append(ItemEntity(item=_food(hunger_change=-0.5)))
        _resolve(gm, UseItemAction(item_name="Apple"))
        self.assertAlmostEqual(gm.player.food_eaten_timer, 11000 - 900, delta=1)

    def test_alcohol_is_applied_to_intoxication_and_clamps_at_the_stat_maximum(self):
        item = _food("Whisky", hunger_change=-0.01, alcoholic=True)
        gm, _ = _eat(item, hunger=0.9)
        self.assertGreater(gm.player.stats.get(CharacterStat.INTOXICATION), 95)

    def test_alcohol_amounts_before_the_clamp(self):
        from managers.simulation import alcohol_intoxication

        whole = _food("Whisky", hunger_change=-0.01, alcoholic=True)
        none = _food("Spirit", alcoholic=True)
        beer = _food("Beer", hunger_change=-0.01, alcoholic=True, low_alcohol=True)
        self.assertEqual(alcohol_intoxication(whole, 0.9), 1000)
        self.assertAlmostEqual(alcohol_intoxication(whole, 0.7), 880)
        self.assertEqual(alcohol_intoxication(whole, 0.2), 800)
        self.assertEqual(alcohol_intoxication(none, 0.9), 500)
        self.assertEqual(alcohol_intoxication(none, 0.2), 400)
        self.assertEqual(alcohol_intoxication(beer, 0.2), 200)

    def test_alcohol_hunger_bands_and_their_strict_cutoffs(self):
        from managers.simulation import alcohol_intoxication

        whole = _food("Whisky", hunger_change=-0.01, alcoholic=True)
        for hunger, expected in (
            (0.5, 800),
            (0.6, 800),
            (0.61, 880),
            (0.7, 880),
            (0.8, 880),
            (0.81, 1000),
        ):
            with self.subTest(hunger=hunger):
                self.assertAlmostEqual(alcohol_intoxication(whole, hunger), expected)

    def test_the_alcohol_band_uses_hunger_before_the_meal(self):
        from unittest import mock

        import managers.simulation as simulation

        item = _food("Whisky", hunger_change=-0.1, alcoholic=True)
        gm = GameManager()
        gm.player.stats.set(CharacterStat.HUNGER, 0.65)
        with mock.patch.object(
            simulation, "alcohol_intoxication", wraps=simulation.alcohol_intoxication
        ) as spy:
            SimulationCore(gm)._consume(item)
        self.assertAlmostEqual(spy.call_args.args[1], 0.65)
        self.assertAlmostEqual(simulation.alcohol_intoxication(item, 0.65), 880)

    def test_a_non_alcoholic_item_adds_no_intoxication(self):
        gm, _ = _eat(_food(hunger_change=-0.2))
        self.assertEqual(gm.player.stats.get(CharacterStat.INTOXICATION), 0)

    def test_a_food_item_costs_its_eat_minutes(self):
        for minutes in (5, 12):
            gm, facts = _eat(_food(hunger_change=-0.1, eat_minutes=minutes))
            self.assertEqual(gm.narrative.minutes, minutes)

    def test_eating_reports_the_status_effect_it_clears(self):
        gm, facts = _eat(_food(hunger_change=-0.5), hunger=0.5)
        self.assertIn("Orton is no longer Very Hungry.", facts[0])

    def test_water_is_a_drink_with_a_thirst_change_only(self):
        gm, _ = _eat(_food("Water", thirst_change=-0.5), thirst=0.8)
        self.assertAlmostEqual(gm.player.stats.get(CharacterStat.THIRST), 0.3, delta=0.01)
        self.assertEqual(gm.player.food_eaten_timer, 0)


if __name__ == "__main__":
    unittest.main()


class WeatherWiringTests(unittest.TestCase):
    """Spec 04, Components: the simulation core feeds each chunk its weather."""

    def test_each_chunk_gets_the_weather_at_its_midpoint_and_the_zone_shelter(self):
        gm = GameManager()
        core = SimulationCore(gm)
        seen = []

        class Spy:
            def apply(self, stats, hours, ctx):
                seen.append((ctx.weather, ctx.indoors))

        core.stats_engine.register(Spy())
        core.resolve([WaitAction(duration=Duration(minutes=45))])
        self.assertEqual(len(seen), 5)
        for weather, indoors in seen:
            self.assertIsNotNone(weather)
            self.assertTrue(indoors)
        self.assertEqual(seen[0][0], gm.climate.sample(5))

    def test_the_climate_advances_with_the_clock(self):
        gm = GameManager()
        core = SimulationCore(gm)
        core.resolve([WaitAction(duration=Duration(minutes=180))])
        self.assertEqual(gm.climate.last_hour, 3)

    def test_time_after_death_still_advances_the_climate(self):
        gm = GameManager()
        gm.narrative.game_over = True
        core = SimulationCore(gm)
        spent, facts = core._spend(150)
        self.assertEqual((spent, facts), (150, []))
        self.assertEqual(gm.climate.last_hour, 2)

    def test_a_weather_fact_comes_before_the_stat_facts(self):
        gm = GameManager()
        gm.climate.start_period(1, 0.5)
        core = SimulationCore(gm)

        def advance(player, minutes, ctx, weather_for_chunk=None):
            assert weather_for_chunk is not None
            weather_for_chunk(55, 10)
            core.stats_engine.minutes_advanced = minutes
            return ["STAT FACT"]

        core.stats_engine.advance = advance
        _, facts = core._spend(10)
        self.assertEqual(facts, ["It starts to rain.", "STAT FACT"])
