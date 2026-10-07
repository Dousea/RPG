"""ContextBuilder: the knowledge-firewall boundary between state and prompts."""

import unittest
from unittest import mock

from adapters import llm
from data.items import ITEMS
from managers import creation
from managers.context import ContextBuilder
from managers.game import GameManager
from managers.simulation import SimulationCore
from modules.action.parser import TALK_APPROACH_LABELS
from modules.action.types import (
    DropAction,
    Duration,
    MoveAction,
    SearchAction,
    WaitAction,
    WearAction,
)
from modules.body import BodyLocation, BodyPart
from modules.character.appearance import Appearance, Gender
from modules.character.build import CharacterBuild
from modules.character.equipment import CharacterArmorSlot, CharacterHoldableSlot
from modules.character.skills import SkillState
from modules.entity.barrier import BarrierEntity, BarrierKind
from modules.entity.corpse import CorpseEntity
from modules.entity.item import ItemEntity
from modules.entity.zombie import AttackSide, ZombieEntity, ZombieState
from modules.item import ClothingItem
from modules.quest import QuestState
from modules.stats import CharacterStat
from modules.weather import WeatherSample
from tests.support import adjust_regard, npc_of, resolve_actions, set_health


class WorldFlagFirewallTests(unittest.TestCase):
    """doc 11's actual complaint: every world flag went out unfiltered,
    whether or not anything in the story ever revealed it to the player."""

    def setUp(self):
        self.gm = GameManager()
        self.builder = ContextBuilder(self.gm)

    def test_an_undiscovered_flag_never_reaches_the_narrator_prompt(self):
        self.gm.narrative.flags["power_grid_stable"] = False
        prompt = self.builder.build_narrator_prompt("look")
        self.assertNotIn("power_grid_stable", prompt)

    def test_a_discovered_flag_reaches_the_narrator_prompt(self):
        self.gm.narrative.flags["power_grid_stable"] = False
        SimulationCore(self.gm).discover_flag("power_grid_stable")
        prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("power_grid_stable=False", prompt)

    def test_discovering_a_flag_that_was_never_set_is_harmless(self):
        self.gm.narrative.discovered_flags.add("never_set")
        prompt = self.builder.build_narrator_prompt("look")
        # Nothing to show -- the flag has no value -- but this must not raise.
        self.assertIn("Flags: None", prompt)

    def test_setting_the_same_flag_twice_does_not_undiscover_it(self):
        self.gm.narrative.flags["power_grid_stable"] = False
        SimulationCore(self.gm).discover_flag("power_grid_stable")
        self.gm.narrative.flags["power_grid_stable"] = True
        prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("power_grid_stable=True", prompt)


class ParserPromptFirewallTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()
        self.builder = ContextBuilder(self.gm)

    def test_parser_prompt_carries_no_relationship_or_flag_data_at_all(self):
        self.gm.narrative.flags["power_grid_stable"] = False
        SimulationCore(self.gm).discover_flag("power_grid_stable")
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
        resolve_actions(self.gm, MoveAction(destination="the window"))
        parser_prompt = self.builder.build_parser_prompt("look")
        narrator_prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("Specific spot: the window", parser_prompt)
        self.assertIn("Specific spot: the window", narrator_prompt)


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
        condition = prompt.split("[CONDITION]")[1].split("[QUESTS]")[0]
        self.assertTrue(condition.strip().endswith("Fine"))

    def test_the_parser_sees_the_same_status_effect_list(self):
        self.gm.player.stats.set(CharacterStat.FATIGUE, 0.85)
        prompt = self.builder.build_parser_prompt("sleep")
        self.assertIn("Very Tired (3/4)", prompt)

    def test_the_well_fed_timer_shows_as_a_status_effect(self):
        self.gm.player.food_eaten_timer = 2000
        prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("Well Fed (2/4)", prompt)


class PartLinesTests(unittest.TestCase):
    """Spec 12, What the narrator and the player see: `[CONDITION]` part lines."""

    def setUp(self):
        self.gm = GameManager()
        self.builder = ContextBuilder(self.gm)

    def condition(self, narrator: bool = True) -> str:
        if narrator:
            prompt = self.builder.build_narrator_prompt("look")
            return prompt.split("[CONDITION]")[1].split("[QUESTS]")[0]
        prompt = self.builder.build_parser_prompt("look")
        return prompt.split("[CONDITION]")[1].split("[WEATHER]")[0]

    def test_a_bleeding_bite_reads_bite_bleeding(self):
        state = self.gm.player.body[BodyPart.FOREARM_L]
        state.bite_time = 60.0
        state.bleeding_time = 10.0
        self.assertIn("left forearm: bite, bleeding", self.condition())

    def test_a_dirty_bandage_reads_bandaged_dirty(self):
        state = self.gm.player.body[BodyPart.FOREARM_L]
        state.bite_time = 60.0
        state.bleeding_time = 10.0
        state.bandage = "item_bandage"
        state.bandage_life = 0.0
        self.assertIn("left forearm: bite, bandaged (dirty)", self.condition())

    def test_a_clean_bandage_reads_bandaged(self):
        state = self.gm.player.body[BodyPart.HAND_R]
        state.scratch_time = 6.0
        state.bandage = "item_bandage"
        state.bandage_life = 3.0
        self.assertIn("right hand: scratch, bandaged\n", self.condition() + "\n")

    def test_an_infected_unbandaged_wound_reads_infected(self):
        state = self.gm.player.body[BodyPart.HAND_R]
        state.scratch_time = 6.0
        state.infected_wound = True
        state.wound_infection = 2.0
        self.assertIn("right hand: scratch, infected", self.condition())

    def test_infection_is_not_shown_under_a_bandage(self):
        state = self.gm.player.body[BodyPart.HAND_R]
        state.scratch_time = 6.0
        state.infected_wound = True
        state.bandage = "item_bandage"
        state.bandage_life = 3.0
        self.assertNotIn("infected", self.condition())

    def test_a_healed_part_drops_off_the_list(self):
        self.gm.player.body[BodyPart.HAND_R].health = 40.0
        self.assertNotIn("right hand", self.condition())

    def test_a_laceration_reads_laceration(self):
        state = self.gm.player.body[BodyPart.TORSO_LOWER]
        state.cut_time = 12.0
        self.assertIn("stomach: laceration", self.condition())

    def test_the_parser_sees_the_part_lines_too(self):
        state = self.gm.player.body[BodyPart.FOREARM_L]
        state.bite_time = 60.0
        self.assertIn("left forearm: bite", self.condition(narrator=False))

    def test_the_lines_are_words_only(self):
        state = self.gm.player.body[BodyPart.FOREARM_L]
        state.bite_time = 60.0
        state.bleeding_time = 10.0
        state.wound_infection = 4.0
        line = next(
            each for each in self.condition().splitlines() if each.startswith("left forearm")
        )
        self.assertFalse(any(ch.isdigit() for ch in line))

    def test_zombie_infection_is_never_named(self):
        state = self.gm.player.body[BodyPart.FOREARM_L]
        state.bite_time = 60.0
        state.zombie_infected = True
        self.gm.player.zombie_infection_since = 0.0
        self.gm.player.stats.set(CharacterStat.ZOMBIE_INFECTION, 80)
        for prompt in (
            self.builder.build_narrator_prompt("look"),
            self.builder.build_parser_prompt("look"),
        ):
            self.assertNotIn("zombie_infection", prompt.casefold())
            self.assertNotIn("zombie_infection", prompt.casefold())

    def test_bleeding_and_pain_status_effects_show_by_name(self):
        self.gm.player.body[BodyPart.FOREARM_L].bleeding_time = 5.0
        self.gm.player.stats.set(CharacterStat.PAIN, 15)
        condition = self.condition()
        self.assertIn("Minor Bleeding (1/4)", condition)
        self.assertIn("Minor Pain (1/4)", condition)

    def test_the_inventory_shows_uses_left(self):
        self.gm.player.inventory.append(ItemEntity(item=ITEMS["item_painkillers"]))
        self.gm.player.inventory[-1].uses = 7
        parser = self.builder.build_parser_prompt("look")
        self.assertIn("Painkillers (7 left)", parser.split("[INVENTORY]")[1].split("[WORN]")[0])
        narrator = self.builder.build_narrator_prompt("look")
        self.assertIn("Painkillers (7 left)", narrator)

    def test_a_single_use_item_shows_no_count(self):
        self.gm.player.inventory.append(ItemEntity(item=ITEMS["item_dirty_bandage"]))
        parser = self.builder.build_parser_prompt("look")
        inventory = parser.split("[INVENTORY]")[1].split("[WORN]")[0]
        self.assertIn("Dirty Bandage", inventory)
        self.assertNotIn("left", inventory)


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
        set_health(self.gm.player, 37)
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
        if "[WEATHER]" in prompt:
            return prompt.split("[WEATHER]")[1].split("\n\n[")[0]
        section = prompt.split("[TIME AND WEATHER]")[1].split("[CURRENT LOCATION]")[0]
        return section[section.index("Sky:") :]

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


