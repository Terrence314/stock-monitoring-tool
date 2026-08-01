"""Regression tests for the two gates that existed but never fired.

A. The EMA200 long-term trend filter in paper_trading._entry_timing_ok read
   `s.get("ema200")`, but main.py never copied that field into stock_results,
   so the value was always None -> `or 0` -> falsy -> the filter was skipped
   for every ticker on every run.

B. signal_validator vetoed BUYs for the Telegram message only. run_paper_trading
   was called without that veto list, so the tracked paper record included
   positions the user was explicitly never alerted to (e.g. NTES, blocked
   2026-07-31 with "AI review REJECTED", still opened by the engine).
"""

import os
import sys
import json
import inspect
import tempfile

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import paper_trading                                                 # noqa: E402
from paper_trading import run_paper_trading, REGIME_NORMAL           # noqa: E402


def _result(ticker, score, price=100.0, ema200=None, macd=1.0):
    s = {
        "ticker": ticker,
        "score": score,
        "price": price,
        "macd": macd,
        "sector": "Technology",
        "entry_verdict": {"label": "GO", "reason": ""},
    }
    if ema200 is not None:
        s["ema200"] = ema200
    return s


@pytest.fixture
def portfolio(tmp_path, monkeypatch):
    p = tmp_path / "paper_portfolio.json"
    p.write_text(json.dumps({"trades": [], "last_updated": ""}))
    monkeypatch.setattr(paper_trading, "PORTFOLIO_FILE", str(p))
    # Keep the test offline — the calendar/OHLC sweeps hit yfinance.
    monkeypatch.setattr(paper_trading, "_fetch_calendar", lambda *_a, **_k: [])
    monkeypatch.setattr(paper_trading, "_fetch_ohlc_bulk", lambda *_a, **_k: {})
    monkeypatch.setattr(paper_trading, "_fetch_prices_bulk", lambda *_a, **_k: {})
    return p


def _opened(portfolio_path):
    return {t["ticker"] for t in json.loads(portfolio_path.read_text())["trades"]}


# ── A. EMA200 gate ────────────────────────────────────────────────────────────

def test_ema200_is_exported_by_the_pipeline():
    """main.py must copy ema200 into stock_results or the gate is dead code."""
    src = open(os.path.join(os.path.dirname(__file__), "..", "src", "main.py")).read()
    assert '"ema200"' in src, "main.py no longer exports ema200 to stock_results"

    src_pr = open(os.path.join(os.path.dirname(__file__), "..", "src", "price_refresh.py")).read()
    assert '"ema200"' in src_pr, "price_refresh.py no longer exports ema200"


def test_long_below_ema200_is_skipped(portfolio, tmp_path):
    stock_results = [
        _result("SPY", REGIME_NORMAL),
        _result("BELOW", 90, price=90.0, ema200=120.0),   # downtrend -> skip
        _result("ABOVE", 90, price=150.0, ema200=120.0),  # uptrend  -> open
    ]
    scores = {"BELOW": 90, "ABOVE": 90}

    run_paper_trading("2026-08-03", scores, stock_results,
                      output_dir=str(tmp_path))

    opened = _opened(portfolio)
    assert "ABOVE" in opened
    assert "BELOW" not in opened


# ── B. Validator veto reaches the engine ──────────────────────────────────────

def test_run_paper_trading_accepts_blocked_tickers():
    assert "blocked_tickers" in inspect.signature(run_paper_trading).parameters


def test_blocked_ticker_is_not_opened(portfolio, tmp_path):
    stock_results = [
        _result("SPY", REGIME_NORMAL),
        _result("VETOED", 90, price=150.0, ema200=100.0),
        _result("CLEAN", 90, price=150.0, ema200=100.0),
    ]
    scores = {"VETOED": 90, "CLEAN": 90}

    run_paper_trading("2026-08-03", scores, stock_results,
                      output_dir=str(tmp_path),
                      blocked_tickers={"VETOED"})

    opened = _opened(portfolio)
    assert "CLEAN" in opened
    assert "VETOED" not in opened, "validator veto did not reach the engine"


def test_missing_spy_blocks_all_entries(portfolio, tmp_path):
    """Fail closed: the old default of 55 put a failed SPY fetch into buying."""
    stock_results = [_result("AAA", 100, price=150.0, ema200=100.0)]

    run_paper_trading("2026-08-03", {"AAA": 100}, stock_results,
                      output_dir=str(tmp_path))

    assert _opened(portfolio) == set()
