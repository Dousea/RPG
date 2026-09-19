"""GameManager: starting state, prompt assembly, action verbs, memory tiers."""

import unittest

from managers.game import MAX_RECENT_EVENTS, SUMMARY_THRESHOLD, GameManager


class StartingStateTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()

    def test_player_starts_in_the_hallway(self):
        self.assertEqual(self.gm.player.current_location_id, "location_id_hallway")

    def test_every_connection_points_at_a_real_location(self):
        # Regression: the Lobby was keyed 'location_id_hobby' while its id was
        # 'location_id_lobby', so the hallway's south exit led nowhere.
        for location in self.gm.world.locations.values():
            for direction, target in location.connections.items():
                self.assertIn(
                    target,
                    self.gm.world.locations,
                    f"{location.id} {direction} -> missing {target}",
                )

    def test_location_keys_match_their_ids(self):
        for key, location in self.gm.world.locations.items():
            self.assertEqual(key, location.id)

    def test_npc_roster_is_loaded_and_placed(self):
        self.assertEqual(len(self.gm.npcs), 3)
        for npc in self.gm.npcs.values():
            self.assertIn(npc.current_location_id, self.gm.world.locations)

    def test_starting_relationships_are_npc_towards_player(self):
        # Direction matters: every reader asks how the NPC regards the player,
        # so seeding the other way round would leave the values unreachable.
        self.assertEqual(
            self.gm.relationship_manager.get_trust("npc_emma", "player"), 5
        )
        # The prompt shows the band, never the number -- see the firewall tests.
        self.assertIn("trust: unformed", self.gm.build_prompt("look"))

    def test_two_games_do_not_share_mutable_state(self):
        # Locations and NPCs used to be module-level singletons, so a dropped
        # item or an NPC's status leaked into the next game after a reset.
        first = GameManager()
        first.apply_action("MOVE_TO north")
        first.apply_action("TAKE Crowbar")
        first.apply_action("NPC_STATUS Emma ADD frightened")

        second = GameManager()
        office = second.world.locations["location_id_office"]
        self.assertIn("Crowbar", [e.item.name for e in office.entities])
        self.assertEqual(second.resolve_npc("Emma").status, ["friendly", "curious about new neighbor"])
        self.assertEqual(second.player.inventory, [])


class PromptTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()

    def test_prompt_contains_every_section(self):
        prompt = self.gm.build_prompt("look around", ["Orton heard sirens."])
        for section in (
            "[CHARACTER]",
            "[DEEP MEMORY]",
            "[CURRENT LOCATION]",
            "[ITEMS IN CURRENT LOCATION]",
            "[NEARBY LOCATIONS]",
            "[NPCS PRESENT]",
            "[SUMMARY OF PAST EVENTS]",
            "[RECENT EVENTS]",
            "[SCENE]",
        ):
            self.assertIn(section, prompt)

    def test_prompt_carries_deep_memories(self):
        prompt = self.gm.build_prompt("look", ["Orton heard sirens."])
        self.assertIn("Orton heard sirens.", prompt)

    def test_prompt_describes_present_npcs_only(self):
        prompt = self.gm.build_prompt("look")
        self.assertIn("Emma", prompt)  # in the hallway with the player
        self.assertNotIn("Marcus", prompt)  # in the lobby

    def test_prompt_lists_exits_by_direction(self):
        self.assertIn("North: Office", self.gm.build_prompt("look"))

    def test_prompt_reflects_recent_events_and_summaries(self):
        self.assertIn("(No recent events)", self.gm.build_prompt("look"))
        self.gm.record_event("Orton locked the door.")
        self.gm.memory.summaries.append("The city grew quiet.")
        prompt = self.gm.build_prompt("look")
        self.assertIn("Orton locked the door.", prompt)
        self.assertIn("The city grew quiet.", prompt)


