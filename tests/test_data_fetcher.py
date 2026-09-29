"""fetch_stock_data must ignore a trailing bar with no close.

Yahoo sometimes returns a placeholder bar for the new session with NaN
Close/OHLC (seen on every price-refresh run that fired just after 00:00 UTC).
Taking iloc[-1] blindly turned every price into NaN and every TA score into
garbage — SPY fell from 36 to 12 and the regime gate locked new entries.
"""
import math
import sys
from pathlib import Path
from unittest.mock import patch

import pandas as pd

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "src"))

import data_fetcher  # noqa: E402


class _FakeTicker:
    def __init__(self, hist):
        self._hist = hist
        self.info = {"shortName": "Fake Co", "sector": "Technology"}
        self.news = []

    def history(self, period):
        return self._hist


def _hist(closes, volumes):
    idx = pd.date_range("2026-09-01", periods=len(closes), freq="B")
    return pd.DataFrame(
        {
            "Open": closes,
            "High": closes,
            "Low": closes,
            "Close": closes,
            "Volume": volumes,
        },
        index=idx,
    )


def _fetch(hist):
    with patch.object(data_fetcher.yf, "Ticker", return_value=_FakeTicker(hist)):
        return data_fetcher.fetch_stock_data("FAKE")


def test_trailing_nan_bar_is_dropped():
    hist = _hist([100, 101, 102, 103, 104, 105, float("nan")], [1, 1, 1, 1, 1, 1, 0])

    data = _fetch(hist)

    assert data is not None
    assert data["current_price"] == 105
    assert data["prev_close"] == 104
    assert not math.isnan(data["price_change_pct"])
    assert not data["history"]["Close"].isna().any()


def test_clean_history_is_unchanged():
    hist = _hist([100, 101, 102, 103, 104, 105], [1, 1, 1, 1, 1, 1])

    data = _fetch(hist)

    assert data["current_price"] == 105
    assert len(data["history"]) == 6


def test_too_few_valid_bars_returns_none():
    nan = float("nan")
    hist = _hist([100, 101, 102, nan, nan, nan], [1, 1, 1, 0, 0, 0])

    assert _fetch(hist) is None
