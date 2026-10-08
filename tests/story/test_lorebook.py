"""world-lore: The lorebook: the file, conditions in JSON, loading and validation."""

import json
import tempfile
import unittest
from pathlib import Path
from typing import Any

from data.story import lore as lore_k
from managers.story.lorebook import (
    LorebookError,
    get_lorebook,
    known_ids,
    load_lorebook,
    validate_entries,
)
from modules.story.beats import (
    AllOf,
    BeatFiredAgo,
    ClockAtOrPast,
    FlagDiscovered,
    ItemHeld,
    OutbreakStarted,
    PlayerInZone,
)
from modules.story.lore import LoreFormatError, Position, parse_condition, parse_entry

CANON_IDS = [
    "canon_city",
    "canon_neighbourhood",
    "canon_shops",
    "canon_hospital",
    "canon_no_rescue",
    "canon_offmap",
    "canon_cause",
]


def keyed(entry_id: str = "e", **fields: Any) -> dict[str, Any]:
    return {
        "id": entry_id,
        "content": "Something people say.",
        "keys": ["word"],
        "position": "world",
        **fields,
    }


def constant(entry_id: str = "c", **fields: Any) -> dict[str, Any]:
    return {
        "id": entry_id,
        "content": "Something true.",
        "constant": True,
        "position": "world",
        **fields,
    }


def system(entry_id: str = "s", **fields: Any) -> dict[str, Any]:
    return constant(entry_id, position="system", **fields)


def load_raw(*entries: dict[str, Any]):
    entries_list = [parse_entry(raw) for raw in entries]
    return validate_entries(entries_list, known_ids())


class ShippedFileTests(unittest.TestCase):
    def test_the_shipped_file_loads_and_its_system_entries_are_the_canon_in_order(self):
        book = get_lorebook()
        system_entries = sorted(book.system_entries(), key=lambda e: (e.order, e.entry_id))
        self.assertEqual([e.entry_id for e in system_entries], CANON_IDS)
        self.assertEqual([e.order for e in system_entries], [10, 20, 30, 40, 50, 60, 70])
        self.assertEqual(lore_k.WORLD_MAX_CHARS, 1800)
        self.assertEqual(lore_k.SYSTEM_MAX_CHARS, 1200)
        self.assertEqual(lore_k.ENTRY_MAX_CHARS, 300)
        self.assertEqual(lore_k.STICKY_MAX_TURNS, 10)
        self.assertEqual(lore_k.LORE_SEMANTIC_MAX, 2)
        self.assertEqual(lore_k.LORE_SEMANTIC_MIN_SCORE, 0.35)

    def test_it_is_cached(self):
        self.assertIs(get_lorebook(), get_lorebook())


class ConditionTests(unittest.TestCase):
    def test_each_json_condition_parses_to_its_dataclass(self):
        cases: list[tuple[dict[str, Any], Any]] = [
            ({"clock": 4260}, ClockAtOrPast(4260)),
            ({"clock": 0}, ClockAtOrPast(0)),
            ({"zone": "zone_clinic"}, PlayerInZone("zone_clinic")),
            ({"flag": "cordon"}, FlagDiscovered("cordon")),
            ({"outbreak": True}, OutbreakStarted()),
            ({"beat": "cordon"}, BeatFiredAgo("cordon", 0)),
            ({"beat": "cordon", "minutes": 30}, BeatFiredAgo("cordon", 30)),
            ({"item": "item_study_binder"}, ItemHeld("item_study_binder")),
        ]
        for raw, expected in cases:
            with self.subTest(raw):
                self.assertEqual(parse_condition(raw), expected)

    def test_all_nests(self):
        raw = {"all": [{"flag": "a"}, {"all": [{"outbreak": True}, {"clock": 5}]}]}
        self.assertEqual(
            parse_condition(raw),
            AllOf((FlagDiscovered("a"), AllOf((OutbreakStarted(), ClockAtOrPast(5))))),
        )

    def test_bad_shapes_raise(self):
        bad: list[Any] = [
            {},
            {"flag": "a", "clock": 1},
            {"unknown": 1},
            {"clock": -1},
            {"clock": "5"},
            {"clock": True},
            {"outbreak": False},
            {"flag": 3},
            {"beat": "cordon", "minutes": -1},
            {"beat": "cordon", "minutes": 1.5},
            {"minutes": 30},
            {"all": []},
            {"all": "flag"},
            {"all": [{"bogus": 1}]},
            "flag",
        ]

        for raw in bad:
            with self.subTest(raw), self.assertRaises(LoreFormatError):
                parse_condition(raw)


