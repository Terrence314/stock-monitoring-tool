"""Which entry signal, in which market regime — measured, not assumed.

The engine buys on three conditions whose forward returns are negative in
outputs/pattern_backtest.html: Golden Cross (n=121, -2.24% over 10 days),
MACD Bull (n=81, -1.85%) and Above MA60 (n=145, -1.51%). Every open position
carries all three.

Two hypotheses explain that, and they imply opposite fixes:

  REGIME  — trend-following signals lose in chop and win in trends, and the
            2024-2026 window was mostly chop. Fix the regime filter, keep the
            signals.
  LEVEL   — the signals are states, not events. `_golden_cross` is
            `MA5 > MA20`, which is true for the whole of an uptrend, so the
            engine buys the late middle of moves as readily as the start.
            Fix the signals, measure acceleration instead of level.

This module tests both at once: every variant is scored separately inside
each regime. It is research, not production — nothing here feeds the live
engine, and no result should be wired in without an out-of-sample check.

Run:
    python3 src/signal_research.py

Output: outputs/signal_research.json + a console table.
"""
from __future__ import annotations

import json
import os
import sys
import warnings
from datetime import date

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from technical_analysis import _macd, _rsi, _stochastic        # noqa: E402
from trading_costs import DEFAULT_NOTIONAL_USD, round_trip_pct  # noqa: E402

warnings.filterwarnings("ignore")

HOLD_DAYS   = 10     # match the live engine, so results are comparable to it
COOLDOWN    = 10     # no re-entry in the same name inside a live position
LOOKBACK_Y  = 2
BENCHMARK   = "SPY"
OUT_FILE    = os.path.join("outputs", "signal_research.json")

# Kaufman efficiency ratio: net move over the sum of daily moves. High means
# price travelled in a line, low means it churned. This is the cleanest
# available separator of "trend" from "chop" and needs no fitted parameter.
ER_WINDOW   = 20
ER_TRENDING = 0.30


# ── Indicators ────────────────────────────────────────────────────────────────

def _frame(df: pd.DataFrame) -> pd.DataFrame:
    f = pd.DataFrame(index=df.index)
    c = df["Close"]
    f["close"] = c
    f["ma5"]   = c.rolling(5).mean()
    f["ma20"]  = c.rolling(20).mean()
    f["ma60"]  = c.rolling(60).mean()
    f["rsi"]   = _rsi(c)
    _macd_line, _sig, hist = _macd(c)
    f["macd"], f["macd_signal"], f["hist"] = _macd_line, _sig, hist
    f["k"], f["d"] = _stochastic(df["High"], df["Low"], c)
    return f


def _efficiency_ratio(close: pd.Series, window: int = ER_WINDOW) -> pd.Series:
    net = (close - close.shift(window)).abs()
    path = close.diff().abs().rolling(window).sum()
    return net / path.replace(0, float("nan"))


# ── Signal variants ───────────────────────────────────────────────────────────
# Each returns a boolean Series. "state" variants are what the engine uses now;
# "event" and "slope" variants are the alternatives under test.

def _rising(s: pd.Series, n: int) -> pd.Series:
    """True where s has increased on each of the last n bars."""
    out = pd.Series(True, index=s.index)
    for i in range(n):
        out &= s.shift(i) > s.shift(i + 1)
    return out


# The control. Enters every name every COOLDOWN days regardless of any signal,
# so its alpha is what the universe itself pays over the benchmark. A signal is
# only worth running if it beats THIS, not if it beats zero: a variant showing
# -0.10% alpha in a universe that pays -0.19% is adding value, and one showing
# +0.05% in a universe that pays +0.10% is destroying it. Without this row the
# whole table is unreadable.
NULL_BASELINE = lambda f: pd.Series(True, index=f.index)   # noqa: E731

