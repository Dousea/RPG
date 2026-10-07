"""Spec 06, Set point and metabolic rate; Heat per node; The core; The skin; Integration;
Body multipliers; Thermal damage."""

import unittest

from data.items import ITEMS
from data.thermal import Metabolic
from managers.climate import FeltAir
from managers.stats.drivers import StatContext
from managers.stats.engine import StatsEngine
from managers.stats.status_effects import status_effect_level
from managers.thermoregulator import (
    NodeClothing,
    ThermalInputs,
    ThermoregulatorDriver,
    advance_core,
    body_heat_delta,
    body_multipliers,
    energy_term,
    health_cap,
    metabolic_target,
    movement_modifier,
    node_heat,
    node_responses,
    part_clothing,
    real_metabolic_rate,
    relax,
    skin_limits,
    skin_rate,
    skin_target,
    thermal_damage_tick,
    thermal_step,
)
from modules.body import BodyLocation, BodyPart
from modules.entity.item import ItemEntity
from modules.entity.player import PlayerEntity
from modules.item import ClothingItem
from modules.stats import CharacterStat, StatusEffect
from modules.thermal import ThermalState
from modules.weather import WeatherSample


def weather(temperature, wind=0.0, humidity=0.5):
    return WeatherSample(
        air_temperature=temperature,
        humidity=humidity,
        wind_intensity=wind,
        wind_angle=0.0,
        cloud_intensity=0.0,
        precipitation_intensity=0.0,
        precipitation_is_snow=False,
        fog_intensity=0.0,
        daylight=1.0,
    )


def shirt_and_jeans() -> dict[BodyLocation, ItemEntity]:
    return {
        BodyLocation.TSHIRT: ItemEntity(item=ITEMS["item_tshirt"]),
        BodyLocation.PANTS: ItemEntity(item=ITEMS["item_jeans"]),
    }


def make_player(worn=None) -> PlayerEntity:
    player = PlayerEntity(name="Orton", current_location_id="zone_home")
    player.worn = worn if worn is not None else {}
    return player


def still_inputs(temperature=22.0, chill=None, clothing=None) -> ThermalInputs:
    return ThermalInputs(
        air=FeltAir(temperature, temperature if chill is None else chill),
        clothing=clothing or {},
    )


