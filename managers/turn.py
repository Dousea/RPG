"""A turn: the legs of one plan run in order, and what the turn as a whole did.

`start_turn` takes a checked first leg and `resume_turn` a paused turn with the player's
answers; both run the legs through `SimulationCore.resolve`. A leg ends at its
first zone change; the turn may go on with one more leg, planned at the destination by the
injected leg planner, the turn's one seam to the LLM. A second zone change stops the turn
there, and `MAX_PLAN_ACTIONS` is one budget for all legs.

The turn owns what a single leg can't know: `SimulationCore.begin_turn` (the per-turn
resets, run once here and never by `resolve`), the minute of a turn that did nothing or
shouted, the net status-effect changes, "About N minutes pass", which refusals the plan
check made before the zone change, and whether the rest of the plan was reached.

A turn that waits on the player's choice among several things is a `Paused` value: the
plan still to run, the choices open in it, what the turn has done and the player's words
for a later leg. It is never saved.
"""

import logging
from collections.abc import Callable, Sequence
from dataclasses import dataclass, replace

from data.story import mentions as mention_k
from data.time_costs import MAX_PLAN_ACTIONS
from managers.body.stats.status_effects import player_status_effect_levels
from managers.context import NOTHING_DONE_FACT
from managers.game import GameManager
from managers.plan import OpenChoice, PlanStep, bind_choices, open_choices, steps_of
from managers.simulation import Leg, LegEnd, SimulationCore
from modules.action.choices import Candidate
from modules.action.pins import Mention, pinned_ids, render_input
from modules.action.types import AnyAction
from modules.action.words import describe_action

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class CheckedLeg:
    """A parsed plan after the plan check, ready to run as a leg.

    `dropped` holds each flagged action with its place in the parsed plan and its refusal;
    `kept_at` the place of each kept action. `cut` says the plan's tail after a predicted
    zone change was left out. `failures` are the refusals, in words, for the lines the
    parser couldn't read.
    """

    kept: tuple[AnyAction, ...]
    kept_at: tuple[int, ...]
    dropped: tuple[tuple[int, AnyAction, str], ...]
    cut: bool
    failures: tuple[str, ...] = ()

    @property
    def nothing_parsed(self) -> bool:
        return not (self.kept or self.dropped or self.failures or self.cut)

    def refused_before(self, change: AnyAction | None) -> list[tuple[AnyAction, str]]:
        """The flagged actions parsed before `change`, the action that really changed zone (all of them when none did)."""
        at = next((i for i, action in enumerate(self.kept) if action is change), None)
        if change is None or at is None:
            return [(action, fact) for _, action, fact in self.dropped]

        limit = self.kept_at[at]
        return [(action, fact) for place, action, fact in self.dropped if place < limit]

    def refused_before_pending(self, pending: Sequence[AnyAction]) -> list[tuple[AnyAction, str]]:
        """The flagged actions parsed before the actions still to run; the later ones wait for the resumed run."""
        limit = self._pending_at(pending)
        return [(action, fact) for place, action, fact in self.dropped if place < limit]

    def resumed(self, pending: Sequence[AnyAction]) -> "CheckedLeg":
        """The check for the actions still to run, holding the flagged ones that come after them."""
        limit = self._pending_at(pending)
        start = self.kept_at.index(limit)
        return replace(
            self,
            kept=tuple(pending),
            kept_at=self.kept_at[start : start + len(pending)],
            dropped=tuple(entry for entry in self.dropped if entry[0] > limit),
            failures=(),
        )

    def _pending_at(self, pending: Sequence[AnyAction]) -> int:
        start = next(i for i, action in enumerate(self.kept) if action is pending[0])
        return self.kept_at[start]


@dataclass(frozen=True)
class Said:
    """What the player typed (a mark where each pick stands) and the picks, kept so a later leg can be parsed again."""

    typed: str = ""
    picks: tuple[Mention, ...] = ()

    @property
    def shown(self) -> str:
        """The player's words with each pick as its name."""
        return render_input(self.typed, list(self.picks), for_parser=False)


