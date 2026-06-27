"""polygon_fetcher.py — Polygon.io data fetcher (drop-in enhancement for data_fetcher.py).

Free tier: 5 API calls/min, 2 years daily OHLCV, no real-time.
Used as primary source; data_fetcher.py yfinance is the fallback.

Set POLYGON_API_KEY in config/secrets.json or env var.
"""
import os
import time
import requests
import pandas as pd
from datetime import datetime, timedelta

_BASE = "https://api.polygon.io"
_LAST_CALL = 0.0
_MIN_INTERVAL = 12.1  # 5 calls/min free tier → 12s between calls


def _api_key() -> str:
    return os.getenv("POLYGON_API_KEY", "")


def _get(path: str, params: dict = None) -> dict | None:
    global _LAST_CALL
    key = _api_key()
    if not key:
        return None
    # Rate limit: free tier = 5 req/min
    elapsed = time.time() - _LAST_CALL
    if elapsed < _MIN_INTERVAL:
        time.sleep(_MIN_INTERVAL - elapsed)
    _LAST_CALL = time.time()

    url = f"{_BASE}{path}"
    p = {"apiKey": key, **(params or {})}
    try:
        r = requests.get(url, params=p, timeout=10)
        if r.status_code == 200:
            return r.json()
        return None
    except Exception:
        return None


def fetch_stock_data_polygon(ticker: str, period: str = "6mo") -> dict | None:
    """Fetch OHLCV from Polygon — returns same shape as data_fetcher.fetch_stock_data.

    Returns None if key not set or request fails (caller falls back to yfinance).
    """
    if not _api_key():
        return None

    # Map period to date range
    end   = datetime.today()
    days  = {"6mo": 180, "3mo": 90, "1y": 365, "2y": 730}.get(period, 180)
    start = end - timedelta(days=days)

    data = _get(
        f"/v2/aggs/ticker/{ticker}/range/1/day/{start.strftime('%Y-%m-%d')}/{end.strftime('%Y-%m-%d')}",
        {"adjusted": "true", "sort": "asc", "limit": 500}
    )
    if not data or data.get("resultsCount", 0) == 0:
        return None

    results = data.get("results", [])
    if len(results) < 5:
        return None

    # Build DataFrame matching yfinance structure
    df = pd.DataFrame(results)
    df["Date"]   = pd.to_datetime(df["t"], unit="ms")
    df["Open"]   = df["o"]
    df["High"]   = df["h"]
    df["Low"]    = df["l"]
    df["Close"]  = df["c"]
    df["Volume"] = df["v"]
    df = df.set_index("Date")[["Open","High","Low","Close","Volume"]]

    # Ticker details for name/market cap
    detail = _get(f"/v3/reference/tickers/{ticker}")
    info   = {}
    if detail and detail.get("results"):
        res = detail["results"]
        info = {
            "shortName":  res.get("name", ticker),
            "marketCap":  res.get("market_cap"),
        }

    current = float(df["Close"].iloc[-1])
    prev    = float(df["Close"].iloc[-2])
    return {
        "ticker":           ticker,
        "history":          df,
        "info":             info,
        "current_price":    current,
        "prev_close":       prev,
        "price_change":     current - prev,
        "price_change_pct": (current - prev) / prev * 100,
        "volume":           int(df["Volume"].iloc[-1]),
        "high":             float(df["High"].iloc[-1]),
        "low":              float(df["Low"].iloc[-1]),
        "open":             float(df["Open"].iloc[-1]),
        "name":             info.get("shortName", ticker),
        "market_cap":       info.get("marketCap"),
    }
