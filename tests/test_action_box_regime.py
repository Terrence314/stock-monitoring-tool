"""Regression tests for the four Action Box / paper-engine divergences found
on 2026-08-01, when the dashboard published BUY tickets for 12 straight days
that the paper engine refused to open.

1. Action Box had no market-regime gate (paper engine did) — SPY score 23
   held every entry while the page kept printing tickets.
2. Ticket size was the hardcoded string "$1,000" for every trade, while the
   engine sizes $1,000 / $1,500 / $2,000 by conviction.
3. Stop/target percentages were re-typed as literals in three places.
4. A missing SPY defaulted to a score of 55 — above REGIME_NORMAL — so a
   failed fetch put the engine into normal buying.
"""

import os
import sys
import json
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from report_generator import _build_action_box                      # noqa: E402
from paper_trading import (                                          # noqa: E402
    STOP_LOSS_PCT, TAKE_PROFIT_PCT, HOLD_DAYS,
    REGIME_FLOOR, REGIME_NORMAL, HIGH_CONVICTION_MIN,
    _notional_for_score,
)
from entry_selection import account_equity_usd                       # noqa: E402


def _stock(ticker, score, label="GO", price=100.0, vol_ratio=1.5):
    return {
        "ticker": ticker,
        "score": score,
        "price": price,
        "vol_ratio": vol_ratio,
        "sector": "Technology",
        "entry_verdict": {"label": label, "reason": f"Score {score}"},
    }


@pytest.fixture
def outdir():
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "paper_portfolio.json"), "w") as f:
        json.dump({"trades": []}, f)
    yield d


# ── 1. Regime gate ────────────────────────────────────────────────────────────

def test_bear_regime_publishes_no_buys(outdir):
    """SPY below REGIME_FLOOR must suppress tickets, matching the engine."""
    stocks = [_stock("SPY", REGIME_FLOOR - 1), _stock("AAA", 95)]

    box = _build_action_box(stocks, outdir)

    assert box["regime"] == "bear"
    assert box["buys"] == []
    assert box["no_action"] is True


def test_transitional_regime_requires_high_conviction(outdir):
    """Between FLOOR and NORMAL only score >= HIGH_CONVICTION_MIN qualifies."""
    stocks = [
        _stock("SPY", REGIME_NORMAL - 1),
        _stock("HIGH", HIGH_CONVICTION_MIN),
        _stock("LOW", HIGH_CONVICTION_MIN - 1),
    ]

    box = _build_action_box(stocks, outdir)

    assert box["regime"] == "transitional"
    assert [b["ticker"] for b in box["buys"]] == ["HIGH"]


def test_bull_regime_uses_base_threshold(outdir):
    stocks = [_stock("SPY", REGIME_NORMAL), _stock("AAA", 70), _stock("BBB", 69)]

    box = _build_action_box(stocks, outdir)

    assert box["regime"] == "bull"
    assert [b["ticker"] for b in box["buys"]] == ["AAA"]


def test_missing_spy_fails_closed(outdir):
    """No SPY score must block new entries, not fall through to buying."""
    stocks = [_stock("AAA", 100)]

    box = _build_action_box(stocks, outdir)

    assert box["regime"] == "unknown"
    assert box["buys"] == []


# ── 2. Conviction-weighted ticket size ────────────────────────────────────────

@pytest.mark.parametrize("score", [70, 80, 95])
def test_ticket_carries_engine_notional(outdir, score):
    """The ticket used to say "$1,000" regardless of conviction sizing.

    The literal dollar amounts this once asserted retired on 2026-08-05, when
    sizing moved from a fixed $1,000/$1,500/$2,000 unit to a percent of account
    equity — a $1,500 ticket was 32% of a USD 4,650 account. What must hold is
    unchanged: the published ticket and the engine size the same position.
    """
    stocks = [_stock("SPY", REGIME_NORMAL), _stock("AAA", score)]

    box = _build_action_box(stocks, outdir)

    equity, _basis = account_equity_usd(outdir)
    assert box["buys"][0]["notional"] == _notional_for_score(score, equity)


def test_ticket_size_still_scales_with_conviction(outdir):
    equity, _basis = account_equity_usd(outdir)
    sizes = [_notional_for_score(s, equity) for s in (70, 85, 95)]
    assert sizes[0] < sizes[1] < sizes[2]


# ── 3. Stop/target derived from the engine's constants ────────────────────────

def test_stop_and_target_derive_from_constants(outdir):
    price = 250.0
    stocks = [_stock("SPY", REGIME_NORMAL), _stock("AAA", 80, price=price)]

    buy = _build_action_box(stocks, outdir)["buys"][0]

    assert buy["stop"] == round(price * (1 - STOP_LOSS_PCT / 100), 2)
    assert buy["target"] == round(price * (1 + TAKE_PROFIT_PCT / 100), 2)


def test_box_exports_constants_for_every_surface(outdir):
    """Dashboard and Telegram read these instead of re-typing literals."""
    box = _build_action_box([_stock("SPY", REGIME_NORMAL)], outdir)

    assert box["stop_pct"] == STOP_LOSS_PCT
    assert box["target_pct"] == TAKE_PROFIT_PCT
    assert box["hold_days"] == HOLD_DAYS


# ── 4. Volume confirmation still applies to squeeze breakouts ─────────────────

def test_squeeze_breakout_still_needs_volume(outdir):
    stocks = [
        _stock("SPY", REGIME_NORMAL),
        _stock("THIN", 90, label="BREAKOUT ↑", vol_ratio=0.4),
        _stock("FAT", 90, label="BREAKOUT ↑", vol_ratio=1.1),
    ]

    box = _build_action_box(stocks, outdir)

    assert [b["ticker"] for b in box["buys"]] == ["FAT"]
