"""llm-contract: Memory and Plans: the turn runs a plan's legs, with one more parse at a zone change.

The leg planner is scripted: it returns the checked leg a test prepares, so no LLM stands behind it.
"""

import random
import unittest
from collections.abc import Sequence
from dataclasses import replace
from typing import Any

from data.items import ITEMS
from data.story.mentions import REST_NOT_REACHED_FACT
from data.time_costs import MAX_PLAN_ACTIONS
from managers.context import NOTHING_DONE_FACT
from managers.game import GameManager
from managers.simulation import Leg, SimulationCore
from managers.turn import CheckedLeg, TurnOutcome, run_turn
from modules.action.pins import Mention, Pinned
from modules.action.types import (
    AddGoalAction,
    AnyAction,
    DropAction,
    Duration,
    MoveAction,
    SearchAction,
    ShoutAction,
    TakeAction,
    WaitAction,
)
from modules.action.words import describe_action
from modules.entity.item import ItemEntity
from tests.support import checked_leg, make_dying, turn_of

REST = REST_NOT_REACHED_FACT.format(name="Orton")
NOTHING = NOTHING_DONE_FACT.format(name="Orton")


UNREADABLE: dict[str, Any] = {"failures": ["Refused: nonsense."]}
DROPPED: dict[str, Any] = {"dropped": [(0, TakeAction(item_name="knife"), "Not asked for.")]}


def goal(text: str) -> AddGoalAction:
    return AddGoalAction(horizon="short_term", goal_text=text)


class Planner:
    """A leg planner that answers each call with the next checked leg it holds (None once it has none) and records its calls."""

    def __init__(self, *legs: CheckedLeg | None):
        self._legs = list(legs)
        self.calls: list[tuple[list[str], list[Mention]]] = []

    def __call__(self, done: Sequence[str], picks: Sequence[Mention]) -> CheckedLeg | None:
        self.calls.append((list(done), list(picks)))
        return self._legs.pop(0) if self._legs else None


def planning(*actions: AnyAction) -> Planner:
    return Planner(checked_leg(actions))


def run(
    gm: GameManager,
    actions: Sequence[AnyAction],
    planner: Planner | None = None,
    **leg: Any,
) -> TurnOutcome:
    return turn_of(SimulationCore(gm, rng=random.Random(1)), actions, planner, **leg)


def street() -> GameManager:
    gm = GameManager()
    gm.player.current_location_id = "zone_street"
    return gm


