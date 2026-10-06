"""Spec 12, The body minute: bleeding, healing, wound infection, zombie infection and stress."""

import random
import unittest

from managers.body import (
    BodyEngine,
    generate_bleeding,
    heal_per_hour,
    infection_chance,
    land_wound,
)
from managers.stats.status_effects import player_status_effect_levels
from modules.body import BodyPart, PartState, overall_health
from modules.entity.player import PlayerEntity
from modules.stats import CharacterStat, StatusEffect
from tests.support import set_health


def make_player(traits=()) -> PlayerEntity:
    return PlayerEntity(name="Orton", current_location_id="zone_home", traits=list(traits))


def run(player: PlayerEntity, minutes: int, *, seed: int = 0, start_hours: float = 0.0):
    """Run body minutes until the player dies; returns (minutes run, facts, death fact)."""
    engine = BodyEngine(random.Random(seed))
    facts: list[str] = []
    for index in range(minutes):
        facts.extend(engine.minute(player, start_hours + index / 60))
        if engine.death_fact:
            return index + 1, facts, engine.death_fact
    return minutes, facts, ""


class NeverInfectsRng(random.Random):
    """Every chance roll misses, so a wound never becomes infected."""

    def random(self) -> float:
        return 0.999


class MidRng(random.Random):
    """A range roll always lands in the middle of its range."""

    def uniform(self, a: float, b: float) -> float:
        return (a + b) / 2


def bandage(player: PlayerEntity, part: BodyPart, life: float = 5.0, alcoholic: bool = False):
    state = player.body[part]
    state.bandage = "item_bandage"
    state.bandage_life = life
    state.bandage_alcoholic = alcoholic


class BleedingTests(unittest.TestCase):
    """Spec 12, Bleeding."""

    def test_an_unbandaged_neck_bite_kills_in_six_to_ten_minutes(self):
        for seed in range(20):
            player = make_player()
            land_wound(player, "bite", BodyPart.NECK, 10.0, False, random.Random(seed))
            minutes, _, death = run(player, 30, seed=seed)
            self.assertTrue(6 <= minutes <= 10, (seed, minutes))
            self.assertIn(death, ("Orton bled to death.", "Orton died of the wounds."))

    def test_a_neck_bite_bandaged_at_minute_two_leaves_the_player_alive(self):
        for seed in range(20):
            player = make_player()
            land_wound(player, "bite", BodyPart.NECK, 10.0, False, random.Random(seed))
            engine = BodyEngine(random.Random(seed))
            for minute in range(6 * 60):
                if minute == 2:
                    bandage(player, BodyPart.NECK)
                engine.minute(player, minute / 60)
                self.assertEqual(engine.death_fact, "", (seed, minute))
            self.assertGreater(player.health, 90)

    def lower_torso_laceration_hours(self, rng: random.Random) -> float:
        player = make_player()
        state = player.body[BodyPart.TORSO_LOWER]
        state.health = 95.0
        state.cut_time = 15.0
        generate_bleeding(state, BodyPart.TORSO_LOWER, rng)
        minutes, _, death = run(player, 60 * 12)
        self.assertEqual(death, "Orton bled to death.")
        return minutes / 60

    def test_an_unbandaged_lower_torso_laceration_kills_in_four_to_six_hours(self):
        self.assertTrue(4 <= self.lower_torso_laceration_hours(MidRng()) <= 6)

    def test_the_bleeding_roll_moves_that_death_by_about_an_hour_either_way(self):
        for seed in range(10):
            hours = self.lower_torso_laceration_hours(random.Random(seed))
            self.assertTrue(3.5 <= hours <= 7, (seed, hours))

    def test_a_bandaged_forearm_laceration_is_at_full_health_within_an_hour(self):
        for seed in range(10):
            player = make_player()
            land_wound(player, "laceration", BodyPart.FOREARM_L, 10.0, False, random.Random(seed))
            bandage(player, BodyPart.FOREARM_L)
            minutes, _, _ = run(player, 60, seed=seed)
            self.assertAlmostEqual(player.health, 100.0, delta=0.01, msg=seed)

    def test_each_bleeding_part_drains_one_point_seven_six_three_hp_per_hour_per_unit(self):
        player = make_player()
        player.body[BodyPart.FOREARM_L].bleeding_time = 10.0
        engine = BodyEngine(random.Random(0))
        engine.minute(player, 0.0)
        self.assertAlmostEqual(100 - player.health, 1.763 * 10 / 60, places=3)

    def test_the_neck_drains_eight_point_eight_two_per_unit(self):
        player = make_player()
        player.body[BodyPart.NECK].bleeding_time = 10.0
        BodyEngine(random.Random(0)).minute(player, 0.0)
        extra_massive_blood_loss = 178.2 / 60
        self.assertAlmostEqual(
            100 - player.health, 8.82 * 10 / 60 + extra_massive_blood_loss, places=2
        )

    def test_a_bandaged_part_does_not_bleed(self):
        player = make_player()
        player.body[BodyPart.FOREARM_L].bleeding_time = 10.0
        bandage(player, BodyPart.FOREARM_L)
        BodyEngine(random.Random(0)).minute(player, 0.0)
        self.assertEqual(player.health, 100.0)

    def test_the_bleeding_status_effect_counts_bleeding_parts_and_is_four_for_the_neck(self):
        player = make_player()
        self.assertEqual(player_status_effect_levels(player)[StatusEffect.BLEEDING], 0)
        player.body[BodyPart.HAND_L].bleeding_time = 1
        self.assertEqual(player_status_effect_levels(player)[StatusEffect.BLEEDING], 1)
        player.body[BodyPart.HAND_R].bleeding_time = 1
        player.body[BodyPart.FOREARM_L].bleeding_time = 1
        self.assertEqual(player_status_effect_levels(player)[StatusEffect.BLEEDING], 3)
        for part in (BodyPart.FOREARM_R, BodyPart.UPPERARM_L, BodyPart.UPPERARM_R):
            player.body[part].bleeding_time = 1
        self.assertEqual(player_status_effect_levels(player)[StatusEffect.BLEEDING], 4)
        other = make_player()
        other.body[BodyPart.NECK].bleeding_time = 1
        self.assertEqual(player_status_effect_levels(other)[StatusEffect.BLEEDING], 4)

    def test_a_bandaged_part_does_not_count_for_the_bleeding_status_effect(self):
        player = make_player()
        player.body[BodyPart.HAND_L].bleeding_time = 1
        bandage(player, BodyPart.HAND_L)
        self.assertEqual(player_status_effect_levels(player)[StatusEffect.BLEEDING], 0)

    def test_massive_blood_loss_costs_a_hundred_seventy_eight_point_two_an_hour(self):
        player = make_player()
        player.body[BodyPart.NECK].bleeding_time = 0.0001
        player.body[BodyPart.NECK].bleeding_time = 1e-9
        for part in (BodyPart.HAND_L, BodyPart.HAND_R, BodyPart.FOREARM_L, BodyPart.FOREARM_R):
            player.body[part].bleeding_time = 1e-9
        BodyEngine(random.Random(0)).minute(player, 0.0)
        self.assertAlmostEqual(100 - player.health, 178.2 / 60, places=3)

    def test_a_scratch_reaching_zero_health_holds_overall_at_eighty(self):
        player = make_player()
        land_wound(player, "scratch", BodyPart.FOREARM_L, 5.0, False, random.Random(1))
        minutes, _, death = run(player, 60 * 4)
        self.assertEqual(death, "")
        self.assertEqual(player.body[BodyPart.FOREARM_L].health, 0.0)
        self.assertAlmostEqual(player.health, 80.0, delta=0.5)


