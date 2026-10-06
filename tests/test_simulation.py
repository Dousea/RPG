"""Simulation Core: deterministic outcome resolution for accepted actions."""

import dataclasses
import random
import unittest

from adapters.save import codec
from data.items import ITEMS
from managers.game import GameManager
from managers.simulation import SimulationCore
from managers.skills import SkillEngine
from managers.validator import ActionValidator, Rejected
from managers.zombies import (
    MinuteReport,
    PlayerMinute,
    ZombieLoop,
    enter_zone,
    redistribution_due,
    threat_views,
)
from modules.action.types import (
    AddGoalAction,
    AttackAction,
    DropAction,
    Duration,
    MoveAction,
    NpcMoveAction,
    NpcStatusAction,
    SetFlagAction,
    SleepAction,
    StanceAction,
    TakeAction,
    TakeOffAction,
    UpdateInventoryAction,
    UpdateRelationshipAction,
    UseItemAction,
    WaitAction,
    WearAction,
)
from modules.body import BodyLocation, BodyPart
from modules.character.equipment import CharacterHoldableSlot
from modules.character.skills import SkillState
from modules.effect import StartOutbreakEffect
from modules.entity.item import ItemEntity
from modules.entity.object import DoorEntity, UnlockableEntityLockState
from modules.entity.zombie import AttackSide, ZombieEntity, ZombieState
from modules.item import ClothingItem, ConsumableItem
from modules.modifier import HPModifier
from modules.stats import CharacterStat
from modules.weather import WeatherSample
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


def zombie_game(zone_id: str = "zone_street") -> GameManager:
    """A game after the outbreak, with no zombies yet, the player standing in `zone_id`."""
    gm = GameManager()
    gm.player.current_location_id = zone_id
    gm.world.outbreak_started_at = 0
    gm.world.last_redistribution_minute = 0
    clear = WeatherSample(
        air_temperature=15,
        humidity=0.5,
        wind_intensity=0,
        wind_angle=0,
        cloud_intensity=0,
        precipitation_intensity=0,
        precipitation_is_snow=False,
        fog_intensity=0,
        daylight=1.0,
    )
    gm.climate.sample = lambda minutes: clear  # type: ignore[method-assign]
    return gm


def add_zombie(
    gm: GameManager,
    zone_id: str | None = None,
    *,
    gap: float,
    state: ZombieState = ZombieState.IDLE,
    facing_cos: float = 0.0,
    speed_mod: float = 0.6,
    lunger: bool = False,
    health: float = 2.0,
) -> ZombieEntity:
    number = gm.world.next_zombie_number
    gm.world.next_zombie_number += 1
    zombie = ZombieEntity(
        zombie_id=f"z{number}",
        zone_id=zone_id or gm.player.current_location_id,
        health=health,
        speed_type=2 if lunger else 3,
        speed_mod=speed_mod,
        lunger=lunger,
        strength=3,
        memory=800,
        sight=2,
        hearing=2,
        state=state,
        gap=gap,
        facing_cos=facing_cos,
        sound_gap=gap,
    )
    gm.world.zombies[zombie.zombie_id] = zombie
    return zombie


