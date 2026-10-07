"""The wetness driver: rain, sweat and drying walk through clothing once per game minute (spec 06)."""

from dataclasses import dataclass

from data.body import thermal as thermal_k
from data.world.clock import MINUTES_PER_HOUR
from managers.body.stats.drivers import StatContext
from managers.body.thermoregulator import chunk_air, clamp
from modules.body.parts import BodyPart
from modules.body.stats import CharacterStat, Stats
from modules.entity.item import ItemEntity
from modules.entity.player import PlayerEntity
from modules.item import ClothingItem


@dataclass
class _Minute:
    """The inputs one minute's walk reads, and the deltas it collects."""

    rain: float
    drying: float
    still_c: float
    start_item: dict[int, float]
    item_delta: dict[int, float]
    items: dict[int, ItemEntity]
    skin_start: dict[BodyPart, float]
    skin_delta: dict[BodyPart, float]

    @property
    def raining(self) -> bool:
        return self.rain > 0


def rain_intensity(ctx: StatContext) -> float:
    """The rain that reaches the player; 0 indoors, in snow or below the minimum intensity."""
    sample = ctx.weather
    if sample is None or ctx.indoors or sample.precipitation_is_snow:
        return 0.0
    if sample.precipitation_intensity < thermal_k.RAIN_MIN_INTENSITY:
        return 0.0
    return sample.precipitation_intensity


def drying_rate(still_c: float) -> float:
    if still_c > thermal_k.DRYING_REFERENCE_C:
        return (
            thermal_k.DRYING_BASE_RATE
            + (still_c - thermal_k.DRYING_REFERENCE_C) * thermal_k.DRYING_PER_DEGREE
        )
    return thermal_k.DRYING_BASE_RATE


def _layers(player: PlayerEntity, part: BodyPart) -> list[ItemEntity]:
    return [e for e in player.layers_for(part) if isinstance(e.item, ClothingItem)]


def _water_resistance(entity: ItemEntity) -> float:
    item = entity.item
    return item.water_resistance if isinstance(item, ClothingItem) else 0.0


def _pass_one(player: PlayerEntity, part: BodyPart, m: _Minute) -> int:
    """Skin sweat and evaporation; passes the delta outward through the layers. Returns perspiring parts."""
    node = thermal_k.THERMAL_NODES[part]
    secondary = clamp(player.thermal.secondary[part], 0.0, 1.0)
    perspiration = secondary**2 * (
        thermal_k.PERSPIRATION_DIST_BASE
        + thermal_k.PERSPIRATION_DIST_SCALE * (1 - node.distance_to_core)
    )
    if perspiration > thermal_k.PERSPIRATION_MIN:
        base = perspiration
    elif m.raining:
        base = 0.0
    else:
        skin_temp = player.thermal.skin[part]
        evaporation = (
            (skin_temp - thermal_k.EVAPORATION_SKIN_FLOOR_C) / thermal_k.EVAPORATION_SKIN_RANGE_C
        ) ** 2
        base = -max(0.0, evaporation - m.rain)
    base *= thermal_k.WETNESS_INCREASE_per_min if base > 0 else thermal_k.WETNESS_DECREASE_per_min
    m.skin_delta[part] += base
    skin_after = m.skin_start[part] + m.skin_delta[part]
    perspiring = 1 if base > 0 else 0
    touched = (base > 0 and skin_after >= thermal_k.WETNESS_HYSTERESIS_WET) or (
        base < 0 and skin_after <= thermal_k.WETNESS_HYSTERESIS_DRY
    )
    if not touched:
        return perspiring
    delta = base
    if base > 0:
        outdoor = clamp(
            m.still_c + thermal_k.SWEAT_OUTDOOR_OFFSET_C, 0.0, thermal_k.SWEAT_OUTDOOR_SPAN_C
        )
        delta *= (
            thermal_k.SWEAT_OUTDOOR_BASE
            + thermal_k.SWEAT_OUTDOOR_SCALE * outdoor / thermal_k.SWEAT_OUTDOOR_SPAN_C
        )
    skipped = False
    for entity in _layers(player, part):
        if base > 0:
            perspiring += 1
        wet = m.start_item[id(entity)]
        if (
            part in entity.holes
            or (base > 0 and wet >= thermal_k.LAYER_SOAK_MAX)
            or (base < 0 and wet <= 0)
        ):
            skipped = True
            continue
        if base > 0:
            factor = max(0.0, 1 - _water_resistance(entity))
            if factor == 0:
                perspiring -= 1
                break
            delta *= factor
        if skipped:
            delta /= 2
        m.item_delta[id(entity)] += delta
        break
    return perspiring


