"""One trading-day calendar, shared by every surface that counts sessions.

Three places disagreed about what a "trading day" is:
  - the Action Box counted bare weekdays for the order ticket's expiry;
  - signal_validator counted bare weekdays for earnings distance;
  - the paper engine used the real NYSE calendar derived from SPY bars.

So a ticket could state an expiry the engine would not act on, and an
earnings date across a holiday weekend read as further away than it was.
"""

import os
import sys
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from market_calendar import (                                        # noqa: E402
    add_trading_days, trading_days_between, is_trading_day, is_covered, missing_sessions,
    NYSE_HOLIDAYS, COVERED_YEARS,
)
import signal_validator as sv                                        # noqa: E402


# ── Holidays are not trading days ─────────────────────────────────────────────

@pytest.mark.parametrize("holiday", [
    date(2026, 1, 1),    # New Year's Day
    date(2026, 7, 3),    # Independence Day observed — a Friday
    date(2026, 11, 26),  # Thanksgiving
    date(2026, 12, 25),  # Christmas
])
def test_market_holidays_are_excluded(holiday):
    assert holiday.weekday() < 5, "these are weekday closures, the interesting case"
    assert not is_trading_day(holiday)


def test_ordinary_weekdays_and_weekends():
    assert is_trading_day(date(2026, 7, 13))      # Monday
    assert not is_trading_day(date(2026, 7, 11))  # Saturday
    assert not is_trading_day(date(2026, 7, 12))  # Sunday


# ── Counting ──────────────────────────────────────────────────────────────────

def test_hold_spanning_a_holiday_lands_a_day_later():
    """A weekday-only count put the ticket expiry one session early."""
    start = date(2026, 6, 29)
    assert add_trading_days(start, 10) == date(2026, 7, 14)


def test_hold_with_no_holiday_matches_plain_weekday_counting():
    start = date(2026, 8, 3)     # no NYSE closure in the following fortnight
    assert add_trading_days(start, 10) == date(2026, 8, 17)


def test_thanksgiving_week_is_short():
    assert trading_days_between(date(2026, 11, 23), date(2026, 11, 30)) == 4


def test_weekend_distance_is_still_one_session():
    """Friday -> Monday is 1 trading day, not 3 calendar days."""
    assert trading_days_between(date(2026, 7, 10), date(2026, 7, 13)) == 1


def test_distance_is_signed_and_symmetric():
    a, b = date(2026, 8, 3), date(2026, 8, 10)
    assert trading_days_between(a, b) == -trading_days_between(b, a)
    assert trading_days_between(a, a) == 0


# ── The validator uses it ─────────────────────────────────────────────────────

def test_validator_delegates_to_the_shared_calendar():
    assert sv._trading_day_delta(date(2026, 7, 10), date(2026, 7, 13)) == 1
    # Across Independence Day (observed Fri 2026-07-03)
    assert sv._trading_day_delta(date(2026, 7, 1), date(2026, 7, 7)) == 3


# ── The table must announce when it expires ───────────────────────────────────

def test_covered_years_are_known():
    assert is_covered(date(2026, 5, 1))
    assert is_covered(date(2027, 5, 1))


def test_uncovered_year_is_reported_not_silently_degraded():
    """The FOMC table's failure mode, avoided here."""
    beyond = max(COVERED_YEARS) + 1
    assert not is_covered(date(beyond, 5, 1))


def test_holiday_table_is_not_empty_for_a_covered_year():
    for year in COVERED_YEARS:
        assert any(h.year == year for h in NYSE_HOLIDAYS)


# ── Feed gaps ────────────────────────────────────────────────────────────────
#
# yfinance dropped Monday 2026-08-17 from SPY's history with no error. The
# trading calendar paper_trading builds is derived from that series, and every
# hold-period exit is "the Nth trading day after entry" against it -- so a
# missing session shifts exits later by a day and nothing reports it.

def test_a_missing_session_is_detected():
    """The real gap, replayed."""
    fetched = ["2026-08-13", "2026-08-14", "2026-08-18", "2026-08-19"]
    gaps = missing_sessions(fetched, date(2026, 8, 13), date(2026, 8, 19))
    assert gaps == [date(2026, 8, 17)]


def test_a_complete_feed_reports_nothing():
    fetched = ["2026-08-13", "2026-08-14", "2026-08-17", "2026-08-18", "2026-08-19"]
    assert missing_sessions(fetched, date(2026, 8, 13), date(2026, 8, 19)) == []


def test_weekends_are_not_reported_as_missing():
    fetched = ["2026-08-14", "2026-08-17"]           # Fri then Mon
    assert missing_sessions(fetched, date(2026, 8, 14), date(2026, 8, 17)) == []


def test_holidays_are_not_reported_as_missing():
    """A closed exchange is not a feed failure."""
    holiday = next(iter(sorted(NYSE_HOLIDAYS)))
    h = holiday if isinstance(holiday, date) else date.fromisoformat(str(holiday))
    assert h not in missing_sessions([], h, h)


def test_an_empty_feed_reports_every_session():
    gaps = missing_sessions([], date(2026, 8, 17), date(2026, 8, 19))
    assert len(gaps) == 3


def test_date_objects_and_strings_are_both_accepted():
    as_str = missing_sessions(["2026-08-18"], date(2026, 8, 17), date(2026, 8, 18))
    as_obj = missing_sessions([date(2026, 8, 18)], date(2026, 8, 17), date(2026, 8, 18))
    assert as_str == as_obj == [date(2026, 8, 17)]
