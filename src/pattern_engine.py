"""pattern_engine.py — Named technical pattern detection and lifecycle tracking.

Detects 10 named patterns per ticker by evaluating today's indicator DataFrame.
Tracks each pattern's full lifecycle: start → active (persists) → end.

Persistence
-----------
outputs/pattern_history.json  — current active/ended state per ticker × pattern
outputs/pattern_events.json   — full historical event log (consumed by pattern_backtest)
"""

import os
import json
from datetime import datetime

import pandas as pd

PATTERN_HISTORY_FILE = os.path.join("outputs", "pattern_history.json")
PATTERN_EVENTS_FILE  = os.path.join("outputs", "pattern_events.json")


# ── Pattern condition functions ───────────────────────────────────────────────
# Each receives (row, prev) — the latest and previous indicator rows.
# Returns True if the pattern condition holds TODAY (state-based, not crossover).
# The engine infers "start" / "end" events by comparing to yesterday's stored state.

def _golden_cross(row, prev):
    """MA5 > MA20 — mid-term uptrend alignment."""
    return (not pd.isna(row["MA5"]) and not pd.isna(row["MA20"])
            and float(row["MA5"]) > float(row["MA20"]))


def _death_cross(row, prev):
    """MA5 < MA20 — mid-term downtrend alignment."""
    return (not pd.isna(row["MA5"]) and not pd.isna(row["MA20"])
            and float(row["MA5"]) < float(row["MA20"]))


def _macd_bull(row, prev):
    """MACD line > signal line — bullish momentum."""
    return (not pd.isna(row["MACD"]) and not pd.isna(row["MACD_signal"])
            and float(row["MACD"]) > float(row["MACD_signal"]))


def _macd_bear(row, prev):
    """MACD line < signal line — bearish momentum."""
    return (not pd.isna(row["MACD"]) and not pd.isna(row["MACD_signal"])
            and float(row["MACD"]) < float(row["MACD_signal"]))


def _rsi_oversold_bounce(row, prev):
    """RSI in 30–45 zone and rising — oversold recovery."""
    if pd.isna(row["RSI"]) or pd.isna(prev["RSI"]):
        return False
    rsi = float(row["RSI"])
    return 30 <= rsi <= 45 and rsi > float(prev["RSI"])


def _rsi_overbought(row, prev):
    """RSI > 70 and falling — overbought caution zone."""
    if pd.isna(row["RSI"]) or pd.isna(prev["RSI"]):
        return False
    rsi = float(row["RSI"])
    return rsi > 70 and rsi < float(prev["RSI"])


def _volume_breakout(row, prev):
    """Price up + volume ≥ 2× MA20 — strong buying surge."""
    if pd.isna(row["Vol_ratio"]) or pd.isna(prev["Close"]):
        return False
    return (float(row["Vol_ratio"]) >= 2.0
            and float(row["Close"]) > float(prev["Close"]))


def _volume_breakdown(row, prev):
    """Price down + volume ≥ 2× MA20 — strong selling surge."""
    if pd.isna(row["Vol_ratio"]) or pd.isna(prev["Close"]):
        return False
    return (float(row["Vol_ratio"]) >= 2.0
            and float(row["Close"]) < float(prev["Close"]))


def _above_ma60(row, prev):
    """Price above MA60 — holding above long-term trend."""
    return (not pd.isna(row["MA60"])
            and float(row["Close"]) > float(row["MA60"]))


def _below_ma60(row, prev):
    """Price below MA60 — below long-term trend."""
    return (not pd.isna(row["MA60"])
            and float(row["Close"]) < float(row["MA60"]))


# ── BB Squeeze Breakout patterns (2-row: needs prev + latest) ─────────────────

