"""
broad_scan.py — TA-only universe scanner.

Downloads OHLCV for all tickers in data/universe_tickers.json,
computes the 5-factor score (no Gemini), and writes a ranked list
to outputs/broad_scan_latest.json.

Designed to run as the FIRST step in the daily pipeline, before
main.py launches full Gemini analysis on the Tier 2 shortlist.
"""

import json
import os
import sys
import time
from datetime import datetime

import yfinance as yf
import pandas as pd

# Add src/ to path when run directly
sys.path.insert(0, os.path.dirname(__file__))
from technical_analysis import calculate_indicators

UNIVERSE_FILE  = os.path.join("data", "universe_tickers.json")
OUTPUT_FILE    = os.path.join("outputs", "broad_scan_latest.json")
BATCH_SIZE     = 50   # tickers per yf.download batch
SCAN_PERIOD    = "3mo"
MIN_BARS       = 20   # skip tickers with fewer bars


def _load_universe() -> list[dict]:
    """Load universe ticker list from data/universe_tickers.json."""
    try:
        with open(UNIVERSE_FILE, encoding="utf-8") as f:
            data = json.load(f)
        tickers = data.get("universe", [])
        # Deduplicate by ticker symbol (preserve first occurrence)
        seen = set()
        unique = []
        for item in tickers:
            t = item["ticker"].upper()
            if t not in seen:
                seen.add(t)
                unique.append({**item, "ticker": t})
        return unique
    except FileNotFoundError:
        print(f"  [broad_scan] ⚠️  Universe file not found: {UNIVERSE_FILE}")
        return []
    except Exception as e:
        print(f"  [broad_scan] ⚠️  Failed to load universe: {e}")
        return []


def _score_batch(batch: list[dict]) -> list[dict]:
    """Download + score one batch of tickers. Returns list of result dicts."""
    if not batch:
        return []

    ticker_syms  = [item["ticker"] for item in batch]
    ticker_str   = " ".join(ticker_syms)
    results      = []

    try:
        raw = yf.download(
            ticker_str,
            period=SCAN_PERIOD,
            auto_adjust=True,
            progress=False,
            group_by="ticker",
        )
    except Exception as e:
        print(f"    [batch download] error: {e} — falling back to individual")
        raw = None

    for item in batch:
        ticker = item["ticker"]
        try:
            if raw is None:
                # Individual fallback
                stock = yf.Ticker(ticker)
                df = stock.history(period=SCAN_PERIOD, auto_adjust=True)
            elif len(batch) == 1:
                # Single ticker: yfinance returns flat columns (no MultiIndex)
                df = raw
            else:
                # Multi-ticker batch: yfinance 1.x returns MultiIndex (ticker, field)
                # Level 0 = ticker symbol, Level 1 = OHLCV field names
                if isinstance(raw.columns, pd.MultiIndex):
                    tickers_in_batch = raw.columns.get_level_values(0).unique().tolist()
                    if ticker not in tickers_in_batch:
                        continue
                    df = raw[ticker]   # returns DataFrame with Open/High/Low/Close/Volume
                else:
                    # Flat columns — single ticker was returned despite multi request
                    df = raw

            if df is None or df.empty:
                continue

            df = df.dropna(subset=["Close"])
            if len(df) < MIN_BARS:
                continue

            ta = calculate_indicators(df)
            results.append({
                "ticker":   ticker,
                "name":     item.get("name", ticker),
                "sector":   item.get("sector", "Unknown"),
                "score":    ta["score"],
                "strength": ta.get("strength_en", ""),
                "rsi":      ta.get("rsi"),
                "ma5":      ta.get("ma5"),
                "ma20":     ta.get("ma20"),
                "ma60":     ta.get("ma60"),
                "bb_pct":   ta.get("bb_pct"),
                "bb_squeeze": ta.get("bb_squeeze", False),
                "signals":  ta.get("signals", []),
            })
        except Exception:
            # Silently skip individual ticker errors — broad scan is best-effort
            pass

    return results


def run_broad_scan(today_str: str | None = None) -> list[dict]:
    """
    Score all universe tickers and write outputs/broad_scan_latest.json.
    Returns the full ranked result list (sorted descending by score).
    """
    if today_str is None:
        today_str = datetime.now().strftime("%Y-%m-%d")

    print(f"  [broad_scan] Loading universe…")
    universe = _load_universe()
    if not universe:
        print("  [broad_scan] ⚠️  Empty universe — skipping scan.")
        return []

    total = len(universe)
    print(f"  [broad_scan] Scanning {total} tickers in batches of {BATCH_SIZE}…")

    all_results: list[dict] = []
    batches = [universe[i:i + BATCH_SIZE] for i in range(0, total, BATCH_SIZE)]

    for idx, batch in enumerate(batches, 1):
        print(f"    Batch {idx}/{len(batches)} ({len(batch)} tickers)…", end=" ", flush=True)
        t0 = time.time()
        batch_results = _score_batch(batch)
        all_results.extend(batch_results)
        elapsed = time.time() - t0
        print(f"  → {len(batch_results)} scored in {elapsed:.1f}s")

    # Sort by score descending
    all_results.sort(key=lambda x: x["score"], reverse=True)

    # Persist
    output = {
        "date":           today_str,
        "total_scanned":  len(all_results),
        "generated_at":   datetime.now().isoformat(),
        "results":        all_results,
    }
    os.makedirs("outputs", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(output, f, ensure_ascii=False, indent=2)

    scored_count = len(all_results)
    top5 = [f"{r['ticker']}({r['score']})" for r in all_results[:5]]
    print(f"  [broad_scan] ✅ {scored_count}/{total} scored. Top 5: {', '.join(top5)}")
    print(f"  [broad_scan] Saved → {OUTPUT_FILE}")

    return all_results


if __name__ == "__main__":
    results = run_broad_scan()
    print(f"\nTop 20:")
    for r in results[:20]:
        print(f"  {r['ticker']:<8} {r['score']:>3}/100  {r['strength']:<12}  {r['sector']}")
