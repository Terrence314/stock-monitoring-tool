"""ibkr_sync.py — Sync IBKR positions to outputs/ibkr_positions.json.

Uses IBKR Client Portal API (localhost:5000) — requires IB Gateway or
Client Portal Gateway running and authenticated.

Usage:
    python3 src/ibkr_sync.py

Run this locally before generating the dashboard to get position-aware
badges and alerts. The daily GitHub Actions pipeline reads the file if
present; gracefully skips if absent.

ALERTS ONLY — this module never places orders.
"""
import json
import os
import sys
import urllib.request
import urllib.error
import ssl
from datetime import datetime

GATEWAY_BASE = "https://localhost:5000/v1/api"
OUTPUT_FILE  = os.path.join("outputs", "ibkr_positions.json")

# Bypass self-signed cert on localhost gateway
_ctx = ssl.create_default_context()
_ctx.check_hostname = False
_ctx.verify_mode = ssl.CERT_NONE


def _get(path: str) -> dict | list:
    url = f"{GATEWAY_BASE}{path}"
    req = urllib.request.Request(url, headers={"User-Agent": "ibkr-sync/1.0"})
    with urllib.request.urlopen(req, context=_ctx, timeout=10) as resp:
        return json.loads(resp.read())


# IBKR returns ±DBL_MAX when a field is unavailable rather than omitting it.
# Stored as-is, dailyPnL = -1.7976931348623157e+308 was compared against the
# -$20 daily-loss threshold and fired a catastrophic-looking false alert.
_IBKR_UNAVAILABLE = 1e12


def _num(value, digits: int = 2) -> float | None:
    """Round an IBKR numeric field, mapping its unavailable sentinel to None."""
    try:
        v = float(value)
    except (TypeError, ValueError):
        return None
    if abs(v) > _IBKR_UNAVAILABLE:
        return None
    return round(v, digits)


REPORTING_CCY = "USD"


def _fx_rates(currencies: set[str]) -> dict[str, float]:
    """Rate to multiply an amount in each currency by to get USD.

    The account is genuinely mixed — net liquidation denominated in HKD,
    US positions in USD, SPYL.L on the LSE — and nothing converted, so every
    cross-position total (exposure, sector concentration, drawdown %) was
    summing different units. Falls back to 1.0 and flags the currency rather
    than inventing a rate.
    """
    rates = {REPORTING_CCY: 1.0}
    todo = {c for c in currencies if c and c != REPORTING_CCY}
    if not todo:
        return rates
    try:
        import yfinance as yf
    except ImportError:
        return rates
    for ccy in todo:
        try:
            raw = yf.download(f"{ccy}{REPORTING_CCY}=X", period="5d",
                              progress=False, auto_adjust=True)
            # yfinance returns column-MultiIndexed frames, so raw["Close"] is a
            # single-column DataFrame and .iloc[-1] is a Series, not a float.
            # float() on it raised every time, the except below swallowed it as
            # "FX unavailable", and every _usd field published as null — which
            # in turn made entry_selection fall back to the default equity even
            # on a freshly synced account.
            close = raw["Close"].squeeze("columns").dropna()
            if not close.empty:
                rates[ccy] = float(close.iloc[-1])
        except Exception as e:
            print(f"   ⚠️ FX {ccy}->{REPORTING_CCY} unavailable ({e}); left unconverted")
    return rates


def fetch_positions() -> dict:
    # Get account ID
    accounts = _get("/portfolio/accounts")
    if not accounts:
        raise RuntimeError("No accounts returned")
    account_id = accounts[0]["id"]

    # Account summary
    summary_raw = _get(f"/portfolio/{account_id}/summary")
    summary = {
        "net_liquidation": summary_raw.get("netliquidation", {}).get("amount"),
        "buying_power":    summary_raw.get("buyingpower", {}).get("amount"),
        "currency":        summary_raw.get("netliquidation", {}).get("currency", "USD"),
    }

    # Positions
    pos_raw = _get(f"/portfolio/{account_id}/positions/0")
    positions = []
    for p in pos_raw or []:
        # Preserve exchange suffix for LSE/international tickers (e.g. SPYL.L)
        desc = p.get("ticker", p.get("contractDesc", ""))
        base = desc.split()[0]
        # Re-append .L for LSE tickers (contractDesc contains @LSEETF)
        if "@LSEETF" in desc or "@LSE" in desc:
            base = base + ".L"
        ticker = base
        positions.append({
            "ticker":         ticker,
            "qty":            p.get("position", 0),
            "avg_cost":       _num(p.get("avgCost"), 4),
            "market_price":   _num(p.get("mktPrice"), 4),
            "market_value":   _num(p.get("mktValue")),
            "unrealized_pnl": _num(p.get("unrealizedPnl")),
            "daily_pnl":      _num(p.get("dailyPnL")),
            "currency":       p.get("currency", "USD"),
        })

    # Normalise every money figure to one reporting currency and record the
    # rates used, so downstream totals are comparable and auditable.
    rates = _fx_rates({p.get("currency") for p in positions} | {summary.get("currency")})
    for p in positions:
        r = rates.get(p.get("currency"))
        p["fx_rate"] = r
        p["fx_converted"] = r is not None
        for f in ("market_value", "unrealized_pnl", "daily_pnl"):
            v = p.get(f)
            p[f + "_usd"] = round(v * r, 2) if (v is not None and r) else None
    _sr = rates.get(summary.get("currency"))
    summary["reporting_currency"] = REPORTING_CCY
    summary["fx_rate"] = _sr
    for f in ("net_liquidation", "buying_power"):
        try:
            v = float(summary.get(f))
        except (TypeError, ValueError):
            v = None
        summary[f + "_usd"] = round(v * _sr, 2) if (v is not None and _sr) else None

    return {
        "synced_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
        "fx_rates":  rates,
        "account":   summary,
        "positions": positions,
    }


def main() -> None:
    os.makedirs("outputs", exist_ok=True)
    print("Connecting to IBKR Client Portal Gateway…")
    try:
        data = fetch_positions()
        with open(OUTPUT_FILE, "w") as f:
            json.dump(data, f, indent=2)
        print(f"✅ {len(data['positions'])} positions saved → {OUTPUT_FILE}")
        for p in data["positions"]:
            _u = p["unrealized_pnl"]
            pnl_str = "—" if _u is None else (f"+${_u:.2f}" if _u >= 0 else f"-${abs(_u):.2f}")
            print(f"   {p['ticker']:6s} ×{p['qty']} @ ${p['avg_cost'] or 0:.2f}  "
                  f"now ${p['market_price'] or 0:.2f}  {pnl_str}")
    except urllib.error.URLError as e:
        print(f"❌ Gateway unreachable: {e}")
        print("   Is IB Gateway running? (paper port 4002, Client Portal port 5000)")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
