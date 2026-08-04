"""Tests for the shared entry selector (fix 2026-08-05).

Measured over 2026-07-17..08-04, the Action Box published BUY tickets for 37
tickers while the paper engine opened 9, overlapping on 6. The page and the
validation record described two different strategies. These tests pin the
behaviour that must now hold for BOTH callers, because both go through
entry_selection.select_entries().

Run: python3 -m pytest tests/test_entry_selection.py
"""

import json
import os
import sys
import tempfile
from datetime import datetime, timedelta

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from entry_selection import (                                        # noqa: E402
    FALLBACK_EQUITY_USD, HIGH_CONVICTION_MIN, MAX_OPEN_POSITIONS,
    MAX_PER_SECTOR, REGIME_FLOOR, REGIME_NORMAL,
    account_equity_usd, entry_timing_ok, position_notional, select_entries,
)


def _stock(ticker, score, label="GO", price=100.0, vol_ratio=1.5,
           sector="Technology", ema200=0):
    return {
        "ticker": ticker, "score": score, "price": price,
        "vol_ratio": vol_ratio, "sector": sector, "ema200": ema200,
        "entry_verdict": {"label": label, "reason": f"Score {score}"},
    }


def _open(ticker, sector="Technology"):
    return {"ticker": ticker, "status": "open", "direction": "long", "sector": sector}


@pytest.fixture
def outdir():
    """Empty output dir — no broker snapshot, so sizing uses the fallback."""
    return tempfile.mkdtemp()


def _equity_file(d, net_liq_usd, days_old=0, currency="USD", converted=True):
    synced = (datetime.now() - timedelta(days=days_old)).strftime("%Y-%m-%d")
    account = {"net_liquidation": net_liq_usd, "currency": currency}
    if converted:
        account["net_liquidation_usd"] = net_liq_usd
    with open(os.path.join(d, "ibkr_positions.json"), "w") as f:
        json.dump({"synced_at": synced, "account": account, "positions": []}, f)
    return d


# ── Regime gate ───────────────────────────────────────────────────────────────

def test_bear_regime_selects_nothing(outdir):
    stocks = [_stock("SPY", REGIME_FLOOR - 1), _stock("AAA", 95)]
    entries, ctx = select_entries(stocks, [], output_dir=outdir)
    assert ctx["regime"] == "bear"
    assert entries == []


def test_missing_spy_fails_closed(outdir):
    entries, ctx = select_entries([_stock("AAA", 100)], [], output_dir=outdir)
    assert ctx["regime"] == "unknown"
    assert entries == []


def test_transitional_requires_high_conviction(outdir):
    stocks = [_stock("SPY", REGIME_NORMAL - 1),
              _stock("HIGH", HIGH_CONVICTION_MIN, sector="Tech"),
              _stock("LOW", HIGH_CONVICTION_MIN - 1, sector="Health")]
    entries, _ = select_entries(stocks, [], output_dir=outdir)
    assert [e["ticker"] for e in entries] == ["HIGH"]


# ── Timing gates — the union of what the two callers each used to apply ──────

def test_wait_verdict_is_skipped():
    assert not entry_timing_ok(_stock("AAA", 95, label="WAIT ⏸"))


def test_squeeze_breakout_needs_volume():
    """The Action Box required this; the engine did not. Now both do."""
    assert not entry_timing_ok(_stock("AAA", 95, label="BREAKOUT ↑", vol_ratio=0.8))
    assert entry_timing_ok(_stock("AAA", 95, label="BREAKOUT ↑", vol_ratio=1.2))


def test_price_below_ema200_is_skipped():
    """The engine required this; the Action Box did not. Now both do."""
    assert not entry_timing_ok(_stock("AAA", 95, price=90.0, ema200=100.0))
    assert entry_timing_ok(_stock("AAA", 95, price=110.0, ema200=100.0))


# ── Portfolio caps ────────────────────────────────────────────────────────────

