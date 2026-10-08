"""llm-contract: The `@` list: what the player can pin to a turn, and in what words."""

import re
import unittest
from typing import cast

from data.items import ITEMS
from managers.game import GameManager
from managers.mentions import labels, mentionables, picked
from managers.story.beats import visible_topics
from managers.zombies.population import threat_views
from modules.action.pins import Mention
from modules.body.parts import BodyPart
from modules.entity.corpse import CorpseEntity
from modules.entity.item import ItemEntity
from modules.entity.zombie import ZombieState
from modules.item import ClothingItem
from tests.test_simulation import add_zombie, zombie_game


def kinds(mentions: list[Mention], kind: str) -> list[Mention]:
    return [m for m in mentions if m.kind == kind]


def ids(mentions: list[Mention], kind: str) -> list[str]:
    return [m.id for m in kinds(mentions, kind)]


class MentionListTests(unittest.TestCase):
    """llm-contract: What can be mentioned."""

    def test_seen_zombies_are_listed_with_distance_and_state_words(self):
        gm = zombie_game()
        near = add_zombie(gm, gap=3, state=ZombieState.CHASING)
        far = add_zombie(gm, gap=12)
        zombies = kinds(mentionables(gm), "zombie")
        self.assertEqual([z.id for z in zombies], [near.zombie_id, far.zombie_id])
        self.assertEqual(zombies[0].name, "man")
        self.assertEqual(zombies[0].description, "close, coming at you")
        self.assertEqual(zombies[1].description, "nearby, hasn't noticed you")

    def test_a_zombie_only_heard_is_not_listed(self):
        gm = zombie_game("zone_street")
        gm.world.barriers["door_lobby"].open = False
        heard = add_zombie(gm, "zone_building", gap=3, state=ZombieState.THUMPING)
        heard.thump_barrier = "door_lobby"
        self.assertTrue(threat_views(gm))
        self.assertEqual(ids(mentionables(gm), "zombie"), [])

    def test_zombies_in_the_same_outer_garment_get_another_garment_then_the_state_words(self):
        gm = zombie_game()
        jacket = ItemEntity(item=ITEMS["item_jacket_police"])
        jeans = ItemEntity(item=ITEMS["item_jeans"])
        shirt = ItemEntity(item=ITEMS["item_tshirt"])
        first = add_zombie(gm, gap=3, state=ZombieState.CHASING)
        second = add_zombie(gm, gap=3, state=ZombieState.CHASING)
        third = add_zombie(gm, gap=12)
        for zombie, worn in (
            (first, [jacket, jeans]),
            (second, [jacket, shirt]),
            (third, [jacket]),
        ):
            zombie.worn = {cast(ClothingItem, w.item).body_location: w for w in worn}
        names = [m.name for m in kinds(mentionables(gm), "zombie")]
        self.assertEqual(len(names), 3)
        self.assertEqual(len(set(names[:2])), 2)
        self.assertTrue(all("police jacket" in n for n in names))
        for mention in mentionables(gm):
            self.assertNotRegex(mention.name + mention.description, r"\bz\d+\b")

    def test_corpses_are_listed_by_their_scene_words(self):
        gm = zombie_game()
        gm.world.corpses["c1"] = CorpseEntity(
            corpse_id="c1",
            zone_id="zone_street",
            gap=3.0,
            female=False,
            outfit="generic01",
            died_at=0,
            rot_at_death=1,
        )
        (body,) = kinds(mentionables(gm), "corpse")
        self.assertEqual((body.id, body.name), ("c1", "man"))
        self.assertIn("close", body.description)
        self.assertIn("not searched", body.description)

    def test_bare_bones_are_listed_without_a_sex(self):
        gm = zombie_game()
        gm.world.corpses["c1"] = CorpseEntity(
            corpse_id="c1",
            zone_id="zone_street",
            gap=3.0,
            female=True,
            outfit="generic01",
            died_at=0,
            rot_at_death=1,
            skeleton=True,
        )
        (body,) = kinds(mentionables(gm), "corpse")
        self.assertEqual(body.name, "bare bones")
        self.assertNotRegex(body.name, "man|woman")

    def test_entries_that_still_read_alike_get_the_numbered_label_the_pick_will_show(self):
        gm = zombie_game()
        add_zombie(gm, gap=3, state=ZombieState.CHASING)
        add_zombie(gm, gap=4, state=ZombieState.CHASING)
        gm.world.corpses["c1"] = CorpseEntity(
            corpse_id="c1",
            zone_id="zone_street",
            gap=3.0,
            female=False,
            outfit="generic01",
            died_at=0,
            rot_at_death=1,
        )
        listed = mentionables(gm)
        shown = labels(listed)
        alike = [label for m, label in zip(listed, shown, strict=True) if m.name == "man"]
        self.assertEqual(alike, ["man #1", "man #2", "man #3"])
        for m, label in zip(listed, shown, strict=True):
            if m.name != "man":
                self.assertEqual(label, m.name)

    def test_npcs_in_the_zone_are_listed_and_topics_are_not(self):
        gm = GameManager()
        gm.player.current_location_id = "zone_building"
        listed = mentionables(gm)
        here = {n.npc_id: n for n in gm.npcs_in_location(gm.player.current_location_id)}
        self.assertEqual(set(ids(listed, "npc")), set(here))
        self.assertTrue(here)
        topic_ids = {topic.topic_id for npc in here.values() for topic in visible_topics(gm, npc)}
        self.assertFalse(topic_ids & {m.id for m in listed})

    def test_the_barriers_of_the_zones_connections_are_listed_with_state_and_zones(self):
        gm = zombie_game("zone_neighborhood")
        window = gm.world.barriers["window_supermarket"]
        window.open = False
        window.locked = False
        listed = {m.id: m for m in kinds(mentionables(gm), "barrier")}
        self.assertEqual(
            set(listed),
            {"window_pharmacy", "door_clinic", "window_supermarket", "door_hardware"},
        )
        self.assertEqual(listed["window_supermarket"].name, "supermarket window")
        self.assertEqual(
            listed["window_supermarket"].description,
            "closed, between The Neighborhood and The Supermarket",
        )

    def test_rooms_and_containers_say_where_the_player_is_and_what_is_opened(self):
        gm = GameManager()
        gm.player.current_room = "kitchen"
        listed = mentionables(gm)
        rooms = {m.id: m for m in kinds(listed, "room")}
        self.assertEqual(set(rooms), set(gm.current_location.rooms))
        self.assertEqual(rooms["kitchen"].description, "you are here")
        self.assertEqual(rooms["bedroom"].description, "not where you are")
        fridge = next(m for m in kinds(listed, "container") if m.name == "fridge")
        self.assertEqual(fridge.description, "in the kitchen, not opened")
        gm.current_location.rooms["kitchen"].containers[2].opened = True
        again = next(m for m in kinds(mentionables(gm), "container") if m.name == "fridge")
        self.assertEqual(again.description, "in the kitchen, opened")

    def test_every_zone_zone_path_reaches_is_listed_with_how_it_connects(self):
        gm = zombie_game("zone_street")
        gm.world.barriers["window_bodega"].open = False
        gm.world.barriers["window_bodega"].locked = False
        zones = {m.id: m for m in kinds(mentionables(gm), "zone")}
        self.assertNotIn("zone_street", zones)
        self.assertEqual(zones["zone_building"].description, "in")
        self.assertEqual(zones["zone_neighborhood"].description, "out")
        self.assertEqual(
            zones["zone_bodega"].description, "store, blocked by the shop window (closed)"
        )
        self.assertEqual(zones["zone_pharmacy"].description, "via The Neighborhood")
        self.assertEqual(zones["zone_home"].description, "via Your Building")
        self.assertEqual(zones["zone_bodega"].name, "The Corner Store")

    def test_a_zone_zone_path_cannot_reach_is_not_listed(self):
        gm = zombie_game("zone_street")
        gm.world.locations["zone_island"] = gm.world.locations["zone_bodega"].__class__(
            id="zone_island", name="The Island", description="", connections={}
        )
        self.assertNotIn("zone_island", ids(mentionables(gm), "zone"))

    def test_hurt_and_bandaged_parts_are_listed_with_their_words(self):
        gm = GameManager()
        gm.player.body[BodyPart.HAND_L].scratch_time = 10.0
        gm.player.body[BodyPart.HEAD].bandage = "bandage"
        gm.player.body[BodyPart.HEAD].bandage_life = 5.0
        gm.player.body[BodyPart.HEAD].scratch_time = 0.0
        parts = {m.id: m for m in kinds(mentionables(gm), "body_part")}
        self.assertEqual(parts["hand_l"].name, "left hand")
        self.assertEqual(parts["hand_l"].description, "scratch")
        self.assertEqual(parts["head"].description, "bandaged")

    def test_no_description_carries_a_digit_and_items_are_never_listed(self):
        gm = zombie_game("zone_neighborhood")
        add_zombie(gm, gap=3, state=ZombieState.CHASING)
        gm.player.body[BodyPart.HAND_L].scratch_time = 10.0
        for mention in mentionables(gm):
            self.assertNotRegex(mention.description, r"\d", mention)
        self.assertEqual(
            {m.kind for m in mentionables(gm)},
            {"zombie", "npc", "barrier", "zone", "body_part"},
        )
        self.assertFalse(re.search("item_", " ".join(m.id for m in mentionables(gm))))


class ReachTests(unittest.TestCase):
    """llm-contract: A mention is checked against what is in reach before the parser runs."""

    def test_listed_ids_come_back_in_the_order_given(self):
        gm = zombie_game()
        first = add_zombie(gm, gap=3, state=ZombieState.CHASING)
        second = add_zombie(gm, gap=4, state=ZombieState.CHASING)
        found, gone = picked(gm, [second.zombie_id, first.zombie_id])
        self.assertEqual([m.id for m in found], [second.zombie_id, first.zombie_id])
        self.assertEqual(gone, [])

    def test_a_zombie_that_moved_off_is_gone(self):
        gm = zombie_game()
        zombie = add_zombie(gm, gap=3, state=ZombieState.CHASING)
        zombie.zone_id = "zone_building"
        self.assertEqual(picked(gm, [zombie.zombie_id]), ([], [zombie.zombie_id]))


if __name__ == "__main__":
    unittest.main()
