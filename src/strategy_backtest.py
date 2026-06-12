"""strategy_backtest.py — Historical replay of the exact Action Box rules.

Answers: "if I had followed the dashboard's BUY tickets for the last 3 years,
what would have happened?" — evidence now instead of waiting out the
60-day forward gate blind.

Entry rule (identical to the Action Box / paper engine):
    entry verdict GO ✅ or BREAKOUT ↑  AND  score >= 70
    (verdict + score computed bar-by-bar with no lookahead)

Exit variants compared:
    A  fixed      : stop −8% · target +12% · max 10 trading days   (current production)
    B  ATR stop   : stop entry − 2.5×ATR(14) · target +12% · max 10 days

Run locally (couple of minutes for 30 tickers × 3y):

    python3 src/strategy_backtest.py

Output: outputs/strategy_backtest.json + console summary table.
"""
import json
import os
import sys
import warnings

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(__file__))
from technical_analysis import calculate_indicators
from report_generator import _entry_verdict

warnings.filterwarnings("ignore")

YEARS          = 3
WARMUP_BARS    = 260      # bars needed before first signal (EMA200 etc.)
MIN_SCORE      = 70
HOLD_DAYS      = 10
TARGET_PCT     = 12.0
STOP_PCT       = 8.0
ATR_PERIOD     = 14
ATR_MULT       = 2.5
COOLDOWN_BARS  = 10       # one position per ticker at a time (approximation)

OUT_FILE = os.path.join("outputs", "strategy_backtest.json")


def _atr(df: pd.DataFrame, period: int = ATR_PERIOD) -> pd.Series:
    hi, lo, cl = df["High"], df["Low"], df["Close"]
    tr = pd.concat([
        hi - lo,
        (hi - cl.shift(1)).abs(),
        (lo - cl.shift(1)).abs(),
    ], axis=1).max(axis=1)
    return tr.rolling(period).mean()


def _entry_ok(ta: dict) -> bool:
    """Same gate as _build_action_box / paper engine."""
    if ta.get("score", 0) < MIN_SCORE:
        return False
    v = _entry_verdict(
        ta["score"], ta.get("bb_pct"), ta.get("rsi"), ta.get("bb_squeeze", False),
        bb_squeeze_breakout_up=ta.get("bb_squeeze_breakout_up", False),
        bb_squeeze_breakout_down=ta.get("bb_squeeze_breakout_down", False),
        bb_walking_up=ta.get("bb_walking_up", False),
        bb_walking_down=ta.get("bb_walking_down", False),
        kd_golden_cross_low=ta.get("kd_golden_cross_low", False),
        bb_lower_touch=ta.get("bb_lower_touch", False),
        bb_upper_touch=ta.get("bb_upper_touch", False),
    ) or {}
    label = v.get("label", "")
    return "GO" in label or "BREAKOUT ↑" in label


def _simulate(df: pd.DataFrame, signals: list[int], variant: str) -> list[dict]:
    """Walk forward from each signal bar. Entry = next bar open."""
    atr = _atr(df)
    trades = []
    blocked_until = -1
    for i in signals:
        if i <= blocked_until or i + 1 >= len(df):
            continue
        entry = float(df["Open"].iloc[i + 1])
        if entry <= 0:
            continue
        if variant == "A":
            stop = entry * (1 - STOP_PCT / 100)
        else:
            a = float(atr.iloc[i]) if pd.notna(atr.iloc[i]) else None
            if not a or a <= 0:
                continue
            stop = entry - ATR_MULT * a
        target = entry * (1 + TARGET_PCT / 100)

        exit_px, exit_reason, exit_bar = None, "time", min(i + 1 + HOLD_DAYS, len(df) - 1)
        for j in range(i + 1, exit_bar + 1):
            lo, hi = float(df["Low"].iloc[j]), float(df["High"].iloc[j])
            # conservative: stop checked before target within the same bar
            if lo <= stop:
                exit_px, exit_reason, exit_bar = stop, "stop", j
                break
            if hi >= target:
                exit_px, exit_reason, exit_bar = target, "target", j
                break
        if exit_px is None:
            exit_px = float(df["Close"].iloc[exit_bar])
        pnl_pct = (exit_px - entry) / entry * 100
        trades.append({
            "date": str(df.index[i].date()), "entry": round(entry, 2),
            "exit": round(exit_px, 2), "pnl_pct": round(pnl_pct, 2),
            "reason": exit_reason, "held": exit_bar - i,
        })
        blocked_until = exit_bar
    return trades