class ZombieMinuteLoopTests(unittest.TestCase):
    """Spec 09, The minute loop and Interruptions."""

    def spent(self, gm: GameManager, *actions) -> tuple[int, list[str]]:
        before = gm.narrative.minutes
        facts = simulate(gm, *actions, rng=random.Random(1))
        return gm.narrative.minutes - before, facts

    def test_nothing_happens_before_the_outbreak(self):
        gm = zombie_game()
        gm.world.outbreak_started_at = None
        add_zombie(gm, gap=3, state=ZombieState.ALERTED, facing_cos=1.0)
        minutes, facts = self.spent(gm, WaitAction(duration=Duration(minutes=30)))
        self.assertEqual(minutes, 30)
        self.assertFalse(any("zombie" in fact.casefold() for fact in facts))

    def test_a_wait_beside_a_zombie_facing_the_player_stops_in_the_first_minute(self):
        gm = zombie_game()
        control = codec.from_dict(codec.to_dict(gm))
        simulate(control, WaitAction(duration=Duration(minutes=30)))
        zombie = add_zombie(gm, gap=6, state=ZombieState.ALERTED, facing_cos=1.0)
        start = gm.player.stats.get(CharacterStat.HUNGER)
        minutes, facts = self.spent(gm, WaitAction(duration=Duration(minutes=30)))
        self.assertEqual(minutes, 1)
        self.assertEqual(zombie.state, ZombieState.CHASING)
        self.assertTrue(any("notices" in fact for fact in facts))
        one_minute = gm.player.stats.get(CharacterStat.HUNGER) - start
        thirty_minutes = control.player.stats.get(CharacterStat.HUNGER) - start
        self.assertAlmostEqual(one_minute, thirty_minutes / 30, delta=thirty_minutes / 300)

    def test_an_interruption_cancels_the_rest_of_the_plan(self):
        gm = zombie_game("zone_building")
        add_zombie(gm, gap=6, state=ZombieState.ALERTED, facing_cos=1.0)
        self.spent(gm, WaitAction(duration=Duration(minutes=30)), MoveAction(destination="out"))
        self.assertEqual(gm.player.current_location_id, "zone_building")

    def test_walking_away_from_a_shambler_opens_the_gap_and_it_forgets(self):
        gm = zombie_game("zone_building")
        shambler = add_zombie(gm, gap=10, state=ZombieState.CHASING, facing_cos=1.0, speed_mod=0.6)
        shambler.time_since_seen = 0
        minutes, _ = self.spent(gm, MoveAction(destination="zone_neighborhood"))
        self.assertEqual(minutes, 20)
        self.assertEqual(shambler.state, ZombieState.IDLE)
        self.assertGreater(shambler.gap, 20)

    def test_a_lunger_keeps_the_gap(self):
        gm = zombie_game("zone_building")
        lunger = add_zombie(
            gm, gap=10, state=ZombieState.CHASING, facing_cos=1.0, speed_mod=0.9, lunger=True
        )
        lunger.time_since_seen = 0
        self.spent(gm, MoveAction(destination="zone_neighborhood"))
        self.assertEqual(lunger.state, ZombieState.CHASING)
        self.assertGreater(lunger.gap, 14)
        self.assertLess(lunger.gap, 20)

    def test_footsteps_alert_an_idle_zombie_in_earshot(self):
        gm = zombie_game("zone_street")
        zombie = add_zombie(gm, gap=5, state=ZombieState.IDLE)
        self.spent(gm, MoveAction(destination="zone_neighborhood"))
        self.assertNotEqual(zombie.state, ZombieState.IDLE)

    def test_a_chaser_forgets_on_its_fifth_minute_unseen(self):
        gm = zombie_game()
        gm.climate.sample = lambda minutes: dataclasses.replace(  # type: ignore[method-assign]
            WeatherSample(15, 0.5, 0, 0, 0, 0, False, 0, daylight=0.0)
        )
        chaser = add_zombie(gm, gap=100, state=ZombieState.CHASING, facing_cos=1.0)
        chaser.time_since_seen = 0
        self.spent(gm, WaitAction(duration=Duration(minutes=4)))
        self.assertEqual(chaser.state, ZombieState.CHASING)
        self.spent(gm, WaitAction(duration=Duration(minutes=1)))
        self.assertEqual(chaser.state, ZombieState.IDLE)

    def test_a_sleeper_is_woken_in_a_panic_when_a_zombie_notices_them(self):
        gm = zombie_game("zone_building")
        gm.player.stats.set(CharacterStat.FATIGUE, 1)
        add_zombie(gm, gap=6, state=ZombieState.ALERTED, facing_cos=1.0)
        minutes, facts = self.spent(gm, SleepAction())
        self.assertLess(minutes, 10)
        self.assertIn("A zombie wakes Orton in a panic.", facts)
        self.assertFalse(gm.player.asleep)

    def test_the_population_is_redistributed_every_twelve_hours(self):
        gm = zombie_game("zone_home")
        self.spent(gm, WaitAction(duration=Duration(minutes=780)))
        self.assertEqual(gm.world.last_redistribution_minute, 720)
        zones = {z.zone_id for z in gm.world.zombies.values()}
        self.assertIn("zone_neighborhood", zones)
        self.assertNotIn("zone_home", zones)

    def test_sneaking_past_zombies_that_never_notice_trains_sneaking(self):
        gm = zombie_game("zone_street")
        add_zombie(gm, gap=30, state=ZombieState.IDLE)
        simulate(gm, StanceAction(sneaking=True))
        simulate(gm, MoveAction(destination="zone_neighborhood"), rng=random.Random(2))
        self.assertGreater(gm.player.skills["sneaking"].xp, 0)

    def test_a_chaser_left_behind_stays_in_the_zone_the_player_left(self):
        gm = zombie_game("zone_street")
        shambler = add_zombie(gm, gap=15, state=ZombieState.CHASING, speed_mod=0.6)
        shambler.time_since_seen = 0
        self.spent(gm, MoveAction(destination="zone_building"))
        self.assertEqual(gm.player.current_location_id, "zone_building")
        self.assertGreater(shambler.gap, 20)
        self.assertEqual(shambler.zone_id, "zone_street")

    def test_a_chaser_keeping_pace_follows_the_player_into_the_new_zone(self):
        gm = zombie_game("zone_street")
        lunger = add_zombie(gm, gap=10, state=ZombieState.CHASING, speed_mod=0.9, lunger=True)
        lunger.time_since_seen = 0
        self.spent(gm, MoveAction(destination="zone_building"))
        self.assertLessEqual(lunger.gap, 20)
        self.assertEqual(lunger.zone_id, "zone_building")

    def test_a_zombie_that_reaches_the_player_attacks_and_stops_the_action(self):
        gm = zombie_game()
        zombie = add_zombie(gm, gap=1, state=ZombieState.CHASING, facing_cos=1.0)
        zombie.time_since_seen = 0
        minutes, facts = self.spent(gm, WaitAction(duration=Duration(minutes=30)))
        self.assertEqual(minutes, 1)
        self.assertEqual(zombie.state, ZombieState.ATTACKING)
        self.assertEqual(zombie.side.value, "front")  # type: ignore[union-attr]
        self.assertTrue(any("A zombie" in fact or "shoves" in fact for fact in facts))

    def test_three_zombies_on_the_player_drag_them_down(self):
        facts: list[str] = []
        gm = zombie_game()
        for seed in range(30):
            gm = zombie_game()
            for _ in range(3):
                zombie = add_zombie(gm, gap=1, state=ZombieState.CHASING, facing_cos=1.0)
                zombie.time_since_seen = 0
            facts = simulate(gm, WaitAction(duration=Duration(minutes=5)), rng=random.Random(seed))
            if gm.narrative.game_over:
                break
        self.assertTrue(gm.narrative.game_over)
        self.assertIn("dragged down by the dead", gm.narrative.death_cause)
        self.assertTrue(any("has died" in fact for fact in facts))

    def test_an_attack_wakes_a_sleeper(self):
        gm = zombie_game("zone_building")
        gm.player.stats.set(CharacterStat.FATIGUE, 1)
        zombie = add_zombie(gm, gap=1, state=ZombieState.CHASING, facing_cos=1.0)
        zombie.time_since_seen = 0
        minutes, facts = self.spent(gm, SleepAction())
        self.assertEqual(minutes, 1)
        self.assertFalse(gm.player.asleep)
        self.assertIn("A zombie wakes Orton in a panic.", facts)

    def test_minutes_with_an_attacker_count_as_exercise(self):
        gm = zombie_game()
        zombie = add_zombie(gm, gap=1, state=ZombieState.CHASING, facing_cos=1.0)
        zombie.time_since_seen = 0
        before = gm.player.stats.get(CharacterStat.ENDURANCE)
        simulate(gm, WaitAction(duration=Duration(minutes=30)), rng=random.Random(3))
        self.assertLess(gm.player.stats.get(CharacterStat.ENDURANCE), before)

    def test_a_wound_lowers_health(self):
        lost = 0
        for seed in range(40):
            gm = zombie_game()
            zombie = add_zombie(gm, gap=1, state=ZombieState.CHASING, facing_cos=1.0)
            zombie.time_since_seen = 0
            simulate(gm, WaitAction(duration=Duration(minutes=1)), rng=random.Random(seed))
            lost += gm.player.max_hit_points - gm.player.hit_points
        self.assertGreater(lost, 0)


