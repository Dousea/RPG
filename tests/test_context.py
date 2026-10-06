"""ContextBuilder: the knowledge-firewall boundary between state and prompts."""

import unittest

from managers.context import ContextBuilder
from managers.game import GameManager
from modules.action import DiscoverFlagAction, MoveAction, SetFlagAction
from modules.quest import QuestState
from modules.stats import CharacterStat
from tests.support import resolve_actions


class WorldFlagFirewallTests(unittest.TestCase):
    """doc 11's actual complaint: every world flag went out unfiltered,
    whether or not anything in the story ever revealed it to the player."""

    def setUp(self):
        self.gm = GameManager()
        self.builder = ContextBuilder(self.gm)

    def test_an_undiscovered_flag_never_reaches_the_narrator_prompt(self):
        resolve_actions(self.gm, SetFlagAction(flag_name="power_grid_stable", value=False))
        prompt = self.builder.build_narrator_prompt("look")
        self.assertNotIn("power_grid_stable", prompt)

    def test_a_discovered_flag_reaches_the_narrator_prompt(self):
        resolve_actions(
            self.gm,
            SetFlagAction(flag_name="power_grid_stable", value=False),
            DiscoverFlagAction(flag_name="power_grid_stable"),
        )
        prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("power_grid_stable=False", prompt)

    def test_discovering_a_flag_that_was_never_set_is_harmless(self):
        resolve_actions(self.gm, DiscoverFlagAction(flag_name="never_set"))
        prompt = self.builder.build_narrator_prompt("look")
        # Nothing to show -- the flag has no value -- but this must not raise.
        self.assertIn("Flags: None", prompt)

    def test_setting_the_same_flag_twice_does_not_undiscover_it(self):
        resolve_actions(
            self.gm,
            SetFlagAction(flag_name="power_grid_stable", value=False),
            DiscoverFlagAction(flag_name="power_grid_stable"),
            SetFlagAction(flag_name="power_grid_stable", value=True),
        )
        prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("power_grid_stable=True", prompt)


class ParserPromptFirewallTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()
        self.builder = ContextBuilder(self.gm)

    def test_parser_prompt_carries_no_relationship_or_flag_data_at_all(self):
        resolve_actions(
            self.gm,
            SetFlagAction(flag_name="power_grid_stable", value=False),
            DiscoverFlagAction(flag_name="power_grid_stable"),
        )
        prompt = self.builder.build_parser_prompt("look")
        self.assertNotIn("power_grid_stable", prompt)
        self.assertNotIn("Disposition", prompt)


class ZoneContextTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()
        self.builder = ContextBuilder(self.gm)

    def test_parser_prompt_lists_the_zone_roster(self):
        # The parser can only aim MOVE_TO at a zone it has been told exists.
        prompt = self.builder.build_parser_prompt("look")
        self.assertIn("[ZONES]", prompt)
        for zone in ("Your Apartment", "Your Building", "The Street", "The Neighborhood"):
            self.assertIn(zone, prompt)

    def test_parser_prompt_zone_count_is_derived_not_hard_coded(self):
        # The roster's zone count comes from the world, not a literal
        # "four" that would silently go stale if a zone were added or
        # removed.
        prompt = self.builder.build_parser_prompt("look")
        self.assertIn(f"{len(self.gm.world.locations)} zones", prompt)

    def test_parser_prompt_lists_at_least_one_alias_per_zone(self):
        # Naming a listed landmark, not just the zone's own name, moves
        # Orton there -- the roster must actually show that.
        prompt = self.builder.build_parser_prompt("look")
        for location in self.gm.world.locations.values():
            self.assertTrue(location.aliases, f"{location.id} has no aliases to list")
            self.assertIn(location.aliases[0], prompt)

    def test_prompts_carry_the_specific_spot(self):
        resolve_actions(self.gm, MoveAction(destination="the kitchen"))
        parser_prompt = self.builder.build_parser_prompt("look")
        narrator_prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("Specific spot: the kitchen", parser_prompt)
        self.assertIn("Specific spot: the kitchen", narrator_prompt)


class NpcGoalVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()
        # Orton now starts alone in his apartment; Emma starts in zone_building.
        self.gm.player.current_location_id = "zone_building"
        self.builder = ContextBuilder(self.gm)

    def test_npc_goals_are_shown_as_visible_intent(self):
        emma = self.gm.resolve_npc("Emma")
        emma.goals.append("find out who the new neighbor is")
        prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("Visible intent: find out who the new neighbor is", prompt)

    def test_npc_knowledge_is_never_rendered(self):
        emma = self.gm.resolve_npc("Emma")
        emma.knowledge.add("secret_bunker_location")
        prompt = self.builder.build_narrator_prompt("look")
        self.assertNotIn("secret_bunker_location", prompt)


class QuestVisibilityTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()
        self.builder = ContextBuilder(self.gm)

    def test_an_active_quests_title_and_open_objective_are_shown(self):
        self.gm.quests.clear()
        self.gm.quests["find_the_bunker"] = QuestState(
            quest_id="find_the_bunker",
            title="Find the Bunker",
            objectives=["discover:bunker_location"],
            objective_labels={"discover:bunker_location": "Locate the bunker"},
        )
        prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("Find the Bunker", prompt)
        self.assertIn("[ ] Locate the bunker", prompt)

    def test_a_completed_objective_is_checked_off(self):
        # Two objectives, not one -- a quest whose only objective just
        # finished completes outright and drops out of [QUESTS] entirely
        # (see ContextBuilder._quests_section), so a single-objective quest
        # here would never render its own checkmark to assert on.
        self.gm.quests.clear()
        self.gm.quests["get_gear"] = QuestState(
            quest_id="get_gear",
            title="Get Some Gear",
            objectives=["reach:zone_street", "take:item_crowbar"],
            objective_labels={
                "reach:zone_street": "Get to the street",
                "take:item_crowbar": "Find something to defend yourself with",
            },
        )
        resolve_actions(self.gm, MoveAction(destination="out"), MoveAction(destination="out"))
        prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("[x] Get to the street", prompt)
        self.assertIn("[ ] Find something to defend yourself with", prompt)

    def test_a_quest_with_no_label_falls_back_to_its_raw_key(self):
        self.gm.quests.clear()
        self.gm.quests["mystery"] = QuestState(
            quest_id="mystery", objectives=["discover:something"]
        )
        prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("[ ] discover:something", prompt)

    def test_no_active_quests_renders_none(self):
        self.gm.quests.clear()
        prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("[QUESTS]", prompt)
        self.assertIn("None", prompt)


class ConditionBlockTests(unittest.TestCase):
    """Spec 03, What the narrator and the player see."""

    def setUp(self):
        self.gm = GameManager()
        self.builder = ContextBuilder(self.gm)

    def test_condition_lists_status_effects_by_name_and_level(self):
        self.gm.player.stats.set(CharacterStat.HUNGER, 0.5)
        self.gm.player.stats.set(CharacterStat.FATIGUE, 0.61)
        prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("[CONDITION]", prompt)
        self.assertIn("Very Hungry (3/4), Drowsy (1/4)", prompt)

    def test_condition_never_carries_a_raw_stat_value(self):
        self.gm.player.stats.set(CharacterStat.HUNGER, 0.5123)
        self.gm.player.stats.set(CharacterStat.THIRST, 0.3377)
        self.gm.player.stats.set(CharacterStat.PANIC, 41.25)
        prompt = self.builder.build_narrator_prompt("look")
        condition = prompt.split("[CONDITION]")[1].split("[")[0]
        for raw in ("0.5123", "0.3377", "41.25", "0.51", "0.34"):
            self.assertNotIn(raw, condition)

    def test_a_player_with_no_status_effects_reads_as_fine(self):
        prompt = self.builder.build_narrator_prompt("look")
        condition = prompt.split("[CONDITION]")[1].split("[DEEP MEMORY]")[0]
        self.assertTrue(condition.strip().endswith("Fine"))

    def test_the_parser_sees_the_same_status_effect_list(self):
        self.gm.player.stats.set(CharacterStat.FATIGUE, 0.85)
        prompt = self.builder.build_parser_prompt("sleep")
        self.assertIn("Very Tired (3/4)", prompt)

    def test_the_well_fed_timer_shows_as_a_status_effect(self):
        self.gm.player.food_eaten_timer = 2000
        prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("Well Fed (2/4)", prompt)


if __name__ == "__main__":
    unittest.main()


class WeatherWordBandTests(unittest.TestCase):
    """Spec 04, Word bands."""

    def test_wind_bands(self):
        from managers.climate import wind_word

        self.assertEqual(wind_word(0.05), "still")
        self.assertEqual(wind_word(0.06), "mild")
        self.assertEqual(wind_word(0.25), "mild")
        self.assertEqual(wind_word(0.26), "moderate")
        self.assertEqual(wind_word(0.5), "moderate")
        self.assertEqual(wind_word(0.51), "strong")
        self.assertEqual(wind_word(0.76), "storm-strength")

    def test_cloud_bands(self):
        from managers.climate import cloud_word

        self.assertEqual(cloud_word(0.0), "clear skies")
        self.assertEqual(cloud_word(0.4), "clear skies")
        self.assertEqual(cloud_word(0.41), "some clouds")
        self.assertEqual(cloud_word(0.7), "some clouds")
        self.assertEqual(cloud_word(0.71), "overcast")

    def test_fog_bands(self):
        from managers.climate import fog_word

        self.assertIsNone(fog_word(0.2))
        self.assertEqual(fog_word(0.21), "light fog")
        self.assertEqual(fog_word(0.75), "light fog")
        self.assertEqual(fog_word(0.76), "thick fog")
        self.assertEqual(fog_word(0.99), "thick fog")
        self.assertEqual(fog_word(1.0), "very thick fog")

    def test_temperature_bands(self):
        from managers.climate import temperature_word

        for value, word in [
            (-10.1, "freezing"),
            (-10.0, "freezing"),
            (-9.9, "bitter cold"),
            (0.0, "bitter cold"),
            (0.1, "cold"),
            (8.0, "cold"),
            (8.1, "chilly"),
            (15.1, "mild"),
            (22.1, "warm"),
            (29.1, "hot"),
        ]:
            self.assertEqual(temperature_word(value), word, value)


