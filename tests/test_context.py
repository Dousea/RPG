"""ContextBuilder: the knowledge-firewall boundary between state and prompts."""

import unittest

from adapters import llm
from data.items import ITEMS
from managers import creation
from managers.context import ContextBuilder
from managers.game import GameManager
from managers.simulation import SimulationCore
from modules.action.types import (
    DiscoverFlagAction,
    DropAction,
    Duration,
    MoveAction,
    SetFlagAction,
    WaitAction,
)
from modules.character.appearance import Appearance, Gender
from modules.character.build import CharacterBuild
from modules.character.equipment import CharacterHoldableSlot
from modules.entity.item import ItemEntity
from modules.entity.zombie import AttackSide, ZombieEntity, ZombieState
from modules.quest import QuestState
from modules.stats import CharacterStat
from modules.weather import WeatherSample
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

    def test_condition_lists_the_temperature_status_effects_without_numbers(self):
        """Spec 06, What the narrator and the player see."""
        stats = self.gm.player.stats
        stats.set(CharacterStat.WETNESS, 41.7)
        stats.set(CharacterStat.TEMPERATURE, 34.8)
        stats.set(CharacterStat.COLD_STRENGTH, 61.3)
        stats.set(CharacterStat.WINDCHILL, 11.9)
        prompt = self.builder.build_narrator_prompt("look")
        condition = prompt.split("[CONDITION]")[1].split("[")[0]
        self.assertIn("Wet (2/4)", condition)
        self.assertIn("Heavy Cold (3/4)", condition)
        self.assertIn("Cold (2/4)", condition)
        self.assertIn("Wind Chill (2/4)", condition)
        for raw in ("41.7", "34.8", "61.3", "11.9"):
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


