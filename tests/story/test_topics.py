"""Topics: what an NPC can tell the player (llm-contract: Topics)."""

import unittest

from data.story.quests import build_starting_quests
from data.story.topics import TOPICS
from managers.game import GameManager
from managers.validator import ActionValidator, Rejected
from modules.action.parser import parse_action_line
from modules.action.types import AskAction
from modules.character.state import CharacterTrust
from modules.story.beats import OutbreakStarted
from modules.story.quest import QuestStatus
from tests.support import adjust_regard, simulate

NEWS = (
    "The news is calling it the zombie infection. Bites spread it, and the ones who "
    "die from it get back up."
)


def jen_game(*, outbreak: bool = True, trust: int = 10) -> GameManager:
    """Orton beside Jen, whose trust is `trust` (it starts at 2)."""
    gm = GameManager()
    gm.player.current_location_id = "zone_neighborhood"
    if outbreak:
        gm.world.outbreak_started_at = 0
    adjust_regard(gm, "npc_jen", trust=trust - 2)
    return gm


ASK_NEWS = AskAction(npc_name="Jen", request="about", argument="outbreak_news")


class TopicRowTests(unittest.TestCase):
    """llm-contract: Topics: the one starting topic."""

    def test_outbreak_news_is_jens_and_needs_the_outbreak_and_tentative_trust(self):
        topic = TOPICS["outbreak_news"]
        self.assertEqual(topic.npc_id, "npc_jen")
        self.assertEqual(topic.requires, OutbreakStarted())
        self.assertEqual(topic.min_trust, CharacterTrust.TENTATIVE)
        self.assertEqual(topic.fact, NEWS)
        self.assertEqual(topic.discovers, "apocalypse_cause")

    def test_the_registry_has_exactly_one_row(self):
        self.assertEqual(list(TOPICS), ["outbreak_news"])

    def test_the_parser_reads_an_about_request_with_a_topic_id(self):
        self.assertEqual(parse_action_line("ASK Jen about outbreak_news"), ASK_NEWS)


class AskAboutTests(unittest.TestCase):
    def test_at_the_minimum_trust_the_fact_is_told(self):
        gm = jen_game(trust=10)
        facts = simulate(gm, ASK_NEWS)
        self.assertIn(f"Jen tells Orton: {NEWS}", facts)
        self.assertIn("outbreak_news", gm.narrative.social_log.told_topics)

    def test_the_flag_it_reveals_is_discovered(self):
        gm = jen_game()
        simulate(gm, ASK_NEWS)
        self.assertIn("apocalypse_cause", gm.narrative.discovered_flags)
        self.assertIs(gm.narrative.flags["apocalypse_cause"], True)

    def test_below_the_minimum_trust_she_deflects(self):
        gm = jen_game(trust=9)
        facts = simulate(gm, ASK_NEWS)
        self.assertIn("Jen deflects the question.", facts)
        self.assertNotIn("outbreak_news", gm.narrative.social_log.told_topics)
        self.assertNotIn("apocalypse_cause", gm.narrative.discovered_flags)

    def test_quest_understand_the_crisis_completes_through_the_topic(self):
        gm = jen_game()
        facts = simulate(gm, ASK_NEWS)
        quest = gm.quests["quest_understand_the_crisis"]
        self.assertEqual(quest.status, QuestStatus.COMPLETED)
        self.assertIn("Quest 'quest_understand_the_crisis' completed!", " ".join(facts))

    def test_a_topic_needing_the_outbreak_is_refused_before_it(self):
        gm = jen_game(outbreak=False)
        result = ActionValidator(gm).validate(ASK_NEWS)
        assert isinstance(result, Rejected)
        self.assertEqual(result.reason, "Jen has nothing to say about that.")

    def test_an_unknown_topic_is_refused(self):
        gm = jen_game()
        result = ActionValidator(gm).validate(
            AskAction(npc_name="Jen", request="about", argument="the_bunker")
        )
        assert isinstance(result, Rejected)
        self.assertEqual(result.reason, "Jen has nothing to say about that.")

    def test_another_npc_has_nothing_to_say_about_jens_topic(self):
        gm = jen_game()
        gm.player.current_location_id = "zone_building"
        result = ActionValidator(gm).validate(
            AskAction(npc_name="Emma", request="about", argument="outbreak_news")
        )
        assert isinstance(result, Rejected)
        self.assertEqual(result.reason, "Emma has nothing to say about that.")

    def test_asking_costs_five_minutes_and_needs_no_roll(self):
        gm = jen_game()
        facts = simulate(gm, ASK_NEWS)
        self.assertEqual(gm.narrative.minutes, 5)
        self.assertEqual(facts[-1], "About 5 minutes pass.")

    def test_a_topic_can_be_asked_again(self):
        gm = jen_game()
        simulate(gm, ASK_NEWS)
        facts = simulate(gm, ASK_NEWS)
        self.assertIn(f"Jen tells Orton: {NEWS}", facts)

    def test_a_refused_topic_costs_nothing(self):
        gm = jen_game(outbreak=False)
        simulate(gm, ASK_NEWS)
        self.assertEqual(gm.narrative.minutes, 0)


class QuestKeysAreProducedTests(unittest.TestCase):
    """The starting quests can only complete through the engine's own producers."""

    def test_every_discover_objective_is_revealed_by_a_topic(self):
        revealed = {topic.discovers for topic in TOPICS.values()}
        for quest in build_starting_quests().values():
            for objective in quest.objectives:
                if objective.startswith("discover:"):
                    self.assertIn(objective.removeprefix("discover:"), revealed)

    def test_every_npc_status_objective_is_a_derived_status(self):
        for quest in build_starting_quests().values():
            for objective in quest.objectives:
                if objective.startswith("npc_status:"):
                    self.assertEqual(objective.split(":")[2], "trusts_player")
