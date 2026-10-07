"""Reading story conditions against the game (spec 10, Story beats and Topics)."""

from data.story.topics import TOPICS, Topic
from managers.game import GameManager
from modules.entity.npc import NpcEntity
from modules.story.beats import (
    AllOf,
    BeatFiredAgo,
    ClockAtOrPast,
    Condition,
    FlagDiscovered,
    OutbreakStarted,
    PlayerInZone,
)


def holds(condition: Condition, manager: GameManager) -> bool:
    match condition:
        case ClockAtOrPast(minute=minute):
            return manager.narrative.minutes >= minute
        case PlayerInZone(zone_id=zone_id):
            return manager.player.current_location_id == zone_id
        case FlagDiscovered(flag=flag):
            return flag in manager.narrative.discovered_flags
        case OutbreakStarted():
            return manager.world.outbreak_started_at is not None
        case BeatFiredAgo(beat_id=beat_id, minutes=minutes):
            fired = manager.world.fired_beats.get(beat_id)
            return fired is not None and manager.narrative.minutes - fired >= minutes
        case AllOf(conditions=conditions):
            return all(holds(part, manager) for part in conditions)


def clock_minutes(condition: Condition) -> list[int]:
    """The minutes of every `ClockAtOrPast` in a condition, however deeply nested."""
    match condition:
        case ClockAtOrPast(minute=minute):
            return [minute]
        case AllOf(conditions=conditions):
            return [minute for part in conditions for minute in clock_minutes(part)]
    return []


def visible_topics(manager: GameManager, npc: NpcEntity) -> list[Topic]:
    """The topics this NPC can be asked about right now."""
    return [
        topic
        for topic in TOPICS.values()
        if topic.npc_id == npc.npc_id and (topic.requires is None or holds(topic.requires, manager))
    ]