def run_driver(player, minutes, sample, *, indoors, step=10, **ctx):
    engine = StatsEngine([ThermoregulatorDriver()])
    cores = []
    for _ in range(minutes // step):
        engine.advance(player, step, StatContext(weather=sample, indoors=indoors, **ctx))
        cores.append(player.stats.get(CharacterStat.TEMPERATURE))
    return cores


def coat(insulation, wind=0.0, wetness=0.0, condition=None) -> ItemEntity:
    item = ClothingItem(
        id="test_coat",
        name="coat",
        description="",
        max_hit_points=10,
        tags=[],
        body_location=BodyLocation.JACKET,
        covers=frozenset({BodyPart.TORSO_UPPER}),
        insulation=insulation,
        wind_resistance=wind,
        water_resistance=0.0,
        weight=1.0,
    )
    entity = ItemEntity(item=item, wetness=wetness)
    if condition is not None:
        entity.hit_points = condition
    return entity


class MetabolicTests(unittest.TestCase):
    """Spec 06, Set point and metabolic rate."""

    def test_targets_from_the_met_table(self):
        self.assertEqual(metabolic_target(Metabolic.DEFAULT, 1.0, 1.0), 1.5)
        self.assertEqual(metabolic_target(Metabolic.WALKING_5KMH, 1.0, 1.0), 3.1)
        self.assertEqual(metabolic_target(Metabolic.MEDIUM_WORK, 1.0, 1.0), 3.9)
        self.assertEqual(metabolic_target(Metabolic.HEAVY_WORK, 1.0, 1.0), 6.0)
        self.assertEqual(metabolic_target(Metabolic.LIGHT_DOMESTIC, 1.0, 1.0), 1.6)
        self.assertEqual(metabolic_target(Metabolic.HEAVY_DOMESTIC, 1.0, 1.0), 2.0)
        self.assertEqual(metabolic_target(Metabolic.USING_TOOLS, 1.0, 1.0), 2.5)
        self.assertEqual(metabolic_target(Metabolic.LIGHT_WORK, 1.0, 1.0), 3.2)
        self.assertEqual(metabolic_target(Metabolic.WALKING_2KMH, 1.0, 1.0), 1.9)
        self.assertEqual(metabolic_target(Metabolic.RUNNING_10KMH, 1.0, 1.0), 6.9)
        self.assertEqual(metabolic_target(Metabolic.RUNNING_15KMH, 1.0, 1.0), 9.5)
        self.assertEqual(metabolic_target(Metabolic.FITNESS, 1.0, 1.0), 6.0)
        self.assertEqual(metabolic_target(Metabolic.FITNESS_HEAVY, 1.0, 1.0), 9.0)
        self.assertEqual(metabolic_target(Metabolic.DEFAULT_EXERCISE, 1.0, 1.0), 3.0)

    def test_the_highest_candidate_wins_and_nothing_lowers_the_target(self):
        self.assertEqual(metabolic_target(Metabolic.HEAVY_WORK, 0.0, 1.0), 6.0)
        self.assertEqual(metabolic_target(Metabolic.DEFAULT, 0.0, 1.0), 3.0)

    def test_exercise_term_is_three_times_energy_at_endurance_zero(self):
        self.assertEqual(metabolic_target(Metabolic.DEFAULT, 0.0, 1.0), 3.0)
        self.assertAlmostEqual(metabolic_target(Metabolic.DEFAULT, 0.0, 0.8), 2.4)
        self.assertAlmostEqual(metabolic_target(Metabolic.DEFAULT, 0.5, 1.0), 1.5)
        self.assertAlmostEqual(metabolic_target(Metabolic.DEFAULT, 0.25, 1.0), 2.25)

    def test_full_carried_weight_multiplies_the_target_by_1_35(self):
        self.assertAlmostEqual(metabolic_target(Metabolic.DEFAULT, 1.0, 1.0, 1.0), 1.5 * 1.35)
        self.assertAlmostEqual(metabolic_target(Metabolic.DEFAULT, 1.0, 1.0, 0.5), 1.5 * 1.0875)
        self.assertAlmostEqual(metabolic_target(Metabolic.DEFAULT, 1.0, 1.0, 3.0), 1.5 * 1.35)

    def test_the_target_caps_at_10_3_before_the_carry_term(self):
        self.assertAlmostEqual(metabolic_target(Metabolic.RUNNING_15KMH, 0.0, 1.0, 1.0), 9.5 * 1.35)

    def test_energy_term_from_hunger_and_fatigue(self):
        self.assertEqual(energy_term(0.0, 0.0), 1.0)
        self.assertAlmostEqual(energy_term(0.5, 0.0), 0.6 * (1 - (0.2 + 0.15)) + 0.4)
        self.assertAlmostEqual(energy_term(0.0, 1.0), 0.6)
        self.assertAlmostEqual(energy_term(1.0, 1.0), 0.0)

    def test_rate_eases_up_at_0_001_per_frame(self):
        self.assertAlmostEqual(relax(1.0, 3.0, 0.001, 112.5), 3 - 2 * (1 - 0.001) ** 112.5)

    def test_rate_eases_down_at_0_0004_per_frame(self):
        state = ThermalState()
        state.metabolic_rate = 3.0
        thermal_step(state, 37.0, still_inputs(), 112.5)
        self.assertAlmostEqual(state.metabolic_rate, 1.5 + 1.5 * (1 - 0.0004) ** 112.5)

    def test_rate_eases_up_inside_a_thermal_step(self):
        state = ThermalState()
        inp = still_inputs()
        inp.target_met = 3.1
        thermal_step(state, 37.0, inp, 112.5)
        self.assertAlmostEqual(state.metabolic_rate, 3.1 - 1.6 * (1 - 0.001) ** 112.5)

    def test_real_rate_is_rate_times_0_2_plus_0_8_energy(self):
        self.assertAlmostEqual(real_metabolic_rate(3.0, 1.0, 1.0), 3.0)
        self.assertAlmostEqual(real_metabolic_rate(3.0, 0.5, 1.0), 3.0 * 0.6)
        self.assertAlmostEqual(real_metabolic_rate(2.0, 1.0, 0.66), 2.0 * (0.2 + 0.8 * 0.66))

    def test_movement_modifier_by_hypothermia_and_hyperthermia(self):
        self.assertEqual(movement_modifier(0, 0), 1.0)
        self.assertEqual(movement_modifier(1, 0), 1.0)
        self.assertEqual(movement_modifier(2, 0), 0.66)
        self.assertEqual(movement_modifier(3, 0), 0.33)
        self.assertEqual(movement_modifier(4, 0), 0.0)
        self.assertEqual(movement_modifier(4, 2), 0.66)
        self.assertEqual(movement_modifier(1, 1), 1.0)
        self.assertEqual(movement_modifier(0, 2), 1.0)
        self.assertEqual(movement_modifier(0, 4), 1.0)
        self.assertEqual(movement_modifier(1, 3), 0.33)

    def test_initial_rate_is_the_default_target(self):
        self.assertEqual(ThermalState().metabolic_rate, 1.5)


class ClothingPerNodeTests(unittest.TestCase):
    """Spec 06, Clothing per node."""

    def test_an_uncovered_part_has_no_insulation_or_wind_resistance(self):
        self.assertEqual(part_clothing([], BodyPart.HEAD), NodeClothing())

    def test_one_dry_layer_is_the_true_values_plus_the_base(self):
        c = part_clothing([coat(0.5, 0.4)], BodyPart.TORSO_UPPER)
        self.assertAlmostEqual(c.insulation, 2 * 0.5 + 0.5 * 0.5**3 + 0.05)
        self.assertAlmostEqual(c.wind_resistance, 0.4 + 0.5 * 0.4**2 + 0.05)

    def test_layers_sum_and_each_adds_the_base(self):
        c = part_clothing([coat(0.5), coat(0.2)], BodyPart.TORSO_UPPER)
        self.assertAlmostEqual(c.insulation, 1.0625 + 0.404 + 0.1)

    def test_wetness_scales_insulation_by_1_minus_0_75_w_and_wind_by_0_45_w(self):
        dry = part_clothing([coat(0.5, 0.4)], BodyPart.TORSO_UPPER)
        wet = part_clothing([coat(0.5, 0.4, wetness=100)], BodyPart.TORSO_UPPER)
        half = part_clothing([coat(0.5, 0.4, wetness=40)], BodyPart.TORSO_UPPER)
        self.assertAlmostEqual(wet.insulation - 0.05, (dry.insulation - 0.05) * 0.25)
        self.assertAlmostEqual(wet.wind_resistance - 0.05, (dry.wind_resistance - 0.05) * 0.55)
        self.assertAlmostEqual(half.insulation - 0.05, (dry.insulation - 0.05) * (1 - 0.75 * 0.4))
        self.assertAlmostEqual(
            half.wind_resistance - 0.05, (dry.wind_resistance - 0.05) * (1 - 0.45 * 0.4)
        )
        self.assertEqual(dry.wetness, 0.0)
        self.assertEqual(wet.wetness, 1.0)

    def test_condition_scales_by_0_5_plus_0_5_condition(self):
        worn = part_clothing([coat(0.5, 0.4, condition=0)], BodyPart.TORSO_UPPER)
        whole = part_clothing([coat(0.5, 0.4)], BodyPart.TORSO_UPPER)
        self.assertAlmostEqual(worn.insulation - 0.05, (whole.insulation - 0.05) * 0.5)
        half = part_clothing([coat(0.5, 0.4, condition=5)], BodyPart.TORSO_UPPER)
        self.assertAlmostEqual(half.insulation - 0.05, (whole.insulation - 0.05) * 0.75)

    def test_a_holed_layer_adds_nothing_but_still_counts(self):
        holed = coat(0.5, 0.4, wetness=100)
        holed.holes.add(BodyPart.TORSO_UPPER)
        c = part_clothing([holed, coat(0.2)], BodyPart.TORSO_UPPER)
        self.assertAlmostEqual(c.insulation, 0.404 + 0.1)
        self.assertAlmostEqual(c.wetness, 0.5)

    def test_wetness_is_the_layer_average(self):
        c = part_clothing([coat(0.5, wetness=100), coat(0.2)], BodyPart.TORSO_UPPER)
        self.assertAlmostEqual(c.wetness, 0.5)

    def test_items_with_no_insulation_and_no_wind_resistance_are_not_layers(self):
        self.assertEqual(
            part_clothing([coat(0.0, 0.0, wetness=100)], BodyPart.TORSO_UPPER), NodeClothing()
        )


class HeatPerNodeTests(unittest.TestCase):
    """Spec 06, Heat per node."""

    def heat(self, part=BodyPart.TORSO_UPPER, skin=30.0, primary=0.0, secondary=0.0, **inputs):
        state = ThermalState()
        state.skin[part] = skin
        state.primary[part] = primary
        state.secondary[part] = secondary
        inp = ThermalInputs(**inputs)
        from managers.thermoregulator import humidity_mod, prim_heat_mod

        return node_heat(part, state, inp, prim_heat_mod(inp), humidity_mod(inp.humidity))

    def test_bare_node_exchanges_0_3_of_the_gap_times_skin_surface(self):
        h = self.heat(air=FeltAir(22.0, 22.0))
        self.assertAlmostEqual(h, (22 - 30) * 0.3 * 0.18)

    def test_warm_air_gives_heat_in(self):
        h = self.heat(air=FeltAir(40.0, 40.0), skin=30.0)
        self.assertAlmostEqual(h, 10 * 0.3 * 0.18)

    def test_insulation_divides_the_exchange(self):
        h = self.heat(air=FeltAir(22.0, 22.0), clothing={BodyPart.TORSO_UPPER: NodeClothing(1.0)})
        self.assertAlmostEqual(h, (22 - 30) * 0.3 / 2 * 0.18)

    def test_wind_chill_reaches_the_skin_through_the_wind_resistance(self):
        bare = self.heat(air=FeltAir(22.0, 12.0))
        wrapped = self.heat(
            air=FeltAir(22.0, 12.0), clothing={BodyPart.TORSO_UPPER: NodeClothing(0.0, 1.0)}
        )
        self.assertAlmostEqual(bare, (12 - 30) * 0.3 * 0.18)
        self.assertAlmostEqual(wrapped, (17 - 30) * 0.3 * 0.18)

    def test_wet_skin_loses_heat_faster_and_gains_it_slower(self):
        cold = self.heat(air=FeltAir(22.0, 22.0), body_wetness=0.5)
        self.assertAlmostEqual(cold, (22 - 30) * (1 + 0.75 * 0.5) * 0.3 * 0.18)
        warm = self.heat(air=FeltAir(40.0, 40.0), body_wetness=0.5)
        self.assertAlmostEqual(warm, 10 / (1 + 3 * 0.5) * 0.3 * 0.18)

    def test_shivering_adds_heat_by_energy(self):
        wt = (min(max((80 / 75 - 0.5) * 0.666, 0), 1) - 0.5) * 2
        h = self.heat(air=FeltAir(30.0, 30.0), skin=30.0, primary=-0.5, energy=1.0)
        self.assertAlmostEqual(h, 1.5 * 0.5 * 0.18 * 1.0 * (1 + 0.2 * wt))
        tired = self.heat(air=FeltAir(30.0, 30.0), skin=30.0, primary=-0.5, energy=0.0)
        self.assertAlmostEqual(tired, 1.5 * 0.5 * 0.18 * 0.2 * (1 + 0.2 * wt))
        self.assertAlmostEqual(wt, -0.2452, places=3)

    def test_the_cooling_response_removes_heat(self):
        wt = -0.2452
        h = self.heat(air=FeltAir(40.0, 40.0), skin=40.0, primary=0.5, fluids=1.0, set_point=37.0)
        prim_heat_mod = 0.0
        self.assertAlmostEqual(
            h,
            -1.5 * 0.5 * 0.18 * 1.0 * (0.1 + 0.9 * prim_heat_mod) * 1.0 * (1 - 0.2 * wt),
            places=3,
        )

    def test_dehydration_weakens_the_cooling_response(self):
        full = self.heat(air=FeltAir(30.0, 30.0), skin=30.0, primary=0.5, fluids=1.0)
        dry = self.heat(air=FeltAir(30.0, 30.0), skin=30.0, primary=0.5, fluids=0.0)
        self.assertAlmostEqual(dry / full, 0.2, places=6)

    def test_prim_heat_mod_fades_as_the_air_nears_set_point_plus_2(self):
        from managers.thermoregulator import prim_heat_mod

        self.assertEqual(prim_heat_mod(still_inputs(30.0)), 1.0)
        self.assertEqual(prim_heat_mod(still_inputs(39.0)), 0.0)
        self.assertAlmostEqual(prim_heat_mod(still_inputs(37.0)), 1 - (37 - 35) / 4)
        self.assertEqual(prim_heat_mod(still_inputs(30.0, chill=34.0)), 1.0)

    def test_humidity_mod_only_drops_above_half(self):
        from managers.thermoregulator import humidity_mod

        self.assertEqual(humidity_mod(0.3), 1.0)
        self.assertEqual(humidity_mod(0.5), 1.0)
        self.assertAlmostEqual(humidity_mod(0.8), 0.4)

    def test_sweating_removes_heat_and_humidity_weakens_it(self):
        dry_air = self.heat(
            air=FeltAir(30.0, 30.0), skin=30.0, secondary=0.5, fluids=1.0, humidity=0.5
        )
        wet_air = self.heat(
            air=FeltAir(30.0, 30.0), skin=30.0, secondary=0.5, fluids=1.0, humidity=1.0
        )
        wt = -0.2452
        self.assertAlmostEqual(
            dry_air, -10.3 * 0.75 * 0.5 * 0.18 * 1.0 * 1.0 * (1 - 0.2 * wt), places=3
        )
        self.assertAlmostEqual(wet_air / dry_air, 0.85, places=6)

    def test_the_secondary_warming_response_uses_the_weaker_energy_mix(self):
        h = self.heat(air=FeltAir(30.0, 30.0), skin=30.0, secondary=-0.5, energy=0.0)
        wt = -0.2452
        self.assertAlmostEqual(h, 1.5 * 0.5 * 0.18 * 0.1 * (1 + 0.2 * wt), places=3)

    def test_fitness_scales_the_responses_by_one_plus_0_2_fit(self):
        base = self.heat(air=FeltAir(30.0, 30.0), skin=30.0, primary=-0.5)
        fit = self.heat(air=FeltAir(30.0, 30.0), skin=30.0, primary=-0.5, fitness=1.0)
        self.assertAlmostEqual(fit / base, 1.2)

    def test_weight_term_is_zero_at_93_8_kg_and_clamped(self):
        from managers.thermoregulator import weight_term

        self.assertAlmostEqual(weight_term(80), -0.2452, places=3)
        self.assertAlmostEqual(weight_term(1000), 1.0)
        self.assertAlmostEqual(weight_term(0), -1.0)


class CoreTests(unittest.TestCase):
    """Spec 06, The core."""

    def test_delta_is_total_heat_times_0_00025_per_frame(self):
        self.assertAlmostEqual(advance_core(37.0, 4.0, 37.0, 100), 37.0 + 0.001 * 100)

    def test_a_delta_above_0_001_moves_the_core_by_half(self):
        self.assertAlmostEqual(advance_core(37.0, 8.0, 37.0, 100), 37.0 + 0.001 * 100)
        self.assertAlmostEqual(advance_core(37.0, 8.0, 37.0, 1), 37.001)
        self.assertAlmostEqual(advance_core(37.0, 3.9, 37.0, 1), 37.000975)

    def test_cooling_above_set_point_is_scaled_by_one_plus_gap_over_two(self):
        self.assertAlmostEqual(advance_core(39.0, -2.0, 37.0, 1), 39.0 - 0.0005 * 2.0)

    def test_heating_below_set_point_is_scaled_by_one_plus_gap_over_four(self):
        self.assertAlmostEqual(advance_core(35.0, 4.0, 37.0, 1), 35.0 + 0.001 * 1.5 / 2)

    def test_cooling_below_and_heating_above_are_not_scaled(self):
        self.assertAlmostEqual(advance_core(35.0, -4.0, 37.0, 1), 35.0 - 0.001)
        self.assertAlmostEqual(advance_core(39.0, 4.0, 37.0, 1), 39.0 + 0.001)

    def test_the_core_clamps_at_20_and_the_reported_core_at_40(self):
        self.assertEqual(advance_core(20.5, -1000.0, 37.0, 1000), 20.0)
        self.assertEqual(advance_core(39.99, 1000.0, 37.0, 1000), 40.0)

    def test_body_heat_delta_below_the_set_point(self):
        self.assertAlmostEqual(body_heat_delta(36.5, 37.0), -0.4)
        self.assertAlmostEqual(body_heat_delta(36.0, 37.0), -0.8)
        self.assertAlmostEqual(body_heat_delta(35.0, 37.0), -0.8 - 0.2 * 0.1)
        self.assertAlmostEqual(body_heat_delta(26.0, 37.0), -1.0)
        self.assertAlmostEqual(body_heat_delta(21.0, 37.0), -1.0)
        self.assertAlmostEqual(body_heat_delta(24.0, 37.0), -1.0)

    def test_body_heat_delta_at_and_above_the_set_point(self):
        self.assertAlmostEqual(body_heat_delta(37.0, 37.0), 0.0)
        self.assertAlmostEqual(body_heat_delta(37.5, 37.0), 0.5)
        self.assertAlmostEqual(body_heat_delta(40.0, 37.0), 1.0)


class SkinTests(unittest.TestCase):
    """Spec 06, The skin."""

    def test_primary_scales_with_distance_when_cold_and_with_its_complement_when_warm(self):
        p, s = node_responses(-0.5, 0.3)
        self.assertAlmostEqual(p, -0.65)
        self.assertAlmostEqual(s, -0.65 * 0.65 * 0.65)
        p, s = node_responses(0.5, 0.3)
        self.assertAlmostEqual(p, 0.85)
        self.assertAlmostEqual(s, 0.85**3)

    def test_primary_clamps_to_one(self):
        self.assertEqual(node_responses(-1.0, 1.0)[0], -1.0)
        self.assertEqual(node_responses(1.0, 0.0)[0], 1.0)

    def test_cooling_target_moves_from_the_base_toward_the_cold_aim_by_primary(self):
        self.assertAlmostEqual(skin_target(37.0, -0.5, 0.8, 0.0), 33 + (33 - 12 * 0.88 - 33) * 0.5)

    def test_warming_target_uses_insulation_and_stops_at_the_core(self):
        self.assertAlmostEqual(skin_target(37.0, 0.5, 0.8, 1.0), 33 + (35.08 - 33) * 0.5)
        self.assertAlmostEqual(skin_target(37.0, 1.0, 0.0, 9.0), 37.0)

    def test_insulation_keeps_a_cooling_skin_warmer(self):
        self.assertGreater(skin_target(37.0, -1.0, 1.0, 2.0), skin_target(37.0, -1.0, 1.0, 0.0))

    def test_warming_target_with_heavy_insulation_uses_half_the_insulation(self):
        self.assertAlmostEqual(
            skin_target(37.0, 0.5, 0.8, 3.0), 33 + (33 + 4 * 0.52 * 1.04 - 33) * 0.5
        )

    def test_skin_min_in_warm_air_never_exceeds_the_air(self):
        low, _ = skin_limits(37.0, 36.0, 0.0)
        self.assertAlmostEqual(low, 35.0)
        self.assertLessEqual(low, 36.0)

    def test_skin_min_is_the_air_in_cool_air_and_the_max_is_the_core(self):
        self.assertEqual(skin_limits(37.0, 22.0, 0.8), (22.0, 37.0))
        self.assertEqual(skin_limits(37.0, 10.0, 0.8), (17.0, 37.0))

    def test_skin_min_in_warm_air(self):
        low, high = skin_limits(37.0, 36.0, 0.8)
        self.assertAlmostEqual(low, 33 + 4 * 0.5 * (0.4 + 0.6 * 0.2))
        self.assertEqual(high, 37.0)

    def test_skin_min_never_exceeds_the_max(self):
        low, high = skin_limits(30.0, 40.0, 0.0)
        self.assertAlmostEqual(low, high - 0.25)

    def test_skin_moves_three_times_faster_toward_the_comfort_band(self):
        self.assertAlmostEqual(skin_rate(34.0, 30.0), 0.0075)
        self.assertAlmostEqual(skin_rate(30.0, 34.0), 0.0075)
        self.assertAlmostEqual(skin_rate(30.0, 25.0), 0.0025)
        self.assertAlmostEqual(skin_rate(36.0, 37.0), 0.0025)

    def test_skin_follows_the_closed_form_toward_its_clamped_target(self):
        state = ThermalState()
        state.primary[BodyPart.HAND_L] = 0.0
        core = thermal_step(state, 37.0, still_inputs(10.0), 10)
        target = skin_target(core, state.primary[BodyPart.HAND_L], 0.8, 0.0)
        lowest, highest = skin_limits(core, 10.0, 0.8)
        target = min(max(target, lowest), highest)
        self.assertAlmostEqual(
            state.skin[BodyPart.HAND_L], target + (33.0 - target) * (1 - 0.0025) ** 10
        )

    def test_node_temperature_is_the_core_or_halfway_between_skin_and_core(self):
        state = ThermalState()
        thermal_step(state, 37.0, still_inputs(22.0), 10)
        for part in BodyPart:
            skin = state.skin[part]
            core = 37.0
            self.assertLessEqual(state.node_temp[part], core)
            self.assertAlmostEqual(state.node_temp[part], (skin + core) / 2, places=1)


class SteadyStateTests(unittest.TestCase):
    """Spec 06, Heat per node: the settled body."""

    def test_shirt_and_jeans_at_22_settle_with_core_36_7_to_37_0_and_stay_steady(self):
        player = make_player(shirt_and_jeans())
        cores = run_driver(player, 24 * 60, weather(22.0), indoors=False)
        self.assertGreaterEqual(cores[-1], 36.7)
        self.assertLessEqual(cores[-1], 37.0)
        self.assertLess(abs(cores[-1] - cores[71]), 0.01)

    def test_naked_at_22_settles_with_core_36_5_to_36_8(self):
        player = make_player()
        cores = run_driver(player, 24 * 60, weather(22.0), indoors=False)
        self.assertGreaterEqual(cores[-1], 36.5)
        self.assertLessEqual(cores[-1], 36.8)
        self.assertLess(abs(cores[-1] - cores[71]), 0.01)

    def test_naked_at_0_with_wind_the_core_falls_and_level_1_comes_before_level_2(self):
        player = make_player()
        first = {}
        engine = StatsEngine([ThermoregulatorDriver()])
        for minute in range(480):
            engine.advance(player, 1, StatContext(weather=weather(0.0, wind=0.5)))
            level = status_effect_level(
                StatusEffect.HYPOTHERMIA, player.stats.get(CharacterStat.TEMPERATURE)
            )
            for reached in range(1, level + 1):
                first.setdefault(reached, minute)
        self.assertLess(player.stats.get(CharacterStat.TEMPERATURE), 36.0)
        self.assertIn(1, first)
        self.assertIn(2, first)
        self.assertLess(first[1], first[2])

    def test_more_torso_insulation_slows_core_cooling(self):
        bare = make_player()
        wrapped = make_player({BodyLocation.JACKET: coat(0.9)})
        sample = weather(0.0, wind=0.5)
        cold_bare = run_driver(bare, 60, sample, indoors=False)[-1]
        cold_wrapped = run_driver(wrapped, 60, sample, indoors=False)[-1]
        self.assertGreater(cold_wrapped, cold_bare)

    def test_more_wind_resistance_slows_cooling_in_wind(self):
        loose = make_player({BodyLocation.JACKET: coat(0.5, wind=0.0)})
        tight = make_player({BodyLocation.JACKET: coat(0.5, wind=0.9)})
        sample = weather(0.0, wind=0.5)
        self.assertGreater(
            run_driver(tight, 60, sample, indoors=False)[-1],
            run_driver(loose, 60, sample, indoors=False)[-1],
        )

    def test_no_weather_is_a_still_dry_22_degrees(self):
        player = make_player(shirt_and_jeans())
        engine = StatsEngine([ThermoregulatorDriver()])
        engine.advance(player, 600, StatContext())
        self.assertAlmostEqual(player.stats.get(CharacterStat.TEMPERATURE), 37.0, delta=0.3)

    def test_the_sickness_set_point_rises_by_two_degrees_per_sickness(self):
        well = make_player(shirt_and_jeans())
        sick = make_player(shirt_and_jeans())
        sick.stats.set(CharacterStat.SICKNESS, 1.0)
        a = run_driver(well, 360, weather(22.0), indoors=False)[-1]
        b = run_driver(sick, 360, weather(22.0), indoors=False)[-1]
        self.assertGreater(b, a + 0.5)

    def test_windchill_amount_is_written_outdoors_and_zero_indoors(self):
        player = make_player(shirt_and_jeans())
        run_driver(player, 10, weather(0.0, wind=0.5), indoors=False)
        self.assertGreater(player.stats.get(CharacterStat.WINDCHILL), 5.0)
        run_driver(player, 10, weather(0.0, wind=0.5), indoors=True)
        self.assertEqual(player.stats.get(CharacterStat.WINDCHILL), 0.0)

    def test_a_walk_raises_the_metabolic_rate_toward_the_walking_target(self):
        player = make_player(shirt_and_jeans())
        run_driver(player, 60, weather(22.0), indoors=True, metabolic=Metabolic.WALKING_5KMH)
        self.assertAlmostEqual(
            player.thermal.metabolic_rate, 3.1 - 1.6 * (1 - 0.001) ** (60 * 112.5), places=3
        )

    def test_a_tired_body_burns_more_through_the_exercise_term(self):
        player = make_player(shirt_and_jeans())
        player.stats.set(CharacterStat.ENDURANCE, 0.0)
        run_driver(player, 60, weather(22.0), indoors=True)
        self.assertGreater(player.thermal.metabolic_rate, 2.5)


class IntegrationTests(unittest.TestCase):
    """Spec 06, Integration."""

    def reference(self, inputs: ThermalInputs, frames=13500, core=37.0, state=None):
        state = state or ThermalState()
        for _ in range(frames):
            core = thermal_step(state, core, inputs, 1)
        return core, state

    def substepped(self, inputs: ThermalInputs, frames=13500, core=37.0):
        state = ThermalState()
        for _ in range(frames // 10):
            core = thermal_step(state, core, inputs, 10)
        return core, state

    def scenarios(self):
        clothed = {
            part: part_clothing(
                [ItemEntity(item=ITEMS["item_tshirt"]), ItemEntity(item=ITEMS["item_jeans"])]
                if part
                in (
                    BodyPart.TORSO_UPPER,
                    BodyPart.TORSO_LOWER,
                    BodyPart.UPPERLEG_L,
                    BodyPart.UPPERLEG_R,
                )
                else [],
                part,
            )
            for part in BodyPart
        }
        return {
            "shirt and jeans at 10": still_inputs(10.0, clothing=clothed),
            "naked at 22": still_inputs(22.0),
            "naked at 5 with wind chill": still_inputs(5.0, chill=-3.0),
        }

    def test_ten_frame_sub_steps_track_a_one_frame_loop_over_two_hours(self):
        for name, inputs in self.scenarios().items():
            with self.subTest(name):
                ref_core, ref = self.reference(inputs)
                core, state = self.substepped(inputs)
                self.assertLess(abs(core - ref_core), 0.05)
                for part in BodyPart:
                    self.assertLess(abs(state.skin[part] - ref.skin[part]), 0.1, part)

    def test_a_shorter_last_sub_step_matches_the_same_frames_in_one_step(self):
        a, b = ThermalState(), ThermalState()
        core_a = thermal_step(a, 37.0, still_inputs(5.0), 5)
        core_b = 37.0
        for _ in range(5):
            core_b = thermal_step(b, core_b, still_inputs(5.0), 1)
        self.assertAlmostEqual(core_a, core_b, places=4)

    def test_the_driver_runs_112_5_frames_per_game_minute(self):
        player = make_player()
        StatsEngine([ThermoregulatorDriver()]).advance(
            player, 4, StatContext(weather=weather(22.0))
        )
        reference = ThermalState()
        core = 37.0
        inp = still_inputs(22.0)
        for _ in range(45):
            core = thermal_step(reference, core, inp, 10)
        self.assertAlmostEqual(player.thermal.metabolic_rate, reference.metabolic_rate, places=9)
        self.assertAlmostEqual(player.stats.get(CharacterStat.TEMPERATURE), core, places=6)

    def test_a_chunk_of_fractional_frames_ends_with_a_shorter_sub_step(self):
        player = make_player()
        StatsEngine([ThermoregulatorDriver()]).advance(
            player, 1, StatContext(weather=weather(22.0))
        )
        reference = ThermalState()
        core = 37.0
        for frames in [10.0] * 11 + [2.5]:
            core = thermal_step(reference, core, still_inputs(22.0), frames)
        self.assertAlmostEqual(player.thermal.metabolic_rate, reference.metabolic_rate, places=9)


class BodyMultiplierTests(unittest.TestCase):
    """Spec 06, Body multipliers."""

    def test_shivering_side_energy_and_fatigue(self):
        p, s = -0.6, -0.4
        energy, fluids, fatigue = body_multipliers(p, s)
        self.assertAlmostEqual(energy, 1 + 0.05 * p**2 + 0.1 * s**2)
        self.assertAlmostEqual(fluids, 1.0)
        self.assertAlmostEqual(fatigue, 1 + 0.25 * p**2 + 0.75 * s**2)

    def test_sweating_side_fluids_and_fatigue(self):
        p, s = 0.5, 0.8
        energy, fluids, fatigue = body_multipliers(p, s)
        self.assertAlmostEqual(energy, 1.0)
        self.assertAlmostEqual(fluids, 1 + 0.25 * p**2 + 3.75 * s**2)
        self.assertAlmostEqual(fatigue, 1 + 0.25 * p**2 + 1.75 * s**2)

    def test_each_total_picks_its_own_side(self):
        p, s = -0.5, 0.5
        energy, fluids, fatigue = body_multipliers(p, s)
        self.assertAlmostEqual(energy, 1 + 0.05 * p**2)
        self.assertAlmostEqual(fluids, 1 + 3.75 * s**2)
        self.assertAlmostEqual(fatigue, 1 + 0.25 * p**2 + 1.75 * s**2)

    def test_zero_totals_leave_every_multiplier_at_one(self):
        self.assertEqual(body_multipliers(0.0, 0.0), (1.0, 1.0, 1.0))

    def test_a_thermal_step_stores_the_multipliers_of_its_totals(self):
        state = ThermalState()
        thermal_step(state, 36.0, still_inputs(0.0), 10)
        self.assertLess(state.primary_total, 0)
        energy, fluids, fatigue = body_multipliers(state.primary_total, state.secondary_total)
        self.assertEqual(
            (state.energy_mult, state.fluids_mult, state.fatigue_mult), (energy, fluids, fatigue)
        )
        self.assertGreater(state.energy_mult, 1.0)

    def test_totals_weight_each_node_by_its_skin_surface(self):
        state = ThermalState()
        thermal_step(state, 36.0, still_inputs(22.0), 10)
        from data.thermal import THERMAL_NODES

        self.assertAlmostEqual(
            state.primary_total,
            sum(state.primary[p] * n.skin_surface for p, n in THERMAL_NODES.items()),
        )

    def test_the_engine_hands_the_stored_multipliers_to_the_survival_drivers(self):
        from managers.stats.drivers import FatigueDriver, HungerDriver, ThirstDriver

        def run(mults):
            player = make_player()
            t = player.thermal
            t.energy_mult, t.fluids_mult, t.fatigue_mult = mults
            engine = StatsEngine([HungerDriver(), ThirstDriver(), FatigueDriver()])
            engine.advance(player, 6, StatContext(indoors=True))
            return tuple(
                player.stats.get(s)
                for s in (CharacterStat.HUNGER, CharacterStat.THIRST, CharacterStat.FATIGUE)
            )

        base = run((1.0, 1.0, 1.0))
        scaled = run((2.0, 3.0, 4.0))
        for got, want, factor in zip(scaled, base, (2.0, 3.0, 4.0), strict=True):
            self.assertAlmostEqual(got, want * factor, places=6)

    def test_a_caller_given_multiplier_wins_over_the_stored_one(self):
        from managers.stats.drivers import BodyMultipliers, HungerDriver

        player = make_player()
        player.thermal.energy_mult = 5.0
        StatsEngine([HungerDriver()]).advance(
            player, 6, StatContext(indoors=True, body=BodyMultipliers(energy=2.0))
        )
        reference = make_player()
        StatsEngine([HungerDriver()]).advance(reference, 6, StatContext(indoors=True))
        self.assertAlmostEqual(
            player.stats.get(CharacterStat.HUNGER), reference.stats.get(CharacterStat.HUNGER) * 2.0
        )


class ThermalDamageTests(unittest.TestCase):
    """Spec 06, Thermal damage."""

    def freezing_state(self, stage=0.0, duration=0.0, cache=24.0) -> ThermalState:
        state = ThermalState()
        state.thermal_damage = stage
        state.thermal_duration = duration
        state.core_cache = cache
        return state

    def test_cold_tick_builds_by_the_hand_computed_amount(self):
        state = self.freezing_state()
        thermal_damage_tick(state, 24.0, 4, 0, -10.0)
        frost = 1 - (24.0 - 20) / 5
        expected = (1.0 / (120 + 480 * frost)) * 1.2
        self.assertAlmostEqual(state.thermal_duration, 1.07)
        self.assertAlmostEqual(state.thermal_damage, min(expected, 1.07 / 7200))

    def test_cold_tick_amount_for_core_22_and_air_minus_5(self):
        state = self.freezing_state(duration=1000.0, cache=22.0)
        thermal_damage_tick(state, 22.0, 4, 0, -5.0)
        self.assertAlmostEqual(state.thermal_damage, (5 / 10) / (120 + 480 * (1 - 2 / 5)) * 1.2)

    def test_cold_tick_is_capped_at_duration_over_7200(self):
        state = self.freezing_state(duration=0.0, cache=22.0)
        thermal_damage_tick(state, 22.0, 4, 0, -5.0)
        self.assertAlmostEqual(state.thermal_damage, 1.07 / 7200)

    def test_hot_tick_amount(self):
        state = self.freezing_state(cache=40.0)
        thermal_damage_tick(state, 41.5, 0, 4, 41.0)
        self.assertAlmostEqual(state.thermal_damage, (4 / 8) / (120 + 480 * 0.5))

    def test_the_stage_grows_to_duration_over_7200_so_one_after_two_hours(self):
        state = self.freezing_state()
        ticks = int(2 * 3600 / 1.07)
        for _ in range(ticks + 5):
            thermal_damage_tick(state, 24.0, 4, 0, -10.0)
        self.assertAlmostEqual(state.thermal_damage, 1.0)
        self.assertEqual(round(7200 / 1.07 / 56.25), 120)

    def test_the_stage_tracks_duration_over_7200(self):
        state = self.freezing_state()
        for _ in range(1000):
            thermal_damage_tick(state, 24.0, 4, 0, -10.0)
        self.assertAlmostEqual(state.thermal_damage, 1000 * 1.07 / 7200)

    def test_air_damage_scales_with_the_wind_chill_size(self):
        weak = self.freezing_state()
        strong = self.freezing_state()
        thermal_damage_tick(weak, 24.0, 4, 0, -2.0)
        thermal_damage_tick(strong, 24.0, 4, 0, -12.0)
        self.assertLessEqual(weak.thermal_damage, strong.thermal_damage)

    def test_a_rising_core_decays_the_stage_instead(self):
        state = self.freezing_state(stage=0.5, duration=100.0, cache=23.0)
        thermal_damage_tick(state, 24.0, 4, 0, -10.0)
        self.assertAlmostEqual(state.thermal_damage, 0.5 - 0.011111)
        self.assertEqual(state.thermal_duration, 0.0)

    def test_it_needs_hypothermia_4_and_wind_chill_air_below_zero(self):
        for level, air in ((3, -10.0), (4, 0.0), (4, 5.0)):
            with self.subTest(level=level, air=air):
                state = self.freezing_state(stage=0.5)
                thermal_damage_tick(state, 24.0, level, 0, air)
                self.assertAlmostEqual(state.thermal_damage, 0.5 - 0.011111)

    def test_the_stage_falls_0_011111_per_tick_and_stays_at_zero(self):
        state = self.freezing_state(stage=0.6)
        thermal_damage_tick(state, 37.0, 0, 0, 22.0)
        self.assertAlmostEqual(state.thermal_damage, 0.588889)
        state.thermal_damage = 0.005
        thermal_damage_tick(state, 37.0, 0, 0, 22.0)
        self.assertEqual(state.thermal_damage, 0.0)

    def test_the_stage_falls_37_5_per_game_hour_in_driver_ticks(self):
        player = make_player(shirt_and_jeans())
        player.thermal.thermal_damage = 1.0
        engine = StatsEngine([ThermoregulatorDriver()])
        engine.advance(player, 1, StatContext(weather=weather(22.0)))
        self.assertAlmostEqual(player.thermal.thermal_damage, 1.0 - 0.011111 * 56.25, places=2)

    def test_the_hot_branch_caps_at_0_3_and_resets_duration(self):
        state = self.freezing_state(duration=50.0, cache=40.0)
        for _ in range(100000):
            thermal_damage_tick(state, 41.9, 0, 4, 60.0)
        self.assertLessEqual(state.thermal_damage, 0.3)
        self.assertEqual(state.thermal_duration, 0.0)

    def test_it_reads_the_wind_chill_air_so_5_degrees_with_enough_wind_counts(self):
        player = make_player()
        player.stats.set(CharacterStat.TEMPERATURE, 21.0)
        run_driver(player, 5, weather(5.0, wind=1.0), indoors=False, step=1)
        self.assertGreater(player.thermal.thermal_damage, 0.0)
        calm = make_player()
        calm.stats.set(CharacterStat.TEMPERATURE, 21.0)
        run_driver(calm, 5, weather(5.0, wind=0.0), indoors=False, step=1)
        self.assertEqual(calm.thermal.thermal_damage, 0.0)

    def test_two_real_frames_make_a_tick(self):
        state = ThermalState()
        state.thermal_damage = 1.0
        thermal_step(state, 37.0, still_inputs(22.0), 10)
        self.assertAlmostEqual(state.thermal_damage, 1.0 - 5 * 0.011111)
        state2 = ThermalState()
        state2.thermal_damage = 1.0
        thermal_step(state2, 37.0, still_inputs(22.0), 1)
        self.assertEqual(state2.thermal_damage, 1.0)
        thermal_step(state2, 37.0, still_inputs(22.0), 1)
        self.assertAlmostEqual(state2.thermal_damage, 1.0 - 0.011111)

    def test_the_cache_refreshes_every_seven_sub_steps(self):
        state = ThermalState()
        state.core_cache = 30.0
        for _ in range(6):
            thermal_step(state, 37.0, still_inputs(22.0), 10)
        self.assertEqual(state.core_cache, 30.0)
        thermal_step(state, 37.0, still_inputs(22.0), 10)
        self.assertAlmostEqual(state.core_cache, 37.0, places=2)

    def test_health_cap_is_100_minus_100_times_the_stage(self):
        self.assertEqual(health_cap(0.0), 100.0)
        self.assertAlmostEqual(health_cap(0.25), 75.0)
        self.assertEqual(health_cap(1.0), 0.0)

    def test_the_stage_caps_no_health_yet(self):
        player = make_player()
        player.stats.set(CharacterStat.TEMPERATURE, 21.0)
        run_driver(player, 5, weather(-10.0, wind=1.0), indoors=False, step=1)
        self.assertGreater(player.thermal.thermal_damage, 0.0)
        self.assertEqual(player.hit_points, 100)


class WiringTests(unittest.TestCase):
    """Spec 06, Set point and metabolic rate: what the simulation hands the drivers."""

    def test_attack_metabolic_targets_by_weapon(self):
        from data.items import ITEMS
        from data.melee import BARE_HANDS
        from managers.thermoregulator import attack_metabolic
        from modules.character.equipment import AnyCharacterEquipmentSlot, CharacterHoldableSlot
        from modules.item import MeleeWeaponItem, RangedWeaponItem
        from modules.weapon import RangedWeaponType

        def ranged(kind):
            slots: list[AnyCharacterEquipmentSlot] = [CharacterHoldableSlot.RIGHT_HAND]
            return RangedWeaponItem("g", "g", "", 1, [], slots, False, kind, 3, 5, weight=1.5)

        crowbar = ITEMS["item_crowbar"]
        knife = ITEMS["item_kitchen_knife"]
        assert isinstance(crowbar, MeleeWeaponItem) and isinstance(knife, MeleeWeaponItem)
        self.assertEqual(attack_metabolic(None), Metabolic.MEDIUM_WORK)
        self.assertEqual(attack_metabolic(BARE_HANDS), Metabolic.MEDIUM_WORK)
        self.assertEqual(attack_metabolic(crowbar), Metabolic.HEAVY_WORK)
        self.assertEqual(attack_metabolic(knife), Metabolic.LIGHT_WORK)
        self.assertEqual(attack_metabolic(ranged(RangedWeaponType.RIFLE)), Metabolic.LIGHT_WORK)
        self.assertEqual(attack_metabolic(ranged(RangedWeaponType.PISTOL)), Metabolic.USING_TOOLS)

    def test_the_stat_context_carries_floor_power_target_and_traits(self):
        from data.traits import PRONE_TO_ILLNESS_ID
        from managers.game import GameManager
        from managers.simulation import SimulationCore
        from modules.action.types import Duration, MoveAction, WaitAction

        game = GameManager()
        game.player.traits.append(PRONE_TO_ILLNESS_ID)
        core = SimulationCore(game)
        ctx = core._stat_context(MoveAction(destination="out"))
        self.assertEqual(ctx.floor, 1)
        self.assertTrue(ctx.power_on)
        self.assertEqual(ctx.metabolic, Metabolic.WALKING_5KMH)
        self.assertIn(PRONE_TO_ILLNESS_ID, ctx.traits)
        self.assertEqual(core._stat_context(None).metabolic, Metabolic.DEFAULT)
        self.assertEqual(
            core._stat_context(WaitAction(duration=Duration(minutes=10))).metabolic,
            Metabolic.DEFAULT,
        )
        game.world.power_on = False
        self.assertFalse(core._stat_context(None).power_on)

    def test_a_default_engine_runs_the_thermal_drivers(self):
        player = make_player()
        player.stats.set(CharacterStat.TEMPERATURE, 35.0)
        StatsEngine().advance(
            player, 30, StatContext(weather=weather(22.0), indoors=True, power_on=True)
        )
        self.assertGreater(player.stats.get(CharacterStat.TEMPERATURE), 35.0)


if __name__ == "__main__":
    unittest.main()
