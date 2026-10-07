"""Conversion of per-frame and per-day rates to per-game-hour rates (survival-stats).

Three rules cover every rate in the mechanics: day-scaled rates, frame rates
and real-time frame rates. The factors assume the pinned day length of 90 real
minutes per game day.
"""

DAY_SCALED_PER_HOUR = 3600  # survival-stats
FRAME_RATE_PER_HOUR = 10800  # survival-stats
REAL_TIME_PER_HOUR = 6750  # survival-stats


MINUTES_PER_HOUR = 60
TIMED_ACTION_FRAMES_PER_MINUTE = 180  # health
MINUTE_ROUND_UP_AT = 1.5  # doors: a timed action under a minute and a half takes 1 minute


def per_minute_from_frame(rate: float) -> float:
    """A rate applied once per game-time frame, per game minute."""
    return per_hour_from_frame(rate) / MINUTES_PER_HOUR


def per_minute_from_real_frame(rate: float) -> float:
    """A rate applied once per real-time frame, per game minute."""
    return per_hour_from_real_frame(rate) / MINUTES_PER_HOUR


def real_frames_per_minute() -> float:
    """Real-time frames in one game minute (112.5)."""
    return per_minute_from_real_frame(1)


def per_hour_from_day_scaled(rate: float) -> float:
    """A rate that also scales with the day length, per game hour."""
    return rate * DAY_SCALED_PER_HOUR


def per_hour_from_frame(rate: float) -> float:
    """A rate applied once per game-time frame, per game hour."""
    return rate * FRAME_RATE_PER_HOUR


def per_hour_from_real_frame(rate: float) -> float:
    """A rate applied once per real-time frame, per game hour."""
    return rate * REAL_TIME_PER_HOUR


def minutes_from_timed_action_frames(frames: float) -> int:
    """Whole game minutes a timed action of `frames` frames takes, at least 1."""
    minutes = frames / TIMED_ACTION_FRAMES_PER_MINUTE
    if minutes < MINUTE_ROUND_UP_AT:
        return 1
    return int(minutes + 0.5)
