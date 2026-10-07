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
    BandageAction,
    CloseAction,
    DropAction,
    Duration,
    MoveAction,
    OpenAction,
    SearchAction,
    ShoutAction,
    SleepAction,
    StanceAction,
    TakeAction,
    TakeOffAction,
    UseItemAction,
    WaitAction,
    WearAction,
)
from modules.body import BodyLocation, BodyPart
from modules.character.equipment import CharacterHoldableSlot
from modules.character.skills import SkillState
from modules.entity.barrier import BarrierEntity, BarrierKind
from modules.entity.corpse import CorpseEntity
from modules.entity.item import ItemEntity
from modules.entity.zombie import AttackSide, ZombieEntity, ZombieState
from modules.item import ClothingItem
from modules.pace import Pace
from modules.stats import CharacterStat
from modules.story import StartOutbreak
from modules.weather import WeatherSample
from tests.support import make_dying, set_health, simulate


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
        set_health(gm.player, 50)
        gm.player.inventory.clear()  # drop the starting apartment key
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_canned_beans"]))
        facts = simulate(gm, UseItemAction(item_name="Canned Beans"))
        self.assertLess(gm.player.health, 60)
        self.assertEqual(gm.player.inventory, [])
        self.assertIn("succeeded", facts[0])

    def test_using_painkillers_spends_a_pill_and_keeps_the_bottle(self):
        gm = GameManager()
        gm.player.inventory.clear()
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_painkillers"]))
        simulate(gm, UseItemAction(item_name="Painkillers"))
        self.assertEqual(len(gm.player.inventory), 1)
        self.assertEqual(gm.player.inventory[0].uses, 9)

    def test_eating_refills_hunger_and_thirst(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.HUNGER, 0.5)
        gm.player.stats.set(CharacterStat.THIRST, 0.5)
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_granola_bar"]))
        simulate(gm, UseItemAction(item_name="Granola Bar"))
        self.assertAlmostEqual(gm.player.stats.get(CharacterStat.HUNGER), 0.352, delta=0.01)
        self.assertGreater(gm.player.stats.get(CharacterStat.THIRST), 0.45)
        self.assertLess(gm.player.stats.get(CharacterStat.THIRST), 0.55)


class WorldStateResolutionTests(unittest.TestCase):
    def test_add_goal(self):
        gm = GameManager()
        simulate(gm, AddGoalAction(horizon="short_term", goal_text="Find a weapon"))
        self.assertIn("Find a weapon", gm.narrative.goals["short_term"])


class PlayerDeathResolutionTests(unittest.TestCase):
    """SimulationCore._check_player_death is the only producer of
    NarrativeState.game_over/death_cause -- player health only moves through
    the body, so the LLM can never kill Orton by declaration."""

    def test_a_dying_player_ends_the_game(self):
        gm = GameManager()
        make_dying(gm.player)
        facts = simulate(gm, WaitAction(duration=Duration(minutes=10)))
        self.assertTrue(gm.narrative.game_over)
        self.assertIn("Orton", gm.narrative.death_cause)
        self.assertTrue(any("Orton has died" in fact for fact in facts))
        self.assertEqual(gm.player.hit_points, 0)

    def test_actions_after_death_are_refused(self):
        gm = GameManager()
        make_dying(gm.player)
        facts = simulate(
            gm,
            WaitAction(duration=Duration(minutes=10)),
            AddGoalAction(horizon="short_term", goal_text="Survive"),
        )
        self.assertTrue(any("Orton has died" in fact for fact in facts))
        self.assertTrue(any(fact.startswith("Refused:") for fact in facts))
        self.assertNotIn("Survive", gm.narrative.goals["short_term"])

    def test_surviving_hp_does_not_end_the_game(self):
        gm = GameManager()
        set_health(gm.player, 50)
        gm.player.inventory.clear()  # drop the starting apartment key
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_canned_beans"]))
        facts = simulate(gm, UseItemAction(item_name="Canned Beans"))
        self.assertFalse(gm.narrative.game_over)
        self.assertEqual(gm.narrative.death_cause, "")
        self.assertNotIn("Orton has died", facts[0])


class RefusalWordingTests(unittest.TestCase):
    """Spec 10, Failures: a refusal reads as a sentence, never a class name."""

    def test_a_refused_action_names_what_orton_could_not_do_and_why(self):
        facts = simulate(GameManager(), BandageAction(part_name="left hand"))
        self.assertEqual(len(facts), 1)
        self.assertTrue(facts[0].startswith("Refused: Orton can't bandage the left hand: "), facts)
        self.assertNotIn("Action", facts[0])
        self.assertNotIn(" -- ", facts[0])


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

    def test_eating_says_nothing_about_health(self):
        set_health(self.gm.player, 50)
        self.gm.player.inventory.append(ItemEntity(item=ITEMS["item_canned_beans"]))
        fact = self._first_fact(UseItemAction(item_name="Canned Beans"))
        self.assertTrue(fact.startswith("Use Canned Beans: succeeded."), fact)
        self.assertNotIn("hurt", fact)
        self.assertNotIn("injured", fact)


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


