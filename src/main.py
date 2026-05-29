import os
import json
import sys
from datetime import datetime, timedelta

from data_fetcher import fetch_stock_data, fetch_market_overview, fetch_finnhub_data, fetch_fear_greed, fetch_hk_indicators
from technical_analysis import calculate_indicators
from ai_analysis import setup_gemini, run_morning_brief, run_stock_quick_view, run_news_sentiment, run_hk_morning_brief
from report_generator import generate_dashboard
from notifier import send_telegram, send_health_alert, format_daily_message
from backtest import run_backtest
from paper_trading import run_paper_trading
from pattern_engine import run_pattern_scan, format_pattern_alert, get_todays_new_events
from pattern_backtest import run_pattern_backtest
from portfolio import run_portfolio


SCORE_HISTORY_FILE = os.path.join("outputs", "score_history.json")
ALERT_HISTORY_FILE = os.path.join("outputs", "alert_history.json")
HISTORY_KEEP_DAYS  = 30
ALERT_KEEP_ENTRIES = 30


def load_json_file(path: str, default):
    """Load a JSON file, returning default if missing or corrupt."""
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def save_json_file(path: str, data) -> None:
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def update_score_history(today_str: str, stock_results: list) -> dict:
    """Append today's scores; prune to last HISTORY_KEEP_DAYS days."""
    history: dict = load_json_file(SCORE_HISTORY_FILE, {})
    today_scores = {s["ticker"]: s["score"] for s in stock_results}
    history[today_str] = today_scores

    # Keep only recent days
    cutoff = (datetime.now() - timedelta(days=HISTORY_KEEP_DAYS)).strftime("%Y-%m-%d")
    history = {d: v for d, v in history.items() if d >= cutoff}

    save_json_file(SCORE_HISTORY_FILE, history)
    return history


def update_alert_history(today_str: str, stock_results: list, threshold: int) -> list:
    """Append high-signal stocks; keep last ALERT_KEEP_ENTRIES entries."""
    alerts: list = load_json_file(ALERT_HISTORY_FILE, [])
    for s in stock_results:
        if s["score"] >= threshold:
            alerts.append({
                "date":     today_str,
                "ticker":   s["ticker"],
                "score":    s["score"],
                "strength": s["strength"],
            })
    # Trim to most recent entries
    alerts = alerts[-ALERT_KEEP_ENTRIES:]
    save_json_file(ALERT_HISTORY_FILE, alerts)
    return alerts


def load_config(path: str = "config/config.json") -> dict:
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)

    # Env vars override config file — safe for GitHub Actions secrets
    cfg["telegram"]["bot_token"]     = os.getenv("TELEGRAM_BOT_TOKEN") or cfg["telegram"]["bot_token"]
    cfg["telegram"]["chat_id"]       = os.getenv("TELEGRAM_CHAT_ID")   or cfg["telegram"]["chat_id"]
    cfg["gemini"]["api_key"]         = os.getenv("GEMINI_API_KEY")      or cfg["gemini"]["api_key"]
    cfg["gemini"]["finnhub_api_key"] = os.getenv("FINNHUB_API_KEY")     or cfg["gemini"].get("finnhub_api_key", "")

    return cfg


def validate_config(cfg: dict) -> list[str]:
    errors = []
    if not cfg["gemini"]["api_key"]:
        errors.append("GEMINI_API_KEY is missing")
    if not cfg["telegram"]["bot_token"]:
        errors.append("TELEGRAM_BOT_TOKEN is missing")
    if not cfg["telegram"]["chat_id"]:
        errors.append("TELEGRAM_CHAT_ID is missing")
    return errors