class LegLoopTests(unittest.TestCase):
    def test_a_zone_change_with_nothing_after_it_still_plans_the_next_leg(self):
        gm = GameManager()
        planner = planning(goal("Ask Marcus"))

        outcome = run(gm, [MoveAction(destination="out")], planner)

        self.assertEqual(len(planner.calls), 1)
        self.assertEqual(gm.narrative.goals["short_term"], ["Ask Marcus"])
        self.assertNotIn(REST, outcome.narrated)

    def test_the_planner_gets_what_the_turn_did_in_words_earlier_runs_first(self):
        move = MoveAction(destination="out")
        earlier = goal("Earlier")
        planner = planning(goal("Next"))

        outcome = run_turn(
            SimulationCore(GameManager()), checked_leg([move]), planner, done=[earlier]
        )

        self.assertEqual(planner.calls[0][0], [describe_action(earlier), describe_action(move)])
        self.assertEqual(outcome.done, (earlier, move, goal("Next")))

    def test_the_actions_after_a_zone_change_are_never_named_or_run(self):
        gm = GameManager()

        outcome = run(
            gm, [MoveAction(destination="out"), TakeAction(item_name="knife")], Planner(None)
        )

        self.assertEqual(gm.player.current_location_id, "zone_building")
        self.assertIn(REST, outcome.narrated)
        self.assertNotIn(REST, outcome.facts)
        self.assertFalse(any("knife" in fact or "hasn't yet" in fact for fact in outcome.facts))

    def test_a_planner_that_gives_no_actions_leaves_the_rest_unreached(self):
        outcome = run(GameManager(), [MoveAction(destination="out")], planning())

        self.assertIn(REST, outcome.narrated)

    def test_a_second_zone_change_stops_the_turn_there(self):
        gm = GameManager()
        planner = Planner(checked_leg([MoveAction(destination="out"), goal("Later")]))

        outcome = run(gm, [MoveAction(destination="out")], planner)

        self.assertEqual(len(planner.calls), 1)
        self.assertEqual(gm.narrative.goals["short_term"], [])
        self.assertIn(REST, outcome.narrated)

    def test_the_action_budget_is_shared_across_legs(self):
        gm = GameManager()
        planner = planning(goal("C"), goal("D"), goal("E"))

        outcome = run(
            gm, [goal("A"), goal("B"), MoveAction(destination="out"), goal("Rest")], planner
        )

        self.assertEqual(MAX_PLAN_ACTIONS, 5)
        self.assertEqual(gm.narrative.goals["short_term"], ["A", "B", "C", "D"])
        self.assertTrue(any(fact.startswith("Refused:") for fact in outcome.facts))

    def test_an_interrupted_move_leaves_the_rest_unreached_but_an_interrupted_wait_does_not(self):
        class Interrupted(SimulationCore):
            def _after_action(self) -> list[str]:
                self._interruption = "something"
                return []

        wait = WaitAction(duration=Duration(minutes=30))
        for actions, reached in (([MoveAction(destination="out")], False), ([wait], True)):
            with self.subTest(actions=actions):
                gm = GameManager()
                planner = planning(goal("Later"))

                outcome = turn_of(Interrupted(gm), actions, planner)

                self.assertEqual(len(planner.calls), 0)
                self.assertEqual(REST in outcome.narrated, not reached)


class RepeatedMoveTests(unittest.TestCase):
    """A move the second leg repeats, blocked at the barrier the first stopped at, is not run again."""

    def moves_in(self, outcome: TurnOutcome) -> int:
        return len([fact for fact in outcome.facts if fact.startswith("Move to")])

    def test_a_blocked_move_the_planner_repeats_is_not_run_again(self):
        move = MoveAction(destination="pharmacy")
        for repeat in (
            move,
            MoveAction(destination="The Pharmacy"),
            MoveAction(destination="pharmacy", run=True),
        ):
            with self.subTest(repeat=repeat):
                gm = street()

                outcome = run(gm, [move, goal("Smashed")], planning(repeat, goal("Smashed")))

                self.assertEqual(self.moves_in(outcome), 1)
                self.assertEqual(gm.narrative.goals["short_term"], ["Smashed"])

    def test_the_rest_of_the_second_leg_runs_after_the_skipped_move(self):
        gm = street()
        move = MoveAction(destination="pharmacy")
        smashed = goal("Smashed")

        outcome = run(gm, [move], planning(move, smashed))

        self.assertEqual(outcome.done[-1], smashed)

    def test_a_dropped_repeat_leaves_the_rest_unreached(self):
        move = MoveAction(destination="pharmacy")

        outcome = run(street(), [move, TakeAction(item_name="knife")], planning(move))

        self.assertIn(REST, outcome.narrated)
        self.assertFalse(any("knife" in fact for fact in outcome.facts))

    def test_a_move_the_planner_does_not_repeat_is_not_skipped(self):
        gm = street()
        move = MoveAction(destination="pharmacy")

        outcome = run(gm, [move], planning(goal("Smashed")))

        self.assertEqual(gm.narrative.goals["short_term"], ["Smashed"])
        self.assertEqual(self.moves_in(outcome), 1)


class RefusedActionTests(unittest.TestCase):
    def test_a_refusal_the_second_leg_redoes_is_dropped_from_the_turn(self):
        gm = GameManager()
        gm.world.locations["zone_building"].entities.append(
            ItemEntity(item=ITEMS["item_baseball_bat"])
        )
        take = TakeAction(item_name="Baseball Bat")

        outcome = run(gm, [take, MoveAction(destination="out")], planning(take))

        self.assertEqual(outcome.refused, ())
        self.assertIn(take, outcome.done)

    def test_a_refusal_no_later_leg_redoes_stays_in_the_turn(self):
        take = TakeAction(item_name="Baseball Bat")

        outcome = run(
            GameManager(), [take, MoveAction(destination="out")], planning(goal("Find water"))
        )

        self.assertEqual([action for action, _ in outcome.refused], [take])


