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

ANALYSIS_FILE  = os.path.join("outputs", "last_analysis.json")
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
    stocks = data.get("stocks", data if isinstance(data, list) else [])
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
    cfg = _load_json(os.path.join("config", "config.json"), {})
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN") or cfg.get("telegram", {}).get("bot_token", "")
    chat_id   = os.getenv("TELEGRAM_CHAT_ID")   or cfg.get("telegram", {}).get("chat_id", "")

    levels = _load_levels()
    # Highest-score tickers first, capped at gateway line limit
    watch = sorted(levels, key=lambda t: levels[t]["score"], reverse=True)[:MAX_SYMBOLS]
    if not watch:
        print("No tickers found in last_analysis.json — run the daily pipeline first.")
        return

    print(f"Streaming {len(watch)} tickers: {', '.join(watch[:10])}{'…' if len(watch) > 10 else ''}")

    ib = IB()
    ib.connect(GATEWAY_HOST, GATEWAY_PORT, clientId=CLIENT_ID, timeout=10)
    ib.reqMarketDataType(3)   # delayed fallback works without data subscription

    history = _load_json(COOLDOWN_FILE, {})
    tick_state: dict[str, dict] = {t: {} for t in watch}
    contracts = {}
    for t in watch:
        c = Stock(t, "SMART", "USD")
        ib.qualifyContracts(c)
        contracts[t] = c
        ib.reqMktData(c)

    print("Live — Ctrl+C to stop. Alerts fire to Telegram, cooldown "
          f"{COOLDOWN_HOURS}h per ticker/rule. NO orders are ever placed.")

    def on_tick(tickers):
        for tk in tickers:
            sym = tk.contract.symbol
            price = tk.last or tk.close
            if not price or sym not in levels:
                continue
            for rule, msg in _check_triggers(sym, float(price), levels[sym], tick_state[sym]):
                if _cooldown_ok(history, sym, rule):
                    print(f"[ALERT] {msg}")
                    if bot_token and chat_id:
                        send_telegram(bot_token, chat_id, msg)
                    _mark_alerted(history, sym, rule)

    ib.pendingTickersEvent += on_tick
    try:
        ib.run()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        ib.disconnect()


if __name__ == "__main__":
    main()