class WoundDamageTests(unittest.TestCase):
    """Spec 12, Wound damage."""

    def minute_loss(self, part, **fields):
        player = make_player()
        state = player.body[part]
        for name, value in fields.items():
            setattr(state, name, value)
        BodyEngine(random.Random(0)).minute(player, 0.0)
        return 100 - state.health

    def test_an_open_scratch_costs_57_9_part_health_an_hour(self):
        self.assertAlmostEqual(self.minute_loss(BodyPart.HAND_L, scratch_time=10.0), 57.9 / 60)

    def test_an_open_laceration_costs_115_7_an_hour(self):
        self.assertAlmostEqual(self.minute_loss(BodyPart.HAND_L, cut_time=10.0), 115.7 / 60)

    def test_an_open_bite_costs_135_an_hour(self):
        self.assertAlmostEqual(self.minute_loss(BodyPart.HAND_L, bite_time=60.0), 135.0 / 60)

    def test_the_neck_takes_five_times_as_much(self):
        self.assertAlmostEqual(
            self.minute_loss(BodyPart.NECK, scratch_time=10.0), 5 * 57.9 / 60, places=4
        )
        self.assertAlmostEqual(
            self.minute_loss(BodyPart.NECK, bite_time=60.0), 5 * 135.0 / 60, places=4
        )

    def test_a_bandage_even_a_dirty_one_stops_the_damage(self):
        self.assertEqual(
            self.minute_loss(
                BodyPart.HAND_L, scratch_time=10.0, bandage="item_dirty_bandage", bandage_life=0.0
            ),
            0.0,
        )