class TakeClothingFactTests(unittest.TestCase):
    """Spec 05, Actions: taking a garment carries it; only WEAR puts it on."""

    def setUp(self):
        self.gm = GameManager()
        self.gm.player.inventory.clear()

    def _take(self, item_id: str) -> list[str]:
        self.gm.current_location.entities.append(ItemEntity(item=ITEMS[item_id]))
        return SimulationCore(self.gm).resolve([TakeAction(item_name=ITEMS[item_id].name)])

    def test_the_fact_says_a_taken_garment_is_carried_not_worn(self):
        facts = self._take("item_black_jacket")
        self.assertIn(
            "Take Black jacket: succeeded. Orton carries it; he is not wearing it.", facts
        )

    def test_other_items_keep_the_plain_fact(self):
        self.assertIn("Take Water Bottle: succeeded.", self._take("item_water_bottle"))


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
            self.assertEqual(gm.player.body[part].stiffness, 2.5)


class DeathBeforeTicksTests(unittest.TestCase):
    """Spec 08, Where XP comes from: a lethal chunk is judged before the ticks run."""

    def test_a_starvation_death_in_a_levelling_chunk_ends_the_game(self):
        gm = GameManager()
        gm.narrative.minutes = 2405
        player = gm.player
        make_dying(player)
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

    def test_a_crowbar_hit_on_an_npc_trains_fitness_and_strength_only(self):
        gm = _crowbar_game()
        simulate(gm, AttackAction(target_name="Emma"))
        skills = gm.player.skills
        self.assertAlmostEqual(skills["fitness"].xp, 37501)
        self.assertAlmostEqual(skills["strength"].xp, 37501)
        self.assertEqual(skills["long_blunt"].xp, 0)

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
    """A game after the outbreak, with no zombies yet, the player standing in `zone_id`.

    Every door stands open, so the zombie rules of spec 09 are tested without them.
    """
    gm = GameManager()
    for barrier in gm.world.barriers.values():
        barrier.open = True
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

    def test_a_wait_is_interrupted_when_a_fake_dead_body_rises(self):
        """Spec 14, Fake-dead corpses."""
        gm = zombie_game()
        gm.world.corpses["c1"] = CorpseEntity(
            corpse_id="c1",
            zone_id="zone_street",
            gap=3.0,
            female=False,
            outfit="generic01",
            died_at=-100,
            rot_at_death=1,
            fake_dead=True,
        )
        minutes, facts = self.spent(gm, WaitAction(duration=Duration(minutes=30)))
        self.assertEqual(minutes, 1)
        self.assertIn("A body on the ground lurches to its feet.", facts)
        self.assertEqual(list(gm.world.zombies), ["z1"])
        self.assertEqual(gm.world.corpses, {})

    def test_a_plan_of_search_then_take_from_runs(self):
        """Spec 14, Searching and looting."""
        gm = zombie_game()
        gm.world.corpses["c1"] = CorpseEntity(
            corpse_id="c1",
            zone_id="zone_street",
            gap=1.0,
            female=False,
            outfit="generic01",
            died_at=0,
            rot_at_death=1,
            contents=[ItemEntity(item=ITEMS["item_jacket_police"])],
        )
        minutes, facts = self.spent(
            gm, SearchAction(target_name="c1"), TakeAction(item_name="jacket", from_name="c1")
        )
        self.assertEqual(minutes, 2)
        self.assertIn("Orton goes through c1: a police jacket.", facts)
        self.assertEqual(gm.player.inventory[-1].item.id, "item_jacket_police")

    def test_an_attack_during_the_search_cancels_the_rest_but_not_the_search(self):
        """Spec 14, Interruptions."""
        gm = zombie_game()
        gm.world.corpses["c1"] = CorpseEntity(
            corpse_id="c1",
            zone_id="zone_street",
            gap=1.0,
            female=False,
            outfit="generic01",
            died_at=0,
            rot_at_death=1,
            contents=[ItemEntity(item=ITEMS["item_jacket_police"])],
        )
        zombie = add_zombie(gm, gap=1, state=ZombieState.ATTACKING, facing_cos=1.0)
        zombie.time_since_seen = 0
        zombie.side = AttackSide.FRONT
        _, facts = self.spent(
            gm, SearchAction(target_name="c1"), TakeAction(item_name="jacket", from_name="c1")
        )
        self.assertTrue(gm.world.corpses["c1"].searched)
        self.assertIn("Orton goes through c1: a police jacket.", facts)
        self.assertTrue(any("never gets to: take the jacket from c1" in fact for fact in facts))
        self.assertEqual(len(gm.world.corpses["c1"].contents), 1)

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
        if gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND] is None:
            crowbar = ItemEntity(item=ITEMS["item_crowbar"])
            gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND] = crowbar
            gm.player.equipment[CharacterHoldableSlot.LEFT_HAND] = crowbar
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
        zombie = add_zombie(gm, gap=1, health=0.05)
        _, facts = self.attack(gm, zombie.zombie_id)
        self.assertNotIn(zombie.zombie_id, gm.world.zombies)
        self.assertTrue(any("goes still" in fact for fact in facts))
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
        SimulationCore(gm, rng=random.Random(1)).apply_story_effect(StartOutbreak())
        self.assertEqual(gm.world.outbreak_started_at, gm.narrative.minutes)
        self.assertEqual(gm.world.last_redistribution_minute, gm.narrative.minutes)
        zones = [zombie.zone_id for zombie in gm.world.zombies.values()]
        self.assertGreater(len(zones), 20)
        self.assertNotIn("zone_home", zones)

    def test_zombies_in_the_players_zone_come_into_view_on_the_next_minute(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_street"
        core = SimulationCore(gm, rng=random.Random(1))
        core.apply_story_effect(StartOutbreak())
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

    def test_a_chaser_in_another_zone_stops_at_a_closed_door_and_pounds_on_it(self):
        gm = zombie_game("zone_street")
        gm.world.barriers["gate"] = BarrierEntity(
            barrier_id="gate",
            kind=BarrierKind.DOOR,
            zones=("zone_street", "zone_neighborhood"),
            inside_zone="zone_street",
            name="gate",
            health=500,
            max_health=500,
        )
        chaser = add_zombie(
            gm, "zone_neighborhood", gap=60, state=ZombieState.CHASING, facing_cos=1.0
        )
        chaser.time_since_seen = 0
        chaser.memory = 10**6
        self.run_wait(gm, 1)
        self.assertEqual(chaser.state, ZombieState.CHASING)
        self.run_wait(gm, 30)
        self.assertEqual(chaser.state, ZombieState.THUMPING)
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
        gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND] = ItemEntity(
            item=ITEMS["item_crowbar"]
        )
        zombie = add_zombie(gm, gap=1, health=3.0, state=ZombieState.ATTACKING)
        self.loop(gm)._swing(0, PlayerMinute(swing_target=zombie.zombie_id), MinuteReport())
        self.assertLess(zombie.health, 3.0)
        self.assertTrue(zombie.has_chased)

    def test_following_a_sound_up_to_the_player_sets_has_chased(self):
        gm = zombie_game()
        zombie = add_zombie(gm, gap=1.5, state=ZombieState.ALERTED)
        zombie.sound_gap = 30
        self.loop(gm)._follow_sound(zombie, 40, PlayerMinute(), MinuteReport())
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


