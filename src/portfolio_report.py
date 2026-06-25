"""portfolio_report.py — Local-only IBKR portfolio dashboard.

Generates outputs/portfolio.html and opens in browser.
NEVER committed or deployed — outputs/ is gitignored.

Usage:
    python3 src/portfolio_report.py
"""
import json
import os
import webbrowser
from datetime import datetime, date, timedelta

POSITIONS_FILE  = os.path.join("outputs", "ibkr_positions.json")
ANALYSIS_FILE   = os.path.join("outputs", "last_analysis.json")
OUTPUT_FILE     = os.path.join("outputs", "portfolio.html")
PNL_HISTORY_FILE = os.path.join("outputs", "pnl_history.json")


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


def _suggested_move(score, macd, sell_signals, signals):
    """Generate a concise suggested move based on signal data."""
    if sell_signals:
        return ("🔴 考慮平倉或設保護性止損",
                "rgba(248,113,113,0.15)", "#f87171")

    if macd is None:
        return ("⏳ 待下次分析更新", "rgba(90,92,110,0.15)", "#5a5c6e")

    macd_above = macd > 0

    if score >= 70 and macd_above:
        return ("✅ 趨勢強 · 持有 · 可考慮加倉",
                "rgba(52,211,153,0.12)", "#34d399")
    if score >= 50 and macd_above:
        return ("🟡 持有 · 觀察動能是否持續",
                "rgba(245,185,66,0.12)", "#f5b942")
    if score >= 30 and macd_above:
        return ("🟡 謹慎持有 · 信號偏弱，等待改善",
                "rgba(251,146,60,0.12)", "#fb923c")
    if not macd_above:
        return ("⚠️ MACD 在0軸以下 · 考慮減倉或設止損",
                "rgba(251,146,60,0.15)", "#fb923c")
    return ("⚠️ 信號偏弱 · 謹慎",
            "rgba(90,92,110,0.15)", "#5a5c6e")


