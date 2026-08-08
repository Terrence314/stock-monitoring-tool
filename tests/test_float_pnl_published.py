"""Open positions must publish their unrealized P&L (fix 2026-08-08).

Found by the daily portfolio cross-check, not by this repo's own tests: every
open position in the published paper_portfolio.json carried `pnl: null` and
`pnl_pct: null`, because those keys are written only at exit. All 11 open
positions on gh-pages were null on 2026-08-07. Any consumer of the published
file either rediscovered (current - entry) * shares itself or scored the
position as zero.

The figures go in SEPARATE keys — `float_pnl` / `float_pnl_pct` — rather than
filling in `pnl`. Several call sites sum `pnl` over a trade list without
filtering on status, and unrealized money inside a realized total is a worse
bug than a null.

Run: python3 -m pytest tests/test_float_pnl_published.py
"""

import json
import os
import sys
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import paper_trading as pt                                           # noqa: E402
from paper_trading import _publish_float_pnl                         # noqa: E402


def _open_trade(entry=100.0, current=110.0, shares=10.0, direction="long"):
    return {
        "ticker": "TEST", "direction": direction, "status": "open",
        "entry_price": entry, "current_price": current, "shares": shares,
        "pnl": None, "pnl_pct": None,
    }


# ── The figure itself ─────────────────────────────────────────────────────────

def test_long_gain_is_published():
    t = _open_trade(entry=100.0, current=110.0, shares=10.0)
    _publish_float_pnl(t)
    assert t["float_pnl"] == 100.0
    assert t["float_pnl_pct"] == 10.0


def test_long_loss_is_published():
    t = _open_trade(entry=100.0, current=92.0, shares=10.0)
    _publish_float_pnl(t)
    assert t["float_pnl"] == -80.0
    assert t["float_pnl_pct"] == -8.0


def test_short_direction_inverts():
    t = _open_trade(entry=100.0, current=90.0, shares=10.0, direction="short")
    _publish_float_pnl(t)
    assert t["float_pnl"] == 100.0


def test_unmarked_position_reports_zero_not_null():
    """No current_price yet — flat is a number; null forces every reader to guess."""
    t = _open_trade(entry=100.0, shares=10.0)
    t["current_price"] = None
    _publish_float_pnl(t)
    assert t["float_pnl"] == 0.0


# ── Separation from realized P&L ──────────────────────────────────────────────

def test_realized_pnl_is_left_alone():
    """Filling in `pnl` would put unrealized money into realized totals."""
    t = _open_trade(entry=100.0, current=110.0, shares=10.0)
    _publish_float_pnl(t)
    assert t["pnl"] is None and t["pnl_pct"] is None


def test_closed_trades_do_not_publish_a_stale_float(tmp_path, monkeypatch):
    """A closed position's last mark must not survive into the published file."""
    portfolio = {"trades": [
        {"ticker": "OPEN", "status": "open", "direction": "long",
         "entry_price": 100.0, "current_price": 110.0, "shares": 10.0,
         "float_pnl": 100.0, "float_pnl_pct": 10.0},
        {"ticker": "SHUT", "status": "closed", "direction": "long",
         "entry_price": 100.0, "current_price": 110.0, "shares": 10.0,
         "pnl": 95.0, "pnl_pct": 9.5, "float_pnl": 100.0, "float_pnl_pct": 10.0},
    ]}
    out = tmp_path / "paper_portfolio.json"
    monkeypatch.setattr(pt, "PORTFOLIO_FILE", str(out))

    pt._save_portfolio(portfolio)

    saved = {t["ticker"]: t for t in json.loads(out.read_text())["trades"]}
    assert "float_pnl" not in saved["SHUT"], "stale unrealized left on a closed trade"
    assert saved["SHUT"]["pnl"] == 95.0, "realized P&L must be untouched"
    assert saved["OPEN"]["float_pnl"] == 100.0, "open position must keep its float"


def test_no_open_position_publishes_null_float():
    """The exact shape found on gh-pages: 11 open positions, all null."""
    trades = [_open_trade(entry=100.0 + i, current=105.0 + i) for i in range(11)]
    for t in trades:
        _publish_float_pnl(t)
    assert all(t["float_pnl"] is not None for t in trades)