class PlanTests(unittest.TestCase):
    """Spec 10, Plans."""

    def test_a_sixth_action_is_refused(self):
        gm = GameManager()
        goals = [AddGoalAction(horizon="short_term", goal_text=f"Goal {n}") for n in range(7)]
        facts = simulate(gm, *goals)
        self.assertEqual(len(gm.narrative.goals["short_term"]), 5)
        refusals = [fact for fact in facts if fact.startswith("Refused:")]
        self.assertEqual(refusals, ["Refused: Too much at once; Orton does the first five things."])

    def test_exactly_five_actions_all_resolve(self):
        gm = GameManager()
        goals = [AddGoalAction(horizon="short_term", goal_text=f"Goal {n}") for n in range(5)]
        facts = simulate(gm, *goals)
        self.assertEqual(len(gm.narrative.goals["short_term"]), 5)
        self.assertEqual([fact for fact in facts if fact.startswith("Refused:")], [])

    def test_a_six_action_plan_resolves_the_first_five_and_refuses_the_sixth(self):
        gm = GameManager()
        goals = [AddGoalAction(horizon="short_term", goal_text=f"Goal {n}") for n in range(6)]
        facts = simulate(gm, *goals)
        self.assertEqual(gm.narrative.goals["short_term"], [f"Goal {n}" for n in range(5)])
        self.assertEqual(
            [fact for fact in facts if fact.startswith("Refused:")],
            ["Refused: Too much at once; Orton does the first five things."],
        )

    def test_a_refused_action_does_not_stop_the_plan(self):
        gm = GameManager()
        facts = simulate(
            gm,
            TakeAction(item_name="Unicorn"),
            AddGoalAction(horizon="short_term", goal_text="Find water"),
        )
        self.assertTrue(facts[0].startswith("Refused:"))
        self.assertEqual(gm.narrative.goals["short_term"], ["Find water"])

    def test_an_interrupted_action_cancels_the_rest_with_one_fact(self):
        gm = zombie_game("zone_building")
        add_zombie(gm, gap=6, state=ZombieState.ALERTED, facing_cos=1.0)
        facts = simulate(
            gm,
            WaitAction(duration=Duration(minutes=30)),
            TakeAction(item_name="knife"),
            DropAction(item_name="bag"),
            rng=random.Random(1),
        )
        self.assertEqual(
            [fact for fact in facts if "never gets to" in fact],
            ["Orton never gets to: take the knife, drop the bag."],
        )
        self.assertEqual(sum("Refused" in fact for fact in facts), 0)

    def test_an_interruption_in_the_last_action_cancels_nothing(self):
        gm = zombie_game("zone_building")
        add_zombie(gm, gap=6, state=ZombieState.ALERTED, facing_cos=1.0)
        facts = simulate(gm, WaitAction(duration=Duration(minutes=30)), rng=random.Random(1))
        self.assertFalse(any("never gets to" in fact for fact in facts))

    def test_a_none_turn_costs_one_minute(self):
        gm = GameManager()
        facts = simulate(gm)
        self.assertEqual(gm.narrative.minutes, 1)
        self.assertEqual(facts, ["About 1 minute passes."])

    def test_a_turn_of_only_refused_lines_costs_nothing(self):
        gm = GameManager()
        facts = SimulationCore(gm).resolve([], refused=2)
        self.assertEqual(gm.narrative.minutes, 0)
        self.assertEqual(facts, [])

    def test_a_turn_of_only_refused_actions_costs_nothing(self):
        gm = GameManager()
        simulate(gm, TakeAction(item_name="Unicorn"), TakeAction(item_name="Dragon"))
        self.assertEqual(gm.narrative.minutes, 0)


