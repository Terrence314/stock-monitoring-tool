"""
Lightweight price-only refresh — no Gemini, no Finnhub API calls.

Runs every 15 min during US trading hours to update prices and TA scores
on the dashboard. AI analysis (ai_view, sentiment, news) is preserved
from the last full daily run via outputs/last_analysis.json.
"""
import json
import os
import sys
from datetime import datetime, timezone

from data_fetcher import fetch_fear_greed, fetch_market_overview, fetch_stock_data
from notifier import send_exit_alert
from report_generator import generate_dashboard
from technical_analysis import calculate_indicators


LAST_ANALYSIS_CACHE  = os.path.join("outputs", "last_analysis.json")
SCORE_HISTORY_FILE   = os.path.join("outputs", "score_history.json")
ALERT_HISTORY_FILE   = os.path.join("outputs", "alert_history.json")
EXIT_ALERT_FILE      = os.path.join("outputs", "exit_alert_history.json")

# Exit alert thresholds
EXIT_PREV_MIN   = 70   # previous score must have been >= this (was a long signal)
EXIT_CURR_MAX   = 50   # current score must be <= this (momentum faded)
EXIT_DROP_MIN   = 20   # score must drop by at least this many points
EXIT_COOLDOWN_H = 20   # hours before re-alerting the same ticker

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


def _detect_exit_alerts(stock_results: list, cached_stocks: dict) -> list:
    """Compare fresh scores against last daily-run scores.

    Returns alerts for tickers that were a long signal (score >= EXIT_PREV_MIN)
    in the last daily run but have now dropped to <= EXIT_CURR_MAX with a fall
    of at least EXIT_DROP_MIN points — indicating momentum has faded.
    """
    alerts = []
    for stock in stock_results:
        ticker     = stock["ticker"]
        prev       = cached_stocks.get(ticker, {})
        prev_score = prev.get("score", 0)
        curr_score = stock["score"]
        drop       = prev_score - curr_score
        if (
            prev_score >= EXIT_PREV_MIN
            and curr_score <= EXIT_CURR_MAX
            and drop >= EXIT_DROP_MIN
        ):
            alerts.append({
                "ticker":          ticker,
                "prev_score":      prev_score,
                "curr_score":      curr_score,
                "drop":            drop,
                "price":           stock["price"],
                "price_change_pct": stock.get("price_change_pct", 0),
                "strength":        stock.get("strength", ""),
                "prev_strength":   prev.get("strength", ""),
            })
    return alerts


def _filter_exit_cooldown(alerts: list) -> list:
    """Drop tickers already alerted within EXIT_COOLDOWN_H hours."""
    history = load_json_file(EXIT_ALERT_FILE, {})
    now     = datetime.now(timezone.utc)
    fresh   = []
    for a in alerts:
        last_iso = history.get(a["ticker"])
        if last_iso:
            last_dt  = datetime.fromisoformat(last_iso)
            # Ensure last_dt is offset-aware for comparison
            if last_dt.tzinfo is None:
                last_dt = last_dt.replace(tzinfo=timezone.utc)
            elapsed_h = (now - last_dt).total_seconds() / 3600
            if elapsed_h < EXIT_COOLDOWN_H:
                print(f"    [{a['ticker']}] exit alert suppressed (cooldown {elapsed_h:.1f}h < {EXIT_COOLDOWN_H}h)")
                continue
        fresh.append(a)
    return fresh


def _save_exit_alert_history(alerts: list) -> None:
    """Record send time for each alerted ticker."""
    history = load_json_file(EXIT_ALERT_FILE, {})
    now_iso = datetime.now(timezone.utc).isoformat()
    for a in alerts:
        history[a["ticker"]] = now_iso
    os.makedirs(os.path.dirname(EXIT_ALERT_FILE) or ".", exist_ok=True)
    with open(EXIT_ALERT_FILE, "w", encoding="utf-8") as f:
        json.dump(history, f, ensure_ascii=False, indent=2)


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
                "bb_upper":         ta.get("bb_upper"),
                "bb_mid":           ta.get("bb_mid"),
                "bb_lower":         ta.get("bb_lower"),
                "bb_pct":           ta.get("bb_pct"),
                "bb_squeeze":       ta.get("bb_squeeze", False),
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

    # ── Exit alert detection ─────────────────────────────────────────────────
    bot_token  = cfg["telegram"].get("bot_token", "")
    chat_id    = cfg["telegram"].get("chat_id", "")
    report_url = os.getenv("REPORT_URL", "")

    raw_exits  = _detect_exit_alerts(stock_results, cached_stocks)
    exits      = _filter_exit_cooldown(raw_exits)

    if exits:
        tickers_str = ", ".join(a["ticker"] for a in exits)
        print(f"\n  🚨 Exit alerts: {tickers_str}")
        if bot_token and chat_id:
            ok = send_exit_alert(bot_token, chat_id, exits, report_url)
            print(f"  Telegram exit alert: {'✅' if ok else '❌'}")
            if ok:
                _save_exit_alert_history(exits)
        else:
            print("  ⚠️  Telegram not configured — skipping alert send")
    else:
        print(f"\n  ✅ No exit alerts triggered (checked {scored} tickers)")

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