class WoundTimerTests(unittest.TestCase):
    """Spec 12, Wound times."""

    def hour(self, bandaged: bool, **fields):
        player = make_player()
        state = player.body[BodyPart.HAND_L]
        for name, value in fields.items():
            setattr(state, name, value)
        if bandaged:
            bandage(player, BodyPart.HAND_L, life=1000.0)
        engine = BodyEngine(NeverInfectsRng(0))
        for minute in range(60):
            engine.minute(player, minute / 60)
        return state

    def test_one_hour_of_each_timer_unbandaged(self):
        for field, rate in (
            ("scratch_time", 0.108),
            ("cut_time", 0.0108),
            ("bite_time", 0.054),
            ("bleeding_time", 0.216),
        ):
            state = self.hour(False, **{field: 100.0 if field != "bleeding_time" else 5.0})
            start = 100.0 if field != "bleeding_time" else 5.0
            self.assertAlmostEqual(getattr(state, field), start - rate, places=6, msg=field)

    def test_one_hour_of_each_timer_bandaged(self):
        for field, rate in (
            ("scratch_time", 1.62),
            ("cut_time", 0.54),
            ("bite_time", 1.08),
            ("bleeding_time", 2.16),
        ):
            state = self.hour(True, **{field: 100.0})
            self.assertAlmostEqual(getattr(state, field), 100.0 - rate, places=6, msg=field)

    def test_a_scratch_running_out_also_stops_the_bleeding_of_an_open_cut(self):
        player = make_player()
        state = player.body[BodyPart.HAND_L]
        state.scratch_time = 0.001
        state.cut_time = 50.0
        state.bleeding_time = 5.0
        BodyEngine(random.Random(0)).minute(player, 0.0)
        self.assertEqual(state.scratch_time, 0.0)
        self.assertEqual(state.bleeding_time, 0.0)

    def test_a_cut_running_out_stops_the_bleeding(self):
        player = make_player()
        state = player.body[BodyPart.HAND_L]
        state.cut_time = 0.0001
        state.bleeding_time = 5.0
        BodyEngine(random.Random(0)).minute(player, 0.0)
        self.assertEqual(state.cut_time, 0.0)
        self.assertEqual(state.bleeding_time, 0.0)

    def test_a_healed_wound_makes_a_bandage_worth_xp_again(self):
        player = make_player()
        state = player.body[BodyPart.HAND_L]
        state.scratch_time = 0.0001
        state.bandage_xp_ready = False
        BodyEngine(random.Random(0)).minute(player, 0.0)
        self.assertTrue(state.bandage_xp_ready)

    def test_a_part_with_every_wound_healed_forgets_its_infection(self):
        player = make_player()
        state = player.body[BodyPart.HAND_L]
        state.scratch_time = 0.0001
        state.infected_wound = True
        state.wound_infection = 3.0
        BodyEngine(random.Random(0)).minute(player, 0.0)
        self.assertFalse(state.infected_wound)
        self.assertEqual(state.wound_infection, 0.0)

    def test_a_healed_scratch_gives_a_fact(self):
        player = make_player()
        player.body[BodyPart.HAND_L].scratch_time = 0.0001
        facts = BodyEngine(random.Random(0)).minute(player, 0.0)
        self.assertIn("The scratch on the left hand has healed.", facts)

    def test_a_bandaged_part_whose_bleeding_runs_out_gives_no_fact(self):
        player = make_player()
        state = player.body[BodyPart.FOREARM_L]
        state.cut_time = 5.0
        state.bleeding_time = 0.0001
        bandage(player, BodyPart.FOREARM_L, life=5.0)
        facts = BodyEngine(random.Random(0)).minute(player, 0.0)
        self.assertEqual(state.bleeding_time, 0.0)
        self.assertNotIn("The left forearm has stopped bleeding.", facts)

    def test_a_part_that_stops_bleeding_gives_a_fact(self):
        player = make_player()
        state = player.body[BodyPart.FOREARM_L]
        state.cut_time = 0.0001
        state.bleeding_time = 5.0
        facts = BodyEngine(random.Random(0)).minute(player, 0.0)
        self.assertIn("The left forearm has stopped bleeding.", facts)


class BandageWearTests(unittest.TestCase):
    """Spec 12, Bandage wear."""

    def hour(self, **fields):
        player = make_player()
        state = player.body[BodyPart.HAND_L]
        for name, value in fields.items():
            setattr(state, name, value)
        bandage(player, BodyPart.HAND_L, life=50.0)
        engine = BodyEngine(NeverInfectsRng(0))
        for minute in range(60):
            engine.minute(player, minute / 60)
        return 50.0 - state.bandage_life

    def test_an_open_bite_wears_a_bandage_at_one_point_zero_eight_an_hour(self):
        self.assertAlmostEqual(self.hour(bite_time=500.0), 1.08, places=3)

    def test_a_bleeding_part_wears_it_at_three_point_two_four(self):
        self.assertAlmostEqual(self.hour(bleeding_time=500.0), 3.24, places=3)

    def test_an_infected_wound_wears_it_at_two_point_one_six(self):
        self.assertAlmostEqual(
            self.hour(scratch_time=500.0, infected_wound=True, wound_infection=5.0),
            0.864 + 2.16,
            places=2,
        )

    def test_an_open_scratch_wears_it_at_zero_point_eight_six_four(self):
        self.assertAlmostEqual(self.hour(scratch_time=500.0), 0.864, places=3)

    def test_an_open_laceration_wears_it_at_zero_point_one_zero_eight(self):
        self.assertAlmostEqual(self.hour(cut_time=500.0), 0.108, places=3)

    def test_life_never_goes_below_zero_and_a_soaked_bandage_gives_a_fact(self):
        player = make_player()
        state = player.body[BodyPart.HAND_L]
        state.bite_time = 500.0
        bandage(player, BodyPart.HAND_L, life=0.0001)
        state.bandage_xp_ready = False
        facts = BodyEngine(random.Random(0)).minute(player, 0.0)
        self.assertEqual(state.bandage_life, 0.0)
        self.assertTrue(state.bandage_xp_ready)
        self.assertIn("The bandage on the left hand is soaked through.", facts)