class ShoutTests(unittest.TestCase):
    """Spec 10, SHOUT."""

    def sounds_after(self, gm: GameManager, *actions) -> list[tuple[float, float]]:
        core = SimulationCore(gm, rng=random.Random(1))
        heard: list[tuple[float, float]] = []
        real = core._loop.run_minute

        def spy(now, minute, extra_sounds=()):
            heard.extend((sound.radius, sound.volume) for sound in extra_sounds)
            return real(now, minute, extra_sounds)

        core._loop.run_minute = spy  # type: ignore[method-assign]
        core.resolve(list(actions))
        return heard

    def test_a_shout_is_a_sound_of_radius_30_and_volume_30(self):
        gm = zombie_game("zone_street")
        self.assertEqual(self.sounds_after(gm, ShoutAction()), [(30, 30)])

    def test_a_sneaking_shout_is_radius_6_and_volume_6(self):
        gm = zombie_game("zone_street")
        gm.player.sneaking = True
        self.assertEqual(self.sounds_after(gm, ShoutAction()), [(6, 6)])

    def test_a_shout_alone_costs_the_one_minute_floor(self):
        gm = zombie_game("zone_street")
        simulate(gm, ShoutAction(), rng=random.Random(1))
        self.assertEqual(gm.narrative.minutes, 1)

    def test_a_shout_beside_a_timed_action_adds_no_time_of_its_own(self):
        gm = zombie_game("zone_street")
        simulate(gm, ShoutAction(), WaitAction(duration=Duration(minutes=10)), rng=random.Random(1))
        self.assertEqual(gm.narrative.minutes, 10)

    def test_a_shout_after_a_timed_action_adds_no_time_of_its_own(self):
        gm = zombie_game("zone_street")
        simulate(gm, WaitAction(duration=Duration(minutes=10)), ShoutAction(), rng=random.Random(1))
        self.assertEqual(gm.narrative.minutes, 10)

    def test_a_shout_wakes_an_idle_zombie_in_range(self):
        gm = zombie_game("zone_street")
        zombie = add_zombie(gm, gap=25, state=ZombieState.IDLE)
        simulate(gm, ShoutAction(), rng=random.Random(1))
        self.assertNotEqual(zombie.state, ZombieState.IDLE)


class WhatPainDoesTests(unittest.TestCase):
    """Spec 12, What pain does."""

    def refusal(self, gm: GameManager) -> str | None:
        result = ActionValidator(gm).validate(SleepAction(duration=Duration(minutes=60)))
        return result.reason if isinstance(result, Rejected) else None

    def test_sleep_is_refused_at_panic_level_one(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.PANIC, 10)
        self.assertEqual(self.refusal(gm), "Orton is too panicked to sleep.")

    def test_sleep_is_refused_at_pain_two_with_fatigue_half(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.PAIN, 25)
        gm.player.stats.set(CharacterStat.FATIGUE, 0.5)
        self.assertEqual(self.refusal(gm), "Orton is in too much pain to sleep.")

    def test_sleep_is_allowed_at_pain_two_with_fatigue_point_nine(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.PAIN, 25)
        gm.player.stats.set(CharacterStat.FATIGUE, 0.9)
        self.assertIsNone(self.refusal(gm))

    def test_sleep_is_allowed_at_pain_level_one(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.PAIN, 15)
        gm.player.stats.set(CharacterStat.FATIGUE, 0.5)
        self.assertIsNone(self.refusal(gm))

    def minutes_for(self, gm: GameManager, action) -> int:
        before = gm.narrative.minutes
        simulate(gm, action)
        return gm.narrative.minutes - before

    def test_an_unhappy_player_takes_longer_over_a_fixed_cost_action(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.UNHAPPINESS, 50)
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_painkillers"]))
        self.assertEqual(self.minutes_for(gm, DropAction(item_name="Painkillers")), 2)

    def test_a_calm_player_takes_one_minute(self):
        gm = GameManager()
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_painkillers"]))
        self.assertEqual(self.minutes_for(gm, DropAction(item_name="Painkillers")), 1)

    def test_hand_pain_slows_a_bandage(self):
        gm = GameManager()
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_bandage"]))
        state = gm.player.body[BodyPart.HAND_L]
        state.scratch_time = 5.0
        state.extra_pain = 400.0
        from modules.action.types import BandageAction

        self.assertEqual(self.minutes_for(gm, BandageAction(part_name="left hand")), 2)

    def test_a_wait_is_not_slowed(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.UNHAPPINESS, 50)
        self.assertEqual(self.minutes_for(gm, WaitAction(duration=Duration(minutes=10))), 10)

    def test_equip_and_unequip_are_slowed_too(self):
        from modules.action.types import EquipAction, UnequipAction

        gm = GameManager()
        gm.player.stats.set(CharacterStat.UNHAPPINESS, 50)
        gm.player.inventory.append(ItemEntity(item=ITEMS["item_kitchen_knife"]))
        self.assertEqual(self.minutes_for(gm, EquipAction(item_name="Kitchen Knife")), 2)
        self.assertEqual(self.minutes_for(gm, UnequipAction(item_name="Kitchen Knife")), 2)


