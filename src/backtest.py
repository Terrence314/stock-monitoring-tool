"""backtest.py — Signal score backtesting module.

For each historical date where a ticker's signal score reached ≥ THRESHOLD,
measures forward price returns at +5, +10, and +20 trading days.

Called from main.py after the daily run completes.
Output: outputs/backtest.html
"""

import os
import json
from datetime import datetime
import yfinance as yf
from jinja2 import Template


SCORE_HISTORY_FILE = os.path.join("outputs", "score_history.json")
SIGNAL_THRESHOLD   = 70
FORWARD_DAYS       = [5, 10, 20]


# ── Data helpers ───────────────────────────────────────────────────────────────

def _load_score_history() -> dict:
    try:
        with open(SCORE_HISTORY_FILE, encoding="utf-8") as f:
            return json.load(f)
    except (FileNotFoundError, json.JSONDecodeError):
        return {}


def _fetch_price_series(tickers: list[str]) -> dict[str, dict[str, float]]:
    """Download 2y of daily close prices for all tickers.

    Returns {ticker: {date_str: close_price}}.
    """
    if not tickers:
        return {}
    raw = yf.download(
        tickers,
        period="2y",
        auto_adjust=True,
        progress=False,
        threads=True,
    )
    prices: dict[str, dict[str, float]] = {}

    if len(tickers) == 1:
        # Single ticker: raw is a flat DataFrame with Close column
        ticker = tickers[0]
        if "Close" in raw.columns:
            prices[ticker] = {
                str(ts.date()): float(v)
                for ts, v in raw["Close"].dropna().items()
            }
    else:
        close = raw.get("Close", raw)
        for ticker in tickers:
            if ticker in close.columns:
                prices[ticker] = {
                    str(ts.date()): float(v)
                    for ts, v in close[ticker].dropna().items()
                }
    return prices


# ── Core backtest logic ────────────────────────────────────────────────────────

def _run_signals(
    score_history: dict,
    price_series: dict[str, dict[str, float]],
) -> list[dict]:
    """Enumerate every (date, ticker) where score ≥ THRESHOLD and compute forward returns."""
    results = []
    sorted_dates = sorted(score_history.keys())

    for date_str in sorted_dates:
        day_scores = score_history[date_str]
        for ticker, score in day_scores.items():
            if score < SIGNAL_THRESHOLD:
                continue
            series = price_series.get(ticker)
            if not series:
                continue
            all_dates = sorted(series.keys())

            # Find entry date index
            if date_str not in series:
                # Use the next available trading date
                future = [d for d in all_dates if d >= date_str]
                if not future:
                    continue
                entry_date = future[0]
            else:
                entry_date = date_str

            entry_idx = all_dates.index(entry_date)
            entry_price = series[entry_date]
            if entry_price <= 0:
                continue

            forward: dict[str, float | None] = {}
            for fd in FORWARD_DAYS:
                target_idx = entry_idx + fd
                if target_idx < len(all_dates):
                    exit_price = series[all_dates[target_idx]]
                    forward[f"r{fd}"] = round((exit_price - entry_price) / entry_price * 100, 2)
                else:
                    forward[f"r{fd}"] = None

            results.append({
                "ticker":       ticker,
                "signal_date":  date_str,
                "entry_date":   entry_date,
                "entry_price":  round(entry_price, 2),
                "score":        score,
                **forward,
            })

    return results


def _aggregate(signals: list[dict]) -> dict:
    """Compute overall and per-ticker stats from signal results."""
    if not signals:
        return {"overall": {}, "by_ticker": {}}

    def stats_for(rows: list[dict], fd: int) -> dict:
        key = f"r{fd}"
        vals = [r[key] for r in rows if r.get(key) is not None]
        if not vals:
            return {"n": 0, "win_rate": None, "avg": None, "median": None}
        wins = sum(1 for v in vals if v > 0)
        sorted_v = sorted(vals)
        mid = len(sorted_v) // 2
        median = (sorted_v[mid - 1] + sorted_v[mid]) / 2 if len(sorted_v) % 2 == 0 else sorted_v[mid]
        return {
            "n":        len(vals),
            "win_rate": round(wins / len(vals) * 100, 1),
            "avg":      round(sum(vals) / len(vals), 2),
            "median":   round(median, 2),
        }

    overall = {fd: stats_for(signals, fd) for fd in FORWARD_DAYS}

    by_ticker: dict[str, dict] = {}
    tickers = sorted({r["ticker"] for r in signals})
    for ticker in tickers:
        rows = [r for r in signals if r["ticker"] == ticker]
        by_ticker[ticker] = {
            "n_signals": len(rows),
            **{fd: stats_for(rows, fd) for fd in FORWARD_DAYS},
        }

    return {"overall": overall, "by_ticker": by_ticker}