class TimeLineTests(unittest.TestCase):
    def test_the_narrators_time_line_names_the_weekday(self):
        gm = GameManager()
        prompt = ContextBuilder(gm).build_narrator_prompt("look")
        self.assertIn("08:00 AM, Sunday 2023-10-01", prompt)
        gm.advance_clock(24 * 60)
        prompt = ContextBuilder(gm).build_narrator_prompt("look")
        self.assertIn("Monday 2023-10-02", prompt)


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
        actions = self.prompt().split("[AVAILABLE ACTIONS]")[1]
        self.assertIn("- EXERCISE <text> -- ", actions)


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


def in_view_block(prompt: str) -> str:
    return prompt.split("[IN VIEW]")[1].split("\n[")[0]


class InViewTests(unittest.TestCase):
    """Spec 10, What the narrator sees: [IN VIEW] repeats who and what the story must show."""

    def setUp(self):
        self.gm = GameManager()
        self.gm.player.current_location_id = "zone_building"
        self.gm.world.outbreak_started_at = 0
        clear_sky(self.gm)

    def prompt(self) -> str:
        return ContextBuilder(self.gm).build_narrator_prompt("look", ["a fact"])

    def test_it_lists_each_perceived_zombie_then_each_person_present(self):
        add_zombie(self.gm, 3, ZombieState.CHASING)
        lines = in_view_block(self.prompt()).strip().splitlines()[1:]
        self.assertEqual(lines, [" - a zombie, close, coming at you", " - Emma", " - Marcus"])

    def test_it_comes_after_the_outcomes(self):
        prompt = self.prompt()
        self.assertLess(prompt.index("[OUTCOMES]"), prompt.index("[IN VIEW]"))

    def test_it_is_left_out_when_no_one_and_nothing_is_in_view(self):
        self.gm.player.current_location_id = "zone_home"
        self.assertNotIn("[IN VIEW]", self.prompt())


def corpses_block(prompt: str) -> str:
    return prompt.split("[CORPSES]")[1].split("\n[")[0]


class CorpsesContextTests(unittest.TestCase):
    """Spec 14, What the narrator and the player see: the [CORPSES] block."""

    def setUp(self):
        self.gm = GameManager()
        self.gm.player.current_location_id = "zone_street"
        self.gm.world.outbreak_started_at = 0
        clear_sky(self.gm)

    def body(self, gap: float = 3.0, *items: str, **fields) -> CorpseEntity:
        number = len(self.gm.world.corpses) + 1
        corpse = CorpseEntity(
            corpse_id=f"c{number}",
            zone_id="zone_street",
            gap=gap,
            female=fields.pop("female", False),
            outfit="generic01",
            died_at=0,
            rot_at_death=fields.pop("rot_at_death", 1),
            contents=[ItemEntity(item=ITEMS[item]) for item in items],
            **fields,
        )
        self.gm.world.corpses[corpse.corpse_id] = corpse
        return corpse

    def parser(self) -> str:
        return corpses_block(ContextBuilder(self.gm).build_parser_prompt("look")).strip()

    def narrator(self) -> str:
        block = corpses_block(ContextBuilder(self.gm).build_narrator_prompt("look"))
        return block.split(")\n", 1)[1].strip()

    def test_the_parser_sees_the_id_the_distance_the_clothes_the_rot_and_whether_searched(self):
        self.body(3.0, "item_jacket_police")
        self.assertEqual(
            self.parser(), "- c1, close, a man in a police jacket, fresh, not searched"
        )

    def test_a_searched_body_lists_what_it_holds(self):
        self.body(3.0, "item_jacket_police", "item_kitchen_knife", searched=True)
        self.assertEqual(
            self.parser(), "- c1, close, fresh, searched: police jacket, kitchen knife"
        )

    def test_a_woman_and_the_rot_words(self):
        self.body(8.0, "item_jacket_police", female=True, rot_at_death=2)
        self.body(8.0, "item_jacket_police", rot_at_death=3)
        lines = [line.strip() for line in self.parser().splitlines()]
        self.assertEqual(
            lines[0], "- c1, nearby, a woman in a police jacket, decaying, not searched"
        )
        self.assertEqual(lines[1], "- c2, nearby, a man in a police jacket, rotten, not searched")

    def test_a_skeleton_is_bare_bones(self):
        self.body(3.0, skeleton=True)
        self.assertEqual(self.parser(), "- c1, close, bare bones")

    def test_the_narrator_sees_no_ids(self):
        self.body(3.0, "item_jacket_police")
        self.assertEqual(self.narrator(), "- close, a man in a police jacket, fresh, not searched")

    def test_a_body_is_never_described_as_fake_dead_or_crawling(self):
        self.body(3.0, "item_jacket_police", fake_dead=True, crawling=True)
        for text in (self.parser(), self.narrator()):
            self.assertNotIn("fake", text)
            self.assertNotIn("crawl", text)
            self.assertNotIn("rise", text)

    def test_a_body_beyond_sight_is_not_listed(self):
        self.body(30.0, "item_jacket_police")
        self.assertEqual(self.parser(), "None")

    def test_the_block_says_none_without_bodies(self):
        self.assertEqual(self.parser(), "None")
        self.assertEqual(self.narrator(), "None")

    def test_a_body_in_another_zone_is_not_listed(self):
        corpse = self.body(3.0, "item_jacket_police")
        corpse.zone_id = "zone_building"
        self.assertEqual(self.parser(), "None")

    def test_narrator_facts_name_a_corpse_id_as_the_body(self):
        self.body(3.0)
        prompt = ContextBuilder(self.gm).build_narrator_prompt(
            "look", ["Orton goes through c1: nothing."]
        )
        self.assertIn("Orton goes through the body: nothing.", prompt)