class KnowledgeFirewallTests(unittest.TestCase):
    """The prompt must not hand the game master numbers Orton cannot know."""

    def setUp(self):
        self.gm = GameManager()

    def _npcs_section(self) -> str:
        prompt = self.gm.build_prompt("look")
        return prompt.split("[NPCS PRESENT]")[1].split("[SUMMARY OF PAST EVENTS]")[0]

    def test_raw_relationship_scores_never_reach_the_prompt(self):
        self.gm.apply_action("UPDATE_RELATIONSHIP Emma affection +37")
        self.gm.apply_action("UPDATE_RELATIONSHIP Emma trust +42")
        section = self._npcs_section()

        self.assertIn("Emma", section)
        for leak in ("37", "42", "affection", "trust +"):
            self.assertNotIn(leak, section)

    def test_scores_are_reported_as_bands(self):
        self.gm.apply_action("UPDATE_RELATIONSHIP Emma affection +50")
        self.gm.apply_action("UPDATE_RELATIONSHIP Emma trust +45")
        self.assertIn("Disposition: friendly (trust: solid)", self.gm.build_prompt("look"))

    def test_bands_move_with_the_underlying_scores(self):
        self.assertIn("Disposition: neutral (trust: unformed)", self.gm.build_prompt("look"))
        self.gm.apply_action("UPDATE_RELATIONSHIP Emma affection -50")
        self.gm.apply_action("UPDATE_RELATIONSHIP Emma trust -45")
        self.assertIn("Disposition: hostile (trust: broken)", self.gm.build_prompt("look"))


class ActionTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()

    def assertAction(self, action: str):
        succeeded, message = self.gm.apply_action(action)
        self.assertTrue(succeeded, f"{action!r} failed: {message}")

    def assertActionRejected(self, action: str):
        succeeded, _ = self.gm.apply_action(action)
        self.assertFalse(succeeded, f"{action!r} should have been rejected")

    def test_move_by_direction_name_and_id(self):
        self.assertAction("MOVE_TO north")
        self.assertEqual(self.gm.player.current_location_id, "location_id_office")
        self.assertAction("MOVE_TO Hallway")
        self.assertEqual(self.gm.player.current_location_id, "location_id_hallway")
        self.assertAction("MOVE_TO location_id_lobby")
        self.assertEqual(self.gm.player.current_location_id, "location_id_lobby")

    def test_move_to_unknown_location_is_rejected(self):
        self.assertActionRejected("MOVE_TO Atlantis")
        self.assertEqual(self.gm.player.current_location_id, "location_id_hallway")

    def test_take_and_drop_round_trip(self):
        self.assertAction("MOVE_TO north")
        self.assertAction("TAKE Crowbar")
        self.assertEqual([e.item.name for e in self.gm.player.inventory], ["Crowbar"])
        # Gone from the floor, so taking it again fails.
        self.assertActionRejected("TAKE Crowbar")
        self.assertAction("DROP Crowbar")
        self.assertEqual(self.gm.player.inventory, [])
        self.assertIn("Crowbar", [e.item.name for e in self.gm.current_location.entities])

    def test_item_names_are_case_insensitive(self):
        self.assertAction("MOVE_TO north")
        self.assertAction("TAKE crowbar")

    def test_take_is_rejected_when_inventory_is_full(self):
        self.gm.player.max_inventory_size = 0
        self.assertAction("MOVE_TO north")
        self.assertActionRejected("TAKE Crowbar")

    def test_update_condition_sets_and_adjusts(self):
        self.assertAction("UPDATE_CONDITION hunger 80")
        self.assertEqual(self.gm.player.hunger, 80)
        self.assertAction("UPDATE_CONDITION hunger -30")
        self.assertEqual(self.gm.player.hunger, 50)
        self.assertAction("UPDATE_CONDITION hunger +10")
        self.assertEqual(self.gm.player.hunger, 60)

    def test_update_condition_clamps_percentages(self):
        self.assertAction("UPDATE_CONDITION morale -500")
        self.assertEqual(self.gm.player.morale, 0)
        self.assertAction("UPDATE_CONDITION morale +500")
        self.assertEqual(self.gm.player.morale, 100)

    def test_update_condition_accepts_narrative_fields(self):
        self.assertAction("UPDATE_CONDITION sleep Exhausted")
        self.assertEqual(self.gm.narrative.conditions["sleep"], "Exhausted")

    def test_update_condition_rejects_junk(self):
        self.assertActionRejected("UPDATE_CONDITION hunger lots")
        self.assertActionRejected("UPDATE_CONDITION charisma 5")

    def test_health_clamps_to_max_hit_points(self):
        self.assertAction("UPDATE_CONDITION health 9999")
        self.assertEqual(self.gm.player.hit_points, self.gm.player.max_hit_points)

    def test_relationship_axes_move_independently(self):
        self.assertAction("UPDATE_RELATIONSHIP Emma affection +12")
        self.assertAction("UPDATE_RELATIONSHIP Emma trust -2")
        manager = self.gm.relationship_manager
        self.assertEqual(manager.get_affinity("npc_emma", "player"), 12)
        self.assertEqual(manager.get_trust("npc_emma", "player"), 3)  # seeded at 5

    def test_relationship_is_clamped(self):
        self.assertAction("UPDATE_RELATIONSHIP Emma affection +500")
        self.assertEqual(
            self.gm.relationship_manager.get_affinity("npc_emma", "player"), 100
        )

    def test_relationship_with_unknown_npc_is_rejected(self):
        self.assertActionRejected("UPDATE_RELATIONSHIP Nobody affection +1")

    def test_goals_add_and_remove(self):
        self.assertAction("ADD_GOAL short_term Find a weapon")
        self.assertIn("Find a weapon", self.gm.narrative.goals["short_term"])
        self.assertAction("REMOVE_GOAL short_term Find a weapon")
        self.assertEqual(self.gm.narrative.goals["short_term"], [])
        self.assertActionRejected("ADD_GOAL someday Find a weapon")

    def test_flags(self):
        self.assertAction("SET_FLAG power_grid_stable false")
        self.assertIs(self.gm.narrative.flags["power_grid_stable"], False)
        self.assertActionRejected("SET_FLAG power_grid_stable maybe")

    def test_time_advance_rolls_the_day_over(self):
        self.assertAction("TIME_ADVANCE evening")
        self.assertEqual(self.gm.narrative.day, 1)
        self.assertAction("TIME_ADVANCE morning")
        self.assertEqual(self.gm.narrative.day, 2)
        self.assertActionRejected("TIME_ADVANCE teatime")

    def test_time_advance_to_the_same_part_of_day_keeps_the_day(self):
        # Regression: the wrap check was `<=`, so re-declaring the current part
        # of the day silently pushed the calendar forward.
        self.assertEqual(self.gm.narrative.time_of_day, "morning")
        self.assertAction("TIME_ADVANCE morning")
        self.assertEqual(self.gm.narrative.day, 1)
        self.assertAction("TIME_ADVANCE night")
        self.assertAction("TIME_ADVANCE night")
        self.assertEqual(self.gm.narrative.day, 1)

    def test_world_clock_follows_the_narrative_clock(self):
        # Regression: nothing ever wrote World.time/date, so the prompt claimed
        # noon on 1 October 2023 for the entire game.
        self.assertEqual(self.gm.world.time, "08:00 AM")
        self.assertEqual(self.gm.world.date, "2023-10-01")

        self.assertAction("TIME_ADVANCE evening")
        self.assertEqual(self.gm.world.time, "07:00 PM")
        self.assertEqual(self.gm.world.date, "2023-10-01")

        self.assertAction("TIME_ADVANCE morning")  # rolls over into day 2
        self.assertEqual(self.gm.world.time, "08:00 AM")
        self.assertEqual(self.gm.world.date, "2023-10-02")

    def test_world_clock_agrees_with_the_narrative_clock_in_the_prompt(self):
        self.assertAction("TIME_ADVANCE evening")
        prompt = self.gm.build_prompt("look")
        self.assertIn("Day 1, Evening -- 07:00 PM, 2023-10-01", prompt)

    def test_status_maps_onto_simulated_conditions(self):
        self.assertAction("STATUS_ADD panic")
        self.assertIn("panic", [c.value for c in self.gm.player.conditions])
        self.assertAction("STATUS_REMOVE panic")
        self.assertEqual(self.gm.player.conditions, [])

    def test_free_text_status_is_narrative_only(self):
        self.assertAction("STATUS_ADD settled in")
        self.assertIn("settled in", self.gm.narrative.player_status)
        self.assertEqual(self.gm.player.conditions, [])

    def test_npc_move_and_status(self):
        self.assertAction("NPC_MOVE Emma TO Lobby")
        self.assertEqual(
            self.gm.resolve_npc("Emma").current_location_id, "location_id_lobby"
        )
        self.assertAction("NPC_STATUS Emma ADD frightened")
        self.assertIn("frightened", self.gm.resolve_npc("Emma").status)
        self.assertAction("NPC_STATUS Emma REMOVE frightened")
        self.assertNotIn("frightened", self.gm.resolve_npc("Emma").status)

    def test_npc_move_needs_the_to_separator(self):
        self.assertActionRejected("NPC_MOVE Emma Lobby")

    def test_relationship_notes_accumulate(self):
        self.assertAction("ADD_RELATIONSHIP_NOTE Emma Seemed shaken")
        self.assertAction("ADD_RELATIONSHIP_NOTE Emma Offered coffee")
        notes = self.gm.resolve_npc("Emma").notes
        self.assertIn("Seemed shaken", notes)
        self.assertIn("Offered coffee", notes)

    def test_update_inventory_add_and_remove(self):
        self.assertAction("UPDATE_INVENTORY First Aid Kit ADD 1")
        self.assertIn("First Aid Kit", [e.item.name for e in self.gm.player.inventory])
        self.assertAction("UPDATE_INVENTORY First Aid Kit REMOVE 1")
        self.assertEqual(self.gm.player.inventory, [])

    def test_update_inventory_quantity_adjusts_entity_count(self):
        self.assertAction("UPDATE_INVENTORY Canned Beans ADD 1")
        self.assertAction("UPDATE_INVENTORY Canned Beans UPDATE_QUANTITY 3")
        beans = [e for e in self.gm.player.inventory if e.item.name == "Canned Beans"]
        self.assertEqual(len(beans), 3)
        self.assertAction("UPDATE_INVENTORY Canned Beans UPDATE_QUANTITY 1")
        beans = [e for e in self.gm.player.inventory if e.item.name == "Canned Beans"]
        self.assertEqual(len(beans), 1)

    def test_update_inventory_condition(self):
        self.assertAction("UPDATE_INVENTORY Canned Beans ADD 1")
        self.assertAction("UPDATE_INVENTORY Canned Beans UPDATE_CONDITION 2")
        self.assertEqual(self.gm.player.inventory[0].hit_points, 2)

    def test_update_inventory_rejects_unknown_item(self):
        self.assertActionRejected("UPDATE_INVENTORY Plasma Rifle ADD 1")

    def test_unknown_verb_is_rejected_not_raised(self):
        self.assertActionRejected("FROBNICATE the widget")

    def test_none_and_blank_are_no_ops(self):
        for action in ("NONE", "", "   "):
            succeeded, _ = self.gm.apply_action(action)
            self.assertTrue(succeeded)

    def test_leading_bullet_is_tolerated(self):
        # Models habitually emit "- TAKE x" despite the format instructions.
        self.assertAction("MOVE_TO north")
        self.assertAction("- TAKE Crowbar")

    def test_malformed_action_never_raises(self):
        for action in (
            "UPDATE_RELATIONSHIP",
            "NPC_STATUS ADD",
            "UPDATE_INVENTORY",
            "SET_FLAG",
            "ADD_GOAL",
        ):
            succeeded, message = self.gm.apply_action(action)
            self.assertFalse(succeeded)
            self.assertTrue(message)


