"""day_trading_backtest.py — Step 1 of Day-Trading Mode: define + backtest
intraday entry/exit rules BEFORE building any live engine.

Isolated from production (action_box.json, paper_portfolio.json, swing gate
untouched). Uses 5-min bars (yfinance 60-day limit = ~4680 bars/ticker).

Variants compared (one trade per ticker per day, long-only, exit by EOD):
    A  ORB    : Opening Range Breakout — entry on close > 30-min opening-range
                high, stop = OR low, target = entry + 2R, exit EOD if neither hit
    B  VWAP   : VWAP Reclaim — entry when price closes back above session VWAP
                after the opening 30 min, stop = -1%, target = +1.5%, exit EOD

Run:
    python3 src/day_trading_backtest.py

Output: outputs/day_trading_backtest.json + console summary table.
"""
import json
import os
import warnings

import pandas as pd
import yfinance as yf

warnings.filterwarnings("ignore")

PERIOD       = "60d"
INTERVAL     = "5m"
ORB_BARS     = 6        # first 30 min (6 x 5-min bars)
ORB_RR       = 2.0      # target = entry + ORB_RR x risk
VWAP_STOP    = 1.0      # %
VWAP_TARGET  = 1.5      # %

OUT_FILE = os.path.join("outputs", "day_trading_backtest.json")


def _session_days(df: pd.DataFrame):
    """Yield (date, day_df) for each regular-session trading day."""
    for date, day_df in df.groupby(df.index.date):
        if len(day_df) >= ORB_BARS + 2:
            yield date, day_df


def _orb_trade(day_df: pd.DataFrame) -> dict | None:
    orb = day_df.iloc[:ORB_BARS]
    or_high, or_low = float(orb["High"].max()), float(orb["Low"].min())
    rest = day_df.iloc[ORB_BARS:]

    breakout_idx = None
    for i in range(len(rest) - 1):  # leave room for next-bar entry
        if float(rest["Close"].iloc[i]) > or_high:
            breakout_idx = i
            break
    if breakout_idx is None:
        return None

    entry = float(rest["Open"].iloc[breakout_idx + 1])
    stop = or_low
    risk = entry - stop
    if risk <= 0:
        return None
    target = entry + ORB_RR * risk

    walk = rest.iloc[breakout_idx + 1:]
    exit_px, reason = None, "time"
    for _, bar in walk.iterrows():
        lo, hi = float(bar["Low"]), float(bar["High"])
        if lo <= stop:
            exit_px, reason = stop, "stop"
            break
        if hi >= target:
            exit_px, reason = target, "target"
            break
    if exit_px is None:
        exit_px = float(walk["Close"].iloc[-1])

    return {
        "entry": round(entry, 2), "exit": round(exit_px, 2),
        "pnl_pct": round((exit_px - entry) / entry * 100, 2),
        "reason": reason,
    }


def _vwap_trade(day_df: pd.DataFrame) -> dict | None:
    typical = (day_df["High"] + day_df["Low"] + day_df["Close"]) / 3
    vwap = (typical * day_df["Volume"]).cumsum() / day_df["Volume"].cumsum()

    reclaim_idx = None
    for i in range(ORB_BARS, len(day_df) - 1):
        prev_close, prev_vwap = float(day_df["Close"].iloc[i - 1]), float(vwap.iloc[i - 1])
        close, vw = float(day_df["Close"].iloc[i]), float(vwap.iloc[i])
        if prev_close < prev_vwap and close > vw:
            reclaim_idx = i
            break
    if reclaim_idx is None:
        return None

    entry = float(day_df["Open"].iloc[reclaim_idx + 1])
    stop = entry * (1 - VWAP_STOP / 100)
    target = entry * (1 + VWAP_TARGET / 100)

    walk = day_df.iloc[reclaim_idx + 1:]
    exit_px, reason = None, "time"
    for _, bar in walk.iterrows():
        lo, hi = float(bar["Low"]), float(bar["High"])
        if lo <= stop:
            exit_px, reason = stop, "stop"
            break
        if hi >= target:
            exit_px, reason = target, "target"
            break
    if exit_px is None:
        exit_px = float(walk["Close"].iloc[-1])

    return {
        "entry": round(entry, 2), "exit": round(exit_px, 2),
        "pnl_pct": round((exit_px - entry) / entry * 100, 2),
        "reason": reason,
    }