def put_on_armour(gm: GameManager) -> None:
    """Clothing that stops every wound, so a fight's outcome doesn't depend on the dice."""
    item = ClothingItem(
        id="item_test_armour",
        name="Test armour",
        description="",
        max_hit_points=100,
        tags=[],
        body_location=BodyLocation.JACKET,
        covers=frozenset(BodyPart),
        insulation=0.5,
        wind_resistance=0.5,
        water_resistance=0.5,
        weight=1.0,
        scratch_defense=100,
        bite_defense=100,
    )
    gm.player.worn[BodyLocation.JACKET] = ItemEntity(item=item)


class ZombieAttackActionTests(unittest.TestCase):
    """Spec 09, Zombies going down: ATTACK on a zombie, approach minutes and removal."""

    def attack(self, gm: GameManager, target: str, seed: int = 1) -> tuple[int, list[str]]:
        before = gm.narrative.minutes
        facts = simulate(gm, AttackAction(target_name=target), rng=random.Random(seed))
        return gm.narrative.minutes - before, facts

    def test_attacking_a_zombie_six_tiles_away_spends_the_approach_then_the_swing(self):
        gm = zombie_game()
        put_on_armour(gm)
        zombie = add_zombie(gm, gap=6, health=3.0)
        minutes, facts = self.attack(gm, zombie.zombie_id)
        self.assertEqual(minutes, 3)
        self.assertLess(zombie.health, 3.0)
        self.assertFalse(any(fact.startswith("Refused") for fact in facts))

    def test_a_zombie_next_to_the_player_costs_only_the_swing(self):
        gm = zombie_game()
        zombie = add_zombie(gm, gap=1, health=3.0)
        minutes, _ = self.attack(gm, zombie.zombie_id)
        self.assertEqual(minutes, 1)

    def test_the_word_zombie_means_the_nearest_one(self):
        gm = zombie_game()
        put_on_armour(gm)
        far = add_zombie(gm, gap=12, health=3.0, state=ZombieState.CHASING)
        far.time_since_seen = 0
        near = add_zombie(gm, gap=2, health=3.0)
        self.attack(gm, "zombie")
        self.assertLess(near.health, 3.0)
        self.assertEqual(far.health, 3.0)

    def test_a_zombie_at_zero_health_is_removed_and_stays_gone(self):
        gm = zombie_game()
        zombie = add_zombie(gm, gap=1, health=0.4)
        _, facts = self.attack(gm, zombie.zombie_id)
        self.assertNotIn(zombie.zombie_id, gm.world.zombies)
        self.assertTrue(any("down" in fact for fact in facts))
        simulate(gm, WaitAction(duration=Duration(minutes=60)))
        self.assertNotIn(zombie.zombie_id, gm.world.zombies)

    def test_a_zombie_that_is_not_here_is_refused(self):
        gm = zombie_game()
        add_zombie(gm, "zone_building", gap=3)
        _, facts = self.attack(gm, "z1")
        self.assertTrue(facts[0].startswith("Refused"))
        _, facts = self.attack(gm, "zombie")
        self.assertTrue(facts[0].startswith("Refused"))

    def test_attacking_wakes_an_idle_zombie_and_it_hits_back(self):
        gm = zombie_game()
        zombie = add_zombie(gm, gap=1, health=3.0)
        self.attack(gm, zombie.zombie_id)
        self.assertEqual(zombie.state, ZombieState.ATTACKING)

    def test_a_fight_is_only_interrupted_by_a_wound_or_a_drag_down(self):
        gm = zombie_game()
        zombie = add_zombie(gm, gap=1, health=3.0)
        zombie.state = ZombieState.ATTACKING
        zombie.time_since_seen = 0
        zombie.side = AttackSide.FRONT
        gm.player.skills["fitness"] = SkillState(level=10, xp=0)
        gm.player.skills["strength"] = SkillState(level=10, xp=0)
        self.assertFalse(gm.narrative.game_over)
        minutes, _ = self.attack(gm, zombie.zombie_id)
        self.assertEqual(minutes, 1)

    def test_a_zombie_coming_into_view_is_counted_once_for_the_stats(self):
        gm = zombie_game()
        add_zombie(gm, gap=30, state=ZombieState.ALERTED, facing_cos=1.0)
        counts: list[int] = []

        class Recorder:
            def apply(self, stats, hours, ctx):  # noqa: ANN001
                counts.append(ctx.new_zombies_seen)

        core = SimulationCore(gm, rng=random.Random(1))
        core.stats_engine.register(Recorder())
        core.resolve([WaitAction(duration=Duration(minutes=20))])
        self.assertEqual(counts, [1])