def _bb_squeeze_breakout_up(row, prev):
    """BB squeeze just fired upward — bands expanding after compression, price near upper band."""
    for col in ("BB_bw", "BB_bw_avg"):
        if col not in row.index or pd.isna(row[col]):
            return False
        if col not in prev.index or pd.isna(prev[col]):
            return False
    if "BB_pct" not in row.index or pd.isna(row["BB_pct"]):
        return False
    prev_squeezed   = float(prev["BB_bw"]) < float(prev["BB_bw_avg"]) * 0.75
    today_expanding = float(row["BB_bw"]) >= float(row["BB_bw_avg"]) * 0.75
    price_up        = float(row["BB_pct"]) > 0.85
    return prev_squeezed and today_expanding and price_up


def _bb_squeeze_breakout_down(row, prev):
    """BB squeeze just fired downward — bands expanding after compression, price near lower band."""
    for col in ("BB_bw", "BB_bw_avg"):
        if col not in row.index or pd.isna(row[col]):
            return False
        if col not in prev.index or pd.isna(prev[col]):
            return False
    if "BB_pct" not in row.index or pd.isna(row["BB_pct"]):
        return False
    prev_squeezed   = float(prev["BB_bw"]) < float(prev["BB_bw_avg"]) * 0.75
    today_expanding = float(row["BB_bw"]) >= float(row["BB_bw_avg"]) * 0.75
    price_down      = float(row["BB_pct"]) < 0.15
    return prev_squeezed and today_expanding and price_down


# ── Pattern registry ──────────────────────────────────────────────────────────
# name → (condition_fn, direction, zh_description)

PATTERNS: dict[str, tuple] = {
    "Golden Cross":        (_golden_cross,        "buy",  "MA5 > MA20 — 中期多頭排列"),
    "Death Cross":         (_death_cross,         "sell", "MA5 < MA20 — 中期空頭排列"),
    "MACD Bull":           (_macd_bull,           "buy",  "MACD > 信號線 — 多頭動能持續"),
    "MACD Bear":           (_macd_bear,           "sell", "MACD < 信號線 — 空頭動能持續"),
    "RSI Oversold Bounce": (_rsi_oversold_bounce, "buy",  "RSI 30-45 回升 — 超賣反彈中"),
    "RSI Overbought":      (_rsi_overbought,      "sell", "RSI > 70 且回落 — 超買警戒"),
    "Volume Breakout":     (_volume_breakout,     "buy",  "爆量上漲 (≥2× 均量) — 強勢突破"),
    "Volume Breakdown":    (_volume_breakdown,    "sell", "爆量下跌 (≥2× 均量) — 強勢殺盤"),
    "Above MA60":          (_above_ma60,          "buy",  "站上 MA60 — 站穩長期均線"),
    "Below MA60":          (_below_ma60,          "sell", "跌破 MA60 — 跌破長期均線"),
    "BB Squeeze Breakout Up":   (_bb_squeeze_breakout_up,   "buy",  "BB擠壓向上突破 — 低波動蓄勢後能量向上釋放"),
    "BB Squeeze Breakout Down": (_bb_squeeze_breakout_down, "sell", "BB擠壓向下突破 — 低波動蓄勢後向下破位"),
}


# ── BB Walking: multi-bar detection (needs full df, not just row+prev) ──────────
# Checks last N consecutive bars of BB%B — can't be expressed as a 2-row condition.

_WALK_BARS       = 3
_WALK_UP_THRESH  = 0.80   # BB%B > 0.80 for N bars = walking upper band
_WALK_DOWN_THRESH= 0.20   # BB%B < 0.20 for N bars = walking lower band

MULTIBAR_PATTERNS: dict[str, tuple] = {
    "BB Walking Up":   ("buy",  "BB走軌向上 — 連續貼近上軌，趨勢強勁，持倉勿急出"),
    "BB Walking Down": ("sell", "BB走軌向下 — 連續貼近下軌，下跌趨勢持續，避免做多"),
}


def _detect_walking_patterns(df: pd.DataFrame) -> dict[str, bool]:
    """Return {pattern_name: is_active} for BB Walking patterns."""
    result = {name: False for name in MULTIBAR_PATTERNS}
    if len(df) < _WALK_BARS or "BB_pct" not in df.columns:
        return result
    recent = df["BB_pct"].dropna().tail(_WALK_BARS)
    if len(recent) < _WALK_BARS:
        return result
    result["BB Walking Up"]   = bool(all(v > _WALK_UP_THRESH   for v in recent))
    result["BB Walking Down"] = bool(all(v < _WALK_DOWN_THRESH for v in recent))
    return result


