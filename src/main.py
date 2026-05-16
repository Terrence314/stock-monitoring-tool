import os
import json
import sys
from datetime import datetime

from data_fetcher import fetch_stock_data, fetch_market_overview
from technical_analysis import calculate_indicators
from ai_analysis import setup_gemini, run_morning_brief, run_stock_quick_view
from report_generator import generate_dashboard
from notifier import send_telegram, format_daily_message


def load_config(path: str = "config/config.json") -> dict:
    with open(path, encoding="utf-8") as f:
        cfg = json.load(f)

    # Env vars override config file — safe for GitHub Actions secrets
    cfg["telegram"]["bot_token"] = os.getenv("TELEGRAM_BOT_TOKEN") or cfg["telegram"]["bot_token"]
    cfg["telegram"]["chat_id"]   = os.getenv("TELEGRAM_CHAT_ID")   or cfg["telegram"]["chat_id"]
    cfg["gemini"]["api_key"]     = os.getenv("GEMINI_API_KEY")      or cfg["gemini"]["api_key"]

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

    cfg = load_config()
    today = datetime.now().strftime("%Y/%m/%d")

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
    print(f"      取得 {len(market)} 個市場指標")

    # ── 3. Morning brief ─────────────────────────────────────────────────────
    print("[3/5] 生成早盤簡報（F→G→H→I）…")
    morning_brief = run_morning_brief(model, market)

    # ── 4. Watchlist analysis ────────────────────────────────────────────────
    print(f"[4/5] 分析 {len(cfg['watchlist'])} 檔股票…")
    stock_results = []
    threshold = cfg.get("analysis", {}).get("signal_threshold_alert", 70)

    for ticker in cfg["watchlist"]:
        print(f"      {ticker}…", end=" ", flush=True)
        try:
            data = fetch_stock_data(ticker, period=cfg.get("analysis", {}).get("history_period", "6mo"))
            if not data:
                print("跳過（無數據）")
                continue

            ta = calculate_indicators(data["history"])
            ai_view = run_stock_quick_view(model, ticker, data["name"], data, ta)

            stock_results.append({
                "ticker":           ticker,
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
                "ai_view":          ai_view,
            })
            flag = " 🔥" if ta["score"] >= threshold else ""
            print(f"信號 {ta['score']}/100{flag}")
        except Exception as e:
            print(f"跳過（錯誤：{e}）")

    # ── 5. Generate report ───────────────────────────────────────────────────
    print("[5/5] 生成報告 + 推送 Telegram…")
    report_path = generate_dashboard(today, market, morning_brief, stock_results)
    print(f"      報告已儲存：{report_path}")

    report_url = os.getenv("REPORT_URL", "")
    message = format_daily_message(today, morning_brief, stock_results, report_url)
    ok = send_telegram(cfg["telegram"]["bot_token"], cfg["telegram"]["chat_id"], message)
    print(f"      Telegram：{'✅ 成功' if ok else '❌ 失敗'}")

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
