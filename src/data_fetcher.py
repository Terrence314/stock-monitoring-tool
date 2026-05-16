import yfinance as yf
import pandas as pd
from datetime import datetime, timedelta

try:
    import finnhub as _finnhub_module
    _FINNHUB_AVAILABLE = True
except ImportError:
    _FINNHUB_AVAILABLE = False


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


def fetch_finnhub_data(ticker: str, api_key: str) -> dict:
    """Fetch Finnhub data: news, analyst recommendations, basic financials, earnings calendar.

    Returns a dict with keys:
        news          - list of {headline, source} (top 5)
        analyst_buy   - int buy count from latest recommendation trend (or None)
        analyst_hold  - int hold count (or None)
        analyst_sell  - int sell count (or None)
        analyst_period - str period label (or "")
        pe_ratio      - float P/E (normalised annual) or None
        week52_high   - float 52-week high or None
        week52_low    - float 52-week low or None
        next_earnings - str "YYYY-MM-DD" if within 30 days, else None

    Each section is wrapped in its own try/except — partial failures return empty
    for that field only.  ETF-specific fields (earnings, P/E) gracefully return None.
    """
    if not _FINNHUB_AVAILABLE or not api_key:
        return {
            "news": [], "analyst_buy": None, "analyst_hold": None,
            "analyst_sell": None, "analyst_period": "",
            "pe_ratio": None, "week52_high": None, "week52_low": None,
            "next_earnings": None,
        }

    client = _finnhub_module.Client(api_key=api_key)
    today = datetime.now().date()
    seven_days_ago = (today - timedelta(days=7)).strftime("%Y-%m-%d")
    today_str = today.strftime("%Y-%m-%d")
    thirty_days_ahead = (today + timedelta(days=30)).strftime("%Y-%m-%d")

    # ── News ─────────────────────────────────────────────────────────────────
    news = []
    try:
        raw_news = client.company_news(ticker, _from=seven_days_ago, to=today_str)
        for item in (raw_news or [])[:5]:
            headline = item.get("headline", "").strip()
            source   = item.get("source", "").strip()
            if headline:
                news.append({"headline": headline, "source": source})
    except Exception:
        pass

    # ── Analyst recommendations ───────────────────────────────────────────────
    analyst_buy    = None
    analyst_hold   = None
    analyst_sell   = None
    analyst_period = ""
    try:
        trends = client.recommendation_trends(ticker)
        if trends:
            latest = trends[0]
            analyst_buy    = latest.get("buy")
            analyst_hold   = latest.get("hold")
            analyst_sell   = latest.get("sell")
            analyst_period = latest.get("period", "")
    except Exception:
        pass

    # ── Basic financials (52W range, P/E) ─────────────────────────────────────
    pe_ratio    = None
    week52_high = None
    week52_low  = None
    try:
        fins = client.company_basic_financials(ticker, "all")
        metrics = fins.get("metric", {}) if fins else {}
        week52_high = metrics.get("52WeekHigh")
        week52_low  = metrics.get("52WeekLow")
        pe_ratio    = metrics.get("peNormalizedAnnual")
    except Exception:
        pass

    # ── Earnings calendar ─────────────────────────────────────────────────────
    next_earnings = None
    try:
        cal = client.earnings_calendar(
            _from=today_str, to=thirty_days_ahead, symbol=ticker
        )
        earnings_list = (cal or {}).get("earningsCalendar", [])
        if earnings_list:
            next_earnings = earnings_list[0].get("date")
    except Exception:
        pass

    return {
        "news":           news,
        "analyst_buy":    analyst_buy,
        "analyst_hold":   analyst_hold,
        "analyst_sell":   analyst_sell,
        "analyst_period": analyst_period,
        "pe_ratio":       pe_ratio,
        "week52_high":    week52_high,
        "week52_low":     week52_low,
        "next_earnings":  next_earnings,
    }


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
