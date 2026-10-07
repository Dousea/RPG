"""The thermoregulator: heat balance, core and skin temperatures, multipliers, thermal damage (body-temperature)."""

import logging
from dataclasses import dataclass, field
from functools import cache

from data.body import status_effects as status_effect_k
from data.body import thermal as thermal_k
from data.character import skills as skill_k
from data.world import climate as climate_k
from data.world.clock import MINUTES_PER_HOUR
from managers.body.stats.drivers import StatContext
from managers.body.stats.status_effects import hypothermia_level, status_effect_level
from managers.character.skills import fitness_level
from managers.world.climate import FeltAir, felt_air
from modules import units
from modules.body.parts import BodyPart
from modules.body.stats import CharacterStat, Stats, StatusEffect
from modules.body.thermal import ThermalState
from modules.entity.item import ItemEntity
from modules.item import ClothingItem, MeleeWeaponItem, RangedWeaponItem
from modules.weapon import RangedWeaponType

logger = logging.getLogger(__name__)


def relax(value: float, target: float, rate_per_frame: float, frames: float) -> float:
    """`value` after `frames` frames of `value += (target - value) * rate`, in closed form."""
    return target + (value - target) * (1 - rate_per_frame) ** frames


def clamp(value: float, low: float, high: float) -> float:
    return max(low, min(high, value))


def energy_term(hunger: float, fatigue: float) -> float:
    """How much the body has in reserve, 0 to 1, from hunger and fatigue."""
    hunger_left = 1 - (thermal_k.ENERGY_LINEAR * hunger + thermal_k.ENERGY_QUADRATIC * hunger**2)
    fatigue_left = 1 - (thermal_k.ENERGY_LINEAR * fatigue + thermal_k.ENERGY_QUADRATIC * fatigue**2)
    return thermal_k.ENERGY_HUNGER_MIX * hunger_left + thermal_k.ENERGY_FATIGUE_MIX * fatigue_left


def metabolic_target(
    activity: thermal_k.Metabolic, endurance: float, energy: float, carry_ratio: float = 0.0
) -> float:
    """The met the body works toward: the highest of the activity, the default and the exercise term."""
    target = max(
        thermal_k.METABOLICS[thermal_k.Metabolic.DEFAULT],
        thermal_k.METABOLICS[activity],
        clamp(1 - endurance, 0.0, 1.0) * thermal_k.EXERCISE_TERM_MET * energy,
    )
    target = min(target, thermal_k.METABOLIC_MAX)
    return target * (1 + clamp(carry_ratio, 0.0, 1.0) ** 2 * thermal_k.CARRY_RATIO_COEFF)


def movement_modifier(hypothermia: int, hyperthermia: int) -> float:
    """Hypothermia or Hyperthermia slows the body's work; hyperthermia wins from level 2."""
    if hypothermia < 1:
        return 1.0
    modifier = thermal_k.MOVEMENT_MODIFIER.get(hypothermia, 1.0)
    if hyperthermia >= 2:
        modifier = thermal_k.MOVEMENT_MODIFIER.get(hyperthermia, 1.0)
    return modifier


def real_metabolic_rate(rate: float, energy: float, move_mod: float) -> float:
    return rate * (
        thermal_k.METABOLIC_REAL_BASE + thermal_k.METABOLIC_REAL_ENERGY * energy * move_mod
    )


def true_insulation(insulation: float) -> float:
    return (
        thermal_k.TRUE_INSULATION_LINEAR * insulation
        + thermal_k.TRUE_INSULATION_CUBIC * insulation**3
    )


def true_wind_resistance(resistance: float) -> float:
    return resistance + thermal_k.TRUE_WINDRESIST_QUADRATIC * resistance**2


@dataclass(frozen=True)
class NodeClothing:
    """What covers one body part: insulation, wind resistance and layer-average wetness (0 to 1)."""

    insulation: float = 0.0
    wind_resistance: float = 0.0
    wetness: float = 0.0


