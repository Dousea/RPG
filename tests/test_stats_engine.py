"""Spec 02, Drivers while awake, Sleep, Health loss from status effects, Layout."""

import unittest

from data.survival import BED_MULTIPLIERS
from managers.stats.drivers import StatContext, default_drivers
from managers.stats.engine import StatsEngine
from managers.stats.status_effects import status_effect_level
from modules.entity.player import PlayerEntity
from modules.stats import CharacterStat as S
from modules.stats import StatusEffect


def make_player() -> PlayerEntity:
    return PlayerEntity(name="Orton", current_location_id="zone_home")


def run(player, minutes, **ctx_fields):
    engine = StatsEngine(default_drivers())
    return engine, engine.advance(player, minutes, StatContext(**ctx_fields))


class StatusEffectLevelTests(unittest.TestCase):
    """Spec 03, Status effects (the level function the engine reads)."""

    def test_thresholds_are_strict(self):
        self.assertEqual(status_effect_level(StatusEffect.HUNGRY, 0.15), 0)
        self.assertEqual(status_effect_level(StatusEffect.HUNGRY, 0.1501), 1)
        self.assertEqual(status_effect_level(StatusEffect.HUNGRY, 0.71), 4)

    def test_endurance_is_inverted_and_inclusive(self):
        self.assertEqual(status_effect_level(StatusEffect.ENDURANCE, 0.76), 0)
        self.assertEqual(status_effect_level(StatusEffect.ENDURANCE, 0.75), 1)
        self.assertEqual(status_effect_level(StatusEffect.ENDURANCE, 0.10), 4)