VARIANTS = {
    "NULL_buy_anything":    NULL_BASELINE,
    # --- what the engine does today -----------------------------------------
    "golden_cross_STATE":   lambda f: f["ma5"] > f["ma20"],
    "macd_bull_STATE":      lambda f: f["macd"] > f["macd_signal"],
    "above_ma60_STATE":     lambda f: f["close"] > f["ma60"],
    "engine_combo_STATE":   lambda f: ((f["ma5"] > f["ma20"])
                                       & (f["macd"] > f["macd_signal"])
                                       & (f["close"] > f["ma60"])),
    # --- same conditions, first day only (the actual "cross") ---------------
    "golden_cross_EVENT":   lambda f: (f["ma5"] > f["ma20"]) & (f["ma5"].shift(1) <= f["ma20"].shift(1)),
    "macd_bull_EVENT":      lambda f: (f["macd"] > f["macd_signal"]) & (f["macd"].shift(1) <= f["macd_signal"].shift(1)),
    # --- rate of change rather than level ------------------------------------
    "hist_expanding":       lambda f: (f["hist"] > 0) & _rising(f["hist"], 2),
    "hist_recovering":      lambda f: (f["hist"] < 0) & _rising(f["hist"], 3),
    "rsi50_rising":         lambda f: (f["rsi"] > 50) & _rising(f["rsi"], 1),
    # --- the confluence rule from the Threads post ---------------------------
    "post_confluence":      lambda f: ((f["k"] > 50) & (f["rsi"] > 50)
                                       & (f["hist"] > 0) & _rising(f["hist"], 2)),
}


# ── Evaluation ────────────────────────────────────────────────────────────────

def _forward_returns(frames: dict, regimes: pd.Series, fire,
                     bench_fwd: pd.Series | None = None) -> list[dict]:
    """Net forward return for every firing, deduped to one live position.

    A state variant is true on every day of a trend, so without the cooldown it
    would produce ten overlapping entries where the engine could hold only one.
    Deduping to HOLD_DAYS makes state and event variants comparable instead of
    rewarding whichever one fires most often.
    """
    rows = []
    for ticker, f in frames.items():
        sig = fire(f).fillna(False)
        last = None
        for i, (dt, on) in enumerate(sig.items()):
            if not on or i + HOLD_DAYS >= len(f):
                continue
            if last is not None and (i - last) < COOLDOWN:
                continue
            entry = float(f["close"].iloc[i])
            exit_ = float(f["close"].iloc[i + HOLD_DAYS])
            if entry <= 0:
                continue
            gross = (exit_ - entry) / entry * 100
            net   = gross - round_trip_pct(entry, exit_, DEFAULT_NOTIONAL_USD)
            key   = dt.normalize() if hasattr(dt, "normalize") else dt
            # Raw return is not evidence. Over a rising two-year window every
            # long signal prints positive, so the only figure that separates a
            # signal from the market it fired in is the excess over holding the
            # index for the same ten days. Omitting this is the same defect
            # this repo's other backtests had.
            bench = float(bench_fwd.get(key, float("nan"))) if bench_fwd is not None else float("nan")
            rows.append({"ticker": ticker, "date": str(key)[:10], "net": net,
                         "alpha": (net - bench) if bench == bench else None,
                         "regime": regimes.get(key, "unknown")})
            last = i
    return rows