def _pass_two(player: PlayerEntity, part: BodyPart, m: _Minute, perspiring: int) -> None:
    """Rain and air: the walk from the outermost layer inward, then the skin."""
    base = (
        m.rain * thermal_k.WETNESS_INCREASE_per_min
        if m.raining
        else -m.drying * thermal_k.WETNESS_DECREASE_per_min
    )
    inner_to_outer = _layers(player, part)
    divider = float(thermal_k.LAYER_DIVIDER)
    flagged = False
    for index in range(len(inner_to_outer) - 1, -1, -1):
        entity = inner_to_outer[index]
        wet = m.start_item[id(entity)]
        if part in entity.holes:
            flagged = True
            continue
        if m.raining and wet >= thermal_k.LAYER_SOAK_MAX:
            flagged = True
            continue
        if not m.raining and wet <= 0:
            flagged = True
            continue
        factor = 1.0
        if m.raining:
            factor = max(0.0, 1 - _water_resistance(entity))
            if factor == 0:
                break
        item = entity.item
        assert isinstance(item, ClothingItem)
        delta = base * factor / len(item.covers)
        if flagged:
            delta /= divider
        takes = m.raining or index >= perspiring - 1
        if takes:
            m.item_delta[id(entity)] += delta
            if flagged:
                divider *= 2
            if m.raining:
                break
    if inner_to_outer:
        innermost = m.start_item[id(inner_to_outer[0])]
        skin_now = m.skin_start[part] + m.skin_delta[part]
        rain_reaches = (
            m.raining
            and innermost >= thermal_k.SKIN_RAIN_INNER_MIN
            and skin_now <= thermal_k.LAYER_SOAK_MAX
        )
        air_reaches = not m.raining and innermost <= thermal_k.SKIN_DRY_INNER_MAX
        if perspiring == 0 and (rain_reaches or air_reaches):
            m.skin_delta[part] += base / 2
    else:
        m.skin_delta[part] += base


def walk_minute(player: PlayerEntity, stats: Stats, ctx: StatContext) -> None:
    """One game minute of wetting and drying, then the merge into body wetness."""
    air, _ = chunk_air(ctx)
    rain = rain_intensity(ctx)
    body = stats.get(CharacterStat.WETNESS)
    m = _Minute(
        rain=rain,
        drying=drying_rate(air.still_c),
        still_c=air.still_c,
        start_item={},
        item_delta={},
        items={},
        skin_start={part: body for part in BodyPart},
        skin_delta={part: 0.0 for part in BodyPart},
    )
    for part in BodyPart:
        for entity in _layers(player, part):
            m.start_item[id(entity)] = entity.wetness
            m.item_delta.setdefault(id(entity), 0.0)
            m.items[id(entity)] = entity
    for part in BodyPart:
        perspiring = _pass_one(player, part, m)
        _pass_two(player, part, m, perspiring)
    for key, entity in m.items.items():
        entity.wetness = clamp(m.start_item[key] + m.item_delta[key], 0.0, thermal_k.LAYER_SOAK_MAX)
    changes = [
        clamp(body + m.skin_delta[part], 0.0, thermal_k.LAYER_SOAK_MAX) - body for part in BodyPart
    ]
    mean_change = sum(changes) / len(changes)
    stats.set(CharacterStat.WETNESS, body + (1 - thermal_k.BODY_MERGE_FACTOR) * mean_change)


class WetnessDriver:
    def apply(self, stats: Stats, hours: float, ctx: StatContext) -> None:
        player = ctx.wearer
        if player is None:
            return
        for _ in range(max(1, round(hours * MINUTES_PER_HOUR))):
            walk_minute(player, stats, ctx)