def _stats(trades: list[dict]) -> dict:
    if not trades:
        return {"trades": 0}
    wins   = [t["pnl_pct"] for t in trades if t["pnl_pct"] > 0]
    losses = [t["pnl_pct"] for t in trades if t["pnl_pct"] <= 0]
    gross_win  = sum(wins)
    gross_loss = abs(sum(losses))
    return {
        "trades":        len(trades),
        "win_rate":      round(len(wins) / len(trades) * 100, 1),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else float("inf"),
        "avg_win":       round(sum(wins) / len(wins), 2) if wins else 0,
        "avg_loss":      round(sum(losses) / len(losses), 2) if losses else 0,
        "total_pnl_pct": round(sum(t["pnl_pct"] for t in trades), 1),
        "expectancy":    round(sum(t["pnl_pct"] for t in trades) / len(trades), 3),
        "stops_hit":     sum(1 for t in trades if t["reason"] == "stop"),
        "targets_hit":   sum(1 for t in trades if t["reason"] == "target"),
        "time_exits":    sum(1 for t in trades if t["reason"] == "time"),
    }


def main() -> None:
    with open(os.path.join("config", "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    tickers = [i["ticker"] for i in cfg["watchlist"] if not i["ticker"].endswith(".HK")]
    print(f"Backtesting {len(tickers)} tickers × {YEARS}y — entry: verdict GO/BREAKOUT↑ + score≥{MIN_SCORE}")

    results = {"A": [], "B": []}
    per_ticker = {}
    for n, t in enumerate(tickers, 1):
        try:
            df = yf.download(t, period=f"{YEARS}y", interval="1d",
                             auto_adjust=True, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if df.empty or len(df) < WARMUP_BARS + 30:
                print(f"  [{n:2}/{len(tickers)}] {t}: insufficient history — skipped")
                continue

            # bar-by-bar signal scan (no lookahead: indicators on data up to bar i)
            signals = []
            for i in range(WARMUP_BARS, len(df) - 1):
                ta = calculate_indicators(df.iloc[: i + 1])
                if _entry_ok(ta):
                    signals.append(i)

            ta_count = len(signals)
            tr_a = _simulate(df, signals, "A")
            tr_b = _simulate(df, signals, "B")
            results["A"].extend(tr_a)
            results["B"].extend(tr_b)
            per_ticker[t] = {"signals": ta_count, "trades": len(tr_a)}
            print(f"  [{n:2}/{len(tickers)}] {t}: {ta_count} signals → {len(tr_a)} trades")
        except Exception as e:
            print(f"  [{n:2}/{len(tickers)}] {t}: error {e} — skipped")

    summary = {
        "generated":   pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "rule":        f"verdict GO/BREAKOUT↑ + score>={MIN_SCORE}, next-bar-open entry",
        "variant_A":   {"label": f"fixed −{STOP_PCT}% / +{TARGET_PCT}% / {HOLD_DAYS}d", **_stats(results["A"])},
        "variant_B":   {"label": f"{ATR_MULT}×ATR({ATR_PERIOD}) stop / +{TARGET_PCT}% / {HOLD_DAYS}d", **_stats(results["B"])},
        "per_ticker":  per_ticker,
        "trades_A":    results["A"][-300:],
        "trades_B":    results["B"][-300:],
    }
    os.makedirs("outputs", exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)

    print("\n══════════ RESULTS ══════════")
    for k in ("variant_A", "variant_B"):
        s = summary[k]
        print(f"\n{k}  ({s['label']})")
        if s.get("trades", 0) == 0:
            print("  no trades")
            continue
        print(f"  trades {s['trades']} · win rate {s['win_rate']}% · profit factor {s['profit_factor']}")
        print(f"  avg win {s['avg_win']}% · avg loss {s['avg_loss']}% · expectancy {s['expectancy']}%/trade")
        print(f"  exits — stop {s['stops_hit']} / target {s['targets_hit']} / time {s['time_exits']}")
    print(f"\nSaved → {OUT_FILE}")


if __name__ == "__main__":
    main()