class HealingTests(unittest.TestCase):
    """Spec 12, Healing."""

    def levels(self, hungry=0, thirst=0, sick=0):
        levels = {status_effect: 0 for status_effect in StatusEffect}
        levels[StatusEffect.HUNGRY] = hungry
        levels[StatusEffect.THIRST] = thirst
        levels[StatusEffect.SICK] = sick
        return levels

    def test_awake_healthy_heals_21_6_an_hour(self):
        self.assertAlmostEqual(heal_per_hour(self.levels(), asleep=False, fed=False), 21.6)

    def test_level_two_hungry_thirst_or_sick_heals_14_04(self):
        for kwargs in ({"hungry": 2}, {"thirst": 2}, {"sick": 2}):
            self.assertAlmostEqual(
                heal_per_hour(self.levels(**kwargs), asleep=False, fed=False), 14.04
            )

    def test_level_three_heals_8_64(self):
        for kwargs in ({"hungry": 3}, {"thirst": 3}, {"sick": 3}):
            self.assertAlmostEqual(
                heal_per_hour(self.levels(**kwargs), asleep=False, fed=False), 8.64
            )

    def test_hungry_or_thirst_at_four_heals_nothing(self):
        self.assertEqual(heal_per_hour(self.levels(hungry=4), asleep=False, fed=False), 0)
        self.assertEqual(heal_per_hour(self.levels(thirst=4), asleep=False, fed=False), 0)

    def test_sick_at_four_alone_does_not_slow_healing(self):
        self.assertAlmostEqual(heal_per_hour(self.levels(sick=4), asleep=False, fed=False), 21.6)

    def test_asleep_heals_216_an_hour(self):
        self.assertAlmostEqual(heal_per_hour(self.levels(), asleep=True, fed=False), 216.0)

    def test_the_well_fed_timer_adds_162(self):
        self.assertAlmostEqual(heal_per_hour(self.levels(), asleep=False, fed=True), 21.6 + 162.0)
        self.assertAlmostEqual(heal_per_hour(self.levels(), asleep=True, fed=True), 216.0 + 162.0)

    def test_asleep_and_starving_regains_nothing_food_included(self):
        self.assertEqual(heal_per_hour(self.levels(hungry=4), asleep=True, fed=True), 0)
        self.assertEqual(heal_per_hour(self.levels(thirst=4), asleep=True, fed=True), 0)

    def test_a_minute_of_healing_goes_to_the_hurt_part(self):
        player = make_player()
        player.body[BodyPart.HEAD].health = 50.0
        BodyEngine(random.Random(0)).minute(player, 0.0)
        self.assertAlmostEqual(player.body[BodyPart.HEAD].health, 50.0 + 21.6 / 60)

    def test_the_well_fed_timer_running_heals_faster_in_a_minute(self):
        player = make_player()
        player.food_eaten_timer = 100.0
        player.body[BodyPart.HEAD].health = 50.0
        BodyEngine(random.Random(0)).minute(player, 0.0)
        self.assertAlmostEqual(player.body[BodyPart.HEAD].health, 50.0 + (21.6 + 162.0) / 60)

    def test_no_status_effect_heals_health_by_itself_without_a_wound(self):
        player = make_player()
        BodyEngine(random.Random(0)).minute(player, 0.0)
        self.assertEqual(player.health, 100.0)


class StatusEffectDamageTests(unittest.TestCase):
    """Spec 12, The body minute: status effect damage moved from spec 02."""

    def hour(self, stat, value, minutes=60):
        player = make_player()
        player.stats.set(stat, value)
        before = player.health
        _, facts, death = run(player, minutes)
        return before - player.health, facts, death

    def per_hour(self, stat, value):
        lost, _, _ = self.hour(stat, value, minutes=1)
        return lost * 60

    def test_starving_costs_3_56_an_hour(self):
        self.assertAlmostEqual(self.per_hour(CharacterStat.HUNGER, 0.8), 3.564, delta=0.01)

    def test_dying_of_thirst_costs_17_82_an_hour(self):
        self.assertAlmostEqual(self.per_hour(CharacterStat.THIRST, 0.9), 17.82, delta=0.01)

    def test_fever_from_food_sickness_costs_178_2_an_hour(self):
        self.assertAlmostEqual(self.per_hour(CharacterStat.FOOD_SICKNESS, 95), 178.2, delta=0.01)

    def test_fever_from_the_infection_alone_costs_nothing_here(self):
        self.assertAlmostEqual(self.per_hour(CharacterStat.ZOMBIE_INFECTION, 95), 0.0, places=6)

    def test_a_weakening_fact_comes_once_per_cause(self):
        for stat, value, word in (
            (CharacterStat.HUNGER, 0.8, "hunger"),
            (CharacterStat.THIRST, 0.9, "thirst"),
            (CharacterStat.FOOD_SICKNESS, 95, "fever"),
        ):
            _, facts, _ = self.hour(stat, value)
            self.assertEqual(facts.count(f"Orton is weakening from {word}."), 1, stat)

    def test_dying_of_thirst_names_the_cause(self):
        player = make_player()
        player.stats.set(CharacterStat.THIRST, 0.9)
        minutes, _, death = run(player, 60 * 10)
        self.assertEqual(death, "Orton died of thirst.")
        self.assertLess(minutes, 60 * 6)

    def test_high_wound_infection_at_sick_four_costs_178_2_an_hour(self):
        player = make_player()
        for part in (BodyPart.HAND_L, BodyPart.HAND_R, BodyPart.FOREARM_L):
            state = player.body[part]
            state.infected_wound = True
            state.wound_infection = 3.5
            state.scratch_time = 100.0
        BodyEngine(random.Random(0)).minute(player, 0.0)
        wounds = (0.1 + 0.1 + 0.2) * 57.9 / 60
        self.assertAlmostEqual(100 - player.health, 178.2 / 60 + wounds, delta=0.01)