# ── Persistence helpers ───────────────────────────────────────────────────────

def _load_history() -> dict:
    try:
        with open(PATTERN_HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _save_history(h: dict) -> None:
    os.makedirs(os.path.dirname(PATTERN_HISTORY_FILE) or ".", exist_ok=True)
    with open(PATTERN_HISTORY_FILE, "w", encoding="utf-8") as f:
        json.dump(h, f, ensure_ascii=False, indent=2)


def _load_events() -> list:
    try:
        with open(PATTERN_EVENTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save_events(events: list) -> None:
    os.makedirs(os.path.dirname(PATTERN_EVENTS_FILE) or ".", exist_ok=True)
    with open(PATTERN_EVENTS_FILE, "w", encoding="utf-8") as f:
        json.dump(events, f, ensure_ascii=False, indent=2)


# ── Core detection ────────────────────────────────────────────────────────────

def detect_patterns(df: pd.DataFrame) -> dict[str, bool]:
    """Return {pattern_name: is_active_today} for a single ticker's indicator df."""
    if len(df) < 2:
        return {name: False for name in PATTERNS}
    row  = df.iloc[-1]
    prev = df.iloc[-2]
    result: dict[str, bool] = {}
    for name, (fn, _dir, _desc) in PATTERNS.items():
        try:
            result[name] = bool(fn(row, prev))
        except Exception:
            result[name] = False
    return result


# ── Main pipeline entry ───────────────────────────────────────────────────────

def run_pattern_scan(
    stock_results: list,
    ta_dfs: dict,          # {ticker: indicator DataFrame from calculate_indicators()["df"]}
    today_str: str,        # YYYY-MM-DD
) -> dict:
    """Scan all tickers, update lifecycle state, return active patterns per ticker.

    Returns
    -------
    active_by_ticker : dict
        {ticker: [{name, direction, desc, start_date, days_active}]}
        Only tickers with ≥1 active pattern are included.

    Side effects
    ------------
    - Updates outputs/pattern_history.json (current state)
    - Appends new start/end events to outputs/pattern_events.json
    """
    history    = _load_history()
    events     = _load_events()
    new_events: list = []

    active_by_ticker: dict = {}

    for item in stock_results:
        ticker = item["ticker"]
        df     = ta_dfs.get(ticker)
        if df is None or len(df) < 2:
            continue

        today_state  = detect_patterns(df)
        ticker_hist  = history.setdefault(ticker, {})
        ticker_active: list = []

        for name, (fn, direction, desc) in PATTERNS.items():
            is_active = today_state.get(name, False)
            stored    = ticker_hist.get(name)           # {"start": "...", "end": null|str}
            was_active = stored is not None and stored.get("end") is None

            if is_active and not was_active:
                # Pattern just started today
                ticker_hist[name] = {"start": today_str, "end": None}
                new_events.append({
                    "date":      today_str,
                    "ticker":    ticker,
                    "pattern":   name,
                    "direction": direction,
                    "type":      "start",
                    "price":     round(float(item.get("price", 0)), 2),
                    "score":     item.get("score", 0),
                })

            elif not is_active and was_active:
                # Pattern just ended today
                ticker_hist[name]["end"] = today_str
                new_events.append({
                    "date":      today_str,
                    "ticker":    ticker,
                    "pattern":   name,
                    "direction": direction,
                    "type":      "end",
                    "price":     round(float(item.get("price", 0)), 2),
                })

            if is_active:
                start = ticker_hist[name]["start"]
                try:
                    days = (
                        datetime.strptime(today_str, "%Y-%m-%d")
                        - datetime.strptime(start, "%Y-%m-%d")
                    ).days + 1
                except Exception:
                    days = 1
                ticker_active.append({
                    "name":        name,
                    "direction":   direction,
                    "desc":        desc,
                    "start_date":  start,
                    "days_active": days,
                })

        # ── Multibar patterns (BB Walking) ───────────────────────────────────
        walking_state = _detect_walking_patterns(df)
        for walk_name, (walk_dir, walk_desc) in MULTIBAR_PATTERNS.items():
            is_active  = walking_state.get(walk_name, False)
            stored     = ticker_hist.get(walk_name)
            was_active = stored is not None and stored.get("end") is None

            if is_active and not was_active:
                ticker_hist[walk_name] = {"start": today_str, "end": None}
                new_events.append({
                    "date":      today_str,
                    "ticker":    ticker,
                    "pattern":   walk_name,
                    "direction": walk_dir,
                    "type":      "start",
                    "price":     round(float(item.get("price", 0)), 2),
                    "score":     item.get("score", 0),
                })
            elif not is_active and was_active:
                ticker_hist[walk_name]["end"] = today_str
                new_events.append({
                    "date":      today_str,
                    "ticker":    ticker,
                    "pattern":   walk_name,
                    "direction": walk_dir,
                    "type":      "end",
                    "price":     round(float(item.get("price", 0)), 2),
                })

            if is_active:
                start = ticker_hist[walk_name]["start"]
                try:
                    days = (
                        datetime.strptime(today_str, "%Y-%m-%d")
                        - datetime.strptime(start, "%Y-%m-%d")
                    ).days + 1
                except Exception:
                    days = 1
                ticker_active.append({
                    "name":        walk_name,
                    "direction":   walk_dir,
                    "desc":        walk_desc,
                    "start_date":  start,
                    "days_active": days,
                })

        if ticker_active:
            active_by_ticker[ticker] = ticker_active

    if new_events:
        events.extend(new_events)
        _save_events(events)

    _save_history(history)

    n_new = sum(1 for e in new_events if e["type"] == "start")
    n_end = sum(1 for e in new_events if e["type"] == "end")
    print(f"  [pattern_engine] {len(active_by_ticker)} tickers active · "
          f"+{n_new} new / -{n_end} ended today")

    return active_by_ticker


# ── Telegram alert formatter ──────────────────────────────────────────────────

def format_pattern_alert(new_events: list, today_str: str) -> str:
    """Format a Telegram message for newly started patterns."""
    starts = [e for e in new_events if e["type"] == "start"]
    if not starts:
        return ""

    buys  = [e for e in starts if e["direction"] == "buy"]
    sells = [e for e in starts if e["direction"] == "sell"]

    lines = [
        "🔍 <b>Pattern Alert｜新信號</b>",
        f"📅 {today_str}",
        "",
    ]

    # Build combined pattern description lookup (PATTERNS + MULTIBAR_PATTERNS)
    def _get_desc(pattern_name: str) -> str:
        if pattern_name in PATTERNS:
            return PATTERNS[pattern_name][2]
        if pattern_name in MULTIBAR_PATTERNS:
            return MULTIBAR_PATTERNS[pattern_name][1]
        return ""

    if buys:
        lines.append("🟢 <b>買入信號</b>")
        for e in buys:
            desc = _get_desc(e["pattern"])
            lines.append(f"  • <b>{e['ticker']}</b> — {e['pattern']}  <i>({desc})</i>  @ ${e['price']:.2f}")
        lines.append("")

    if sells:
        lines.append("🔴 <b>賣出信號</b>")
        for e in sells:
            desc = _get_desc(e["pattern"])
            lines.append(f"  • <b>{e['ticker']}</b> — {e['pattern']}  <i>({desc})</i>  @ ${e['price']:.2f}")
        lines.append("")

    lines.append("⚠️ 僅供參考，不構成投資建議")
    return "\n".join(lines)


def get_todays_new_events(today_str: str) -> list:
    """Return today's new start events from pattern_events.json."""
    events = _load_events()
    return [e for e in events if e["date"] == today_str and e["type"] == "start"]