class FreeMoves(SimulationCore):
    """A core whose legs cost only the minutes they state, so a zone change takes no time of its own."""

    def resolve(self, actions: list[AnyAction], *, budget: int = MAX_PLAN_ACTIONS) -> Leg:
        leg = super().resolve(actions, budget=budget)
        return replace(leg, minutes=leg.stated_minutes)


def time_facts(outcome: TurnOutcome) -> list[str]:
    return [fact for fact in outcome.facts if fact.startswith("About")]


class TurnFactTests(unittest.TestCase):
    def test_a_turn_with_nothing_planned_costs_one_minute(self):
        gm = GameManager()

        outcome = run(gm, [])

        self.assertEqual(gm.narrative.minutes, 1)
        self.assertEqual(len(time_facts(outcome)), 1)

    def test_a_turn_of_only_refused_lines_costs_no_time(self):
        for leg in (UNREADABLE, DROPPED):
            with self.subTest(leg=leg):
                gm = GameManager()

                run(gm, [], **leg)

                self.assertEqual(gm.narrative.minutes, 0)

    def test_a_turn_of_only_refused_actions_costs_no_time(self):
        gm = GameManager()

        run(gm, [TakeAction(item_name="Unicorn"), TakeAction(item_name="Dragon")])

        self.assertEqual(gm.narrative.minutes, 0)

    def test_a_shout_costs_a_minute_only_when_nothing_else_did(self):
        wait = WaitAction(duration=Duration(minutes=10))
        for actions, minutes in (
            ([ShoutAction()], 1),
            ([ShoutAction(), wait], 10),
            ([wait, ShoutAction()], 10),
        ):
            with self.subTest(actions=actions):
                gm = GameManager()

                run(gm, actions)

                self.assertEqual(gm.narrative.minutes, minutes)

    def test_a_shout_in_the_second_leg_costs_a_minute_when_no_leg_cost_any(self):
        shouting = GameManager()
        silent = GameManager()

        turn_of(FreeMoves(shouting), [MoveAction(destination="out")], planning(ShoutAction()))
        turn_of(FreeMoves(silent), [MoveAction(destination="out")], planning(goal("Quiet")))

        self.assertEqual(shouting.narrative.minutes, silent.narrative.minutes + 1)

    def test_the_turn_states_the_time_only_when_no_fact_already_did(self):
        moved = run(GameManager(), [MoveAction(destination="out")], planning())
        waited = run(GameManager(), [WaitAction(duration=Duration(minutes=10))])

        self.assertEqual(len(time_facts(moved)), 1)
        self.assertEqual(time_facts(waited), [])

    def test_the_minutes_the_legs_state_are_summed(self):
        outcome = turn_of(
            FreeMoves(GameManager()),
            [WaitAction(duration=Duration(minutes=10)), MoveAction(destination="out")],
            planning(WaitAction(duration=Duration(minutes=5))),
        )

        self.assertEqual(time_facts(outcome), [])

    def test_the_finds_of_every_leg_are_kept(self):
        outcome = run(
            GameManager(),
            [SearchAction(target_name="kitchen counter"), MoveAction(destination="out")],
            planning(goal("Later")),
        )

        self.assertTrue(outcome.finds)


class NothingDoneTests(unittest.TestCase):
    def test_a_plan_the_parser_found_nothing_in_is_noted_for_the_narrator_only(self):
        outcome = run(GameManager(), [])

        self.assertEqual(outcome.narrated[0], NOTHING)
        self.assertNotIn(NOTHING, outcome.facts)

    def test_an_action_a_refused_line_or_a_dropped_action_is_not_nothing(self):
        for actions, leg in (([goal("Rest")], {}), ([], UNREADABLE), ([], DROPPED)):
            with self.subTest(actions=actions, leg=leg):
                outcome = run(GameManager(), actions, **leg)

                self.assertNotIn(NOTHING, outcome.narrated)