class DeathCauseTests(unittest.TestCase):
    """Spec 12, Death."""

    def test_wound_damage_names_the_wounds(self):
        player = make_player()
        for state in player.body.values():
            state.health = 1.0
        player.body[BodyPart.NECK].scratch_time = 50.0
        player.body[BodyPart.NECK].health = 0.5
        for part, state in player.body.items():
            if part is not BodyPart.NECK:
                state.health = 0.0
        player.body[BodyPart.NECK].health = 20.0
        minutes, _, death = run(player, 120)
        self.assertEqual(death, "Orton died of the wounds.")

    def test_health_helpers_agree_with_the_body(self):
        player = make_player()
        set_health(player, 70.0)
        self.assertAlmostEqual(overall_health(player.body), 70.0)


class PainMinuteTests(unittest.TestCase):
    """Spec 12, Pain."""

    def test_the_pain_stat_climbs_toward_the_target_over_minutes(self):
        player = make_player()
        player.body[BodyPart.FOREARM_L].extra_pain = 50.0
        engine = BodyEngine(random.Random(0))
        engine.minute(player, 0.0)
        target = 50 * 0.6
        first = player.stats.get(CharacterStat.PAIN)
        self.assertAlmostEqual(first, target - target * 0.7985, places=1)
        for index in range(1, 6):
            engine.minute(player, index / 60)
        self.assertGreater(player.stats.get(CharacterStat.PAIN), target * 0.6)

    def test_a_lower_target_drops_pain_at_once(self):
        player = make_player()
        player.stats.set(CharacterStat.PAIN, 80)
        BodyEngine(random.Random(0)).minute(player, 0.0)
        self.assertEqual(player.stats.get(CharacterStat.PAIN), 0)

    def test_extra_pain_falls_fifty_four_an_hour(self):
        player = make_player()
        player.body[BodyPart.HAND_L].extra_pain = 100.0
        run(player, 60)
        self.assertAlmostEqual(player.body[BodyPart.HAND_L].extra_pain, 46.0, places=3)

    def test_extra_pain_does_not_go_below_zero(self):
        player = make_player()
        player.body[BodyPart.HAND_L].extra_pain = 0.5
        run(player, 5)
        self.assertEqual(player.body[BodyPart.HAND_L].extra_pain, 0.0)

    def test_stiffness_falls_21_6_an_hour_when_no_region_is_still_draining(self):
        player = make_player()
        player.body[BodyPart.UPPERLEG_L].stiffness = 50.0
        run(player, 60)
        self.assertAlmostEqual(player.body[BodyPart.UPPERLEG_L].stiffness, 50.0 - 21.6, places=3)

    def test_stiffness_holds_while_a_region_is_still_draining(self):
        player = make_player()
        player.body[BodyPart.UPPERLEG_L].stiffness = 50.0
        player.exercise.future_stiffness["legs"] = 3.0
        run(player, 60)
        self.assertEqual(player.body[BodyPart.UPPERLEG_L].stiffness, 50.0)

    def test_painkillers_drop_pain_157_5_an_hour(self):
        player = make_player()
        player.body[BodyPart.NECK].extra_pain = 1000.0
        player.stats.set(CharacterStat.PAIN, 100.0)
        player.pain_effect_minutes = 48.0
        engine = BodyEngine(random.Random(0))
        for index in range(20):
            engine.minute(player, index / 60)
        self.assertAlmostEqual(
            player.stats.get(CharacterStat.PAIN), 100.0 - 157.5 * 20 / 60, places=2
        )
        self.assertAlmostEqual(player.pain_effect_minutes, 28.0)

    def test_the_painkiller_effect_lasts_48_minutes(self):
        player = make_player()
        player.pain_effect_minutes = 48.0
        engine = BodyEngine(random.Random(0))
        for index in range(48):
            engine.minute(player, index / 60)
        self.assertEqual(player.pain_effect_minutes, 0.0)

    def test_painkillers_do_not_let_pain_climb_to_its_target(self):
        player = make_player()
        player.body[BodyPart.NECK].extra_pain = 1000.0
        player.pain_effect_minutes = 10.0
        BodyEngine(random.Random(0)).minute(player, 0.0)
        self.assertEqual(player.stats.get(CharacterStat.PAIN), 0.0)

    def test_pain_climbs_again_once_the_painkillers_wear_off(self):
        player = make_player()
        player.body[BodyPart.NECK].extra_pain = 1000.0
        player.pain_effect_minutes = 1.0
        engine = BodyEngine(random.Random(0))
        engine.minute(player, 0.0)
        engine.minute(player, 1 / 60)
        self.assertGreater(player.stats.get(CharacterStat.PAIN), 100 * 0.1)