class HitPointsStayOutOfTheNarratorPromptTests(unittest.TestCase):
    """docs/01-engine-authority.md: the narrator gets HP and item condition in
    words, never as numbers."""

    def setUp(self):
        self.gm = GameManager()
        self.builder = ContextBuilder(self.gm)

    def _character(self) -> str:
        prompt = self.builder.build_narrator_prompt("look")
        return prompt.split("[CHARACTER]")[1].split("[CONDITION]")[0]

    def test_player_hit_points_are_not_in_the_prompt(self):
        self.gm.player.hit_points = 37
        prompt = self.builder.build_narrator_prompt("look")
        self.assertNotIn("37", prompt)
        self.assertNotIn("Health:", prompt)
        self.assertIn("Severe Injuries (3/4)", prompt)

    def test_item_condition_is_a_word(self):
        key = self.gm.player.inventory[0]
        cases = (
            (key.max_hit_points, "intact"),
            (key.max_hit_points // 2, "worn"),
            (key.max_hit_points // 2 - 1, "damaged"),
            (1, "damaged"),
            (0, "broken"),
        )
        for hit_points, word in cases:
            with self.subTest(hit_points=hit_points):
                key.hit_points = hit_points
                character = self._character()
                self.assertIn(f"{key.item.name} ({word})", character)
                self.assertNotIn(f"{hit_points}/", character)

    def test_equipped_item_condition_is_a_word(self):
        key = self.gm.player.inventory[0]
        key.hit_points = 0
        self.gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND] = key
        self.assertIn(f"RIGHT_HAND: {key.item.name} (broken)", self._character())


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
        from modules.action.types import Duration, WaitAction

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


MARA = CharacterBuild(
    appearance=Appearance(
        forename="Mara",
        surname="Quinn",
        gender=Gender.FEMALE,
        skin_tone=4,
        hair_style="ponytail",
        hair_colour="red",
        backstory="Left the city for a night shift and never went home.",
    ),
    occupation_id="nurse",
    traits=("brave", "hemophobic"),
    outfit=("item_tshirt", "item_jeans"),
)


class CharacterBlockTests(unittest.TestCase):
    """Spec 07, What the narrator and the parser see."""

    def setUp(self):
        self.assertEqual(creation.validate(MARA), [])
        self.gm = GameManager(player=creation.new_player(MARA))
        self.builder = ContextBuilder(self.gm)
        self.prompt = self.builder.build_narrator_prompt("look")

    def character_block(self) -> str:
        return self.prompt.split("[CHARACTER]")[1].split("[CONDITION]")[0]

    def test_the_block_names_the_character_pronouns_occupation_looks_and_traits(self):
        block = self.character_block()
        self.assertIn("Name: Mara Quinn", block)
        self.assertIn("she/her", block)
        self.assertIn("Occupation: Nurse", block)
        self.assertIn("brown skin", block)
        self.assertIn("ponytail red hair", block)
        self.assertIn("Left the city for a night shift", block)
        self.assertIn("Brave:", block)
        self.assertIn("Fear of Blood:", block)
        self.assertIn("Night Owl:", block)

    def test_a_job_title_replaces_the_occupation_name(self):
        build = CharacterBuild(
            appearance=Appearance(forename="Sam"),
            occupation_id="unemployed",
            job_title="Software Developer",
        )
        prompt = ContextBuilder(
            GameManager(player=creation.new_player(build))
        ).build_narrator_prompt("look")
        self.assertIn("Occupation: Software Developer", prompt)

    def test_the_block_shows_no_costs_points_or_skill_numbers(self):
        block = self.character_block()
        lowered = block.lower()
        for word in ("cost", "points"):
            self.assertNotIn(word, lowered)
        details = [
            line
            for line in block.splitlines()
            if line.startswith(("Name", "Pronouns", "Occupation", "Appearance", "Backstory"))
        ]
        self.assertFalse(any(char.isdigit() for char in "".join(details)))

    def test_the_block_lists_skills_from_level_one_in_words(self):
        """Spec 08, What the narrator and the player see."""
        skills_line = next(
            line for line in self.character_block().splitlines() if line.startswith("Skills:")
        )
        self.assertEqual(
            skills_line,
            "Skills: First Aid (capable), Fitness (skilled), Strength (skilled), Lightfooted (novice)",
        )
        self.assertFalse(any(char.isdigit() for char in skills_line))

    def test_the_block_has_no_level_or_xp_line(self):
        self.assertNotIn("XP", self.character_block())
        self.assertNotIn("Level:", self.character_block())

    def test_no_prompt_names_orton_unless_the_character_is_orton(self):
        parser = self.builder.build_parser_prompt("go out")
        for text in (self.prompt, parser, llm.PARSER_SYSTEM_PROMPT, llm.NARRATOR_SYSTEM_PROMPT):
            self.assertNotIn("Orton", text)
        self.assertIn("Mara", parser)
        self.assertIn("she/her", parser)

    def test_the_preset_is_named_orton_in_the_prompts(self):
        prompt = ContextBuilder(GameManager()).build_narrator_prompt("look")
        self.assertIn("Name: Orton", prompt)
        self.assertIn("he/him", prompt)
        self.assertIn("Software Developer", prompt)

    def test_engine_facts_use_the_forename_and_pronouns(self):
        facts = resolve_actions(self.gm, WaitAction(duration=Duration(minutes=10)))
        self.assertEqual(facts[0], "Mara waits 10 minutes.")
        self.assertFalse(any("Orton" in fact for fact in facts))
        refused = SimulationCore(self.gm).resolve([DropAction(item_name="Apartment Key")])
        self.assertEqual(refused[0].count("Mara keeps her keys on her."), 1)


class ExerciseParserPromptTests(unittest.TestCase):
    """Spec 08, What the narrator and the player see: the parser sees the exercise list."""

    def prompt(self, *item_ids: str) -> str:
        gm = GameManager()
        for item_id in item_ids:
            gm.player.inventory.append(ItemEntity(item=ITEMS[item_id]))
        return ContextBuilder(gm).build_parser_prompt("do some push-ups")

    def test_the_prompt_lists_every_exercise(self):
        section = self.prompt().split("[EXERCISES]")[1].split("[")[0]
        for name in (
            "Squats",
            "Push-ups",
            "Sit-ups",
            "Burpees",
            "Barbell curls",
            "Dumbbell press",
            "Biceps curls",
        ):
            self.assertIn(name, section)

    def test_the_prompt_says_which_gym_items_are_carried(self):
        self.assertIn("Carrying: nothing to lift", self.prompt())
        self.assertIn("Carrying: a barbell", self.prompt("item_barbell"))
        self.assertIn("a dumbbell", self.prompt("item_dumbbell"))

    def test_the_parser_is_taught_the_verb(self):
        self.assertIn("EXERCISE", llm.PARSER_SYSTEM_PROMPT)


def clear_sky(gm: GameManager, daylight: float = 1.0) -> None:
    gm.climate.sample = lambda minutes: WeatherSample(  # type: ignore[method-assign]
        15, 0.5, 0, 0, 0, 0, False, 0, daylight=daylight
    )


def add_zombie(gm: GameManager, gap: float, state: ZombieState, **fields) -> ZombieEntity:
    number = gm.world.next_zombie_number
    gm.world.next_zombie_number += 1
    zombie = ZombieEntity(
        zombie_id=f"z{number}",
        zone_id=gm.player.current_location_id,
        health=fields.pop("health", 1.7),
        speed_type=2,
        speed_mod=fields.pop("speed_mod", 0.91),
        lunger=fields.pop("lunger", False),
        strength=3,
        memory=800,
        sight=3,
        hearing=3,
        state=state,
        gap=gap,
        **fields,
    )
    gm.world.zombies[zombie.zombie_id] = zombie
    return zombie


def threats_block(prompt: str) -> str:
    return prompt.split("[THREATS]")[1].split("\n[")[0]


class ThreatsContextTests(unittest.TestCase):
    """Spec 09, What the narrator and the player see: the [THREATS] block."""

    def setUp(self):
        self.gm = GameManager()
        self.gm.player.current_location_id = "zone_street"
        self.gm.world.outbreak_started_at = 0
        clear_sky(self.gm)

    def narrator_threats(self) -> str:
        block = threats_block(ContextBuilder(self.gm).build_narrator_prompt("look"))
        return block.split("number.)\n", 1)[1]

    def test_perceived_zombies_are_listed_with_a_distance_word_and_what_they_do(self):
        add_zombie(self.gm, 3, ZombieState.CHASING)
        add_zombie(self.gm, 12, ZombieState.IDLE)
        add_zombie(self.gm, 18, ZombieState.IDLE)
        block = self.narrator_threats()
        self.assertIn("z1, close, coming at you", block)
        self.assertIn("z2, nearby, hasn't noticed you", block)
        self.assertIn("z3, far off, hasn't noticed you", block)

    def test_the_distance_words(self):
        for gap in (1, 5, 6, 15, 16):
            add_zombie(self.gm, gap, ZombieState.IDLE)
        words = [line.split(", ")[1] for line in self.narrator_threats().strip().splitlines()]
        self.assertEqual(words, ["on you", "close", "nearby", "nearby", "far off"])

    def test_a_zombie_behind_the_player_is_right_behind_them(self):
        add_zombie(self.gm, 1, ZombieState.ATTACKING, side=AttackSide.BEHIND)
        self.assertIn("z1, on you, right behind you", self.narrator_threats())

    def test_a_lunger_that_has_chased_is_fast(self):
        lunger = add_zombie(self.gm, 8, ZombieState.CHASING, lunger=True)
        lunger.has_chased = True
        self.assertIn("z1, nearby, coming at you fast", self.narrator_threats())

    def test_never_health_speed_or_senses(self):
        add_zombie(self.gm, 3, ZombieState.CHASING, health=2.345, speed_mod=0.8765)
        block = self.narrator_threats().casefold()
        for forbidden in ("2.3", "0.87", "health", "speed", "sight", "hearing", "shambler", "poor"):
            self.assertNotIn(forbidden, block)
        self.assertNotRegex(block, r"\d\.\d")

    def test_zombies_beyond_what_the_player_perceives_are_not_listed(self):
        add_zombie(self.gm, 30, ZombieState.IDLE)
        other = add_zombie(self.gm, 3, ZombieState.IDLE)
        other.zone_id = "zone_building"
        self.assertEqual(self.narrator_threats().strip(), "None")

    def test_before_the_outbreak_there_is_nothing(self):
        self.gm.world.outbreak_started_at = None
        self.assertEqual(self.narrator_threats().strip(), "None")

    def test_a_zombie_that_is_only_heard_is_never_described(self):
        clear_sky(self.gm, daylight=0.0)
        self.gm.player.traits.append("keenhearing")
        add_zombie(self.gm, 6, ZombieState.IDLE)
        block = self.narrator_threats()
        self.assertIn("something shuffling nearby", block)
        self.assertNotIn("z1", block)

    def test_the_parser_sees_the_ids_and_distances_only(self):
        add_zombie(self.gm, 3, ZombieState.CHASING)
        block = threats_block(ContextBuilder(self.gm).build_parser_prompt("look"))
        self.assertIn("z1 (close)", block)
        self.assertNotIn("coming at you", block)
