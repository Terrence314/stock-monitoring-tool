"""Tests for signal_validator fixes (review findings 2026-07-06).

Run: python3 tests/test_signal_validator.py
No pytest dependency — plain asserts, exits non-zero on failure.
"""

import json
import os
import sys
import tempfile
from datetime import date

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import signal_validator as sv


def test_earnings_window_counts_trading_days():
    """Finding #1 (HIGH): Friday earnings + Monday run must block (1 trading day apart)."""
    monday = date(2026, 7, 13)
    friday_before = date(2026, 7, 10)

    orig = sv._get_earnings_date
    sv._get_earnings_date = lambda ticker: friday_before
    try:
        risky, reason = sv._is_earnings_risk("TEST", monday)
    finally:
        sv._get_earnings_date = orig

    assert risky, (
        "Friday earnings before a Monday run is 1 trading day away — must block "
        f"(got risky={risky}, reason={reason!r})"
    )

    # Earnings 3 trading days out USED to be a "must not block" control. It
    # now blocks: the +/-1-day window only ever covered the entry day, while
    # holds run HOLD_WINDOW trading days, so a print 3 days out lands
    # squarely inside the open position. Kept as a positive case to pin the
    # widened behaviour.
    thursday_next = date(2026, 7, 16)
    sv._get_earnings_date = lambda ticker: thursday_next
    try:
        risky, reason = sv._is_earnings_risk("TEST", monday)
    finally:
        sv._get_earnings_date = orig
    assert risky, "earnings inside the hold window must block"
    assert "hold" in reason

    # Control: beyond the hold window it must still NOT block.
    far_out = date(2026, 9, 30)
    sv._get_earnings_date = lambda ticker: far_out
    try:
        risky, _ = sv._is_earnings_risk("TEST", monday)
    finally:
        sv._get_earnings_date = orig
    assert not risky, "earnings beyond the hold window must not block"


def test_trading_day_delta_signs_and_weekends():
    f = sv._trading_day_delta
    mon, fri_before, tue = date(2026, 7, 13), date(2026, 7, 10), date(2026, 7, 14)
    assert f(mon, mon) == 0
    assert f(mon, fri_before) == -1, "Mon -> prior Fri = -1 trading day"
    assert f(fri_before, mon) == 1, "Fri -> next Mon = +1 trading day"
    assert f(mon, tue) == 1


def test_corrupt_portfolio_row_does_not_disable_guard():
    """Finding #3 (MEDIUM): one row missing 'ticker' must not empty the whole set."""
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump({"trades": [
            {"status": "open"},                      # corrupt row — no ticker
            {"ticker": "AAPL", "status": "open"},
            {"ticker": "MSFT", "status": "closed"},
        ]}, f)
        path = f.name
    try:
        tickers = sv._load_open_tickers(path)
    finally:
        os.unlink(path)
    assert tickers == {"AAPL"}, f"guard must survive corrupt row (got {tickers})"


def test_log_write_is_atomic():
    """Finding #4 (MEDIUM): log write must go through tmp + os.replace."""
    import inspect
    src = inspect.getsource(sv._append_validator_log)
    assert "os.replace" in src, "log write must use atomic tmp + os.replace pattern"


def test_validate_signals_end_to_end_smoke():
    """Existing behavior intact: gate fail blocks, good buy passes."""
    orig = sv._get_earnings_date
    sv._get_earnings_date = lambda ticker: None
    try:
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump({"trades": []}, f)
            path = f.name
        action_box = {"buys": [
            {"ticker": "GOOD", "price": 10, "score": 80},
            {"ticker": "WEAK", "price": 10, "score": 50},
        ], "sells": []}
        stock_results = [
            {"ticker": "GOOD", "score": 80, "entry_verdict": {"label": "GO"}},
            {"ticker": "WEAK", "score": 50, "entry_verdict": {"label": "WAIT"}},
        ]
        box, blocked = sv.validate_signals(action_box, stock_results, portfolio_path=path)
        os.unlink(path)
    finally:
        sv._get_earnings_date = orig
    assert [b["ticker"] for b in box["buys"]] == ["GOOD"]
    assert len(blocked) == 1 and blocked[0]["ticker"] == "WEAK"


if __name__ == "__main__":
    failures = 0
    for name, fn in sorted(globals().items()):
        if name.startswith("test_") and callable(fn):
            try:
                fn()
                print(f"PASS {name}")
            except AssertionError as e:
                print(f"FAIL {name}: {e}")
                failures += 1
            except Exception as e:
                print(f"ERROR {name}: {type(e).__name__}: {e}")
                failures += 1
    sys.exit(1 if failures else 0)