def part_clothing(layers: list[ItemEntity], part: BodyPart) -> NodeClothing:
    """Combine the worn layers over `part` (inner to outer) into its insulation and wind resistance."""
    insulation = 0.0
    wind = 0.0
    wetness = 0.0
    count = 0
    for entity in layers:
        item = entity.item
        if not isinstance(item, ClothingItem):
            continue
        if item.insulation <= 0 and item.wind_resistance <= 0:
            continue
        cw = clamp(entity.wetness / thermal_k.LAYER_SOAK_MAX, 0.0, 1.0)
        count += 1
        wetness += cw
        if part in entity.holes:
            continue
        condition = thermal_k.CONDITION_BASE + thermal_k.CONDITION_SCALE * (
            entity.hit_points / entity.max_hit_points if entity.max_hit_points else 1.0
        )
        insulation += (
            true_insulation(item.insulation)
            * (1 - thermal_k.CLOTHING_WET_INSULATION * cw)
            * condition
        )
        wind += (
            true_wind_resistance(item.wind_resistance)
            * (1 - thermal_k.CLOTHING_WET_WIND * cw)
            * condition
        )
    if not count:
        return NodeClothing()
    return NodeClothing(
        insulation + thermal_k.LAYER_BASE * count,
        wind + thermal_k.LAYER_BASE * count,
        wetness / count,
    )


@dataclass
class ThermalInputs:
    """What a chunk fixes for the heat balance: the air, the body's reserves and its clothing."""

    air: FeltAir
    humidity: float = thermal_k.HUMIDITY_REFERENCE
    set_point: float = thermal_k.CORE_SET_POINT_C
    energy: float = 1.0
    fluids: float = 1.0
    weight_kg: float = thermal_k.DEFAULT_BODY_WEIGHT_KG
    fitness: float = 0.0
    body_wetness: float = 0.0
    intoxication: float = 0.0
    target_met: float = thermal_k.METABOLICS[thermal_k.Metabolic.DEFAULT]
    clothing: dict[BodyPart, NodeClothing] = field(default_factory=dict[BodyPart, NodeClothing])


@cache
def weight_term(weight_kg: float) -> float:
    scaled = clamp(
        (weight_kg / thermal_k.WEIGHT_REFERENCE_KG - thermal_k.WEIGHT_OFFSET)
        * thermal_k.WEIGHT_SCALE,
        0.0,
        1.0,
    )
    return (scaled - 0.5) * 2


def prim_heat_mod(inp: ThermalInputs) -> float:
    still, chill, set_point = inp.air.still_c, inp.air.wind_chill_c, inp.set_point
    if chill <= set_point - thermal_k.PRIM_HEAT_MOD_RANGE_C:
        return 1.0
    if still >= set_point + thermal_k.PRIM_HEAT_MOD_RANGE_C:
        return 0.0
    return (
        1
        - (still - (set_point - thermal_k.PRIM_HEAT_MOD_RANGE_C)) / thermal_k.PRIM_HEAT_MOD_DIVISOR
    )


def humidity_mod(humidity: float) -> float:
    if humidity > thermal_k.HUMIDITY_REFERENCE:
        return 1 - (humidity - thermal_k.HUMIDITY_REFERENCE) * 2
    return 1.0


