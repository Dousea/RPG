"""The event-log entry the engine writes for a turn, from the turn itself and never from narrator text."""

from managers.context import zombie_ids_to_words
from managers.game import GameManager


def event_stamp(manager: GameManager) -> str:
    """Game day, clock time and zone, as they stand when the player acts."""
    return f"Day {manager.narrative.day}, {manager.world.time}, {manager.current_location.name}"


def build_event_entry(manager: GameManager, stamp: str, player_input: str, facts: list[str]) -> str:
    """The stamp, what the player tried (quoted), then the outcome facts in words."""
    name = manager.player.appearance.forename
    entry = f'{stamp}. {name} tries: "{player_input}"'
    if not facts:
        return entry
    return f"{entry} {' '.join(zombie_ids_to_words(fact) for fact in facts)}"
