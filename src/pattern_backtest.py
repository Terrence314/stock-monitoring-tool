"""pattern_backtest.py — Per-pattern forward-return backtest.

Reads outputs/pattern_events.json (start events only), fetches 2y of close prices,
measures +5 / +10 / +20 trading-day returns for each named pattern.
Ranks patterns by +10d win-rate so you can see which signals are most reliable.

Output: outputs/pattern_backtest.html
"""

import os
import json
from datetime import datetime
import yfinance as yf
from jinja2 import Template

PATTERN_EVENTS_FILE = os.path.join("outputs", "pattern_events.json")
FORWARD_DAYS        = [5, 10, 20]


# ── Data helpers ──────────────────────────────────────────────────────────────

def _load_events() -> list:
    try:
        with open(PATTERN_EVENTS_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _fetch_price_series(tickers: list[str]) -> dict[str, dict[str, float]]:
    """Bulk-download 2y of daily close prices. Returns {ticker: {date_str: price}}."""
    if not tickers:
        return {}

    def _to_date_str(ts) -> str:
        if hasattr(ts, "date"):
            return str(ts.date())
        return str(ts)[:10]

    raw = yf.download(
        tickers, period="2y",
        auto_adjust=True, progress=False, threads=True,
    )
    prices: dict[str, dict[str, float]] = {}

    if len(tickers) == 1:
        t = tickers[0]
        if "Close" in raw.columns:
            prices[t] = {
                _to_date_str(ts): float(v)
                for ts, v in raw["Close"].dropna().items()
            }
    else:
        close = raw.get("Close", raw)
        for t in tickers:
            if t in close.columns:
                prices[t] = {
                    _to_date_str(ts): float(v)
                    for ts, v in close[t].dropna().items()
                }
    return prices


# ── Core backtest logic ───────────────────────────────────────────────────────

def _compute_forward_returns(
    start_events: list,
    price_series: dict[str, dict[str, float]],
) -> list[dict]:
    """For each 'start' event, compute forward returns at +5/+10/+20 trading days."""
    results = []
    for event in start_events:
        ticker   = event["ticker"]
        date_str = event["date"]
        series   = price_series.get(ticker)
        if not series:
            continue
        all_dates = sorted(series.keys())
        if date_str not in series:
            future = [d for d in all_dates if d >= date_str]
            if not future:
                continue
            entry_date = future[0]
        else:
            entry_date = date_str

        entry_idx   = all_dates.index(entry_date)
        entry_price = series[entry_date]
        if entry_price <= 0:
            continue

        forward: dict = {}
        for fd in FORWARD_DAYS:
            target_idx = entry_idx + fd
            if target_idx < len(all_dates):
                exit_price = series[all_dates[target_idx]]
                forward[f"r{fd}"] = round((exit_price - entry_price) / entry_price * 100, 2)
            else:
                forward[f"r{fd}"] = None

        results.append({
            "pattern":    event["pattern"],
            "direction":  event["direction"],
            "ticker":     ticker,
            "date":       date_str,
            "entry_date": entry_date,
            "entry_price": round(entry_price, 2),
            **forward,
        })
    return results


def _stats_for(rows: list[dict], fd: int) -> dict:
    key  = f"r{fd}"
    vals = [r[key] for r in rows if r.get(key) is not None]
    if not vals:
        return {"n": 0, "win_rate": None, "avg": None, "median": None}
    wins = sum(1 for v in vals if v > 0)
    sv   = sorted(vals)
    mid  = len(sv) // 2
    med  = (sv[mid - 1] + sv[mid]) / 2 if len(sv) % 2 == 0 else sv[mid]
    return {
        "n":        len(vals),
        "win_rate": round(wins / len(vals) * 100, 1),
        "avg":      round(sum(vals) / len(vals), 2),
        "median":   round(med, 2),
    }


def _aggregate_by_pattern(results: list[dict]) -> list[dict]:
    """Return per-pattern stats sorted by +10d win rate descending."""
    pattern_names = sorted({r["pattern"] for r in results})
    rows = []
    for name in pattern_names:
        group     = [r for r in results if r["pattern"] == name]
        direction = group[0]["direction"] if group else "buy"
        stats = {fd: _stats_for(group, fd) for fd in FORWARD_DAYS}
        sort_key = stats[10]["win_rate"] or 0
        rows.append({
            "pattern":    name,
            "direction":  direction,
            "n_signals":  len(group),
            "stats":      stats,
            "_sort_key":  sort_key,
        })
    rows.sort(key=lambda r: r["_sort_key"], reverse=True)
    return rows


# ── HTML template ─────────────────────────────────────────────────────────────

PATTERN_BT_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Pattern Backtest · {{ date }}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --bg:#0b0c10; --surface:#13141b; --elevated:#1a1c25; --border:#23252f;
  --border-hi:#33363f; --text:#e7e8ec; --text-2:#8a8c98; --muted:#52545e;
  --up:#34d399; --down:#f87171; --amber:#f5b942; --blue:#7aa2ff; --purple:#b18cff;
  --mono:'JetBrains Mono',monospace; --sans:'Inter',system-ui,sans-serif;
}
*, *::before, *::after { box-sizing:border-box; margin:0; padding:0; }
body { background:var(--bg); color:var(--text); font-family:var(--sans);
  font-size:13px; line-height:1.55; min-height:100vh; -webkit-font-smoothing:antialiased; }