class MemoryTests(unittest.TestCase):
    def setUp(self):
        self.gm = GameManager()

    def test_recent_buffer_is_capped_and_newest_first(self):
        for i in range(MAX_RECENT_EVENTS + 3):
            self.gm.record_event(f"Event {i}")
        self.assertEqual(len(self.gm.memory.recent_events), MAX_RECENT_EVENTS)
        self.assertEqual(self.gm.memory.recent_events[0], f"Event {MAX_RECENT_EVENTS + 2}")

    def test_full_log_keeps_everything(self):
        for i in range(20):
            self.gm.record_event(f"Event {i}")
        self.assertEqual(len(self.gm.memory.full_event_log), 20)

    def test_empty_events_are_ignored(self):
        self.gm.record_event("")
        self.assertEqual(self.gm.memory.full_event_log, [])

    def test_summary_batches_appear_once_the_threshold_is_crossed(self):
        for i in range(SUMMARY_THRESHOLD - 1):
            self.gm.record_event(f"Event {i}")
        self.assertEqual(self.gm.events_pending_summary(), [])

        self.gm.record_event("One more")
        self.assertEqual(len(self.gm.events_pending_summary()), SUMMARY_THRESHOLD)

        # Once summarized, the same batch is not offered again.
        self.gm.memory.summaries.append("A summary.")
        self.assertEqual(self.gm.events_pending_summary(), [])


if __name__ == "__main__":
    unittest.main()
