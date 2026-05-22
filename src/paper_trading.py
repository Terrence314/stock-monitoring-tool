"""paper_trading.py — Paper trading simulator (long + short).

On every daily run, this module:
  1. Opens LONG $1,000 positions for tickers scoring >= BUY_THRESHOLD (≥70)
  2. Opens SHORT $1,000 positions for tickers scoring <= SELL_THRESHOLD (≤30)
  3. Updates floating P&L for all open positions using today's fresh prices
  4. Auto-closes positions held for HOLD_DAYS trading days
  5. Renders outputs/paper_trading.html

Short P&L is inverted: profit when price falls (sell high → buy back low).
Portfolio state persists in outputs/paper_portfolio.json, deployed to
GitHub Pages and restored via curl before each pipeline run.
"""

import os
import json
from datetime import datetime, timedelta, timezone
import yfinance as yf
from jinja2 import Template

PORTFOLIO_FILE   = os.path.join("outputs", "paper_portfolio.json")
BUY_THRESHOLD    = 70       # score >= this → LONG signal
SELL_THRESHOLD   = 30       # score <= this → SHORT signal
SIGNAL_THRESHOLD = BUY_THRESHOLD   # kept for backtest compat
NOTIONAL         = 1000.0   # USD virtual capital per trade
HOLD_DAYS        = 10       # trading days before auto-close


# ── Persistence ────────────────────────────────────────────────────────────────