def node_heat(
    part: BodyPart, state: ThermalState, inp: ThermalInputs, prim_mod: float, humid_mod: float
) -> float:
    """The heat one node gains (positive) or loses through its skin and its body's responses."""
    node = thermal_k.THERMAL_NODES[part]
    cover = inp.clothing.get(part, NodeClothing())
    insulation = 1 + cover.insulation
    wt = weight_term(inp.weight_kg)
    fit = inp.fitness
    fit_mult = 1 + thermal_k.WEIGHT_FITNESS_MULT * fit
    cool_weight = 1 - thermal_k.WEIGHT_FITNESS_MULT * wt
    warm_weight = 1 + thermal_k.WEIGHT_FITNESS_MULT * wt
    bw = inp.body_wetness
    external = inp.air.still_c
    if inp.air.wind_chill_c < inp.air.still_c:
        external -= (inp.air.still_c - inp.air.wind_chill_c) / (1 + cover.wind_resistance)
    delta = external - state.skin[part]
    if delta <= 0:
        delta *= 1 + thermal_k.BODY_WET_COOLING * bw
    else:
        delta /= 1 + thermal_k.BODY_WET_WARMING_DIVISOR * bw
    heat = delta * thermal_k.NODE_EXCHANGE_FACTOR / insulation * node.skin_surface
    ss = node.skin_surface
    primary = state.primary[part]
    secondary = state.secondary[part]
    if primary > 0:
        heat -= (
            thermal_k.RESPONSE_GAIN
            * primary
            * ss
            / insulation
            * (thermal_k.PRIMARY_FLUIDS_BASE + thermal_k.PRIMARY_FLUIDS_SCALE * inp.fluids)
            * (thermal_k.PRIMARY_HEATMOD_BASE + thermal_k.PRIMARY_HEATMOD_SCALE * prim_mod)
            * humid_mod
            * cool_weight
            * fit_mult
        )
    else:
        heat += (
            thermal_k.RESPONSE_GAIN
            * abs(primary)
            * ss
            * (thermal_k.SHIVER_ENERGY_BASE + thermal_k.SHIVER_ENERGY_SCALE * inp.energy)
            * warm_weight
            * fit_mult
        )
    if secondary > 0:
        heat -= (
            thermal_k.SECONDARY_SWEAT_MET
            * secondary
            * ss
            / insulation
            * (thermal_k.SECONDARY_FLUIDS_BASE + thermal_k.SECONDARY_FLUIDS_SCALE * inp.fluids)
            * (thermal_k.SECONDARY_HUMIDITY_BASE + thermal_k.SECONDARY_HUMIDITY_SCALE * humid_mod)
            * cool_weight
            * fit_mult
        )
    else:
        heat += (
            thermal_k.RESPONSE_GAIN
            * abs(secondary)
            * ss
            * (thermal_k.SECONDARY_ENERGY_BASE + thermal_k.SECONDARY_ENERGY_SCALE * inp.energy)
            * warm_weight
            * fit_mult
        )
    return heat


def advance_core(core: float, total_heat: float, set_point: float, frames: float) -> float:
    """The core after `frames` frames of `total_heat`; the reported core is capped at 40 C."""
    delta = total_heat * thermal_k.BODY_HEAT_PER_FRAME
    if delta < 0 and core > set_point:
        delta *= 1 + (core - set_point) / thermal_k.CORE_ABOVE_SET_DIV
    elif delta >= 0 and core < set_point:
        delta *= 1 + (set_point - core) / thermal_k.CORE_BELOW_SET_DIV
    if abs(delta) > thermal_k.CORE_STAT_TOLERANCE:
        delta /= 2
    core = clamp(core + delta * frames, thermal_k.CORE_MIN_C, thermal_k.CORE_MAX_C)
    return clamp(core, thermal_k.STAT_MIN_C, thermal_k.STAT_MAX_C)


def body_heat_delta(core: float, set_point: float) -> float:
    gap = core - set_point
    if gap < 0:
        size = abs(gap)
        if size <= thermal_k.BODY_HEAT_NEAR_GAP:
            gap *= thermal_k.BODY_HEAT_NEAR_MULT
        else:
            excess = (
                clamp(size, thermal_k.BODY_HEAT_NEAR_GAP, thermal_k.BODY_HEAT_FAR_MAX_GAP)
                - thermal_k.BODY_HEAT_NEAR_GAP
            )
            gap = (
                thermal_k.BODY_HEAT_FAR_BASE
                - thermal_k.BODY_HEAT_FAR_SLOPE * excess / thermal_k.BODY_HEAT_FAR_RANGE
            )
    return clamp(gap, -1.0, 1.0)


def node_responses(body_heat: float, dist: float) -> tuple[float, float]:
    """A node's primary and secondary deltas from the body heat delta."""
    reach = dist if body_heat < 0 else 1 - dist
    primary = body_heat * (1 + reach)
    primary = max(-1.0, min(1.0, primary))
    return primary, primary * abs(primary) * abs(primary)