class CorpseSceneKeyTests(CorpsesContextTests):
    """Spec 14, What the narrator and the player see: SEARCH and TAKE come with the bodies."""

    def setUp(self):
        super().setUp()
        self.gm.player.inventory.clear()
        self.gm.player.worn.clear()
        self.gm.current_location.entities.clear()
        self.gm.world.barriers.clear()

    def test_a_perceived_body_gives_corpses_and_search(self):
        self.body(3.0, "item_jacket_police")
        builder = ContextBuilder(self.gm)
        self.assertEqual(builder.scene_keys(), frozenset({"corpses"}))
        listed = listed_in_prompt(builder.build_parser_prompt("look"))
        self.assertEqual(listed, ALWAYS | {"CARRY", "SEARCH"})

    def test_a_searched_body_with_contents_gives_loot_and_take(self):
        self.body(3.0, "item_jacket_police", searched=True)
        builder = ContextBuilder(self.gm)
        self.assertEqual(builder.scene_keys(), frozenset({"corpses", "loot"}))
        listed = listed_in_prompt(builder.build_parser_prompt("look"))
        self.assertEqual(listed, ALWAYS | {"CARRY", "SEARCH", "TAKE"})


class CrawlerThreatsTests(unittest.TestCase):
    """Spec 14, What the narrator and the player see: `[THREATS]` says crawling."""

    def setUp(self):
        self.gm = GameManager()
        self.gm.player.current_location_id = "zone_street"
        self.gm.world.outbreak_started_at = 0
        clear_sky(self.gm)

    def test_a_crawler_reads_crawling_toward_you_or_on_you_crawling(self):
        add_zombie(self.gm, 3, ZombieState.CHASING, crawling=True)
        add_zombie(self.gm, 1, ZombieState.ATTACKING, crawling=True)
        block = threats_block(ContextBuilder(self.gm).build_narrator_prompt("look"))
        self.assertIn("a zombie, close, crawling toward you", block)
        self.assertIn("a zombie, on you, crawling", block)

    def test_a_lunger_that_is_a_crawler_is_never_fast(self):
        crawler = add_zombie(self.gm, 3, ZombieState.CHASING, crawling=True, lunger=True)
        crawler.has_chased = True
        block = threats_block(ContextBuilder(self.gm).build_narrator_prompt("look"))
        self.assertNotIn("fast", block)


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
        self.assertIn("a zombie, close, coming at you", block)
        self.assertIn("a zombie, nearby, hasn't noticed you", block)
        self.assertIn("a zombie, far off, hasn't noticed you", block)

    def test_the_distance_words(self):
        for gap in (1, 5, 6, 15, 16):
            add_zombie(self.gm, gap, ZombieState.IDLE)
        words = [line.split(", ")[1] for line in self.narrator_threats().strip().splitlines()]
        self.assertEqual(words, ["on you", "close", "nearby", "nearby", "far off"])

    def test_a_zombie_behind_the_player_is_right_behind_them(self):
        add_zombie(self.gm, 1, ZombieState.ATTACKING, side=AttackSide.BEHIND)
        self.assertIn("a zombie, on you, right behind you", self.narrator_threats())

    def test_a_lunger_that_has_chased_is_fast(self):
        lunger = add_zombie(self.gm, 8, ZombieState.CHASING, lunger=True)
        lunger.has_chased = True
        self.assertIn("a zombie, nearby, coming at you fast", self.narrator_threats())

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

    def test_the_narrator_never_sees_a_zombie_id(self):
        add_zombie(self.gm, 3, ZombieState.CHASING)
        facts = [
            "Orton hits z1 with the kitchen knife and it staggers back.",
            "The knife goes in under z12's jaw.",
            "z1 goes still.",
        ]
        prompt = ContextBuilder(self.gm).build_narrator_prompt("I attack z1", facts)
        outcomes = prompt.split("[OUTCOMES]")[1].split("\n[")[0]
        self.assertIn(
            "Orton hits the zombie with the kitchen knife and it staggers back.", outcomes
        )
        self.assertIn("The knife goes in under the zombie's jaw.", outcomes)
        self.assertIn(" - The zombie goes still.", outcomes)
        before_scene = prompt.split("[SCENE]")[0]
        self.assertNotRegex(before_scene, r"\bz\d+\b")

    def test_the_parser_sees_the_ids_and_distances_only(self):
        add_zombie(self.gm, 3, ZombieState.CHASING)
        block = threats_block(ContextBuilder(self.gm).build_parser_prompt("look"))
        self.assertIn("z1 (close)", block)
        self.assertNotIn("coming at you", block)


class MeleeContextTests(unittest.TestCase):
    """Spec 11, What the narrator and the player see."""

    def setUp(self):
        self.gm = GameManager()
        self.gm.player.current_location_id = "zone_street"
        self.gm.world.outbreak_started_at = 0
        clear_sky(self.gm)

    def hold(self, item_id: str) -> ItemEntity:
        entity = ItemEntity(item=ITEMS[item_id])
        for slot in entity.item.slots:  # type: ignore[attr-defined]
            self.gm.player.equipment[slot] = entity  # type: ignore[index]
        return entity

    def narrator(self) -> str:
        return ContextBuilder(self.gm).build_narrator_prompt("look")

    def test_a_held_knife_is_in_hands_not_worn(self):
        self.gm.player.worn.clear()
        knife = self.hold("item_kitchen_knife")
        self.gm.player.inventory.append(knife)
        builder = ContextBuilder(self.gm)
        parser = builder.build_parser_prompt("look")
        worn = parser.split("[WORN]")[1].split("[CONDITION]")[0]
        self.assertNotIn("Kitchen Knife", worn)
        self.assertIn("Kitchen Knife (in hands)", parser.split("[INVENTORY]")[1])
        self.assertIn("Kitchen Knife", self.narrator().split("Equipment:")[1].split("Wearing:")[0])

    def test_a_down_zombie_reads_down(self):
        zombie = add_zombie(self.gm, 1, ZombieState.ATTACKING)
        zombie.down_until = self.gm.narrative.minutes + 2
        block = threats_block(self.narrator())
        self.assertIn("a zombie, on you, down", block)

    def test_the_condition_block_has_a_hands_line_with_a_word_and_no_number(self):
        entity = self.hold("item_crowbar")
        entity.condition = 8
        condition = self.narrator().split("[CONDITION]")[1].split("\n[")[0]
        self.assertIn("Holding: crowbar (worn)", condition)
        self.assertNotRegex(condition.split("Holding:")[1], r"\d")

    def test_no_hands_line_when_nothing_is_held(self):
        condition = self.narrator().split("[CONDITION]")[1].split("\n[")[0]
        self.assertNotIn("Holding", condition)

    def test_the_parser_inventory_marks_held_and_broken_items(self):
        self.hold("item_crowbar")
        broken = ItemEntity(item=ITEMS["item_kitchen_knife"])
        broken.condition = 0
        self.gm.player.inventory.append(broken)
        prompt = ContextBuilder(self.gm).build_parser_prompt("look")
        inventory = prompt.split("[INVENTORY]")[1].split("\n[")[0]
        self.assertIn("Crowbar (in hands)", inventory)
        self.assertIn("Kitchen Knife (broken)", inventory)

    def test_the_condition_words_by_share_of_full_condition(self):
        from data.melee import condition_word

        self.assertEqual(condition_word(15, 15), "good")
        self.assertEqual(condition_word(12, 15), "good")
        self.assertEqual(condition_word(11, 15), "worn")
        self.assertEqual(condition_word(6, 15), "worn")
        self.assertEqual(condition_word(5, 15), "badly worn")
        self.assertEqual(condition_word(1, 15), "badly worn")
        self.assertEqual(condition_word(0, 15), "broken")