def _build_card(p: dict, sig: dict | None) -> str:
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

    has_sig = sig is not None
    score    = sig.get("score", 0) if has_sig else None
    strength = sig.get("strength", "—") if has_sig else "待分析"
    macd     = sig.get("macd") if has_sig else None
    signals  = sig.get("signals", []) if has_sig else []
    sell_sigs = sig.get("sell_signals", []) if has_sig else []
    ai_view  = sig.get("ai_view", "") if has_sig else ""

    # Score delta from sparkline history ([-2] = prev day, [-1] = current)
    score_delta_html = ""
    if has_sig and score is not None:
        sp = sig.get("sparkline_points", [])
        if len(sp) >= 2:
            prev_score = sp[-2]
            delta = score - prev_score
            if abs(delta) >= 2:  # only show meaningful change
                d_col = "#34d399" if delta > 0 else "#f87171"
                d_arr = "↑" if delta > 0 else "↓"
                score_delta_html = f'<span style="font-size:11px;color:{d_col};font-weight:700;margin-left:6px">{d_arr}{abs(delta):.0f}</span>'

    # Signal freshness badge
    sig_date = sig.get("_analysis_date", "") if has_sig else ""
    freshness_html = ""
    if sig_date:
        today_s = date.today().isoformat()
        is_fresh = sig_date == today_s
        f_color = "#34d399" if is_fresh else "#f5b942"
        f_label = "今日" if is_fresh else sig_date
        freshness_html = f'<span style="font-size:10px;padding:2px 7px;border-radius:4px;background:rgba(255,255,255,0.04);color:{f_color};border:1px solid {f_color}33">📡 {f_label}</span>'

    macd_above = (macd or 0) > 0 if macd is not None else None
    macd_zone_txt = ("0軸以上 ✅" if macd_above else "0軸以下 ⚠️") if macd is not None else "—"
    macd_zone_color = ("#34d399" if macd_above else "#fb923c") if macd is not None else "#5a5c6e"

    # Suggested move
    move_txt, move_bg, move_color = _suggested_move(score or 0, macd, sell_sigs, signals)

    # Top signals to show (filter out pure neutral lines)
    key_signals = [s for s in signals if any(c in s for c in ["✅","🟡","❌","⚠️","🔴","🎯","⚡"])][:5]

    # Sell signals
    sell_html = ""
    for s in sell_sigs[:3]:
        sell_html += f'<div class="risk-tag sell">{s[:80]}</div>'

    # Signal list
    sig_list_html = ""
    for s in key_signals:
        sig_list_html += f'<div class="sig-item">{s}</div>'

    if not has_sig:
        sig_list_html = '<div class="sig-item" style="color:#5a5c6e">⏳ 待下次每日分析更新後顯示（此股新增至監控清單）</div>'

    # AI view snippet
    ai_html = ""
    if ai_view and len(ai_view.strip()) > 20:
        ai_snippet = ai_view.strip()[:200] + ("…" if len(ai_view) > 200 else "")
        ai_html = f'<div class="ai-view">💬 {ai_snippet}</div>'

    card_border = "rgba(248,113,113,0.35)" if sell_sigs else ("rgba(255,255,255,0.06)" if has_sig else "rgba(255,255,255,0.04)")
    score_display = f'{score}<span style="font-size:11px;opacity:.5">/100</span>{score_delta_html}' if score is not None else '<span style="font-size:14px;color:#5a5c6e">N/A</span>'
    score_color = _score_color(score) if score is not None else "#5a5c6e"

    return f"""
    <div class="pos-card" style="border-color:{card_border}">
      <div class="pos-head">
        <div class="pos-tile">{ticker[:3]}</div>
        <div class="pos-info">
          <div class="pos-ticker" style="display:flex;align-items:center;gap:8px">
            {ticker}
            {freshness_html}
          </div>
          <div class="pos-sub">{qty} 股 · 均價 ${avg:.2f} · {cur}</div>
        </div>
        <div style="text-align:right">
          <div class="pos-price">${price:.2f}</div>
          <div style="font-size:11px;color:#5a5c6e;margin-top:2px">{strength}</div>
          {sig.get("price_sparkline_svg","") if has_sig else ""}
        </div>
      </div>

      <div class="pos-pnl-row">
        <div class="pnl-block">
          <div class="pnl-label">浮盈/虧</div>
          <div class="pnl-val" style="color:{_pnl_color(upnl)}">{_fmt_pnl(upnl)}</div>
          <div class="pnl-pct" style="color:{_pnl_color(upnl_pct)}">{upnl_pct:+.1f}%</div>
        </div>
        <div class="pnl-block">
          <div class="pnl-label">今日盈虧</div>
          <div class="pnl-val" style="color:{_pnl_color(dpnl)}">{_fmt_pnl(dpnl)}</div>
        </div>
        <div class="pnl-block">
          <div class="pnl-label">市值</div>
          <div class="pnl-val">${mktval:,.2f}</div>
        </div>
        <div class="pnl-block">
          <div class="pnl-label">成本</div>
          <div class="pnl-val">${cost_b:,.2f}</div>
        </div>
      </div>

      <div class="sig-meta-row">
        <div style="display:flex;align-items:center;gap:12px">
          <div class="sig-score" style="color:{score_color}">{score_display}</div>
          <div>
            <div style="font-size:12px;color:{macd_zone_color};font-weight:600">MACD {macd_zone_txt}</div>
            <div style="font-size:11px;color:#5a5c6e">信號強度評分</div>
          </div>
        </div>
        <div class="move-badge" style="background:{move_bg};color:{move_color}">{move_txt}</div>
      </div>

      {f'<div class="risk-block">{sell_html}</div>' if sell_html else ''}

      <div class="signals-section">
        <div class="signals-title">技術信號</div>
        {sig_list_html}
      </div>

      {ai_html}
    </div>"""




def _update_pnl_history(positions: list, total_upnl: float, total_dpnl: float):
    """Persist daily P&L snapshot for sparkline history."""
    history = _load(PNL_HISTORY_FILE, {})
    today = date.today().isoformat()
    history[today] = {
        "total_upnl":  round(total_upnl, 2),
        "total_dpnl":  round(total_dpnl, 2),
        "positions": [
            {"ticker": p.get("ticker"), "upnl": round(p.get("unrealized_pnl", 0), 2),
             "price": round(p.get("market_price", 0), 2)}
            for p in positions
        ]
    }
    # Keep last 30 days
    if len(history) > 30:
        oldest = sorted(history.keys())[0]
        del history[oldest]
    try:
        os.makedirs("outputs", exist_ok=True)
        with open(PNL_HISTORY_FILE, "w") as f:
            json.dump(history, f, indent=2)
    except OSError:
        pass
    return history