def test_sector_cap_applies_within_one_pass(outdir):
    """Three same-sector candidates in one run must not all be selected."""
    stocks = [_stock("SPY", REGIME_NORMAL)] + [
        _stock(t, 90, sector="Technology") for t in ("AAA", "BBB", "CCC")
    ]
    entries, _ = select_entries(stocks, [], output_dir=outdir)
    assert len(entries) == MAX_PER_SECTOR


def test_position_cap_limits_total_open(outdir):
    stocks = [_stock("SPY", REGIME_NORMAL)] + [
        _stock(f"T{i}", 90, sector=f"S{i}") for i in range(MAX_OPEN_POSITIONS + 3)
    ]
    entries, ctx = select_entries(stocks, [], output_dir=outdir)
    assert len(entries) == MAX_OPEN_POSITIONS == ctx["slots_left"]


def test_existing_open_positions_consume_slots(outdir):
    stocks = [_stock("SPY", REGIME_NORMAL)] + [
        _stock(f"T{i}", 90, sector=f"S{i}") for i in range(5)
    ]
    held = [_open(f"H{i}", sector=f"H{i}") for i in range(MAX_OPEN_POSITIONS - 1)]
    entries, ctx = select_entries(stocks, held, output_dir=outdir)
    assert ctx["slots_left"] == 1
    assert len(entries) == 1


def test_already_held_ticker_is_not_reselected(outdir):
    stocks = [_stock("SPY", REGIME_NORMAL), _stock("AAA", 90)]
    entries, _ = select_entries(stocks, [_open("AAA")], output_dir=outdir)
    assert entries == []


def test_validator_veto_reaches_the_selector(outdir):
    """The veto used to reach the engine but never the published ticket."""
    stocks = [_stock("SPY", REGIME_NORMAL), _stock("AAA", 90), _stock("BBB", 85, sector="Health")]
    entries, _ = select_entries(stocks, [], blocked_tickers={"AAA"}, output_dir=outdir)
    assert [e["ticker"] for e in entries] == ["BBB"]


# ── Sizing ────────────────────────────────────────────────────────────────────

def test_notional_scales_with_equity_not_a_fixed_unit():
    """A $1,500 ticket against a USD 4,650 account asked for 32% of everything."""
    small = position_notional(80, 4650.0)
    big = position_notional(80, 46500.0)
    assert big == pytest.approx(small * 10)
    assert small < 4650.0 * 0.15


def test_notional_rises_with_conviction():
    eq = 10000.0
    assert position_notional(95, eq) > position_notional(85, eq) > position_notional(75, eq)


def test_total_exposure_is_bounded(outdir):
    """Position cap x top band must leave the account solvent."""
    eq = 10000.0
    assert MAX_OPEN_POSITIONS * position_notional(100, eq) <= eq


def test_equity_read_from_broker_snapshot(outdir):
    _equity_file(outdir, 8000.0)
    equity, basis = account_equity_usd(outdir)
    assert (equity, basis) == (8000.0, "ibkr")


def test_stale_equity_falls_back(outdir):
    _equity_file(outdir, 8000.0, days_old=30)
    equity, basis = account_equity_usd(outdir)
    assert (equity, basis) == (FALLBACK_EQUITY_USD, "fallback")


def test_missing_snapshot_falls_back(outdir):
    assert account_equity_usd(outdir) == (FALLBACK_EQUITY_USD, "fallback")


def test_unconverted_foreign_currency_is_not_read_as_usd(outdir):
    """HKD 36,215 read as USD would oversize every ticket ~8x."""
    _equity_file(outdir, 36215.0, currency="HKD", converted=False)
    equity, basis = account_equity_usd(outdir)
    assert (equity, basis) == (FALLBACK_EQUITY_USD, "fallback")


def test_selected_entries_carry_sizing_context(outdir):
    _equity_file(outdir, 8000.0)
    stocks = [_stock("SPY", REGIME_NORMAL), _stock("AAA", 90)]
    entries, ctx = select_entries(stocks, [], output_dir=outdir)
    assert ctx["sizing_basis"] == "ibkr"
    assert entries[0]["notional"] == position_notional(90, 8000.0)
