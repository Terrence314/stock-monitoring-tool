"""Tests for history-based stop-loss/take-profit enforcement (fix 2026-07-17).

Bug: positions whose tickers rotate out of the daily broad-scan watchlist
never receive price updates, so their stops are never evaluated — MRVL
closed -19.7% and ON -22.1% as hold_period exits on 2026-07-06 despite the
-8% stop. The fix walks daily OHLC history since entry and closes at the
stop/target price on the day it was first breached.

Run: python3 tests/test_paper_trading_exits.py
No pytest dependency — plain asserts, exits non-zero on failure.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from paper_trading import _apply_ohlc_stops, STOP_LOSS_PCT, TAKE_PROFIT_PCT


def _trade(ticker="TEST", entry=100.0, signal_date="2026-07-01", direction="long"):
    return {
        "id": f"{ticker}-{signal_date}",
        "ticker": ticker,
        "direction": direction,
        "signal_date": signal_date,
        "entry_price": entry,
        "shares": 10.0,
        "status": "open",
        "exit_date": None,
        "exit_price": None,
        "exit_reason": None,
        "current_price": entry,
        "current_date": signal_date,
        "pnl": None,
        "pnl_pct": None,
    }


def _bar(low, high, close):
    return {"low": low, "high": high, "close": close}


# Bars are built RELATIVE to the live stop/target rather than as literals.
# These tests hardcoded 97.0 / 92.0 / 113.5, chosen around -8%/+12%. When the
# exits were reset to -3%/+6% on 2026-08-22 four of them failed -- not because
# the fill logic broke, but because a bar that used to sit safely inside a wide
# stop now sits outside a tight one. A fixture pinned to a parameter's old
# value tests the parameter, not the behaviour.

def _pct(entry, pct):
    return entry * (1 + pct / 100)


def _inside_bar(entry=100.0):
    """A quiet session: never reaches either exit level."""
    half_stop = -STOP_LOSS_PCT / 2
    half_tgt  = TAKE_PROFIT_PCT / 2
    return _bar(_pct(entry, half_stop), _pct(entry, half_tgt), entry)


def test_stop_breach_closes_at_stop_price():
    """Low breaches -8% stop → closed as stop_loss at the stop price, on breach day."""
    t = _trade(entry=100.0)
    stop_price = 100.0 * (1 - STOP_LOSS_PCT / 100)
    deep = _pct(100.0, -STOP_LOSS_PCT * 2.5)      # well through the stop
    ohlc = {"TEST": {
        "2026-07-02": _inside_bar(),
        "2026-07-03": _bar(_pct(100.0, -STOP_LOSS_PCT - 1), _pct(100.0, 1), 95.0),
        "2026-07-06": _bar(deep, deep * 1.1, deep),   # far worse by hold-period close
    }}
    closed = _apply_ohlc_stops([t], ohlc, "2026-07-07")
    assert closed == 1, f"expected 1 close, got {closed}"
    assert t["status"] == "closed"
    assert t["exit_reason"] == "stop_loss"
    assert t["exit_date"] == "2026-07-03", f"exit on breach day, got {t['exit_date']}"
    assert abs(t["exit_price"] - stop_price) < 1e-9, f"exit at stop price, got {t['exit_price']}"
    # pnl_pct is now NET of commission + slippage, so it sits just past the
    # stop. The fill price above is the invariant that must stay exact.
    assert -STOP_LOSS_PCT - 0.5 < t["pnl_pct"] <= -STOP_LOSS_PCT, \
        f"pnl_pct must be -{STOP_LOSS_PCT} net of costs, got {t['pnl_pct']}"


def test_no_breach_stays_open_and_updates_price():
    """No stop/target breach → position stays open, current_price = latest close."""
    t = _trade(entry=100.0)
    ohlc = {"TEST": {
        "2026-07-02": _inside_bar(),
        "2026-07-03": _bar(_pct(100.0, -STOP_LOSS_PCT / 3),
                           _pct(100.0, TAKE_PROFIT_PCT / 3), 101.5),
    }}
    closed = _apply_ohlc_stops([t], ohlc, "2026-07-07")
    assert closed == 0
    assert t["status"] == "open"
    assert t["current_price"] == 101.5, f"orphan price must refresh, got {t['current_price']}"
    assert t["current_date"] == "2026-07-03"


def test_target_breach_closes_at_target_price():
    """High breaches +12% target → closed as take_profit at target price."""
    t = _trade(entry=100.0)
    target = 100.0 * (1 + TAKE_PROFIT_PCT / 100)
    ohlc = {"TEST": {
        "2026-07-02": _bar(_pct(100.0, 1), _pct(100.0, TAKE_PROFIT_PCT + 1.5),
                           _pct(100.0, TAKE_PROFIT_PCT + 0.5)),
    }}
    closed = _apply_ohlc_stops([t], ohlc, "2026-07-07")
    assert closed == 1
    assert t["exit_reason"] == "take_profit"
    assert abs(t["exit_price"] - target) < 1e-9
    # Costs shave the net return just under the target.
    assert TAKE_PROFIT_PCT - 0.5 < t["pnl_pct"] <= TAKE_PROFIT_PCT


def test_same_day_stop_and_target_prefers_stop():
    """Both stop and target hit in one bar → conservative: stop_loss wins."""
    t = _trade(entry=100.0)
    ohlc = {"TEST": {"2026-07-02": _bar(_pct(100.0, -STOP_LOSS_PCT - 2),
                                       _pct(100.0, TAKE_PROFIT_PCT + 3), 100.0)}}
    _apply_ohlc_stops([t], ohlc, "2026-07-07")
    assert t["exit_reason"] == "stop_loss", f"got {t['exit_reason']}"


def test_entry_day_bar_ignored():
    """Entry-day low predates the intraday entry — must not trigger the stop."""
    t = _trade(entry=100.0, signal_date="2026-07-01")
    ohlc = {"TEST": {
        # entry-day dip, before our entry
        "2026-07-01": _bar(_pct(100.0, -STOP_LOSS_PCT * 3), 102.0, 100.0),
        "2026-07-02": _inside_bar(),
    }}
    closed = _apply_ohlc_stops([t], ohlc, "2026-07-07")
    assert closed == 0
    assert t["status"] == "open"


def test_missing_history_leaves_trade_untouched():
    """Ticker absent from OHLC data → no crash, trade untouched."""
    t = _trade(ticker="GONE", entry=100.0)
    closed = _apply_ohlc_stops([t], {}, "2026-07-07")
    assert closed == 0
    assert t["status"] == "open"
    assert t["current_price"] == 100.0


def test_short_positions_skipped():
    """Engine is LONG_ONLY; shorts (legacy) are left for existing logic."""
    t = _trade(entry=100.0, direction="short")
    ohlc = {"TEST": {"2026-07-02": _bar(80.0, 120.0, 100.0)}}
    closed = _apply_ohlc_stops([t], ohlc, "2026-07-07")
    assert closed == 0
    assert t["status"] == "open"


def test_fetch_ohlc_bulk_handles_multiindex_single_ticker():
    """Review finding: 1-element ticker list still returns MultiIndex columns
    on recent yfinance — must not silently return {} for a lone open position."""
    import pandas as pd
    import paper_trading as pt

    idx = pd.to_datetime(["2026-07-02", "2026-07-03"])
    # Open is carried too — the exit paths need it to tell a gap fill from an
    # intraday breach (see tests/test_stop_fill.py).
    cols = pd.MultiIndex.from_product([["Open", "Low", "High", "Close"], ["TEST"]])
    df = pd.DataFrame(
        [[99.0, 95.0, 105.0, 100.0], [100.5, 96.0, 106.0, 101.0]],
        index=idx, columns=cols,
    )
    orig = pt.yf.download
    pt.yf.download = lambda *a, **k: df
    try:
        out = pt._fetch_ohlc_bulk(["TEST"], "2026-07-01")
    finally:
        pt.yf.download = orig
    assert "TEST" in out, f"MultiIndex single-ticker frame must parse, got {out}"
    assert out["TEST"]["2026-07-02"] == {
        "open": 99.0, "low": 95.0, "high": 105.0, "close": 100.0,
    }


def test_fetch_ohlc_bulk_handles_flat_columns():
    """Older yfinance single-ticker shape (flat columns) must also parse."""
    import pandas as pd
    import paper_trading as pt

    idx = pd.to_datetime(["2026-07-02"])
    df = pd.DataFrame(
        {"Open": [99.0], "Low": [95.0], "High": [105.0], "Close": [100.0]}, index=idx
    )
    orig = pt.yf.download
    pt.yf.download = lambda *a, **k: df
    try:
        out = pt._fetch_ohlc_bulk(["TEST"], "2026-07-01")
    finally:
        pt.yf.download = orig
    assert out.get("TEST", {}).get("2026-07-02") == {
        "open": 99.0, "low": 95.0, "high": 105.0, "close": 100.0,
    }


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ✅ {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  ❌ {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