class RefusedBeforeTheChangeTests(unittest.TestCase):
    """The plan check's drops count only when they were parsed before the action that really changed zone."""

    def test_only_drops_parsed_before_the_real_move_are_refused(self):
        before = TakeAction(item_name="rope")
        after = TakeAction(item_name="knife")
        move = MoveAction(destination="out")

        outcome = run(
            GameManager(),
            [goal("First"), move],
            planning(),
            dropped=[(1, before, "Before the move."), (3, after, "After the move.")],
        )

        self.assertIn("Before the move.", outcome.facts)
        self.assertNotIn("After the move.", outcome.facts)

    def test_every_drop_is_refused_when_no_move_changed_zone(self):
        outcome = run(
            GameManager(),
            [goal("First")],
            dropped=[(1, TakeAction(item_name="rope"), "Not asked for.")],
        )

        self.assertIn("Not asked for.", outcome.facts)

    def test_the_second_legs_drops_are_all_refused(self):
        second = checked_leg([goal("Second")], dropped=[(1, TakeAction(item_name="x"), "Later.")])

        outcome = run(GameManager(), [MoveAction(destination="out")], Planner(second))

        self.assertIn("Later.", outcome.facts)

    def test_a_drop_does_not_count_as_a_refusal_the_narrator_is_handed_as_an_action(self):
        outcome = run(
            GameManager(), [goal("First")], dropped=[(1, TakeAction(item_name="x"), "No.")]
        )

        self.assertEqual(outcome.refused, ())


class RestUnreachedTests(unittest.TestCase):
    def test_a_cut_plan_whose_predicted_zone_change_never_happened_leaves_the_rest_unreached(self):
        outcome = run(GameManager(), [goal("First")], cut=True)

        self.assertIn(REST, outcome.narrated)

    def test_a_second_leg_the_check_flags_whole_still_gives_its_refusal(self):
        flagged = checked_leg([], dropped=[(0, TakeAction(item_name="x"), "Not here.")])

        outcome = run(GameManager(), [MoveAction(destination="out")], Planner(flagged))

        self.assertIn("Not here.", outcome.facts)
        self.assertIn(REST, outcome.narrated)

    def test_a_cut_plan_that_changed_zone_and_ran_a_second_plan_reaches_the_rest(self):
        outcome = run(
            GameManager(), [MoveAction(destination="out")], planning(goal("Later")), cut=True
        )

        self.assertNotIn(REST, outcome.narrated)

    def test_the_player_dying_leaves_nothing_unreached(self):
        gm = GameManager()
        make_dying(gm.player)

        outcome = run(gm, [WaitAction(duration=Duration(minutes=30))], cut=True)

        self.assertNotIn(REST, outcome.narrated)


class ParseFailureTests(unittest.TestCase):
    def test_the_refusals_of_every_leg_are_facts_after_the_legs_own(self):
        second = checked_leg([goal("Next")], failures=["Refused: second."])

        outcome = run(
            GameManager(),
            [MoveAction(destination="out")],
            Planner(second),
            failures=["Refused: first."],
        )

        self.assertEqual(outcome.facts[-2:], ("Refused: first.", "Refused: second."))
        self.assertGreater(outcome.facts.index("Refused: first."), 0)


