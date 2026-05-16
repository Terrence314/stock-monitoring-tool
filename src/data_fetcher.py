import yfinance as yf
import pandas as pd
from datetime import datetime


MARKET_INDICES = {
    "SPY":  "S&P 500",
    "QQQ":  "納指 100",
    "^VIX": "VIX 恐慌",
    "GLD":  "黃金",
    "USO":  "原油",
    "TLT":  "20Y 美債",
    "UUP":  "美元指數",
    "BTC-USD": "比特幣",
}


def fetch_stock_data(ticker: str, period: str = "6mo") -> dict | None:
    try:
        stock = yf.Ticker(ticker)
        hist = stock.history(period=period)
        if hist.empty or len(hist) < 5:
            return None
        info = stock.info or {}
        current = float(hist["Close"].iloc[-1])
        prev    = float(hist["Close"].iloc[-2])
        return {
            "ticker":        ticker,
            "history":       hist,
            "info":          info,
            "current_price": current,
            "prev_close":    prev,
            "price_change":  current - prev,
            "price_change_pct": (current - prev) / prev * 100,
            "volume":        int(hist["Volume"].iloc[-1]),
            "high":          float(hist["High"].iloc[-1]),
            "low":           float(hist["Low"].iloc[-1]),
            "open":          float(hist["Open"].iloc[-1]),
            "name":          info.get("shortName", ticker),
            "market_cap":    info.get("marketCap"),
            "sector":        info.get("sector", "Unknown"),
        }
    except Exception as e:
        print(f"  [data_fetcher] {ticker} error: {e}")
        return None


def fetch_market_overview() -> dict:
    overview = {}
    for ticker, name in MARKET_INDICES.items():
        try:
            hist = yf.Ticker(ticker).history(period="5d")
            if hist.empty:
                continue
            latest = float(hist["Close"].iloc[-1])
            prev   = float(hist["Close"].iloc[-2]) if len(hist) > 1 else latest
            change_pct = (latest - prev) / prev * 100
            overview[ticker] = {
                "name":       name,
                "price":      latest,
                "change_pct": change_pct,
                "direction":  "up" if change_pct >= 0 else "down",
            }
        except Exception as e:
            print(f"  [data_fetcher] market {ticker} error: {e}")
    return overview