def _build_pnl_sparkline(history: dict, width=120, height=32) -> str:
    """Build SVG sparkline from pnl_history for total unrealized P&L."""
    if not history or len(history) < 2:
        return ""
    dates  = sorted(history.keys())[-14:]
    values = [history[d]["total_upnl"] for d in dates]
    mn, mx = min(values), max(values)
    rng = mx - mn or 1
    pad = 3
    w   = width - pad * 2
    h   = height - pad * 2
    pts = []
    for i, v in enumerate(values):
        x = pad + (i / (len(values) - 1)) * w
        y = pad + h - ((v - mn) / rng) * h
        pts.append(f"{x:.1f},{y:.1f}")
    latest = values[-1]
    color  = "#34d399" if latest >= 0 else "#f87171"
    pts_str = " ".join(pts)
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<polyline points="{pts_str}" fill="none" stroke="{color}" '
        f'stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>'
        f'</svg>'
    )


def _build_weight_bar(positions: list, total_mktval: float) -> str:
    """Build portfolio allocation bar HTML."""
    if total_mktval <= 0:
        return ""
    COLORS = ["#63b3ed","#34d399","#f5b942","#fb923c","#a78bfa","#f472b6","#38bdf8","#4ade80"]
    segments = ""
    labels   = ""
    for i, p in enumerate(positions):
        pct   = (p.get("market_value", 0) / total_mktval) * 100
        color = COLORS[i % len(COLORS)]
        upnl  = p.get("unrealized_pnl", 0)
        border_color = "rgba(52,211,153,0.4)" if upnl >= 0 else "rgba(248,113,113,0.4)"
        segments += (
            f'<div title="{p['ticker']} {pct:.1f}%" '
            f'style="width:{pct:.1f}%;background:{color};opacity:0.85"></div>'
        )
        labels += (
            f'<div style="display:flex;align-items:center;gap:5px;font-size:11px">'
            f'<div style="width:8px;height:8px;border-radius:2px;background:{color};flex-shrink:0"></div>'
            f'<span style="color:#8a8c98">{p["ticker"]}</span>'
            f'<span style="color:#5a5c6e">{pct:.0f}%</span>'
            f'</div>'
        )
    return (
        f'<div style="background:#161820;border:1px solid rgba(255,255,255,0.06);'
        f'border-radius:12px;padding:14px 16px;margin-bottom:20px">'
        f'<div style="display:flex;gap:1px;height:8px;border-radius:5px;overflow:hidden;margin-bottom:10px">'
        f'{segments}</div>'
        f'<div style="display:flex;gap:12px;flex-wrap:wrap">{labels}</div>'
        f'</div>'
    )