class AwakeDriverTests(unittest.TestCase):
    """Spec 02, Drivers while awake: one hand-computed hour per driver."""

    def test_hunger_fasted(self):
        player = make_player()
        run(player, 6)
        self.assertAlmostEqual(player.stats.get(S.HUNGER), 0.003456, places=6)

    def test_hunger_scales_with_appetite(self):
        player = make_player()
        player.stats.set(S.HUNGER, 0.5)
        run(player, 6)
        self.assertAlmostEqual(player.stats.get(S.HUNGER), 0.5 + 0.003456 * 0.5, places=6)

    def test_hunger_exercising_fasted_is_a_third_of_the_fed_rate(self):
        player = make_player()
        run(player, 6, exercising=True)
        self.assertAlmostEqual(player.stats.get(S.HUNGER), 0.002304, places=6)

    def test_hunger_well_fed_idle_does_not_grow_and_exercising_doubles(self):
        player = make_player()
        player.food_eaten_timer = 10000
        run(player, 6)
        self.assertEqual(player.stats.get(S.HUNGER), 0)
        run(player, 6, exercising=True)
        self.assertAlmostEqual(player.stats.get(S.HUNGER), 0.006912, places=6)

    def test_hunger_is_scaled_by_the_energy_multiplier(self):
        from managers.stats.drivers import BodyMultipliers

        player = make_player()
        run(player, 6, body=BodyMultipliers(energy=2.0))
        self.assertAlmostEqual(player.stats.get(S.HUNGER), 0.006912, places=6)

    def test_thirst(self):
        player = make_player()
        run(player, 60)
        self.assertAlmostEqual(player.stats.get(S.THIRST), 0.0288, places=4)

    def test_thirst_exercising(self):
        player = make_player()
        run(player, 60, exercising=True)
        self.assertAlmostEqual(player.stats.get(S.THIRST), 0.0288 * 1.2, places=4)

    def test_fatigue_with_full_endurance_uses_the_floor(self):
        player = make_player()
        run(player, 60)
        self.assertAlmostEqual(player.stats.get(S.FATIGUE), 0.1242 * 0.3, places=4)

    def test_fatigue_follows_endurance_loss(self):
        player = make_player()
        player.stats.set(S.ENDURANCE, 0.2)
        run(player, 6, walking=False, resting=False)
        self.assertAlmostEqual(player.stats.get(S.FATIGUE), 0.009936, places=6)

    def test_fatigue_resting_is_divided_by_one_and_a_half(self):
        player = make_player()
        run(player, 60, resting=True)
        self.assertAlmostEqual(player.stats.get(S.FATIGUE), 0.1242 * 0.3 / 1.5, places=4)

    def test_stress_decays(self):
        player = make_player()
        player.stats.set(S.STRESS, 0.5)
        run(player, 60)
        self.assertAlmostEqual(player.stats.get(S.STRESS), 0.5 - 0.108, places=4)

    def test_endurance_drains_while_exercising(self):
        player = make_player()
        run(player, 60, exercising=True)
        self.assertAlmostEqual(player.stats.get(S.ENDURANCE), 1 - 0.2808, places=3)

    def test_endurance_regenerates_resting(self):
        player = make_player()
        player.stats.set(S.ENDURANCE, 0.2)
        run(player, 6, resting=True)
        self.assertAlmostEqual(player.stats.get(S.ENDURANCE), 0.2 + 0.1 * 1.674 * 1.2, delta=0.002)

    def test_endurance_regenerates_standing(self):
        player = make_player()
        player.stats.set(S.ENDURANCE, 0.2)
        run(player, 6)
        self.assertAlmostEqual(player.stats.get(S.ENDURANCE), 0.2 + 0.1 * 0.3348 * 1.2, delta=0.001)

    def test_endurance_regenerates_walking_above_status_effect_level_two(self):
        player = make_player()
        player.stats.set(S.ENDURANCE, 0.6)
        run(player, 60, walking=True)
        self.assertAlmostEqual(player.stats.get(S.ENDURANCE), 0.6 + 0.0837 * 1.2, delta=0.01)

    def test_endurance_drains_walking_at_status_effect_level_two(self):
        player = make_player()
        player.stats.set(S.ENDURANCE, 0.5)
        run(player, 60, walking=True)
        self.assertAlmostEqual(player.stats.get(S.ENDURANCE), 0.5 - 0.0501, places=3)

    def test_sneaking_walk_drain_is_one_and_a_half_times(self):
        player = make_player()
        player.stats.set(S.ENDURANCE, 0.5)
        run(player, 60, walking=True, sneaking=True)
        self.assertAlmostEqual(player.stats.get(S.ENDURANCE), 0.5 - 0.0501 * 1.5, places=3)

    def test_idleness_rises_resting_and_faster_indoors(self):
        outdoors = make_player()
        run(outdoors, 30, resting=True)
        self.assertAlmostEqual(outdoors.stats.get(S.IDLENESS), 0.9, places=4)
        indoors = make_player()
        run(indoors, 30, resting=True, indoors=True)
        self.assertEqual(indoors.stats.get(S.IDLENESS), 1)

    def test_idleness_falls_when_busy_and_resets_in_combat(self):
        player = make_player()
        player.stats.set(S.IDLENESS, 0.5)
        run(player, 60 * 0.5, resting=False)
        self.assertAlmostEqual(player.stats.get(S.IDLENESS), 0, places=4)
        player.stats.set(S.IDLENESS, 0.5)
        run(player, 1, exercising=True)
        self.assertEqual(player.stats.get(S.IDLENESS), 0)

    def test_boredom_falls_outdoors_when_not_resting(self):
        player = make_player()
        player.stats.set(S.BOREDOM, 80)
        run(player, 60)
        self.assertAlmostEqual(player.stats.get(S.BOREDOM), 80 - 41.58, places=2)

    def test_boredom_rises_resting_in_proportion_to_idleness(self):
        player = make_player()
        player.stats.set(S.IDLENESS, 1)
        run(player, 6, resting=True)
        self.assertAlmostEqual(player.stats.get(S.BOREDOM), 10.8 * 0.1, places=2)

    def test_boredom_busy_indoors_decays_when_idleness_is_low(self):
        player = make_player()
        player.stats.set(S.BOREDOM, 50)
        run(player, 6, indoors=True)
        self.assertAlmostEqual(player.stats.get(S.BOREDOM), 50 - 20.79, places=2)

    def test_boredom_talking_and_npcs_and_drunk(self):
        cases = (
            ({"talking": True}, {}, 41.58),
            ({"npcs_present": True}, {}, 4.158),
            ({}, {S.INTOXICATION: 50}, 83.16),
        )
        for fields, other, drop in cases:
            player = make_player()
            player.stats.set(S.BOREDOM, 90)
            for stat, value in other.items():
                player.stats.set(stat, value)
            run(player, 6, resting=True, **fields)
            self.assertAlmostEqual(player.stats.get(S.BOREDOM), 90 - drop, delta=0.25)

    def test_panic_above_five_resets_boredom(self):
        player = make_player()
        player.stats.set(S.BOREDOM, 60)
        player.stats.set(S.PANIC, 50)
        run(player, 1)
        self.assertEqual(player.stats.get(S.BOREDOM), 0)

    def test_unhappiness_from_bored_and_stress_levels(self):
        player = make_player()
        player.stats.set(S.BOREDOM, 60)
        player.stats.set(S.STRESS, 0.62)
        run(player, 6, resting=True, indoors=True)
        bored_level, stress_level = 2, 2
        self.assertAlmostEqual(
            player.stats.get(S.UNHAPPINESS),
            (5.4 * bored_level + 2.7 * stress_level) * 0.1,
            places=1,
        )

    def test_unhappiness_does_not_grow_below_level_two(self):
        player = make_player()
        player.stats.set(S.BOREDOM, 30)
        run(player, 6, resting=True)
        self.assertEqual(player.stats.get(S.UNHAPPINESS), 0)

    def test_panic_rises_per_zombie_and_decays(self):
        player = make_player()
        run(player, 1, new_zombies_seen=2)
        self.assertAlmostEqual(player.stats.get(S.PANIC), 14 - 405 / 60, places=2)

    def test_panic_decay_grows_with_months_survived(self):
        player = make_player()
        player.stats.set(S.PANIC, 100)
        run(player, 1, hours_survived=720 * 2)
        self.assertAlmostEqual(player.stats.get(S.PANIC), 100 - 405 * 3 / 60, places=2)

    def test_panic_decay_months_are_capped_at_five(self):
        player = make_player()
        player.stats.set(S.PANIC, 100)
        run(player, 1, hours_survived=720 * 20)
        self.assertAlmostEqual(player.stats.get(S.PANIC), 100 - 405 * 6 / 60, places=2)

    def test_intoxication_decays(self):
        player = make_player()
        player.stats.set(S.INTOXICATION, 60)
        run(player, 60)
        self.assertAlmostEqual(player.stats.get(S.INTOXICATION), 60 - 45.36, places=2)

    def test_food_sickness_decays_without_corpses(self):
        player = make_player()
        player.stats.set(S.FOOD_SICKNESS, 50)
        run(player, 60)
        self.assertAlmostEqual(player.stats.get(S.FOOD_SICKNESS), 50 - 16.2, places=2)

    def test_corpses_raise_food_sickness_instead_of_the_decay(self):
        player = make_player()
        player.stats.set(S.FOOD_SICKNESS, 50)
        run(player, 60, corpse_count=15, corpse_defence=50)
        self.assertAlmostEqual(player.stats.get(S.FOOD_SICKNESS), 50 + 1.134 * 10 * 0.5, places=2)

    def test_five_corpses_or_fewer_do_not_make_sick(self):
        player = make_player()
        run(player, 60, corpse_count=5)
        self.assertEqual(player.stats.get(S.FOOD_SICKNESS), 0)

    def test_corpse_sickness_caps_at_twenty_excess_corpses(self):
        player = make_player()
        run(player, 60, corpse_count=100)
        self.assertAlmostEqual(player.stats.get(S.FOOD_SICKNESS), 1.134 * 20, places=2)


