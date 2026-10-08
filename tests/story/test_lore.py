"""world-lore: Selection and the cap, Stages, Known not just true."""

import logging
import unittest
from unittest import mock

from data.story import lore as lore_k
from managers.game import GameManager
from managers.story.lore import (
    LoreHit,
    drop_order,
    record_turn,
    select_lore,
    system_text,
    world_lines,
)
from managers.story.lorebook import Lorebook, get_lorebook, holds_number, known_ids
from modules.action.types import AddGoalAction
from modules.story.lore import LoreEntry, Position
from tests.support import simulate

STAGE_IDS = ("stage_news", "stage_broadcast", "stage_evacuation", "stage_cordon", "stage_loop")


def shown(manager: GameManager, text: str = "", scores: dict[str, float] | None = None):
    hits = select_lore(manager, text, scores or {})
    return [hit.entry.entry_id for hit in hits if hit.shown]


def discover(manager: GameManager, *flags: str) -> None:
    manager.narrative.discovered_flags.update(flags)


def at_minute(minute: int, *, fire: bool = True) -> GameManager:
    gm = GameManager()
    gm.advance_clock(minute)
    if fire:
        simulate(gm, AddGoalAction("short_term", "rest"))
    return gm


class PublicAndLockedTests(unittest.TestCase):
    def test_a_public_entry_shows_once_its_condition_holds_and_not_before(self):
        gm = GameManager()
        self.assertNotIn("army_evac", shown(gm, "the army"))
        discover(gm, "evacuation")
        self.assertIn("army_evac", shown(gm, "the army"))

    def test_an_entry_stops_showing_once_its_replacement_holds(self):
        gm = GameManager()
        discover(gm, "apocalypse_cause")
        self.assertIn("ship_story", shown(gm, "the ship"))
        discover(gm, "trial_truth")
        ids = shown(gm, "the ship")
        self.assertIn("ship_story_wrong", ids)
        self.assertNotIn("ship_story", ids)

    def test_a_replacement_is_judged_on_its_condition_alone_not_its_keys(self):
        gm = GameManager()
        discover(gm, "apocalypse_cause", "trial_truth")
        self.assertNotIn("ship_story", shown(gm, "ship"))
        self.assertNotIn("ship_story", shown(gm, "something else"))

    def test_a_public_entry_is_replaced_by_a_secret_one(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_clinic"
        self.assertIn("clinic_public", shown(gm))
        discover(gm, "trial_truth")
        ids = shown(gm)
        self.assertIn("imrie_truth", ids)
        self.assertNotIn("clinic_public", ids)

    def test_a_locked_entry_never_shows_before_its_flag_even_with_its_zone_and_words(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_clinic"
        ids = shown(gm, "the study binder, Velloran, VX-7, ship")
        for locked in ("trial_truth", "imrie_truth", "velloran_memo", "clinic_odd"):
            self.assertNotIn(locked, ids)
        discover(gm, "trial_truth")
        self.assertIn("trial_truth", shown(gm))

    def test_an_all_entry_needs_both_flags(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_clinic"
        discover(gm, "trial_truth")
        self.assertNotIn("danny_in_binder", shown(gm, "Danny"))
        discover(gm, "trial_rumour")
        self.assertIn("danny_in_binder", shown(gm, "Danny"))
        gm = GameManager()
        discover(gm, "trial_rumour")
        self.assertNotIn("danny_in_binder", shown(gm, "Danny"))

    def test_a_beat_and_minutes_link_shows_only_once_that_long_has_passed(self):
        gm = at_minute(7020)
        self.assertEqual(gm.world.fired_beats["cordon"], 7020)
        self.assertIn("bridges_cordon", shown(gm, "the bridge"))
        gm.advance_clock(4319)
        ids = shown(gm, "the bridge")
        self.assertIn("bridges_cordon", ids)
        self.assertNotIn("bridges_burnt", ids)
        gm.advance_clock(1)
        ids = shown(gm, "the bridge")
        self.assertIn("bridges_burnt", ids)
        self.assertNotIn("bridges_cordon", ids)


class KeyTests(unittest.TestCase):
    def test_a_zone_key_shows_the_entry_in_that_zone_only(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_pharmacy"
        self.assertIn("pharmacy", shown(gm))
        gm.player.current_location_id = "zone_supermarket"
        self.assertNotIn("pharmacy", shown(gm))

    def test_an_npc_key_shows_the_entry_while_that_npc_is_present(self):
        gm = GameManager()
        discover(gm, "hospital_texts")
        gm.player.current_location_id = "zone_street"
        self.assertNotIn("hospital_texts", shown(gm))
        gm.player.current_location_id = "zone_neighborhood"
        self.assertEqual(gm.npcs["npc_jen"].current_location_id, "zone_neighborhood")
        self.assertIn("hospital_texts", shown(gm))

    def test_a_word_key_matches_whole_words_with_case_ignored(self):
        gm = GameManager()
        self.assertIn("merrow_star", shown(gm, "What about the SHIP?"))
        self.assertNotIn("merrow_star", shown(gm, "tell me about our relationship"))
        self.assertNotIn("merrow_star", shown(gm, "a hardship"))
        self.assertNotIn("merrow_star", shown(gm, ""))

    def test_a_phrase_key_matches(self):
        gm = GameManager()
        self.assertIn("bridges", shown(gm, "can I cross at ferry street?"))
        self.assertNotIn("bridges", shown(gm, "ferry"))

    def test_the_npc_keyed_rumour_shows_with_emma_only_once_discovered(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        self.assertEqual(gm.npcs["npc_emma"].current_location_id, "zone_building")
        self.assertNotIn("trial_rumour", shown(gm))
        discover(gm, "trial_rumour")
        self.assertIn("trial_rumour", shown(gm))
        gm.player.current_location_id = "zone_street"
        self.assertNotIn("trial_rumour", shown(gm))

    def test_a_constant_entry_shows_without_a_key_once_known(self):
        gm = GameManager()
        self.assertNotIn("power_out", shown(gm))
        discover(gm, "power_out")
        self.assertIn("power_out", shown(gm))

    def test_system_entries_are_never_world_hits(self):
        ids = shown(GameManager(), "Calder Ashby ship")
        self.assertFalse([i for i in ids if i.startswith("canon_")])

    def test_each_hit_is_logged_with_its_id_and_reason(self):
        gm = GameManager()
        with self.assertLogs("managers.story.lore", logging.DEBUG) as logs:
            select_lore(gm, "the ship", {})
        text = "\n".join(logs.output)
        self.assertIn("stage_news constant", text)
        self.assertIn("merrow_star key", text)

    def test_scores_are_ignored_for_now(self):
        gm = GameManager()
        hits = select_lore(gm, "", {"merrow_star": 0.99})
        self.assertNotIn("merrow_star", [h.entry.entry_id for h in hits])

    def test_selecting_changes_nothing(self):
        gm = GameManager()
        before = (set(gm.narrative.discovered_flags), dict(gm.narrative.flags))
        select_lore(gm, "ship", {})
        self.assertEqual((gm.narrative.discovered_flags, gm.narrative.flags), before)


class StageTests(unittest.TestCase):
    def test_exactly_one_stage_line_shows_at_every_minute(self):
        expected = [
            (0, "stage_news"),
            (2759, "stage_news"),
            (2760, "stage_broadcast"),
            (4259, "stage_broadcast"),
            (4260, "stage_evacuation"),
            (7019, "stage_evacuation"),
            (7020, "stage_cordon"),
            (11759, "stage_cordon"),
            (11760, "stage_loop"),
            (19380, "stage_loop"),
            (28920, "stage_loop"),
            (50000, "stage_loop"),
        ]

        for minute, stage_id in expected:
            with self.subTest(minute):
                gm = at_minute(minute)
                hits = select_lore(gm, "", {})
                stages = [h.entry.entry_id for h in hits if h.shown and h.entry.stage]
                self.assertEqual(stages, [stage_id])

    def test_a_stage_fired_by_a_long_gap_shows_the_latest_stage(self):
        gm = at_minute(9000)
        self.assertEqual(
            [h.entry.entry_id for h in select_lore(gm, "", {}) if h.entry.stage and h.shown],
            ["stage_cordon"],
        )

    def test_the_stage_line_is_first_in_the_block(self):
        gm = at_minute(0)
        lines = world_lines(select_lore(gm, "ship", {}))
        self.assertEqual(lines[0], get_lorebook().entries["stage_news"].content)


def entry(entry_id: str, order: int, content: str = "x", *, stage: bool = False) -> LoreEntry:
    return LoreEntry(
        entry_id=entry_id,
        content=content,
        position=Position.WORLD,
        constant=True,
        order=order,
        stage=stage,
    )


def hit(entry_id: str, order: int, reason: str = "constant", score: float = 0.0, **kw):
    return LoreHit(entry(entry_id, order, **kw), reason, score, True)  # pyright: ignore[reportArgumentType]


class DropOrderTests(unittest.TestCase):
    def test_the_highest_order_goes_first_ties_by_id_descending(self):
        hits = [hit("a", 10), hit("b", 50), hit("c", 50), hit("d", 30)]
        self.assertEqual([h.entry.entry_id for h in drop_order(hits)], ["c", "b", "d", "a"])

    def test_the_stage_entry_is_never_in_it(self):
        hits = [hit("stage", 0, stage=True), hit("a", 10)]
        self.assertEqual([h.entry.entry_id for h in drop_order(hits)], ["a"])

    def test_semantic_hits_go_first_worst_score_first(self):
        hits = [
            hit("key", 90),
            hit("good", 10, "semantic", 0.8),
            hit("poor", 5, "semantic", 0.4),
        ]
        self.assertEqual([h.entry.entry_id for h in drop_order(hits)], ["poor", "good", "key"])

    def test_a_hit_already_hidden_is_skipped(self):
        hidden = LoreHit(entry("gone", 99), "constant", 0.0, False)
        self.assertEqual(drop_order([hidden, hit("a", 1)])[0].entry.entry_id, "a")
        self.assertEqual(len(drop_order([hidden, hit("a", 1)])), 1)


class CapTests(unittest.TestCase):
    def test_over_the_cap_the_highest_order_goes_and_the_stage_stays(self):
        piece = "y" * 600
        entries = [
            entry("stage", 0, "s" * 100, stage=True),
            entry("low", 10, piece),
            entry("mid", 50, piece),
            entry("high", 80, piece),
        ]
        book = Lorebook({e.entry_id: e for e in entries})
        with mock.patch("managers.story.lore.get_lorebook", return_value=book):
            hits = select_lore(GameManager(), "", {})

        self.assertEqual([h.entry.entry_id for h in hits], ["stage", "low", "mid", "high"])
        self.assertEqual([h.shown for h in hits], [True, True, True, False])
        total = sum(len(line) for line in world_lines(hits))
        self.assertLessEqual(total, lore_k.WORLD_MAX_CHARS)

    def test_with_nothing_to_drop_only_the_stage_line_is_left(self):
        book = Lorebook({"stage": entry("stage", 0, "s" * 2000, stage=True)})
        with mock.patch("managers.story.lore.get_lorebook", return_value=book):
            hits = select_lore(GameManager(), "", {})
        self.assertTrue(hits[0].shown)

    def test_the_shipped_lorebook_fits_with_everything_keyed_at_once(self):
        gm = at_minute(40000)
        discover(gm, *known_ids().flags)
        words = " ".join(k for e in get_lorebook().world_entries() for k in e.keys)
        hits = select_lore(gm, words, {})
        self.assertLessEqual(sum(len(line) for line in world_lines(hits)), lore_k.WORLD_MAX_CHARS)


class SystemTextTests(unittest.TestCase):
    def test_system_text_joins_the_canon_in_order_with_single_spaces(self):
        book = get_lorebook()
        text = system_text(book)
        ordered = sorted(book.system_entries(), key=lambda e: (e.order, e.entry_id))
        self.assertEqual(text, " ".join(e.content for e in ordered))
        self.assertNotIn("\n", text)

    def test_the_truth_is_never_in_a_canon_entry(self):
        text = system_text(get_lorebook()).lower()
        for secret in ("velloran", "vx-7", "study", "binder"):
            self.assertNotIn(secret, text)


class StickyTests(unittest.TestCase):
    """world-lore: Sticky: a keyed entry stays on after its last trigger."""

    def turn(self, gm: GameManager, text: str = "") -> list[str]:
        hits = select_lore(gm, text, {})
        record_turn(gm, hits)
        return [hit.entry.entry_id for hit in hits if hit.shown]

    def ship_manager(self) -> GameManager:
        gm = GameManager()
        discover(gm, "apocalypse_cause")
        return gm

    def test_an_entry_shows_on_the_trigger_turn_and_the_turns_after_it(self):
        gm = self.ship_manager()
        stay = 3
        self.assertEqual(get_lorebook().entries["ship_story"].sticky, stay)
        seen = [
            "ship_story" in self.turn(gm, "the ship" if turn == 0 else "")
            for turn in range(stay + 2)
        ]
        self.assertEqual(seen, [True, True, True, True, False])
        self.assertEqual(gm.narrative.lore_sticky, {})

    def test_a_new_match_resets_the_count(self):
        gm = self.ship_manager()
        self.turn(gm, "the ship")
        self.turn(gm)
        self.turn(gm, "the ship")
        self.assertEqual(gm.narrative.lore_sticky["ship_story"], 3)
        self.assertTrue(all("ship_story" in self.turn(gm) for _ in range(3)))
        self.assertNotIn("ship_story", self.turn(gm))

    def test_a_replaced_entry_is_gone_at_once_and_leaves_the_state(self):
        gm = self.ship_manager()
        self.turn(gm, "the ship")
        self.assertIn("ship_story", gm.narrative.lore_sticky)
        discover(gm, "trial_truth")
        ids = self.turn(gm)
        self.assertNotIn("ship_story", ids)
        self.assertNotIn("ship_story", gm.narrative.lore_sticky)

    def test_an_entry_whose_condition_turned_false_leaves_the_state(self):
        gm = self.ship_manager()
        self.turn(gm, "the ship")
        gm.narrative.discovered_flags.clear()
        self.assertNotIn("ship_story", self.turn(gm))
        self.assertNotIn("ship_story", gm.narrative.lore_sticky)

    def test_a_locked_entry_never_shows_through_sticky(self):
        gm = GameManager()
        gm.narrative.lore_sticky["trial_truth"] = 5
        self.assertNotIn("trial_truth", [h.entry.entry_id for h in select_lore(gm, "", {})])
        record_turn(gm, [])
        self.assertEqual(gm.narrative.lore_sticky, {})

    def test_an_entry_the_cap_drops_still_counts_down(self):
        def keyed(entry_id: str, order: int) -> LoreEntry:
            return LoreEntry(
                entry_id, "y" * 1000, Position.WORLD, keys=("alpha",), order=order, sticky=3
            )

        book = Lorebook({"low": keyed("low", 10), "high": keyed("high", 80)})
        gm = GameManager()
        with mock.patch("managers.story.lore.get_lorebook", return_value=book):
            hits = select_lore(gm, "alpha", {})
            self.assertEqual([h.shown for h in hits], [True, False])
            record_turn(gm, hits)
            self.assertEqual(gm.narrative.lore_sticky, {"low": 3, "high": 3})
            record_turn(gm, select_lore(gm, "", {}))
        self.assertEqual(gm.narrative.lore_sticky, {"low": 2, "high": 2})

    def test_a_semantic_hit_starts_the_stay(self):
        gm = self.ship_manager()
        entry_ = get_lorebook().entries["ship_story"]
        record_turn(gm, [LoreHit(entry_, "semantic", 0.9)])
        self.assertEqual(gm.narrative.lore_sticky, {"ship_story": entry_.sticky})
        hits = select_lore(gm, "", {})
        self.assertEqual([h.reason for h in hits if h.entry is entry_], ["sticky"])

    def test_selecting_changes_nothing(self):
        gm = self.ship_manager()
        gm.narrative.lore_sticky["ship_story"] = 2
        select_lore(gm, "the ship", {})
        select_lore(gm, "", {})
        self.assertEqual(gm.narrative.lore_sticky, {"ship_story": 2})


class ContentTests(unittest.TestCase):
    def test_no_entry_holds_a_number(self):
        for e in get_lorebook().entries.values():
            self.assertFalse(holds_number(e.content), e.entry_id)

    def test_lore_text_says_ashby_fever_never_the_engines_name(self):
        for e in get_lorebook().entries.values():
            self.assertNotIn("zombie infection", e.content.lower(), e.entry_id)


if __name__ == "__main__":
    unittest.main()