def build_html(positions, account, sig_map, synced_at, analysis_date, market=None, generated_at=None):
    total_upnl   = sum(p.get("unrealized_pnl", 0) for p in positions)
    total_dpnl   = sum(p.get("daily_pnl", 0) for p in positions)
    total_mktval = sum(p.get("market_value", 0) for p in positions)
    net_liq      = account.get("net_liquidation", 0)
    buying_pow   = account.get("buying_power", 0)
    currency     = account.get("currency", "HKD")

    # ── Staleness ────────────────────────────────────────────────────────────
    today_str    = date.today().isoformat()
    try:
        analysis_dt  = datetime.strptime(analysis_date, "%Y-%m-%d").date()
        days_stale   = (date.today() - analysis_dt).days
    except Exception:
        days_stale = 0
    is_stale = days_stale > 0
    stale_banner = ""
    if is_stale:
        stale_color = "#fb923c" if days_stale <= 3 else "#f87171"
        stale_banner = f'''
    <div style="background:rgba(251,146,60,0.1);border:1px solid rgba(251,146,60,0.3);
      border-radius:10px;padding:12px 16px;margin-bottom:16px;
      display:flex;align-items:center;gap:10px">
      <span style="font-size:18px">⚠️</span>
      <div>
        <div style="font-size:13px;font-weight:600;color:{stale_color}">信號數據已過期 {days_stale} 天</div>
        <div style="font-size:11px;color:#8a8c98;margin-top:2px">
          分析日期：{analysis_date} · 點擊頁面右下角 🔄 Refresh 更新
        </div>
      </div>
    </div>'''

    # ── IBKR sync age ────────────────────────────────────────────────────────
    try:
        fmt = "%Y-%m-%d %H:%M" if " " in str(synced_at) else "%Y-%m-%d"
        sync_dt   = datetime.strptime(str(synced_at), fmt)
        sync_age  = datetime.now() - sync_dt
        sync_hrs  = int(sync_age.total_seconds() / 3600)
        sync_mins = int((sync_age.total_seconds() % 3600) / 60)
        sync_label = f"{sync_hrs}h {sync_mins}m ago" if sync_hrs else f"{sync_mins}m ago"
        sync_color = "#f87171" if sync_hrs >= 8 else ("#f5b942" if sync_hrs >= 4 else "#34d399")
    except Exception:
        sync_label = synced_at
        sync_color = "#8a8c98"

    gen_label = generated_at or datetime.now().strftime("%H:%M:%S")

    # ── Market context strip ─────────────────────────────────────────────────
    mkt_html = ""
    if market:
        SHOW_MKT = ["SPY", "QQQ", "^VIX", "GLD", "BTC-USD"]
        mkt_items = ""
        for ticker in SHOW_MKT:
            m = market.get(ticker)
            if not m: continue
            chg  = m.get("change_pct", 0)
            col  = "#34d399" if chg >= 0 else "#f87171"
            arr  = "▲" if chg >= 0 else "▼"
            name = m.get("name", ticker)
            mkt_items += f'''
          <div class="mkt-item">
            <div class="mkt-name">{name}</div>
            <div class="mkt-price">${m.get("price", 0):.2f}</div>
            <div class="mkt-chg" style="color:{col}">{arr}{abs(chg):.2f}%</div>
          </div>'''
        if mkt_items:
            mkt_html = f'<div class="mkt-strip">{mkt_items}</div>'

    # ── Alert count for tab title ─────────────────────────────────────────────
    alert_count = sum(1 for p in positions
                      if sig_map.get(p["ticker"], {}).get("sell_signals"))
    page_title = f"⚠️ {alert_count} alerts · Portfolio" if alert_count else "📦 Portfolio"

    # ── Next CI time (8:30 PM HKT = 12:30 UTC) ──────────────────────────────
    from datetime import timezone
    hkt_now   = datetime.now()  # local time, assume HKT
    next_ci   = "20:30 HKT"

    # ── Status bar HTML ──────────────────────────────────────────────────────
    status_bar = f'''
    <div id="status-bar">
      <span>📊 分析：{analysis_date} <span style="color:{"#f87171" if is_stale else "#34d399"}">{"⚠️ 已過期" if is_stale else "✅ 最新"}</span></span>
      <span>🔗 IBKR：<span style="color:{sync_color}">{sync_label}</span></span>
      <span>⏰ 生成：{gen_label}</span>
      <span>🤖 CI 每日：{next_ci}</span>
    </div>'''''''''



    # Sort: sell-signal first, then by daily P&L
    def sort_key(p):
        sig = sig_map.get(p["ticker"], {})
        has_sell = 1 if sig.get("sell_signals") else 0
        return (-has_sell, p.get("daily_pnl", 0))

    sorted_pos = sorted(positions, key=sort_key)
    cards_html = "".join(_build_card(p, sig_map.get(p["ticker"])) for p in sorted_pos)

    upnl_color = _pnl_color(total_upnl)
    dpnl_color = _pnl_color(total_dpnl)
    matched_count = sum(1 for p in positions if p["ticker"] in sig_map)

    # P2: Weight bar + P&L history sparkline
    weight_bar_section = _build_weight_bar(sorted_pos, total_mktval)
    pnl_history  = _update_pnl_history(positions, total_upnl, total_dpnl)
    pnl_sparkline = _build_pnl_sparkline(pnl_history)
    pnl_spark_html = (
        f'<div style="display:flex;align-items:center;gap:8px">' +
        pnl_sparkline +
        f'<span style="font-size:10px;color:#5a5c6e">14d</span></div>'
    ) if pnl_sparkline else ""

    return f"""<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{page_title}</title>
<style>
  * {{ box-sizing:border-box; margin:0; padding:0; }}
  body {{
    background:#0d0f14; color:#e2e4ed;
    font-family:-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;
    padding:24px 16px 80px; min-height:100vh;
  }}
  .page {{ max-width:700px; margin:0 auto; }}

  .header {{ margin-bottom:24px; }}
  .header h1 {{ font-size:22px; font-weight:700; letter-spacing:-.02em; color:#fff; }}
  .meta {{ font-size:11px; color:#5a5c6e; margin-top:5px; line-height:1.6; }}

  .account-bar {{
    display:grid; grid-template-columns:repeat(3,1fr); gap:10px; margin-bottom:16px;
  }}
  .acct-block {{
    background:#161820; border:1px solid rgba(255,255,255,0.06);
    border-radius:12px; padding:14px 16px;
  }}
  .acct-label {{ font-size:10px; color:#5a5c6e; text-transform:uppercase; letter-spacing:.07em; margin-bottom:6px; }}
  .acct-val {{ font-size:18px; font-weight:700; letter-spacing:-.02em; }}

  .summary-strip {{
    background:#161820; border:1px solid rgba(255,255,255,0.06);
    border-radius:12px; padding:16px 20px; margin-bottom:28px;
    display:flex; gap:28px; flex-wrap:wrap; align-items:center;
  }}
  .sum-item {{ display:flex; flex-direction:column; gap:3px; }}
  .sum-label {{ font-size:10px; color:#5a5c6e; text-transform:uppercase; letter-spacing:.07em; }}
  .sum-val {{ font-size:20px; font-weight:700; letter-spacing:-.02em; }}

  .section-title {{ font-size:10px; text-transform:uppercase; letter-spacing:.08em; color:#5a5c6e; margin-bottom:12px; }}

  .pos-grid {{ display:flex; flex-direction:column; gap:14px; }}

  .pos-card {{
    background:#161820; border:1px solid;
    border-radius:14px; padding:20px;
  }}
  .pos-head {{ display:flex; align-items:center; gap:12px; margin-bottom:16px; }}
  .pos-tile {{
    width:44px; height:44px; border-radius:10px;
    background:rgba(99,179,237,0.1); color:#63b3ed;
    display:flex; align-items:center; justify-content:center;
    font-size:11px; font-weight:800; letter-spacing:.02em; flex-shrink:0;
  }}
  .pos-info {{ flex:1; }}
  .pos-ticker {{ font-size:17px; font-weight:700; letter-spacing:-.01em; }}
  .pos-sub {{ font-size:11px; color:#5a5c6e; margin-top:2px; }}
  .pos-price {{ font-size:20px; font-weight:700; letter-spacing:-.02em; }}

  .pos-pnl-row {{
    display:grid; grid-template-columns:repeat(4,1fr); gap:8px;
    padding:12px 0; border-top:1px solid rgba(255,255,255,0.05);
    border-bottom:1px solid rgba(255,255,255,0.05); margin-bottom:14px;
  }}
  .pnl-block {{ display:flex; flex-direction:column; gap:3px; }}
  .pnl-label {{ font-size:10px; color:#5a5c6e; text-transform:uppercase; letter-spacing:.06em; }}
  .pnl-val {{ font-size:14px; font-weight:700; }}
  .pnl-pct {{ font-size:11px; font-weight:600; }}

  .sig-meta-row {{
    display:flex; align-items:center; justify-content:space-between;
    gap:12px; margin-bottom:14px; flex-wrap:wrap;
  }}
  .sig-score {{ font-size:30px; font-weight:800; letter-spacing:-.04em; line-height:1; }}

  .move-badge {{
    font-size:12px; font-weight:600; padding:7px 12px;
    border-radius:8px; line-height:1.3; max-width:260px; text-align:right;
  }}

  .risk-block {{ margin-bottom:12px; display:flex; flex-direction:column; gap:5px; }}
  .risk-tag {{
    font-size:11px; padding:5px 10px; border-radius:7px; line-height:1.4;
  }}
  .risk-tag.sell {{ background:rgba(248,113,113,0.12); color:#f87171; border:1px solid rgba(248,113,113,0.25); }}

  .signals-section {{ margin-bottom:12px; }}
  .signals-title {{ font-size:10px; text-transform:uppercase; letter-spacing:.07em; color:#5a5c6e; margin-bottom:7px; }}
  .sig-item {{ font-size:12px; padding:4px 0; border-bottom:1px solid rgba(255,255,255,0.04); color:#b0b3c0; line-height:1.5; }}
  .sig-item:last-child {{ border-bottom:none; }}

  .ai-view {{
    font-size:12px; color:#8a8c98; background:rgba(255,255,255,0.03);
    border:1px solid rgba(255,255,255,0.05); border-radius:8px;
    padding:10px 12px; margin-top:4px; line-height:1.6; font-style:italic;
  }}

  .footer {{ margin-top:40px; text-align:center; font-size:11px; color:#3a3c4e; line-height:1.8; }}

  /* Market strip */
  .mkt-strip {{
    display:flex; gap:0; overflow-x:auto; margin-bottom:16px;
    background:#161820; border:1px solid rgba(255,255,255,0.06);
    border-radius:12px; padding:0 4px;
  }}
  .mkt-item {{
    display:flex; flex-direction:column; align-items:center;
    padding:12px 14px; gap:3px; min-width:90px; flex-shrink:0;
    border-right:1px solid rgba(255,255,255,0.04);
  }}
  .mkt-item:last-child {{ border-right:none; }}
  .mkt-name {{ font-size:10px; color:#5a5c6e; text-transform:uppercase; letter-spacing:.05em; }}
  .mkt-price {{ font-size:14px; font-weight:700; }}
  .mkt-chg {{ font-size:11px; font-weight:600; }}

  /* Status bar */
  #status-bar {{
    position:fixed; bottom:0; left:0; right:0;
    background:#0a0c10; border-top:1px solid rgba(255,255,255,0.07);
    padding:8px 20px; display:flex; gap:20px; flex-wrap:wrap;
    font-size:11px; color:#5a5c6e; z-index:100;
    align-items:center;
  }}
  #status-bar span {{ white-space:nowrap; }}
</style>
</head>
<body>
<div class="page">
  <div class="header">
    <h1>📦 My Portfolio</h1>
    <div class="meta">
      信號匹配：{matched_count}/{len(positions)} 持倉 &nbsp;·&nbsp;
      🔒 本機私有 · 不上傳
    </div>
  </div>

  {stale_banner}
  {mkt_html}

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
    <div class="acct-block" style="border-color:{'rgba(248,113,113,0.35)' if alert_count else 'rgba(52,211,153,0.2)'}">
      <div class="acct-label">需關注</div>
      <div class="acct-val" style="color:{'#f87171' if alert_count else '#34d399'}">
        {'⚠️ ' + str(alert_count) + ' 持倉' if alert_count else '✅ 全清'}
      </div>
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
      <div class="sum-label">持倉數</div>
      <div class="sum-val">{len(positions)}</div>
    </div>
    <div class="sum-item">
      <div class="sum-label">持倉佔比</div>
      <div class="sum-val">{(total_mktval / (net_liq / 7.8) * 100) if net_liq else 0:.0f}%</div>
    </div>
    {f'<div class="sum-item"><div class="sum-label">浮盈走勢 14d</div>{pnl_spark_html}</div>' if pnl_spark_html else ""}
  </div>

  {weight_bar_section}

  <div class="section-title">持倉明細 · 信號分析 · 建議行動</div>
  <div class="pos-grid">{cards_html}</div>

  <div class="footer">
    本頁所有資料僅存於本機 · 不會上傳至 GitHub 或任何雲端服務<br>
    建議行動僅供參考，不構成投資建議 · 所有交易決定由用戶自行負責
  </div>
</div>
{status_bar}
</body>
</html>"""