class WoundInfectionTests(unittest.TestCase):
    """Spec 12, Wound infection."""

    def per_hour(self, **fields) -> float:
        return infection_chance(PartState(**fields)) * 60

    def test_the_chance_table(self):
        self.assertAlmostEqual(self.per_hour(scratch_time=5.0), 0.68, delta=0.02)
        self.assertAlmostEqual(
            self.per_hour(scratch_time=5.0, bandage="item_bandage", bandage_life=3.0),
            0.34,
            delta=0.02,
        )
        self.assertAlmostEqual(self.per_hour(cut_time=5.0), 1.35, delta=0.02)
        self.assertAlmostEqual(
            self.per_hour(cut_time=5.0, bandage="item_bandage", bandage_life=3.0),
            0.45,
            delta=0.02,
        )

    def test_a_dirty_bandage_is_the_worst_for_either_wound(self):
        for fields in ({"scratch_time": 5.0}, {"cut_time": 5.0}):
            self.assertAlmostEqual(
                self.per_hour(bandage="item_dirty_bandage", bandage_life=0.0, **fields),
                1.35,
                delta=0.02,
            )

    def test_the_per_frame_chance_is_one_in_n_over_112_5_frames(self):
        self.assertAlmostEqual(
            infection_chance(PartState(scratch_time=5.0)), 1 - (1 - 1 / 10000) ** 112.5
        )
        self.assertAlmostEqual(
            infection_chance(PartState(cut_time=5.0)), 1 - (1 - 1 / 5000) ** 112.5
        )

    def test_an_unbandaged_scratch_infects_at_about_point_six_eight_per_hour(self):
        engine = BodyEngine(random.Random(7))
        player = make_player()
        state = player.body[BodyPart.HAND_L]
        infected = 0
        trials = 60000
        for _ in range(trials):
            state.scratch_time = 5.0
            state.infected_wound = False
            engine.minute(player, 0.0)
            infected += state.infected_wound
            state.health = 100.0
        self.assertAlmostEqual(infected / trials * 60, 0.68, delta=0.05)

    def test_an_alcohol_bandage_with_life_left_never_infects(self):
        engine = BodyEngine(random.Random(3))
        for _ in range(2000):
            player = make_player()
            state = player.body[BodyPart.HAND_L]
            state.cut_time = 5.0
            bandage(player, BodyPart.HAND_L, life=100.0, alcoholic=True)
            engine.minute(player, 0.0)
            self.assertFalse(state.infected_wound)

    def test_a_spent_alcohol_bandage_no_longer_protects(self):
        self.assertAlmostEqual(
            self.per_hour(
                cut_time=5.0,
                bandage="item_sterilized_bandage",
                bandage_life=0.0,
                bandage_alcoholic=True,
            ),
            1.35,
            delta=0.02,
        )

    def test_a_zombie_infection_part_and_an_infected_wound_do_not_roll(self):
        engine = BodyEngine(random.Random(3))
        player = make_player()
        player.body[BodyPart.HAND_L].cut_time = 5.0
        player.body[BodyPart.HAND_L].zombie_infected = True
        player.body[BodyPart.HAND_R].cut_time = 5.0
        player.body[BodyPart.HAND_R].infected_wound = True
        for _ in range(3000):
            engine.minute(player, 0.0)
        self.assertFalse(player.body[BodyPart.HAND_L].infected_wound)

    def test_each_eligible_part_draws_one_roll_per_minute_in_part_order(self):
        class CountingRng(random.Random):
            draws = 0

            def random(self):
                CountingRng.draws += 1
                return 0.5

        player = make_player()
        player.body[BodyPart.HAND_L].scratch_time = 5.0
        player.body[BodyPart.FOOT_R].cut_time = 5.0
        player.body[BodyPart.NECK].health = 100.0
        BodyEngine(CountingRng(0)).minute(player, 0.0)
        self.assertEqual(CountingRng.draws, 2)

    def test_an_infected_wound_rises_point_one_oh_eight_an_hour(self):
        player = make_player()
        state = player.body[BodyPart.HAND_L]
        state.scratch_time = 500.0
        state.infected_wound = True
        state.wound_infection = 1.0
        run(player, 60)
        self.assertAlmostEqual(state.wound_infection, 1.0 + 0.108, places=3)

    def test_a_zombie_infection_wound_rises_two_point_one_six_an_hour(self):
        player = make_player()
        state = player.body[BodyPart.HAND_L]
        state.scratch_time = 500.0
        state.infected_wound = True
        state.zombie_infected = True
        state.wound_infection = 1.0
        run(player, 60)
        self.assertAlmostEqual(state.wound_infection, 1.0 + 2.16, places=3)

    def test_infection_is_capped_at_ten(self):
        player = make_player()
        state = player.body[BodyPart.HAND_L]
        state.scratch_time = 500.0
        state.infected_wound = True
        state.wound_infection = 9.99
        state.zombie_infected = True
        run(player, 60)
        self.assertEqual(state.wound_infection, 10.0)

    def test_disinfectant_cures_four_levels_over_about_one_point_eight_five_hours(self):
        player = make_player()
        state = player.body[BodyPart.HAND_L]
        state.scratch_time = 500.0
        state.infected_wound = True
        state.wound_infection = 4.0
        state.alcohol = 4.0
        minutes = 0
        engine = BodyEngine(random.Random(0))
        while state.infected_wound and minutes < 300:
            engine.minute(player, minutes / 60)
            minutes += 1
        self.assertAlmostEqual(minutes / 60, 4 / 2.16, delta=0.05)
        self.assertEqual(state.alcohol, 0.0)

    def test_alcohol_on_a_wound_that_is_not_infected_falls_two_point_one_six_an_hour(self):
        player = make_player()
        state = player.body[BodyPart.HAND_L]
        state.alcohol = 4.0
        run(player, 60)
        self.assertAlmostEqual(state.alcohol, 4.0 - 2.16, places=3)

    def test_antibiotics_cure_and_fall_ten_point_eight_an_hour_plus_two_point_one_six_per_wound(
        self,
    ):
        player = make_player()
        state = player.body[BodyPart.HAND_L]
        state.scratch_time = 500.0
        state.infected_wound = True
        state.wound_infection = 8.0
        player.reduce_infection_power = 50.0
        run(player, 60)
        self.assertAlmostEqual(state.wound_infection, 8.0 - 2.16, places=3)
        self.assertAlmostEqual(player.reduce_infection_power, 50.0 - 10.8 - 2.16, places=3)

    def test_antibiotic_power_does_not_go_below_zero(self):
        player = make_player()
        player.reduce_infection_power = 0.05
        run(player, 30)
        self.assertEqual(player.reduce_infection_power, 0.0)

    def test_an_alcohol_bandage_lowers_infection_six_point_four_eight_an_hour(self):
        player = make_player()
        state = player.body[BodyPart.HAND_L]
        state.scratch_time = 500.0
        state.infected_wound = True
        state.wound_infection = 9.0
        bandage(player, BodyPart.HAND_L, life=100.0, alcoholic=True)
        run(player, 60)
        self.assertAlmostEqual(state.wound_infection, 9.0 + 0.108 - 6.48, places=3)

    def test_infection_at_zero_or_below_ends_the_infection_and_floors_at_minus_two(self):
        player = make_player()
        state = player.body[BodyPart.HAND_L]
        state.scratch_time = 500.0
        state.infected_wound = True
        state.wound_infection = 0.01
        state.alcohol = 4.0
        run(player, 5)
        self.assertFalse(state.infected_wound)
        self.assertGreaterEqual(state.wound_infection, -2.0)

    def test_a_bite_is_infected_from_the_start_and_stays_so(self):
        player = make_player()
        land_wound(player, "bite", BodyPart.HAND_L, 5.0, False, random.Random(0))
        run(player, 30)
        self.assertTrue(player.body[BodyPart.HAND_L].infected_wound)


