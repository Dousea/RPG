"""Spec 10, Memory: the last story goes to the narrator, the last turn to the parser."""

import unittest

from adapters import engine as engine_module
from adapters.llm import LLMError
from adapters.save import codec
from data.memory import LAST_SCENE_MAX_CHARS
from managers.context import ContextBuilder
from managers.game import GameManager
from tests.test_engine import EngineTestCase

STORY = "You walk out into the building."


def _builder() -> ContextBuilder:
    gm = GameManager()
    gm.player.current_location_id = "zone_building"
    return ContextBuilder(gm)


class LastSceneBlockTests(unittest.TestCase):
    def test_the_story_is_rendered_verbatim_between_memory_and_state(self):
        builder = _builder()
        builder.manager.memory.last_story = 'Emma said: "Stay close."\nYou nod.'
        prompt = builder.build_narrator_prompt("look")
        self.assertIn("[LAST SCENE]", prompt)
        self.assertIn('Emma said: "Stay close."\nYou nod.', prompt)
        self.assertLess(prompt.index("[RECENT EVENTS]"), prompt.index("[LAST SCENE]"))
        self.assertLess(prompt.index("[LAST SCENE]"), prompt.index("[TIME AND WEATHER]"))

    def test_the_block_is_absent_without_a_story(self):
        self.assertNotIn("[LAST SCENE]", _builder().build_narrator_prompt("look"))

    def _block(self, story: str) -> str:
        builder = _builder()
        builder.manager.memory.last_story = story
        prompt = builder.build_narrator_prompt("look")
        block = prompt.split("[LAST SCENE]")[1].split("[TIME AND WEATHER]")[0]
        return block.split("\n\n", 1)[1].strip()

    def test_a_long_story_is_cut_at_a_sentence_boundary(self):
        story = "A sentence here. " * 400
        shown = self._block(story)
        self.assertLessEqual(len(shown), LAST_SCENE_MAX_CHARS)
        self.assertTrue(shown.endswith("here."))
        self.assertGreater(len(shown), LAST_SCENE_MAX_CHARS - 40)

    def test_a_long_story_prefers_a_line_boundary_when_later(self):
        story = ("word " * 100 + "\n") * 40
        shown = self._block(story)
        self.assertLessEqual(len(shown), LAST_SCENE_MAX_CHARS)
        self.assertTrue(shown.endswith("word"))

    def test_only_the_last_paragraph_is_shown(self):
        story = "The zombie falls and lies still.\n\nYou look up.\n\nSirens wail far off."
        self.assertEqual(self._block(story), "Sirens wail far off.")

    def test_the_block_says_it_is_where_the_scene_left_off(self):
        builder = _builder()
        builder.manager.memory.last_story = STORY
        prompt = builder.build_narrator_prompt("look")
        self.assertIn("(Where the story the player last read left off.", prompt)

    def test_a_short_story_is_not_cut(self):
        self.assertEqual(self._block("Short. Story."), "Short. Story.")


class LastTurnBlockTests(unittest.TestCase):
    def test_the_latest_entry_sits_right_before_the_player_input(self):
        builder = _builder()
        builder.manager.record_event('Day 1, 08:00 AM, X. Orton tries: "old"')
        builder.manager.record_event('Day 1, 08:05 AM, X. Orton tries: "new" It happens.')
        prompt = builder.build_parser_prompt("do that again")
        self.assertIn("[LAST TURN]", prompt)
        block = prompt.split("[LAST TURN]")[1].split("[PLAYER INPUT]")[0]
        self.assertIn('"new" It happens.', block)
        self.assertNotIn('"old"', block)
        self.assertLess(prompt.index("[AVAILABLE ACTIONS]"), prompt.index("[LAST TURN]"))

    def test_the_block_is_absent_with_an_empty_log(self):
        self.assertNotIn("[LAST TURN]", _builder().build_parser_prompt("look"))

    def test_no_story_text_reaches_the_parser(self):
        builder = _builder()
        builder.manager.memory.last_story = "UNIQUE PROSE"
        builder.manager.record_event('Day 1, 08:00 AM, X. Orton tries: "a"')
        self.assertNotIn("UNIQUE PROSE", builder.build_parser_prompt("look"))


class LastStoryEngineTests(EngineTestCase):
    def test_the_story_is_stored_after_a_narrated_turn(self):
        self.engine.play("go out")
        self.assertEqual(self.engine.game.memory.last_story, STORY)

    def test_the_next_turn_replaces_it(self):
        self.engine.play("go out")
        self.llm.story = "STORY:\nSecond."
        self.engine.play("look")
        self.assertEqual(self.engine.game.memory.last_story, "Second.")

    def test_the_next_narrator_prompt_carries_it(self):
        self.engine.play("go out")
        self.engine.play("look")
        self.assertIn(STORY, self.llm.narrator_prompts[-1].split("[LAST SCENE]")[1])

    def test_the_first_turn_has_no_block(self):
        self.engine.play("go out")
        self.assertNotIn("[LAST SCENE]", self.llm.narrator_prompts[0])

    def test_a_failed_narrator_call_clears_it(self):
        self.engine.play("go out")

        def failing(prompt: str) -> str:
            raise LLMError("narrator offline")

        engine_module.llm.query_narrator = failing
        self.engine.play("look")
        self.assertEqual(self.engine.game.memory.last_story, "")

    def test_the_parser_gets_the_last_turn_but_never_the_story(self):
        self.engine.play("go out")
        self.engine.play("again")
        prompt = self.llm.prompts[-1]
        self.assertIn("[LAST TURN]", prompt)
        self.assertIn('tries: "go out"', prompt)
        self.assertNotIn(STORY, prompt)


class LastStorySaveTests(unittest.TestCase):
    def test_a_save_round_trips_the_story(self):
        gm = GameManager()
        gm.memory.last_story = "Line one.\nLine two."
        loaded = codec.from_dict(codec.to_dict(gm))
        self.assertEqual(loaded.memory.last_story, "Line one.\nLine two.")

    def test_a_new_game_has_none(self):
        self.assertEqual(GameManager().memory.last_story, "")