def skin_limits(core: float, still_c: float, dist: float) -> tuple[float, float]:
    """The lowest and highest a node's skin can settle at."""
    highest = core
    lowest = core - thermal_k.SKIN_MIN_BELOW_CORE_C
    if lowest < still_c:
        if still_c < thermal_k.SKIN_REFERENCE_C:
            lowest = still_c
        else:
            lowest = thermal_k.SKIN_REFERENCE_C + thermal_k.SKIN_MIN_WARM_RANGE_C * (
                (still_c - thermal_k.SKIN_REFERENCE_C) / thermal_k.SKIN_MIN_WARM_SPAN_C
            ) * (thermal_k.SKIN_DIST_BASE + thermal_k.SKIN_DIST_SCALE * (1 - dist))
            lowest = clamp(lowest, thermal_k.SKIN_REFERENCE_C, still_c)
            if lowest > highest:
                lowest = highest - thermal_k.SKIN_MAX_MARGIN_C
    return lowest, highest


def skin_target(core: float, primary: float, dist: float, clothing_insulation: float) -> float:
    """Where a node's skin is headed, before the limits."""
    base = core - thermal_k.SKIN_BASE_BELOW_CORE_C
    insulation = 1 + clothing_insulation
    if primary < 0:
        dc = thermal_k.SKIN_DIST_BASE + thermal_k.SKIN_DIST_SCALE * dist
        aim = base - thermal_k.SKIN_COOL_RANGE_C * dc / insulation
        return base + (aim - base) * abs(primary)
    dc = thermal_k.SKIN_DIST_BASE + thermal_k.SKIN_DIST_SCALE * (1 - dist)
    aim = min(
        base
        + thermal_k.SKIN_WARM_RANGE_C
        * dc
        * max(insulation * thermal_k.SKIN_WARM_INSULATION_MULT * dc, 1.0),
        core,
    )
    return base + (aim - base) * primary


def skin_rate(skin: float, target: float) -> float:
    """Per-frame rate the skin moves at: three times faster toward the 33 C comfort band."""
    rate = thermal_k.SKIN_RATE_PER_FRAME
    if (target < skin and skin > thermal_k.SKIN_REFERENCE_C) or (
        target > skin and skin < thermal_k.SKIN_REFERENCE_C
    ):
        rate *= thermal_k.SKIN_FAST_FACTOR
    return min(rate, thermal_k.SKIN_RATE_CAP)


def body_multipliers(primary: float, secondary: float) -> tuple[float, float, float]:
    """The energy, fluids and fatigue multipliers a primary and a secondary total give."""
    energy = fluids = fatigue = 1.0
    parts = (
        (primary, 0, thermal_k.FATIGUE_COLD_COEFFS[0], thermal_k.FATIGUE_HOT_COEFFS[0]),
        (secondary, 1, thermal_k.FATIGUE_COLD_COEFFS[1], thermal_k.FATIGUE_HOT_COEFFS[1]),
    )
    for total, index, cold_coeff, hot_coeff in parts:
        square = total * total
        if total < 0:
            energy += thermal_k.ENERGY_MULT_COEFFS[index] * square
            fatigue += cold_coeff * square
        elif total > 0:
            fluids += thermal_k.FLUIDS_MULT_COEFFS[index] * square
            fatigue += hot_coeff * square
    return energy, fluids, fatigue


