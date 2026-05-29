"""portfolio.py — Personal investment portfolio tracker.

Reads data/portfolio_transactions.json, fetches live prices + USDHKD FX rate,
computes holdings / P&L / cash balance, and renders outputs/portfolio.html.

Transaction types
-----------------
  deposit   — add cash (USD or HKD)
  withdraw  — remove cash
  buy       — purchase shares (price in USD or HKD)
  sell      — sell shares

All internal calculations are in USD. HKD amounts are converted using the
live USDHKD rate fetched from yfinance (USDHKD=X).
"""

import os
import json
from datetime import datetime
from collections import defaultdict

import yfinance as yf
from jinja2 import Template

TRANSACTIONS_FILE = os.path.join("data", "portfolio_transactions.json")
FX_TICKER         = "USDHKD=X"   # 1 USD = ? HKD


# ── Data loading ──────────────────────────────────────────────────────────────

def load_transactions() -> list:
    try:
        with open(TRANSACTIONS_FILE, encoding="utf-8") as f:
            data = json.load(f)
        txns = data.get("transactions", [])
        return sorted(txns, key=lambda t: t["date"])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def save_transactions(txns: list) -> None:
    os.makedirs(os.path.dirname(TRANSACTIONS_FILE), exist_ok=True)
    with open(TRANSACTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump({"transactions": txns}, f, ensure_ascii=False, indent=2)


# ── FX rate ───────────────────────────────────────────────────────────────────

def fetch_usdhkd() -> float:
    """Fetch live USD/HKD rate. Falls back to 7.80 peg if unavailable."""
    try:
        raw = yf.download(FX_TICKER, period="2d", progress=False, auto_adjust=True)
        if not raw.empty:
            return float(raw["Close"].dropna().iloc[-1])
    except Exception:
        pass
    return 7.80


def hkd_to_usd(amount_hkd: float, rate: float) -> float:
    """Convert HKD amount to USD."""
    return round(amount_hkd / rate, 4) if rate else round(amount_hkd / 7.80, 4)


# ── Price fetching ────────────────────────────────────────────────────────────

def fetch_current_prices(tickers: list[str]) -> dict[str, float]:
    """Bulk-fetch latest close prices. Returns {ticker: price}."""
    if not tickers:
        return {}
    try:
        raw = yf.download(tickers, period="2d", progress=False, auto_adjust=True)
        prices: dict[str, float] = {}
        if len(tickers) == 1:
            t = tickers[0]
            if "Close" in raw.columns:
                val = raw["Close"].dropna().iloc[-1]
                prices[t] = float(val)
        else:
            close = raw.get("Close", raw)
            for t in tickers:
                if t in close.columns:
                    val = close[t].dropna()
                    if not val.empty:
                        prices[t] = float(val.iloc[-1])
        return prices
    except Exception:
        return {}


def fetch_prev_close(tickers: list[str]) -> dict[str, float]:
    """Fetch previous close for day-change calculation."""
    if not tickers:
        return {}
    try:
        raw = yf.download(tickers, period="5d", progress=False, auto_adjust=True)
        prev: dict[str, float] = {}
        if len(tickers) == 1:
            t = tickers[0]
            if "Close" in raw.columns:
                series = raw["Close"].dropna()
                if len(series) >= 2:
                    prev[t] = float(series.iloc[-2])
        else:
            close = raw.get("Close", raw)
            for t in tickers:
                if t in close.columns:
                    series = close[t].dropna()
                    if len(series) >= 2:
                        prev[t] = float(series.iloc[-2])
        return prev
    except Exception:
        return {}


# ── Portfolio calculation ─────────────────────────────────────────────────────

def compute_portfolio(txns: list, usdhkd: float) -> dict:
    """Compute current holdings, P&L, and cash balances from transaction history.

    Uses FIFO cost basis for realized P&L calculations.
    All monetary values returned in USD (with HKD equivalents where shown).
    """
    # Cash tracking in USD
    cash_usd = 0.0

    # FIFO lots per ticker: deque of [shares, cost_per_share_usd]
    lots: dict[str, list] = defaultdict(list)

    # Realized P&L per ticker
    realized: dict[str, float] = defaultdict(float)

    # Transaction log with running balance
    enriched_txns: list = []

    for txn in txns:
        t_type    = txn.get("type", "").lower()
        ticker    = txn.get("ticker", "")
        shares    = float(txn.get("shares", 0) or 0)
        price     = float(txn.get("price", 0) or 0)
        currency  = txn.get("currency", "USD").upper()
        notes     = txn.get("notes", "")
        date      = txn.get("date", "")

        # Convert price to USD
        price_usd = hkd_to_usd(price, usdhkd) if currency == "HKD" else price

        if t_type == "deposit":
            amount_usd = hkd_to_usd(shares or price, usdhkd) if currency == "HKD" else (shares or price)
            cash_usd  += amount_usd
            enriched_txns.append({
                **txn, "amount_usd": round(amount_usd, 2),
                "cash_after": round(cash_usd, 2),
                "label": f"Deposit +${amount_usd:,.2f}",
            })

        elif t_type == "withdraw":
            amount_usd = hkd_to_usd(shares or price, usdhkd) if currency == "HKD" else (shares or price)
            cash_usd  -= amount_usd
            enriched_txns.append({
                **txn, "amount_usd": round(-amount_usd, 2),
                "cash_after": round(cash_usd, 2),
                "label": f"Withdraw -${amount_usd:,.2f}",
            })

        elif t_type == "buy" and ticker and shares > 0 and price_usd > 0:
            cost_usd   = shares * price_usd
            cash_usd  -= cost_usd
            lots[ticker].append([shares, price_usd])
            enriched_txns.append({
                **txn, "amount_usd": round(-cost_usd, 2),
                "price_usd": round(price_usd, 4),
                "cash_after": round(cash_usd, 2),
                "label": f"Buy {shares:g} × ${price_usd:.2f}",
            })

        elif t_type == "sell" and ticker and shares > 0 and price_usd > 0:
            proceeds   = shares * price_usd
            cash_usd  += proceeds
            # FIFO cost basis
            remaining  = shares
            cost_basis = 0.0
            while remaining > 0 and lots[ticker]:
                lot_shares, lot_price = lots[ticker][0]
                use = min(remaining, lot_shares)
                cost_basis += use * lot_price
                remaining  -= use
                lots[ticker][0][0] -= use
                if lots[ticker][0][0] <= 0:
                    lots[ticker].pop(0)
            rpnl = proceeds - cost_basis
            realized[ticker] += rpnl
            enriched_txns.append({
                **txn, "amount_usd": round(proceeds, 2),
                "price_usd": round(price_usd, 4),
                "cash_after": round(cash_usd, 2),
                "realized_pnl": round(rpnl, 2),
                "label": f"Sell {shares:g} × ${price_usd:.2f}",
            })

    # Current holdings
    holdings: list = []
    held_tickers = [t for t, lot_list in lots.items() if sum(l[0] for l in lot_list) > 0]

    return {
        "cash_usd":       round(cash_usd, 2),
        "cash_hkd":       round(cash_usd * usdhkd, 2),
        "held_tickers":   held_tickers,
        "lots":           {t: list(v) for t, v in lots.items()},
        "realized":       dict(realized),
        "enriched_txns":  list(reversed(enriched_txns)),   # most recent first
    }


def enrich_with_prices(
    portfolio: dict,
    prices: dict[str, float],
    prev_closes: dict[str, float],
    usdhkd: float,
) -> dict:
    """Add market values, unrealized P&L, and day change to held positions."""
    holdings = []
    total_market_value = 0.0
    total_cost_basis   = 0.0

    for ticker in portfolio["held_tickers"]:
        lots       = portfolio["lots"].get(ticker, [])
        shares     = sum(l[0] for l in lots)
        if shares <= 0:
            continue
        avg_cost   = sum(l[0] * l[1] for l in lots) / shares if shares else 0
        cur_price  = prices.get(ticker, 0.0)
        mkt_value  = shares * cur_price
        cost_basis = shares * avg_cost
        unreal_pnl = mkt_value - cost_basis
        unreal_pct = (unreal_pnl / cost_basis * 100) if cost_basis else 0
        prev       = prev_closes.get(ticker, cur_price)
        day_chg    = ((cur_price - prev) / prev * 100) if prev else 0

        total_market_value += mkt_value
        total_cost_basis   += cost_basis

        holdings.append({
            "ticker":       ticker,
            "shares":       round(shares, 6),
            "avg_cost":     round(avg_cost, 4),
            "cur_price":    round(cur_price, 2),
            "mkt_value":    round(mkt_value, 2),
            "cost_basis":   round(cost_basis, 2),
            "unreal_pnl":   round(unreal_pnl, 2),
            "unreal_pct":   round(unreal_pct, 2),
            "day_chg_pct":  round(day_chg, 2),
            "realized_pnl": round(portfolio["realized"].get(ticker, 0), 2),
        })

    holdings.sort(key=lambda h: abs(h["unreal_pnl"]), reverse=True)

    total_realized  = sum(portfolio["realized"].values())
    total_portfolio = portfolio["cash_usd"] + total_market_value
    total_return    = ((total_portfolio - total_cost_basis) / total_cost_basis * 100
                       if total_cost_basis > 0 else 0)

    return {
        **portfolio,
        "holdings":           holdings,
        "total_market_value": round(total_market_value, 2),
        "total_cost_basis":   round(total_cost_basis, 2),
        "total_realized":     round(total_realized, 2),
        "total_unreal":       round(total_market_value - total_cost_basis, 2),
        "total_portfolio":    round(total_portfolio, 2),
        "total_portfolio_hkd": round(total_portfolio * usdhkd, 2),
        "total_return_pct":   round(total_return, 2),
        "usdhkd":             round(usdhkd, 4),
    }


# ── HTML template ─────────────────────────────────────────────────────────────

PORTFOLIO_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Portfolio · {{ date }}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --bg:#0b0c10; --surface:#13141b; --elevated:#1a1c25; --border:#23252f;
  --border-hi:#33363f; --text:#e7e8ec; --text-2:#8a8c98; --muted:#52545e;
  --up:#34d399; --down:#f87171; --amber:#f5b942; --blue:#7aa2ff; --purple:#b18cff;
  --cyan:#22d3ee;
  --mono:'JetBrains Mono',monospace; --sans:'Inter',system-ui,sans-serif;
}
*, *::before, *::after { box-sizing:border-box; margin:0; padding:0; }
body { background:var(--bg); color:var(--text); font-family:var(--sans);
  font-size:13px; line-height:1.55; min-height:100vh; -webkit-font-smoothing:antialiased; }