# ── HTML Template ──────────────────────────────────────────────────────────────

BACKTEST_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Signal Backtest · {{ date }}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700&family=JetBrains+Mono:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
:root {
  --bg:#0b0c10; --surface:#13141b; --elevated:#1a1c25; --border:#23252f;
  --border-hi:#33363f; --text:#e7e8ec; --text-2:#8a8c98; --muted:#52545e;
  --up:#34d399; --down:#f87171; --amber:#f5b942; --blue:#7aa2ff; --purple:#b18cff;
  --mono:'JetBrains Mono',monospace; --sans:'Inter',system-ui,sans-serif;
}
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
body { background:var(--bg); color:var(--text); font-family:var(--sans);
  font-size:13px; line-height:1.55; min-height:100vh;
  -webkit-font-smoothing:antialiased; }
.top { position:sticky; top:0; z-index:50; background:var(--surface);
  border-bottom:1px solid var(--border); backdrop-filter:blur(12px); }
.top-row { display:flex; align-items:center; gap:16px; padding:0 24px; height:56px; }
.brand-logo { width:26px; height:26px; border-radius:7px;
  background:linear-gradient(135deg,var(--blue),var(--purple));
  display:flex; align-items:center; justify-content:center;
  color:#fff; font-weight:700; font-size:13px; font-family:var(--mono); }
.brand-title { font-size:14px; font-weight:600; }
.brand-sub { font-family:var(--mono); font-size:10px; color:var(--text-2); }
.back-btn { margin-left:auto; font-family:var(--mono); font-size:11px;
  color:var(--blue); text-decoration:none; padding:5px 10px;
  border:1px solid rgba(122,162,255,0.3); border-radius:6px; }
.back-btn:hover { background:rgba(122,162,255,0.08); }
.page { max-width:1100px; margin:0 auto; padding:20px 24px 60px;
  display:flex; flex-direction:column; gap:16px; }
.card { background:var(--surface); border:1px solid var(--border);
  border-radius:12px; padding:18px 20px; }
.card-title { font-size:14px; font-weight:600; letter-spacing:-0.005em; }
.card-sub { font-size:11px; color:var(--text-2); }
.section-pill {
  display:inline-flex; align-items:center; justify-content:center;
  font-family:var(--mono); font-size:9px; font-weight:700;
  letter-spacing:0.06em; text-transform:uppercase;
  padding:3px 9px; border-radius:10px;
  background:rgba(122,162,255,0.10); color:var(--blue);
  border:1px solid rgba(122,162,255,0.25); margin-bottom:14px;
}
.stat-grid { display:grid; grid-template-columns:repeat(3,1fr); gap:10px; }
@media (max-width:700px) { .stat-grid { grid-template-columns:1fr 1fr; } }
.stat-box { background:var(--elevated); border:1px solid var(--border);
  border-radius:10px; padding:14px 16px; }
.stat-label { font-size:11px; color:var(--text-2); font-weight:500; }
.stat-val { font-family:var(--mono); font-size:22px; font-weight:700;
  letter-spacing:-0.02em; margin-top:6px; }
.stat-sub { font-family:var(--mono); font-size:10px; color:var(--text-2); margin-top:2px; }
.stat-val.up { color:var(--up); }
.stat-val.down { color:var(--down); }
.stat-val.amber { color:var(--amber); }
.fd-row { display:grid; grid-template-columns:repeat(3,1fr); gap:12px; margin-top:14px; }
@media (max-width:700px) { .fd-row { grid-template-columns:1fr; } }
.fd-card { background:var(--bg); border:1px solid var(--border); border-radius:10px;
  padding:14px 16px; }
.fd-label { font-family:var(--mono); font-size:10px; font-weight:700;
  color:var(--text-2); text-transform:uppercase; letter-spacing:0.06em; margin-bottom:10px; }
.fd-metric { display:flex; justify-content:space-between; align-items:center;
  padding:5px 0; border-bottom:1px solid var(--border); }
.fd-metric:last-child { border-bottom:none; }
.fd-metric-label { font-size:12px; color:var(--text-2); }
.fd-metric-val { font-family:var(--mono); font-size:12px; font-weight:600; }
tbl { width:100%; border-collapse:collapse; }
table { width:100%; border-collapse:collapse; }
thead tr { background:var(--bg); }
th { padding:9px 12px; font-size:11px; font-weight:500; color:var(--text-2);
  text-align:right; border-bottom:1px solid var(--border); white-space:nowrap; }
th.first { text-align:left; }
td { padding:11px 12px; border-bottom:1px solid var(--border);
  vertical-align:middle; }
tbody tr:last-child td { border-bottom:none; }
tbody tr:hover td { background:rgba(255,255,255,0.02); }
.mono { font-family:var(--mono); font-size:12px; }
.num { font-family:var(--mono); font-size:12px; text-align:right; }
.chip { font-family:var(--mono); font-size:11px; font-weight:600;
  padding:2px 8px; border-radius:4px; display:inline-block; }
.chip.up   { color:var(--up);   background:rgba(52,211,153,0.10); }
.chip.down { color:var(--down); background:rgba(248,113,113,0.10); }
.chip.na   { color:var(--muted); background:rgba(255,255,255,0.03); }
.ticker-tag { font-family:var(--mono); font-size:11px; font-weight:700; color:var(--text);
  background:var(--elevated); border:1px solid var(--border-hi);
  padding:2px 8px; border-radius:4px; }
.wr-bar { height:4px; border-radius:2px; background:var(--elevated); margin-top:4px; }
.wr-fill { height:100%; border-radius:2px; }
.empty { padding:40px; text-align:center; font-family:var(--mono);
  font-size:12px; color:var(--text-2); }
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
    <div class="brand-logo">S</div>
    <div>
      <div class="brand-title">Backtest · Signal ≥ {{ threshold }}</div>
      <div class="brand-sub">generated {{ date }} · {{ n_signals }} signal events · {{ n_tickers }} tickers</div>
    </div>
    <a href="./index.html" class="back-btn">← 返回總覽</a>
  </div>
</header>

<div class="page">

{% if not signals %}
<div class="card">
  <div class="empty">
    No signals with score ≥ {{ threshold }} in history yet.<br>
    Run the pipeline a few days with active signals to build a backtest dataset.
  </div>
</div>
{% else %}

<!-- ── OVERALL SUMMARY ── -->
<div class="card">
  <span class="section-pill">Overall Performance</span>
  <div style="display:flex;align-items:baseline;justify-content:space-between;flex-wrap:wrap;gap:8px;margin-bottom:16px">
    <div>
      <div class="card-title">{{ n_signals }} Signal Events · Score ≥ {{ threshold }}</div>
      <div class="card-sub" style="margin-top:3px">{{ n_tickers }} tickers · dates from {{ date_range }}</div>
    </div>
  </div>

  <div class="fd-row">
    {% for fd in forward_days %}
    {% set s = overall[fd] %}
    <div class="fd-card">
      <div class="fd-label">+{{ fd }} Trading Days</div>
      {% if s.n > 0 %}
      <div class="fd-metric">
        <span class="fd-metric-label">Signals</span>
        <span class="fd-metric-val" style="color:var(--text)">{{ s.n }}</span>
      </div>
      <div class="fd-metric">
        <span class="fd-metric-label">Win rate</span>
        <span class="fd-metric-val" style="color:{{ 'var(--up)' if s.win_rate >= 55 else ('var(--amber)' if s.win_rate >= 45 else 'var(--down)') }}">{{ s.win_rate }}%</span>
      </div>
      <div class="fd-metric">
        <span class="fd-metric-label">Avg return</span>
        <span class="fd-metric-val" style="color:{{ 'var(--up)' if s.avg >= 0 else 'var(--down)' }}">{{ '%+.2f'|format(s.avg) }}%</span>
      </div>
      <div class="fd-metric">
        <span class="fd-metric-label">Median return</span>
        <span class="fd-metric-val" style="color:{{ 'var(--up)' if s.median >= 0 else 'var(--down)' }}">{{ '%+.2f'|format(s.median) }}%</span>
      </div>
      {% else %}
      <div style="color:var(--muted);font-family:var(--mono);font-size:11px">Insufficient data</div>
      {% endif %}
    </div>
    {% endfor %}
  </div>
</div>

<!-- ── PER-TICKER SUMMARY ── -->
<div class="card" style="padding:0;overflow:hidden">
  <div style="padding:16px 20px;border-bottom:1px solid var(--border);display:flex;align-items:center;justify-content:space-between">
    <div>
      <div class="card-title">Per-Ticker Statistics</div>
      <div class="card-sub" style="margin-top:3px">sorted by +10d win rate</div>
    </div>
  </div>
  <div style="overflow-x:auto">
  <table>
    <thead>
      <tr>
        <th class="first">Ticker</th>
        <th class="first">Signals</th>
        <th>+5d win%</th>
        <th>+5d avg</th>
        <th class="mob-hide">+10d win%</th>
        <th class="mob-hide">+10d avg</th>
        <th>+20d win%</th>
        <th>+20d avg</th>
      </tr>
    </thead>
    <tbody>
      {% for row in ticker_rows %}
      <tr>
        <td><span class="ticker-tag">{{ row.ticker }}</span></td>
        <td class="num">{{ row.n_signals }}</td>
        <td class="num">
          {% if row.r5.win_rate is not none %}
          <span style="font-family:var(--mono);font-size:11px;color:{{ 'var(--up)' if row.r5.win_rate >= 55 else ('var(--amber)' if row.r5.win_rate >= 45 else 'var(--down)') }}">{{ row.r5.win_rate }}%</span>
          {% else %}<span class="chip na">—</span>{% endif %}
        </td>
        <td class="num">
          {% if row.r5.avg is not none %}
          <span class="chip {{ 'up' if row.r5.avg >= 0 else 'down' }}">{{ '%+.1f'|format(row.r5.avg) }}%</span>
          {% else %}<span class="chip na">—</span>{% endif %}
        </td>
        <td class="num mob-hide">
          {% if row.r10.win_rate is not none %}
          <span style="font-family:var(--mono);font-size:11px;color:{{ 'var(--up)' if row.r10.win_rate >= 55 else ('var(--amber)' if row.r10.win_rate >= 45 else 'var(--down)') }}">{{ row.r10.win_rate }}%</span>
          {% else %}<span class="chip na">—</span>{% endif %}
        </td>
        <td class="num mob-hide">
          {% if row.r10.avg is not none %}
          <span class="chip {{ 'up' if row.r10.avg >= 0 else 'down' }}">{{ '%+.1f'|format(row.r10.avg) }}%</span>
          {% else %}<span class="chip na">—</span>{% endif %}
        </td>
        <td class="num">
          {% if row.r20.win_rate is not none %}
          <span style="font-family:var(--mono);font-size:11px;color:{{ 'var(--up)' if row.r20.win_rate >= 55 else ('var(--amber)' if row.r20.win_rate >= 45 else 'var(--down)') }}">{{ row.r20.win_rate }}%</span>
          {% else %}<span class="chip na">—</span>{% endif %}
        </td>
        <td class="num">
          {% if row.r20.avg is not none %}
          <span class="chip {{ 'up' if row.r20.avg >= 0 else 'down' }}">{{ '%+.1f'|format(row.r20.avg) }}%</span>
          {% else %}<span class="chip na">—</span>{% endif %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  </div>
</div>

<!-- ── SIGNAL LOG ── -->
<div class="card" style="padding:0;overflow:hidden">
  <div style="padding:16px 20px;border-bottom:1px solid var(--border)">
    <div class="card-title">Signal Log</div>
    <div class="card-sub" style="margin-top:3px">all events · most recent first</div>
  </div>
  <div style="overflow-x:auto">
  <table>
    <thead>
      <tr>
        <th class="first">Signal date</th>
        <th class="first">Ticker</th>
        <th>Score</th>
        <th>Entry $</th>
        <th>+5d</th>
        <th class="mob-hide">+10d</th>
        <th>+20d</th>
      </tr>
    </thead>
    <tbody>
      {% for row in signals | sort(attribute='signal_date', reverse=True) %}
      <tr>
        <td class="mono" style="color:var(--text-2)">{{ row.signal_date }}</td>
        <td><span class="ticker-tag">{{ row.ticker }}</span></td>
        <td class="num" style="color:var(--amber)">{{ row.score }}</td>
        <td class="num">{{ '%.2f'|format(row.entry_price) }}</td>
        <td class="num">
          {% if row.r5 is not none %}
          <span class="chip {{ 'up' if row.r5 >= 0 else 'down' }}">{{ '%+.2f'|format(row.r5) }}%</span>
          {% else %}<span class="chip na">—</span>{% endif %}
        </td>
        <td class="num mob-hide">
          {% if row.r10 is not none %}
          <span class="chip {{ 'up' if row.r10 >= 0 else 'down' }}">{{ '%+.2f'|format(row.r10) }}%</span>
          {% else %}<span class="chip na">—</span>{% endif %}
        </td>
        <td class="num">
          {% if row.r20 is not none %}
          <span class="chip {{ 'up' if row.r20 >= 0 else 'down' }}">{{ '%+.2f'|format(row.r20) }}%</span>
          {% else %}<span class="chip na">—</span>{% endif %}
        </td>
      </tr>
      {% endfor %}
    </tbody>
  </table>
  </div>
</div>

{% endif %}

</div><!-- /.page -->
<div class="footer">SIGNAL MONITOR · BACKTEST ENGINE · {{ date }}</div>
</body>
</html>
"""


# ── Entry point ────────────────────────────────────────────────────────────────

def run_backtest(tickers: list[str], output_dir: str = "outputs") -> str | None:
    """Run the full backtest pipeline and write outputs/backtest.html.

    Returns the output path, or None if no score history exists yet.
    """
    score_history = _load_score_history()
    if not score_history:
        print("  [backtest] no score_history.json — skipping")
        return None

    # Collect all tickers that have ever scored ≥ THRESHOLD
    signal_tickers: set[str] = set()
    for day_scores in score_history.values():
        for ticker, score in day_scores.items():
            if score >= SIGNAL_THRESHOLD:
                signal_tickers.add(ticker)

    if not signal_tickers:
        print(f"  [backtest] no signals ≥ {SIGNAL_THRESHOLD} in history — skipping")
        return None

    print(f"  [backtest] fetching 2y price history for {len(signal_tickers)} tickers…")
    price_series = _fetch_price_series(sorted(signal_tickers))

    signals = _run_signals(score_history, price_series)
    if not signals:
        print("  [backtest] no valid signal events with forward price data")
        return None

    agg = _aggregate(signals)
    overall_raw = agg["overall"]
    by_ticker = agg["by_ticker"]

    # Sort ticker rows by +10d win_rate descending
    ticker_rows = []
    for ticker, stats in by_ticker.items():
        r10_wr = (stats[10]["win_rate"] or 0) if stats[10]["n"] > 0 else 0
        ticker_rows.append({
            "ticker":    ticker,
            "n_signals": stats["n_signals"],
            "r5":        stats[5],
            "r10":       stats[10],
            "r20":       stats[20],
            "_sort_key": r10_wr,
        })
    ticker_rows.sort(key=lambda r: r["_sort_key"], reverse=True)

    # Date range string
    all_signal_dates = sorted({r["signal_date"] for r in signals})
    date_range = f"{all_signal_dates[0]} → {all_signal_dates[-1]}" if all_signal_dates else "—"

    today_str = datetime.now().strftime("%Y/%m/%d")
    html = Template(BACKTEST_HTML).render(
        date=today_str,
        threshold=SIGNAL_THRESHOLD,
        forward_days=FORWARD_DAYS,
        n_signals=len(signals),
        n_tickers=len(by_ticker),
        date_range=date_range,
        overall=overall_raw,
        ticker_rows=ticker_rows,
        signals=signals,
    )

    os.makedirs(output_dir, exist_ok=True)
    out_path = os.path.join(output_dir, "backtest.html")
    with open(out_path, "w", encoding="utf-8") as f:
        f.write(html)

    print(f"  [backtest] → {out_path}  ({len(signals)} events, {len(by_ticker)} tickers)")
    return out_path