def _load_portfolio() -> dict:
    try:
        with open(PORTFOLIO_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {"trades": [], "last_updated": ""}


def _save_portfolio(p: dict) -> None:
    os.makedirs(os.path.dirname(PORTFOLIO_FILE) or ".", exist_ok=True)
    with open(PORTFOLIO_FILE, "w", encoding="utf-8") as f:
        json.dump(p, f, ensure_ascii=False, indent=2)


# ── Trading calendar ───────────────────────────────────────────────────────────

def _fetch_calendar(from_date: str) -> list:
    """List of NYSE trading days from from_date to today via SPY."""
    raw = yf.download("SPY", start=from_date, progress=False, auto_adjust=True)
    if raw.empty:
        return []
    dates = []
    for d in raw.index:
        dates.append(str(d.date()) if hasattr(d, "date") else str(d)[:10])
    return sorted(dates)


def _nth_trading_day_after(start: str, n: int, cal: list) -> str | None:
    """Return the date that is exactly n trading days after start (exclusive)."""
    future = [d for d in cal if d > start]
    return future[n - 1] if len(future) >= n else None


def _days_elapsed(start: str, today: str, cal: list) -> int:
    """Count trading days strictly between start and today (inclusive of today)."""
    return sum(1 for d in cal if start < d <= today)


# ── Price fetching ─────────────────────────────────────────────────────────────

def _fetch_prices_bulk(tickers: list, start_date: str) -> dict:
    """Bulk-fetch close prices for tickers from start_date to today.

    Returns {ticker: {date_str: close_price}}.
    """
    if not tickers:
        return {}

    def _to_str(ts) -> str:
        return str(ts.date()) if hasattr(ts, "date") else str(ts)[:10]

    raw = yf.download(
        tickers, start=start_date,
        auto_adjust=True, progress=False, threads=True,
    )
    result: dict = {}
    if len(tickers) == 1:
        t = tickers[0]
        if "Close" in raw.columns:
            result[t] = {_to_str(d): float(v) for d, v in raw["Close"].dropna().items()}
    else:
        close = raw.get("Close", raw)
        for t in tickers:
            if t in close.columns:
                result[t] = {_to_str(d): float(v) for d, v in close[t].dropna().items()}
    return result


def _get_exit_price(ticker: str, exit_date: str, series: dict) -> float | None:
    """Find closest closing price on or after exit_date from a price series dict."""
    for d in sorted(series.keys()):
        if d >= exit_date:
            return series[d]
    return None


# ── Stats helpers ──────────────────────────────────────────────────────────────

def _float_pnl(trade: dict) -> tuple:
    """Return (pnl_dollars, pnl_pct) for an open position using current_price.

    For LONG:  profit when price rises   → (current - entry) * shares
    For SHORT: profit when price falls   → (entry - current) * shares
    """
    cp = trade.get("current_price") or trade["entry_price"]
    ep = trade["entry_price"]
    shares = trade["shares"]
    is_short = trade.get("direction", "long") == "short"
    if is_short:
        pnl = round((ep - cp) * shares, 2)
        pct = round((ep - cp) / ep * 100, 2) if ep > 0 else 0.0
    else:
        pnl = round((cp - ep) * shares, 2)
        pct = round((cp - ep) / ep * 100, 2) if ep > 0 else 0.0
    return pnl, pct


def _build_stats(trades: list) -> dict:
    closed = [t for t in trades if t["status"] == "closed"]
    open_t = [t for t in trades if t["status"] == "open"]

    longs  = [t for t in trades if t.get("direction", "long") == "long"]
    shorts = [t for t in trades if t.get("direction", "long") == "short"]

    realized_pnl = round(sum(t["pnl"] or 0 for t in closed), 2)

    float_pnl_total = 0.0
    for t in open_t:
        fp, _ = _float_pnl(t)
        float_pnl_total += fp
    float_pnl_total = round(float_pnl_total, 2)

    wins = [t for t in closed if (t["pnl"] or 0) > 0]
    win_rate = round(len(wins) / len(closed) * 100, 1) if closed else None

    pnl_pcts = [t["pnl_pct"] for t in closed if t.get("pnl_pct") is not None]
    avg_return = round(sum(pnl_pcts) / len(pnl_pcts), 2) if pnl_pcts else None

    # Per-side closed stats
    def _side_stats(side_trades: list) -> dict:
        side_closed = [t for t in side_trades if t["status"] == "closed"]
        if not side_closed:
            return {"n": 0, "win_rate": None, "avg": None, "pnl": 0.0}
        side_wins = sum(1 for t in side_closed if (t["pnl"] or 0) > 0)
        side_pcts = [t["pnl_pct"] for t in side_closed if t.get("pnl_pct") is not None]
        return {
            "n":        len(side_closed),
            "win_rate": round(side_wins / len(side_closed) * 100, 1),
            "avg":      round(sum(side_pcts) / len(side_pcts), 2) if side_pcts else None,
            "pnl":      round(sum(t["pnl"] or 0 for t in side_closed), 2),
        }

    return {
        "n_open":          len(open_t),
        "n_closed":        len(closed),
        "n_long":          len(longs),
        "n_short":         len(shorts),
        "total_trades":    len(trades),
        "realized_pnl":    realized_pnl,
        "float_pnl":       float_pnl_total,
        "win_rate":        win_rate,
        "avg_return":      avg_return,
        "total_notional":  len(trades) * NOTIONAL,
        "long_stats":      _side_stats(longs),
        "short_stats":     _side_stats(shorts),
    }


def _build_equity_curve(trades: list) -> list:
    """Return [{date, cumulative_pnl}] sorted by exit_date for closed trades."""
    closed = sorted(
        [t for t in trades if t["status"] == "closed" and t.get("exit_date")],
        key=lambda t: t["exit_date"],
    )
    curve = []
    running = 0.0
    for t in closed:
        running += t.get("pnl") or 0
        curve.append({"date": t["exit_date"], "ticker": t["ticker"],
                       "pnl": t["pnl"], "cum": round(running, 2)})
    return curve


def _svg_pnl_bars(curve: list, w: int = 600, h: int = 80) -> str:
    """Generate a minimal SVG bar chart for per-trade P&L."""
    if not curve:
        return ""
    pnls = [c["pnl"] for c in curve]
    max_abs = max(abs(v) for v in pnls) or 1
    n = len(pnls)
    bar_w = max(4, min(40, (w - 20) // n - 2))
    spacing = (w - 20) // n
    mid_y = h // 2
    parts = []
    for i, v in enumerate(pnls):
        x = 10 + i * spacing
        bar_h = max(2, int(abs(v) / max_abs * (mid_y - 4)))
        y = mid_y - bar_h if v >= 0 else mid_y
        color = "#34d399" if v >= 0 else "#f87171"
        parts.append(f'<rect x="{x}" y="{y}" width="{bar_w}" height="{bar_h}" fill="{color}" rx="2"/>')
    # Centre line
    parts.append(f'<line x1="0" y1="{mid_y}" x2="{w}" y2="{mid_y}" stroke="#23252f" stroke-width="1"/>')
    return (f'<svg viewBox="0 0 {w} {h}" width="100%" height="{h}" '
            f'xmlns="http://www.w3.org/2000/svg">' + "".join(parts) + "</svg>")


# ── HTML template ──────────────────────────────────────────────────────────────

PAPER_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Paper Trading · Long &amp; Short · {{ date }}</title>
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
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { background:var(--bg); color:var(--text); font-family:var(--sans);
  font-size:13px; line-height:1.55; min-height:100vh; -webkit-font-smoothing:antialiased; }
.top { position:sticky; top:0; z-index:50; background:var(--surface);
  border-bottom:1px solid var(--border); backdrop-filter:blur(12px); }
.top-row { display:flex; align-items:center; gap:16px; padding:0 24px; height:56px; }
.brand-logo { width:26px; height:26px; border-radius:7px;
  background:linear-gradient(135deg,var(--up),var(--cyan));
  display:flex; align-items:center; justify-content:center;
  color:#fff; font-weight:700; font-size:12px; font-family:var(--mono); }
.brand-title { font-size:14px; font-weight:600; }
.brand-sub { font-family:var(--mono); font-size:10px; color:var(--text-2); }
.back-btn { margin-left:auto; font-family:var(--mono); font-size:11px;
  color:var(--blue); text-decoration:none; padding:5px 10px;
  border:1px solid rgba(122,162,255,0.3); border-radius:6px; }
.back-btn:hover { background:rgba(122,162,255,0.08); }
.page { max-width:1100px; margin:0 auto; padding:20px 24px 60px; display:flex; flex-direction:column; gap:16px; }
.card { background:var(--surface); border:1px solid var(--border); border-radius:12px; padding:18px 20px; }
.card-title { font-size:14px; font-weight:600; letter-spacing:-0.005em; }
.card-sub { font-size:11px; color:var(--text-2); }
.section-pill { display:inline-flex; align-items:center; font-family:var(--mono); font-size:9px;
  font-weight:700; letter-spacing:0.06em; text-transform:uppercase; padding:3px 9px;
  border-radius:10px; background:rgba(52,211,153,0.10); color:var(--up);
  border:1px solid rgba(52,211,153,0.25); margin-bottom:14px; }
.section-pill.open-pill { background:rgba(122,162,255,0.10); color:var(--blue);
  border:1px solid rgba(122,162,255,0.25); }
.section-pill.closed-pill { background:rgba(245,185,66,0.10); color:var(--amber);
  border:1px solid rgba(245,185,66,0.25); }
.kpi-grid { display:grid; grid-template-columns:repeat(4,1fr); gap:12px; }
@media (max-width:700px) { .kpi-grid { grid-template-columns:1fr 1fr; } }
.kpi { background:var(--elevated); border:1px solid var(--border); border-radius:10px; padding:14px 16px; }
.kpi-label { font-size:11px; color:var(--text-2); font-weight:500; }
.kpi-val { font-family:var(--mono); font-size:22px; font-weight:700; letter-spacing:-0.02em; margin-top:6px; }
.kpi-sub { font-family:var(--mono); font-size:10px; color:var(--text-2); margin-top:2px; }
.kpi-val.up { color:var(--up); }
.kpi-val.down { color:var(--down); }
.kpi-val.amber { color:var(--amber); }
.kpi-val.blue { color:var(--blue); }
.kpi-val.neutral { color:var(--text); }
table { width:100%; border-collapse:collapse; }
thead tr { background:var(--bg); }
th { padding:9px 12px; font-size:11px; font-weight:500; color:var(--text-2);
  text-align:right; border-bottom:1px solid var(--border); white-space:nowrap; }
th.left { text-align:left; }
td { padding:11px 12px; border-bottom:1px solid var(--border); vertical-align:middle; }
tbody tr:last-child td { border-bottom:none; }
tbody tr:hover td { background:rgba(255,255,255,0.02); }
.mono { font-family:var(--mono); font-size:12px; }
.num { font-family:var(--mono); font-size:12px; text-align:right; }
.chip { font-family:var(--mono); font-size:11px; font-weight:600;
  padding:2px 8px; border-radius:4px; display:inline-block; }
.chip.up   { color:var(--up);   background:rgba(52,211,153,0.10); }
.chip.down { color:var(--down); background:rgba(248,113,113,0.10); }
.chip.na    { color:var(--muted); background:rgba(255,255,255,0.03); }
.chip.open  { color:var(--blue);  background:rgba(122,162,255,0.10); }
.chip.long  { color:var(--up);    background:rgba(52,211,153,0.10); border:1px solid rgba(52,211,153,0.2); }
.chip.short { color:var(--down);  background:rgba(248,113,113,0.10); border:1px solid rgba(248,113,113,0.2); }
.ticker-tag { font-family:var(--mono); font-size:11px; font-weight:700;
  background:var(--elevated); border:1px solid var(--border-hi);
  padding:2px 8px; border-radius:4px; color:var(--text); }
.status-dot { display:inline-block; width:7px; height:7px; border-radius:50%;
  margin-right:5px; vertical-align:middle; }
.status-dot.open   { background:var(--blue); box-shadow:0 0 4px var(--blue); }
.status-dot.closed { background:var(--muted); }
.chart-wrap { margin-top:14px; }
.chart-label { font-family:var(--mono); font-size:9px; color:var(--text-2);
  text-transform:uppercase; letter-spacing:0.06em; margin-bottom:6px; }
.empty { padding:32px; text-align:center; font-family:var(--mono);
  font-size:12px; color:var(--text-2); }
.note-box { background:rgba(122,162,255,0.06); border:1px solid rgba(122,162,255,0.2);
  border-radius:8px; padding:12px 16px; font-size:12px; color:var(--text-2);
  font-family:var(--mono); line-height:1.6; }
.days-bar { background:var(--elevated); border-radius:4px; height:4px; width:80px;
  display:inline-block; vertical-align:middle; overflow:hidden; }
.days-fill { height:100%; border-radius:4px; background:var(--blue); }
.footer { text-align:center; padding:24px; color:var(--muted);
  font-family:var(--mono); font-size:10px; letter-spacing:0.06em; }
@media (max-width:768px) {
  .page { padding:12px 12px 40px; }
  .mob-hide { display:none !important; }
  th, td { padding:8px 8px; }
}
</style>
</head>
<body>
<header class="top">
  <div class="top-row">
    <div class="brand-logo">P</div>
    <div>
      <div class="brand-title">Paper Trading · ${{ notional|int }}/trade · {{ hold_days }}d hold</div>
      <div class="brand-sub">updated {{ date }} · {{ stats.n_long }} long · {{ stats.n_short }} short · buy ≥{{ buy_threshold }} / sell ≤{{ sell_threshold }}</div>
    </div>
    <a href="./index.html" class="back-btn">← 返回總覽</a>
  </div>
</header>

<div class="page">

<!-- ── KPI CARDS ── -->
<div class="card">
  <span class="section-pill">Portfolio Summary</span>
  <div class="kpi-grid">
    <div class="kpi">
      <div class="kpi-label">Capital Deployed</div>
      <div class="kpi-val neutral">${{ '%.0f'|format(stats.total_notional) }}</div>
      <div class="kpi-sub">{{ stats.total_trades }} × ${{ notional|int }}</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Realized P&L</div>
      <div class="kpi-val {{ 'up' if stats.realized_pnl >= 0 else 'down' }}">
        {{ '%+.2f'|format(stats.realized_pnl) }}
      </div>
      <div class="kpi-sub">{{ stats.n_closed }} closed trades</div>
    </div>
    <div class="kpi">
      <div class="kpi-label">Win Rate</div>
      {% if stats.win_rate is not none %}
      <div class="kpi-val {{ 'up' if stats.win_rate >= 55 else ('amber' if stats.win_rate >= 45 else 'down') }}">
        {{ stats.win_rate }}%
      </div>
      <div class="kpi-sub">of {{ stats.n_closed }} closed</div>
      {% else %}
      <div class="kpi-val neutral">—</div>
      <div class="kpi-sub">awaiting closures</div>
      {% endif %}
    </div>
    <div class="kpi">
      <div class="kpi-label">Avg Return / Trade</div>
      {% if stats.avg_return is not none %}
      <div class="kpi-val {{ 'up' if stats.avg_return >= 0 else 'down' }}">
        {{ '%+.2f'|format(stats.avg_return) }}%
      </div>
      {% else %}
      <div class="kpi-val neutral">—</div>
      {% endif %}
      <div class="kpi-sub">closed trades only</div>
    </div>
  </div>

  <!-- Long vs Short breakdown (shown once there are closed trades) -->
  {% if stats.n_closed > 0 %}
  <div style="margin-top:12px;display:grid;grid-template-columns:1fr 1fr;gap:10px">
    <div style="background:rgba(52,211,153,0.05);border:1px solid rgba(52,211,153,0.2);border-radius:8px;padding:12px 14px">
      <div style="font-size:11px;color:var(--up);font-weight:600;margin-bottom:6px">📈 LONG  (score ≥ {{ buy_threshold }})</div>
      {% if stats.long_stats.n > 0 %}
      <span class="mono" style="font-size:12px">{{ stats.long_stats.n }} closed · win rate <strong>{{ stats.long_stats.win_rate }}%</strong> · avg <strong style="color:{{ 'var(--up)' if stats.long_stats.avg >= 0 else 'var(--down)' }}">{{ '%+.2f'|format(stats.long_stats.avg) if stats.long_stats.avg is not none else '—' }}%</strong></span>
      {% else %}
      <span class="mono" style="font-size:11px;color:var(--muted)">no closed longs yet</span>
      {% endif %}
    </div>
    <div style="background:rgba(248,113,113,0.05);border:1px solid rgba(248,113,113,0.2);border-radius:8px;padding:12px 14px">
      <div style="font-size:11px;color:var(--down);font-weight:600;margin-bottom:6px">📉 SHORT  (score ≤ {{ sell_threshold }})</div>
      {% if stats.short_stats.n > 0 %}
      <span class="mono" style="font-size:12px">{{ stats.short_stats.n }} closed · win rate <strong>{{ stats.short_stats.win_rate }}%</strong> · avg <strong style="color:{{ 'var(--up)' if stats.short_stats.avg >= 0 else 'var(--down)' }}">{{ '%+.2f'|format(stats.short_stats.avg) if stats.short_stats.avg is not none else '—' }}%</strong></span>
      {% else %}
      <span class="mono" style="font-size:11px;color:var(--muted)">no closed shorts yet</span>
      {% endif %}
    </div>
  </div>
  {% endif %}
</div>

<!-- ── FLOATING P&L OPEN ── -->
{% if stats.float_pnl != 0 or stats.n_open > 0 %}
<div class="card">
  <div style="display:flex;align-items:center;gap:10px;margin-bottom:4px">
    <span class="section-pill open-pill">Open Positions · {{ stats.n_open }}</span>
  </div>
  <div class="card-sub" style="margin-bottom:12px">
    Floating unrealized: <span style="font-family:var(--mono);color:{{ 'var(--up)' if stats.float_pnl >= 0 else 'var(--down)' }}">{{ '%+.2f'|format(stats.float_pnl) }}</span>
    · Closes at +{{ hold_days }} trading days from entry
  </div>
  {% if open_positions %}
  <div style="overflow-x:auto">
  <table>
    <thead>
      <tr>
        <th class="left">Ticker</th>
        <th class="left mob-hide">Dir</th>
        <th class="left mob-hide">Entry Date</th>
        <th>Score</th>
        <th>Entry $</th>
        <th>Current $</th>
        <th>Float P&L</th>
        <th>Float %</th>
        <th class="mob-hide">Days Held</th>
        <th class="mob-hide">Days Left</th>
      </tr>
    </thead>
    <tbody>
    {% for p in open_positions %}
    <tr>
      <td><span class="status-dot open"></span><span class="ticker-tag">{{ p.ticker }}</span></td>
      <td class="mob-hide"><span class="chip {{ p.direction }}">{{ '↑ LONG' if p.direction == 'long' else '↓ SHORT' }}</span></td>
      <td class="mono mob-hide" style="color:var(--text-2)">{{ p.signal_date }}</td>
      <td class="num" style="color:var(--amber)">{{ p.score }}</td>
      <td class="num">{{ '%.2f'|format(p.entry_price) }}</td>
      <td class="num">{{ '%.2f'|format(p.current_price) }}</td>
      <td class="num">
        <span class="chip {{ 'up' if p.float_pnl >= 0 else 'down' }}">${{ '%+.2f'|format(p.float_pnl) }}</span>
      </td>
      <td class="num">
        <span class="chip {{ 'up' if p.float_pct >= 0 else 'down' }}">{{ '%+.2f'|format(p.float_pct) }}%</span>
      </td>
      <td class="num mob-hide">
        <div style="display:flex;align-items:center;gap:8px;justify-content:flex-end">
          {{ p.days_held }}/{{ hold_days }}
          <div class="days-bar"><div class="days-fill" style="width:{{ [p.days_held * 100 // hold_days, 100]|min }}%"></div></div>
        </div>
      </td>
      <td class="num mob-hide">
        {% if p.days_left > 0 %}
        <span style="color:var(--text-2)">{{ p.days_left }}d</span>
        {% else %}
        <span style="color:var(--amber)">closing next run</span>
        {% endif %}
      </td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
  </div>
  {% else %}
  <div class="empty">No open positions.</div>
  {% endif %}
</div>
{% endif %}

<!-- ── CLOSED TRADES ── -->
<div class="card" style="padding:0;overflow:hidden">
  <div style="padding:16px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;gap:10px;flex-wrap:wrap">
    <span class="section-pill closed-pill">Closed Trades · {{ stats.n_closed }}</span>
    {% if stats.n_closed == 0 %}
    <span style="font-size:12px;color:var(--text-2)">First close in ~{{ hold_days }} trading days from first signal</span>
    {% endif %}
  </div>
  {% if closed_trades %}
  <div style="overflow-x:auto">
  <table>
    <thead>
      <tr>
        <th class="left">Ticker</th>
        <th class="left mob-hide">Dir</th>
        <th class="left mob-hide">Entry Date</th>
        <th class="mob-hide">Exit Date</th>
        <th>Score</th>
        <th>Entry $</th>
        <th>Exit $</th>
        <th>P&L $</th>
        <th>P&L %</th>
      </tr>
    </thead>
    <tbody>
    {% for t in closed_trades %}
    <tr>
      <td><span class="status-dot closed"></span><span class="ticker-tag">{{ t.ticker }}</span></td>
      <td class="mob-hide"><span class="chip {{ t.direction }}">{{ '↑ LONG' if t.direction == 'long' else '↓ SHORT' }}</span></td>
      <td class="mono mob-hide" style="color:var(--text-2)">{{ t.signal_date }}</td>
      <td class="mono mob-hide" style="color:var(--text-2)">{{ t.exit_date }}</td>
      <td class="num" style="color:var(--amber)">{{ t.score }}</td>
      <td class="num">{{ '%.2f'|format(t.entry_price) }}</td>
      <td class="num">{{ '%.2f'|format(t.exit_price) }}</td>
      <td class="num">
        <span class="chip {{ 'up' if t.pnl >= 0 else 'down' }}">${{ '%+.2f'|format(t.pnl) }}</span>
      </td>
      <td class="num">
        <span class="chip {{ 'up' if t.pnl_pct >= 0 else 'down' }}">{{ '%+.2f'|format(t.pnl_pct) }}%</span>
      </td>
    </tr>
    {% endfor %}
    </tbody>
  </table>
  </div>

  <!-- P&L bar chart -->
  <div style="padding:12px 20px 16px;border-top:1px solid var(--border)">
    <div class="chart-label">Trade P&L (each bar = one closed trade)</div>
    {{ pnl_svg | safe }}
  </div>

  {% else %}
  <div class="empty">
    No closed trades yet. Positions auto-close after {{ hold_days }} trading days.<br>
    <span style="color:var(--muted)">First closures expected ~{{ first_close_date }}</span>
  </div>
  {% endif %}
</div>

<!-- ── HOW THIS WORKS ── -->
<div class="note-box">
  <strong style="color:var(--text)">How paper trading works:</strong><br>
  <span style="color:var(--up)">↑ LONG</span> — score ≥ {{ buy_threshold }}: simulates buying ${{ notional|int }} at that day's close. Profit when price rises over the next {{ hold_days }} trading days.<br>
  <span style="color:var(--down)">↓ SHORT</span> — score ≤ {{ sell_threshold }}: simulates shorting ${{ notional|int }} at that day's close. Profit when price falls over the next {{ hold_days }} trading days.<br>
  All positions close automatically at +{{ hold_days }} trading days. No real money, no commissions, no slippage.
  Purpose: test whether signal ≥ {{ buy_threshold }} reliably predicts up moves, and signal ≤ {{ sell_threshold }} reliably predicts down moves.
</div>

</div><!-- /.page -->
<div class="footer">SIGNAL MONITOR · PAPER TRADING · {{ date }}</div>
</body>
</html>
"""


# ── Render ─────────────────────────────────────────────────────────────────────

def _render_html(today_str: str, trades: list, calendar: list) -> str:
    stats = _build_stats(trades)
    curve = _build_equity_curve(trades)
    pnl_svg = _svg_pnl_bars(curve)

    # Open positions — enrich with float P&L and days metrics
    open_positions = []
    for t in sorted(
        [x for x in trades if x["status"] == "open"],
        key=lambda x: x["signal_date"],
    ):
        fp, fpc = _float_pnl(t)
        held = _days_elapsed(t["signal_date"], today_str, calendar)
        left = max(0, HOLD_DAYS - held)
        open_positions.append({
            **t,
            "float_pnl": fp,
            "float_pct": fpc,
            "days_held": held,
            "days_left": left,
        })

    # Closed trades — most recent first
    closed_trades = sorted(
        [x for x in trades if x["status"] == "closed"],
        key=lambda x: x.get("exit_date") or "",
        reverse=True,
    )

    # Estimate first close date for the empty-state message
    first_close_date = "—"
    open_sorted = sorted([x for x in trades if x["status"] == "open"],
                         key=lambda x: x["signal_date"])
    if open_sorted and calendar:
        candidate = _nth_trading_day_after(open_sorted[0]["signal_date"], HOLD_DAYS, calendar)
        if candidate:
            first_close_date = candidate

    return Template(PAPER_HTML).render(
        date=today_str,
        threshold=SIGNAL_THRESHOLD,
        buy_threshold=BUY_THRESHOLD,
        sell_threshold=SELL_THRESHOLD,
        notional=NOTIONAL,
        hold_days=HOLD_DAYS,
        stats=stats,
        open_positions=open_positions,
        closed_trades=closed_trades,
        pnl_svg=pnl_svg,
        first_close_date=first_close_date,
    )


# ── Entry point ────────────────────────────────────────────────────────────────

def run_paper_trading(
    today_str: str,
    today_scores: dict,       # {ticker: score} for today
    stock_results: list,      # today's full stock results (has live prices)
    output_dir: str = "outputs",
) -> str | None:
    """Run paper trading update and generate paper_trading.html.

    Returns the output path, or None on failure.
    """
    portfolio = _load_portfolio()
    trades: list = portfolio.get("trades", [])
    existing_ids = {t["id"] for t in trades}

    # Current price lookup from today's stock results (free — already fetched)
    price_map = {
        s["ticker"]: float(s["price"])
        for s in stock_results
        if s.get("price") and float(s["price"]) > 0
    }

    # ── 1. Open new positions ──────────────────────────────────────────────────
    new_count = 0

    def _open_trade(ticker: str, score: int, direction: str, entry_price: float) -> None:
        nonlocal new_count
        suffix = "" if direction == "long" else "-S"
        trade_id = f"{ticker}{suffix}-{today_str}"
        if trade_id in existing_ids:
            return
        shares = round(NOTIONAL / entry_price, 6)
        trades.append({
            "id":            trade_id,
            "ticker":        ticker,
            "direction":     direction,
            "signal_date":   today_str,
            "entry_price":   round(entry_price, 2),
            "shares":        shares,
            "notional":      NOTIONAL,
            "score":         score,
            "status":        "open",
            "exit_date":     None,
            "exit_price":    None,
            "current_price": round(entry_price, 2),
            "current_date":  today_str,
            "pnl":           None,
            "pnl_pct":       None,
        })
        new_count += 1

    for ticker, score in today_scores.items():
        entry_price = price_map.get(ticker)
        if not entry_price or entry_price <= 0:
            continue
        if score >= BUY_THRESHOLD:
            _open_trade(ticker, score, "long", entry_price)
        elif score <= SELL_THRESHOLD:
            _open_trade(ticker, score, "short", entry_price)

    if not trades:
        print("  [paper_trading] no trades yet — skipping")
        return None

    # ── 2. Trading calendar ────────────────────────────────────────────────────
    earliest = min(t["signal_date"] for t in trades)
    print(f"  [paper_trading] fetching trading calendar from {earliest}…")
    calendar = _fetch_calendar(earliest)

    # ── 3. Update floating prices ──────────────────────────────────────────────
    open_trades = [t for t in trades if t["status"] == "open"]
    for trade in open_trades:
        cp = price_map.get(trade["ticker"])
        if cp and cp > 0:
            trade["current_price"] = round(cp, 2)
            trade["current_date"] = today_str

    # ── 4. Identify positions ready to close ──────────────────────────────────
    need_hist: dict = {}   # {ticker: earliest_exit_date}
    to_close = []
    for trade in open_trades:
        elapsed = _days_elapsed(trade["signal_date"], today_str, calendar)
        if elapsed < HOLD_DAYS:
            continue
        exit_date = _nth_trading_day_after(trade["signal_date"], HOLD_DAYS, calendar)
        if not exit_date:
            continue
        to_close.append((trade, exit_date))
        if exit_date != today_str:
            ticker = trade["ticker"]
            if ticker not in need_hist or exit_date < need_hist[ticker]:
                need_hist[ticker] = exit_date

    # Bulk-fetch historical exit prices (one yfinance call per batch)
    hist_prices: dict = {}
    if need_hist:
        earliest_exit = min(need_hist.values())
        print(f"  [paper_trading] fetching historical exit prices for {list(need_hist.keys())}…")
        hist_prices = _fetch_prices_bulk(list(need_hist.keys()), earliest_exit)

    # ── 5. Close due positions ─────────────────────────────────────────────────
    for trade, exit_date in to_close:
        ticker = trade["ticker"]
        if exit_date == today_str:
            exit_price = price_map.get(ticker)
        else:
            series = hist_prices.get(ticker, {})
            exit_price = _get_exit_price(ticker, exit_date, series)

        if not exit_price or exit_price <= 0:
            continue

        ep = trade["entry_price"]
        if trade.get("direction", "long") == "short":
            # Short: profit when price falls (sold high, buy back low)
            pnl     = round((ep - exit_price) * trade["shares"], 2)
            pnl_pct = round((ep - exit_price) / ep * 100, 2)
        else:
            pnl     = round((exit_price - ep) * trade["shares"], 2)
            pnl_pct = round((exit_price - ep) / ep * 100, 2)
        trade.update({
            "status":     "closed",
            "exit_date":  exit_date,
            "exit_price": round(exit_price, 2),
            "pnl":        pnl,
            "pnl_pct":    pnl_pct,
        })

    portfolio["trades"] = trades
    portfolio["last_updated"] = today_str
    _save_portfolio(portfolio)

    # ── 6. Render HTML ─────────────────────────────────────────────────────────
    html = _render_html(today_str, trades, calendar)
    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "paper_trading.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    n_open   = sum(1 for t in trades if t["status"] == "open")
    n_closed = sum(1 for t in trades if t["status"] == "closed")
    print(f"  [paper_trading] → {out_path}  "
          f"(new={new_count}, open={n_open}, closed={n_closed})")
    return out_path
