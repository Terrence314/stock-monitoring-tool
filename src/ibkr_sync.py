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
            "avg_cost":       round(p.get("avgCost", 0), 4),
            "market_price":   round(p.get("mktPrice", 0), 4),
            "market_value":   round(p.get("mktValue", 0), 2),
            "unrealized_pnl": round(p.get("unrealizedPnl", 0), 2),
            "daily_pnl":      round(p.get("dailyPnL", 0), 2),
            "currency":       p.get("currency", "USD"),
        })

    return {
        "synced_at": datetime.now().strftime("%Y-%m-%d %H:%M"),
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
            pnl_str = f"+${p['unrealized_pnl']:.2f}" if p["unrealized_pnl"] >= 0 else f"-${abs(p['unrealized_pnl']):.2f}"
            print(f"   {p['ticker']:6s} ×{p['qty']} @ ${p['avg_cost']:.2f}  now ${p['market_price']:.2f}  {pnl_str}")
    except urllib.error.URLError as e:
        print(f"❌ Gateway unreachable: {e}")
        print("   Is IB Gateway running? (paper port 4002, Client Portal port 5000)")
        sys.exit(1)
    except Exception as e:
        print(f"❌ Error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