def main():
    print("=" * 50)
    print(f"  AI 股票監控系統  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}")
    print("=" * 50)

    cfg = None
    try:
        cfg = load_config()
    except Exception as e:
        print(f"[FATAL] 無法載入設定：{e}")
        sys.exit(1)

    try:
        _run(cfg)
    except Exception as e:
        print(f"\n[FATAL] Pipeline 崩潰：{type(e).__name__}: {e}")
        try:
            send_health_alert(
                cfg["telegram"]["bot_token"],
                cfg["telegram"]["chat_id"],
                [f"🚨 Pipeline 完全崩潰，今日報告未生成\n錯誤：{type(e).__name__}: {e}"],
            )
        except Exception:
            pass  # Don't mask the original error
        sys.exit(1)


def _run(cfg: dict) -> None:
    today     = datetime.now().strftime("%Y/%m/%d")
    today_key = datetime.now().strftime("%Y-%m-%d")

    errors = validate_config(cfg)
    if errors:
        print("[ERROR] 缺少必要設定：")
        for e in errors:
            print(f"  · {e}")
        print("請設定環境變數後重試。詳見 .env.example")
        sys.exit(1)

    # ── 1. Setup AI ──────────────────────────────────────────────────────────
    print("\n[1/5] 初始化 Gemini AI…")
    model = setup_gemini(cfg["gemini"]["api_key"], cfg["gemini"].get("model", "gemini-2.0-flash"))

    # ── 2. Market overview ───────────────────────────────────────────────────
    print("[2/5] 抓取大盤數據…")
    market = fetch_market_overview()
    fear_greed = fetch_fear_greed()
    print(f"      取得 {len(market)} 個市場指標 · F&G: {fear_greed.get('value', 'N/A')}")

    # ── 2b. HK indicators ────────────────────────────────────────────────────
    print("      抓取港股風向指標（TCEHY / BABA / ^HSI / EWH / ^TNX）…")
    hk_data = fetch_hk_indicators()
    print(f"      取得 {sum(1 for v in hk_data.values() if v.get('price'))} 個港股指標")

    # ── 3. Morning brief ─────────────────────────────────────────────────────
    print("[3/5] 生成早盤簡報（F→G→H→I）…")
    morning_brief = run_morning_brief(model, market)

    print("      生成港股盤前分析…")
    hk_brief = run_hk_morning_brief(model, hk_data, market)

    # ── 4. Watchlist analysis ────────────────────────────────────────────────
    print(f"[4/5] 分析 {len(cfg['watchlist'])} 檔股票…")
    stock_results = []
    ta_dfs: dict   = {}   # {ticker: DataFrame} — fed to pattern_engine after the loop
    threshold    = cfg.get("analysis", {}).get("signal_threshold_alert", 70)
    finnhub_key  = cfg["gemini"].get("finnhub_api_key", "")

    for item in cfg["watchlist"]:
        ticker = item["ticker"]
        asset_type = item.get("type", "stock")
        asset_market = item.get("market", "US")
        print(f"      {ticker}…", end=" ", flush=True)
        try:
            data = fetch_stock_data(ticker, period=cfg.get("analysis", {}).get("history_period", "6mo"))
            if not data:
                print("跳過（無數據）")
                continue

            ta = calculate_indicators(data["history"])
            ta_dfs[ticker] = ta["df"]   # stash for pattern_engine
            ai_view = run_stock_quick_view(model, ticker, data["name"], data, ta)

            # ── Finnhub: news + analyst ratings + financials ───────────────
            fh = fetch_finnhub_data(ticker, finnhub_key) if finnhub_key else {}

            # ── Combine and deduplicate headlines for sentiment ─────────────
            yf_headlines = [item["title"] for item in data.get("news", [])]
            fh_headlines = [item["headline"] for item in fh.get("news", [])]
            seen = set()
            combined_headlines = []
            for h in yf_headlines + fh_headlines:
                key = h.lower().strip()[:80]
                if key not in seen:
                    seen.add(key)
                    combined_headlines.append(h)

            sentiment = run_news_sentiment(model, ticker, combined_headlines)

            # ── Merge Finnhub news into combined news list for display ──────
            combined_news = list(data.get("news", []))
            existing_lower = {item["title"].lower()[:80] for item in combined_news}
            for fh_item in fh.get("news", []):
                if fh_item["headline"].lower()[:80] not in existing_lower:
                    combined_news.append({
                        "title":     fh_item["headline"],
                        "publisher": fh_item.get("source", "Finnhub"),
                    })

            # Extract OHLC history (last 100 bars) for candlestick chart
            _hist = data.get("history")
            _ohlc = []
            if _hist is not None and not _hist.empty:
                for _, row in _hist.tail(100).iterrows():
                    _ohlc.append({
                        "o": round(float(row.get("Open", 0)), 2),
                        "h": round(float(row.get("High", 0)), 2),
                        "l": round(float(row.get("Low", 0)), 2),
                        "c": round(float(row.get("Close", 0)), 2),
                        "v": round(float(row.get("Volume", 0)) / 1e6, 2),
                    })

            stock_results.append({
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
                "bb_squeeze_breakout_up":   ta.get("bb_squeeze_breakout_up", False),
                "bb_squeeze_breakout_down": ta.get("bb_squeeze_breakout_down", False),
                "bb_walking_up":            ta.get("bb_walking_up", False),
                "bb_walking_down":          ta.get("bb_walking_down", False),
                "kd_k":                     ta.get("kd_k"),
                "kd_d":                     ta.get("kd_d"),
                "kd_golden_cross_low":      ta.get("kd_golden_cross_low", False),
                "kd_death_cross_high":      ta.get("kd_death_cross_high", False),
                "kd_oversold":              ta.get("kd_oversold", False),
                "ai_view":          ai_view,
                "sector":           data.get("sector", "Unknown"),
                "entry":            "",  # populated by deep dive if run; placeholder here
                "news":             combined_news[:5],
                "sentiment":        sentiment,
                "analyst_buy":      fh.get("analyst_buy"),
                "analyst_hold":     fh.get("analyst_hold"),
                "analyst_sell":     fh.get("analyst_sell"),
                "analyst_period":   fh.get("analyst_period", ""),
                "pe_ratio":         fh.get("pe_ratio"),
                "week52_high":      fh.get("week52_high"),
                "week52_low":       fh.get("week52_low"),
                "next_earnings":    fh.get("next_earnings"),
                "ohlc":             _ohlc,
                "open_price":       data.get("open", 0),
                "high_price":       data.get("high", 0),
                "low_price":        data.get("low", 0),
                "prev_close":       data.get("prev_close", 0),
            })
            flag = " 🔥" if ta["score"] >= threshold else ""
            print(f"信號 {ta['score']}/100{flag}")
        except Exception as e:
            print(f"跳過（錯誤：{e}）")

    # ── Health Check ─────────────────────────────────────────────────────────
    health_issues = []
    scored_count = len(stock_results)
    total_count  = len(cfg["watchlist"])
    if scored_count < 10:
        health_issues.append(
            f"只有 {scored_count}/{total_count} 檔股票成功評分（數據源可能異常，yfinance 或 Finnhub）"
        )
    no_ai = sum(1 for s in stock_results if not s.get("ai_view", "").strip())
    if no_ai > 5:
        health_issues.append(
            f"{no_ai} 檔股票缺少 AI 分析（Gemini API 可能受限或超出配額）"
        )
    if health_issues:
        print(f"\n  ⚠️ 健康警告：{len(health_issues)} 個問題，發送 Telegram 通知…")
        send_health_alert(
            cfg["telegram"]["bot_token"],
            cfg["telegram"]["chat_id"],
            health_issues,
        )

    # ── 5. Persist history + generate report ────────────────────────────────
    print("[5/5] 生成報告 + 推送 Telegram…")
    score_history = update_score_history(today_key, stock_results)
    alert_history = update_alert_history(today_key, stock_results, threshold)

    report_path = generate_dashboard(
        today, market, morning_brief, stock_results,
        score_history=score_history,
        alert_history=alert_history,
        fear_greed=fear_greed,
        hk_brief=hk_brief,
        hk_data=hk_data,
    )
    print(f"      報告已儲存：{report_path}")

    # ── Cache analysis for 15-min price refresh ─────────────────────────────
    # price_refresh.py reads this to preserve AI fields between daily runs.
    # Exclude the large ohlc array — price_refresh regenerates it from fresh data.
    cache_path = os.path.join("outputs", "last_analysis.json")
    save_json_file(cache_path, {
        "date":          today_key,
        "morning_brief": morning_brief,
        "hk_brief":      hk_brief,
        "hk_data":       hk_data,
        "market":        market,
        "fear_greed":    fear_greed,
        "stock_results": [
            {k: v for k, v in s.items() if k != "ohlc"}
            for s in stock_results
        ],
    })
    print(f"      AI 快取已儲存：{cache_path}")

    report_url = os.getenv("REPORT_URL", "")
    message = format_daily_message(today, morning_brief, stock_results, report_url)
    ok = send_telegram(cfg["telegram"]["bot_token"], cfg["telegram"]["chat_id"], message)
    print(f"      Telegram：{'✅ 成功' if ok else '❌ 失敗'}")

    # ── Pattern scan ─────────────────────────────────────────────────────────
    # Detects active named patterns per ticker; updates pattern_history.json
    active_patterns: dict = {}
    try:
        active_patterns = run_pattern_scan(stock_results, ta_dfs, today_key)
        print(f"      Pattern scan: {sum(len(v) for v in active_patterns.values())} active patterns across {len(active_patterns)} tickers")
    except Exception as pe_err:
        print(f"  [pattern_engine] ⚠️ skipped due to error: {pe_err}")

    # ── Backtest ─────────────────────────────────────────────────────────────
    # Isolated try/except: backtest failures must never block the report deploy
    try:
        run_backtest([item["ticker"] for item in cfg["watchlist"]])
    except Exception as bt_err:
        print(f"  [backtest] ⚠️ skipped due to error: {bt_err}")

    # ── Paper trading ─────────────────────────────────────────────────────────
    # Isolated try/except: same isolation principle as backtest
    try:
        today_scores = {s["ticker"]: s["score"] for s in stock_results}
        run_paper_trading(today_key, today_scores, stock_results, active_patterns=active_patterns)
    except Exception as pt_err:
        print(f"  [paper_trading] ⚠️ skipped due to error: {pt_err}")

    # ── Pattern backtest ──────────────────────────────────────────────────────
    try:
        pb_path = run_pattern_backtest()
        if pb_path:
            print(f"      Pattern backtest: {pb_path}")
    except Exception as pb_err:
        print(f"  [pattern_backtest] ⚠️ skipped due to error: {pb_err}")

    # ── Portfolio ─────────────────────────────────────────────────────────────
    try:
        pf_path = run_portfolio()
        if pf_path:
            print(f"      Portfolio: {pf_path}")
    except Exception as pf_err:
        print(f"  [portfolio] ⚠️ skipped due to error: {pf_err}")

    # ── Pattern Telegram alert (new start events only) ────────────────────────
    try:
        new_events  = get_todays_new_events(today_key)
        pattern_msg = format_pattern_alert(new_events, today_key)
        if pattern_msg:
            ok_p = send_telegram(cfg["telegram"]["bot_token"], cfg["telegram"]["chat_id"], pattern_msg)
            print(f"      Pattern alert Telegram：{'✅ 成功' if ok_p else '❌ 失敗'}")
        else:
            print("      Pattern alert：no new patterns today")
    except Exception as pa_err:
        print(f"  [pattern_alert] ⚠️ skipped due to error: {pa_err}")

    # Summary
    if stock_results:
        top = max(stock_results, key=lambda x: x["score"])
        alerts = [s for s in stock_results if s["score"] >= threshold]
        print(f"\n  最高信號：{top['ticker']} ({top['score']}/100 · {top['strength']})")
        if alerts:
            print(f"  高信號股票（≥{threshold}）：{', '.join(s['ticker'] for s in alerts)}")

    print("\n  完成 ✅")


if __name__ == "__main__":
    main()
