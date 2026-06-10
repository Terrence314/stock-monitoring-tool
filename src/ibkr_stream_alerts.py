"""IBKR real-time streaming trigger engine — Phase 2.

Streams live quotes for high-score watchlist tickers via IB Gateway and
fires Telegram alerts when buy/sell trigger conditions are hit.

ALERTS ONLY — this module never places orders. All trading decisions
require manual action by the user.

Usage (after gateway is logged in):

    python3 src/ibkr_stream_alerts.py

Trigger rules (evaluated on every quote tick, cooldown 4h per ticker/rule):
  BUY side
    • price reclaims MA20 from below AND daily score >= 60   → "MA20 reclaim"
    • price crosses above yesterday's high AND score >= 70   → "breakout"
  SELL side
    • price drops below MA20 AND held above it yesterday     → "MA20 break"
    • price falls more than DROP_PCT from today's high       → "intraday drawdown"

Reference levels (MA20, score, prev high) come from outputs/last_analysis.json
written by the daily pipeline — streaming layer only compares live price
against those precomputed levels.
"""
import json
import os
import time
from datetime import datetime, timezone, timedelta

from ib_async import IB, Stock

from notifier import send_telegram

GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 4002
CLIENT_ID    = 8
REPORT_URL   = "https://terrence314.github.io/stock-monitoring-tool"
HKT          = timezone(timedelta(hours=8))
EXIT_HOUR_HKT = 4   # self-stop at 04:10 HKT (after US close) when started by launchd
EXIT_MIN_HKT  = 10

ANALYSIS_FILE  = os.path.join("outputs", "last_analysis.json")
PORTFOLIO_FILE = os.path.join("outputs", "paper_portfolio.json")
COOLDOWN_FILE  = os.path.join("outputs", "stream_alert_history.json")
COOLDOWN_HOURS = 4
DROP_PCT       = 3.0     # intraday drawdown sell trigger (%)
MIN_SCORE_BUY  = 60
MAX_SYMBOLS    = 40      # gateway line limit safety


def _load_json(path, default):
    try:
        with open(path) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _load_levels() -> dict:
    """Reference levels per ticker from the daily analysis output."""
    data = _load_json(ANALYSIS_FILE, {})
    stocks = data.get("stock_results") or data.get("stocks") or (data if isinstance(data, list) else [])
    levels = {}
    for s in stocks:
        t = s.get("ticker")
        if not t or t.endswith(".HK"):    # US session only for now
            continue
        levels[t] = {
            "score":     s.get("score", 0),
            "ma20":      s.get("ma20"),
            "prev_high": (s.get("ohlc") or [{}])[-1].get("h"),
            "prev_close": s.get("price"),
        }
    return levels


def _cooldown_ok(history: dict, ticker: str, rule: str) -> bool:
    key = f"{ticker}:{rule}"
    last = history.get(key)
    if not last:
        return True
    elapsed = time.time() - last
    return elapsed > COOLDOWN_HOURS * 3600


def _mark_alerted(history: dict, ticker: str, rule: str) -> None:
    history[key] = time.time() if (key := f"{ticker}:{rule}") else None
    with open(COOLDOWN_FILE, "w") as f:
        json.dump(history, f)


def _check_triggers(ticker: str, price: float, lv: dict, state: dict) -> list[tuple[str, str]]:
    """Returns list of (rule_id, message) for triggers that fired."""
    fired = []
    ma20       = lv.get("ma20")
    score      = lv.get("score", 0)
    prev_high  = lv.get("prev_high")
    prev_close = lv.get("prev_close")
    day_high   = state.get("day_high", price)

    if ma20:
        was_below = state.get("below_ma20", price < ma20)
        # BUY: MA20 reclaim
        if was_below and price > ma20 and score >= MIN_SCORE_BUY:
            fired.append(("ma20_reclaim",
                f"🟢 BUY trigger — {ticker} reclaimed MA20 ({ma20:.2f}) @ {price:.2f} · score {score}"))
        # SELL: MA20 break
        if not was_below and price < ma20:
            fired.append(("ma20_break",
                f"🔴 SELL trigger — {ticker} broke below MA20 ({ma20:.2f}) @ {price:.2f}"))
        state["below_ma20"] = price < ma20

    # BUY: breakout above yesterday's high
    if prev_high and price > prev_high and score >= 70 and not state.get("breakout_done"):
        fired.append(("breakout",
            f"🚀 BUY trigger — {ticker} broke yesterday's high ({prev_high:.2f}) @ {price:.2f} · score {score}"))
        state["breakout_done"] = True

    # SELL: intraday drawdown from session high
    if day_high > 0:
        dd = (day_high - price) / day_high * 100
        if dd >= DROP_PCT and not state.get("drawdown_done"):
            fired.append(("drawdown",
                f"⚠️ SELL trigger — {ticker} down {dd:.1f}% from session high ({day_high:.2f}) @ {price:.2f}"))
            state["drawdown_done"] = True
    state["day_high"] = max(day_high, price)

    return fired


