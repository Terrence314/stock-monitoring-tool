"""Regression tests for the go-live gate — the calculation that decides when
real money starts.

Two defects, both found 2026-07-30:

A. quality_ok had NO minimum sample size. `winrate > 50` OR `pf >= 1.3` with
   any number of closed trades, so two winners and zero losers satisfied the
   quality half outright.
B. An all-winners sample gives PF = inf, which was reported as a passing 99.0.
   Infinite PF means "no losses observed yet" — a statement about sample size,
   not about edge.

Plus the window reset: GATE_START_DATE moved to the history-based stop fix
(a0a50b86, 2026-07-17). Before it the -8% stop did not bind — 7 of 42 closed
trades ran past it, worst -22.1% — so that history measures a risk model the
code no longer implements.
"""

import os
import sys
import json
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from report_generator import (                                        # noqa: E402
    _build_action_box, GATE_START_DATE, GATE_MIN_TRADES, GATE_MIN_WINRATE,
)

STOP_FIX_COMMIT_DATE = "2026-07-17"


def _trades(n_win, n_loss, signal_date="2026-07-20", win=50.0, loss=-50.0):
    out = []
    for i in range(n_win):
        out.append(_t(f"W{i}", signal_date, win))
    for i in range(n_loss):
        out.append(_t(f"L{i}", signal_date, loss))
    return out


def _t(ticker, signal_date, pnl):
    return {
        "ticker": ticker, "status": "closed",
        "signal_date": signal_date, "exit_date": "2026-07-30",
        "pnl": pnl, "pnl_pct": pnl / 10,
        "notional": 1000, "entry_price": 100, "shares": 10,
    }


def _gate(trades):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "paper_portfolio.json"), "w") as f:
        json.dump({"trades": trades}, f)
    return _build_action_box([], d)


# ── A. Minimum sample size ────────────────────────────────────────────────────

def test_window_starts_at_the_stop_fix():
    assert GATE_START_DATE == STOP_FIX_COMMIT_DATE


def test_two_winners_no_longer_satisfy_the_gate():
    """The exact shape that used to pass: tiny all-winning sample."""
    box = _gate(_trades(n_win=2, n_loss=0))

    assert box["gate_trades"] == 2
    assert box["gate_enough"] is False
    assert box["gate_ready"] is False


def test_just_below_the_floor_is_not_enough():
    box = _gate(_trades(n_win=GATE_MIN_TRADES - 1, n_loss=0))

    assert box["gate_enough"] is False
    assert box["gate_ready"] is False


def test_floor_reached_reports_enough_data():
    box = _gate(_trades(n_win=GATE_MIN_TRADES, n_loss=0))

    assert box["gate_trades"] == GATE_MIN_TRADES
    assert box["gate_enough"] is True


def test_strong_but_undersized_sample_still_blocked():
    """A 90% win rate over 10 trades must not open the gate."""
    box = _gate(_trades(n_win=9, n_loss=1))

    assert box["gate_winrate"] > GATE_MIN_WINRATE
    assert box["gate_enough"] is False
    assert box["gate_ready"] is False


# ── B. Infinite profit factor ─────────────────────────────────────────────────

def test_no_losses_reports_pf_as_none_not_a_passing_score():
    """PF was mapped to 99.0, which read as an excellent profit factor."""
    box = _gate(_trades(n_win=GATE_MIN_TRADES, n_loss=0))

    assert box["gate_pf"] is None


def test_finite_pf_is_still_reported():
    box = _gate(_trades(n_win=10, n_loss=10, win=130.0, loss=-100.0))

    assert box["gate_pf"] == pytest.approx(1.3, abs=0.01)


# ── Window membership keys on entry date ──────────────────────────────────────

def test_trades_entered_before_the_stop_fix_are_excluded():
    """Pre-fix trades ran under a stop that did not bind — they must not count,
    even though they closed inside the window."""
    pre = _t("OLD", "2026-06-19", -220.0)      # the -22.1% ON trade shape
    post = _trades(n_win=3, n_loss=0)

    box = _gate([pre] + post)

    assert box["gate_trades"] == 3
    assert box["gate_pnl"] > 0        # the -220 pre-fix loss is not counted


# ── Confidence interval is published alongside the point estimate ─────────────

def test_confidence_interval_is_exposed():
    box = _gate(_trades(n_win=15, n_loss=15))

    assert box["gate_winrate"] == 50.0
    assert box["gate_ci_low"] < 50.0 < box["gate_ci_high"]
    assert 0.0 <= box["gate_ci_low"] and box["gate_ci_high"] <= 100.0


def test_empty_window_has_no_interval():
    box = _gate([])

    assert box["gate_trades"] == 0
    assert box["gate_ci_low"] is None
    assert box["gate_enough"] is False
    assert box["gate_ready"] is False