def _positions(prompt: str, headers: list[str]) -> list[int]:
    positions = []
    text = "\n" + prompt
    for header in headers:
        line = f"\n{header}\n"
        assert text.count(line) == 1, header
        positions.append(text.index(line))
    return positions


class ParserBlockOrderTests(unittest.TestCase):
    """Spec 10, What the parser sees."""

    def setUp(self):
        self.gm = GameManager()
        self.gm.player.current_location_id = "zone_building"
        self.builder = ContextBuilder(self.gm)

    def test_the_blocks_appear_in_the_stated_order(self):
        prompt = self.builder.build_parser_prompt("look")
        headers = [
            "[CHARACTER]",
            "[LOCATION]",
            "[EXITS]",
            "[ZONES]",
            "[ITEMS HERE]",
            "[NPCS HERE]",
            "[THREATS]",
            "[CORPSES]",
            "[DOORS AND WINDOWS]",
            "[INVENTORY]",
            "[WORN]",
            "[CONDITION]",
            "[WEATHER]",
            "[EXERCISES]",
            "[AVAILABLE ACTIONS]",
            "[PLAYER INPUT]",
        ]
        positions = _positions(prompt, headers)
        self.assertEqual(positions, sorted(positions))

    def test_character_is_the_name_and_pronouns_only(self):
        block = (
            self.builder.build_parser_prompt("look").split("[CHARACTER]")[1].split("[LOCATION]")[0]
        )
        self.assertIn("Orton (he/him)", block)
        for word in ("Occupation", "Backstory", "Traits", "Skills"):
            self.assertNotIn(word, block)

    def test_npcs_here_shows_following_and_topics_but_no_bands(self):
        npc_of(self.gm, "Emma").following = True
        block = (
            self.builder.build_parser_prompt("look").split("[NPCS HERE]")[1].split("[THREATS]")[0]
        )
        self.assertIn("Emma (following you)", block)
        self.assertIn("Marcus", block)
        self.assertNotIn("Marcus (following you)", block)
        for word in ("Disposition", "trust", "friendly", "neutral"):
            self.assertNotIn(word, block)

    def test_a_topic_is_listed_under_its_npc_once_it_is_available(self):
        self.gm.player.current_location_id = "zone_neighborhood"
        block = (
            self.builder.build_parser_prompt("look").split("[NPCS HERE]")[1].split("[THREATS]")[0]
        )
        self.assertNotIn("outbreak_news", block)
        self.gm.world.outbreak_started_at = 0
        block = (
            self.builder.build_parser_prompt("look").split("[NPCS HERE]")[1].split("[THREATS]")[0]
        )
        self.assertIn("Topic outbreak_news: what the news says about the outbreak", block)

    def test_an_item_an_npc_holds_is_listed_so_it_can_be_asked_for(self):
        npc_of(self.gm, "Emma").inventory.append(ItemEntity(item=ITEMS["item_water_bottle"]))
        block = (
            self.builder.build_parser_prompt("look").split("[NPCS HERE]")[1].split("[THREATS]")[0]
        )
        self.assertIn("Holds: Water Bottle", block)

    def test_the_condition_block_names_sneaking(self):
        self.gm.player.sneaking = True
        block = (
            self.builder.build_parser_prompt("look").split("[CONDITION]")[1].split("[WEATHER]")[0]
        )
        self.assertIn("sneaking", block)

    def test_worn_clothing_has_its_own_block(self):
        block = self.builder.build_parser_prompt("look").split("[WORN]")[1].split("[CONDITION]")[0]
        self.assertIn("Jeans", block)
        self.assertNotIn(
            "Jeans",
            self.builder.build_parser_prompt("look").split("[INVENTORY]")[1].split("[WORN]")[0],
        )


class NarratorBlockOrderTests(unittest.TestCase):
    """Spec 10, What the narrator sees."""

    def setUp(self):
        self.gm = GameManager()
        self.gm.player.current_location_id = "zone_building"
        self.builder = ContextBuilder(self.gm)

    def test_the_blocks_appear_in_the_stated_order_memory_first(self):
        prompt = self.builder.build_narrator_prompt("look", ["a fact"], ["a memory"])
        headers = [
            "[CHARACTER]",
            "[DEEP MEMORY]",
            "[SUMMARY OF PAST EVENTS]",
            "[RECENT EVENTS]",
            "[TIME AND WEATHER]",
            "[CURRENT LOCATION]",
            "[ITEMS IN CURRENT LOCATION]",
            "[NEARBY LOCATIONS]",
            "[CONDITION]",
            "[QUESTS]",
            "[NPCS PRESENT]",
            "[THREATS]",
            "[OUTCOMES]",
            "[IN VIEW]",
            "[CONTINUITY]",
            "[SCENE]",
        ]
        positions = _positions(prompt, headers)
        self.assertEqual(positions, sorted(positions))

    def test_time_and_weather_says_before_the_outbreak(self):
        block = self.builder.build_narrator_prompt("look").split("[TIME AND WEATHER]")[1]
        self.assertIn("before the outbreak", block.split("[CURRENT LOCATION]")[0])

    def test_time_and_weather_counts_the_days_of_the_outbreak(self):
        self.gm.advance_clock(2760)
        self.gm.world.outbreak_started_at = 2760
        block = self.builder.build_narrator_prompt("look").split("[TIME AND WEATHER]")[1]
        self.assertIn("outbreak day 1", block.split("[CURRENT LOCATION]")[0])
        self.gm.advance_clock(1440)
        block = self.builder.build_narrator_prompt("look").split("[TIME AND WEATHER]")[1]
        self.assertIn("outbreak day 2", block.split("[CURRENT LOCATION]")[0])

    def test_the_old_apocalypse_line_is_gone(self):
        self.assertNotIn("Apocalypse", self.builder.build_narrator_prompt("look"))

    def test_character_has_none_of_the_removed_lines(self):
        block = (
            self.builder.build_narrator_prompt("look")
            .split("[CHARACTER]")[1]
            .split("[DEEP MEMORY]")[0]
        )
        for line in (
            "Level:",
            "Health:",
            "Hunger:",
            "Thirst:",
            "Morale:",
            "Sleep:",
            "Infection Risk:",
            "Status:",
            "Conditions:",
        ):
            self.assertNotIn(line, block)

    def test_character_keeps_name_pronouns_occupation_goals_and_outfit(self):
        block = (
            self.builder.build_narrator_prompt("look")
            .split("[CHARACTER]")[1]
            .split("[DEEP MEMORY]")[0]
        )
        for line in ("Name: Orton", "Pronouns: he/him", "Occupation:", "Goals:", "Wearing:"):
            self.assertIn(line, block)

    def test_npcs_present_says_who_is_following(self):
        npc_of(self.gm, "Emma").following = True
        block = (
            self.builder.build_narrator_prompt("look")
            .split("[NPCS PRESENT]")[1]
            .split("[THREATS]")[0]
        )
        self.assertIn("Following Orton", block)
        self.assertEqual(block.count("Following Orton"), 1)

    def test_condition_names_sleep_and_sneaking_and_item_conditions(self):
        from modules.character.state import CharacterCondition

        self.gm.player.sneaking = True
        self.gm.player.asleep = True
        self.gm.player.conditions.append(CharacterCondition.POISONED)
        block = (
            self.builder.build_narrator_prompt("look").split("[CONDITION]")[1].split("[QUESTS]")[0]
        )
        for word in ("asleep", "sneaking", "poisoned"):
            self.assertIn(word, block)

    def test_no_block_carries_a_stat_value_a_relationship_score_or_hp(self):
        gm = self.gm
        gm.player.stats.set(CharacterStat.HUNGER, 0.7371)
        gm.player.stats.set(CharacterStat.STRESS, 0.4242)
        set_health(gm.player, 61)
        adjust_regard(gm, "npc_emma", affection=37, trust=42)
        prompt = self.builder.build_narrator_prompt("look")
        state = prompt.split("[TIME AND WEATHER]")[1].split("[OUTCOMES]")[0]
        for leak in ("0.7371", "0.74", "0.4242", "61", "37", "42", "HP", "Health", "hit points"):
            self.assertNotIn(leak, state)
        for header in ("[CHARACTER]", "[NPCS PRESENT]", "[CONDITION]"):
            self.assertNotIn("0.7371", prompt.split(header)[1].split("\n\n[")[0])

    def test_recent_events_say_they_run_oldest_first(self):
        self.gm.memory.recent_events.append("Orton waved. Emma responds warmly.")
        block = (
            self.builder.build_narrator_prompt("look")
            .split("[RECENT EVENTS]")[1]
            .split("[TIME AND WEATHER]")[0]
        )
        self.assertIn("Orton waved. Emma responds warmly.", block)
        self.assertIn("oldest first", block)