def _stats(trades: list[dict]) -> dict:
    if not trades:
        return {"trades": 0}
    wins = [t["pnl_pct"] for t in trades if t["pnl_pct"] > 0]
    losses = [t["pnl_pct"] for t in trades if t["pnl_pct"] <= 0]
    gross_win, gross_loss = sum(wins), abs(sum(losses))
    return {
        "trades": len(trades),
        "win_rate": round(len(wins) / len(trades) * 100, 1),
        "profit_factor": round(gross_win / gross_loss, 2) if gross_loss else float("inf"),
        "avg_win": round(sum(wins) / len(wins), 2) if wins else 0,
        "avg_loss": round(sum(losses) / len(losses), 2) if losses else 0,
        "total_pnl_pct": round(sum(t["pnl_pct"] for t in trades), 1),
        "expectancy": round(sum(t["pnl_pct"] for t in trades) / len(trades), 3),
        "stops_hit": sum(1 for t in trades if t["reason"] == "stop"),
        "targets_hit": sum(1 for t in trades if t["reason"] == "target"),
        "time_exits": sum(1 for t in trades if t["reason"] == "time"),
    }


def main() -> None:
    with open(os.path.join("config", "config.json"), encoding="utf-8") as f:
        cfg = json.load(f)
    tickers = [i["ticker"] for i in cfg["watchlist"] if not i["ticker"].endswith(".HK")]
    print(f"Day-trading backtest: {len(tickers)} tickers x {PERIOD} @ {INTERVAL}")
    print(f"  A=ORB(30min, {ORB_RR}R) · B=VWAP reclaim ({VWAP_STOP}% stop / {VWAP_TARGET}% target)")

    results = {"A": [], "B": []}
    per_ticker = {}
    for n, t in enumerate(tickers, 1):
        try:
            df = yf.download(t, period=PERIOD, interval=INTERVAL,
                              auto_adjust=True, progress=False)
            if isinstance(df.columns, pd.MultiIndex):
                df.columns = df.columns.get_level_values(0)
            if df.empty:
                print(f"  [{n:2}/{len(tickers)}] {t}: no data — skipped")
                continue

            tr_a, tr_b = [], []
            for _, day_df in _session_days(df):
                a = _orb_trade(day_df)
                if a:
                    tr_a.append(a)
                b = _vwap_trade(day_df)
                if b:
                    tr_b.append(b)

            results["A"].extend(tr_a)
            results["B"].extend(tr_b)
            per_ticker[t] = {"orb_trades": len(tr_a), "vwap_trades": len(tr_b)}
            print(f"  [{n:2}/{len(tickers)}] {t}: ORB {len(tr_a)} · VWAP {len(tr_b)}")
        except Exception as e:
            print(f"  [{n:2}/{len(tickers)}] {t}: error {e} — skipped")

    summary = {
        "generated": pd.Timestamp.now().strftime("%Y-%m-%d %H:%M"),
        "period": PERIOD, "interval": INTERVAL,
        "variant_A": {"label": f"ORB 30min, {ORB_RR}R, exit EOD", **_stats(results["A"])},
        "variant_B": {"label": f"VWAP reclaim, -{VWAP_STOP}%/+{VWAP_TARGET}%, exit EOD", **_stats(results["B"])},
        "per_ticker": per_ticker,
        "trades_A": results["A"][-300:],
        "trades_B": results["B"][-300:],
    }
    os.makedirs("outputs", exist_ok=True)
    with open(OUT_FILE, "w", encoding="utf-8") as f:
        json.dump(summary, f, ensure_ascii=False, indent=1)

    print("\n========== RESULTS ==========")
    for k in ("variant_A", "variant_B"):
        s = summary[k]
        print(f"\n{k}  ({s['label']})")
        if s.get("trades", 0) == 0:
            print("  no trades")
            continue
        print(f"  trades {s['trades']} | win rate {s['win_rate']}% | profit factor {s['profit_factor']}")
        print(f"  avg win {s['avg_win']}% | avg loss {s['avg_loss']}% | expectancy {s['expectancy']}%/trade")
        print(f"  exits - stop {s['stops_hit']} / target {s['targets_hit']} / time {s['time_exits']}")
    print(f"\nSaved -> {OUT_FILE}")


if __name__ == "__main__":
    main()