class PickTests(unittest.TestCase):
    """The planner is asked to bind only the picks the turn hasn't placed."""

    def pick(self, entity_id: str) -> Mention:
        return Mention(kind="item", id=entity_id, name=entity_id, description="")

    def take(self, entity_id: str) -> TakeAction:
        return TakeAction(item_name=Pinned(entity_id, "item", entity_id))

    def test_a_pick_is_left_to_bind_unless_spent_tried_or_pinned_in_a_refusal_before_the_move(self):
        planner = Planner(None)
        picks = [self.pick(name) for name in ("tried", "refused", "spent", "free")]
        first = checked_leg(
            [self.take("tried"), MoveAction(destination="out")],
            dropped=[(0, self.take("refused"), "No.")],
        )

        outcome = run_turn(
            SimulationCore(GameManager()),
            first,
            planner,
            picks=picks,
            spent=frozenset({"spent"}),
        )

        self.assertEqual([pick.id for pick in planner.calls[0][1]], ["free"])
        self.assertEqual(outcome.spent, {"tried", "refused", "spent"})

    def test_a_pick_on_a_drop_after_the_real_move_is_left_to_bind(self):
        planner = Planner(None)
        first = checked_leg(
            [MoveAction(destination="out")], dropped=[(1, self.take("after"), "No.")]
        )
        run_turn(SimulationCore(GameManager()), first, planner, picks=[self.pick("after")])

        self.assertEqual([pick.id for pick in planner.calls[0][1]], ["after"])

    def test_the_move_that_changed_zone_is_the_one_whose_earlier_drops_count(self):
        planner = Planner(None)
        first = checked_leg(
            [self.take("tried"), MoveAction(destination="out")],
            dropped=[(1, self.take("between"), "No.")],
        )

        run_turn(
            SimulationCore(GameManager()),
            first,
            planner,
            picks=[self.pick("between")],
        )

        self.assertEqual(planner.calls[0][1], [])


class PausedTurnTests(unittest.TestCase):
    """A leg that meets an unclear target ends there; the rest waits, with the drops that come after it."""

    def asked_turn(self) -> tuple[TurnOutcome, tuple[AnyAction, ...]]:
        gm = street()
        bat = ITEMS["item_baseball_bat"]
        gm.player.inventory.append(ItemEntity(item=bat, condition=0))
        gm.current_location.entities.append(ItemEntity(item=bat))
        actions: tuple[AnyAction, ...] = (
            DropAction(item_name="broken Baseball Bat"),
            TakeAction(item_name="Baseball Bat"),
            goal("Find water"),
        )
        planner = Planner()
        outcome = run(
            gm,
            actions,
            planner,
            failures=["Refused: unreadable."],
            dropped=[
                (1, TakeAction(item_name="a"), "Ahead of the question."),
                (3, TakeAction(item_name="b"), "Behind the question."),
            ],
        )
        self.assertEqual(planner.calls, [])
        return outcome, actions

    def test_the_turn_pauses_at_the_question_with_the_rest_and_its_later_drops(self):
        outcome, actions = self.asked_turn()

        self.assertIsNotNone(outcome.paused)
        assert outcome.paused is not None
        self.assertEqual(outcome.paused.pending, actions[1:])
        self.assertEqual(outcome.paused.check.kept, actions[1:])
        self.assertEqual(
            [reason for _, _, reason in outcome.paused.check.dropped], ["Behind the question."]
        )
        self.assertEqual(outcome.paused.check.failures, ())
        self.assertEqual(outcome.done, actions[:1])

    def test_the_drops_ahead_of_the_pending_actions_are_refused_now_the_rest_wait(self):
        outcome, _ = self.asked_turn()

        self.assertIn("Ahead of the question.", outcome.facts)
        self.assertNotIn("Behind the question.", outcome.facts)
        self.assertNotIn(REST, outcome.narrated)

    def test_a_player_who_dies_of_the_shout_is_not_paused(self):
        gm = street()
        bat = ITEMS["item_baseball_bat"]
        gm.current_location.entities.extend(
            [ItemEntity(item=bat, condition=0), ItemEntity(item=bat)]
        )
        make_dying(gm.player)

        outcome = run(gm, [ShoutAction(), TakeAction(item_name="Baseball Bat")])

        self.assertTrue(gm.narrative.game_over)
        self.assertIsNone(outcome.paused)

    def test_a_turn_that_runs_to_its_end_is_not_paused(self):
        self.assertIsNone(run(GameManager(), [goal("Rest")]).paused)
