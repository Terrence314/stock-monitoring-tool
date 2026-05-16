import yfinance as yf
import pandas as pd
from datetime import datetime

try:
    from finvizfinance.quote import finvizfinance as fvf
    _FINVIZ_AVAILABLE = True
except ImportError:
    _FINVIZ_AVAILABLE = False


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

        # yFinance news headlines (top 5)
        news = []
        try:
            raw_news = stock.news or []
            for item in raw_news[:5]:
                content = item.get("content", {})
                title = (
                    content.get("title")
                    or item.get("title")
                    or ""
                )
                publisher = (
                    content.get("provider", {}).get("displayName")
                    or item.get("publisher")
                    or ""
                )
                if title:
                    news.append({"title": title, "publisher": publisher})
        except Exception:
            news = []

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
            "news":          news,
        }
    except Exception as e:
        print(f"  [data_fetcher] {ticker} error: {e}")
        return None


def fetch_finviz_data(ticker: str) -> dict:
    """Fetch Finviz news and analyst data for a ticker.

    Returns a dict with keys: news (list), analyst_recom (str), target_price (str).
    Returns an empty dict silently on any failure (rate limit, unknown ticker, etc.).
    """
    if not _FINVIZ_AVAILABLE:
        return {}
    try:
        stock = fvf(ticker)

        # Latest 3 news items
        news = []
        try:
            news_df = stock.ticker_news()
            if news_df is not None and not news_df.empty:
                for _, row in news_df.head(3).iterrows():
                    title = str(row.get("Title") or row.get("title") or "")
                    date  = str(row.get("Date")  or row.get("date")  or "")
                    if title:
                        news.append({"title": title, "date": date})
        except Exception:
            pass

        # Fundamentals: analyst recommendation + target price
        analyst_recom = ""
        target_price  = ""
        try:
            fund = stock.ticker_fundament()
            if fund:
                analyst_recom = str(fund.get("Analyst Recom", "") or "")
                target_price  = str(fund.get("Target Price",  "") or "")
        except Exception:
            pass

        return {
            "news":          news,
            "analyst_recom": analyst_recom,
            "target_price":  target_price,
        }
    except Exception:
        return {}


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
