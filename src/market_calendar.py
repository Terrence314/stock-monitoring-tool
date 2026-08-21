"""market_calendar.py — one NYSE trading-day calendar for the whole system.

Two places counted trading days by skipping weekends and ignoring market
holidays: the Action Box's order-ticket expiry and the validator's
earnings-distance check. The paper engine meanwhile derives the real calendar
from SPY bars. So the expiry printed on a ticket could differ from the date
the engine actually closed the position, and an earnings date one holiday
away was counted as one day nearer than it was.

The engine's SPY-derived calendar stays authoritative — it is ground truth
about which sessions existed. This module covers the surfaces that need a
trading-day answer without a network call, and it fails LOUDLY rather than
silently reverting to weekends-only when its holiday table runs out. That is
the same failure mode the FOMC table had.
"""

from datetime import date, timedelta

# NYSE full-day closures. Half-days (early closes) are still trading days and
# are deliberately absent. Verified against nyse.com/markets/hours-calendars.
# Update every January, alongside signal_validator.FOMC_DATES_*.
NYSE_HOLIDAYS = {
    # 2026
    date(2026, 1, 1),    # New Year's Day
    date(2026, 1, 19),   # Martin Luther King Jr. Day
    date(2026, 2, 16),   # Washington's Birthday
    date(2026, 4, 3),    # Good Friday
    date(2026, 5, 25),   # Memorial Day
    date(2026, 6, 19),   # Juneteenth
    date(2026, 7, 3),    # Independence Day (observed)
    date(2026, 9, 7),    # Labor Day
    date(2026, 11, 26),  # Thanksgiving
    date(2026, 12, 25),  # Christmas
    # 2027
    date(2027, 1, 1),
    date(2027, 1, 18),
    date(2027, 2, 15),
    date(2027, 3, 26),
    date(2027, 5, 31),
    date(2027, 6, 18),   # Juneteenth (observed)
    date(2027, 7, 5),    # Independence Day (observed)
    date(2027, 9, 6),
    date(2027, 11, 25),
    date(2027, 12, 24),  # Christmas (observed)
}

COVERED_YEARS = {d.year for d in NYSE_HOLIDAYS}


def is_covered(d: date) -> bool:
    """True when the holiday table actually covers this date's year."""
    return d.year in COVERED_YEARS


def is_trading_day(d: date) -> bool:
    return d.weekday() < 5 and d not in NYSE_HOLIDAYS


def add_trading_days(start: date, n: int) -> date:
    """The date exactly n trading days after start (exclusive of start)."""
    d, remaining = start, n
    while remaining > 0:
        d += timedelta(days=1)
        if is_trading_day(d):
            remaining -= 1
    return d


def trading_days_between(start: date, target: date) -> int:
    """Signed count of trading days from start to target.

    Positive when target is in the future. Holidays are excluded, so a date
    across a long weekend is correctly reported as nearer than the calendar
    gap suggests.
    """
    if target == start:
        return 0
    step = 1 if target > start else -1
    d, n = start, 0
    while d != target:
        d += timedelta(days=step)
        if is_trading_day(d):
            n += step
    return n


def missing_sessions(fetched_dates, start: date, end: date) -> list:
    """Trading days this calendar expects that a price feed did not return.

    yfinance wraps unofficial Yahoo endpoints: no SLA, undocumented rate
    limits, and gaps that appear without an error. On 2026-08-20 its SPY
    history had no bar for Monday 2026-08-17 -- a normal trading session.

    That gap is not cosmetic here. paper_trading builds its trading calendar
    from the SPY series (`_fetch_calendar`), and every hold-period exit is
    "the Nth trading day after entry". A silently missing session shifts every
    one of those dates by a day, in the direction of holding too long, and
    nothing in the run reports anything wrong.

    Returns the dates the feed owes, so a caller can log or refuse rather than
    quietly compute the wrong exit date.
    """
    have = {d if isinstance(d, date) else date.fromisoformat(str(d)[:10])
            for d in fetched_dates}
    missing, cur = [], start
    while cur <= end:
        if is_trading_day(cur) and cur not in have:
            missing.append(cur)
        cur = cur.fromordinal(cur.toordinal() + 1)
    return missing