class ParseEntryTests(unittest.TestCase):
    def test_every_field_lands_on_the_entry(self):
        entry = parse_entry(
            keyed(
                "full",
                comment="note",
                order=45,
                when={"flag": "cordon"},
                replaced_by="other",
                sticky=3,
                semantic=False,
            )
        )

        self.assertEqual(entry.entry_id, "full")
        self.assertEqual(entry.position, Position.WORLD)
        self.assertEqual(entry.keys, ("word",))
        self.assertEqual(entry.order, 45)
        self.assertEqual(entry.when, FlagDiscovered("cordon"))
        self.assertEqual(entry.replaced_by, "other")
        self.assertEqual(entry.sticky, 3)
        self.assertFalse(entry.semantic)
        self.assertEqual(entry.comment, "note")
        self.assertFalse(entry.constant)
        self.assertFalse(entry.stage)

    def test_defaults(self):
        entry = parse_entry(constant("plain"))
        self.assertEqual(
            (entry.keys, entry.order, entry.when, entry.replaced_by, entry.sticky, entry.semantic),
            ((), 0, None, None, None, True),
        )

    def test_bad_shapes_raise(self):
        bad: list[dict[str, Any]] = [
            keyed(extra=1),
            {k: v for k, v in keyed().items() if k != "id"},
            {k: v for k, v in keyed().items() if k != "content"},
            {k: v for k, v in keyed().items() if k != "position"},
            keyed(position="hall"),
            keyed(keys="word"),
            keyed(keys=[1]),
            keyed(order="3"),
            keyed(order=True),
            keyed(constant="yes"),
            keyed(sticky="3"),
            keyed(when={"flag": 1}),
            keyed(content=5),
            keyed(replaced_by=4),
        ]

        for raw in bad:
            with self.subTest(raw), self.assertRaises(LoreFormatError):
                parse_entry(raw)

    def test_semantic_on_a_constant_or_system_entry_raises(self):
        for raw in (constant(semantic=True), system(semantic=False), constant(semantic=False)):
            with self.subTest(raw), self.assertRaises(LoreFormatError):
                parse_entry(raw)


