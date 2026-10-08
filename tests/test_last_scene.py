"""llm-contract: Memory: the last story goes to the narrator, the last turn to the parser."""

import unittest

from adapters import engine as engine_module
from adapters.llm import DeltaCallback, LLMError
from adapters.save import codec
from data.story.memory import LAST_SCENE_MAX_CHARS, LAST_SCENE_MAX_LINES
from managers.context import ContextBuilder
from managers.game import GameManager
from tests.test_engine import EngineTestCase

STORY = "You walk out into the building."


def _builder() -> ContextBuilder:
    gm = GameManager()
    gm.player.current_location_id = "zone_building"
    return ContextBuilder(gm)


class LastSceneBlockTests(unittest.TestCase):
    def _prompt(self, story: str) -> str:
        builder = _builder()
        builder.manager.memory.last_story = story
        return builder.build_narrator_prompt("look")

    def _lines(self, story: str) -> list[str]:
        prompt = self._prompt(story)
        block = prompt.split("[LAST SCENE]")[1].split("[TIME AND WEATHER]")[0]
        return [line for line in block.splitlines() if line.startswith("- ")]

    def test_the_lines_sit_between_memory_and_state(self):
        prompt = self._prompt('Emma says, "Stay close."')
        self.assertIn('- Emma: "Stay close."', prompt)
        self.assertLess(prompt.index("[RECENT EVENTS]"), prompt.index("[LAST SCENE]"))
        self.assertLess(prompt.index("[LAST SCENE]"), prompt.index("[TIME AND WEATHER]"))

    def test_the_block_is_absent_without_a_story(self):
        self.assertNotIn("[LAST SCENE]", _builder().build_narrator_prompt("look"))

    def test_a_story_without_dialogue_gives_no_block(self):
        self.assertNotIn("[LAST SCENE]", self._prompt("Emma nods. You walk on."))

    def test_lines_come_in_order_with_their_speakers(self):
        story = (
            'Emma turns to face the door. "We can\'t stay here," Emma says.\n\n'
            'You say, "Then we move."\n\n'
            'Somewhere a door slams. "Run!"\n\n'
            'Marcus whispers, "I know a way."'
        )
        self.assertEqual(
            self._lines(story),
            [
                '- Emma: "We can\'t stay here,"',
                '- Orton: "Then we move."',
                '- "Run!"',
                '- Marcus: "I know a way."',
            ],
        )

    def test_the_speaker_after_the_quote_is_found(self):
        self.assertEqual(
            self._lines('"Get down!" Marcus shouts. Jen ducks.'), ['- Marcus: "Get down!"']
        )

    def test_the_first_name_in_the_sentence_speaks(self):
        self.assertEqual(self._lines('You ask Emma, "Are you hurt?"'), ['- Orton: "Are you hurt?"'])
        self.assertEqual(self._lines('Emma looks at you. "I\'m fine."'), ['- "I\'m fine."'])
        self.assertEqual(self._lines('Emma tells you, "I\'m fine."'), ['- Emma: "I\'m fine."'])

    def test_a_name_in_the_next_sentence_is_not_the_speaker(self):
        self.assertEqual(
            self._lines('Jen ducks. "Get down!" The dark swallows it.'), ['- "Get down!"']
        )

    def test_curly_quotes_count(self):
        self.assertEqual(
            self._lines("Jen mutters, \u201cNot again.\u201d"), ['- Jen: "Not again."']
        )

    def test_apostrophes_are_not_quotes(self):
        story = "Emma's hands shake; it's Marcus's gun and you can't hold it."
        self.assertNotIn("[LAST SCENE]", self._prompt(story))

    def test_no_prose_outside_the_quotes_reaches_the_block(self):
        prompt = self._prompt('Silent scream, wide unblinking eyes. Emma says, "Move."')
        block = prompt.split("[LAST SCENE]")[1].split("[TIME AND WEATHER]")[0]
        self.assertNotIn("scream", block)
        self.assertNotIn("unblinking", block)

    def test_only_the_last_lines_are_kept(self):
        story = " ".join(f'Emma says, "Line {n}."' for n in range(LAST_SCENE_MAX_LINES + 3))
        lines = self._lines(story)
        self.assertEqual(len(lines), LAST_SCENE_MAX_LINES)
        self.assertEqual(lines[-1], f'- Emma: "Line {LAST_SCENE_MAX_LINES + 2}."')
        self.assertNotIn('"Line 2."', "".join(lines))

    def test_the_character_cap_is_the_final_cut(self):
        story = " ".join(f'Emma says, "{"word " * 30}{n}."' for n in range(LAST_SCENE_MAX_LINES))
        prompt = self._prompt(story)
        block = prompt.split("[LAST SCENE]")[1].split("[TIME AND WEATHER]")[0]
        lines = block.split("\n\n", 1)[1].strip()
        self.assertLessEqual(len(lines), LAST_SCENE_MAX_CHARS)

    def test_the_block_says_these_are_the_words_spoken(self):
        prompt = self._prompt('Emma says, "Hi."')
        self.assertIn("(The words spoken in the scene the player last read", prompt)


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
        self.llm.story = 'STORY:\nEmma says, "Stay close."'
        self.engine.play("go out")
        self.engine.play("look")
        self.assertIn(
            '- Emma: "Stay close."', self.llm.narrator_prompts[-1].split("[LAST SCENE]")[1]
        )

    def test_the_first_turn_has_no_block(self):
        self.engine.play("go out")
        self.assertNotIn("[LAST SCENE]", self.llm.narrator_prompts[0])

    def test_a_failed_narrator_call_clears_it(self):
        self.engine.play("go out")

        def failing(prompt: str, on_delta: DeltaCallback | None = None) -> str:
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
