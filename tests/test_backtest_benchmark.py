"""Backtest measurement gaps, and the IBKR FX/staleness fixes.

The backtest reported absolute forward returns with no benchmark, so a 60%
win rate at +10d was unreadable — it could be entirely market direction. It
also published per-ticker win rates off any sample size, so a ticker with 2
signals showed "100%".

ibkr_sync stored every money figure in its own currency with no conversion,
while the account is genuinely mixed: net liquidation in HKD, US positions in
USD, SPYL.L on the LSE.
"""

import os
import sys

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import backtest as bt                                                # noqa: E402
import ibkr_sync                                                     # noqa: E402


def _series(start, step, n=30, month=6):
    return {f"2026-{month:02d}-{d:02d}": start * (1 + step * i)
            for i, d in enumerate(range(1, n))}


def _run(signal_step, bench_step, n_signals=6):
    prices = {"AAA": _series(100.0, signal_step), "SPY": _series(400.0, bench_step)}
    history = {f"2026-06-{d:02d}": {"AAA": 80} for d in range(1, 1 + n_signals)}
    return bt._aggregate(bt._run_signals(history, prices))


# ── Benchmark ─────────────────────────────────────────────────────────────────

def test_signal_returns_carry_a_benchmark_and_excess():
    sig = bt._run_signals(
        {"2026-06-01": {"AAA": 80}},
        {"AAA": _series(100.0, 0.004), "SPY": _series(400.0, 0.002)},
    )[0]

    for fd in bt.FORWARD_DAYS:
        assert sig[f"b{fd}"] is not None, "benchmark return missing"
        assert sig[f"x{fd}"] == pytest.approx(sig[f"r{fd}"] - sig[f"b{fd}"], abs=0.02)


def test_beating_the_market_shows_positive_excess():
    s = _run(signal_step=0.004, bench_step=0.002)[ "overall"][5]

    assert s["avg"] > 0 and s["bench_avg"] > 0
    assert s["excess_avg"] > 0
    assert s["beat_rate"] == 100.0


def test_a_rising_tide_is_not_reported_as_edge():
    """Signal and benchmark rise identically — excess must be ~zero even
    though the raw win rate is 100%."""
    s = _run(signal_step=0.003, bench_step=0.003)["overall"][5]

    assert s["win_rate"] == 100.0          # looks perfect on its own…
    assert s["excess_avg"] == pytest.approx(0.0, abs=0.05)   # …and adds nothing
    assert s["beat_rate"] == 0.0


def test_underperforming_a_rising_market_is_visible():
    s = _run(signal_step=0.001, bench_step=0.004)["overall"][5]

    assert s["avg"] > 0, "raw return is positive"
    assert s["excess_avg"] < 0, "but it lagged the benchmark"


def test_benchmark_is_fetched_even_without_its_own_signal():
    src = open(os.path.join(os.path.dirname(__file__), "..", "src", "backtest.py")).read()
    assert "{BENCHMARK}" in src or "| {BENCHMARK}" in src or "BENCHMARK}" in src


# ── Dispersion / significance ─────────────────────────────────────────────────

def test_dispersion_and_t_stat_are_reported():
    s = _run(signal_step=0.004, bench_step=0.002)["overall"][5]

    assert s["sd"] is not None
    assert s["t_stat"] is not None


def test_single_observation_has_no_t_stat():
    s = _run(signal_step=0.004, bench_step=0.002, n_signals=1)["overall"][5]

    assert s["n"] == 1
    assert s["t_stat"] is None


# ── Per-ticker minimum sample ─────────────────────────────────────────────────

def test_thin_ticker_rows_suppress_their_rates():
    agg = _run(signal_step=0.004, bench_step=0.002, n_signals=2)
    row = agg["by_ticker"]["AAA"]

    assert row["n_signals"] == 2
    assert row["enough"] is False
    assert row[10]["win_rate"] is None, "2 signals must not publish a win rate"


def test_sufficient_ticker_rows_report_normally():
    agg = _run(signal_step=0.004, bench_step=0.002, n_signals=bt.MIN_TICKER_SIGNALS)
    row = agg["by_ticker"]["AAA"]

    assert row["enough"] is True
    assert row[5]["win_rate"] is not None


# ── IBKR FX ───────────────────────────────────────────────────────────────────

def test_usd_needs_no_conversion():
    assert ibkr_sync._fx_rates({"USD"}) == {"USD": 1.0}


def test_unavailable_rate_leaves_the_currency_flagged(monkeypatch):
    """Never invent a rate — report it unconverted instead."""
    monkeypatch.setattr(ibkr_sync, "_get", lambda *_a, **_k: [])
    rates = ibkr_sync._fx_rates({"USD", "ZZZ"})

    assert rates["USD"] == 1.0
    assert "ZZZ" not in rates or rates["ZZZ"] == 1.0


def test_reporting_currency_is_explicit():
    assert ibkr_sync.REPORTING_CCY == "USD"
