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
TIMES_OF_DAY = tuple(name for name, _ in TIME_OF_DAY_BANDS)

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
