"""Conversion of per-frame and per-day rates to per-game-hour rates (spec 02).

Three rules cover every rate in the mechanics: day-scaled rates, frame rates
and real-time frame rates. The factors assume the pinned day length of 90 real
minutes per game day.
"""

DAY_SCALED_PER_HOUR = 3600  # spec 02
FRAME_RATE_PER_HOUR = 10800  # spec 02
REAL_TIME_PER_HOUR = 6750  # spec 02


def per_hour_from_day_scaled(rate: float) -> float:
    """A rate that also scales with the day length, per game hour."""
    return rate * DAY_SCALED_PER_HOUR


def per_hour_from_frame(rate: float) -> float:
    """A rate applied once per game-time frame, per game hour."""
    return rate * FRAME_RATE_PER_HOUR


def per_hour_from_real_frame(rate: float) -> float:
    """A rate applied once per real-time frame, per game hour."""
    return rate * REAL_TIME_PER_HOUR
