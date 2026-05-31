"""
tier2_manager.py — Tier 2 promotion, history tracking, and favourites merge.

Rules:
  - Tier 2 = top TIER2_SIZE scorers from broad scan
  - Core tickers (SPY, QQQ, IWM, DIA) always included regardless of score
  - Starred Favourites always included regardless of score
  - Retention rule: a ticker that was on yesterday's list stays if score >= RETENTION_FLOOR
    (prevents one-day churn when scores oscillate near the cutoff)
  - History tracks first_seen, last_seen, consecutive_days, total_appearances

Badge states (returned in each ticker's history entry):
  - "NEW"    — first time ever on Tier 2
  - "STREAK" — on list N consecutive days (N >= 2)
  - "RETURN" — was on list before, gap >= 2 days, now back
  - None     — normal (day 1 re-entry or other)
"""

import json
import os
from datetime import datetime, timedelta

UNIVERSE_FILE      = os.path.join("data", "universe_tickers.json")
FAVOURITES_FILE    = os.path.join("data", "favourites.json")
HISTORY_FILE       = os.path.join("data", "tier2_history.json")
BROAD_SCAN_FILE    = os.path.join("outputs", "broad_scan_latest.json")

TIER2_SIZE         = 50     # how many top scorers to promote
RETENTION_FLOOR    = 55     # score floor to stay on list via retention rule
RETENTION_DAYS     = 2      # how many days retention rule applies after drop