class ScenarioTests(unittest.TestCase):
    """Spec 02, Testing: the success criteria."""

    def _first_level(self, player, status_effect, minutes_limit, ctx, level=1):
        engine = StatsEngine(default_drivers())
        spec_stat = {
            StatusEffect.HUNGRY: S.HUNGER,
            StatusEffect.TIRED: S.FATIGUE,
        }[status_effect]
        for minute in range(0, minutes_limit, 10):
            engine.advance(player, 10, ctx)
            if status_effect_level(status_effect, player.stats.get(spec_stat)) >= level:
                return (minute + 10) / 60
        return None

    def test_idle_orton_is_peckish_between_four_and_five_hours(self):
        hours = self._first_level(make_player(), StatusEffect.HUNGRY, 60 * 8, StatContext())
        assert hours is not None
        self.assertGreaterEqual(hours, 4)
        self.assertLessEqual(hours, 5)

    def test_rested_orton_is_drowsy_between_fifteen_and_seventeen_hours(self):
        hours = self._first_level(make_player(), StatusEffect.TIRED, 60 * 24, StatContext())
        assert hours is not None
        self.assertGreaterEqual(hours, 15)
        self.assertLessEqual(hours, 17)


class SleepTests(unittest.TestCase):
    """Spec 02, Sleep."""

    def test_the_bed_table(self):
        self.assertEqual(
            list(BED_MULTIPLIERS.values()), [1.15, 1.10, 1.05, 1.00, 0.95, 0.90, 0.75, 0.60]
        )

    def test_asleep_hunger_and_thirst(self):
        player = make_player()
        run(player, 60, asleep=True)
        self.assertAlmostEqual(player.stats.get(S.HUNGER), 0.0036, places=4)
        self.assertAlmostEqual(player.stats.get(S.THIRST), 0.0036, places=4)

    def test_asleep_hunger_is_zero_while_well_fed(self):
        player = make_player()
        player.food_eaten_timer = 11000
        run(player, 60, asleep=True)
        self.assertEqual(player.stats.get(S.HUNGER), 0)

    def test_asleep_endurance_regen(self):
        player = make_player()
        player.stats.set(S.ENDURANCE, 0.1)
        run(player, 60, asleep=True)
        self.assertAlmostEqual(player.stats.get(S.ENDURANCE), 0.1 + 0.2232 * 1.2, places=3)

    def test_fatigue_recovery_rate_above_and_below_the_break(self):
        high = make_player()
        high.stats.set(S.FATIGUE, 0.8)
        run(high, 60, asleep=True, bed_type="average_bed")
        self.assertAlmostEqual(high.stats.get(S.FATIGUE), 0.8 - 0.14, places=4)
        low = make_player()
        low.stats.set(S.FATIGUE, 0.2)
        run(low, 60, asleep=True, bed_type="average_bed")
        self.assertAlmostEqual(low.stats.get(S.FATIGUE), 0.2 - 0.3 / 7, places=4)

    def test_the_default_bed_is_the_floor(self):
        player = make_player()
        player.stats.set(S.FATIGUE, 0.8)
        run(player, 60, asleep=True)
        self.assertAlmostEqual(player.stats.get(S.FATIGUE), 0.8 - 0.14 * 0.6, places=4)

    def test_the_bed_scales_recovery(self):
        player = make_player()
        player.stats.set(S.FATIGUE, 0.8)
        run(player, 60, asleep=True, bed_type="floor")
        self.assertAlmostEqual(player.stats.get(S.FATIGUE), 0.8 - 0.14 * 0.6, places=4)

    def test_panic_decay_doubles_asleep(self):
        awake, asleep = make_player(), make_player()
        for player in (awake, asleep):
            player.stats.set(S.PANIC, 100)
        run(awake, 6)
        run(asleep, 6, asleep=True)
        self.assertAlmostEqual(
            100 - asleep.stats.get(S.PANIC), 2 * (100 - awake.stats.get(S.PANIC))
        )

    def test_fatigue_from_point_eight_reaches_zero_in_the_formulas_ten_and_a_half_hours(self):
        # 0.5 above the break at 0.14 an hour, then 0.3 at 0.3 / 7 an hour.
        player = make_player()
        player.stats.set(S.FATIGUE, 0.8)
        engine = StatsEngine(default_drivers())
        ctx = StatContext(asleep=True, bed_type="average_bed")
        minutes = 0
        while player.stats.get(S.FATIGUE) > 0 and minutes < 60 * 16:
            engine.advance(player, 10, ctx)
            minutes += 10
        self.assertAlmostEqual(minutes / 60, 0.5 / 0.14 + 7, delta=0.3)