def main():
    print("Loading IBKR positions…")
    ibkr = _load(POSITIONS_FILE, {})
    if not ibkr:
        print(f"❌ No positions file at {POSITIONS_FILE}")
        print("   Run: python3 src/ibkr_sync.py")
        return

    positions  = ibkr.get("positions", [])
    account    = ibkr.get("account", {})
    synced_at  = ibkr.get("synced_at", "unknown")
    print(f"   {len(positions)} positions loaded")

    print("Loading signal analysis…")
    analysis     = _load(ANALYSIS_FILE, {})
    stocks       = analysis.get("stock_results", [])
    _adate = analysis.get("date", "")
    for s in stocks:
        s["_analysis_date"] = _adate
    sig_map      = {s["ticker"]: s for s in stocks}
    analysis_date = _adate or "unknown"

    matched = [p["ticker"] for p in positions if p["ticker"] in sig_map]
    missing = [p["ticker"] for p in positions if p["ticker"] not in sig_map]
    print(f"   Matched: {matched}")
    if missing:
        print(f"   No signal data yet: {missing} (will appear after next pipeline run)")

    market       = analysis.get("market", {})
    generated_at = datetime.now().strftime("%H:%M:%S")
    print("Generating portfolio.html…")
    html = build_html(positions, account, sig_map, synced_at, analysis_date,
                      market=market, generated_at=generated_at)
    os.makedirs("outputs", exist_ok=True)
    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        f.write(html)

    abs_path = os.path.abspath(OUTPUT_FILE)
    print(f"✅ Saved → {abs_path}")
    webbrowser.open(f"file://{abs_path}")


if __name__ == "__main__":
    main()