class StressTests(unittest.TestCase):
    """Spec 12, Stress."""

    def stress_after_hour(self, player) -> float:
        run(player, 60)
        return player.stats.get(CharacterStat.STRESS)

    def test_an_open_unbandaged_bite_adds_point_one_eight_an_hour(self):
        player = make_player()
        player.body[BodyPart.HAND_L].bite_time = 500.0
        self.assertAlmostEqual(self.stress_after_hour(player), 0.18, places=3)

    def test_an_open_unbandaged_scratch_adds_point_one_eight_an_hour(self):
        player = make_player()
        player.body[BodyPart.HAND_L].scratch_time = 500.0
        self.assertAlmostEqual(self.stress_after_hour(player), 0.18, places=3)

    def test_each_source_counts_once_however_many_parts_have_it(self):
        player = make_player()
        player.body[BodyPart.HAND_L].scratch_time = 500.0
        player.body[BodyPart.HAND_R].scratch_time = 500.0
        self.assertAlmostEqual(self.stress_after_hour(player), 0.18, places=3)

    def test_a_bite_and_a_scratch_together_add_point_three_six(self):
        player = make_player()
        player.body[BodyPart.HAND_L].bite_time = 500.0
        player.body[BodyPart.HAND_R].scratch_time = 500.0
        self.assertAlmostEqual(self.stress_after_hour(player), 0.36, places=3)

    def test_bandaging_stops_the_wound_sources(self):
        player = make_player()
        player.body[BodyPart.HAND_L].bite_time = 500.0
        player.body[BodyPart.HAND_R].scratch_time = 500.0
        bandage(player, BodyPart.HAND_L, life=1000.0)
        bandage(player, BodyPart.HAND_R, life=1000.0)
        self.assertAlmostEqual(self.stress_after_hour(player), 0.0, places=6)

    def test_the_zombie_infection_infection_adds_point_one_eight_an_hour(self):
        player = make_player()
        player.body[BodyPart.HAND_L].zombie_infected = True
        self.assertAlmostEqual(self.stress_after_hour(player), 0.18, places=3)

    def test_a_healed_laceration_adds_none(self):
        player = make_player()
        player.body[BodyPart.HAND_L].cut_time = 500.0
        self.assertEqual(self.stress_after_hour(player), 0.0)