class EngineTests(unittest.TestCase):
    """Spec 02, Layout; spec 03, Status effects (level-change facts, the well-fed timer)."""

    def test_advance_600_matches_ten_advance_60(self):
        one, many = make_player(), make_player()
        for player in (one, many):
            player.stats.set(S.FATIGUE, 0.3)
            player.stats.set(S.ENDURANCE, 0.4)
            player.stats.set(S.PANIC, 40)
        StatsEngine(default_drivers()).advance(one, 600, StatContext(resting=True, indoors=True))
        engine = StatsEngine(default_drivers())
        for _ in range(10):
            engine.advance(many, 60, StatContext(resting=True, indoors=True))
        for stat in S:
            self.assertAlmostEqual(one.stats.get(stat), many.stats.get(stat), delta=1e-6)

    def test_a_driver_registered_after_construction_runs(self):
        class Chill:
            def apply(self, stats, hours, ctx):
                stats.add(S.PAIN, 10 * hours)

        player = make_player()
        engine = StatsEngine(default_drivers())
        engine.register(Chill())
        engine.advance(player, 60, StatContext())
        self.assertAlmostEqual(player.stats.get(S.PAIN), 10)

    def test_a_threshold_crossing_gives_exactly_one_fact(self):
        player = make_player()
        player.stats.set(S.HUNGER, 0.149)
        _, facts = run(player, 10)
        self.assertEqual(facts, ["Orton is now Peckish."])

    def test_no_crossing_gives_no_fact(self):
        _, facts = run(make_player(), 10)
        self.assertEqual(facts, [])

    def test_a_status_effect_clearing_is_reported(self):
        player = make_player()
        player.stats.set(S.INTOXICATION, 10.1)
        _, facts = run(player, 10)
        self.assertEqual(facts, ["Orton is no longer Tipsy."])

    def test_the_well_fed_timer_drains_10800_per_hour(self):
        player = make_player()
        player.food_eaten_timer = 11000
        run(player, 60)
        self.assertAlmostEqual(player.food_eaten_timer, 200)

    def test_the_timer_never_goes_below_zero_and_running_out_is_one_fact(self):
        player = make_player()
        player.food_eaten_timer = 900
        _, facts = run(player, 10)
        self.assertEqual(player.food_eaten_timer, 0)
        self.assertEqual(facts, ["Orton is no longer Well Fed."])

    def test_a_crossing_in_the_middle_of_a_long_span_is_one_fact(self):
        player = make_player()
        player.stats.set(S.HUNGER, 0.149)
        _, facts = run(player, 60)
        self.assertEqual(facts.count("Orton is now Peckish."), 1)

    def test_facts_hold_no_digits(self):
        player = make_player()
        player.stats.set(S.HUNGER, 0.8)
        _, facts = run(player, 60)
        self.assertFalse(any(ch.isdigit() for fact in facts for ch in fact))


