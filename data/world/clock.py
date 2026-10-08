"""Clock constants and the pure arithmetic over the minute clock (clock)."""

MINUTES_PER_DAY = 1440  # clock
MINUTES_PER_HOUR = 60  # clock
WORLD_START_MINUTE_OF_DAY = 480  # clock: the game starts at 08:00

# Band starts as minutes after midnight, in ascending order; night wraps past midnight.
TIME_OF_DAY_BANDS = (  # clock
    ("morning", 360),
    ("afternoon", 720),
    ("evening", 1080),
    ("night", 1320),
)
TIME_OF_DAY_START = dict(TIME_OF_DAY_BANDS)
NOON_MINUTE_OF_DAY = 720  # clock
MIDNIGHT_MINUTE_OF_DAY = 0  # clock
TIME_WORD_START = {  # clock: every word a wait or sleep can target, the bands included
    **TIME_OF_DAY_START,
    "dawn": TIME_OF_DAY_START["morning"],
    "sunrise": TIME_OF_DAY_START["morning"],
    "noon": NOON_MINUTE_OF_DAY,
    "midday": NOON_MINUTE_OF_DAY,
    "dusk": TIME_OF_DAY_START["evening"],
    "sunset": TIME_OF_DAY_START["evening"],
    "midnight": MIDNIGHT_MINUTE_OF_DAY,
}
TIME_WORDS = tuple(TIME_WORD_START)
UNTIL_TIME_REFUSAL = (  # clock: the reason a wait or sleep names a word that is no time
    "{word} is not a time of day. A time of day (morning, noon, dusk, night) "
    "or a clock time like 18:00 works."
)
TIME_OF_DAY_PHRASES = {  # clock: a band as an adverbial phrase for a fact
    "morning": "in the morning",
    "afternoon": "in the afternoon",
    "evening": "in the evening",
    "night": "in the middle of the night",
}

WAIT_CAP_MIN = 1440  # clock: 24 h per action
SLEEP_CAP_MIN = 960  # clock: 16 h per action


def minute_of_day(minutes: int) -> int:
    """Minutes after midnight for a clock reading of `minutes` since the start."""
    return (WORLD_START_MINUTE_OF_DAY + minutes) % MINUTES_PER_DAY


def day_number(minutes: int) -> int:
    return 1 + (WORLD_START_MINUTE_OF_DAY + minutes) // MINUTES_PER_DAY


def time_of_day_at(minute_of_day_value: int) -> str:
    """The band containing a minute of the day; night runs 22:00 to 05:59."""
    current = "night"
    for name, start in TIME_OF_DAY_BANDS:
        if minute_of_day_value >= start:
            current = name
    return current


def minutes_until(minutes: int, target_minute_of_day: int) -> int:
    """Minutes from now to the next occurrence of a clock time, strictly later.

    The same time as now is a full day away, never zero.
    """
    delta = (target_minute_of_day - minute_of_day(minutes)) % MINUTES_PER_DAY
    return delta or MINUTES_PER_DAY