ALWAYS = {
    "MOVE_TO",
    "STANCE",
    "WAIT",
    "SLEEP",
    "EXERCISE",
    "SHOUT",
    "ADD_GOAL",
    "ADD_RELATIONSHIP_NOTE",
}


def listed_in_prompt(prompt: str) -> set[str]:
    block = prompt.split("[AVAILABLE ACTIONS]")[1].split("[PLAYER INPUT]")[0]
    return set(llm.listed_verbs(block))


class SceneKeyTests(unittest.TestCase):
    """Spec 10, Scene filtering."""

    def setUp(self):
        self.gm = GameManager()
        self.gm.player.current_location_id = "zone_street"
        self.gm.player.inventory.clear()
        self.gm.player.worn.clear()
        self.gm.current_location.entities.clear()
        self.gm.world.barriers.clear()
        self.builder = ContextBuilder(self.gm)

    def test_a_bare_scene_has_no_keys_and_lists_the_eight_verbs(self):
        self.assertEqual(self.builder.scene_keys(), frozenset())
        self.assertEqual(listed_in_prompt(self.builder.build_parser_prompt("look")), ALWAYS)

    def test_an_npc_here_gives_npcs_here(self):
        self.gm.player.current_location_id = "zone_building"
        self.gm.current_location.entities.clear()
        self.assertEqual(self.builder.scene_keys(), frozenset({"npcs_here", "rooms"}))
        listed = listed_in_prompt(self.builder.build_parser_prompt("look"))
        self.assertEqual(listed, ALWAYS | {"TALK", "ASK", "GIVE", "ATTACK", "SEARCH"})

    def test_a_perceived_zombie_gives_threats(self):
        self.gm.world.outbreak_started_at = 0
        add_zombie(self.gm, 3, ZombieState.CHASING)
        self.assertEqual(self.builder.scene_keys(), frozenset({"threats"}))
        listed = listed_in_prompt(self.builder.build_parser_prompt("look"))
        self.assertEqual(listed, ALWAYS | {"ATTACK", "SHOVE"})

    def test_a_ground_item_gives_items_here_and_carried_so_take_then_use_can_be_planned(self):
        item = ITEMS["item_apartment_key"]
        self.gm.current_location.entities.append(ItemEntity(item=item))
        self.assertEqual(self.builder.scene_keys(), frozenset({"items_here", "carried"}))
        listed = listed_in_prompt(self.builder.build_parser_prompt("look"))
        self.assertEqual(listed, ALWAYS | {"TAKE", "DROP", "USE_ITEM", "EQUIP"})

    def test_a_ground_item_is_a_carried_choice_beside_the_inventory(self):
        self.gm.player.inventory.append(ItemEntity(item=ITEMS["item_apartment_key"]))
        self.gm.current_location.entities.append(ItemEntity(item=ITEMS["item_water_bottle"]))
        self.assertEqual(self.builder.scene_choices().carried, ("Apartment Key", "Water Bottle"))

    def test_a_carried_item_gives_carried(self):
        self.gm.player.inventory.append(ItemEntity(item=ITEMS["item_apartment_key"]))
        self.assertEqual(self.builder.scene_keys(), frozenset({"carried"}))
        listed = listed_in_prompt(self.builder.build_parser_prompt("look"))
        self.assertEqual(listed, ALWAYS | {"DROP", "USE_ITEM", "EQUIP"})

    def test_a_goal_gives_goals(self):
        self.gm.narrative.goals["short_term"].append("Find water")
        self.assertEqual(self.builder.scene_keys(), frozenset({"goals"}))
        listed = listed_in_prompt(self.builder.build_parser_prompt("look"))
        self.assertEqual(listed, ALWAYS | {"REMOVE_GOAL"})

    def test_a_carried_garment_gives_wearable_and_carried(self):
        clothing = next(i for i in ITEMS.values() if isinstance(i, ClothingItem))
        self.gm.player.inventory.append(ItemEntity(item=clothing))
        self.assertEqual(self.builder.scene_keys(), frozenset({"carried", "wearable"}))
        listed = listed_in_prompt(self.builder.build_parser_prompt("look"))
        self.assertEqual(listed, ALWAYS | {"DROP", "USE_ITEM", "WEAR", "EQUIP"})

    def test_a_garment_on_the_ground_lists_wear_so_take_then_wear_can_be_planned(self):
        clothing = next(i for i in ITEMS.values() if isinstance(i, ClothingItem))
        self.gm.current_location.entities.append(ItemEntity(item=clothing))
        self.assertEqual(
            self.builder.scene_keys(), frozenset({"items_here", "carried", "wearable"})
        )
        listed = listed_in_prompt(self.builder.build_parser_prompt("look"))
        self.assertEqual(listed, ALWAYS | {"TAKE", "DROP", "USE_ITEM", "WEAR", "EQUIP"})

    def test_first_aid_lines_name_only_the_body_part_before_the_with_clause(self):
        self.gm.player.body[BodyPart.HAND_L].scratch_time = 4.0
        prompt = self.builder.build_parser_prompt("look")
        block = prompt.split("[AVAILABLE ACTIONS]")[1]
        self.assertIn("- BANDAGE <body_part> -- ", block)
        self.assertIn("- DISINFECT <body_part> -- ", block)
        self.assertNotIn("<body_part> <item>", block)

    def test_an_injured_part_gives_hurt_and_lists_the_first_aid_verbs(self):
        self.gm.player.body[BodyPart.HAND_L].scratch_time = 4.0
        self.assertEqual(self.builder.scene_keys(), frozenset({"hurt"}))
        listed = listed_in_prompt(self.builder.build_parser_prompt("look"))
        self.assertEqual(listed, ALWAYS | {"BANDAGE", "REMOVE_BANDAGE", "DISINFECT"})

    def test_a_bandaged_part_also_gives_hurt(self):
        self.gm.player.body[BodyPart.HAND_L].bandage = "item_bandage"
        self.assertEqual(self.builder.scene_keys(), frozenset({"hurt"}))

    def test_a_worn_item_gives_worn(self):
        self.gm.player.inventory.append(ItemEntity(item=ITEMS["item_jeans"]))
        resolve_actions(self.gm, WearAction(item_name="Jeans"))
        self.assertEqual(self.builder.scene_keys(), frozenset({"worn"}))
        listed = listed_in_prompt(self.builder.build_parser_prompt("look"))
        self.assertEqual(listed, ALWAYS | {"TAKE_OFF"})