def thermal_damage_tick(
    state: ThermalState, core: float, hypothermia: int, hyperthermia: int, wind_chill_c: float
) -> None:
    """One damage tick (2 real frames): build the stage in deep cold or heat, else decay it."""
    rising = core - state.core_cache
    stage = state.thermal_damage
    if (
        hypothermia == status_effect_k.STATUS_EFFECT_MAX_LEVEL
        and wind_chill_c < thermal_k.THERMAL_DAMAGE_COLD_AIR_C
        and rising <= 0
    ):
        frost = (
            1 - (core - thermal_k.THERMAL_COLD_CORE_FLOOR_C) / thermal_k.THERMAL_COLD_CORE_RANGE_C
        )
        seconds = thermal_k.THERMAL_COLD_BASE_SECONDS + thermal_k.THERMAL_COLD_SPAN_SECONDS * frost
        stage += clamp(abs(wind_chill_c) / thermal_k.THERMAL_COLD_AIR_RANGE_C, 0.0, 1.0) / seconds
        stage *= thermal_k.THERMAL_COLD_GROWTH
        state.thermal_duration += thermal_k.THERMAL_TICK_SECONDS
        stage = min(stage, state.thermal_duration / thermal_k.THERMAL_DURATION_DIV)
    elif (
        hyperthermia == status_effect_k.STATUS_EFFECT_MAX_LEVEL
        and wind_chill_c > thermal_k.THERMAL_DAMAGE_HOT_AIR_C
        and rising >= 0
    ):
        seconds = thermal_k.THERMAL_HOT_BASE_SECONDS + thermal_k.THERMAL_HOT_SPAN_SECONDS * (
            core - thermal_k.THERMAL_HOT_CORE_C
        )
        stage += (
            clamp(
                (wind_chill_c - thermal_k.THERMAL_DAMAGE_HOT_AIR_C)
                / thermal_k.THERMAL_HOT_AIR_RANGE_C,
                0.0,
                1.0,
            )
            / seconds
        )
        stage = min(stage, thermal_k.THERMAL_HOT_CAP)
        state.thermal_duration = 0.0
    else:
        stage -= thermal_k.THERMAL_FALL_PER_TICK
        state.thermal_duration = 0.0
    state.thermal_damage = clamp(stage, 0.0, 1.0)


def health_cap(stage: float) -> float:
    """The health a thermal damage stage caps the body at; applied once health lands."""
    return thermal_k.HEALTH_CAP_BASE - thermal_k.HEALTH_CAP_PER_STAGE * stage


