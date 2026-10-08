"""Run the plan-check cases in evals/plan_check_cases.yaml against the configured decision model.

Run by hand when the check's question or the model changes: `python scripts/eval_plan_check.py`.
It calls the model named in config.yml, so it is not part of the test suite.
"""

import sys
from pathlib import Path
from typing import Protocol

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters.factcheck import FactChecker  # noqa: E402
from managers.context import ContextBuilder  # noqa: E402
from managers.story.check import StateQuestion, reach_question  # noqa: E402
from modules.action.types import UnsupportedAction  # noqa: E402
from scripts.eval_parser import scene  # noqa: E402

CASES_FILE = Path(__file__).resolve().parent.parent / "evals" / "plan_check_cases.yaml"


class PlanAnswerer(Protocol):
    def plan_answer(
        self, player_input: str, question: StateQuestion
    ) -> tuple[str, float] | None: ...


def run_case(case: dict, checker: PlanAnswerer) -> str:
    """The reason key the model picks for the case's request, or "none" when it gives no answer."""
    manager = scene(case)
    verbs = ContextBuilder(manager).available_actions_section(without="UNSUPPORTED")
    question = reach_question(manager, UnsupportedAction(text=case["unsupported"]), verbs)
    answer = checker.plan_answer(case["input"], question)
    return answer[0] if answer else "none"


def main() -> int:
    cases = yaml.safe_load(CASES_FILE.read_text(encoding="utf-8"))
    checker = FactChecker(enabled=True)
    passed = 0
    for case in cases:
        got = run_case(case, checker)
        ok = got == case["reason"]
        passed += ok
        sys.stdout.write(f"{'PASS' if ok else 'FAIL'} {case['name']}\n")
        if not ok:
            sys.stdout.write(f"  expected {case['reason']}\n  got      {got}\n")
    sys.stdout.write(f"{passed}/{len(cases)} passed\n")
    return 0 if passed == len(cases) else 1


if __name__ == "__main__":
    raise SystemExit(main())
