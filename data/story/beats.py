"""Story beats: things the engine makes happen once, when their condition first holds (spec 10)."""

from dataclasses import dataclass

from modules.story.beats import ClockAtOrPast, Condition, Effect, StartOutbreak

OUTBREAK_BEGINS_MINUTE = 2760  # spec 10: game minutes, day 3 at 06:00


@dataclass(frozen=True)
class Beat:
    beat_id: str
    when: Condition
    effects: tuple[Effect, ...]
    fact: str
    interrupts: bool


STORY_BEATS: dict[str, Beat] = {  # spec 10
    "outbreak_begins": Beat(
        beat_id="outbreak_begins",
        when=ClockAtOrPast(OUTBREAK_BEGINS_MINUTE),
        effects=(StartOutbreak(),),
        fact="Sirens start up across the city and don't stop.",
        interrupts=True,
    ),
}
