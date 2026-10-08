"""llm-contract: Outcome facts leak no internal ids."""

import re
import unittest

from data.items import ITEMS
from managers.game import GameManager
from modules.action.types import MoveAction, SearchAction, TakeAction
from modules.entity.corpse import CorpseEntity
from modules.entity.item import ItemEntity
from tests.support import simulate
from tests.test_simulation import zombie_game

ID_TOKEN = re.compile(
    r"\b[a-z]+_[a-z_0-9]+\b|\b(?:item|quest|zone|npc|door|window|corpse|zombie)_\w+"
)


def assert_no_ids(case: unittest.TestCase, facts: list[str]) -> None:
    for fact in facts:
        case.assertIsNone(ID_TOKEN.search(fact), fact)


class OutcomeFactIdTests(unittest.TestCase):
    def test_a_move_a_take_a_search_and_a_refusal_hold_no_ids(self):
        gm = GameManager()
        facts = simulate(
            gm,
            SearchAction(target_name="side table"),
            MoveAction(destination="out"),
            MoveAction(destination="out"),
            TakeAction(item_name="Crowbar"),
            TakeAction(item_name="Unicorn"),
        )
        self.assertTrue(any("Quest" in fact for fact in facts))
        self.assertTrue(any(fact.startswith("Refused:") for fact in facts))
        assert_no_ids(self, facts)

    def test_a_blocked_move_holds_no_ids(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_street"
        assert_no_ids(self, simulate(gm, MoveAction(destination="The Corner Store")))

    def test_a_corpse_search_holds_no_ids(self):
        gm = zombie_game()
        corpse = CorpseEntity(
            corpse_id="c1",
            zone_id="zone_street",
            gap=1.0,
            female=False,
            outfit="generic01",
            died_at=0,
            rot_at_death=1,
        )
        corpse.contents = [ItemEntity(item=ITEMS["item_jacket_police"])]
        gm.world.corpses["c1"] = corpse
        assert_no_ids(self, simulate(gm, SearchAction(target_name="c1")))