.top { position:sticky; top:0; z-index:50; background:var(--surface);
  border-bottom:1px solid var(--border); backdrop-filter:blur(12px); }
.top-row { display:flex; align-items:center; gap:16px; padding:0 24px; height:56px; }
.brand-logo { width:26px; height:26px; border-radius:7px;
  background:linear-gradient(135deg,var(--cyan),var(--blue));
  display:flex; align-items:center; justify-content:center;
  color:#fff; font-weight:700; font-size:12px; font-family:var(--mono); }
.brand-title { font-size:14px; font-weight:600; }
.brand-sub { font-family:var(--mono); font-size:10px; color:var(--text-2); }
.back-btn { margin-left:auto; font-family:var(--mono); font-size:11px;
  color:var(--blue); text-decoration:none; padding:5px 10px;
  border:1px solid rgba(122,162,255,0.3); border-radius:6px; }
.back-btn:hover { background:rgba(122,162,255,0.08); }
.page { max-width:1200px; margin:0 auto; padding:20px 24px 60px;
  display:flex; flex-direction:column; gap:16px; }
.card { background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:18px 20px; }
.section-pill { display:inline-flex; align-items:center; font-family:var(--mono);
  font-size:9px; font-weight:700; letter-spacing:0.06em; text-transform:uppercase;
  padding:3px 9px; border-radius:10px; margin-bottom:14px; }
.pill-cyan   { background:rgba(34,211,238,0.10); color:var(--cyan);   border:1px solid rgba(34,211,238,0.25); }
.pill-blue   { background:rgba(122,162,255,0.10); color:var(--blue);  border:1px solid rgba(122,162,255,0.25); }
.pill-amber  { background:rgba(245,185,66,0.10);  color:var(--amber); border:1px solid rgba(245,185,66,0.25); }
/* Account summary banner */
.account-banner { display:grid; grid-template-columns:repeat(5,1fr); gap:12px; }
@media(max-width:900px){ .account-banner{ grid-template-columns:repeat(3,1fr); } }
@media(max-width:600px){ .account-banner{ grid-template-columns:1fr 1fr; } }
.acct-card { background:var(--elevated); border:1px solid var(--border); border-radius:10px; padding:14px 16px; }
.acct-label { font-size:11px; color:var(--text-2); font-weight:500; }
.acct-val { font-family:var(--mono); font-size:20px; font-weight:700; letter-spacing:-0.02em; margin-top:5px; }
.acct-sub { font-family:var(--mono); font-size:10px; color:var(--text-2); margin-top:2px; }
.acct-val.up { color:var(--up); }
.acct-val.down { color:var(--down); }
.acct-val.neutral { color:var(--text); }
/* FX bar */
.fx-bar { background:rgba(34,211,238,0.06); border:1px solid rgba(34,211,238,0.15);
  border-radius:8px; padding:10px 16px; font-family:var(--mono); font-size:11px;
  color:var(--text-2); display:flex; gap:24px; flex-wrap:wrap; align-items:center; }
/* Tables */
table { width:100%; border-collapse:collapse; }
thead tr { background:var(--bg); }
th { padding:9px 12px; font-size:11px; font-weight:500; color:var(--text-2);
  text-align:right; border-bottom:1px solid var(--border); white-space:nowrap; }
th.left { text-align:left; }
td { padding:10px 12px; border-bottom:1px solid var(--border); vertical-align:middle; }
tbody tr:last-child td { border-bottom:none; }
tbody tr:hover td { background:rgba(255,255,255,0.02); }
.mono { font-family:var(--mono); font-size:12px; }
.num  { font-family:var(--mono); font-size:12px; text-align:right; }
.chip { font-family:var(--mono); font-size:11px; font-weight:600;
  padding:2px 8px; border-radius:4px; display:inline-block; }
.chip.up   { color:var(--up);   background:rgba(52,211,153,0.10); }
.chip.down { color:var(--down); background:rgba(248,113,113,0.10); }
.chip.na   { color:var(--muted); background:rgba(255,255,255,0.03); }
.chip.buy  { color:var(--up);   background:rgba(52,211,153,0.08); border:1px solid rgba(52,211,153,0.2); }
.chip.sell { color:var(--down); background:rgba(248,113,113,0.08); border:1px solid rgba(248,113,113,0.2); }
.chip.dep  { color:var(--cyan); background:rgba(34,211,238,0.08);  border:1px solid rgba(34,211,238,0.2); }
.chip.with { color:var(--amber);background:rgba(245,185,66,0.08);  border:1px solid rgba(245,185,66,0.2); }
.ticker-tag { font-family:var(--mono); font-size:11px; font-weight:700;
  background:var(--elevated); border:1px solid var(--border-hi);
  padding:2px 8px; border-radius:4px; color:var(--text); }
.empty { padding:40px; text-align:center; font-family:var(--mono);
  font-size:12px; color:var(--text-2); }
.help-box { background:rgba(122,162,255,0.05); border:1px solid rgba(122,162,255,0.2);
  border-radius:8px; padding:14px 18px; font-family:var(--mono); font-size:11px;
  color:var(--text-2); line-height:1.7; }
.footer { text-align:center; padding:24px; color:var(--muted);
  font-family:var(--mono); font-size:10px; letter-spacing:0.06em; }
@media(max-width:768px){ .page{padding:12px 12px 40px;} .mob-hide{display:none!important;} }
</style>
</head>
<body>

<header class="top">
  <div class="top-row">
    <div class="brand-logo">$</div>
    <div>
      <div class="brand-title">My Portfolio</div>
      <div class="brand-sub">updated {{ date }} · USD/HKD {{ usdhkd }}</div>
    </div>
    <a href="./index.html" class="back-btn">← 返回總覽</a>
  </div>
</header>

<div class="page">

{% if not has_transactions %}
<div class="card">
  <div class="empty">Portfolio is empty.<br><br>Add your first transaction:</div>
  <div class="help-box" style="margin-top:16px">
    <strong style="color:var(--text)">How to add transactions:</strong><br><br>
    # Deposit cash<br>
    <span style="color:var(--cyan)">python add_transaction.py deposit 50000 HKD</span><br>
    <span style="color:var(--cyan)">python add_transaction.py deposit 10000 USD</span><br><br>
    # Buy shares<br>
    <span style="color:var(--up)">python add_transaction.py buy NVDA 10 125.50 USD</span><br>
    <span style="color:var(--up)">python add_transaction.py buy NVDA 10 980.00 HKD</span><br><br>
    # Sell shares<br>
    <span style="color:var(--down)">python add_transaction.py sell NVDA 5 140.00 USD</span><br><br>
    After running the command, push to GitHub to redeploy.
  </div>
</div>
{% else %}

<!-- ── ACCOUNT SUMMARY ── -->
<div class="card">
  <span class="section-pill pill-cyan">Account Overview</span>
  <div class="account-banner">
    <div class="acct-card">
      <div class="acct-label">Portfolio Value</div>
      <div class="acct-val neutral">${{ '{:,.2f}'.format(total_portfolio) }}</div>
      <div class="acct-sub">≈ HK${{ '{:,.0f}'.format(total_portfolio_hkd) }}</div>
    </div>
    <div class="acct-card">
      <div class="acct-label">Unrealized P&L</div>
      <div class="acct-val {{ 'up' if total_unreal >= 0 else 'down' }}">
        {{ '%+,.2f'|format(total_unreal) }}
      </div>
      <div class="acct-sub">{{ '%+.2f'|format(total_return_pct) }}% total return</div>
    </div>
    <div class="acct-card">
      <div class="acct-label">Realized P&L</div>
      <div class="acct-val {{ 'up' if total_realized >= 0 else 'down' }}">
        {{ '%+,.2f'|format(total_realized) }}
      </div>
      <div class="acct-sub">from closed positions</div>
    </div>
    <div class="acct-card">
      <div class="acct-label">Invested (Cost Basis)</div>
      <div class="acct-val neutral">${{ '{:,.2f}'.format(total_cost_basis) }}</div>
      <div class="acct-sub">in {{ holdings|length }} position{{ 's' if holdings|length != 1 }}</div>
    </div>
    <div class="acct-card">
      <div class="acct-label">Cash Balance</div>
      <div class="acct-val {{ 'up' if cash_usd >= 0 else 'down' }}">${{ '{:,.2f}'.format(cash_usd) }}</div>
      <div class="acct-sub">≈ HK${{ '{:,.0f}'.format(cash_hkd) }}</div>
    </div>
  </div>

  <!-- FX info -->
  <div class="fx-bar" style="margin-top:14px">
    <span>💱 USD/HKD: <strong style="color:var(--cyan)">{{ usdhkd }}</strong></span>
    <span>Positions market value: <strong style="color:var(--text)">${{ '{:,.2f}'.format(total_market_value) }}</strong></span>
    <span>Total cost basis: <strong style="color:var(--text-2)">${{ '{:,.2f}'.format(total_cost_basis) }}</strong></span>
  </div>
</div>

<!-- ── POSITIONS ── -->
{% if holdings %}
<div class="card" style="padding:0;overflow:hidden">
  <div style="padding:16px 20px;border-bottom:1px solid var(--border)">
    <span class="section-pill pill-blue">Open Positions · {{ holdings|length }}</span>
    <div style="font-size:12px;color:var(--text-2)">Prices updated at pipeline run · sorted by unrealized P&L</div>
  </div>
  <div style="overflow-x:auto">
  <table>
    <thead>
      <tr>
        <th class="left">Ticker</th>
        <th>Shares</th>
        <th>Avg Cost</th>
        <th>Current $</th>
        <th>Mkt Value</th>
        <th>Unrealized P&L</th>
        <th>Unrealized %</th>
        <th class="mob-hide">Day Chg %</th>
        <th class="mob-hide">Realized P&L</th>
      </tr>
    </thead>
    <tbody>
    {% for h in holdings %}
    <tr>
      <td><span class="ticker-tag">{{ h.ticker }}</span></td>
      <td class="num">{{ h.shares }}</td>
      <td class="num">${{ '%.2f'|format(h.avg_cost) }}</td>
      <td class="num">${{ '%.2f'|format(h.cur_price) }}</td>
      <td class="num">${{ '{:,.2f}'.format(h.mkt_value) }}</td>
      <td class="num">
        <span class="chip {{ 'up' if h.unreal_pnl >= 0 else 'down' }}">${{ '%+,.2f'|format(h.unreal_pnl) }}</span>
      </td>
      <td class="num">
        <span class="chip {{ 'up' if h.unreal_pct >= 0 else 'down' }}">{{ '%+.2f'|format(h.unreal_pct) }}%</span>
      </td>
      <td class="num mob-hide">
        <span style="font-family:var(--mono);font-size:12px;color:{{ 'var(--up)' if h.day_chg_pct >= 0 else 'var(--down)' }}">{{ '%+.2f'|format(h.day_chg_pct) }}%</span>
      </td>
      <td class="num mob-hide">
        {% if h.realized_pnl %}
        <span class="chip {{ 'up' if h.realized_pnl >= 0 else 'down' }}">${{ '%+,.2f'|format(h.realized_pnl) }}</span>
        {% else %}<span style="color:var(--muted)">—</span>{% endif %}
      </td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
  </div>
</div>
{% endif %}

<!-- ── TRANSACTION LOG ── -->
<div class="card" style="padding:0;overflow:hidden">
  <div style="padding:16px 20px;border-bottom:1px solid var(--border)">
    <span class="section-pill pill-amber">Transaction Log · {{ enriched_txns|length }} entries · most recent first</span>
  </div>
  <div style="overflow-x:auto">
  <table>
    <thead>
      <tr>
        <th class="left">Date</th>
        <th class="left">Type</th>
        <th class="left mob-hide">Ticker</th>
        <th class="mob-hide">Shares</th>
        <th class="mob-hide">Price (orig)</th>
        <th>Amount (USD)</th>
        <th>Cash After</th>
        <th class="mob-hide">Notes</th>
      </tr>
    </thead>
    <tbody>
    {% for t in enriched_txns %}
    <tr>
      <td class="mono" style="color:var(--text-2)">{{ t.date }}</td>
      <td>
        {% set tp = t.type|lower %}
        {% if tp == 'buy' %}<span class="chip buy">↑ BUY</span>
        {% elif tp == 'sell' %}<span class="chip sell">↓ SELL</span>
        {% elif tp == 'deposit' %}<span class="chip dep">+ DEPOSIT</span>
        {% else %}<span class="chip with">- WITHDRAW</span>{% endif %}
      </td>
      <td class="mob-hide">
        {% if t.ticker %}<span class="ticker-tag">{{ t.ticker }}</span>{% else %}<span style="color:var(--muted)">—</span>{% endif %}
      </td>
      <td class="num mob-hide">{{ t.shares if t.shares else '—' }}</td>
      <td class="num mob-hide">
        {% if t.price %}{{ t.price }} {{ t.currency }}{% else %}—{% endif %}
      </td>
      <td class="num">
        {% set amt = t.amount_usd or 0 %}
        <span style="font-family:var(--mono);font-size:12px;color:{{ 'var(--up)' if amt >= 0 else 'var(--down)' }}">{{ '%+,.2f'|format(amt) }}</span>
        {% if t.get('realized_pnl') %}
        <div style="font-size:10px;color:{{ 'var(--up)' if t.realized_pnl >= 0 else 'var(--down)' }}">realised {{ '%+.2f'|format(t.realized_pnl) }}</div>
        {% endif %}
      </td>
      <td class="num">${{ '{:,.2f}'.format(t.cash_after) }}</td>
      <td class="mob-hide" style="color:var(--text-2);font-size:12px">{{ t.notes or '—' }}</td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
  </div>
</div>

{% endif %}

<!-- Help box always shown at bottom -->
<div class="help-box">
  <strong style="color:var(--text)">Add transactions via CLI:</strong><br>
  <span style="color:var(--cyan)">python add_transaction.py deposit 50000 HKD</span> &nbsp;·&nbsp;
  <span style="color:var(--up)">python add_transaction.py buy NVDA 10 125.50 USD</span> &nbsp;·&nbsp;
  <span style="color:var(--down)">python add_transaction.py sell NVDA 5 140.00 USD</span><br>
  Push to GitHub after adding — the next pipeline run updates prices and P&L automatically.
</div>

</div>
<div class="footer">SIGNAL MONITOR · PORTFOLIO · {{ date }} · USD/HKD {{ usdhkd }}</div>
</body>
</html>
"""


# ── Entry point ───────────────────────────────────────────────────────────────

def run_portfolio(output_dir: str = "outputs") -> str | None:
    """Compute portfolio and write outputs/portfolio.html. Returns output path."""
    txns = load_transactions()

    print(f"  [portfolio] fetching USD/HKD rate…")
    usdhkd = fetch_usdhkd()
    print(f"  [portfolio] USD/HKD = {usdhkd:.4f}")

    result = compute_portfolio(txns, usdhkd)

    held = result["held_tickers"]
    prices, prev_closes = {}, {}
    if held:
        print(f"  [portfolio] fetching prices for {held}…")
        prices      = fetch_current_prices(held)
        prev_closes = fetch_prev_close(held)

    result = enrich_with_prices(result, prices, prev_closes, usdhkd)

    today_str = datetime.now().strftime("%Y/%m/%d")
    html = Template(PORTFOLIO_HTML).render(
        date=today_str,
        has_transactions=bool(txns),
        usdhkd=result["usdhkd"],
        cash_usd=result["cash_usd"],
        cash_hkd=result["cash_hkd"],
        total_portfolio=result["total_portfolio"],
        total_portfolio_hkd=result["total_portfolio_hkd"],
        total_market_value=result["total_market_value"],
        total_cost_basis=result["total_cost_basis"],
        total_unreal=result["total_unreal"],
        total_realized=result["total_realized"],
        total_return_pct=result["total_return_pct"],
        holdings=result["holdings"],
        enriched_txns=result["enriched_txns"],
    )

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "portfolio.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    n_pos = len(result["holdings"])
    print(f"  [portfolio] → {out_path}  ({n_pos} positions · ${result['total_portfolio']:,.2f} total)")
    return out_path