class LimpWiringTests(unittest.TestCase):
    """Spec 12, The limp."""

    def hop_minutes(self, **wound) -> int:
        gm = GameManager()
        for name, value in wound.items():
            setattr(gm.player.body[BodyPart.LOWERLEG_L], name, value)
        before = gm.narrative.minutes
        simulate(gm, MoveAction(destination="out"))
        return gm.narrative.minutes - before

    def test_a_whole_player_walks_a_hop_in_ten_minutes(self):
        self.assertEqual(self.hop_minutes(), 10)

    def test_a_shin_laceration_stretches_the_hop_to_twelve(self):
        self.assertEqual(self.hop_minutes(cut_time=15.0), 12)

    def test_a_bitten_shin_stretches_it_to_forty(self):
        self.assertEqual(self.hop_minutes(bite_time=65.0), 40)

    def test_a_limp_slows_the_pace_a_chased_player_opens_the_gap_at(self):
        def gap_after(limping: bool) -> float:
            gm = zombie_game()
            if limping:
                gm.player.body[BodyPart.LOWERLEG_L].bite_time = 65.0
            zombie = add_zombie(gm, gap=20, state=ZombieState.CHASING, facing_cos=1.0)
            zombie.time_since_seen = 0
            loop = ZombieLoop(gm, random.Random(1), SkillEngine())
            loop.run_minute(0, PlayerMinute(pace=Pace.RUN))
            return zombie.gap

        free, limping = gap_after(False), gap_after(True)
        self.assertAlmostEqual(free - limping, 8 * (1 - 0.25))

    def test_a_limp_lengthens_the_walk_up_to_a_zombie(self):
        from managers.zombies import approach_minutes

        self.assertEqual(approach_minutes(10.0, 1.0), 3)
        self.assertEqual(approach_minutes(10.0, 0.25), 9)


class WeakeningInterruptionTests(unittest.TestCase):
    """Spec 12, Interruptions."""

    def test_a_wait_stops_when_the_bleeding_level_rises(self):
        gm = GameManager()
        core = SimulationCore(gm)
        real = core._body.minute
        calls = []

        def minute(player, hours):
            calls.append(hours)
            if len(calls) == 3:
                player.body[BodyPart.FOREARM_L].bleeding_time = 0.5
            return real(player, hours)

        core._body.minute = minute  # type: ignore[method-assign]
        facts = core.resolve([WaitAction(duration=Duration(minutes=60))])
        self.assertEqual(len(calls), 3)
        self.assertIn("Orton is getting weaker.", facts)
        self.assertIn("Orton is now Minor Bleeding.", facts)
        self.assertEqual(gm.narrative.minutes, 3)

    def test_a_sleeper_wakes_when_weakened(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.FATIGUE, 1)
        core = SimulationCore(gm)
        real = core._body.minute
        calls = []

        def minute(player, hours):
            calls.append(hours)
            if len(calls) == 2:
                player.body[BodyPart.FOREARM_L].bleeding_time = 0.5
            return real(player, hours)

        core._body.minute = minute  # type: ignore[method-assign]
        facts = core.resolve([SleepAction(duration=Duration(minutes=120))])
        self.assertFalse(gm.player.asleep)
        self.assertIn("Orton wakes, badly hurt.", facts)

    def test_a_move_is_not_stopped_by_the_weakening_rule(self):
        gm = GameManager()
        core = SimulationCore(gm)
        real = core._body.minute
        calls = []

        def minute(player, hours):
            calls.append(hours)
            if len(calls) == 2:
                player.body[BodyPart.FOREARM_L].bleeding_time = 0.5
            return real(player, hours)

        core._body.minute = minute  # type: ignore[method-assign]
        core.resolve([MoveAction(destination="out")])
        self.assertEqual(len(calls), 10)


