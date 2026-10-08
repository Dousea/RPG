"""Story beats: things the engine makes happen once, when their condition first holds (llm-contract)."""

from dataclasses import dataclass

from modules.story.beats import (
    ClockAtOrPast,
    Condition,
    DiscoverFlag,
    Effect,
    ItemHeld,
    SetFlag,
    StartOutbreak,
)

OUTBREAK_BEGINS_MINUTE = 2760  # llm-contract: game minutes, day 3 at 06:00
EVACUATION_MINUTE = 4260  # world-lore: game minutes, day 4 at 07:00
CORDON_MINUTE = 7020  # world-lore: game minutes, day 6 at 05:00
BROADCAST_LOOP_MINUTE = 11760  # world-lore: game minutes, day 9 at 12:00
POWER_OUT_MINUTE = 19380  # world-lore: game minutes, day 14 at 19:00
WATER_OUT_MINUTE = 28920  # world-lore: game minutes, day 21 at 10:00


@dataclass(frozen=True)
class Beat:
    beat_id: str
    when: Condition
    effects: tuple[Effect, ...]
    fact: str
    interrupts: bool


STORY_BEATS: dict[str, Beat] = {  # llm-contract
    "outbreak_begins": Beat(
        beat_id="outbreak_begins",
        when=ClockAtOrPast(OUTBREAK_BEGINS_MINUTE),
        effects=(StartOutbreak(),),
        fact="Sirens start up across the city and don't stop.",
        interrupts=True,
    ),
    "evacuation_announced": Beat(
        beat_id="evacuation_announced",
        when=ClockAtOrPast(EVACUATION_MINUTE),
        effects=(SetFlag("evacuation"), DiscoverFlag("evacuation")),
        fact="A radio somewhere nearby breaks into an announcement about an evacuation point.",
        interrupts=False,
    ),
    "cordon": Beat(
        beat_id="cordon",
        when=ClockAtOrPast(CORDON_MINUTE),
        effects=(SetFlag("cordon"), DiscoverFlag("cordon")),
        fact="Low helicopters pass over the river, and the distant traffic noise stops all at once.",
        interrupts=False,
    ),
    "broadcast_loop": Beat(
        beat_id="broadcast_loop",
        when=ClockAtOrPast(BROADCAST_LOOP_MINUTE),
        effects=(SetFlag("broadcast_loop"), DiscoverFlag("broadcast_loop")),
        fact="The radio voice stops mid-sentence; a recording takes over.",
        interrupts=False,
    ),
    "power_out": Beat(
        beat_id="power_out",
        when=ClockAtOrPast(POWER_OUT_MINUTE),
        effects=(SetFlag("power_out"), DiscoverFlag("power_out")),
        fact="The lights die all at once, and the hum of the city goes with them.",
        interrupts=False,
    ),
    "water_out": Beat(
        beat_id="water_out",
        when=ClockAtOrPast(WATER_OUT_MINUTE),
        effects=(SetFlag("water_out"), DiscoverFlag("water_out")),
        fact="The pipes knock and gurgle; the taps give a last spit of air.",
        interrupts=False,
    ),
    "trial_files": Beat(
        beat_id="trial_files",
        when=ItemHeld("item_study_binder"),
        effects=(DiscoverFlag("trial_truth"),),
        fact=(
            "The binder is a study log: VX-7, Velloran Biologics, a list of Ashby names. "
            "The last pages are fever charts."
        ),
        interrupts=False,
    ),
}