.top { position:sticky; top:0; z-index:50; background:var(--surface);
  border-bottom:1px solid var(--border); backdrop-filter:blur(12px); }
.top-row { display:flex; align-items:center; gap:16px; padding:0 24px; height:56px; }
.brand-logo { width:26px; height:26px; border-radius:7px;
  background:linear-gradient(135deg,var(--amber),var(--purple));
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
.pill-amber { background:rgba(245,185,66,0.10); color:var(--amber); border:1px solid rgba(245,185,66,0.25); }
.pill-blue  { background:rgba(122,162,255,0.10); color:var(--blue);  border:1px solid rgba(122,162,255,0.25); }
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
.chip.buy  { color:var(--up);   background:rgba(52,211,153,0.08); border:1px solid rgba(52,211,153,0.2); font-size:10px; }
.chip.sell { color:var(--down); background:rgba(248,113,113,0.08); border:1px solid rgba(248,113,113,0.2); font-size:10px; }
.pattern-name { font-weight:600; font-size:13px; }
.wr-bar { height:5px; border-radius:3px; background:var(--elevated); margin-top:4px; width:80px; }
.wr-fill { height:100%; border-radius:3px; }
.signal-row td:first-child { padding-left:16px; }
.empty { padding:40px; text-align:center; font-family:var(--mono);
  font-size:12px; color:var(--text-2); }
.footer { text-align:center; padding:24px; color:var(--muted);
  font-family:var(--mono); font-size:10px; letter-spacing:0.06em; }
@media(max-width:768px){ .page{padding:12px 12px 40px;} .mob-hide{display:none!important;} }
</style>
</head>
<body>

<header class="top">
  <div class="top-row">
    <div class="brand-logo">P</div>
    <div>
      <div class="brand-title">Pattern Backtest</div>
      <div class="brand-sub">generated {{ date }} · {{ n_events }} signal events · {{ n_patterns }} patterns</div>
    </div>
    <a href="./index.html" class="back-btn">← 返回總覽</a>
  </div>
</header>

<div class="page">

{% if not pattern_rows %}
<div class="card">
  <div class="empty">
    No pattern events recorded yet.<br>
    Pattern history builds up as the daily pipeline runs. Check back after a few days.
  </div>
</div>
{% else %}

<!-- Pattern summary table -->
<div class="card" style="padding:0;overflow:hidden">
  <div style="padding:16px 20px;border-bottom:1px solid var(--border)">
    <span class="section-pill pill-amber">Pattern Performance · ranked by +10d win rate</span>
    <div style="font-size:12px;color:var(--text-2)">
      Each row = one named pattern · forward returns measured from pattern start date
    </div>
  </div>
  <div style="overflow-x:auto">
  <table>
    <thead>
      <tr>
        <th class="left">Pattern</th>
        <th class="left">Dir</th>
        <th>Signals</th>
        <th>+5d win%</th>
        <th>+5d avg</th>
        <th class="mob-hide">+10d win%</th>
        <th class="mob-hide">+10d avg</th>
        <th>+20d win%</th>
        <th>+20d avg</th>
      </tr>
    </thead>
    <tbody>
    {% for row in pattern_rows %}
    <tr>
      <td class="pattern-name">{{ row.pattern }}</td>
      <td>
        <span class="chip {{ row.direction }}">{{ '🟢 BUY' if row.direction == 'buy' else '🔴 SELL' }}</span>
      </td>
      <td class="num">{{ row.n_signals }}</td>

      {% for fd_key, s in [(5, row.stats[5]), (10, row.stats[10]), (20, row.stats[20])] %}
      <td class="num {% if fd_key == 10 %}mob-hide{% endif %}">
        {% if s.win_rate is not none %}
        <div style="font-family:var(--mono);font-size:11px;color:{{ 'var(--up)' if s.win_rate >= 55 else ('var(--amber)' if s.win_rate >= 45 else 'var(--down)') }}">
          {{ s.win_rate }}%
        </div>
        <div class="wr-bar">
          <div class="wr-fill" style="width:{{ s.win_rate }}%;background:{{ '#34d399' if s.win_rate >= 55 else ('#f5b942' if s.win_rate >= 45 else '#f87171') }}"></div>
        </div>
        {% else %}<span class="chip na">—</span>{% endif %}
      </td>
      <td class="num {% if fd_key == 10 %}mob-hide{% endif %}">
        {% if s.avg is not none %}
        <span class="chip {{ 'up' if s.avg >= 0 else 'down' }}">{{ '%+.1f'|format(s.avg) }}%</span>
        {% else %}<span class="chip na">—</span>{% endif %}
      </td>
      {% endfor %}
    </tr>
    {% endfor %}
    </tbody>
  </table>
  </div>
</div>

<!-- Full signal log -->
<div class="card" style="padding:0;overflow:hidden">
  <div style="padding:16px 20px;border-bottom:1px solid var(--border)">
    <span class="section-pill pill-blue">Full Signal Log · most recent first</span>
  </div>
  <div style="overflow-x:auto">
  <table>
    <thead>
      <tr>
        <th class="left">Date</th>
        <th class="left">Ticker</th>
        <th class="left">Pattern</th>
        <th class="left mob-hide">Dir</th>
        <th>Entry $</th>
        <th>+5d</th>
        <th class="mob-hide">+10d</th>
        <th>+20d</th>
      </tr>
    </thead>
    <tbody>
    {% for r in signal_log %}
    <tr class="signal-row">
      <td class="mono" style="color:var(--text-2)">{{ r.date }}</td>
      <td><span style="font-family:var(--mono);font-size:11px;font-weight:700;
        background:var(--elevated);border:1px solid var(--border-hi);
        padding:2px 7px;border-radius:4px">{{ r.ticker }}</span></td>
      <td style="font-size:12px">{{ r.pattern }}</td>
      <td class="mob-hide">
        <span class="chip {{ r.direction }}">{{ '🟢' if r.direction == 'buy' else '🔴' }}</span>
      </td>
      <td class="num">${{ '%.2f'|format(r.entry_price) }}</td>
      {% for fd, key in [(5,'r5'),(10,'r10'),(20,'r20')] %}
      <td class="num {% if fd == 10 %}mob-hide{% endif %}">
        {% set v = r[key] %}
        {% if v is not none %}
        <span class="chip {{ 'up' if v >= 0 else 'down' }}">{{ '%+.2f'|format(v) }}%</span>
        {% else %}<span class="chip na">—</span>{% endif %}
      </td>
      {% endfor %}
    </tr>
    {% endfor %}
    </tbody>
  </table>
  </div>
</div>

{% endif %}

</div>
<div class="footer">SIGNAL MONITOR · PATTERN BACKTEST · {{ date }}</div>
</body>
</html>
"""


# ── Entry point ───────────────────────────────────────────────────────────────

def run_pattern_backtest(output_dir: str = "outputs") -> str | None:
    """Run per-pattern backtest and write outputs/pattern_backtest.html.

    Returns output path or None if no events exist yet.
    """
    events = _load_events()
    start_events = [e for e in events if e.get("type") == "start"]

    if not start_events:
        print("  [pattern_backtest] no start events yet — skipping")
        return None

    tickers = sorted({e["ticker"] for e in start_events})
    print(f"  [pattern_backtest] fetching 2y prices for {len(tickers)} tickers…")
    price_series = _fetch_price_series(tickers)

    results = _compute_forward_returns(start_events, price_series)
    if not results:
        print("  [pattern_backtest] no forward price data available yet")
        return None

    pattern_rows = _aggregate_by_pattern(results)
    signal_log   = sorted(results, key=lambda r: r["date"], reverse=True)

    # Rename dict keys for Jinja (r5, r10, r20)
    for r in signal_log:
        r["r5"]  = r.get("r5")
        r["r10"] = r.get("r10")
        r["r20"] = r.get("r20")

    today_str = datetime.now().strftime("%Y/%m/%d")
    html = Template(PATTERN_BT_HTML).render(
        date=today_str,
        n_events=len(start_events),
        n_patterns=len(pattern_rows),
        pattern_rows=pattern_rows,
        signal_log=signal_log,
    )

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "pattern_backtest.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  [pattern_backtest] → {out_path}  ({len(results)} results, {len(pattern_rows)} patterns)")
    return out_path
