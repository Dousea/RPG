"""Simulation Core: deterministic outcome resolution for accepted actions."""

import random
import unittest

from data.items import ITEMS
from managers.game import GameManager
from managers.simulation import SimulationCore
from managers.skills import SkillEngine
from modules.action.types import (
    AddGoalAction,
    AttackAction,
    DropAction,
    Duration,
    MoveAction,
    NpcMoveAction,
    NpcStatusAction,
    SetFlagAction,
    TakeAction,
    TakeOffAction,
    UpdateInventoryAction,
    UpdateRelationshipAction,
    UseItemAction,
    WaitAction,
    WearAction,
)
from modules.body import BodyLocation
from modules.character.equipment import CharacterHoldableSlot
from modules.entity.item import ItemEntity
from modules.item import ConsumableItem
from modules.modifier import HPModifier
from modules.stats import CharacterStat
from tests.support import simulate

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


class ItemResolutionTests(unittest.TestCase):
    def test_take_and_drop(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_street"
        gm.player.inventory.clear()  # drop the starting apartment key
        simulate(gm, TakeAction(item_name="Crowbar"))
        self.assertEqual([e.item.name for e in gm.player.inventory], ["Crowbar"])
        simulate(gm, DropAction(item_name="Crowbar"))
        self.assertEqual(gm.player.inventory, [])

    def test_use_consumable_is_consumed(self):
        gm = GameManager()
        gm.player.hit_points = 50
        gm.player.inventory.clear()  # drop the starting apartment key
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_canned_beans"]))
        facts = simulate(gm, UseItemAction(item_name="Canned Beans"))
        self.assertEqual(gm.player.hit_points, 50)
        self.assertEqual(gm.player.inventory, [])
        self.assertIn("succeeded", facts[0])

    def test_use_appliable_heals_and_is_kept(self):
        gm = GameManager()
        gm.player.hit_points = 50
        gm.player.inventory.clear()  # drop the starting apartment key
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_first_aid_kit"]))
        simulate(gm, UseItemAction(item_name="First Aid Kit"))
        self.assertEqual(gm.player.hit_points, 70)  # HPModifier(amount=20)
        self.assertEqual(len(gm.player.inventory), 1)  # not consumed

    def test_healing_clamps_to_max_hit_points(self):
        gm = GameManager()
        gm.player.hit_points = 95
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_first_aid_kit"]))
        simulate(gm, UseItemAction(item_name="First Aid Kit"))
        self.assertEqual(gm.player.hit_points, gm.player.max_hit_points)

    def test_eating_refills_hunger_and_thirst(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.HUNGER, 0.5)
        gm.player.stats.set(CharacterStat.THIRST, 0.5)
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_granola_bar"]))
        simulate(gm, UseItemAction(item_name="Granola Bar"))
        self.assertAlmostEqual(gm.player.stats.get(CharacterStat.HUNGER), 0.30, delta=0.01)
        self.assertAlmostEqual(gm.player.stats.get(CharacterStat.THIRST), 0.55, delta=0.01)

    def test_removing_or_reconjuring_the_apartment_key_is_refused(self):
        # REMOVE, UPDATE_QUANTITY 0 and UPDATE_QUANTITY 2 on a door key
        # must all be refused before SimulationCore ever mutates state --
        # the key count must stay exactly 1 throughout.
        gm = GameManager()  # starts holding item_apartment_key
        facts = simulate(
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


class WorldStateResolutionTests(unittest.TestCase):
    def test_add_goal(self):
        gm = GameManager()
        simulate(gm, AddGoalAction(horizon="short_term", goal_text="Find a weapon"))
        self.assertIn("Find a weapon", gm.narrative.goals["short_term"])

    def test_set_flag(self):
        gm = GameManager()
        simulate(gm, SetFlagAction(flag_name="power_grid_stable", value=False))
        self.assertIs(gm.narrative.flags["power_grid_stable"], False)

    def test_update_relationship(self):
        gm = GameManager()
        simulate(gm, UpdateRelationshipAction(npc_name="Emma", axis="affection", amount=12))
        self.assertEqual(gm.relationship_manager.get_affinity("npc_emma", "player"), 12)

    def test_npc_move(self):
        gm = GameManager()
        simulate(gm, NpcMoveAction(npc_name="Emma", destination="Your Building"))
        self.assertEqual(gm.resolve_npc("Emma").current_location_id, "zone_building")

    def test_npc_move_accepts_an_alias(self):
        gm = GameManager()
        simulate(gm, NpcMoveAction(npc_name="Emma", destination="Lobby"))
        self.assertEqual(gm.resolve_npc("Emma").current_location_id, "zone_building")

    def test_npc_move_still_rejects_unknown_zones(self):
        # MOVE_TO soft-lands an unknown name into the player's free-text
        # spot, but NPCs have no such field -- if resolution were relaxed for
        # them too, an invented zone would scatter them somewhere
        # unreachable.
        gm = GameManager()
        before = gm.resolve_npc("Emma").current_location_id
        facts = simulate(gm, NpcMoveAction(npc_name="Emma", destination="Atlantis"))
        self.assertTrue(facts[0].startswith("Refused:"))
        self.assertEqual(gm.resolve_npc("Emma").current_location_id, before)

    def test_npc_move_rejects_her_apartment_as_an_unknown_location(self):
        # NPC_MOVE resolves strictly via resolve_zone_exact -- no
        # whole-word fallback -- so a phrase that only MOVE_TO could ever
        # soft-land is simply unknown here.
        gm = GameManager()
        facts = simulate(gm, NpcMoveAction(npc_name="Emma", destination="her apartment"))
        self.assertTrue(facts[0].startswith("Refused:"))

    def test_npc_move_rejects_a_bare_out_direction(self):
        # resolve_zone_exact does no connection directions either --
        # NPC_MOVE is strict, not the player's forgiving MOVE_TO.
        gm = GameManager()
        facts = simulate(gm, NpcMoveAction(npc_name="Jen", destination="out"))
        self.assertTrue(facts[0].startswith("Refused:"))

    def test_npc_move_into_home_is_refused_while_player_is_elsewhere(self):
        # Orton's apartment is locked; nobody gets in unless he's there
        # to let them in.
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        facts = simulate(gm, NpcMoveAction(npc_name="Emma", destination="Your Apartment"))
        self.assertTrue(facts[0].startswith("Refused:"))
        self.assertIn(
            "Orton's apartment is locked; nobody gets in unless he's there to let them in.",
            facts[0],
        )

    def test_npc_move_into_home_is_accepted_while_player_is_there(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_home"
        facts = simulate(gm, NpcMoveAction(npc_name="Emma", destination="Your Apartment"))
        self.assertFalse(facts[0].startswith("Refused:"))
        self.assertEqual(gm.resolve_npc("Emma").current_location_id, "zone_home")

    def test_npc_status(self):
        gm = GameManager()
        simulate(gm, NpcStatusAction(npc_name="Emma", operation="ADD", status="frightened"))
        self.assertIn("frightened", gm.resolve_npc("Emma").status)


class PlayerDeathResolutionTests(unittest.TestCase):
    """SimulationCore._check_player_death is the only producer of
    NarrativeState.game_over/death_cause -- player HP only moves through
    combat and item effects, so the LLM can never kill Orton by declaration."""

    def test_lethal_item_ends_the_game(self):
        gm = GameManager()
        gm.player.inventory.clear()
        gm.player.inventory.append(ItemEntity(item=LETHAL_ITEM))
        facts = simulate(gm, UseItemAction(item_name="Suspicious Vial"))
        self.assertTrue(gm.narrative.game_over)
        self.assertIn("Suspicious Vial", gm.narrative.death_cause)
        self.assertIn("Orton has died", facts[0])
        self.assertEqual(gm.player.hit_points, 0)

    def test_actions_after_death_are_refused(self):
        gm = GameManager()
        gm.player.inventory.clear()
        gm.player.inventory.append(ItemEntity(item=LETHAL_ITEM))
        facts = simulate(
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
        facts = simulate(gm, UseItemAction(item_name="Canned Beans"))
        self.assertFalse(gm.narrative.game_over)
        self.assertEqual(gm.narrative.death_cause, "")
        self.assertNotIn("Orton has died", facts[0])


class OutcomeFactsCarryNoNumbersTests(unittest.TestCase):
    """docs/01-engine-authority.md: outcome facts describe HP, damage and
    relationship scores in words, never as numbers."""

    def setUp(self):
        self.gm = GameManager()
        self.gm.player.current_location_id = "zone_building"  # Emma starts here
        emma = self.gm.resolve_npc("Emma")
        assert emma is not None
        self.emma = emma
        rng = random.Random()
        rng.uniform = lambda a, b: 0.0
        self.rng = rng

    def _first_fact(self, action) -> str:
        fact = simulate(self.gm, action, rng=self.rng)[0]
        self.assertNotRegex(fact, r"\d")
        return fact

    def test_an_attack_reports_how_hurt_the_target_is(self):
        self.gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND] = ItemEntity(
            item=ITEMS["item_crowbar"]
        )
        cases = ((100, "barely hurt"), (40, "badly injured"), (20, "critically injured"))
        for hit_points, words in cases:
            with self.subTest(hit_points=hit_points):
                self.emma.hit_points = hit_points
                fact = self._first_fact(AttackAction(target_name="Emma"))
                self.assertIn(f"Emma is {words}", fact)

    def test_using_an_item_reports_how_hurt_orton_is(self):
        self.gm.player.hit_points = 50
        self.gm.player.inventory.append(ItemEntity(item=ITEMS["item_first_aid_kit"]))
        fact = self._first_fact(UseItemAction(item_name="First Aid Kit"))
        self.assertIn("Use First Aid Kit: succeeded, Orton is ", fact)

    def test_an_unhurt_player_reads_as_unhurt(self):
        self.gm.player.inventory.append(ItemEntity(item=ITEMS["item_first_aid_kit"]))
        fact = self._first_fact(UseItemAction(item_name="First Aid Kit"))
        self.assertIn("Orton is unhurt", fact)

    def test_an_item_condition_update_reads_as_a_word(self):
        fact = self._first_fact(
            UpdateInventoryAction(
                item_name="Apartment Key", operation="UPDATE_CONDITION", value="3"
            )
        )
        self.assertEqual(fact, "Apartment Key is now damaged.")

    def test_relationship_updates_read_as_bands(self):
        relationships = self.gm.relationship_manager
        fact = self._first_fact(
            UpdateRelationshipAction(npc_name="Emma", axis="affection", amount=5)
        )
        disposition = relationships.get_disposition("npc_emma", "player")
        self.assertEqual(fact, f"Emma now feels {disposition} toward Orton.")
        fact = self._first_fact(UpdateRelationshipAction(npc_name="Emma", axis="trust", amount=-5))
        trust = relationships.get_trust_level("npc_emma", "player")
        self.assertEqual(fact, f"Emma's trust in Orton is now {trust}.")


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


class WearTimeMultiplierTests(unittest.TestCase):
    """Spec 01, Time costs: the action-time multiplier scales WEAR and TAKE_OFF."""

    def test_wear_and_take_off_are_multiplied_actions(self):
        from data.time_costs import MULTIPLIED_ACTIONS

        self.assertIn(WearAction, MULTIPLIED_ACTIONS)
        self.assertIn(TakeOffAction, MULTIPLIED_ACTIONS)

    def test_a_doubled_multiplier_doubles_the_wear_cost(self):
        gm = GameManager()
        gm.player.worn.clear()
        gm.player.inventory.clear()
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_tshirt"]))
        core = SimulationCore(gm, rng=random.Random(0))
        core._action_time_multiplier = lambda: 2.0  # type: ignore[method-assign]
        before = gm.narrative.minutes
        core.resolve([WearAction(item_name="T-shirt")])
        self.assertEqual(gm.narrative.minutes - before, 2)


class WearResolutionTests(unittest.TestCase):
    """Spec 05, Actions: WEAR and TAKE_OFF cost 1 minute each."""

    def setUp(self):
        self.gm = GameManager()
        self.gm.player.worn.clear()
        self.gm.player.inventory.clear()

    def _spent(self, action) -> int:
        before = self.gm.narrative.minutes
        simulate(self.gm, action)
        return self.gm.narrative.minutes - before

    def test_wear_moves_the_item_to_its_location_in_one_minute(self):
        entity = ItemEntity(item=ITEMS["item_tshirt"])
        self.gm.player.inventory.append(entity)
        self.assertEqual(self._spent(WearAction(item_name="T-shirt")), 1)
        self.assertEqual(self.gm.player.inventory, [])
        self.assertIs(self.gm.player.worn[BodyLocation.TSHIRT], entity)

    def test_take_off_moves_the_item_to_the_inventory_in_one_minute(self):
        entity = ItemEntity(item=ITEMS["item_jeans"])
        self.gm.player.worn[BodyLocation.PANTS] = entity
        self.assertEqual(self._spent(TakeOffAction(item_name="Jeans")), 1)
        self.assertEqual(self.gm.player.worn, {})
        self.assertEqual(self.gm.player.inventory, [entity])

    def test_a_refused_wear_costs_no_time_and_changes_nothing(self):
        self.assertEqual(self._spent(WearAction(item_name="T-shirt")), 0)
        self.assertEqual(self.gm.player.worn, {})

    def test_wetness_travels_with_the_item(self):
        entity = ItemEntity(item=ITEMS["item_tshirt"], wetness=40.0)
        self.gm.player.inventory.append(entity)
        simulate(self.gm, WearAction(item_name="T-shirt"))
        simulate(self.gm, TakeOffAction(item_name="T-shirt"))
        self.assertEqual(self.gm.player.inventory[0], entity)
        self.assertGreater(entity.wetness, 30.0)
        self.assertLessEqual(entity.wetness, 40.0)


class BoundaryTickWiringTests(unittest.TestCase):
    """Spec 08, Regularity and stiffness over time: the clock drives the ticks."""

    def test_regularity_decays_by_two_thousandths_after_a_day_idle(self):
        gm = GameManager()
        gm.narrative.minutes = 3000
        gm.player.exercise.last_done_minute["squats"] = 0
        gm.player.exercise.regularity["squats"] = 50.0
        simulate(gm, WaitAction(duration=Duration(minutes=10)))
        self.assertAlmostEqual(gm.player.exercise.regularity["squats"], 50 - 0.002)

    def test_a_boundary_drains_one_unit_of_stiffness_into_each_part(self):
        from data.exercises import REGION_PARTS

        gm = GameManager()
        gm.player.exercise.region_timers["arms"] = 0
        gm.player.exercise.future_stiffness["arms"] = 1.0
        simulate(gm, WaitAction(duration=Duration(minutes=10)))
        for part in REGION_PARTS["arms"]:
            self.assertEqual(gm.player.exercise.part_stiffness[part], 2.5)


class DeathBeforeTicksTests(unittest.TestCase):
    """Spec 08, Where XP comes from: a lethal chunk is judged before the ticks run."""

    def test_a_starvation_death_in_a_levelling_chunk_ends_the_game(self):
        gm = GameManager()
        gm.narrative.minutes = 2405
        player = gm.player
        player.hit_points = 1
        player.fractional_hp_loss = 0.999
        player.stats.set(CharacterStat.HUNGER, 1.0)
        player.stats.set(CharacterStat.ENDURANCE, 0.1)
        SkillEngine().set_level(player, "fitness", 5)
        player.skills["fitness"].xp = 37500
        player.loss_timers = {"fitness": 30000}
        player.loss_timer_steps = {"fitness": -5}
        facts = simulate(gm, WaitAction(duration=Duration(minutes=10)))
        self.assertTrue(gm.narrative.game_over)
        self.assertIn("Orton has died", " ".join(facts))
        self.assertEqual(player.skills["fitness"].xp, 37500)


def _crowbar_game() -> GameManager:
    gm = GameManager()
    gm.player.current_location_id = "zone_building"
    gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND] = ItemEntity(item=ITEMS["item_crowbar"])
    return gm


class MeleeHitXpTests(unittest.TestCase):
    """Spec 08, Where XP comes from: a melee hit against an NPC."""

    def test_a_crowbar_hit_trains_fitness_strength_and_long_blunt(self):
        gm = _crowbar_game()
        simulate(gm, AttackAction(target_name="Emma"))
        skills = gm.player.skills
        self.assertAlmostEqual(skills["fitness"].xp, 37501)
        self.assertAlmostEqual(skills["strength"].xp, 37501)
        # min(3, 0.9 x 0.875) = 0.7875, times 0.25 for no boost and 1.3 for Fast Learner
        self.assertAlmostEqual(skills["long_blunt"].xp, 0.2559375)

    def test_bare_hands_train_only_fitness_and_strength(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        simulate(gm, AttackAction(target_name="Emma"))
        trained = {s: st.xp for s, st in gm.player.skills.items() if st.xp}
        self.assertEqual(trained, {"fitness": 37501.0, "strength": 37501.0})

    def test_no_fitness_xp_at_or_below_half_endurance(self):
        gm = _crowbar_game()
        gm.player.stats.set(CharacterStat.ENDURANCE, 0.4)
        simulate(gm, AttackAction(target_name="Emma"))
        self.assertEqual(gm.player.skills["fitness"].xp, 37500)
        self.assertAlmostEqual(gm.player.skills["strength"].xp, 37501)

    def test_a_pistol_hit_trains_no_category(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND] = ItemEntity(
            item=ITEMS["item_pistol"]
        )
        simulate(gm, AttackAction(target_name="Emma"))
        self.assertEqual(gm.player.skills["aiming"].xp, 0)

    def test_a_level_gained_from_a_hit_is_its_own_fact(self):
        gm = _crowbar_game()
        gm.player.skills["strength"].xp = 67499.5
        gm.player.skills["strength"].level = 5
        facts = simulate(gm, AttackAction(target_name="Emma"))
        self.assertIn("Your Strength skill is now level 6.", facts)
        self.assertNotRegex(facts[0], r"\d")


class TickWiringTests(unittest.TestCase):
    """Spec 08, Losing them when you stop training: the 10-minute boundary."""

    def test_ten_minutes_run_the_timers_once(self):
        gm = GameManager()
        simulate(gm, WaitAction(duration=Duration(minutes=10)))
        self.assertEqual(gm.player.loss_timers["fitness"], -49990)

    def test_two_five_minute_waits_cross_one_boundary(self):
        gm = GameManager()
        simulate(gm, WaitAction(duration=Duration(minutes=5)))
        self.assertEqual(gm.player.loss_timers["fitness"], -50000)
        simulate(gm, WaitAction(duration=Duration(minutes=5)))
        self.assertEqual(gm.player.loss_timers["fitness"], -49990)

    def test_an_hour_runs_six_ticks(self):
        gm = GameManager()
        simulate(gm, WaitAction(duration=Duration(minutes=60)))
        self.assertEqual(gm.player.loss_timers["fitness"], -49940)

    def test_the_boundary_hook_knows_whether_the_player_was_walking(self):
        gm = GameManager()
        core = SimulationCore(gm)
        seen: list[bool] = []

        def record(player, *, walking):
            seen.append(walking)
            return []

        core.skill_engine.tick = record  # type: ignore[method-assign]
        core.resolve([WaitAction(duration=Duration(minutes=10))])
        core.resolve([MoveAction(destination="the kitchen")])
        self.assertEqual(seen, [False])
        core.resolve([MoveAction(destination="out")])
        self.assertEqual(seen, [False, True])

    def test_the_players_fitness_level_sets_the_recovery(self):
        low, high = GameManager(), GameManager()
        for gm, level in ((low, 0), (high, 10)):
            gm.player.skills["fitness"].level = level
            gm.player.stats.set(CharacterStat.ENDURANCE, 0.0)
            simulate(gm, WaitAction(duration=Duration(minutes=6)))
        ratio = high.player.stats.get(CharacterStat.ENDURANCE) / low.player.stats.get(
            CharacterStat.ENDURANCE
        )
        self.assertAlmostEqual(ratio, 1.6 / 0.7, places=2)


if __name__ == "__main__":
    unittest.main()