if __name__ == "__main__":
    unittest.main()


class TraitFactorTests(unittest.TestCase):
    """Spec 07, Traits with an effect now."""

    @staticmethod
    def after(setup, minutes, traits, **ctx):
        player = make_player()
        setup(player)
        run(player, minutes, traits=frozenset(traits), **ctx)
        return player

    def test_appetite_factors(self):
        def fed_half(p):
            p.stats.set(S.HUNGER, 0.5)

        base = self.after(fed_half, 6, ()).stats.get(S.HUNGER) - 0.5
        self.assertAlmostEqual(base, 0.003456 * 0.5, places=7)
        hearty = self.after(fed_half, 6, ("heartyappetite",)).stats.get(S.HUNGER) - 0.5
        light = self.after(fed_half, 6, ("lighteater",)).stats.get(S.HUNGER) - 0.5
        self.assertAlmostEqual(hearty, 0.003456 * 0.5 * 1.5, places=7)
        self.assertAlmostEqual(light, 0.003456 * 0.5 * 0.75, places=7)

    def test_thirst_factors(self):
        nothing = lambda p: None  # noqa: E731
        self.assertAlmostEqual(self.after(nothing, 6, ()).stats.get(S.THIRST), 0.00288, places=7)
        high = self.after(nothing, 6, ("highthirst",)).stats.get(S.THIRST)
        low = self.after(nothing, 6, ("lowthirst",)).stats.get(S.THIRST)
        self.assertAlmostEqual(high, 0.00576, places=7)
        self.assertAlmostEqual(low, 0.00144, places=7)

    def test_awake_fatigue_factors(self):
        nothing = lambda p: None  # noqa: E731
        base = self.after(nothing, 60, ()).stats.get(S.FATIGUE)
        self.assertAlmostEqual(base, 0.03726, places=5)
        wakeful = self.after(nothing, 60, ("needslesssleep",)).stats.get(S.FATIGUE)
        sleepy = self.after(nothing, 60, ("needsmoresleep",)).stats.get(S.FATIGUE)
        self.assertAlmostEqual(wakeful, 0.03726 * 0.7, places=5)
        self.assertAlmostEqual(sleepy, 0.03726 * 1.3, places=5)

    def test_sleep_fatigue_factors(self):
        def tired(p):
            p.stats.set(S.FATIGUE, 0.8)

        def lost(*traits):
            player = self.after(tired, 60, traits, asleep=True, bed_type="average_bed")
            return 0.8 - player.stats.get(S.FATIGUE)

        self.assertAlmostEqual(lost(), 0.14, places=5)
        self.assertAlmostEqual(lost("needslesssleep"), 0.14 / 0.75, places=5)
        self.assertAlmostEqual(lost("needsmoresleep"), 0.14 / 1.18, places=5)
        self.assertAlmostEqual(lost("insomniac"), 0.14 * 0.5, places=5)
        self.assertAlmostEqual(lost("nightowl"), 0.14 * 1.4, places=5)

    def test_panic_gain_factors(self):
        nothing = lambda p: None  # noqa: E731

        def panic(*traits):
            return self.after(nothing, 1, traits, new_zombies_seen=5).stats.get(S.PANIC)

        self.assertAlmostEqual(panic(), 35 - 6.75, places=4)
        self.assertAlmostEqual(panic("cowardly"), 70 - 6.75, places=4)
        self.assertAlmostEqual(panic("brave"), 35 * 0.3 - 6.75, places=4)

    def test_desensitized_never_panics(self):
        nothing = lambda p: None  # noqa: E731
        player = self.after(nothing, 1, ("desensitized",), new_zombies_seen=50)
        self.assertEqual(player.stats.get(S.PANIC), 0)
        player = make_player()
        player.stats.set(S.PANIC, 40)
        run(player, 1, traits=frozenset({"desensitized"}), new_zombies_seen=1)
        self.assertEqual(player.stats.get(S.PANIC), 0)
