"""The cold driver: catching, worsening and recovering from a cold, and its sneezes (spec 06)."""

import logging
import random

from data import thermal as k
from data import traits as trait_k
from data.clock import MINUTES_PER_HOUR
from managers.stats.drivers import StatContext, trait_mult
from managers.stats.status_effects import hypothermia_level, status_effect_level
from managers.thermoregulator import NodeClothing, part_clothing
from modules.body import BodyPart
from modules.stats import CharacterStat, Stats, StatusEffect
from modules.thermal import ThermalState

logger = logging.getLogger(__name__)


def catch_cold_delta(
    state: ThermalState,
    clothing: dict[BodyPart, NodeClothing],
    hypothermia: int,
    body_wetness: float = 0.0,
) -> float:
    """How fast the body is catching a cold: cold skin, wet skin and wet clothes, node by node.

    `body_wetness` is 0 to 1.
    """
    total = 0.0
    for part, node in k.THERMAL_NODES.items():
        skin = state.skin[part]
        if skin >= k.COLD_SKIN_BELOW_C:
            continue
        chill = (1 - (skin - k.COLD_SKIN_FLOOR_C) / k.COLD_SKIN_RANGE_C) ** 2
        add = k.COLD_NODE_FACTOR * chill * node.skin_surface
        if body_wetness > 0:
            add *= 1 + body_wetness
        cover = clothing.get(part)
        if cover is not None and cover.wetness > k.WET_CLOTHING_FROM:
            add *= 1 + (cover.wetness - k.WET_CLOTHING_FROM) * 2
        total += add * k.CATCH_COLD_NODE_WEIGHTS.get(part, 1)
    if hypothermia > k.HYPOTHERMIA_DELTA_FROM_LEVEL:
        total *= hypothermia
    return total


def start_cold(state: ThermalState, stats: Stats) -> None:
    """The counter reached its threshold: a cold begins at its starting strength."""
    stats.set(CharacterStat.COLD_STRENGTH, k.COLD_START_STRENGTH)
    state.catch_cold = 0.0
    state.sneeze_timer = 0.0


def roll_sneeze(level: int, rng: random.Random) -> tuple[bool, float]:
    """Whether a trigger at Has a Cold `level` is a sneeze (else a cough), and the next timer in frames."""
    low, high = k.SNEEZE_TIMER_FRAMES[min(level, max(k.SNEEZE_TIMER_FRAMES))]
    sneeze = level == k.SNEEZE_MIN_LEVEL or rng.randrange(k.SNEEZE_COIN_SIDES) > k.SNEEZE_COIN_ABOVE
    return sneeze, low + rng.randrange(high - low)


class ColdDriver:
    """Runs the catch counter, the course and the sneeze timer once per game minute."""

    def __init__(self, rng: random.Random | None = None) -> None:
        self._rng = rng if rng is not None else random.Random()

    def apply(self, stats: Stats, hours: float, ctx: StatContext) -> None:
        player = ctx.wearer
        if player is None:
            return
        state = player.thermal
        clothing = {part: part_clothing(player.layers_for(part), part) for part in BodyPart}
        level = hypothermia_level(
            stats.get(CharacterStat.TEMPERATURE), stats.get(CharacterStat.INTOXICATION)
        )
        delta = catch_cold_delta(
            state, clothing, level, stats.get(CharacterStat.WETNESS) / k.LAYER_SOAK_MAX
        )
        for _ in range(max(1, round(hours * MINUTES_PER_HOUR))):
            self._catch(stats, state, delta, ctx.traits)
            if stats.get(CharacterStat.COLD_STRENGTH) > 0:
                self._course(stats, state, ctx)
                self._sneeze(stats, state, player.appearance.forename)

    def _catch(
        self, stats: Stats, state: ThermalState, delta: float, traits: frozenset[str]
    ) -> None:
        has_cold = stats.get(CharacterStat.COLD_STRENGTH) > 0
        if delta > k.CATCH_COLD_DELTA_MIN:
            if has_cold:
                return
            delta *= trait_mult(trait_k.CATCH_COLD_TRAIT_MULT, traits)
            state.catch_cold += k.CATCH_COLD_INCREASE_per_min * delta
            if state.catch_cold >= k.CATCH_COLD_THRESHOLD:
                start_cold(state, stats)
                logger.debug("A cold starts.")
        else:
            state.catch_cold = max(0.0, state.catch_cold - k.CATCH_COLD_DECREASE_per_min)

    def _recovering(self, stats: Stats, state: ThermalState, ctx: StatContext) -> bool:
        if state.cold_reduction > 0:
            return True
        return (
            ctx.indoors
            and status_effect_level(StatusEffect.WET, stats.get(CharacterStat.WETNESS)) == 0
            and hypothermia_level(
                stats.get(CharacterStat.TEMPERATURE), stats.get(CharacterStat.INTOXICATION)
            )
            == 0
            and stats.get(CharacterStat.FATIGUE) <= k.COLD_RECOVER_FATIGUE_MAX
            and stats.get(CharacterStat.HUNGER) <= k.COLD_RECOVER_HUNGER_MAX
            and stats.get(CharacterStat.THIRST) <= k.COLD_RECOVER_THIRST_MAX
        )

    def _course(self, stats: Stats, state: ThermalState, ctx: StatContext) -> None:
        strength = stats.get(CharacterStat.COLD_STRENGTH)
        step = k.COLD_PROGRESSION_per_min
        if self._recovering(stats, state, ctx):
            step *= trait_mult(trait_k.COLD_RECOVERY_TRAIT_MULT, ctx.traits)
            if state.cold_reduction > 0:
                step *= k.COLD_REDUCTION_STRENGTH_MULT
            strength -= step
        else:
            strength += step * trait_mult(trait_k.COLD_WORSENING_TRAIT_MULT, ctx.traits)
        state.cold_reduction = max(0.0, state.cold_reduction - k.COLD_REDUCTION_per_min)
        if strength < 0:
            stats.set(CharacterStat.COLD_STRENGTH, 0.0)
            state.catch_cold = 0.0
            state.sneeze_timer = 0.0
            return
        stats.set(CharacterStat.COLD_STRENGTH, min(strength, k.COLD_STRENGTH_MAX))

    def _sneeze(self, stats: Stats, state: ThermalState, name: str) -> None:
        level = status_effect_level(StatusEffect.HAS_A_COLD, stats.get(CharacterStat.COLD_STRENGTH))
        frames = k.SNEEZE_FRAMES_PER_MIN
        state.sneeze_active = max(0.0, state.sneeze_active - frames)
        if level < k.SNEEZE_MIN_LEVEL:
            return
        if state.sneeze_timer > frames:
            state.sneeze_timer -= frames
            return
        left = frames - max(state.sneeze_timer, 0.0)
        sneeze, timer = roll_sneeze(level, self._rng)
        fact = k.SNEEZE_FACT if sneeze else k.COUGH_FACT
        state.facts.append(fact.format(name=name))
        state.sneeze_timer = timer - left
        state.sneeze_active = max(0.0, k.SNEEZE_OR_COUGH_ACTIVE_FRAMES - left)
