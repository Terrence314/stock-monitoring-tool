"""Cross-sectional factors: does ranking names against EACH OTHER carry edge?

Every signal tested so far is time-series -- "is this stock above its own
moving average". That whole family measured zero out-of-sample against a null
control (outputs/oos-verdict_2026-08-20.md). The documented equity anomalies
are mostly cross-sectional instead: not "is this stock trending" but "is this
stock stronger than the others right now". That is a genuinely different
hypothesis and it has never been tested here.

PRE-REGISTERED. The primary hypothesis is MOM_12_1 -- twelve-month return
skipping the most recent month, the most robust specification in the
literature. Everything else in FACTORS is exploratory and labelled as such.
Testing seven and reporting the winner is how the +0.51% trend-regime cell
happened; it did not survive out of sample and neither will a factor picked
that way.

HORIZON. Cross-sectional momentum is a 1-12 month phenomenon, so the hold is
quarterly (63 trading days) and monthly (21), not the engine's 10 days.
Testing a slow factor against a 10-day forward return asks a different
question and a null result would mean nothing. It is also what makes the
strategy affordable: at this book's $937 tickets a round trip costs 0.175%,
so swapping 2 of 5 names costs 0.28%/yr quarterly against 1.75%/yr at 10 days.

THREE LIMITS, none of which the harness can fix:

  1. The universe is the 108 tickers in pattern_events.json, selected in
     2026 and applied backwards. That is survivorship bias by construction --
     structurally the same defect as the 30 hand-picked winners in the
     original strategy backtest. The NULL control shares the universe, so the
     RELATIVE number (factor minus control) stays meaningful. The absolute
     alphas do not. Do not quote them.
  2. 108 survivors cannot support decile sorts -- a top decile is ~11 names
     and mostly noise. Selection is a fixed top-N matching the live book.
  3. Cross-sectional factors earn their premium from dispersion across a broad
     universe INCLUDING the losers. A large-cap survivor list is the thinnest,
     most crowded version of the trade.

Run:
    python3 src/factor_research.py            # all three windows
"""
from __future__ import annotations

import json
import os
import statistics as st
import sys
import warnings
from datetime import date

import pandas as pd
import yfinance as yf

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from trading_costs import round_trip_pct                            # noqa: E402

warnings.filterwarnings("ignore")

TOP_N      = 5                       # matches MAX_OPEN_POSITIONS
BENCHMARK  = "SPY"
TICKET_USD = 937.0                   # live book / 5 slots
HOLDS      = {"quarterly": 63, "monthly": 21}
OUT_FILE   = os.path.join("outputs", "factor_research.json")

PRIMARY = "mom_12_1"

# 2022-2024 was already used once, for the trend/regime test. A second pass
# over it is weaker evidence than the first, so a third window that nothing
# has touched is included -- and it carries the COVID crash, which is the
# harder test for a momentum factor.
# A quarterly hold needs YEARS, not months. The first attempt used the same
# 2-year windows as the trend study and produced 4 rebalances per window --
# on which mom_6_1 printed +31% alpha at t=+5.05. Four observations. That is
# the same shape as the +0.51% regime cell that died out of sample, and it is
# worth naming: a t-statistic is a function of n, and n here is the number of
# REBALANCES, not of trades or of days.
#
# Longer windows buy observations at the cost of worse survivorship bias --
# a 2026-selected universe applied to 2016 is more distorted than one applied
# to 2024. That trade is why the NULL control matters more here than anywhere
# else: it shares the universe, so "vs NULL" stays interpretable while the
# absolute alpha becomes meaningless. Read the vs-NULL column, ignore the rest.
WINDOWS = {
    "in-sample":   ("2014-01-01", "2020-01-01"),   # ~16 quarterly rebalances
    "oos-fresh":   ("2020-01-01", "2026-08-20"),   # ~22, incl. COVID + 2022 bear
}


# ── Factors. Each returns a Series ranked so that HIGHER = more attractive ────

def _ret(c: pd.Series, lo: int, hi: int = 0) -> pd.Series:
    """Return from `lo` bars ago to `hi` bars ago (hi=0 means today)."""
    past = c.shift(lo)
    recent = c.shift(hi) if hi else c
    return (recent - past) / past


FACTORS = {
    # PRIMARY -- pre-registered before any result was seen
    "mom_12_1":       lambda c, v: _ret(c, 252, 21),
    # exploratory
    "mom_6_1":        lambda c, v: _ret(c, 126, 21),
    "reversal_1m":    lambda c, v: -_ret(c, 21),
    "rel_strength_60": lambda c, v: _ret(c, 60),
    "low_vol_60":     lambda c, v: -c.pct_change().rolling(60).std(),
    "pct_52w_high":   lambda c, v: c / c.rolling(252).max(),
    "vol_surge":      lambda c, v: v / v.rolling(60).mean(),
}


def _load(tickers: list, start: str, end: str):
    raw = yf.download(tickers + [BENCHMARK], start=start, end=end,
                      progress=False, auto_adjust=True, group_by="ticker")
    closes, vols = {}, {}
    for t in tickers + [BENCHMARK]:
        try:
            df = raw[t].dropna(how="all")
        except Exception:
            continue
        if len(df) < 300:
            continue
        closes[t] = df["Close"]
        vols[t] = df["Volume"]
    return pd.DataFrame(closes), pd.DataFrame(vols)