NO_WORDS = Said()

LegPlanner = Callable[[Said, Sequence[str], Sequence[Mention]], CheckedLeg | None]
"""Plans the leg at the destination from what the player said, the turn's done actions in words and the picks still to bind; None when it couldn't."""


@dataclass(frozen=True)
class Paused:
    """A turn waiting on the player's choice: `check` holds the actions still to run and the flagged ones that come after the first of them.

    `choices` are the targets open in `check.kept`, `done` what the turn already did and
    `spent` the ids of the picks it has placed or dropped.
    """

    check: CheckedLeg
    choices: tuple[OpenChoice, ...]
    said: Said
    done: tuple[AnyAction, ...]
    spent: frozenset[str]

    def steps(self, manager: GameManager) -> list[PlanStep]:
        """The plan screen's steps: what is done, then what is still to do with its open choices."""
        return steps_of(manager, self.done, self.check.kept, self.choices)


@dataclass(frozen=True)
class Declined:
    """The answers a paused turn refused, in words; nothing ran."""

    words: str


@dataclass(frozen=True)
class TurnOutcome:
    """What a turn did, as its callers read it.

    `facts` go in the event log; `narrated` adds the notes only the narrator gets. `refused`
    holds what the legs refused, `done` every action the turn has done (earlier runs
    included) and `spent` the ids of the picks it has placed or dropped.
    """

    facts: tuple[str, ...]
    narrated: tuple[str, ...]
    refused: tuple[tuple[AnyAction, str], ...]
    finds: tuple[str, ...]
    done: tuple[AnyAction, ...]
    spent: frozenset[str]
    paused: Paused | None


def start_turn(
    core: SimulationCore, first: CheckedLeg, planner: LegPlanner, said: Said = NO_WORDS
) -> Paused | TurnOutcome:
    """Start the turn from its checked first leg: paused when the leg has open choices, else run."""
    choices = open_choices(core.manager, first.kept, said.shown)
    if choices:
        _trace_choices(choices)
        return Paused(first, tuple(choices), said, (), frozenset())

    return _run_turn(core, first, planner, said, (), frozenset())


def resume_turn(
    core: SimulationCore, paused: Paused, answers: Sequence[str], planner: LegPlanner
) -> TurnOutcome | Declined:
    """Bind `answers` (one candidate id per open choice, in order) into the paused turn and run it.

    Declined, with nothing run, when the choices have changed since they were offered or an
    answer is not among a choice's candidates.
    """
    now = open_choices(core.manager, paused.check.kept, paused.said.shown)
    answered = _answered(paused.choices, now, answers)
    if answered is None:
        return Declined(mention_k.ANSWER_NOT_ON_OFFER)

    logger.debug(
        "Plan screen picks: %s",
        [(choice.index, choice.attr, pick.id) for choice, pick in zip(now, answered, strict=True)],
    )
    check = replace(paused.check, kept=tuple(bind_choices(paused.check.kept, now, answered)))
    return _run_turn(core, check, planner, paused.said, paused.done, paused.spent)


def _answered(
    asked: Sequence[OpenChoice], now: Sequence[OpenChoice], answers: Sequence[str]
) -> list[Candidate] | None:
    if tuple(now) != tuple(asked) or len(answers) != len(now):
        return None

    found: list[Candidate] = []
    for choice, answer in zip(now, answers, strict=True):
        candidate = next((c for c in choice.candidates if c.id == answer), None)
        if candidate is None:
            return None

        found.append(candidate)
    return found


def _trace_choices(choices: Sequence[OpenChoice]) -> None:
    for choice in choices:
        logger.debug(
            "Which-one asked for action [%s] %s: %s",
            choice.index,
            choice.attr,
            [(c.id, c.name) for c in choice.candidates],
        )