class ZombieInfectionTests(unittest.TestCase):
    """Spec 12, Zombie Infection."""

    def infect(self, traits=(), seed=0, at_hours=10.0) -> PlayerEntity:
        player = make_player(traits)
        player.body[BodyPart.HAND_L].zombie_infected = True
        BodyEngine(random.Random(seed)).minute(player, at_hours)
        return player

    def test_onset_records_when_and_how_long(self):
        player = self.infect(at_hours=10.0)
        self.assertEqual(player.zombie_infection_since, 10.0)
        self.assertTrue(48 <= player.zombie_infection_hours <= 72)

    def test_resilient_takes_one_and_a_quarter_times_as_long(self):
        for seed in range(50):
            player = self.infect(["resilient"], seed=seed)
            self.assertTrue(
                60 <= player.zombie_infection_hours <= 90, player.zombie_infection_hours
            )

    def test_prone_to_illness_takes_three_quarters_as_long(self):
        for seed in range(50):
            player = self.infect(["pronetoillness"], seed=seed)
            self.assertTrue(
                36 <= player.zombie_infection_hours <= 54, player.zombie_infection_hours
            )

    def test_onset_happens_once(self):
        player = self.infect(at_hours=10.0)
        first = (player.zombie_infection_since, player.zombie_infection_hours)
        BodyEngine(random.Random(5)).minute(player, 20.0)
        self.assertEqual((player.zombie_infection_since, player.zombie_infection_hours), first)

    def test_no_zombie_infection_part_means_no_infection(self):
        player = make_player()
        BodyEngine(random.Random(0)).minute(player, 10.0)
        self.assertIsNone(player.zombie_infection_since)
        self.assertEqual(player.stats.get(CharacterStat.ZOMBIE_INFECTION), 0)

    def test_at_fifty_percent_health_is_at_most_93_75_and_the_stat_reads_fifty(self):
        player = make_player()
        player.zombie_infection_since = 0.0
        player.zombie_infection_hours = 60.0
        BodyEngine(random.Random(0)).minute(player, 30.0)
        self.assertAlmostEqual(player.health, 93.75, places=2)
        self.assertAlmostEqual(player.stats.get(CharacterStat.ZOMBIE_INFECTION), 50.0)

    def test_the_cap_table(self):
        for fraction, cap in ((0.75, 68.4), (0.9, 34.4)):
            player = make_player()
            player.zombie_infection_since = 0.0
            player.zombie_infection_hours = 100.0
            BodyEngine(random.Random(0)).minute(player, 100.0 * fraction)
            self.assertAlmostEqual(player.health, cap, delta=0.05)

    def test_no_cap_applies_while_the_cap_is_above_99(self):
        for fraction in (0.1, 0.25):
            player = make_player()
            player.zombie_infection_since = 0.0
            player.zombie_infection_hours = 100.0
            BodyEngine(random.Random(0)).minute(player, 100.0 * fraction)
            self.assertEqual(player.health, 100.0)

    def test_at_one_hundred_percent_the_player_dies_of_the_zombie_infection_infection(self):
        player = make_player()
        player.zombie_infection_since = 0.0
        player.zombie_infection_hours = 50.0
        engine = BodyEngine(random.Random(0))
        engine.minute(player, 50.0)
        self.assertEqual(player.health, 0.0)
        self.assertEqual(engine.death_fact, "Orton died of the zombie infection.")
        self.assertEqual(player.stats.get(CharacterStat.ZOMBIE_INFECTION), 100.0)

    def test_the_zombie_infection_infection_kills_even_with_a_part_already_at_zero(self):
        player = make_player()
        player.body[BodyPart.FOREARM_L].health = 0.0
        player.zombie_infection_since = 0.0
        player.zombie_infection_hours = 50.0
        engine = BodyEngine(random.Random(0))
        engine.minute(player, 50.0)
        self.assertEqual(player.health, 0.0)
        self.assertEqual(engine.death_fact, "Orton died of the zombie infection.")

    def test_the_infection_feeds_the_sick_status_effect(self):
        player = make_player()
        player.zombie_infection_since = 0.0
        player.zombie_infection_hours = 100.0
        BodyEngine(random.Random(0)).minute(player, 51.0)
        self.assertEqual(player_status_effect_levels(player)[StatusEffect.SICK], 2)

    def test_the_health_cap_does_not_stop_healing_below_it(self):
        player = make_player()
        player.zombie_infection_since = 0.0
        player.zombie_infection_hours = 100.0
        player.body[BodyPart.HEAD].health = 10.0
        engine = BodyEngine(random.Random(0))
        engine.minute(player, 50.0)
        self.assertLessEqual(player.health, 93.75 + 1e-9)


class ThermalCapTests(unittest.TestCase):
    """Spec 12, The body minute: step 0."""

    def test_a_stage_of_point_four_caps_health_at_sixty(self):
        player = make_player()
        player.thermal.thermal_damage = 0.4
        BodyEngine(random.Random(0)).minute(player, 0.0)
        self.assertAlmostEqual(player.health, 60.0, delta=0.2)  # the minute's healing lands after

    def test_a_stage_of_one_kills(self):
        player = make_player()
        player.thermal.thermal_damage = 1.0
        player.stats.set(CharacterStat.TEMPERATURE, 25)
        engine = BodyEngine(random.Random(0))
        engine.minute(player, 0.0)
        self.assertEqual(player.health, 0.0)
        self.assertEqual(engine.death_fact, "Orton died of the cold.")

    def test_a_stage_of_one_kills_even_with_a_part_already_at_zero(self):
        player = make_player()
        player.body[BodyPart.FOREARM_L].health = 0.0
        player.thermal.thermal_damage = 1.0
        player.stats.set(CharacterStat.TEMPERATURE, 25)
        engine = BodyEngine(random.Random(0))
        engine.minute(player, 0.0)
        self.assertEqual(player.health, 0.0)
        self.assertEqual(engine.death_fact, "Orton died of the cold.")

    def test_heat_names_the_heat(self):
        player = make_player()
        player.thermal.thermal_damage = 1.0
        player.stats.set(CharacterStat.TEMPERATURE, 40)
        engine = BodyEngine(random.Random(0))
        engine.minute(player, 0.0)
        self.assertEqual(engine.death_fact, "Orton died of the heat.")

    def test_no_stage_means_no_cap(self):
        player = make_player()
        BodyEngine(random.Random(0)).minute(player, 0.0)
        self.assertEqual(player.health, 100.0)


if __name__ == "__main__":
    unittest.main()
