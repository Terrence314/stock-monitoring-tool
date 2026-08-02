"""One fill convention for stop and target, across all three exit paths.

Before this, the same event produced different P&L depending on which code
path noticed it first:

  - _apply_ohlc_stops booked exactly the stop level, even when the session
    gapped straight through it;
  - update_open_positions (the 15-minute poll) booked whatever price it
    happened to observe, minutes or hours after a resting order would have
    filled;
  - the daily check in run_paper_trading did the same.

Live evidence in the 42-trade gate sample: 7 of 42 closed worse than -8.5%,
and three of them — -17.0%, -14.1%, -13.5% — were labelled "stop_loss".
"""

import os
import sys
import json

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import paper_trading as pt                                          # noqa: E402
from paper_trading import (                                         # noqa: E402
    _stop_fill_price, _target_fill_price, _apply_ohlc_stops,
    STOP_LOSS_PCT, TAKE_PROFIT_PCT, REGIME_NORMAL,
)

ENTRY = 100.0
STOP = ENTRY * (1 - STOP_LOSS_PCT / 100)     # 92.0
TARGET = ENTRY * (1 + TAKE_PROFIT_PCT / 100)  # 112.0


# ── The convention itself ─────────────────────────────────────────────────────

def test_intraday_breach_fills_at_the_stop_level():
    fill, gapped = _stop_fill_price(ENTRY, day_open=99.0)
    assert fill == pytest.approx(STOP)
    assert gapped is False


def test_gap_through_the_stop_fills_at_the_open():
    """You cannot be filled at a price that never traded."""
    fill, gapped = _stop_fill_price(ENTRY, day_open=85.0)
    assert fill == 85.0
    assert gapped is True


def test_missing_open_falls_back_to_the_stop_level():
    for missing in (None, 0, 0.0):
        fill, gapped = _stop_fill_price(ENTRY, day_open=missing)
        assert fill == pytest.approx(STOP)
        assert gapped is False


def test_target_mirrors_the_stop_behaviour():
    assert _target_fill_price(ENTRY, 105.0) == (pytest.approx(TARGET), False)
    fill, gapped = _target_fill_price(ENTRY, 120.0)
    assert fill == 120.0 and gapped is True


# ── History sweep uses it ─────────────────────────────────────────────────────

def _trade():
    return {
        "ticker": "AAA", "direction": "long", "status": "open",
        "signal_date": "2026-08-01", "entry_price": ENTRY, "shares": 10.0,
        "notional": 1000, "exit_date": None, "exit_price": None,
        "exit_reason": None, "pnl": None, "pnl_pct": None,
    }


def test_sweep_books_the_stop_on_an_intraday_breach():
    t = _trade()
    ohlc = {"AAA": {"2026-08-03": {"open": 99.0, "low": 90.0, "high": 99.5, "close": 91.0}}}

    assert _apply_ohlc_stops([t], ohlc, "2026-08-05") == 1
    assert t["exit_price"] == pytest.approx(STOP)
    assert t["gapped"] is False
    # Net of costs, so just past the stop; exit_price above is exact.
    assert -STOP_LOSS_PCT - 0.5 < t["pnl_pct"] <= -STOP_LOSS_PCT


def test_sweep_books_the_open_on_a_gap_down():
    t = _trade()
    ohlc = {"AAA": {"2026-08-03": {"open": 80.0, "low": 78.0, "high": 82.0, "close": 81.0}}}

    assert _apply_ohlc_stops([t], ohlc, "2026-08-05") == 1
    assert t["exit_price"] == 80.0
    assert t["gapped"] is True
    assert t["pnl_pct"] < -STOP_LOSS_PCT      # honest: worse than the stop


# ── The 15-minute poll uses it ────────────────────────────────────────────────

@pytest.fixture
def portfolio(tmp_path, monkeypatch):
    p = tmp_path / "paper_portfolio.json"
    p.write_text(json.dumps({"trades": [_trade()], "last_updated": ""}))
    monkeypatch.setattr(pt, "PORTFOLIO_FILE", str(p))
    return p


def test_poll_no_longer_books_the_observed_price(portfolio):
    """Price polled at -17% with no gap must still book the -8% stop."""
    pt.update_open_positions(
        [{"ticker": "AAA", "price": 83.0, "open_price": 99.0}], "2026-08-03"
    )

    t = json.loads(portfolio.read_text())["trades"][0]
    assert t["status"] == "closed"
    assert t["exit_reason"] == "stop_loss"
    assert t["exit_price"] == pytest.approx(STOP)
    # Net of costs, so just past the stop; exit_price above is exact.
    assert -STOP_LOSS_PCT - 0.5 < t["pnl_pct"] <= -STOP_LOSS_PCT


def test_poll_still_reports_a_genuine_gap_honestly(portfolio):
    pt.update_open_positions(
        [{"ticker": "AAA", "price": 82.0, "open_price": 84.0}], "2026-08-03"
    )

    t = json.loads(portfolio.read_text())["trades"][0]
    assert t["exit_price"] == 84.0
    assert t["gapped"] is True


# ── The invariant that failed in production ───────────────────────────────────

def test_no_long_closes_past_the_stop_without_a_gap(portfolio):
    """7 of 42 trades in the old sample violated exactly this."""
    pt.update_open_positions(
        [{"ticker": "AAA", "price": 78.0, "open_price": 99.5}], "2026-08-03"
    )

    t = json.loads(portfolio.read_text())["trades"][0]
    # Allow the cost drag; the point is the fill was not the polled -22%.
    assert t["pnl_pct"] >= -STOP_LOSS_PCT - 0.5 or t.get("gapped"), \
        f"closed at {t['pnl_pct']}% with no gap recorded"