def _summarise(rows: list[dict]) -> dict:
    if not rows:
        return {"n": 0}
    v = [r["net"] for r in rows]
    a = [r["alpha"] for r in rows if r.get("alpha") is not None]
    wins = [x for x in v if x > 0]
    # Entries within HOLD_DAYS of each other measure the same market move, so
    # the honest sample size is the number of distinct windows, not of trades.
    windows = len({r["date"][:7] + str(int(r["date"][8:10]) // HOLD_DAYS) for r in rows})
    return {
        "n": len(v),
        "independent_windows": windows,
        "win_rate": round(len(wins) / len(v) * 100, 1),
        "avg_net": round(sum(v) / len(v), 2),
        "avg_alpha": round(sum(a) / len(a), 2) if a else None,
        "beat_bench_pct": round(sum(1 for x in a if x > 0) / len(a) * 100, 1) if a else None,
    }


# The in-sample window this study was built on, and an earlier window it never
# saw. Every conclusion below was chosen while looking at IN_SAMPLE, so
# IN_SAMPLE cannot test it — the regime split, the ER threshold and the
# variant list were all picked with that data in view. OUT_OF_SAMPLE covers
# the 2022 bear and the 2023 recovery, which is the harder test: a regime
# filter that only works in the tape it was designed on is a curve fit.
IN_SAMPLE     = ("2024-08-20", "2026-08-20")
OUT_OF_SAMPLE = ("2022-01-01", "2024-08-01")


def main(window: tuple[str, str] | None = None, label: str = "in-sample") -> dict:
    start, end = window or IN_SAMPLE
    events = json.load(open(os.path.join("outputs", "pattern_events.json")))
    tickers = sorted({e["ticker"] for e in events if e.get("ticker")})
    print(f"  [signal_research] {label}: {start} -> {end}, {len(tickers)} tickers…")

    raw = yf.download(tickers + [BENCHMARK], start=start, end=end,
                      progress=False, auto_adjust=True, group_by="ticker")

    bench = raw[BENCHMARK].dropna(how="all")
    er    = _efficiency_ratio(bench["Close"])
    above = bench["Close"] > bench["Close"].rolling(200).mean()
    regimes = pd.Series(
        [("trend_up" if a else "chop_or_down") if e >= ER_TRENDING else "chop_or_down"
         for e, a in zip(er.fillna(0), above.fillna(False))],
        index=bench.index)

    bc = bench["Close"]
    bench_fwd = (bc.shift(-HOLD_DAYS) - bc) / bc * 100   # index return over the same window

    frames = {}
    for t in tickers:
        try:
            df = raw[t].dropna(how="all")
        except Exception:
            continue
        if len(df) < 220:
            continue
        frames[t] = _frame(df)
    print(f"  [signal_research] {len(frames)} usable · "
          f"trend_up days {int((regimes == 'trend_up').sum())} / "
          f"chop {int((regimes == 'chop_or_down').sum())}\n")

    report = {"generated": str(date.today()), "hold_days": HOLD_DAYS,
              "window": {"label": label, "start": start, "end": end},
              "notional_usd": DEFAULT_NOTIONAL_USD, "variants": {}}

    hdr = (f"{'variant':24} {'n':>5} {'net%':>7} {'ALPHA%':>7} {'beat':>6} | "
           f"{'TRENDn':>6} {'alpha':>7} | {'CHOPn':>6} {'alpha':>7}")
    print(hdr); print("-" * len(hdr))
    for name, fire in VARIANTS.items():
        rows = _forward_returns(frames, regimes, fire, bench_fwd)
        allr = _summarise(rows)
        tr   = _summarise([r for r in rows if r["regime"] == "trend_up"])
        ch   = _summarise([r for r in rows if r["regime"] == "chop_or_down"])
        report["variants"][name] = {"all": allr, "trend_up": tr, "chop_or_down": ch}
        def _a(d): 
            x = d.get("avg_alpha")
            return x if x is not None else 0.0
        print(f"{name:24} {allr.get('n',0):5} {allr.get('avg_net',0):+7.2f} "
              f"{_a(allr):+7.2f} {allr.get('beat_bench_pct') or 0:5.1f}% | "
              f"{tr.get('n',0):6} {_a(tr):+7.2f} | {ch.get('n',0):6} {_a(ch):+7.2f}")

    os.makedirs("outputs", exist_ok=True)
    out = OUT_FILE if label == "in-sample" else OUT_FILE.replace(
        ".json", f"_{label.replace('-', '_')}.json")
    json.dump(report, open(out, "w"), indent=2)
    print(f"\n  saved -> {out}")
    return report


if __name__ == "__main__":
    which = sys.argv[1] if len(sys.argv) > 1 else "in-sample"
    main(OUT_OF_SAMPLE if which == "oos" else IN_SAMPLE,
         "out-of-sample" if which == "oos" else "in-sample")
