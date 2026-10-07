"""Survival stat engine: runs the stat drivers over game time (spec 02)."""

import dataclasses
import logging
import random
from collections.abc import Callable

from data.body import survival as k
from data.body.status_effects import FOOD_EATEN_DRAIN_per_hour
from data.world.clock import MINUTES_PER_HOUR
from managers.body.cold import ColdDriver
from managers.body.stats.drivers import BodyMultipliers, StatContext, StatDriver, default_drivers
from managers.body.stats.status_effects import (
    food_eaten_level,
    level_change_facts,
    player_status_effect_levels,
)
from managers.body.thermoregulator import ThermoregulatorDriver
from managers.body.wetness import WetnessDriver
from modules.entity.player import PlayerEntity
from modules.world.weather import WeatherSample

logger = logging.getLogger(__name__)


class StatsEngine:
    """Runs every registered driver over a span of minutes in chunks of at most 10.

    After `advance`, `minutes_advanced` is how many minutes passed.
    """

    def __init__(
        self, drivers: list[StatDriver] | None = None, rng: random.Random | None = None
    ) -> None:
        self._drivers: list[StatDriver] = (
            drivers
            if drivers is not None
            else [*default_drivers(), WetnessDriver(), ThermoregulatorDriver(), ColdDriver(rng)]
        )
        self.minutes_advanced = 0

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
        facts: list[str] = []
        remaining = minutes
        body_given = ctx.body != BodyMultipliers()
        while remaining > 0:
            chunk = min(k.MAX_CHUNK_MINUTES, remaining)
            if not body_given:
                thermal = player.thermal
                ctx = dataclasses.replace(
                    ctx,
                    body=BodyMultipliers(
                        thermal.energy_mult, thermal.fluids_mult, thermal.fatigue_mult
                    ),
                )
            if weather_for_chunk is not None:
                ctx = dataclasses.replace(
                    ctx, weather=weather_for_chunk(self.minutes_advanced, chunk)
                )
            facts.extend(self._advance_chunk(player, chunk, ctx))
            self.minutes_advanced += chunk
            remaining -= chunk
            ctx = dataclasses.replace(ctx, new_zombies_seen=0, sound_stress=0.0)
        return facts

    def _advance_chunk(self, player: PlayerEntity, minutes: int, ctx: StatContext) -> list[str]:
        stats = player.stats
        hours = minutes / MINUTES_PER_HOUR
        before = player_status_effect_levels(player)
        ctx = dataclasses.replace(ctx, food_eaten_level=food_eaten_level(player), wearer=player)
        player.thermal.facts.clear()
        for driver in self._drivers:
            driver.apply(stats, hours, ctx)
        player.food_eaten_timer = max(
            0.0, player.food_eaten_timer - FOOD_EATEN_DRAIN_per_hour * hours
        )
        facts = level_change_facts(
            player.appearance.forename, before, player_status_effect_levels(player)
        )
        facts.extend(player.thermal.facts)
        return facts