class StartOutbreakTests(unittest.TestCase):
    """Spec 09, The outbreak: the story effect that starts it."""

    def test_the_effect_stamps_the_minute_and_fills_the_zones(self):
        gm = GameManager()
        gm.advance_clock(3 * 1440 - 480 + 360)
        SimulationCore(gm, rng=random.Random(1)).apply_story_effect(StartOutbreakEffect())
        self.assertEqual(gm.world.outbreak_started_at, gm.narrative.minutes)
        self.assertEqual(gm.world.last_redistribution_minute, gm.narrative.minutes)
        zones = [zombie.zone_id for zombie in gm.world.zombies.values()]
        self.assertGreater(len(zones), 20)
        self.assertNotIn("zone_home", zones)

    def test_zombies_in_the_players_zone_come_into_view_on_the_next_minute(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_street"
        core = SimulationCore(gm, rng=random.Random(1))
        core.apply_story_effect(StartOutbreakEffect())
        counts: list[int] = []

        class Recorder:
            def apply(self, stats, hours, ctx):  # noqa: ANN001
                counts.append(ctx.new_zombies_seen)

        core.stats_engine.register(Recorder())
        core.resolve([WaitAction(duration=Duration(minutes=1))])
        self.assertGreaterEqual(counts[0], 1)


class ZombieFollowUpTests(unittest.TestCase):
    """Spec 09: Hearing, Movement, Population and What the narrator and the player see."""

    def run_wait(self, gm: GameManager, minutes: int) -> None:
        simulate(gm, WaitAction(duration=Duration(minutes=minutes)), rng=random.Random(1))

    def test_redistribution_is_due_at_twelve_hours_and_not_before(self):
        gm = zombie_game()
        self.assertFalse(redistribution_due(gm.world, 719))
        self.assertTrue(redistribution_due(gm.world, 720))

    def test_a_chaser_in_another_zone_stops_at_a_closed_door(self):
        gm = zombie_game("zone_street")
        gm.world.locations["zone_neighborhood"].entities.append(
            DoorEntity(leads_to="zone_street", state=UnlockableEntityLockState.LOCKED)
        )
        chaser = add_zombie(
            gm, "zone_neighborhood", gap=60, state=ZombieState.CHASING, facing_cos=1.0
        )
        chaser.time_since_seen = 0
        self.run_wait(gm, 1)
        self.assertEqual(chaser.state, ZombieState.IDLE)
        self.assertEqual(chaser.zone_id, "zone_neighborhood")

    def test_a_chaser_in_another_zone_closes_in_when_the_way_is_open(self):
        gm = zombie_game("zone_street")
        chaser = add_zombie(
            gm, "zone_neighborhood", gap=60, state=ZombieState.CHASING, facing_cos=1.0
        )
        chaser.time_since_seen = 0
        self.run_wait(gm, 1)
        self.assertEqual(chaser.state, ZombieState.CHASING)
        self.assertLess(chaser.gap, 60)

    def test_a_zombie_alerted_in_the_players_zone_stays_when_the_player_leaves(self):
        gm = zombie_game("zone_street")
        zombie = add_zombie(gm, gap=30, state=ZombieState.ALERTED, facing_cos=-1.0)
        zombie.sound_gap = 12
        enter_zone(gm.world, "zone_neighborhood", "zone_street", random.Random(1))
        gm.player.current_location_id = "zone_neighborhood"
        self.run_wait(gm, 1)
        self.assertEqual(zombie.zone_id, "zone_street")
        self.assertEqual(zombie.state, ZombieState.IDLE)
        self.assertEqual(zombie.sound_gap, 0)

    def test_a_zombie_alerted_in_the_players_zone_stays_when_the_player_walks_away(self):
        gm = zombie_game("zone_street")
        zombie = add_zombie(gm, gap=60, state=ZombieState.ALERTED, facing_cos=-1.0)
        zombie.sound_gap = 12
        simulate(gm, MoveAction(destination="zone_neighborhood"), rng=random.Random(1))
        self.assertEqual(gm.player.current_location_id, "zone_neighborhood")
        self.assertEqual(zombie.zone_id, "zone_street")

    def test_a_lunger_still_reads_fast_after_a_long_time_unseen(self):
        gm = zombie_game("zone_street")
        lunger = add_zombie(gm, gap=5, lunger=True, state=ZombieState.IDLE)
        lunger.has_chased = True
        lunger.time_since_seen = 600 * 180
        words = {view.zombie_id: view.state_word for view in threat_views(gm)}
        self.assertEqual(words[lunger.zombie_id], "coming at you fast")

    def test_a_zombie_alerted_from_another_zone_still_crosses_in(self):
        gm = zombie_game("zone_street")
        zombie = add_zombie(
            gm, "zone_neighborhood", gap=0, state=ZombieState.ALERTED, facing_cos=-1.0
        )
        zombie.sound_gap = 30
        self.run_wait(gm, 5)
        self.assertEqual(zombie.zone_id, "zone_street")

    def test_a_lunger_reads_fast_once_it_has_chased(self):
        gm = zombie_game("zone_street")
        fresh = add_zombie(gm, gap=5, lunger=True, state=ZombieState.ALERTED)
        chased = add_zombie(gm, gap=5, lunger=True, state=ZombieState.IDLE)
        chased.has_chased = True
        words = {view.zombie_id: view.state_word for view in threat_views(gm)}
        self.assertNotIn("fast", words[fresh.zombie_id])
        self.assertEqual(words[chased.zombie_id], "coming at you fast")

    def test_noticing_the_player_sets_has_chased(self):
        gm = zombie_game()
        zombie = add_zombie(gm, gap=6, state=ZombieState.ALERTED, facing_cos=1.0)
        self.run_wait(gm, 1)
        self.assertEqual(zombie.state, ZombieState.CHASING)
        self.assertTrue(zombie.has_chased)

    def loop(self, gm: GameManager) -> ZombieLoop:
        return ZombieLoop(gm, random.Random(1), SkillEngine())

    def test_being_hit_sets_has_chased(self):
        gm = zombie_game()
        zombie = add_zombie(gm, gap=1, health=3.0, state=ZombieState.ATTACKING)
        self.loop(gm)._swing(PlayerMinute(swing_target=zombie.zombie_id), MinuteReport())
        self.assertLess(zombie.health, 3.0)
        self.assertTrue(zombie.has_chased)

    def test_following_a_sound_up_to_the_player_sets_has_chased(self):
        gm = zombie_game()
        zombie = add_zombie(gm, gap=1.5, state=ZombieState.ALERTED)
        zombie.sound_gap = 30
        self.loop(gm)._follow_sound(zombie, 40)
        self.assertEqual(zombie.state, ZombieState.CHASING)
        self.assertTrue(zombie.has_chased)

    def test_reaching_attack_range_sets_has_chased(self):
        gm = zombie_game()
        zombie = add_zombie(gm, gap=1, state=ZombieState.CHASING)
        self.loop(gm)._report_reach(PlayerMinute())
        self.assertEqual(zombie.state, ZombieState.ATTACKING)
        self.assertTrue(zombie.has_chased)

    def test_a_lunger_that_chased_the_player_still_reads_fast_after_it_loses_them(self):
        gm = zombie_game()
        lunger = add_zombie(gm, gap=6, lunger=True, state=ZombieState.ALERTED, facing_cos=1.0)
        self.run_wait(gm, 1)
        self.assertEqual(lunger.state, ZombieState.CHASING)
        lunger.state = ZombieState.IDLE
        lunger.time_since_seen = 600 * 180
        words = {view.zombie_id: view.state_word for view in threat_views(gm)}
        self.assertEqual(words[lunger.zombie_id], "coming at you fast")

    def test_a_zombie_the_player_cannot_perceive_is_not_a_target(self):
        gm = zombie_game("zone_street")
        far = add_zombie(gm, gap=39, health=3.0)
        validator = ActionValidator(gm)
        self.assertIsInstance(validator.validate(AttackAction(target_name=far.zombie_id)), Rejected)
        self.assertIsInstance(validator.validate(AttackAction(target_name="zombie")), Rejected)