def _load_json(path: str, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return default


def _save_json(path: str, data) -> None:
    os.makedirs(os.path.dirname(path) if os.path.dirname(path) else ".", exist_ok=True)
    with open(path, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)


def load_favourites() -> list[str]:
    """Return list of starred ticker symbols (uppercase)."""
    raw = _load_json(FAVOURITES_FILE, [])
    if isinstance(raw, list):
        return [t.upper() for t in raw]
    return []


def save_favourites(tickers: list[str]) -> None:
    """Persist starred ticker list."""
    unique = list(dict.fromkeys(t.upper() for t in tickers))
    os.makedirs("data", exist_ok=True)
    _save_json(FAVOURITES_FILE, unique)


def add_favourite(ticker: str) -> None:
    favs = load_favourites()
    t = ticker.upper()
    if t not in favs:
        favs.append(t)
        save_favourites(favs)


def remove_favourite(ticker: str) -> None:
    favs = load_favourites()
    t = ticker.upper()
    updated = [f for f in favs if f != t]
    save_favourites(updated)


def load_history() -> dict:
    """Load Tier 2 membership history. Returns dict keyed by ticker symbol."""
    return _load_json(HISTORY_FILE, {})


def _date_str(dt: datetime) -> str:
    return dt.strftime("%Y-%m-%d")


def _prev_trading_day(today_str: str) -> str:
    """Return the calendar day before today_str (not exchange-aware, good enough)."""
    d = datetime.strptime(today_str, "%Y-%m-%d") - timedelta(days=1)
    return _date_str(d)


def _compute_badge(history_entry: dict, today_str: str) -> str | None:
    """Return the badge state for a ticker given its history entry."""
    if history_entry["first_seen"] == today_str:
        return "NEW"

    consecutive = history_entry.get("consecutive_days", 1)
    if consecutive >= 2:
        return "STREAK"

    # Was on list before (total > 1) but gap in dates
    if history_entry.get("total_appearances", 1) > 1:
        return "RETURN"

    return None


def _update_history(
    history: dict,
    today_str: str,
    promoted_tickers: list[str],
) -> dict:
    """
    Update tier2_history.json for today's promoted list.
    Returns the updated history dict.
    """
    prev_day = _prev_trading_day(today_str)

    for ticker in promoted_tickers:
        if ticker not in history:
            # First time on the list
            history[ticker] = {
                "first_seen":       today_str,
                "last_seen":        today_str,
                "consecutive_days": 1,
                "total_appearances": 1,
                "dates":            [today_str],
            }
        else:
            entry = history[ticker]
            last  = entry.get("last_seen", "")

            if last == today_str:
                # Already updated today (idempotent re-run)
                pass
            elif last == prev_day or last == today_str:
                # Consecutive day
                entry["consecutive_days"]  = entry.get("consecutive_days", 1) + 1
                entry["total_appearances"] = entry.get("total_appearances", 1) + 1
                entry["last_seen"]         = today_str
                entry["dates"]             = (entry.get("dates", []) + [today_str])[-90:]
            else:
                # Gap — reset consecutive streak
                entry["consecutive_days"]  = 1
                entry["total_appearances"] = entry.get("total_appearances", 1) + 1
                entry["last_seen"]         = today_str
                entry["dates"]             = (entry.get("dates", []) + [today_str])[-90:]

    # For tickers NOT promoted today, reset consecutive_days if they were on yesterday
    # (no action needed — we only update entries for tickers IN the list)

    return history


def get_tier2_list(today_str: str) -> tuple[list[dict], list[dict], dict]:
    """
    Build the Tier 2 analysis list and return:
      (tier2_items, broad_scan_top100, enriched_history)

    tier2_items: list of dicts with keys:
        ticker, name, sector, score, strength, is_favourite, badge, consecutive_days

    broad_scan_top100: top 100 from the broad scan (for the Universe Leaderboard)

    enriched_history: updated history dict (caller saves to disk)
    """
    # Load broad scan results
    scan_data  = _load_json(BROAD_SCAN_FILE, {})
    scan_results: list[dict] = scan_data.get("results", [])

    # Load universe metadata for names/sectors on tickers not in scan
    universe_data  = _load_json(UNIVERSE_FILE, {})
    universe_meta  = {
        item["ticker"].upper(): item
        for item in universe_data.get("universe", [])
    }

    # Load favourites and core tickers
    favourites  = set(load_favourites())
    core_raw    = universe_data.get("core", ["SPY", "QQQ", "IWM", "DIA"])
    core        = set(t.upper() for t in core_raw)

    # Load existing history
    history = load_history()

    # Build score map from broad scan
    score_map: dict[str, dict] = {r["ticker"]: r for r in scan_results}

    # --- Determine yesterday's Tier 2 (for retention rule) ---
    prev_day    = _prev_trading_day(today_str)
    prev_tier2  = set()
    for ticker, entry in history.items():
        if entry.get("last_seen") == prev_day:
            prev_tier2.add(ticker)

    # --- Select Tier 2 set ---
    top50_tickers = {r["ticker"] for r in scan_results[:TIER2_SIZE]}

    # Retention: yesterday's tickers still scoring above floor stay in
    retained = {
        t for t in prev_tier2
        if t not in top50_tickers
        and score_map.get(t, {}).get("score", 0) >= RETENTION_FLOOR
    }

    # Final Tier 2 set: top50 + retained + core + favourites
    promoted_set = top50_tickers | retained | core | favourites

    # Build enriched result list
    def _make_item(ticker: str) -> dict | None:
        meta = score_map.get(ticker) or universe_meta.get(ticker, {})
        return {
            "ticker":           ticker,
            "name":             meta.get("name", ticker),
            "sector":           meta.get("sector", "Unknown"),
            "score":            meta.get("score", 0),
            "strength":         meta.get("strength", meta.get("strength_en", "")),
            "rsi":              meta.get("rsi"),
            "ma5":              meta.get("ma5"),
            "ma20":             meta.get("ma20"),
            "ma60":             meta.get("ma60"),
            "bb_pct":           meta.get("bb_pct"),
            "bb_squeeze":       meta.get("bb_squeeze", False),
            "signals":          meta.get("signals", []),
            "is_favourite":     ticker in favourites,
            "is_core":          ticker in core,
            "is_retained":      ticker in retained and ticker not in top50_tickers,
            "category":         meta.get("category", ""),
            "expense_ratio":    meta.get("expense_ratio"),
        }

    tier2_items_raw = [_make_item(t) for t in promoted_set]
    tier2_items_raw = [i for i in tier2_items_raw if i is not None]
    tier2_items_raw.sort(key=lambda x: (-(x["score"] or 0), x["ticker"]))

    # Update history for today's list
    promoted_list = [item["ticker"] for item in tier2_items_raw]
    history = _update_history(history, today_str, promoted_list)

    # Attach badges and consecutive_days
    for item in tier2_items_raw:
        entry  = history.get(item["ticker"], {})
        item["badge"]            = _compute_badge(entry, today_str)
        item["consecutive_days"] = entry.get("consecutive_days", 1)

    # Save updated history to data/ (source of truth)
    _save_json(HISTORY_FILE, history)

    # Mirror data/ files to outputs/ so GitHub Pages picks them up for next-run restore.
    # The daily pipeline deploys outputs/ to Pages; tier2_history + favourites must
    # survive across runs or streak counts reset and stars vanish.
    import shutil
    os.makedirs("outputs", exist_ok=True)
    for src_path in [HISTORY_FILE, FAVOURITES_FILE]:
        if os.path.exists(src_path):
            shutil.copy2(src_path, os.path.join("outputs", os.path.basename(src_path)))

    # Build top 100 leaderboard (all broad scan results, capped at 100)
    broad_top100 = []
    for r in scan_results[:100]:
        entry = history.get(r["ticker"], {})
        broad_top100.append({
            **r,
            "is_favourite":     r["ticker"] in favourites,
            "badge":            _compute_badge(entry, today_str) if r["ticker"] in {i["ticker"] for i in tier2_items_raw} else None,
            "consecutive_days": entry.get("consecutive_days", 0),
        })

    print(f"  [tier2_manager] Tier 2: {len(tier2_items_raw)} tickers "
          f"(top50={len(top50_tickers & promoted_set)} "
          f"retained={len(retained)} "
          f"core={len(core & promoted_set)} "
          f"favs={len(favourites & promoted_set)})")

    return tier2_items_raw, broad_top100, history


if __name__ == "__main__":
    today = datetime.now().strftime("%Y-%m-%d")
    items, top100, _ = get_tier2_list(today)
    print(f"\nTier 2 ({len(items)} tickers):")
    for it in items[:20]:
        badge_str = f"[{it['badge']}]" if it["badge"] else ""
        fav_str   = "⭐" if it["is_favourite"] else "  "
        print(f"  {fav_str} {it['ticker']:<8} {it['score']:>3}/100  {badge_str:<10} {it['sector']}")
    print(f"\nUniverse Leaderboard top 10:")
    for r in top100[:10]:
        print(f"  {r['ticker']:<8} {r['score']:>3}/100  {r['sector']}")