class WeakeningFactTests(unittest.TestCase):
    """Spec 12, Weakening: the fact is given once per turn, however many actions spend time."""

    def test_two_moves_while_dying_of_thirst_give_one_fact(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.THIRST, 0.9)
        facts = SimulationCore(gm).resolve(
            [MoveAction(destination="out"), MoveAction(destination="in")]
        )
        self.assertEqual(facts.count("Orton is weakening from thirst."), 1, facts)

    def test_the_next_turn_gives_it_again(self):
        gm = GameManager()
        gm.player.stats.set(CharacterStat.THIRST, 0.9)
        core = SimulationCore(gm)
        core.resolve([MoveAction(destination="out")])
        facts = core.resolve([MoveAction(destination="in")])
        self.assertIn("Orton is weakening from thirst.", facts)


class WeakeningComparisonTests(unittest.TestCase):
    """Spec 12, The weakening interruption: either level rising counts."""

    def test_bleeding_rising_while_injured_falls_counts_as_worse(self):
        from managers.simulation import _got_worse

        self.assertTrue(_got_worse((1, 2), (2, 1)))
        self.assertFalse(_got_worse((2, 1), (2, 1)))
        self.assertFalse(_got_worse((1, 1), (2, 2)))


class WoundLandsInThePartTests(unittest.TestCase):
    """Spec 12, Wounds: a zombie's wound goes into its part."""

    def test_a_bite_lands_on_the_neck_with_its_zombie_infection_and_infection_flags(self):
        from unittest.mock import patch

        gm = zombie_game()
        gm.player.worn.clear()
        zombie = add_zombie(gm, gap=1, state=ZombieState.CHASING, facing_cos=1.0)
        zombie.time_since_seen = 0
        with (
            patch("managers.zombie_attack.player_defence", return_value=-100),
            patch("managers.zombie_attack.roll_body_part", return_value=BodyPart.NECK),
            patch("managers.zombie_attack.roll_wound_kind", return_value="bite"),
            patch("managers.zombie_attack.roll_wound_damage", return_value=5.0),
            patch("managers.zombie_attack.clothing_defence", return_value=0),
        ):
            simulate(gm, WaitAction(duration=Duration(minutes=1)), rng=random.Random(1))
        neck = gm.player.body[BodyPart.NECK]
        self.assertGreater(neck.bite_time, 49)
        self.assertTrue(neck.zombie_infected)
        self.assertTrue(neck.infected_wound)
        self.assertGreaterEqual(100.0 - gm.player.health, 5.0 * 0.7 - 1e-9)


class RisingTests(unittest.TestCase):
    """Spec 12, Death: rising."""

    def test_a_death_while_infected_adds_and_rose_again(self):
        gm = GameManager()
        make_dying(gm.player)
        gm.player.body[BodyPart.HAND_L].zombie_infected = True
        gm.player.zombie_infection_since = 0.0
        gm.player.zombie_infection_hours = 60.0
        gm.narrative.minutes = 60 * 10
        facts = simulate(gm, WaitAction(duration=Duration(minutes=20)))
        self.assertTrue(gm.narrative.game_over)
        self.assertTrue(gm.narrative.death_cause.endswith("...and rose again."))
        self.assertTrue(any("and rose again." in fact for fact in facts))

    def test_a_death_without_the_infection_does_not_rise(self):
        gm = GameManager()
        make_dying(gm.player)
        simulate(gm, WaitAction(duration=Duration(minutes=20)))
        self.assertTrue(gm.narrative.game_over)
        self.assertNotIn("rose again", gm.narrative.death_cause)

    def test_the_zombie_infection_infection_ends_the_game_and_the_player_rises(self):
        gm = GameManager()
        gm.player.body[BodyPart.HAND_L].zombie_infected = True
        gm.player.zombie_infection_since = 0.0
        gm.player.zombie_infection_hours = 50.0
        gm.narrative.minutes = 60 * 51
        simulate(gm, WaitAction(duration=Duration(minutes=5)))
        self.assertTrue(gm.narrative.game_over)
        self.assertEqual(
            gm.narrative.death_cause, "Orton died of the zombie infection...and rose again."
        )


def shut_game(zone_id: str = "zone_home") -> GameManager:
    """`zombie_game` with every door shut again."""
    gm = zombie_game(zone_id)
    for barrier in gm.world.barriers.values():
        barrier.open = False
    return gm


def add_thumper(gm: GameManager, barrier_id: str, side: str, rate: float = 1.97) -> ZombieEntity:
    zombie = add_zombie(gm, side, gap=5, state=ZombieState.THUMPING, facing_cos=-1.0)
    zombie.thump_barrier = barrier_id
    zombie.thump_rate = rate
    return zombie


