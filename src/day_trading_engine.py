"""day_trading_engine.py — Day-Trading Mode (Step 2): live ORB engine.

Rules validated by src/day_trading_backtest.py (ORB variant: PF 1.45,
win rate 52.7%, expectancy +0.139%/trade over 30 tickers x 60d).

ALERTS ONLY — never places orders. Fully isolated from the swing
strategy: own in-memory state, own ledger (outputs/day_trading_portfolio.json,
gitignored via outputs/), own Telegram tag "⚡ 日內". Does not read or write
action_box.json / paper_portfolio.json / the 60-day swing gate.

Intended use: instantiated once by ibkr_stream_alerts.py (same IB
connection, same Mac-local process) and polled every 5 minutes during
the US session. reqHistoricalData (5-min bars, RTH only) does not
consume market-data lines, separate from the reqMktData tick stream.
"""
import json
import os
import time
import traceback
from datetime import datetime, timezone
from typing import Callable

from ib_async import IB, Stock

ORB_BARS  = 6     # first 30 min (6 x 5-min bars)
ORB_RR    = 2.0   # target = entry + ORB_RR x risk
POLL_SECS = 300   # 5 minutes — matches bar size

LEDGER_FILE = os.path.join("outputs", "day_trading_portfolio.json")


def _load_ledger() -> dict:
    try:
        with open(LEDGER_FILE) as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return {"trades": []}


def _save_ledger(ledger: dict) -> None:
    os.makedirs("outputs", exist_ok=True)
    with open(LEDGER_FILE, "w") as f:
        json.dump(ledger, f, ensure_ascii=False, indent=1)


class DayTradingEngine:
    """ORB engine — one trade per ticker per day, long-only, exit by EOD."""

    def __init__(self, ib: IB, tickers: list[str], send_alert: Callable[[str], None]):
        self.ib = ib
        self.tickers = tickers
        self.send_alert = send_alert
        self.contracts: dict[str, Stock] = {}
        self.state: dict[str, dict] = {t: self._fresh_state() for t in tickers}
        self.ledger = _load_ledger()
        self._last_poll = 0.0

        skipped = []
        for t in tickers:
            ib_sym = t.replace("-", " ")
            c = Stock(ib_sym, "SMART", "USD")
            qualified = ib.qualifyContracts(c)
            if qualified and c.conId:
                self.contracts[t] = c
            else:
                skipped.append(t)
        if skipped:
            print(f"  [day-trading] skipped (no IBKR contract): {', '.join(skipped)}")

    @staticmethod
    def _fresh_state() -> dict:
        return {
            "date": None,
            "or_high": None, "or_low": None,
            "breakout_seen": False,
            "entered": False, "entry": None, "stop": None, "target": None,
            "closed": False,
        }

    def due(self, now_ts: float) -> bool:
        return now_ts - self._last_poll >= POLL_SECS

    def poll(self) -> None:
        self._last_poll = time.time()
        for t, c in self.contracts.items():
            try:
                self._poll_ticker(t, c)
            except Exception:
                print(f"  [day-trading] {t}: error — skipped this cycle\n{traceback.format_exc()}")

    def _poll_ticker(self, t: str, c: Stock) -> None:
        bars = self.ib.reqHistoricalData(
            c, endDateTime="", durationStr="1 D",
            barSizeSetting="5 mins", whatToShow="TRADES",
            useRTH=True, formatDate=1,
        )
        if len(bars) < ORB_BARS:
            return

        today = bars[-1].date.date() if isinstance(bars[-1].date, datetime) else bars[-1].date
        st = self.state[t]
        if st["date"] != today:
            st.update(self._fresh_state())
            st["date"] = today

        if st["closed"]:
            return

        # Set opening range once we have the first 30 minutes
        if st["or_high"] is None and len(bars) >= ORB_BARS:
            orb = bars[:ORB_BARS]
            st["or_high"] = max(b.high for b in orb)
            st["or_low"] = min(b.low for b in orb)

        if st["or_high"] is None:
            return

        last = bars[-1]
        price = float(last.close)

        # Not yet entered: look for breakout, enter on the bar *after* breakout
        if not st["entered"]:
            if st["breakout_seen"]:
                entry = price
                stop = st["or_low"]
                risk = entry - stop
                if risk <= 0:
                    st["closed"] = True  # invalid setup, skip rest of day
                    return
                st["entered"] = True
                st["entry"] = entry
                st["stop"] = stop
                st["target"] = entry + ORB_RR * risk
                self.send_alert(
                    f"⚡ 日內 — {t} ORB 突破進場 @ {entry:.2f}\n"
                    f"止損 {stop:.2f} · 目標 {st['target']:.2f} (2R) · 今日內收盤前出場"
                )
                return
            if len(bars) > ORB_BARS and price > st["or_high"]:
                st["breakout_seen"] = True
            return

        # Entered: check stop / target on this bar's range
        if last.low <= st["stop"]:
            self._close_trade(t, st, st["stop"], "stop")
        elif last.high >= st["target"]:
            self._close_trade(t, st, st["target"], "target")

    def eod_close(self) -> None:
        """Force-close any open day-trades at last known price (time exit)."""
        for t, c in self.contracts.items():
            st = self.state[t]
            if st["entered"] and not st["closed"]:
                bars = self.ib.reqHistoricalData(
                    c, endDateTime="", durationStr="1 D",
                    barSizeSetting="5 mins", whatToShow="TRADES",
                    useRTH=True, formatDate=1,
                )
                price = float(bars[-1].close) if bars else st["entry"]
                self._close_trade(t, st, price, "time")

    def _close_trade(self, t: str, st: dict, exit_px: float, reason: str) -> None:
        st["closed"] = True
        entry = st["entry"]
        pnl_pct = (exit_px - entry) / entry * 100
        self.ledger.setdefault("trades", []).append({
            "ticker": t, "date": str(st["date"]),
            "entry": round(entry, 2), "exit": round(exit_px, 2),
            "pnl_pct": round(pnl_pct, 2), "reason": reason,
            "closed_at": datetime.now(timezone.utc).isoformat(),
        })
        _save_ledger(self.ledger)
        tag = {"stop": "🔴 止損", "target": "🟢 達標", "time": "⏱ 收盤平倉"}[reason]
        self.send_alert(
            f"⚡ 日內 — {t} {tag} @ {exit_px:.2f} (進場 {entry:.2f}) · {pnl_pct:+.2f}%"
        )
