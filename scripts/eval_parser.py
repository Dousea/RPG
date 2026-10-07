"""Run the parser cases in evals/parser_cases.yaml against the configured model.

Run by hand when the parser prompt or the model changes: `python scripts/eval_parser.py`.
It calls the model named in config.yml, so it is not part of the test suite.
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters import llm  # noqa: E402
from managers.context import ContextBuilder  # noqa: E402
from managers.game import GameManager  # noqa: E402
from managers.locations import connection_target  # noqa: E402
from modules.action.parser import parse_action_plan  # noqa: E402
from modules.action.types import AnyAction, MoveAction  # noqa: E402

CASES_FILE = Path(__file__).resolve().parent.parent / "evals" / "parser_cases.yaml"


def scene(case: dict) -> GameManager:
    manager = GameManager()
    manager.player.current_location_id = case.get("zone", manager.player.current_location_id)
    manager.player.sneaking = bool(case.get("sneaking", False))
    if case.get("outbreak"):
        manager.world.outbreak_started_at = 0
    return manager


def _reached(manager: GameManager, action: AnyAction) -> object:
    """A move as the zone it reaches, so "In" and an alias match; other actions as they are."""
    if not isinstance(action, MoveAction):
        return action
    folded = action.destination.casefold()
    current = manager.current_location
    target = connection_target(folded, current, manager.world.locations)
    target = target or manager.resolve_location(action.destination)
    return (MoveAction.verb, target.id if target else folded, action.run)


def same_plan(manager: GameManager, got: list[AnyAction], want: list[AnyAction]) -> bool:
    """Whether the engine would make the same plan of both."""
    return [_reached(manager, a) for a in got] == [_reached(manager, a) for a in want]


def run_case(case: dict) -> tuple[bool, list[str]]:
    manager = scene(case)
    context = ContextBuilder(manager)
    reply = llm.query_parser(
        context.build_parser_prompt(case["input"]), context.build_plan_schema()
    )
    got, _ = llm.read_parser_reply(reply)
    want, _ = parse_action_plan(list(case["expect"]))
    return same_plan(manager, got, want), [repr(action) for action in got]


def main() -> int:
    cases = yaml.safe_load(CASES_FILE.read_text(encoding="utf-8"))
    passed = 0
    for case in cases:
        try:
            ok, got = run_case(case)
        except llm.LLMError as exc:
            sys.stdout.write(f"ERROR {case['name']}: {exc}\n")
            continue
        passed += ok
        sys.stdout.write(f"{'PASS' if ok else 'FAIL'} {case['name']}\n")
        if not ok:
            sys.stdout.write(f"  expected {case['expect']}\n  got      {got}\n")
    sys.stdout.write(f"{passed}/{len(cases)} passed\n")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