class DoorSimulationTests(unittest.TestCase):
    """Spec 13, `MOVE_TO` through a barrier, Interruptions and Stress from sounds."""

    def spent(self, gm: GameManager, *actions) -> tuple[int, list[str]]:
        before = gm.narrative.minutes
        facts = simulate(gm, *actions, rng=random.Random(1))
        return gm.narrative.minutes - before, facts

    def test_move_to_home_shuts_the_apartment_door_behind_the_player(self):
        gm = shut_game("zone_building")
        minutes, facts = self.spent(gm, MoveAction(destination="in"))
        self.assertEqual(gm.player.current_location_id, "zone_home")
        self.assertEqual(minutes, 10)
        door = gm.world.barriers["door_apartment"]
        self.assertFalse(door.open)
        self.assertEqual(gm.player.at_barrier, "door_apartment")
        self.assertIn("succeeded", facts[0])

    def test_an_open_door_stays_open_after_the_move(self):
        gm = shut_game("zone_building")
        gm.world.barriers["door_apartment"].open = True
        self.spent(gm, MoveAction(destination="in"))
        self.assertTrue(gm.world.barriers["door_apartment"].open)

    def test_a_later_move_in_the_zone_clears_the_barrier_the_player_is_at(self):
        gm = shut_game("zone_building")
        self.spent(gm, MoveAction(destination="in"))
        self.spent(gm, MoveAction(destination="the kitchen"))
        self.assertIsNone(gm.player.at_barrier)

    def test_a_chaser_left_behind_the_shut_door_becomes_a_thumper(self):
        gm = shut_game("zone_building")
        chaser = add_zombie(
            gm, "zone_building", gap=30, state=ZombieState.CHASING, speed_mod=0.01, facing_cos=1.0
        )
        chaser.time_since_seen = 0
        chaser.memory = 10**6
        self.spent(gm, MoveAction(destination="in"))
        self.assertEqual(chaser.state, ZombieState.THUMPING)
        self.assertEqual(chaser.thump_barrier, "door_apartment")
        self.assertEqual(chaser.zone_id, "zone_building")

    def test_every_chaser_left_behind_the_shut_door_thumps_even_one_at_gap_1(self):
        gm = shut_game("zone_building")
        near = add_zombie(
            gm, "zone_building", gap=1, state=ZombieState.CHASING, speed_mod=0.01, facing_cos=1.0
        )
        far = add_zombie(
            gm, "zone_building", gap=5, state=ZombieState.CHASING, speed_mod=0.01, facing_cos=1.0
        )
        for chaser in (near, far):
            chaser.time_since_seen = 0
            chaser.memory = 10**6
        self.spent(gm, MoveAction(destination="in"))
        for chaser in (near, far):
            self.assertEqual(chaser.state, ZombieState.THUMPING)
            self.assertEqual(chaser.thump_barrier, "door_apartment")

    def test_the_zombies_the_opening_released_follow_through_instead_of_thumping(self):
        gm = shut_game("zone_home")
        released = add_thumper(gm, "door_apartment", "zone_building")
        self.spent(gm, OpenAction(barrier_name="apartment door"))
        self.assertEqual(released.state, ZombieState.CHASING)
        gm = shut_game("zone_home")
        released = add_thumper(gm, "door_apartment", "zone_building")
        self.spent(gm, MoveAction(destination="out"))
        self.assertNotEqual(released.state, ZombieState.THUMPING)

    def test_a_walk_through_the_lobby_door_leaves_street_chasers_pounding_on_it(self):
        gm = shut_game("zone_street")
        chaser = add_zombie(
            gm, "zone_street", gap=35, state=ZombieState.CHASING, speed_mod=0.01, facing_cos=1.0
        )
        chaser.time_since_seen = 0
        chaser.memory = 10**6
        self.spent(gm, MoveAction(destination="zone_building"))
        self.assertEqual(chaser.state, ZombieState.THUMPING)
        self.assertEqual(chaser.thump_barrier, "door_lobby")

    def test_open_and_close_cost_0_and_walking_to_a_barrier_costs_1(self):
        gm = shut_game("zone_home")
        minutes, _ = self.spent(gm, OpenAction(barrier_name="apartment door"))
        self.assertEqual(minutes, 1)
        minutes, _ = self.spent(gm, CloseAction(barrier_name="apartment door"))
        self.assertEqual(minutes, 0)

    def test_a_wait_stops_when_thumping_starts(self):
        gm = shut_game("zone_home")
        chaser = add_zombie(gm, "zone_building", gap=30, state=ZombieState.CHASING, facing_cos=1.0)
        chaser.time_since_seen = 0
        minutes, facts = self.spent(gm, WaitAction(duration=Duration(minutes=30)))
        self.assertGreater(minutes, 1)
        self.assertLess(minutes, 30)
        self.assertEqual(chaser.state, ZombieState.THUMPING)
        self.assertIn("Something starts pounding on the apartment door.", facts)

    def test_a_sleep_does_not_stop_when_thumping_starts(self):
        gm = shut_game("zone_home")
        chaser = add_zombie(gm, "zone_building", gap=30, state=ZombieState.CHASING, facing_cos=1.0)
        chaser.time_since_seen = 0
        minutes, facts = self.spent(gm, SleepAction(duration=Duration(minutes=30)))
        self.assertEqual(minutes, 30)
        self.assertEqual(chaser.state, ZombieState.THUMPING)
        self.assertNotIn("Something starts pounding on the apartment door.", facts)

    def test_a_door_breaking_wakes_the_sleeper(self):
        gm = shut_game("zone_home")
        gm.world.barriers["door_apartment"].health = 3
        add_thumper(gm, "door_apartment", "zone_building")
        add_thumper(gm, "door_apartment", "zone_building")
        minutes, facts = self.spent(gm, SleepAction(duration=Duration(minutes=60)))
        self.assertEqual(minutes, 1)
        self.assertFalse(gm.player.asleep)
        self.assertIn("The apartment door bursts from its hinges.", facts)
        self.assertIn("The crash wakes Orton.", facts)

    def test_a_plank_breaking_stops_a_wait_but_not_a_sleep(self):
        gm = shut_game("zone_home")
        gm.world.barriers["door_apartment"].barricades["zone_home"] = [3, 3]
        add_thumper(gm, "door_apartment", "zone_building", rate=3.0)
        minutes, facts = self.spent(gm, WaitAction(duration=Duration(minutes=30)))
        self.assertEqual(minutes, 1)
        self.assertIn("A plank on the apartment door splinters.", facts)

    def test_a_break_outside_the_players_building_is_not_their_business(self):
        gm = shut_game("zone_home")
        gm.world.barriers["door_lobby"].health = 3
        add_thumper(gm, "door_lobby", "zone_street", rate=3.0)
        add_thumper(gm, "door_lobby", "zone_street", rate=3.0)
        minutes, _ = self.spent(gm, WaitAction(duration=Duration(minutes=10)))
        self.assertTrue(gm.world.barriers["door_lobby"].broken)
        self.assertEqual(minutes, 1)

    def test_thumping_at_the_door_raises_stress_by_about_0_0076_a_minute(self):
        def stress_after(thumping: bool) -> float:
            gm = shut_game("zone_home")
            gm.player.traits.clear()
            gm.player.stats.set(CharacterStat.STRESS, 0.5)
            if thumping:
                add_thumper(gm, "door_apartment", "zone_building")
            simulate(gm, WaitAction(duration=Duration(minutes=30)), rng=random.Random(1))
            return gm.player.stats.get(CharacterStat.STRESS)

        gain = stress_after(True) - stress_after(False)
        self.assertAlmostEqual(gain, 30 * 0.00768, delta=0.01)

    def test_a_deaf_player_gets_no_stress_from_the_thumping(self):
        def stress_after(traits: list[str]) -> float:
            gm = shut_game("zone_home")
            gm.player.traits[:] = traits
            gm.player.stats.set(CharacterStat.STRESS, 0.5)
            add_thumper(gm, "door_apartment", "zone_building")
            simulate(gm, WaitAction(duration=Duration(minutes=30)), rng=random.Random(1))
            return gm.player.stats.get(CharacterStat.STRESS)

        self.assertLess(stress_after(["deaf"]), stress_after([]))

    def test_the_lobby_door_holds_street_zombies_out_of_a_redistribution(self):
        gm = shut_game("zone_home")
        for _ in range(30):
            add_zombie(gm, "zone_street", gap=10)
        from managers.zombies import redistribute

        redistribute(gm.world, 720, "zone_home", random.Random(2))
        self.assertEqual([z for z in gm.world.zombies.values() if z.zone_id == "zone_building"], [])

    def test_a_thumper_behind_the_door_shows_up_in_the_threats_in_words(self):
        gm = shut_game("zone_home")
        add_thumper(gm, "door_apartment", "zone_building")
        (view,) = threat_views(gm)
        self.assertIsNone(view.zombie_id)
        self.assertEqual(view.state_word, "something at the apartment door")


class BarrierStoryBeatTests(unittest.TestCase):
    """Spec 13, Edge cases: a story beat does not move an NPC across planks."""

    def beat_move(self, gm: GameManager, zone_id: str) -> str:
        from modules.story import MoveNpc

        npc = next(iter(gm.npcs.values()))
        SimulationCore(gm).apply_story_effect(MoveNpc(npc_id=npc.npc_id, zone_id=zone_id))
        return npc.current_location_id

    def test_a_beat_skips_a_move_across_planks_and_logs_it(self):
        gm = GameManager()
        npc = next(iter(gm.npcs.values()))
        npc.current_location_id = "zone_building"
        gm.world.barriers["door_apartment"].barricades["zone_home"] = [1000]
        with self.assertLogs("managers.simulation", level="WARNING"):
            where = self.beat_move(gm, "zone_home")
        self.assertEqual(where, "zone_building")

    def test_closed_and_locked_doors_do_not_stop_a_beat(self):
        gm = GameManager()
        npc = next(iter(gm.npcs.values()))
        npc.current_location_id = "zone_building"
        self.assertEqual(self.beat_move(gm, "zone_home"), "zone_home")
