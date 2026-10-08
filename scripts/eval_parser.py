"""Run the parser cases in evals/parser_cases.yaml against the configured model.

Run by hand when the parser prompt or the model changes: `python scripts/eval_parser.py`.
It calls the model named in config.yml, so it is not part of the test suite.
"""

import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from adapters import llm  # noqa: E402
from data.items import ITEMS  # noqa: E402
from managers.context import ContextBuilder  # noqa: E402
from managers.game import GameManager  # noqa: E402
from managers.world.locations import connection_target  # noqa: E402
from modules.action.parser import parse_action_plan  # noqa: E402
from modules.action.types import AnyAction, MoveAction, TalkAction, UnsupportedAction  # noqa: E402
from modules.entity.item import ItemEntity  # noqa: E402
from modules.entity.zombie import ZombieEntity, ZombieState  # noqa: E402
from modules.item import HoldableItem  # noqa: E402

CASES_FILE = Path(__file__).resolve().parent.parent / "evals" / "parser_cases.yaml"
DOWN_FOR_MINUTES = 10_000


def scene(case: dict) -> GameManager:
    manager = GameManager()
    manager.player.current_location_id = case.get("zone", manager.player.current_location_id)
    manager.player.sneaking = bool(case.get("sneaking", False))
    manager.player.inventory.extend(ItemEntity(item=ITEMS[i]) for i in case.get("carrying", []))
    if case.get("outbreak"):
        manager.world.outbreak_started_at = 0
    if holding := case.get("holding"):
        held = ItemEntity(item=ITEMS[holding])
        assert isinstance(held.item, HoldableItem)
        for slot in held.item.slots:
            manager.player.equipment[slot] = held
    for _ in range(case.get("standing_zombies", 0)):
        _add_zombie(manager, down=False)
    for _ in range(case.get("downed_zombies", 0)):
        _add_zombie(manager, down=True)
    return manager


def _add_zombie(manager: GameManager, *, down: bool) -> None:
    number = manager.world.next_zombie_number
    manager.world.next_zombie_number += 1
    manager.world.zombies[f"z{number}"] = ZombieEntity(
        zombie_id=f"z{number}",
        zone_id=manager.player.current_location_id,
        health=2.0,
        speed_type=3,
        speed_mod=0.6,
        lunger=False,
        strength=3,
        memory=800,
        sight=2,
        hearing=2,
        state=ZombieState.IDLE,
        gap=1.0,
        down_until=manager.narrative.minutes + DOWN_FOR_MINUTES if down else 0,
    )


def _reached(manager: GameManager, action: AnyAction) -> object:
    """A move as the zone it reaches (or the zones its words fit), so "In" and an alias match; a talk by whether words came with it; other actions as they are."""
    if isinstance(action, TalkAction):
        return (TalkAction.verb, action.npc_name, action.approach, bool(action.speech))
    if isinstance(action, UnsupportedAction):
        return UnsupportedAction.verb
    if not isinstance(action, MoveAction):
        return action
    folded = action.destination.casefold()
    current = manager.current_location
    target = connection_target(folded, current, manager.world.locations)
    target = target or manager.resolve_places(action.destination)
    if isinstance(target, list):
        reached = tuple(zone.id for zone in target)
    else:
        reached = target.id if target else folded
    return (MoveAction.verb, reached, action.run)


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
    for lines in [case["expect"], *case.get("expect_instead", [])]:
        want, _ = parse_action_plan(list(lines))
        if same_plan(manager, got, want):
            return True, [repr(action) for action in got]
    return False, [repr(action) for action in got]


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
