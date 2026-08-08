"""Single source of truth for which tickers qualify as a new long entry.

The dashboard Action Box and the paper engine each used to implement their own
version of this decision, and they drifted. Measured over the validation window
2026-07-17 → 08-04: the Action Box published BUY tickets for 37 tickers, the
engine opened 9, and the two overlapped on only 6. Three causes, all fixed by
routing both callers through `select_entries()` here:

  * the Action Box applied a volume check on squeeze breakouts that the engine
    did not, and the engine applied an EMA200 trend gate and a sector cap that
    the Action Box did not;
  * the validator veto reached the engine but never the published ticket;
  * the two ran at different times (see `price_refresh.py`).

Sizing lives here too, for the same reason: a ticket that names a dollar
amount the account cannot fund is a wrong ticket, not a display detail.
"""

import json
import os
from datetime import datetime

# ── Signal thresholds ─────────────────────────────────────────────────────────
BUY_THRESHOLD       = 70     # score >= this → long candidate
REGIME_FLOOR        = 35     # SPY below this → no new longs at all
REGIME_NORMAL       = 50     # SPY below this → high-conviction entries only
HIGH_CONVICTION_MIN = 80     # minimum score in a transitional market

# ── Portfolio limits ──────────────────────────────────────────────────────────
MAX_PER_SECTOR      = 2      # open longs per sector
MAX_OPEN_POSITIONS  = 5      # open longs in total

# ── Position sizing ───────────────────────────────────────────────────────────
# Percent of account net liquidation per position, by conviction. The old model
# was a flat $1,000 base unit scaled to $1,500 / $2,000, which on a ~USD 4,650
# account meant a single ticket asked for 32–43% of everything. These are the
# risk knobs: MAX_OPEN_POSITIONS x the top band bounds total exposure (5 x 12%
# = 60%), and one -8% stop costs at most 0.96% of the account.
POSITION_PCT = ((90, 12.0), (80, 10.0), (0, 7.0))

# Used only when account equity cannot be read. Sizing does NOT fail closed —
# an unreachable broker API must not silently stop the validation record — but
# every ticket sized this way is tagged so the dashboard can say so.
FALLBACK_EQUITY_USD = 5000.0
EQUITY_MAX_AGE_DAYS = 7


def _pct_for_score(score: int) -> float:
    for floor, pct in POSITION_PCT:
        if score >= floor:
            return pct
    return POSITION_PCT[-1][1]


def account_equity_usd(output_dir: str = "outputs") -> tuple[float, str]:
    """Return (equity_usd, basis) where basis is 'ibkr' or 'fallback'.

    Reads the snapshot `ibkr_sync.py` writes. Prefers the pre-converted USD
    figure; a HKD net liquidation read as USD would undersize every ticket by
    roughly 8x, so an unconverted non-USD account counts as unreadable.
    """
    path = os.path.join(output_dir, "ibkr_positions.json")
    try:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    except (OSError, ValueError):
        return FALLBACK_EQUITY_USD, "fallback"

    account = data.get("account") or {}
    equity = account.get("net_liquidation_usd")
    if equity is None and (account.get("currency") or "USD").upper() == "USD":
        equity = account.get("net_liquidation")
    if not equity or equity <= 0:
        return FALLBACK_EQUITY_USD, "fallback"

    synced_at = data.get("synced_at") or ""
    try:
        age_days = (datetime.now() - datetime.strptime(synced_at[:10], "%Y-%m-%d")).days
    except ValueError:
        return FALLBACK_EQUITY_USD, "fallback"
    if age_days > EQUITY_MAX_AGE_DAYS:
        return FALLBACK_EQUITY_USD, "fallback"

    return float(equity), "ibkr"


def position_notional(score: int, equity_usd: float) -> float:
    """Conviction-weighted position size in USD."""
    return round(equity_usd * _pct_for_score(score) / 100, 2)