def _evaluate(closes: pd.DataFrame, vols: pd.DataFrame, hold: int) -> dict:
    """Forward net return of a top-N basket vs SPY, for each factor.

    Rebalances every `hold` bars -- non-overlapping by construction, so each
    period is one independent observation and effective n is the number of
    rebalances. Overlapping windows are what made two earlier findings look
    significant when they were not.
    """
    bench = closes[BENCHMARK]
    names = [c for c in closes.columns if c != BENCHMARK]
    cost = round_trip_pct(100.0, 100.0, TICKET_USD)

    scores = {f: fn(closes[names], vols[names]) for f, fn in FACTORS.items()}
    rebal = list(range(252, len(closes) - hold, hold))
    out: dict = {}

    for fname, sc in scores.items():
        per_period, bench_per = [], []
        for i in rebal:
            row = sc.iloc[i].dropna()
            if len(row) < TOP_N * 2:
                continue
            picks = row.nlargest(TOP_N).index
            fwd = [(closes[p].iloc[i + hold] - closes[p].iloc[i]) / closes[p].iloc[i] * 100
                   for p in picks
                   if pd.notna(closes[p].iloc[i]) and pd.notna(closes[p].iloc[i + hold])
                   and closes[p].iloc[i] > 0]
            fwd = [float(x) for x in fwd if pd.notna(x) and abs(x) < 1e6]
            if len(fwd) < 2:
                continue
            b = float((bench.iloc[i + hold] - bench.iloc[i]) / bench.iloc[i] * 100)
            per_period.append(st.mean(fwd) - cost)      # every rebalance turns the book
            bench_per.append(b)
        if len(per_period) < 3:
            out[fname] = {"periods": len(per_period)}
            continue
        alpha = [float(a - b) for a, b in zip(per_period, bench_per)]
        alpha = [a for a in alpha if a == a and abs(a) < 1e6]
        if len(alpha) < 3:
            out[fname] = {"periods": len(alpha)}
            continue
        m, sd = st.mean(alpha), (st.stdev(alpha) if len(alpha) > 1 else 0.0)
        out[fname] = {
            "periods": len(alpha),
            "net_pct": round(st.mean(per_period), 2),
            "bench_pct": round(st.mean(bench_per), 2),
            "alpha_pct": round(m, 2),
            "beat_pct": round(sum(1 for a in alpha if a > 0) / len(alpha) * 100, 1),
            "t": round(m / (sd / len(alpha) ** 0.5), 2) if sd else 0.0,
        }

    # NULL control: hold the whole universe equally. Same names, same dates,
    # no ranking. A factor is only worth running if it beats THIS.
    per_period, bench_per = [], []
    for i in rebal:
        fwd = [(closes[p].iloc[i + hold] - closes[p].iloc[i]) / closes[p].iloc[i] * 100
               for p in names if pd.notna(closes[p].iloc[i]) and pd.notna(closes[p].iloc[i + hold])]
        if not fwd:
            continue
        per_period.append(st.mean(fwd) - cost)
        bench_per.append(float((bench.iloc[i + hold] - bench.iloc[i]) / bench.iloc[i] * 100))
    if per_period:
        alpha = [float(a - b) for a, b in zip(per_period, bench_per)]
        alpha = [a for a in alpha if a == a]
        out["NULL_whole_universe"] = {
            "periods": len(alpha),
            "net_pct": round(st.mean(per_period), 2),
            "bench_pct": round(st.mean(bench_per), 2),
            "alpha_pct": round(st.mean(alpha), 2),
            "beat_pct": round(sum(1 for a in alpha if a > 0) / len(alpha) * 100, 1),
            "t": 0.0,
        }
    return out


def main() -> dict:
    events = json.load(open(os.path.join("outputs", "pattern_events.json")))
    tickers = sorted({e["ticker"] for e in events if e.get("ticker")})
    report = {"generated": str(date.today()), "primary": PRIMARY,
              "top_n": TOP_N, "ticket_usd": TICKET_USD, "windows": {}}

    for wname, (start, end) in WINDOWS.items():
        print(f"\n{'='*74}\n{wname}  ({start} -> {end})\n{'='*74}")
        closes, vols = _load(tickers, start, end)
        print(f"  {closes.shape[1]-1} usable tickers, {len(closes)} bars")
        report["windows"][wname] = {}
        for hname, hold in HOLDS.items():
            res = _evaluate(closes, vols, hold)
            report["windows"][wname][hname] = res
            null = res.get("NULL_whole_universe", {})
            na = null.get("alpha_pct", 0.0)
            print(f"\n  --- {hname} hold ({hold} bars) ---")
            print(f"  {'factor':20} {'periods':>7} {'alpha%':>8} {'vs NULL':>8} {'beat':>6} {'t':>6}")
            for f in ["NULL_whole_universe"] + list(FACTORS):
                r = res.get(f, {})
                if "alpha_pct" not in r:
                    continue
                tag = " *PRIMARY" if f == PRIMARY else ""
                print(f"  {f:20} {r['periods']:7} {r['alpha_pct']:+8.2f} "
                      f"{r['alpha_pct']-na:+8.2f} {r['beat_pct']:5.1f}% {r['t']:+6.2f}{tag}")

    os.makedirs("outputs", exist_ok=True)
    json.dump(report, open(OUT_FILE, "w"), indent=2)
    print(f"\nsaved -> {OUT_FILE}")
    return report


if __name__ == "__main__":
    main()
