"""portfolio_report.py — Local-only IBKR portfolio dashboard.

Generates outputs/portfolio.html and opens it in the browser.
NEVER committed or deployed — outputs/ is gitignored.

Usage:
    python3 src/portfolio_report.py

Reads:
    outputs/ibkr_positions.json   — from ibkr_sync.py
    outputs/last_analysis.json    — from daily pipeline
"""
import json
import os
import webbrowser
from datetime import datetime

POSITIONS_FILE = os.path.join("outputs", "ibkr_positions.json")
ANALYSIS_FILE  = os.path.join("outputs", "last_analysis.json")
OUTPUT_FILE    = os.path.join("outputs", "portfolio.html")


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _score_color(score):
    if score >= 70: return "#34d399"
    if score >= 50: return "#f5b942"
    if score >= 30: return "#fb923c"
    return "#f87171"


def _pnl_color(v):
    return "#34d399" if v >= 0 else "#f87171"


def _fmt_pnl(v):
    return f"+${v:,.2f}" if v >= 0 else f"-${abs(v):,.2f}"


def build_html(positions: list, account: dict, sig_map: dict, synced_at: str, analysis_date: str) -> str:
    total_upnl  = sum(p.get("unrealized_pnl", 0) for p in positions)
    total_dpnl  = sum(p.get("daily_pnl", 0) for p in positions)
    total_mktval = sum(p.get("market_value", 0) for p in positions)
    net_liq     = account.get("net_liquidation", 0)
    buying_pow  = account.get("buying_power", 0)
    currency    = account.get("currency", "HKD")

    cards_html = ""
    for p in sorted(positions, key=lambda x: x.get("unrealized_pnl", 0), reverse=True):
        ticker  = p.get("ticker", "")
        qty     = p.get("qty", 0)
        avg     = p.get("avg_cost", 0)
        price   = p.get("market_price", 0)
        upnl    = p.get("unrealized_pnl", 0)
        dpnl    = p.get("daily_pnl", 0)
        mktval  = p.get("market_value", 0)
        cur     = p.get("currency", "USD")
        cost_b  = avg * qty
        upnl_pct = (upnl / cost_b * 100) if cost_b else 0

        sig = sig_map.get(ticker, {})
        score    = sig.get("score", 0)
        strength = sig.get("strength", "—")
        macd     = sig.get("macd") or 0
        signals  = sig.get("signals", [])
        sell_sigs = sig.get("sell_signals", [])
        macd_zone = "0軸以上 ✅" if macd > 0 else "0軸以下 ⚠️"
        macd_zone_color = "#34d399" if macd > 0 else "#fb923c"

        # Risk status
        bearish_sigs = [s for s in signals if any(w in s for w in ["❌", "🔴", "死叉", "跌穿"])]
        risk_html = ""
        if sell_sigs:
            for s in sell_sigs[:2]:
                risk_html += f'<div class="risk-tag sell">{s[:70]}</div>'
        elif bearish_sigs:
            for s in bearish_sigs[:2]:
                risk_html += f'<div class="risk-tag warn">{s[:70]}</div>'

        card_border = "rgba(248,113,113,0.3)" if (sell_sigs or score < 30) else "rgba(255,255,255,0.06)"

        cards_html += f"""
        <div class="pos-card" style="border-color:{card_border}">
          <div class="pos-head">
            <div class="pos-tile">{ticker[:2]}</div>
            <div class="pos-info">
              <div class="pos-ticker">{ticker}</div>
              <div class="pos-sub">{qty} shares · avg ${avg:.2f} · {cur}</div>
            </div>
            <div class="pos-price">${price:.2f}</div>
          </div>

          <div class="pos-pnl-row">
            <div class="pnl-block">
              <div class="pnl-label">浮盈/虧</div>
              <div class="pnl-val" style="color:{_pnl_color(upnl)}">{_fmt_pnl(upnl)}</div>
              <div class="pnl-pct" style="color:{_pnl_color(upnl_pct)}">{upnl_pct:+.1f}%</div>
            </div>
            <div class="pnl-block">
              <div class="pnl-label">今日</div>
              <div class="pnl-val" style="color:{_pnl_color(dpnl)}">{_fmt_pnl(dpnl)}</div>
            </div>
            <div class="pnl-block">
              <div class="pnl-label">市值</div>
              <div class="pnl-val">${mktval:,.2f}</div>
            </div>
          </div>

          <div class="sig-row">
            <div class="sig-score" style="color:{_score_color(score)}">{score}<span style="font-size:11px;opacity:.6">/100</span></div>
            <div class="sig-detail">
              <div style="color:{_score_color(score)};font-size:12px;font-weight:600">{strength}</div>
              <div style="color:{macd_zone_color};font-size:11px">MACD {macd_zone}</div>
            </div>
          </div>

          {f'<div class="risk-block">{risk_html}</div>' if risk_html else ''}
        </div>"""

    upnl_color = _pnl_color(total_upnl)
    dpnl_color = _pnl_color(total_dpnl)

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>Portfolio — {synced_at}</title>
<style>
  * {{ box-sizing: border-box; margin: 0; padding: 0; }}
  body {{
    background: #0d0f14;
    color: #e2e4ed;
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI", sans-serif;
    min-height: 100vh;
    padding: 24px 16px 60px;
  }}
  .page {{ max-width: 680px; margin: 0 auto; }}

  /* Header */
  .header {{ margin-bottom: 28px; }}
  .header h1 {{ font-size: 22px; font-weight: 700; letter-spacing: -.02em; color: #fff; }}
  .header .meta {{ font-size: 12px; color: #5a5c6e; margin-top: 4px; }}

  /* Account summary */
  .account-bar {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 12px;
    margin-bottom: 28px;
  }}
  .acct-block {{
    background: #161820;
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 14px 16px;
  }}
  .acct-label {{ font-size: 11px; color: #5a5c6e; text-transform: uppercase; letter-spacing: .06em; margin-bottom: 6px; }}
  .acct-val {{ font-size: 20px; font-weight: 700; letter-spacing: -.02em; }}

  /* Summary strip */
  .summary-strip {{
    background: #161820;
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 12px;
    padding: 16px 20px;
    margin-bottom: 28px;
    display: flex;
    gap: 32px;
    align-items: center;
    flex-wrap: wrap;
  }}
  .sum-item {{ display: flex; flex-direction: column; gap: 3px; }}
  .sum-label {{ font-size: 11px; color: #5a5c6e; text-transform: uppercase; letter-spacing: .06em; }}
  .sum-val {{ font-size: 18px; font-weight: 700; }}

  /* Section title */
  .section-title {{
    font-size: 11px;
    text-transform: uppercase;
    letter-spacing: .08em;
    color: #5a5c6e;
    margin-bottom: 12px;
  }}

  /* Position cards */
  .pos-grid {{ display: flex; flex-direction: column; gap: 12px; }}
  .pos-card {{
    background: #161820;
    border: 1px solid;
    border-radius: 14px;
    padding: 18px 20px;
  }}
  .pos-head {{ display: flex; align-items: center; gap: 12px; margin-bottom: 16px; }}
  .pos-tile {{
    width: 42px; height: 42px;
    border-radius: 10px;
    background: rgba(99,179,237,0.12);
    color: #63b3ed;
    display: flex; align-items: center; justify-content: center;
    font-size: 13px; font-weight: 800; letter-spacing: .02em;
    flex-shrink: 0;
  }}
  .pos-info {{ flex: 1; }}
  .pos-ticker {{ font-size: 16px; font-weight: 700; letter-spacing: -.01em; }}
  .pos-sub {{ font-size: 11px; color: #5a5c6e; margin-top: 2px; }}
  .pos-price {{ font-size: 18px; font-weight: 700; letter-spacing: -.02em; }}

  .pos-pnl-row {{
    display: grid;
    grid-template-columns: repeat(3, 1fr);
    gap: 8px;
    padding: 12px 0;
    border-top: 1px solid rgba(255,255,255,0.05);
    border-bottom: 1px solid rgba(255,255,255,0.05);
    margin-bottom: 14px;
  }}
  .pnl-block {{ display: flex; flex-direction: column; gap: 3px; }}
  .pnl-label {{ font-size: 10px; color: #5a5c6e; text-transform: uppercase; letter-spacing: .06em; }}
  .pnl-val {{ font-size: 15px; font-weight: 700; }}
  .pnl-pct {{ font-size: 11px; font-weight: 600; }}

  .sig-row {{ display: flex; align-items: center; gap: 14px; margin-bottom: 10px; }}
  .sig-score {{ font-size: 28px; font-weight: 800; letter-spacing: -.04em; line-height: 1; }}
  .sig-detail {{ display: flex; flex-direction: column; gap: 3px; }}

  .risk-block {{ margin-top: 10px; display: flex; flex-direction: column; gap: 5px; }}
  .risk-tag {{
    font-size: 11px; padding: 4px 10px; border-radius: 6px;
    line-height: 1.4;
  }}
  .risk-tag.sell {{ background: rgba(248,113,113,0.12); color: #f87171; border: 1px solid rgba(248,113,113,0.25); }}
  .risk-tag.warn {{ background: rgba(251,146,60,0.1); color: #fb923c; border: 1px solid rgba(251,146,60,0.2); }}

  .footer {{ margin-top: 40px; text-align: center; font-size: 11px; color: #3a3c4e; }}
</style>
</head>
<body>
<div class="page">
  <div class="header">
    <h1>📦 My Portfolio</h1>
    <div class="meta">同步時間：{synced_at} · 信號資料：{analysis_date} · 🔒 本機私有，不上傳</div>
  </div>

  <div class="account-bar">
    <div class="acct-block">
      <div class="acct-label">淨資產</div>
      <div class="acct-val">{currency} {net_liq:,.0f}</div>
    </div>
    <div class="acct-block">
      <div class="acct-label">可用資金</div>
      <div class="acct-val">{currency} {buying_pow:,.0f}</div>
    </div>
    <div class="acct-block">
      <div class="acct-label">持倉市值</div>
      <div class="acct-val">USD {total_mktval:,.0f}</div>
    </div>
  </div>

  <div class="summary-strip">
    <div class="sum-item">
      <div class="sum-label">總浮盈/虧</div>
      <div class="sum-val" style="color:{upnl_color}">{_fmt_pnl(total_upnl)}</div>
    </div>
    <div class="sum-item">
      <div class="sum-label">今日盈虧</div>
      <div class="sum-val" style="color:{dpnl_color}">{_fmt_pnl(total_dpnl)}</div>
    </div>
    <div class="sum-item">
      <div class="sum-label">持倉數目</div>
      <div class="sum-val">{len(positions)}</div>
    </div>
  </div>

  <div class="section-title">持倉明細 · 信號對照</div>
  <div class="pos-grid">
    {cards_html}
  </div>

  <div class="footer">本頁資料僅存於本機 · 不會上傳至 GitHub 或任何雲端服務</div>
</div>
</body>
</html>"""


def main():
    print("Loading positions…")
    ibkr = _load(POSITIONS_FILE, {})
    if not ibkr:
        print(f"❌ No positions file at {POSITIONS_FILE}")
        print("   Run: python3 src/ibkr_sync.py")
        return

    positions  = ibkr.get("positions", [])
    account    = ibkr.get("account", {})
    synced_at  = ibkr.get("synced_at", "unknown")

    print(f"   {len(positions)} positions loaded")

    print("Loading signal data…")
    analysis   = _load(ANALYSIS_FILE, {})
    stocks     = analysis.get("stock_results", [])
    sig_map    = {s["ticker"]: s for s in stocks}
    analysis_date = analysis.get("date", "unknown")

    matched = [p["ticker"] for p in positions if p["ticker"] in sig_map]
    print(f"   Signal data matched: {matched}")

    print("Generating portfolio.html…")
    html = build_html(positions, account, sig_map, synced_at, analysis_date)
    os.makedirs("outputs", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    abs_path = os.path.abspath(OUTPUT_FILE)
    print(f"✅ Saved → {abs_path}")
    webbrowser.open(f"file://{abs_path}")


if __name__ == "__main__":
    main()
