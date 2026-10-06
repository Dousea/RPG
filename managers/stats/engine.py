"""Survival stat engine: runs the stat drivers over game time (spec 02)."""

import dataclasses
import logging
import math
from collections.abc import Callable

from data import survival as k
from data.clock import MINUTES_PER_HOUR
from data.status_effects import FOOD_EATEN_DRAIN_per_hour
from managers.stats.drivers import StatContext, StatDriver, default_drivers
from managers.stats.status_effects import (
    food_eaten_level,
    level_change_facts,
    player_status_effect_levels,
)
from modules.entity.player import PlayerEntity
from modules.stats import CharacterStat, StatusEffect
from modules.weather import WeatherSample

logger = logging.getLogger(__name__)

WEAKENING_FACTS = {
    "starvation": "Orton is weakening from hunger.",
    "thirst": "Orton is weakening from thirst.",
    "fever": "Orton is weakening from fever.",
}


class StatsEngine:
    """Runs every registered driver over a span of minutes in chunks of at most 10.

    After `advance`, `minutes_advanced` is how many minutes actually passed (less
    than asked when the player died), `health_lost` is the fractional HP the
    status effects took, and `death_cause` is set when they took the last of it.
    """

    def __init__(self, drivers: list[StatDriver] | None = None) -> None:
        self._drivers: list[StatDriver] = drivers if drivers is not None else default_drivers()
        self.minutes_advanced = 0
        self.health_lost = 0.0
        self.death_cause = ""
        self._weakening_reported: set[str] = set()

    def register(self, driver: StatDriver) -> None:
        self._drivers.append(driver)

    def advance(
        self,
        player: PlayerEntity,
        minutes: int,
        ctx: StatContext,
        weather_for_chunk: Callable[[int, int], WeatherSample] | None = None,
    ) -> list[str]:
        """Advance the player's stats by `minutes`; returns status-effect-change and health facts.

        `weather_for_chunk(offset, chunk)` gives the weather of the chunk that
        starts `offset` minutes in and lasts `chunk` minutes.
        """
        self.minutes_advanced = 0
        self.health_lost = 0.0
        self.death_cause = ""
        self._weakening_reported = set()
        facts: list[str] = []
        remaining = minutes
        while remaining > 0:
            chunk = min(k.MAX_CHUNK_MINUTES, remaining)
            if weather_for_chunk is not None:
                ctx = dataclasses.replace(
                    ctx, weather=weather_for_chunk(self.minutes_advanced, chunk)
                )
            facts.extend(self._advance_chunk(player, chunk, ctx))
            self.minutes_advanced += chunk
            remaining -= chunk
            ctx = dataclasses.replace(ctx, new_zombies_seen=0)
            if self.death_cause:
                break
        return facts

    def _advance_chunk(self, player: PlayerEntity, minutes: int, ctx: StatContext) -> list[str]:
        stats = player.stats
        hours = minutes / MINUTES_PER_HOUR
        before = player_status_effect_levels(player)
        ctx = dataclasses.replace(ctx, food_eaten_level=food_eaten_level(player))
        for driver in self._drivers:
            driver.apply(stats, hours, ctx)
        player.food_eaten_timer = max(
            0.0, player.food_eaten_timer - FOOD_EATEN_DRAIN_per_hour * hours
        )
        drivers_done = player_status_effect_levels(player)
        health_facts = self._lose_health(player, drivers_done, hours)
        facts = level_change_facts(before, player_status_effect_levels(player))
        facts.extend(health_facts)
        return facts

    def _lose_health(
        self, player: PlayerEntity, levels: dict[StatusEffect, int], hours: float
    ) -> list[str]:
        stats = player.stats
        sources: list[tuple[float, str]] = []
        if levels[StatusEffect.HUNGRY] >= k.SEVERE_STATUS_EFFECT_LEVEL:
            sources.append((k.STARVING_HP_LOSS_per_hour, "starvation"))
        if levels[StatusEffect.THIRST] >= k.SEVERE_STATUS_EFFECT_LEVEL:
            sources.append((k.DYING_OF_THIRST_HP_LOSS_per_hour, "thirst"))
        if levels[StatusEffect.SICK] >= k.SEVERE_STATUS_EFFECT_LEVEL and stats.get(
            CharacterStat.FOOD_SICKNESS
        ) > stats.get(CharacterStat.ZOMBIE_INFECTION):
            sources.append((k.FEVER_HP_LOSS_per_hour, "fever"))
        if not sources:
            return []
        loss = sum(rate for rate, _ in sources) * hours
        self.health_lost += loss
        player.fractional_hp_loss += loss
        whole = math.floor(player.fractional_hp_loss)
        player.fractional_hp_loss -= whole
        player.hit_points -= whole
        if player.hit_points > 0:
            facts: list[str] = []
            for _, cause in sources:
                if cause not in self._weakening_reported:
                    self._weakening_reported.add(cause)
                    facts.append(WEAKENING_FACTS[cause])
            return facts
        player.fractional_hp_loss = 0.0
        cause = max(sources)[1]
        self.death_cause = f"Orton died of {cause}."
        return [self.death_cause]