class ParserSystemPromptTests(unittest.TestCase):
    """Spec 10, Scene filtering: the system prompt is fixed."""

    def test_the_system_prompt_lists_no_verbs(self):
        self.assertEqual(llm.listed_verbs(llm.PARSER_SYSTEM_PROMPT), [])

    def test_the_system_prompt_is_the_same_whatever_the_scene(self):
        before = llm.PARSER_SYSTEM_PROMPT
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        ContextBuilder(gm).build_parser_prompt("look")
        gm.player.current_location_id = "zone_street"
        ContextBuilder(gm).build_parser_prompt("look")
        self.assertEqual(llm.PARSER_SYSTEM_PROMPT, before)

    def test_a_listed_verb_prints_its_closed_labels_in_full(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        prompt = ContextBuilder(gm).build_parser_prompt("look")
        actions = prompt.split("[AVAILABLE ACTIONS]")[1]
        for label in (*TALK_APPROACH_LABELS, "follow", "stay"):
            self.assertIn(label, actions)

    def test_ask_lists_only_the_requests_the_scene_offers(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        ask = ask_line(ContextBuilder(gm).build_parser_prompt("look"))
        self.assertIn("follow", ask)
        self.assertNotIn("give", ask)
        self.assertNotIn("about", ask)
        self.assertIn("any other question is TALK chat", ask)

    def test_ask_offers_give_when_an_npc_here_carries_something(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        npc = gm.npcs_in_location("zone_building")[0]
        npc.inventory.append(ItemEntity(item=ITEMS["item_water_bottle"]))
        ask = ask_line(ContextBuilder(gm).build_parser_prompt("look"))
        self.assertIn("give <item>", ask)
        self.assertNotIn("about", ask)

    def test_an_unlisted_verbs_labels_are_absent(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_street"
        actions = ContextBuilder(gm).build_parser_prompt("look").split("[AVAILABLE ACTIONS]")[1]
        self.assertNotIn("compliment", actions)
        self.assertNotIn("TALK", actions)

    def test_the_block_prints_argument_kinds_and_gloss(self):
        gm = GameManager()
        actions = ContextBuilder(gm).build_parser_prompt("look").split("[AVAILABLE ACTIONS]")[1]
        self.assertIn("- MOVE_TO <zone> <room> -- ", actions)


def ask_line(prompt: str) -> str:
    actions = prompt.split("[AVAILABLE ACTIONS]")[1]
    return next(line for line in actions.splitlines() if line.startswith("- ASK"))


class NarratorBudgetTests(unittest.TestCase):
    """Spec 10, Token budget: what the narrator prompt drops to fit."""

    DEEP = ["deepmark-1 " + "a" * 150, "deepmark-2 " + "b" * 150]
    SCENE = "scenemark " + "c" * 150 + "."

    def setUp(self):
        self.gm = GameManager()
        self.gm.player.current_location_id = "zone_building"
        memory = self.gm.memory
        memory.summaries = ["summark-1 " + "d" * 150, "summark-2 " + "e" * 150]
        memory.recent_events = ["evmark-3 newest", "evmark-2 " + "f" * 150, "evmark-1 " + "g" * 150]
        memory.last_story = self.SCENE

    def prompt(self, max_chars: int | None = None) -> str:
        return ContextBuilder(self.gm).build_narrator_prompt(
            "look", ["The wind rises."], self.DEEP, max_chars=max_chars
        )

    def test_no_limit_leaves_the_prompt_unchanged(self):
        full = self.prompt()
        for marker in ("deepmark-1", "deepmark-2", "summark-1", "scenemark", "evmark-1"):
            self.assertIn(marker, full)
        self.assertEqual(self.prompt(len(full)), full)

    def test_memory_goes_in_the_documented_order_and_the_newest_event_stays(self):
        gone: list[str] = []
        markers = (
            "deepmark-2",
            "deepmark-1",
            "summark-1",
            "summark-2",
            "scenemark",
            "evmark-1",
            "evmark-2",
        )
        prompt = self.prompt()
        with self.assertLogs("managers.context", level="WARNING"):
            while True:
                prompt = self.prompt(len(prompt) - 1)
                vanished = [m for m in markers if m not in prompt and m not in gone]
                if not vanished:
                    break
                self.assertEqual(len(vanished), 1)
                gone.extend(vanished)
        self.assertEqual(gone, list(markers))
        self.assertIn("evmark-3 newest", prompt)

    def test_a_dropped_section_keeps_its_header_and_placeholder(self):
        with self.assertLogs("managers.context", level="WARNING"):
            prompt = self.prompt(0)
        self.assertIn("[DEEP MEMORY]", prompt)
        self.assertIn("(No relevant memories surfaced)", prompt)
        self.assertIn("[SUMMARY OF PAST EVENTS]", prompt)
        self.assertIn("(No summary available yet)", prompt)
        self.assertNotIn("[LAST SCENE]", prompt)

    def test_current_state_and_outcomes_are_never_dropped(self):
        with self.assertLogs("managers.context", level="WARNING"):
            prompt = self.prompt(0)
        for block in ("[CHARACTER]", "[CURRENT LOCATION]", "[THREATS]", "[CONDITION]"):
            self.assertIn(block, prompt)
        self.assertIn("The wind rises.", prompt)
        self.assertTrue(prompt.endswith("[SCENE]\nlook"))

    def test_the_drops_are_logged_once_per_prompt_with_what_went(self):
        full = self.prompt()
        with self.assertLogs("managers.context", level="WARNING") as logged:
            self.prompt(len(full) - 1)
        self.assertEqual(len(logged.records), 1)
        self.assertIn("deep memory", logged.records[0].getMessage())

    def test_a_prompt_that_cannot_fit_is_returned_with_a_warning(self):
        with self.assertLogs("managers.context", level="WARNING") as logged:
            prompt = self.prompt(0)
        self.assertGreater(len(prompt), 0)
        self.assertTrue(any("still" in r.getMessage() for r in logged.records))

    def test_a_prompt_that_fits_logs_nothing(self):
        with mock.patch("managers.context.logger") as log:
            self.prompt(len(self.prompt()))
        log.warning.assert_not_called()


class BarrierBlockTests(unittest.TestCase):
    """Spec 13, What the narrator and the player see."""

    def setUp(self):
        self.gm = GameManager()
        self.builder = ContextBuilder(self.gm)

    def block(self, prompt: str) -> str:
        return prompt.split("[DOORS AND WINDOWS]")[1].split("\n[")[0].strip()

    def test_the_parser_block_names_each_barrier_of_the_zone_in_words(self):
        block = self.block(self.builder.build_parser_prompt("look"))
        self.assertEqual(block, "- apartment door (to Your Building): closed, locked")

    def test_planks_on_each_side_and_pounding_are_counted_in_words(self):
        door = self.gm.world.barriers["door_apartment"]
        door.barricades["zone_home"] = [900, 800, 700]
        door.barricades["zone_building"] = [400]
        self.gm.world.outbreak_started_at = 0
        self.gm.world.zombies["z1"] = ZombieEntity(
            zombie_id="z1",
            zone_id="zone_building",
            health=2.0,
            speed_type=3,
            speed_mod=0.6,
            lunger=False,
            strength=3,
            memory=800,
            sight=2,
            hearing=2,
            state=ZombieState.THUMPING,
            thump_barrier="door_apartment",
            thump_rate=1.5,
        )
        block = self.block(self.builder.build_parser_prompt("look"))
        self.assertEqual(
            block,
            "- apartment door (to Your Building): closed, locked; 3 planks on this side; "
            "1 plank on the far side; something pounding on the other side",
        )

    def test_the_narrator_sees_the_block_too_and_never_a_health(self):
        door = self.gm.world.barriers["door_apartment"]
        door.health = 123
        door.barricades["zone_home"] = [777]
        prompt = self.builder.build_narrator_prompt("look")
        self.assertIn("[DOORS AND WINDOWS]", prompt)
        block = self.block(prompt)
        self.assertNotIn("123", block)
        self.assertNotIn("777", block)
        self.assertNotIn("500", block)

    def test_a_broken_door_and_an_open_one_read_as_such(self):
        door = self.gm.world.barriers["door_apartment"]
        door.open = True
        self.assertIn("open", self.block(self.builder.build_parser_prompt("look")))
        door.open = False
        door.broken = True
        self.assertIn("broken", self.block(self.builder.build_parser_prompt("look")))

    def test_threats_list_a_seen_thumper_by_id_and_an_only_heard_one_in_words(self):
        self.gm.world.outbreak_started_at = 0
        window = BarrierEntity(
            barrier_id="window_test",
            kind=BarrierKind.WINDOW,
            zones=("zone_home", "zone_building"),
            inside_zone="zone_home",
            name="kitchen window",
            health=50,
            max_health=50,
        )
        self.gm.world.barriers["window_test"] = window
        for number, barrier_id in ((1, "window_test"), (2, "door_apartment")):
            self.gm.world.zombies[f"z{number}"] = ZombieEntity(
                zombie_id=f"z{number}",
                zone_id="zone_building",
                health=2.0,
                speed_type=3,
                speed_mod=0.6,
                lunger=False,
                strength=3,
                memory=800,
                sight=2,
                hearing=2,
                state=ZombieState.THUMPING,
                thump_barrier=barrier_id,
                thump_rate=1.5,
            )
        parser = self.builder.build_parser_prompt("look")
        threats = parser.split("[THREATS]")[1].split("[CORPSES]")[0].strip()
        self.assertEqual(threats, "- z1 (behind the kitchen window)")
        narrator = self.builder.build_narrator_prompt("look")
        section = narrator.split("[THREATS]")[1].split("[OUTCOMES]")[0]
        self.assertIn("a zombie, behind the kitchen window, pounding", section)
        self.assertIn("something at the apartment door", section)

    def test_a_deaf_player_perceives_a_thumper_only_through_glass(self):
        self.gm.world.outbreak_started_at = 0
        self.gm.player.traits.append("deaf")
        self.gm.world.zombies["z1"] = ZombieEntity(
            zombie_id="z1",
            zone_id="zone_building",
            health=2.0,
            speed_type=3,
            speed_mod=0.6,
            lunger=False,
            strength=3,
            memory=800,
            sight=2,
            hearing=2,
            state=ZombieState.THUMPING,
            thump_barrier="door_apartment",
            thump_rate=1.5,
        )
        self.assertEqual(self.builder._threats_section(), "None")

    def test_the_door_verbs_are_listed_where_there_is_a_door(self):
        listed = listed_in_prompt(self.builder.build_parser_prompt("look"))
        self.assertTrue({"OPEN", "CLOSE", "BARRICADE", "UNBARRICADE", "ATTACK"} <= listed)


def section(prompt: str, name: str) -> str:
    """The text of one `[NAME]` block, up to the next block."""
    return prompt.split(f"[{name}]\n", 1)[1].split("\n\n[", 1)[0]


class CarryContextTests(unittest.TestCase):
    """Spec 25, What the narrator and the player see: bags, the body and Heavy Load."""

    def setUp(self):
        self.gm = GameManager()
        self.gm.player.worn.clear()
        self.gm.player.inventory.clear()
        self.gm.current_location.entities.clear()

    def entity(self, item_id: str, *inside: str) -> ItemEntity:
        made = ItemEntity(item=ITEMS[item_id])
        made.contents = [ItemEntity(item=ITEMS[i]) for i in inside]
        return made

    def parser(self) -> str:
        return ContextBuilder(self.gm).build_parser_prompt("look")

    def test_a_bag_on_the_back_lists_its_contents(self):
        bag = self.entity("item_schoolbag", "item_canned_beans", "item_bandage")
        self.gm.player.equipment[CharacterArmorSlot.SHOULDERS] = bag
        self.assertEqual(
            section(self.parser(), "INVENTORY"),
            " - Schoolbag (on your back): Canned Beans, Bandage",
        )

    def test_a_bag_in_a_hand_and_a_bag_in_the_pack(self):
        self.gm.player.equipment[CharacterHoldableSlot.LEFT_HAND] = self.entity(
            "item_toolbox", "item_hammer"
        )
        self.gm.player.inventory.append(self.entity("item_duffel_bag"))
        self.gm.player.inventory.append(self.entity("item_canned_beans"))
        lines = section(self.parser(), "INVENTORY").splitlines()
        self.assertEqual(
            lines,
            [
                " - Toolbox (in your hand): Hammer",
                " - Duffel Bag: empty",
                " - Canned Beans",
            ],
        )

    def test_a_worn_bag_and_a_bag_inside_a_bag(self):
        self.gm.player.worn[BodyLocation.SATCHEL] = self.entity("item_satchel", "item_hammer")
        outer = self.entity("item_duffel_bag")
        outer.contents.append(self.entity("item_toolbox", "item_plank"))
        self.gm.player.inventory.append(outer)
        lines = section(self.parser(), "INVENTORY").splitlines()
        self.assertIn(" - Satchel (worn): Hammer", lines)
        self.assertIn(" - Duffel Bag: Toolbox (Plank)", lines)

    def test_a_weapon_in_hand_still_reads_in_hands(self):
        crowbar = self.entity("item_crowbar")
        self.gm.player.equipment[CharacterHoldableSlot.RIGHT_HAND] = crowbar
        self.gm.player.equipment[CharacterHoldableSlot.LEFT_HAND] = crowbar
        self.assertEqual(section(self.parser(), "INVENTORY"), " - Crowbar (in hands)")

    def test_the_prompts_never_give_a_weight(self):
        self.gm.player.inventory.append(self.entity("item_barbell"))
        builder = ContextBuilder(self.gm)
        for prompt in (builder.build_parser_prompt("look"), builder.build_narrator_prompt("look")):
            self.assertNotIn("kg", prompt)

    def test_heavy_load_is_in_the_condition_block_by_name_and_level(self):
        self.gm.player.skills["strength"] = SkillState(level=0)
        self.gm.player.inventory.extend(self.entity(i) for i in ("item_barbell", "item_plank"))
        for prompt in (
            ContextBuilder(self.gm).build_parser_prompt("look"),
            ContextBuilder(self.gm).build_narrator_prompt("look"),
        ):
            self.assertIn("Very Overloaded (3/4)", section(prompt, "CONDITION"))

    def test_a_carried_body_reads_carried_in_the_corpses_block(self):
        clear_sky(self.gm)
        self.gm.player.current_location_id = "zone_street"
        self.gm.world.outbreak_started_at = 0
        self.gm.world.corpses["c1"] = CorpseEntity(
            corpse_id="c1",
            zone_id="zone_street",
            gap=0.0,
            female=False,
            outfit="generic01",
            died_at=0,
            rot_at_death=1,
        )
        self.gm.player.carrying_corpse = "c1"
        parser = section(self.parser(), "CORPSES")
        self.assertTrue(parser.startswith(" - c1, carried, "), parser)
        narrator = ContextBuilder(self.gm).build_narrator_prompt("look")
        self.assertIn(" - carried, ", narrator.split("[CORPSES]")[1].split("[OUTCOMES]")[0])

    def test_the_scene_names_include_what_is_inside_a_carried_bag(self):
        self.gm.player.equipment[CharacterArmorSlot.SHOULDERS] = self.entity(
            "item_schoolbag", "item_canned_beans"
        )
        self.gm.player.worn[BodyLocation.SATCHEL] = self.entity("item_satchel")
        choices = ContextBuilder(self.gm).scene_choices()
        self.assertEqual(sorted(choices.bags), ["Satchel", "Schoolbag"])
        self.assertEqual(choices.bag_items, ("Canned Beans",))
        self.assertIn("Canned Beans", choices.carried)
        self.assertIn("Schoolbag", choices.carried)
        self.assertEqual(choices.held, ("Schoolbag",))
        keys = ContextBuilder(self.gm).scene_keys()
        self.assertIn("bags", keys)

    def test_put_is_listed_only_with_a_bag(self):
        self.assertNotIn("- PUT ", self.parser())
        self.gm.player.inventory.append(self.entity("item_toolbox"))
        self.assertIn("- PUT ", self.parser())
        self.assertIn("- TAKE ", self.parser())

    def test_a_barbell_in_a_bag_counts_for_the_exercise_block(self):
        self.gm.player.inventory.append(self.entity("item_duffel_bag", "item_barbell"))
        self.assertIn("Carrying: a barbell", self.parser())


class RoomsContextTests(unittest.TestCase):
    """Spec 25, What the narrator and the player see: the [ROOMS] block."""

    def setUp(self):
        self.gm = GameManager()
        self.builder = ContextBuilder(self.gm)

    def block(self, prompt: str) -> str:
        start = prompt.index("[ROOMS]")
        return prompt[start : prompt.index("\n\n[", start)]

    def test_the_block_lists_each_room_and_its_containers_unopened(self):
        lines = self.block(self.builder.build_parser_prompt("look")).splitlines()
        self.assertEqual(
            lines[1:],
            [
                "kitchen: kitchen counter (not opened), kitchen cupboards (not opened), "
                "fridge (not opened), freezer (not opened)",
                "bedroom: wardrobe (not opened), dresser (not opened), bedside table (not opened)",
                "bathroom: medicine cabinet (not opened), bathroom counter (not opened)",
                "living room (you are here): side table (not opened), "
                "living room shelves (not opened)",
            ],
        )

    def test_an_opened_container_lists_what_is_left_in_it(self):
        resolve_actions(self.gm, SearchAction(target_name="bedroom"))
        resolve_actions(self.gm, MoveAction(destination="kitchen"))
        resolve_actions(self.gm, SearchAction(target_name="kitchen counter"))
        lines = self.block(self.builder.build_narrator_prompt("look")).splitlines()
        self.assertIn(
            "kitchen (you are here): kitchen counter (opened: canned beans, water bottle, "
            "kitchen knife, frying pan), kitchen cupboards (not opened), fridge (not opened), "
            "freezer (not opened)",
            lines,
        )
        self.assertTrue(
            any(
                line.startswith("bedroom: wardrobe (opened: black jacket, schoolbag)")
                for line in lines
            )
        )

    def test_an_unopened_container_never_lists_its_contents(self):
        prompt = self.builder.build_parser_prompt("look")
        self.assertNotIn("schoolbag", self.block(prompt))
        self.assertNotIn("canned beans", self.block(prompt))

    def test_an_emptied_container_says_empty(self):
        resolve_actions(self.gm, SearchAction(target_name="wardrobe"))
        self.gm.world.locations["zone_home"].rooms["bedroom"].containers[0].contents.clear()
        self.assertIn(
            "wardrobe (opened: empty)", self.block(self.builder.build_parser_prompt("look"))
        )

    def test_the_block_comes_after_the_zones_and_before_the_doors_in_both_prompts(self):
        parser = self.builder.build_parser_prompt("look")
        self.assertLess(parser.index("[ZONES]"), parser.index("[ROOMS]"))
        self.assertLess(parser.index("[ROOMS]"), parser.index("[DOORS AND WINDOWS]"))
        narrator = self.builder.build_narrator_prompt("look")
        self.assertLess(narrator.index("[ROOMS]"), narrator.index("[DOORS AND WINDOWS]"))

    def test_a_zone_without_rooms_says_none(self):
        self.gm.player.current_location_id = "zone_street"
        self.assertEqual(self.block(self.builder.build_parser_prompt("look")), "[ROOMS]\nNone")

    def test_the_other_zones_rooms_are_not_listed(self):
        self.assertNotIn("hallway", self.block(self.builder.build_parser_prompt("look")))

    def test_search_is_listed_when_the_zone_has_rooms(self):
        self.assertIn("- SEARCH", self.builder.build_parser_prompt("look"))
        self.gm.player.current_location_id = "zone_street"
        self.assertNotIn("- SEARCH", self.builder.build_parser_prompt("look"))

    def test_take_and_put_are_listed_once_a_container_in_the_room_has_been_opened(self):
        self.gm.player.current_room = "kitchen"
        self.assertNotIn("- TAKE <", self.builder.build_parser_prompt("look"))
        resolve_actions(self.gm, SearchAction(target_name="kitchen counter"))
        prompt = self.builder.build_parser_prompt("look")
        self.assertIn("- TAKE <", prompt)
        self.assertIn("- PUT <", prompt)
