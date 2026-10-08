"""Topics: what an NPC can tell the player (llm-contract: Topics)."""

import unittest

from data.story.beats import STORY_BEATS
from data.story.quests import build_starting_quests
from data.story.topics import TOPICS
from managers.game import GameManager
from managers.validator import ActionValidator, Rejected
from modules.action.parser import parse_action_line
from modules.action.types import RequestAction
from modules.character.state import CharacterTrust
from modules.story.beats import DiscoverFlag, FlagDiscovered, OutbreakStarted
from modules.story.quest import QuestStatus
from tests.support import adjust_regard, simulate

NEWS = "The news calls it the Ashby fever. Bites spread it, and the ones who die of it get back up."


def jen_game(*, outbreak: bool = True, trust: int = 10) -> GameManager:
    """Orton beside Jen, whose trust is `trust` (it starts at 2)."""
    gm = GameManager()
    gm.player.current_location_id = "zone_neighborhood"
    if outbreak:
        gm.world.outbreak_started_at = 0
    adjust_regard(gm, "npc_jen", trust=trust - 2)
    return gm


REQUEST_NEWS = RequestAction(npc_name="Jen", request="about", argument="outbreak_news")


TENTATIVE, SOLID = CharacterTrust.TENTATIVE, CharacterTrust.SOLID
FACT_CLINIC_REGULARS = (
    "The clinic's study people came in on payday, a bandage in the crook of every arm. "
    "Lately they'd looked grey, and one fell asleep at the counter."
)
FACT_EMMA_BROTHER = (
    "Her brother Danny took the clinic's paid study for rent money. "
    "He stopped answering two days before the sirens."
)
FACT_ROOF_TANK = (
    "The roof tank holds the building's water after the mains go. "
    "The valve's in the boiler room; he has the key."
)
FACT_JEN_MOTHER = (
    "Her mother is a nurse at St. Agnes. Her last texts said the first fever patients all had "
    "the same bandage in the crook of the arm, and that staff were told to say nothing. "
    "Then they stopped."
)
FACT_MARCUS_PORT = (
    "He worked the container terminal for twenty years. A friend still there says the "
    "quarantined ship's crew had a common flu, and not one of them has turned."
)
FACT_MARCUS_TENANTS = (
    "The Novaks down the hall left in a hurry the week before the sirens: Tomas had a fever "
    "that wouldn't break, and his wife drove him to St. Agnes. They never came back."
)
FACT_EMMA_FLYERS = (
    "She designed the study's recruitment flyers for a client called Velloran: "
    '"Paid volunteers wanted. Earn while you heal." Danny saw them on her desk and signed up.'
)

# topic id: (npc, requires, min trust, gloss, fact, flag it discovers)
WIDER_TOPICS = {
    "outbreak_news": ("npc_jen", OutbreakStarted(), TENTATIVE, None, NEWS, "apocalypse_cause"),
    "clinic_regulars": (
        "npc_jen",
        None,
        TENTATIVE,
        "what Jen has noticed about the clinic's regulars",
        FACT_CLINIC_REGULARS,
        "clinic_odd",
    ),
    "emma_brother": (
        "npc_emma",
        OutbreakStarted(),
        SOLID,
        "Emma's brother",
        FACT_EMMA_BROTHER,
        "trial_rumour",
    ),
    "roof_tank": (
        "npc_marcus",
        FlagDiscovered("cordon"),
        SOLID,
        "the building's water tank",
        FACT_ROOF_TANK,
        "roof_tank",
    ),
    "jen_mother": (
        "npc_jen",
        OutbreakStarted(),
        TENTATIVE,
        "Jen's mother at the hospital",
        FACT_JEN_MOTHER,
        "hospital_texts",
    ),
    "marcus_port": (
        "npc_marcus",
        FlagDiscovered("apocalypse_cause"),
        TENTATIVE,
        "what Marcus heard from the port",
        FACT_MARCUS_PORT,
        "ship_doubt",
    ),
    "marcus_tenants": (
        "npc_marcus",
        None,
        TENTATIVE,
        "the neighbours who left",
        FACT_MARCUS_TENANTS,
        "novaks_left",
    ),
    "emma_flyers": (
        "npc_emma",
        FlagDiscovered("trial_rumour"),
        SOLID,
        "the work Emma did for the study",
        FACT_EMMA_FLYERS,
        "study_flyers",
    ),
}


