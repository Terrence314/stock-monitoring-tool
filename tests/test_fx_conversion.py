"""FX conversion must actually convert (fix 2026-08-09).

`_fx_rates` did `float(raw["Close"].dropna().iloc[-1])`. yfinance returns
column-MultiIndexed frames, so `raw["Close"]` is a single-column DataFrame and
`.iloc[-1]` is a Series — float() on it raises every time. The bare `except`
below it logged "FX unavailable" and carried on, so:

  * every `*_usd` field in ibkr_positions.json published as null;
  * entry_selection.account_equity_usd saw no usable USD figure and fell back
    to the default equity even on a freshly synced account.

The failure was invisible because its handler made it look like an upstream
outage. These tests pin the frame shape rather than hitting the network.

Run: python3 -m pytest tests/test_fx_conversion.py
"""

import os
import sys
from datetime import date, timedelta

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from entry_selection import (                                         # noqa: E402
    EQUITY_MAX_AGE_DAYS, FALLBACK_EQUITY_USD, account_equity_usd,
)


def _yf_shaped_frame(values):
    """A frame shaped like yfinance's: columns MultiIndexed by (field, ticker)."""
    cols = pd.MultiIndex.from_tuples([("Close", "HKDUSD=X")])
    return pd.DataFrame([[v] for v in values], columns=cols)


def test_close_column_is_a_frame_not_a_series():
    """The premise of the bug — if this ever changes, the squeeze is harmless."""
    raw = _yf_shaped_frame([0.1274, 0.1275])
    assert isinstance(raw["Close"], pd.DataFrame)
    with pytest.raises(TypeError):
        float(raw["Close"].dropna().iloc[-1])


def test_squeeze_yields_a_usable_rate():
    """The fix: squeeze the single column before taking the last value."""
    raw = _yf_shaped_frame([0.1274, 0.12748])
    close = raw["Close"].squeeze("columns").dropna()
    assert float(close.iloc[-1]) == pytest.approx(0.12748)


def test_squeeze_is_safe_on_a_plain_frame():
    """Non-MultiIndexed frames must survive the same path unchanged."""
    raw = pd.DataFrame({"Close": [0.1274, 0.12748]})
    close = raw["Close"].squeeze().dropna()
    assert float(close.iloc[-1]) == pytest.approx(0.12748)


# ── The consequence the bug had downstream ────────────────────────────────────

def test_unconverted_account_does_not_size_positions(tmp_path):
    """An HKD account with no usable USD figure must NOT be read at face value.

    HKD 36,854 taken as USD would size every ticket ~7.8x too large.
    """
    import json
    (tmp_path / "ibkr_positions.json").write_text(json.dumps({
        "synced_at": date.today().isoformat(),   # fresh: isolate the currency rule
        "account": {"net_liquidation": 36854.05, "currency": "HKD",
                    "net_liquidation_usd": None},
    }))
    equity, basis = account_equity_usd(str(tmp_path))
    assert (equity, basis) == (FALLBACK_EQUITY_USD, "fallback")


def test_converted_account_is_used(tmp_path):
    """A FRESH converted figure is used.

    This test used to hardcode synced_at: 2026-08-09 and started failing on
    2026-08-16 — not because anything broke, but because the fixture aged past
    EQUITY_MAX_AGE_DAYS and account_equity_usd correctly rejected it. A test
    that passes only during the week it was written is a time bomb: it goes red
    on an unrelated day and trains you to ignore the suite. The date is now
    computed from the clock, and the staleness rule gets its own test below.
    """
    import json
    fresh = date.today().isoformat()
    (tmp_path / "ibkr_positions.json").write_text(json.dumps({
        "synced_at": fresh,
        "account": {"net_liquidation": 36854.05, "currency": "HKD",
                    "fx_rate": 0.12748, "net_liquidation_usd": 4698.25},
    }))
    equity, basis = account_equity_usd(str(tmp_path))
    assert (equity, basis) == (4698.25, "ibkr")


def test_a_stale_sync_falls_back_rather_than_sizing_on_old_equity(tmp_path):
    """The rule that made the test above rot — asserted deliberately.

    A dead IBKR sync must not keep sizing tickets off a figure from weeks ago.
    Sizing silently reverts to the fallback and the UI labels it 估算.
    """
    import json
    stale = (date.today() - timedelta(days=EQUITY_MAX_AGE_DAYS + 1)).isoformat()
    (tmp_path / "ibkr_positions.json").write_text(json.dumps({
        "synced_at": stale,
        "account": {"net_liquidation": 36854.05, "currency": "HKD",
                    "fx_rate": 0.12748, "net_liquidation_usd": 4698.25},
    }))
    equity, basis = account_equity_usd(str(tmp_path))
    assert (equity, basis) == (FALLBACK_EQUITY_USD, "fallback")


def test_the_freshness_boundary_is_inclusive(tmp_path):
    """Exactly EQUITY_MAX_AGE_DAYS old still counts as fresh."""
    import json
    edge = (date.today() - timedelta(days=EQUITY_MAX_AGE_DAYS)).isoformat()
    (tmp_path / "ibkr_positions.json").write_text(json.dumps({
        "synced_at": edge,
        "account": {"net_liquidation": 36854.05, "currency": "HKD",
                    "fx_rate": 0.12748, "net_liquidation_usd": 4698.25},
    }))
    equity, basis = account_equity_usd(str(tmp_path))
    assert (equity, basis) == (4698.25, "ibkr")