def market_regime(stocks: list) -> tuple[str, int | None, int | None]:
    """Return (regime, spy_score, min_score). min_score None = no new longs.

    Fails CLOSED when SPY is missing: a risk gate whose failure mode is
    "trade as usual" is the wrong default.
    """
    spy = next((s for s in stocks if s.get("ticker") == "SPY"), None)
    spy_score = spy.get("score") if spy else None
    if spy_score is None:
        return "unknown", None, None
    if spy_score < REGIME_FLOOR:
        return "bear", spy_score, None
    if spy_score < REGIME_NORMAL:
        return "transitional", spy_score, HIGH_CONVICTION_MIN
    return "bull", spy_score, BUY_THRESHOLD


def entry_timing_ok(stock: dict) -> bool:
    """Verdict, trend and volume gates — the 'high score is not enough' rules."""
    label = (stock.get("entry_verdict") or {}).get("label", "")
    if not ("GO" in label or "BREAKOUT ↑" in label or "BREAKOUT 🚀" in label):
        return False
    # A squeeze breakout without volume expansion is a false-breakout setup.
    if "BREAKOUT" in label and (stock.get("vol_ratio") or 0) < 1.0:
        return False
    # Weekly trend proxy: price below EMA200 is a long-term downtrend.
    price, ema200 = stock.get("price") or 0, stock.get("ema200") or 0
    if ema200 and price and price < ema200:
        return False
    return True


def sector_cap_ok(ticker: str, sector_map: dict, open_trades: list,
                  pending: list | None = None) -> bool:
    """False once MAX_PER_SECTOR longs are already open in the ticker's sector.

    `pending` holds entries selected in this same pass but not yet persisted,
    so one run cannot open three positions in one sector.
    """
    sector = sector_map.get(ticker, "Unknown")
    if sector == "Unknown":
        return True
    count = sum(1 for t in open_trades if (t.get("sector") or "Unknown") == sector)
    count += sum(1 for p in (pending or []) if p.get("sector") == sector)
    return count < MAX_PER_SECTOR


def select_entries(stocks_sorted: list, open_trades: list,
                   blocked_tickers: set | None = None,
                   output_dir: str = "outputs") -> tuple[list, dict]:
    """Pick the new long entries. Returns (entries, context).

    `entries` carry everything both callers need: ticker, score, price,
    notional, reason. `context` reports the regime and sizing basis so the
    dashboard can explain a suppressed or oddly-sized ticket.
    """
    blocked_tickers = set(blocked_tickers or ())
    regime, spy_score, min_score = market_regime(stocks_sorted)
    equity_usd, sizing_basis = account_equity_usd(output_dir)

    open_longs = [t for t in open_trades
                  if t.get("status") == "open" and t.get("direction", "long") == "long"]
    held = {t["ticker"] for t in open_longs}
    sector_map = {s["ticker"]: (s.get("sector") or "Unknown") for s in stocks_sorted}
    slots_left = MAX_OPEN_POSITIONS - len(open_longs)

    context = {
        "regime": regime, "regime_spy": spy_score, "regime_min": min_score,
        "equity_usd": equity_usd, "sizing_basis": sizing_basis,
        "slots_left": max(0, slots_left), "max_open": MAX_OPEN_POSITIONS,
    }

    entries: list = []
    if min_score is None or slots_left <= 0:
        return entries, context

    for s in stocks_sorted:
        if len(entries) >= slots_left:
            break
        ticker = s["ticker"]
        if ticker == "SPY" or ticker in held or ticker in blocked_tickers:
            continue
        price = s.get("price") or 0
        if price <= 0 or (s.get("score") or 0) < min_score:
            continue
        if not entry_timing_ok(s):
            continue
        if not sector_cap_ok(ticker, sector_map, open_longs, entries):
            continue
        score = s["score"]
        entries.append({
            "ticker":   ticker,
            "score":    score,
            "price":    price,
            "notional": position_notional(score, equity_usd),
            "sector":   sector_map.get(ticker, "Unknown"),
            "reason":   (s.get("entry_verdict") or {}).get("reason", ""),
        })

    return entries, context