class TopicRowTests(unittest.TestCase):
    """llm-contract: Topics: the starting topic."""

    def test_outbreak_news_is_jens_and_needs_the_outbreak_and_tentative_trust(self):
        topic = TOPICS["outbreak_news"]
        self.assertEqual(topic.npc_id, "npc_jen")
        self.assertEqual(topic.requires, OutbreakStarted())
        self.assertEqual(topic.min_trust, CharacterTrust.TENTATIVE)
        self.assertEqual(topic.fact, NEWS)
        self.assertEqual(topic.discovers, "apocalypse_cause")

    def test_the_registry_holds_the_eight_topics(self):
        self.assertEqual(list(TOPICS), list(WIDER_TOPICS))

    def test_each_topic_holds_its_npc_requirement_trust_fact_and_flag(self):
        for topic_id, (npc, requires, trust, gloss, fact, flag) in WIDER_TOPICS.items():
            with self.subTest(topic_id):
                topic = TOPICS[topic_id]
                self.assertEqual(topic.npc_id, npc)
                self.assertEqual(topic.requires, requires)
                self.assertEqual(topic.min_trust, trust)
                if gloss is not None:
                    self.assertEqual(topic.gloss, gloss)
                self.assertEqual(topic.fact, fact)
                self.assertEqual(topic.discovers, flag)

    def test_no_fact_holds_a_number(self):
        for topic in TOPICS.values():
            self.assertNotRegex(topic.fact, r"\d", topic.topic_id)

    def test_the_parser_reads_an_about_request_with_a_topic_id(self):
        self.assertEqual(parse_action_line("REQUEST Jen about outbreak_news"), REQUEST_NEWS)


class RequestAboutTests(unittest.TestCase):
    def test_at_the_minimum_trust_the_fact_is_told(self):
        gm = jen_game(trust=10)
        facts = simulate(gm, REQUEST_NEWS)
        self.assertIn(f"Jen tells Orton: {NEWS}", facts)
        self.assertIn("outbreak_news", gm.narrative.social_log.told_topics)

    def test_the_flag_it_reveals_is_discovered(self):
        gm = jen_game()
        simulate(gm, REQUEST_NEWS)
        self.assertIn("apocalypse_cause", gm.narrative.discovered_flags)
        self.assertIs(gm.narrative.flags["apocalypse_cause"], True)

    def test_below_the_minimum_trust_she_deflects(self):
        gm = jen_game(trust=9)
        facts = simulate(gm, REQUEST_NEWS)
        self.assertIn("Jen deflects the question.", facts)
        self.assertNotIn("outbreak_news", gm.narrative.social_log.told_topics)
        self.assertNotIn("apocalypse_cause", gm.narrative.discovered_flags)

    def test_quest_understand_the_crisis_completes_through_the_topic(self):
        gm = jen_game()
        facts = simulate(gm, REQUEST_NEWS)
        quest = gm.quests["quest_understand_the_crisis"]
        self.assertEqual(quest.status, QuestStatus.COMPLETED)
        self.assertIn('Quest "Understand What\'s Happening" completed.', " ".join(facts))

    def test_a_topic_needing_the_outbreak_is_refused_before_it(self):
        gm = jen_game(outbreak=False)
        result = ActionValidator(gm).validate(REQUEST_NEWS)
        assert isinstance(result, Rejected)
        self.assertEqual(result.reason, "Jen has nothing to say about that.")

    def test_an_unknown_topic_is_refused(self):
        gm = jen_game()
        result = ActionValidator(gm).validate(
            RequestAction(npc_name="Jen", request="about", argument="the_bunker")
        )
        assert isinstance(result, Rejected)
        self.assertEqual(result.reason, "Jen has nothing to say about that.")

    def test_another_npc_has_nothing_to_say_about_jens_topic(self):
        gm = jen_game()
        gm.player.current_location_id = "zone_building"
        result = ActionValidator(gm).validate(
            RequestAction(npc_name="Emma", request="about", argument="outbreak_news")
        )
        assert isinstance(result, Rejected)
        self.assertEqual(result.reason, "Emma has nothing to say about that.")

    def test_asking_costs_five_minutes_and_needs_no_roll(self):
        gm = jen_game()
        facts = simulate(gm, REQUEST_NEWS)
        self.assertEqual(gm.narrative.minutes, 5)
        self.assertEqual(facts[-1], "About 5 minutes pass.")

    def test_a_topic_can_be_asked_again(self):
        gm = jen_game()
        simulate(gm, REQUEST_NEWS)
        facts = simulate(gm, REQUEST_NEWS)
        self.assertIn(f"Jen tells Orton: {NEWS}", facts)

    def test_a_refused_topic_costs_nothing(self):
        gm = jen_game(outbreak=False)
        simulate(gm, REQUEST_NEWS)
        self.assertEqual(gm.narrative.minutes, 0)


class QuestKeysAreProducedTests(unittest.TestCase):
    """The starting quests can only complete through the engine's own producers."""

    def test_every_discover_objective_is_revealed_by_a_topic_or_a_beat(self):
        revealed = {topic.discovers for topic in TOPICS.values()} | {
            effect.flag
            for beat in STORY_BEATS.values()
            for effect in beat.effects
            if isinstance(effect, DiscoverFlag)
        }
        for quest in build_starting_quests().values():
            for objective in quest.objectives:
                if objective.startswith("discover:"):
                    self.assertIn(objective.removeprefix("discover:"), revealed)

    def test_every_npc_status_objective_is_a_derived_status(self):
        for quest in build_starting_quests().values():
            for objective in quest.objectives:
                if objective.startswith("npc_status:"):
                    self.assertEqual(objective.split(":")[2], "trusts_player")