def main() -> None:
    cfg     = _load_json(os.path.join("config", "config.json"), {})
    secrets = _load_json(os.path.join("config", "secrets.json"), {})   # gitignored, local only
    bot_token = (os.getenv("TELEGRAM_BOT_TOKEN")
                 or secrets.get("telegram_bot_token", "")
                 or cfg.get("telegram", {}).get("bot_token", ""))
    chat_id   = (os.getenv("TELEGRAM_CHAT_ID")
                 or secrets.get("telegram_chat_id", "")
                 or cfg.get("telegram", {}).get("chat_id", ""))
    if not bot_token or not chat_id:
        print("⚠️ No Telegram credentials — alerts will print to console only.")
        print("   Create config/secrets.json: {\"telegram_bot_token\": \"...\", \"telegram_chat_id\": \"...\"}")

    levels = _load_levels()

    # Open paper positions ALWAYS stream — their SELL alerts must never be missed
    portfolio = _load_json(PORTFOLIO_FILE, {})
    open_positions = {
        t["ticker"] for t in portfolio.get("trades", [])
        if t.get("status") == "open" and not t["ticker"].endswith(".HK")
    }
    for t in open_positions:
        if t not in levels:
            # Not in today's analysis — stream anyway; drawdown rule still protects it
            levels[t] = {"score": 0, "ma20": None, "prev_high": None, "prev_close": None}
    held = sorted(open_positions)

    # Fill remaining slots with highest-score tickers
    by_score = sorted(levels, key=lambda t: levels[t]["score"], reverse=True)
    watch = held + [t for t in by_score if t not in open_positions][:MAX_SYMBOLS - len(held)]
    if held:
        print(f"Open positions pinned to stream: {', '.join(held)}")
    if not watch:
        print("No tickers found in last_analysis.json — run the daily pipeline first.")
        return

    print(f"Streaming {len(watch)} tickers: {', '.join(watch[:10])}{'…' if len(watch) > 10 else ''}")

    ib = IB()
    try:
        ib.connect(GATEWAY_HOST, GATEWAY_PORT, clientId=CLIENT_ID, timeout=10)
    except (ConnectionRefusedError, OSError, TimeoutError) as e:
        print(f"❌ Cannot reach IB Gateway at {GATEWAY_HOST}:{GATEWAY_PORT} — is it open and logged in?")
        if bot_token and chat_id:
            send_telegram(bot_token, chat_id,
                "⚠️ 即時警報引擎無法啟動 — IB Gateway 未開啟或未登入（請開 Gateway 後手動重啟）")
        return
    ib.reqMarketDataType(3)   # delayed fallback works without data subscription

    history = _load_json(COOLDOWN_FILE, {})
    tick_state: dict[str, dict] = {t: {} for t in watch}
    contracts = {}
    skipped = []
    for t in watch:
        # IBKR symbology: dashes in class shares become spaces (BRK-B -> BRK B)
        ib_sym = t.replace("-", " ")
        c = Stock(ib_sym, "SMART", "USD")
        qualified = ib.qualifyContracts(c)
        if not qualified or not c.conId:
            skipped.append(t)
            continue
        contracts[t] = c
        ib.reqMktData(c)
    if skipped:
        print(f"Skipped (no IBKR contract): {', '.join(skipped)}")

    print("Live — Ctrl+C to stop. Alerts fire to Telegram, cooldown "
          f"{COOLDOWN_HOURS}h per ticker/rule. NO orders are ever placed.")

    sym_map = {ct.symbol: t for t, ct in contracts.items()}

    def on_tick(tickers):
        for tk in tickers:
            sym = sym_map.get(tk.contract.symbol, tk.contract.symbol)
            price = tk.last or tk.close
            if not price or price <= 0 or sym not in levels:
                continue
            for rule, msg in _check_triggers(sym, float(price), levels[sym], tick_state[sym]):
                if _cooldown_ok(history, sym, rule):
                    full = f"{msg}\n📊 {REPORT_URL}/{sym}.html"
                    print(f"[ALERT] {msg}")
                    if bot_token and chat_id:
                        send_telegram(bot_token, chat_id, full)
                    _mark_alerted(history, sym, rule)

    ib.pendingTickersEvent += on_tick

    if bot_token and chat_id:
        send_telegram(bot_token, chat_id,
            f"📡 即時警報引擎上線 — streaming {len(contracts)} tickers "
            f"({len(held)} positions pinned) · alerts only, no auto-trading")

    def _auto_exit_check():
        """Self-stop after US close so launchd sessions don't run all day."""
        now = datetime.now(HKT)
        if now.hour == EXIT_HOUR_HKT and now.minute >= EXIT_MIN_HKT:
            print("US session over — engine self-stopping.")
            if bot_token and chat_id:
                send_telegram(bot_token, chat_id, "📡 即時警報引擎下線 — US session closed")
            ib.disconnect()

    try:
        while ib.isConnected():
            ib.sleep(30)
            _auto_exit_check()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        if ib.isConnected():
            ib.disconnect()


if __name__ == "__main__":
    main()