def thermal_step(
    state: ThermalState,
    core: float,
    inp: ThermalInputs,
    frames: float = thermal_k.THERMO_SUBSTEP_FRAMES,
) -> float:
    """Run the per-frame update over `frames` frames at once; returns the new core temperature."""
    hypo = hypothermia_level(core, inp.intoxication)
    hyper = status_effect_level(StatusEffect.HYPERTHERMIA, core)

    state.cache_counter += thermal_k.CACHE_COUNTER_PER_FRAME * frames
    if state.cache_counter > thermal_k.CACHE_COUNTER_LIMIT:
        state.core_cache = core
        state.cache_counter = 0.0

    rate_k = (
        thermal_k.METABOLIC_RATE_INC_PER_FRAME
        if inp.target_met > state.metabolic_rate
        else thermal_k.METABOLIC_RATE_DEC_PER_FRAME
    )
    state.metabolic_rate = relax(state.metabolic_rate, inp.target_met, rate_k, frames)

    prim_mod = prim_heat_mod(inp)
    humid_mod = humidity_mod(inp.humidity)
    total_heat = real_metabolic_rate(
        state.metabolic_rate, inp.energy, movement_modifier(hypo, hyper)
    )
    for part in thermal_k.THERMAL_NODES:
        total_heat += node_heat(part, state, inp, prim_mod, humid_mod)

    core = advance_core(core, total_heat, inp.set_point, frames)

    body_heat = body_heat_delta(core, inp.set_point)
    primary_total = secondary_total = 0.0
    for part, node in thermal_k.THERMAL_NODES.items():
        primary, secondary = node_responses(body_heat, node.distance_to_core)
        state.primary[part] = primary
        state.secondary[part] = secondary
        primary_total += primary * node.skin_surface
        secondary_total += secondary * node.skin_surface
        cover = inp.clothing.get(part, NodeClothing())
        target = skin_target(core, primary, node.distance_to_core, cover.insulation)
        lowest, highest = skin_limits(core, inp.air.still_c, node.distance_to_core)
        target = clamp(target, lowest, highest)
        skin = relax(state.skin[part], target, skin_rate(state.skin[part], target), frames)
        state.skin[part] = skin
        state.node_temp[part] = core if skin >= core else (skin + core) / 2
    state.primary_total = primary_total
    state.secondary_total = secondary_total
    state.energy_mult, state.fluids_mult, state.fatigue_mult = body_multipliers(
        primary_total, secondary_total
    )

    state.tick_frames += frames
    ticks = int(state.tick_frames // thermal_k.THERMAL_TICK_FRAMES)
    state.tick_frames -= ticks * thermal_k.THERMAL_TICK_FRAMES
    hypo = hypothermia_level(core, inp.intoxication)
    hyper = status_effect_level(StatusEffect.HYPERTHERMIA, core)
    for _ in range(ticks):
        thermal_damage_tick(state, core, hypo, hyper, inp.air.wind_chill_c)
    return core


def attack_metabolic(weapon: MeleeWeaponItem | RangedWeaponItem | None) -> thermal_k.Metabolic:
    """The metabolic target of an attack by weapon."""
    if isinstance(weapon, RangedWeaponItem):
        if weapon.type is RangedWeaponType.PISTOL:
            return thermal_k.Metabolic.USING_TOOLS
        return thermal_k.Metabolic.LIGHT_WORK
    if weapon is None:
        return thermal_k.Metabolic.MEDIUM_WORK
    if weapon.is_two_handed:
        return thermal_k.Metabolic.HEAVY_WORK
    if weapon.is_stab:
        return thermal_k.Metabolic.LIGHT_WORK
    return thermal_k.Metabolic.MEDIUM_WORK


def chunk_air(ctx: StatContext) -> tuple[FeltAir, float]:
    """The felt air of a chunk and the humidity; still, dry 22 degrees with no weather."""
    sample = ctx.weather
    if sample is None:
        return FeltAir(
            climate_k.INDOOR_POWERED_C, climate_k.INDOOR_POWERED_C
        ), thermal_k.HUMIDITY_REFERENCE
    air = felt_air(
        sample.air_temperature,
        sample.wind_intensity * climate_k.WIND_TO_KMH,
        indoors=ctx.indoors,
        floor=ctx.floor,
        power_on=ctx.power_on,
        daylight=sample.daylight,
    )
    return air, sample.humidity


def thermal_inputs(stats: Stats, ctx: StatContext, air: FeltAir, humidity: float) -> ThermalInputs:
    """The heat-balance inputs a chunk fixes."""
    player = ctx.wearer
    assert player is not None
    energy = energy_term(stats.get(CharacterStat.HUNGER), stats.get(CharacterStat.FATIGUE))
    set_point = thermal_k.CORE_SET_POINT_C + thermal_k.SICKNESS_SET_POINT_MULT * stats.get(
        CharacterStat.SICKNESS
    )
    return ThermalInputs(
        air=air,
        humidity=humidity,
        set_point=set_point,
        energy=energy,
        fluids=1 - stats.get(CharacterStat.THIRST),
        body_wetness=stats.get(CharacterStat.WETNESS) / thermal_k.LAYER_SOAK_MAX,
        intoxication=stats.get(CharacterStat.INTOXICATION),
        fitness=fitness_level(ctx.skills) / skill_k.FITNESS_STAT_DIVISOR - 1,
        target_met=metabolic_target(
            ctx.metabolic, stats.get(CharacterStat.ENDURANCE), energy, ctx.carry_ratio
        ),
        clothing={part: part_clothing(player.layers_for(part), part) for part in BodyPart},
    )


class ThermoregulatorDriver:
    """Runs the heat balance in 10-frame sub-steps and writes the core temperature back."""

    def apply(self, stats: Stats, hours: float, ctx: StatContext) -> None:
        player = ctx.wearer
        if player is None:
            return
        air, humidity = chunk_air(ctx)
        stats.set(CharacterStat.WINDCHILL, air.windchill_amount)
        inp = thermal_inputs(stats, ctx, air, humidity)
        remaining = hours * MINUTES_PER_HOUR * units.real_frames_per_minute()
        core = stats.get(CharacterStat.TEMPERATURE)
        while remaining > 1e-9:
            frames = min(float(thermal_k.THERMO_SUBSTEP_FRAMES), remaining)
            core = thermal_step(player.thermal, core, inp, frames)
            remaining -= frames
        stats.set(CharacterStat.TEMPERATURE, core)
