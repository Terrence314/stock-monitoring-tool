"""
Lightweight price-only refresh — no Gemini, no Finnhub API calls.

Runs every 15 min during US trading hours to update prices and TA scores
on the dashboard. AI analysis (ai_view, sentiment, news) is preserved
from the last full daily run via outputs/last_analysis.json.
"""
import json
import os
import sys
from datetime import datetime

from data_fetcher import fetch_fear_greed, fetch_market_overview, fetch_stock_data
from report_generator import generate_dashboard
from technical_analysis import calculate_indicators


LAST_ANALYSIS_CACHE = os.path.join("outputs", "last_analysis.json")
SCORE_HISTORY_FILE  = os.path.join("outputs", "score_history.json")
ALERT_HISTORY_FILE  = os.path.join("outputs", "alert_history.json")

# 3 months gives enough history for MA60, RSI, MACD without over-fetching
REFRESH_PERIOD = "3mo"


def load_json_file(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def load_config(path: str = "config/config.json") -> dict:
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)
    # Only telegram needed — no Gemini key required for price refresh
    cfg["telegram"]["bot_token"] = os.getenv("TELEGRAM_BOT_TOKEN") or cfg["telegram"]["bot_token"]
    cfg["telegram"]["chat_id"]   = os.getenv("TELEGRAM_CHAT_ID")   or cfg["telegram"]["chat_id"]
    return cfg


def main():
    print("=" * 50)
    print(f"  💹 Price Refresh  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    try:
        cfg = load_config()
    except Exception as e:
        print(f"[FATAL] 無法載入設定：{e}")
        sys.exit(1)

    today = datetime.now().strftime("%Y/%m/%d")

    # ── Load last AI analysis cache ──────────────────────────────────────────
    cache = load_json_file(LAST_ANALYSIS_CACHE, {})
    cached_stocks  = {s["ticker"]: s for s in cache.get("stock_results", [])}
    morning_brief  = cache.get("morning_brief", "（等待今日早盤簡報…）")
    hk_brief       = cache.get("hk_brief", "")
    hk_data        = cache.get("hk_data", {})
    cached_date    = cache.get("date", "未知")
    print(f"  AI 快取：{len(cached_stocks)} 檔（最後完整分析：{cached_date}）")

    # ── Refresh market overview (free yfinance calls) ────────────────────────
    print("  更新大盤數據…")
    try:
        market     = fetch_market_overview()
        fear_greed = fetch_fear_greed()
        print(f"  取得 {len(market)} 個市場指標 · F&G: {fear_greed.get('value', 'N/A')}")
    except Exception as e:
        print(f"  大盤數據失敗（{e}）— 使用快取")
        market     = cache.get("market", {})
        fear_greed = cache.get("fear_greed", {})

    # ── Refresh prices + TA for all tickers ─────────────────────────────────
    print(f"\n  更新 {len(cfg['watchlist'])} 檔股票…")
    stock_results = []

    for item in cfg["watchlist"]:
        ticker      = item["ticker"]
        asset_type  = item.get("type", "stock")
        asset_market = item.get("market", "US")
        print(f"    {ticker}…", end=" ", flush=True)
        try:
            data = fetch_stock_data(ticker, period=REFRESH_PERIOD)
            if not data:
                print("跳過（無數據）")
                continue

            ta = calculate_indicators(data["history"])

            # Extract fresh OHLC bars (last 100)
            _hist = data.get("history")
            _ohlc = []
            if _hist is not None and not _hist.empty:
                for _, row in _hist.tail(100).iterrows():
                    _ohlc.append({
                        "o": round(float(row.get("Open",   0)), 2),
                        "h": round(float(row.get("High",   0)), 2),
                        "l": round(float(row.get("Low",    0)), 2),
                        "c": round(float(row.get("Close",  0)), 2),
                        "v": round(float(row.get("Volume", 0)) / 1e6, 2),
                    })

            # Merge fresh price/TA with cached AI fields
            prev = cached_stocks.get(ticker, {})
            stock_results.append({
                # ── Live: refreshed every 15 min ──────────────────────────
                "ticker":           ticker,
                "asset_type":       asset_type,
                "market":           asset_market,
                "name":             data["name"],
                "price":            data["current_price"],
                "price_change_pct": data["price_change_pct"],
                "volume":           data["volume"],
                "score":            ta["score"],
                "strength":         ta["strength"],
                "strength_en":      ta["strength_en"],
                "signals":          ta["signals"],
                "ma5":              ta["ma5"],
                "ma20":             ta["ma20"],
                "ma60":             ta["ma60"],
                "rsi":              ta["rsi"],
                "macd":             ta["macd"],
                "macd_hist":        ta["macd_hist"],
                "vol_ratio":        ta["vol_ratio"],
                "ohlc":             _ohlc,
                "open_price":       data.get("open", 0),
                "high_price":       data.get("high", 0),
                "low_price":        data.get("low", 0),
                "prev_close":       data.get("prev_close", 0),
                # ── Cached: preserved from last daily AI run ───────────────
                "ai_view":          prev.get("ai_view", ""),
                "sentiment":        prev.get("sentiment", ""),
                "news":             prev.get("news", []),
                "analyst_buy":      prev.get("analyst_buy"),
                "analyst_hold":     prev.get("analyst_hold"),
                "analyst_sell":     prev.get("analyst_sell"),
                "analyst_period":   prev.get("analyst_period", ""),
                "pe_ratio":         prev.get("pe_ratio"),
                "week52_high":      prev.get("week52_high"),
                "week52_low":       prev.get("week52_low"),
                "next_earnings":    prev.get("next_earnings"),
                "sector":           prev.get("sector", data.get("sector", "Unknown")),
                "entry":            prev.get("entry", ""),
            })

            chg = data["price_change_pct"]
            arrow = "▲" if chg >= 0 else "▼"
            print(f"${data['current_price']:.2f} {arrow}{abs(chg):.2f}%  score={ta['score']}")

        except Exception as e:
            print(f"跳過（{e}）")

    scored = len(stock_results)
    total  = len(cfg["watchlist"])
    print(f"\n  更新 {scored}/{total} 檔股票")

    if scored == 0:
        print("  ⚠️ 無任何股票數據 — 中止，不覆蓋現有報告")
        sys.exit(1)

    # ── Regenerate dashboard with fresh prices ───────────────────────────────
    score_history = load_json_file(SCORE_HISTORY_FILE, {})
    alert_history = load_json_file(ALERT_HISTORY_FILE, [])

    report_path = generate_dashboard(
        today,
        market,
        morning_brief,
        stock_results,
        score_history=score_history,
        alert_history=alert_history,
        fear_greed=fear_greed,
        hk_brief=hk_brief,
        hk_data=hk_data,
    )
    print(f"  報告已更新：{report_path}")
    print("\n  完成 ✅")


if __name__ == "__main__":
    main()