class WeatherBlockTests(unittest.TestCase):
    """Spec 04, What the narrator and the player see."""

    def setUp(self):
        self.gm = GameManager()
        self.builder = ContextBuilder(self.gm)

    def _weather_block(self, prompt: str) -> str:
        return prompt.split("[WEATHER]")[1].split("\n\n[")[0]

    def test_narrator_block_has_no_raw_numbers(self):
        self.gm.climate.start_period(0, 0.9)
        block = self._weather_block(self.builder.build_narrator_prompt("look"))
        self.assertNotRegex(block, r"\d")
        self.assertIn("Sheltered", block)

    def test_parser_prompt_carries_the_same_block(self):
        self.assertIn("[WEATHER]", self.builder.build_parser_prompt("look"))

    def test_shelter_follows_the_zone(self):
        block = self._weather_block(self.builder.build_narrator_prompt("look"))
        self.assertIn("yes", block)
        resolve_actions(self.gm, MoveAction(destination="street"))
        block = self._weather_block(self.builder.build_narrator_prompt("look"))
        self.assertIn("no", block)

    def test_stage_phrases_turn_to_snow_when_it_snows(self):
        from managers.climate import precipitation_phrase

        self.assertEqual(precipitation_phrase("heavy_precipitation", False), "heavy rain")
        self.assertEqual(precipitation_phrase("heavy_precipitation", True), "heavy snow")
        self.assertEqual(precipitation_phrase(None, False), "dry")


class WeatherFactTests(unittest.TestCase):
    """Spec 04, What the narrator and the player see: outcomes."""

    def _sample(self, **changes):
        from modules.weather import WeatherSample

        base = {
            "air_temperature": 10.0,
            "humidity": 0.5,
            "wind_intensity": 0.1,
            "wind_angle": 0.0,
            "cloud_intensity": 0.3,
            "precipitation_intensity": 0.0,
            "precipitation_is_snow": False,
            "fog_intensity": 0.2,
            "daylight": 1.0,
        }
        return WeatherSample(**{**base, **changes})

    def test_changes_become_facts(self):
        from managers.climate import weather_change_facts

        dry = self._sample()
        rain = self._sample(precipitation_intensity=0.5, stage="showers")
        snow = self._sample(precipitation_intensity=0.5, precipitation_is_snow=True)
        thunder = self._sample(precipitation_intensity=1.0, thunder=True)
        foggy = self._sample(fog_intensity=0.6)
        self.assertEqual(weather_change_facts(dry, rain), ["It starts to rain."])
        self.assertEqual(weather_change_facts(rain, snow), ["The rain turns to snow."])
        self.assertEqual(weather_change_facts(snow, dry), ["The snow stops."])
        self.assertEqual(weather_change_facts(rain, thunder), ["Thunder rolls overhead."])
        self.assertEqual(weather_change_facts(foggy, dry), ["The fog lifts."])
        self.assertEqual(weather_change_facts(dry, dry), [])

    def test_a_waited_span_reports_the_rain_starting(self):
        from managers.simulation import SimulationCore
        from modules.action import Duration, WaitAction

        gm = GameManager()
        gm.climate.start_period(gm.narrative.minutes // 60 + 1, 0.5)
        facts = SimulationCore(gm).resolve([WaitAction(duration=Duration(minutes=240))])
        self.assertIn("It starts to rain.", facts)

    def test_thunder_is_reported_once(self):
        from managers.climate import weather_change_facts

        thunder = self._sample(precipitation_intensity=1.0, thunder=True)
        self.assertEqual(weather_change_facts(thunder, thunder), [])

    def test_fog_rolling_in_is_a_fact(self):
        from managers.climate import weather_change_facts

        self.assertEqual(
            weather_change_facts(self._sample(), self._sample(fog_intensity=0.5)),
            ["Fog rolls in."],
        )

    def test_the_block_lists_fog_only_above_point_two(self):
        from managers.climate import describe_weather

        self.assertIn("Fog: light fog", describe_weather(self._sample(fog_intensity=0.6), True))
        self.assertNotIn("Fog", describe_weather(self._sample(fog_intensity=0.2), True))

    def test_every_stage_has_a_rain_and_a_snow_phrase(self):
        from data.climate import STAGE_PHRASES
        from managers.climate import precipitation_phrase

        for stage, (rain, snow) in STAGE_PHRASES.items():
            self.assertEqual(precipitation_phrase(stage, False), rain)
            self.assertEqual(precipitation_phrase(stage, True), snow)
        self.assertEqual(precipitation_phrase("storm", True), "a snow storm")