def _run_turn(
    core: SimulationCore,
    first: CheckedLeg,
    planner: LegPlanner,
    said: Said,
    done: Sequence[AnyAction],
    spent: frozenset[str],
) -> TurnOutcome:
    """Run the turn from its checked leg without asking about open choices; `done` and `spent` are what an earlier run of this turn did and placed.

    The planner is called at most once, when a leg changes zone.
    """
    manager = core.manager
    name = manager.player.appearance.forename
    levels_before = player_status_effect_levels(manager.player)
    facts, minutes = core.begin_turn(idle=not (first.kept or first.dropped or first.failures))

    checks = [first]
    legs: list[Leg] = []
    done_words = [describe_action(action) for action in done]
    tried: list[AnyAction] = []
    rest_unreached = False
    planned = False
    plan = first.kept

    while True:
        leg = core.resolve(list(plan), budget=MAX_PLAN_ACTIONS - len(tried))
        legs.append(leg)
        facts.extend(leg.facts)
        minutes += leg.minutes
        done_words.extend(describe_action(action) for action in leg.done)
        tried.extend(leg.tried)

        if leg.stopped is LegEnd.INTERRUPTED:
            rest_unreached = leg.moved_by is not None
        if leg.stopped is not LegEnd.ZONE_CHANGE:
            break

        checked = None
        if not planned:
            planned = True
            bound = (
                spent | pinned_ids(tried) | pinned_ids(_actions(first.refused_before(leg.moved_by)))
            )
            checked = planner(
                said, done_words, [pick for pick in said.picks if pick.id not in bound]
            )
        if checked is not None:
            checks.append(checked)
        more = checked.kept if checked is not None else ()
        if more and leg.stalled and core.repeats_blocked_move(more[0]):
            more = more[1:]
        if not more:
            rest_unreached = True
            break

        plan = more

    last = legs[-1]
    facts = core.end_turn(
        facts,
        minutes,
        levels_before,
        shouted=last.shouted,
        stated_minutes=sum(leg.stated_minutes for leg in legs),
    )
    ran = [action for leg in legs for action in leg.done]
    redone = {describe_action(action) for action in ran}
    refused = tuple(
        refusal
        for leg in legs
        for refusal in leg.refused
        if describe_action(refusal[0]) not in redone
    )
    paused = last.asked is not None and not manager.narrative.game_over

    refused_in_scene: list[tuple[AnyAction, str]] = []
    waiting: CheckedLeg | None = None
    for number, check in enumerate(checks):
        change = legs[number].moved_by if number < len(legs) else None
        if paused and check is checks[-1]:
            refused_in_scene.extend(check.refused_before_pending(last.pending))
            waiting = check.resumed(last.pending)
        else:
            refused_in_scene.extend(check.refused_before(change))
        if check.cut and change is None and last.asked is None:
            rest_unreached = not manager.narrative.game_over

    recorded = (
        *facts,
        *(failure for check in checks for failure in check.failures),
        *(fact for _, fact in refused_in_scene),
    )
    narrated = recorded
    if first.nothing_parsed:
        narrated = (NOTHING_DONE_FACT.format(name=name), *narrated)
    if rest_unreached:
        narrated = (*narrated, mention_k.REST_NOT_REACHED_FACT.format(name=name))

    turn_done = (*done, *ran)
    turn_spent = frozenset(spent | pinned_ids(tried) | pinned_ids(_actions(refused_in_scene)))
    paused_turn = None
    if waiting is not None:
        choices = open_choices(manager, waiting.kept, said.shown)
        _trace_choices(choices)
        paused_turn = Paused(waiting, tuple(choices), said, turn_done, turn_spent)

    return TurnOutcome(
        facts=recorded,
        narrated=narrated,
        refused=refused,
        finds=tuple(find for leg in legs for find in leg.finds),
        done=turn_done,
        spent=turn_spent,
        paused=paused_turn,
    )


def _actions(refusals: Sequence[tuple[AnyAction, str]]) -> list[AnyAction]:
    return [action for action, _ in refusals]