class ValidationTests(unittest.TestCase):
    def assert_rejected(self, entry_id: str, *entries: dict[str, Any]):
        with self.assertRaises(LorebookError) as caught:
            load_raw(*entries)
        self.assertIn(entry_id, str(caught.exception))

    def test_good_entries_pass(self):
        book = load_raw(
            keyed("a", when={"flag": "cordon"}, replaced_by="b", sticky=10),
            keyed("b", keys=["zone_clinic", "npc_jen", "Ferry Street"], semantic=False),
            system("s"),
        )
        self.assertEqual(sorted(book.entries), ["a", "b", "s"])

    def test_a_duplicate_id(self):
        self.assert_rejected("dup", keyed("dup"), keyed("dup"))

    def test_replaced_by_nothing_itself_or_a_cycle(self):
        self.assert_rejected("a", keyed("a", replaced_by="ghost"))
        self.assert_rejected("a", keyed("a", replaced_by="a"))
        self.assert_rejected("a", keyed("a", replaced_by="b"), keyed("b", replaced_by="a"))

    def test_an_unknown_id_in_a_condition_or_key(self):
        cases = [
            {"when": {"flag": "never_set"}},
            {"when": {"beat": "never_fires"}},
            {"when": {"item": "item_nothing"}},
            {"when": {"zone": "zone_moon"}},
            {"when": {"all": [{"flag": "cordon"}, {"flag": "never_set"}]}},
            {"keys": ["zone_moon"]},
            {"keys": ["npc_nobody"]},
            {"keys": [" "]},
            {"keys": [""]},
        ]
        for fields in cases:
            with self.subTest(fields):
                self.assert_rejected("bad", keyed("bad", **fields))

    def test_a_system_entry_with_anything_that_would_change_the_prompt_prefix(self):
        for fields in (
            {"when": {"outbreak": True}},
            {"keys": ["word"]},
            {"sticky": 3},
            {"replaced_by": "other"},
            {"stage": True},
            {"constant": False},
        ):
            with self.subTest(fields):
                self.assert_rejected("bad", system("bad", **fields), constant("other"))

    def test_a_world_entry_that_could_never_show_or_is_confused(self):
        self.assert_rejected("bad", constant("bad", keys=["word"]))
        self.assert_rejected("bad", keyed("bad", keys=[]))
        self.assert_rejected("bad", keyed("bad", stage=True))

    def test_sticky_must_be_one_to_ten_on_a_keyed_entry(self):
        self.assert_rejected("bad", keyed("bad", sticky=0))
        self.assert_rejected("bad", keyed("bad", sticky=lore_k.STICKY_MAX_TURNS + 1))
        self.assert_rejected("bad", constant("bad", sticky=3))
        load_raw(keyed("ok", sticky=1), keyed("ok2", sticky=lore_k.STICKY_MAX_TURNS))

    def test_a_number_in_content_but_not_a_name_that_holds_one(self):
        self.assert_rejected("bad", keyed("bad", content="It began on day 3."))
        self.assert_rejected("bad", keyed("bad", content="About 12 of them."))
        load_raw(keyed("ok", content="The drug VX-7 and a 3rd floor."))

    def test_keys_may_hold_digits(self):
        load_raw(keyed("ok", keys=["VX-7", "route 9"]))

    def test_content_length(self):
        self.assert_rejected("bad", keyed("bad", content="x" * (lore_k.ENTRY_MAX_CHARS + 1)))
        load_raw(keyed("ok", content="x" * lore_k.ENTRY_MAX_CHARS))

    def test_system_content_totals(self):
        half = "x" * (lore_k.SYSTEM_MAX_CHARS // 5 + 1)
        entries = [system(f"s{i}", content=half) for i in range(5)]
        with self.assertRaises(LorebookError):
            load_raw(*entries)
        load_raw(*entries[:4])


class FileTests(unittest.TestCase):
    def load_text(self, text: str):
        with tempfile.TemporaryDirectory() as folder:
            path = Path(folder) / "lorebook.json"
            path.write_text(text, encoding="utf-8")
            return load_lorebook(path, known_ids())

    def test_a_file_that_is_not_json(self):
        with self.assertRaises(LorebookError):
            self.load_text("not json")

    def test_a_file_that_is_not_an_entries_object(self):
        for text in (
            "[]",
            '{"entries": 3}',
            '{"entries": [], "extra": 1}',
            "{}",
            '{"entries": [3]}',
        ):
            with self.subTest(text), self.assertRaises(LorebookError):
                self.load_text(text)

    def test_a_bad_entry_is_named(self):
        text = json.dumps({"entries": [keyed("oops", extra=1)]})
        with self.assertRaisesRegex(LorebookError, "oops"):
            self.load_text(text)

    def test_a_good_file_loads(self):
        book = self.load_text(json.dumps({"entries": [keyed("a"), system("s")]}))
        self.assertEqual(sorted(book.entries), ["a", "s"])


if __name__ == "__main__":
    unittest.main()
