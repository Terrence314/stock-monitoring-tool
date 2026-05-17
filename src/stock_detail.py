"""stock_detail.py — Per-ticker HTML detail page generator.

Generates outputs/TICKER.html for each stock using the V1 terminal dark aesthetic.
Called from report_generator.generate_dashboard() after the main index.html is written.
"""

import os
import math
from jinja2 import Template


# ── Helpers ────────────────────────────────────────────────────────────────────

def _parse_float(val) -> float:
    """Safely parse a value (string like '895.12', float, int, or '—') to float.
    Returns 0.0 on any failure.
    """
    if val is None:
        return 0.0
    if isinstance(val, (int, float)):
        return float(val)
    try:
        return float(str(val).replace(",", "").strip())
    except (ValueError, TypeError):
        return 0.0


def _fmt(v, decimals=2) -> str:
    """Format a float to a fixed-decimal string, or '—' if zero/None."""
    f = _parse_float(v)
    if f == 0.0:
        return "—"
    return f"{f:.{decimals}f}"


# ── SVG Candlestick Chart ──────────────────────────────────────────────────────

def _build_candle_svg(ohlc: list, width: int = 760, height: int = 400) -> str:
    """Generate a full SVG candlestick chart with MA lines, volume, and MACD.

    Layout (top to bottom):
      Price area  : 62% of height  (includes MA5/20/60)
      Volume area : 16% of height
      MACD area   : remaining 22%
    Padding: left 12px, right 52px (y-axis labels), top 8px, bottom 20px
    """
    if not ohlc or len(ohlc) < 2:
        return ""

    n = len(ohlc)

    # ── Layout constants ──────────────────────────────────────────────────────
    pad_l, pad_r, pad_t, pad_b = 12, 58, 12, 22
    chart_w = width - pad_l - pad_r
    total_h = height - pad_t - pad_b

    price_h  = int(total_h * 0.62)
    vol_h    = int(total_h * 0.16)
    macd_h   = total_h - price_h - vol_h
    vol_y    = pad_t + price_h + 4
    macd_y   = vol_y + vol_h + 4

    # ── Data extraction ───────────────────────────────────────────────────────
    closes  = [b.get("c", 0) for b in ohlc]
    opens   = [b.get("o", 0) for b in ohlc]
    highs   = [b.get("h", 0) for b in ohlc]
    lows    = [b.get("l", 0) for b in ohlc]
    vols    = [b.get("v", 0) for b in ohlc]

    # ── Moving averages (computed inline) ────────────────────────────────────
    def _sma(data, period):
        result = []
        for i in range(len(data)):
            if i < period - 1:
                result.append(None)
            else:
                result.append(sum(data[i - period + 1:i + 1]) / period)
        return result

    ma5  = _sma(closes, 5)
    ma20 = _sma(closes, 20)
    ma60 = _sma(closes, 60)

    # ── MACD (12/26/9) ────────────────────────────────────────────────────────
    def _ema(data, period):
        k = 2 / (period + 1)
        result = []
        for i, v in enumerate(data):
            if i == 0:
                result.append(v)
            else:
                result.append(v * k + result[-1] * (1 - k))
        return result

    ema12 = _ema(closes, 12)
    ema26 = _ema(closes, 26)
    dif   = [a - b for a, b in zip(ema12, ema26)]
    dea   = _ema(dif, 9)
    hist  = [2 * (d - e) for d, e in zip(dif, dea)]

    # ── Price scale ───────────────────────────────────────────────────────────
    price_min = min(lows)
    price_max = max(highs)
    price_rng = price_max - price_min
    if price_rng == 0:
        price_rng = price_max * 0.01 or 1
    # Add 3% padding
    price_min -= price_rng * 0.03
    price_max += price_rng * 0.03
    price_rng = price_max - price_min

    def px(price_val):
        """Convert price to SVG y-coordinate within the price area."""
        return pad_t + price_h - ((price_val - price_min) / price_rng) * price_h

    def bx(idx, fraction=0.5):
        """Convert bar index to SVG x-coordinate."""
        bar_w = chart_w / n
        return pad_l + bar_w * (idx + fraction)

    # ── Volume scale ──────────────────────────────────────────────────────────
    max_vol = max(vols) if vols else 1
    if max_vol == 0:
        max_vol = 1

    def vy(vol_val):
        """Convert volume to height within volume area."""
        return (vol_val / max_vol) * vol_h

    # ── MACD scale ───────────────────────────────────────────────────────────
    macd_vals = [abs(v) for v in hist + dif + dea if v is not None]
    macd_max = max(macd_vals) if macd_vals else 1
    if macd_max == 0:
        macd_max = 1
    macd_half = macd_max * 1.2  # symmetric around zero

    def my(val):
        """Convert MACD value to SVG y-coordinate within MACD area."""
        mid = macd_y + macd_h / 2
        return mid - (val / macd_half) * (macd_h / 2)

    bar_w = chart_w / n
    candle_w = max(bar_w * 0.6, 1.5)

    # ── Build SVG pieces ──────────────────────────────────────────────────────
    parts = []
    parts.append(
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg" style="display:block;width:100%;height:auto">'
    )

    # Background
    parts.append(
        f'<rect width="{width}" height="{height}" fill="#0b0c10" rx="0"/>'
    )

    # ── Grid lines (price) ────────────────────────────────────────────────────
    parts.append('<g opacity="0.35">')
    for pct in [0.0, 0.25, 0.5, 0.75, 1.0]:
        gy = pad_t + price_h * pct
        parts.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{pad_l + chart_w}" y2="{gy:.1f}" '
            f'stroke="#23252f" stroke-width="1"/>'
        )
        p_val = price_max - (price_rng * pct)
        if p_val > 0:
            label = f"{p_val:.2f}" if p_val < 1000 else f"{p_val:,.0f}"
            lx = pad_l + chart_w + 4
            parts.append(
                f'<text x="{lx}" y="{gy + 4:.1f}" fill="#52545e" font-size="9" '
                f'font-family="JetBrains Mono, monospace">{label}</text>'
            )
    parts.append('</g>')

    # ── MA lines ─────────────────────────────────────────────────────────────
    def _ma_path(ma_vals, color):
        pts = [(bx(i), px(v)) for i, v in enumerate(ma_vals) if v is not None]
        if len(pts) < 2:
            return ""
        d = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in pts)
        return f'<path d="{d}" stroke="{color}" stroke-width="1.2" fill="none" opacity="0.85"/>'

    parts.append(_ma_path(ma5,  "#f5b942"))   # amber
    parts.append(_ma_path(ma20, "#7aa2ff"))   # blue
    parts.append(_ma_path(ma60, "#b18cff"))   # purple

    # ── Candlesticks ─────────────────────────────────────────────────────────
    for i in range(n):
        o, h, l, c = opens[i], highs[i], lows[i], closes[i]
        is_up = c >= o
        color = "#34d399" if is_up else "#f87171"
        cx = bx(i)
        body_top    = px(max(o, c))
        body_bottom = px(min(o, c))
        body_height = max(body_bottom - body_top, 1)

        # Wick
        parts.append(
            f'<line x1="{cx:.1f}" y1="{px(h):.1f}" x2="{cx:.1f}" y2="{px(l):.1f}" '
            f'stroke="{color}" stroke-width="1" opacity="0.7"/>'
        )
        # Body
        parts.append(
            f'<rect x="{cx - candle_w/2:.1f}" y="{body_top:.1f}" '
            f'width="{candle_w:.1f}" height="{body_height:.1f}" '
            f'fill="{color}" opacity="0.85"/>'
        )

    # ── Last price tag ────────────────────────────────────────────────────────
    last_price = closes[-1]
    last_y = px(last_price)
    is_up_last = last_price >= opens[-1]
    tag_color = "#34d399" if is_up_last else "#f87171"
    lx_tag = pad_l + chart_w + 4
    parts.append(
        f'<rect x="{lx_tag}" y="{last_y - 8:.1f}" width="50" height="16" '
        f'fill="{tag_color}" rx="3" opacity="0.9"/>'
    )
    label_last = f"{last_price:.2f}" if last_price < 1000 else f"{last_price:,.0f}"
    parts.append(
        f'<text x="{lx_tag + 3}" y="{last_y + 4:.1f}" fill="#0b0c10" font-size="9" '
        f'font-family="JetBrains Mono, monospace" font-weight="700">{label_last}</text>'
    )

    # ── Volume bars ───────────────────────────────────────────────────────────
    parts.append(f'<text x="{pad_l}" y="{vol_y - 2}" fill="#52545e" font-size="8" '
                 f'font-family="JetBrains Mono, monospace">VOL</text>')
    for i in range(n):
        is_up_v = closes[i] >= opens[i]
        color_v = "#34d399" if is_up_v else "#f87171"
        bar_h_px = vy(vols[i])
        vx = bx(i)
        parts.append(
            f'<rect x="{vx - candle_w/2:.1f}" y="{vol_y + vol_h - bar_h_px:.1f}" '
            f'width="{candle_w:.1f}" height="{bar_h_px:.1f}" '
            f'fill="{color_v}" opacity="0.55"/>'
        )

    # ── MACD section ──────────────────────────────────────────────────────────
    parts.append(f'<text x="{pad_l}" y="{macd_y - 2}" fill="#52545e" font-size="8" '
                 f'font-family="JetBrains Mono, monospace">MACD</text>')
    # Zero line
    zero_y = my(0)
    parts.append(
        f'<line x1="{pad_l}" y1="{zero_y:.1f}" x2="{pad_l + chart_w}" y2="{zero_y:.1f}" '
        f'stroke="#33363f" stroke-width="1"/>'
    )
    # MACD histogram bars
    for i in range(n):
        hv = hist[i]
        color_m = "#34d399" if hv >= 0 else "#f87171"
        bar_top = min(my(hv), zero_y)
        bar_ht  = abs(my(hv) - zero_y)
        mx_bar  = bx(i)
        parts.append(
            f'<rect x="{mx_bar - candle_w/2:.1f}" y="{bar_top:.1f}" '
            f'width="{candle_w:.1f}" height="{max(bar_ht, 1):.1f}" '
            f'fill="{color_m}" opacity="0.65"/>'
        )
    # DIF line (amber)
    dif_pts = [(bx(i), my(v)) for i, v in enumerate(dif)]
    if len(dif_pts) >= 2:
        d_dif = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in dif_pts)
        parts.append(f'<path d="{d_dif}" stroke="#f5b942" stroke-width="1" fill="none"/>')
    # DEA line (blue)
    dea_pts = [(bx(i), my(v)) for i, v in enumerate(dea)]
    if len(dea_pts) >= 2:
        d_dea = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in dea_pts)
        parts.append(f'<path d="{d_dea}" stroke="#7aa2ff" stroke-width="1" fill="none"/>')

    # MACD label (current values)
    cur_dif  = dif[-1]
    cur_dea  = dea[-1]
    cur_hist = hist[-1]
    macd_lbl = f"DIF {cur_dif:+.2f}  DEA {cur_dea:+.2f}  HIST {cur_hist:+.2f}"
    parts.append(
        f'<text x="{pad_l + 10}" y="{macd_y + 10}" fill="#8a8c98" font-size="8" '
        f'font-family="JetBrains Mono, monospace">{macd_lbl}</text>'
    )

    # ── X-axis time labels at 25 / 50 / 75 % ─────────────────────────────────
    for pct in [0.25, 0.5, 0.75]:
        idx = int(n * pct)
        tx = bx(idx)
        parts.append(
            f'<text x="{tx:.1f}" y="{height - 6}" fill="#52545e" font-size="8" '
            f'text-anchor="middle" font-family="JetBrains Mono, monospace">'
            f'bar {idx}</text>'
        )

    # ── MA legend ─────────────────────────────────────────────────────────────
    legend_y = pad_t + 14
    legend_items = [
        ("#f5b942", "MA5"),
        ("#7aa2ff", "MA20"),
        ("#b18cff", "MA60"),
    ]
    lx_leg = pad_l + 8
    for color_l, lbl_l in legend_items:
        parts.append(
            f'<rect x="{lx_leg}" y="{legend_y - 7}" width="14" height="2" fill="{color_l}" rx="1"/>'
        )
        parts.append(
            f'<text x="{lx_leg + 18}" y="{legend_y}" fill="{color_l}" font-size="9" '
            f'font-family="JetBrains Mono, monospace">{lbl_l}</text>'
        )
        lx_leg += 60

    parts.append("</svg>")
    return "".join(parts)


# ── Key Levels ────────────────────────────────────────────────────────────────

def _build_key_levels(s: dict) -> list[dict]:
    """Derive key support/resistance levels from MA and 52W data."""
    price = _parse_float(s.get("price"))
    ma20  = _parse_float(s.get("ma20"))
    ma60  = _parse_float(s.get("ma60"))
    w52h  = _parse_float(s.get("week52_high")) or price * 1.3
    w52l  = _parse_float(s.get("week52_low"))  or price * 0.7
    levels = []

    if w52h > price * 1.02:
        levels.append({"l": "52W 高點壓力", "v": f"{w52h:.2f}", "tier": "resistance"})

    if ma20 > 0:
        if price * 1.03 > ma20 > price * 0.97:
            levels.append({"l": "MA20 關鍵", "v": f"{ma20:.2f}", "tier": "neutral"})
        elif ma20 > price:
            levels.append({"l": "MA20 壓力", "v": f"{ma20:.2f}", "tier": "resistance"})
        else:
            levels.append({"l": "MA20 支撐", "v": f"{ma20:.2f}", "tier": "support"})

    if ma60 > 0:
        if ma60 > price:
            levels.append({"l": "MA60 壓力",    "v": f"{ma60:.2f}", "tier": "resistance"})
        else:
            levels.append({"l": "MA60 主要支撐", "v": f"{ma60:.2f}", "tier": "support"})

    if w52l > 0 and w52l < price * 0.92:
        levels.append({"l": "52W 低點支撐", "v": f"{w52l:.2f}", "tier": "support"})

    return levels


# ── Scenarios ─────────────────────────────────────────────────────────────────

def _build_scenarios(s: dict) -> list[dict]:
    """Derive bull / neutral / bear scenarios from signal score."""
    sc    = s.get("score", 50)
    price = _parse_float(s.get("price"))

    if sc >= 70:
        bp, np_, dp = 50, 35, 15
    elif sc >= 50:
        bp, np_, dp = 30, 45, 25
    else:
        bp, np_, dp = 15, 35, 50

    return [
        {
            "i": "🐂", "t": "強勢續漲", "p": bp, "c": "up",
            "desc": f"技術面強勢，信號分數 {sc}/100，資金持續流入",
            "range": f"{price * 1.05:.2f} → {price * 1.12:.2f}",
        },
        {
            "i": "⟿", "t": "高檔震盪", "p": np_, "c": "amber",
            "desc": "整理換手，等待方向選擇",
            "range": f"{price * 0.96:.2f} ~ {price * 1.04:.2f}",
        },
        {
            "i": "🐻", "t": "短線回調", "p": dp, "c": "down",
            "desc": "回測支撐，需留意止損",
            "range": f"{price * 0.88:.2f} ~ {price * 0.95:.2f}",
        },
    ]


# ── Bull/Bear Targets ─────────────────────────────────────────────────────────

def _build_bull_bear_targets(s: dict) -> list[dict]:
    """Compute price target table from current price."""
    p = _parse_float(s.get("price"))
    return [
        {"s": "超級牛市", "c": "強勁突破+資金追漲", "t": f"{p * 1.25:.2f} ~ {p * 1.45:.2f}", "tier": "up"},
        {"s": "基本牛市", "c": "維持強勢趨勢",      "t": f"{p * 1.10:.2f} ~ {p * 1.22:.2f}", "tier": "up_soft"},
        {"s": "中性",     "c": "區間整理",           "t": f"{p * 0.97:.2f} ~ {p * 1.08:.2f}", "tier": "neutral"},
        {"s": "保守",     "c": "回測主要支撐",        "t": f"{p * 0.88:.2f} ~ {p * 0.96:.2f}", "tier": "amber"},
        {"s": "熊市",     "c": "跌破關鍵支撐",        "t": f"< {p * 0.80:.2f}",               "tier": "down"},
    ]


# ── Generic Risks ─────────────────────────────────────────────────────────────

def _build_risks(s: dict) -> list[str]:
    """Return a list of generic risks appropriate to the asset type."""
    atype = s.get("asset_type", "stock")
    score = s.get("score", 50)
    risks = []

    if atype == "etf":
        risks = [
            "指數成份股集中，追蹤誤差風險",
            "流動性較個股低，大單衝擊成本較高",
            "宏觀事件（利率、政策）可能拖累整體板塊",
        ]
    else:
        risks = [
            "個股盈利不及預期，下修風險",
            "大盤系統性風險，高 Beta 個股跌幅可能更深",
            "主力出貨或機構減倉，籌碼面轉弱",
        ]
        if score < 50:
            risks.append("技術面趨勢尚未反轉，逢反彈需謹慎追高")
        else:
            risks.append("短線漲幅過快，追高需注意回調壓力")

    return risks


# ── Strategy Cards ────────────────────────────────────────────────────────────

def _build_strategy(s: dict) -> list[dict]:
    """Generate 3 investor-type strategy cards."""
    sc    = s.get("score", 50)
    price = _parse_float(s.get("price"))

    if sc >= 70:
        short_action = "積極追入，設緊止損"
        short_stop   = f"${price * 0.95:.2f}"
        short_target = f"${price * 1.10:.2f}"
        mid_action   = "逢低建倉，分批佈局"
        mid_note     = "訊號強勁，可加大至標準倉位"
        long_action  = "核心倉位持有"
        long_note    = "趨勢完好，無需操作"
    elif sc >= 50:
        short_action = "觀望為主，確認方向再進場"
        short_stop   = f"${price * 0.93:.2f}"
        short_target = f"${price * 1.08:.2f}"
        mid_action   = "小批試單，等待確認"
        mid_note     = "訊號中等，控制倉位"
        long_action  = "繼續持有，注意停利"
        long_note    = "訊號未達高位，不宜加碼"
    else:
        short_action = "避免做多，等待築底信號"
        short_stop   = "—"
        short_target = "—"
        mid_action   = "暫時觀望，靜待反轉"
        mid_note     = "弱勢確認前不宜進場"
        long_action  = "注意停損或降低倉位"
        long_note    = "下行風險仍在，保守為宜"

    return [
        {
            "type":   "短線操作",
            "sub":    "Short-term",
            "action": short_action,
            "stop":   short_stop,
            "target": short_target,
        },
        {
            "type":   "中線佈局",
            "sub":    "Mid-term",
            "action": mid_action,
            "note":   mid_note,
        },
        {
            "type":   "長線投資",
            "sub":    "Long-term",
            "action": long_action,
            "note":   long_note,
        },
    ]


# ── Verdict ───────────────────────────────────────────────────────────────────

def _build_verdict(s: dict) -> dict:
    """Return label + color class for the summary footer verdict."""
    sc = s.get("score", 50)
    if sc >= 80:
        return {"label": "強力做多",   "cls": "up",    "en": "STRONG BUY"}
    if sc >= 65:
        return {"label": "偏多操作",   "cls": "up",    "en": "BUY"}
    if sc >= 50:
        return {"label": "中性觀望",   "cls": "amber", "en": "NEUTRAL"}
    if sc >= 35:
        return {"label": "偏空謹慎",   "cls": "down",  "en": "CAUTION"}
    return     {"label": "弱勢回避",   "cls": "down",  "en": "AVOID"}


# ── Analyst bar helper ────────────────────────────────────────────────────────

def _analyst_total(s: dict) -> int:
    ab = s.get("analyst_buy")  or 0
    ah = s.get("analyst_hold") or 0
    as_ = s.get("analyst_sell") or 0
    return (ab or 0) + (ah or 0) + (as_ or 0)


# ── HTML Template ─────────────────────────────────────────────────────────────

DETAIL_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>{{ s.ticker }} · Signal Monitor</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=Inter:wght@400;500;600;700;800&family=JetBrains+Mono:wght@400;500;600;700&family=Noto+Sans+TC:wght@400;500;600;700&display=swap" rel="stylesheet">
<style>
/* ── DESIGN TOKENS · V1 ────────────────────────────────────────────── */
:root {
  --bg:        #0b0c10;
  --surface:   #13141b;
  --elevated:  #1a1c25;
  --border:    #23252f;
  --border-hi: #33363f;
  --text:      #e7e8ec;
  --text-2:    #8a8c98;
  --muted:     #52545e;
  --up:        #34d399;
  --down:      #f87171;
  --blue:      #7aa2ff;
  --amber:     #f5b942;
  --purple:    #b18cff;
  --mono: 'JetBrains Mono', 'Fira Code', monospace;
  --sans: 'Inter', 'Noto Sans TC', system-ui, sans-serif;
}

/* ── RESET ─────────────────────────────────────────────────────────── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }
html { scroll-behavior: smooth; }
body {
  background: var(--bg);
  color: var(--text);
  font-family: var(--sans);
  font-size: 13px;
  line-height: 1.55;
  min-height: 100vh;
  -webkit-font-smoothing: antialiased;
  text-rendering: optimizeLegibility;
}

/* ── TOP BAR ────────────────────────────────────────────────────────── */
.topbar {
  position: sticky; top: 0; z-index: 50;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  display: flex; align-items: center; gap: 16px;
  padding: 0 28px; height: 52px;
}
.back-link {
  font-family: var(--mono); font-size: 12px; font-weight: 600;
  color: var(--text-2); text-decoration: none;
  display: flex; align-items: center; gap: 6px;
  padding: 5px 10px; border-radius: 7px;
  border: 1px solid var(--border);
  transition: color 0.15s, border-color 0.15s;
}
.back-link:hover { color: var(--text); border-color: var(--border-hi); }
.topbar-ticker {
  font-family: var(--mono); font-size: 14px; font-weight: 700; color: var(--text);
}
.topbar-name { font-size: 12px; color: var(--text-2); }
.spacer { flex: 1; }
.topbar-date { font-family: var(--mono); font-size: 11px; color: var(--muted); }

/* ── PAGE WRAPPER ───────────────────────────────────────────────────── */
.page-detail {
  max-width: 1280px; margin: 0 auto;
  padding: 24px 28px 64px;
  display: flex; flex-direction: column; gap: 18px;
}

/* ── SECTION LABEL ─────────────────────────────────────────────────── */
.sec-label {
  display: flex; align-items: center; gap: 12px; margin-bottom: 14px;
}
.sec-pill {
  background: var(--amber); color: #fff;
  font-family: var(--mono); font-size: 9px; font-weight: 800;
  letter-spacing: 0.08em; padding: 3px 9px; border-radius: 10px;
  text-transform: uppercase;
}
.sec-title {
  font-size: 16px; font-weight: 700; color: var(--text); letter-spacing: -0.01em;
}
.sec-sub { font-size: 11px; color: var(--text-2); }

/* ── CARD ───────────────────────────────────────────────────────────── */
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 22px 24px;
}
.card.elevated { background: var(--elevated); }

/* ── HERO CARD ──────────────────────────────────────────────────────── */
.hero-card {
  background: var(--surface);
  border: 1px solid var(--border-hi);
  border-radius: 16px;
  padding: 28px 32px;
}
.hero-top { display: flex; align-items: flex-start; gap: 22px; flex-wrap: wrap; }
.hero-logo {
  width: 64px; height: 64px; border-radius: 14px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--mono); font-size: 20px; font-weight: 800; color: #fff;
}
.hero-id { flex: 1; min-width: 180px; }
.hero-ticker {
  font-family: var(--mono); font-size: 36px; font-weight: 700;
  color: var(--text); letter-spacing: -0.02em; line-height: 1;
}
.hero-name { font-size: 14px; color: var(--text-2); margin-top: 5px; }
.hero-badges { display: flex; gap: 6px; margin-top: 10px; flex-wrap: wrap; }
.tag {
  font-family: var(--mono); font-size: 9px; font-weight: 700;
  padding: 2px 8px; border-radius: 4px;
  letter-spacing: 0.04em; text-transform: uppercase;
}
.tag.stock  { background: rgba(122,162,255,0.12); color: var(--blue); border: 1px solid rgba(122,162,255,0.25); }
.tag.etf    { background: rgba(177,140,255,0.12); color: var(--purple); border: 1px solid rgba(177,140,255,0.25); }
.tag.market { background: rgba(255,255,255,0.04); color: var(--text-2); border: 1px solid var(--border); }
.tag.date   { background: rgba(245,185,66,0.10); color: var(--amber); border: 1px solid rgba(245,185,66,0.25); }

.hero-price-block { text-align: right; }
.hero-price {
  font-family: var(--mono); font-size: 42px; font-weight: 700;
  letter-spacing: -0.03em; line-height: 1;
}
.hero-chg {
  font-family: var(--mono); font-size: 16px; font-weight: 600; margin-top: 5px;
}
.hero-chg.up   { color: var(--up); }
.hero-chg.down { color: var(--down); }

.hero-stats {
  display: grid; grid-template-columns: repeat(6, 1fr); gap: 10px;
  margin-top: 22px; padding-top: 20px; border-top: 1px solid var(--border);
}
@media (max-width: 900px) { .hero-stats { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 600px) { .hero-stats { grid-template-columns: repeat(2, 1fr); } }
.hero-stat { display: flex; flex-direction: column; gap: 3px; }
.hs-label { font-size: 10px; color: var(--muted); text-transform: uppercase; letter-spacing: 0.04em; }
.hs-val { font-family: var(--mono); font-size: 14px; font-weight: 600; color: var(--text); }

/* ── 2-COL ROW ──────────────────────────────────────────────────────── */
.row-2 { display: grid; grid-template-columns: 1fr 1fr; gap: 16px; }
@media (max-width: 860px) { .row-2 { grid-template-columns: 1fr; } }

/* ── 3-COL ROW ──────────────────────────────────────────────────────── */
.row-3 { display: grid; grid-template-columns: 1fr 1fr 1fr; gap: 16px; }
@media (max-width: 1100px) { .row-3 { grid-template-columns: 1fr 1fr; } }
@media (max-width: 700px)  { .row-3 { grid-template-columns: 1fr; } }

/* ── CHECK / WARNING ITEMS ──────────────────────────────────────────── */
.check-list { display: flex; flex-direction: column; gap: 7px; margin-top: 6px; }
.check-item { font-size: 12.5px; color: var(--text); line-height: 1.5; }
.check-item::before { content: '✓'; color: var(--up); margin-right: 8px; font-weight: 700; }
.warn-item  { font-size: 12.5px; color: var(--text); line-height: 1.5; }
.warn-item::before  { content: '⚠'; color: var(--amber); margin-right: 8px; }
.num-item { font-size: 12.5px; color: var(--text); line-height: 1.5; }

/* ── TECHNICAL ANALYSIS ─────────────────────────────────────────────── */
.tech-layout { display: grid; grid-template-columns: 1fr 280px; gap: 22px; }
@media (max-width: 1000px) { .tech-layout { grid-template-columns: 1fr; } }
.chart-area { min-width: 0; }
.chart-area svg { display: block; width: 100%; border-radius: 8px; overflow: hidden; }
.no-chart {
  height: 200px; display: flex; align-items: center; justify-content: center;
  color: var(--muted); font-family: var(--mono); font-size: 12px;
  background: var(--elevated); border-radius: 8px; border: 1px solid var(--border);
}
.chart-legend {
  display: flex; gap: 14px; flex-wrap: wrap; margin-top: 8px;
  font-family: var(--mono); font-size: 10px;
}
.legend-dot { width: 10px; height: 3px; border-radius: 2px; display: inline-block; margin-right: 4px; vertical-align: middle; }

.tech-sidebar { display: flex; flex-direction: column; gap: 14px; }

/* ── SIGNAL SCORE RING ───────────────────────────────────────────────── */
.ring-card {
  background: var(--elevated); border: 1px solid var(--border);
  border-radius: 12px; padding: 16px;
  display: flex; flex-direction: column; align-items: center; gap: 10px;
}
.ring-large { width: 100px; height: 100px; position: relative; }
.ring-large svg { transform: rotate(-90deg); display: block; }
.ring-large .ring-num {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--mono); font-size: 28px; font-weight: 700;
}
.strength-big {
  font-size: 13px; font-weight: 700; padding: 4px 14px; border-radius: 10px;
}
.strength-big.high { color: var(--up);    background: rgba(52,211,153,0.12); border: 1px solid rgba(52,211,153,0.30); }
.strength-big.mid  { color: var(--amber); background: rgba(245,185,66,0.12); border: 1px solid rgba(245,185,66,0.30); }
.strength-big.low  { color: var(--down);  background: rgba(248,113,113,0.12); border: 1px solid rgba(248,113,113,0.30); }

.breakout-badge {
  font-family: var(--mono); font-size: 10px; font-weight: 700;
  letter-spacing: 0.06em; padding: 4px 12px; border-radius: 6px;
  text-transform: uppercase;
}

/* ── KEY LEVELS TABLE ───────────────────────────────────────────────── */
.levels-table { width: 100%; border-collapse: collapse; margin-top: 8px; }
.levels-table td { padding: 9px 10px; border-bottom: 1px solid var(--border); font-size: 12px; }
.levels-table tr:last-child td { border-bottom: none; }
.level-label { color: var(--text-2); }
.level-val { font-family: var(--mono); font-weight: 600; text-align: right; }
.level-dot { width: 8px; height: 8px; border-radius: 50%; display: inline-block; margin-right: 6px; }

/* ── SCENARIO CARDS ──────────────────────────────────────────────────── */
.scenario-card {
  background: var(--elevated); border: 1px solid var(--border);
  border-radius: 10px; padding: 14px 16px; display: flex; flex-direction: column; gap: 6px;
}
.scen-top { display: flex; align-items: center; justify-content: space-between; }
.scen-title { font-size: 13px; font-weight: 700; color: var(--text); }
.prob-bar { height: 5px; border-radius: 3px; background: var(--border); margin-top: 4px; overflow: hidden; }
.prob-fill { height: 100%; border-radius: 3px; }
.prob-pct { font-family: var(--mono); font-size: 11px; font-weight: 700; }

/* ── BULL/BEAR TABLE ────────────────────────────────────────────────── */
.bb-table { width: 100%; border-collapse: collapse; margin-top: 8px; }
.bb-table th {
  font-size: 10px; color: var(--text-2); font-weight: 500;
  text-align: left; padding: 6px 10px; border-bottom: 1px solid var(--border);
  text-transform: uppercase; letter-spacing: 0.04em;
}
.bb-table td { padding: 9px 10px; border-bottom: 1px solid var(--border); font-size: 12px; }
.bb-table tr:last-child td { border-bottom: none; }
.bb-table .target-val { font-family: var(--mono); font-weight: 600; }

/* ── STRATEGY CARDS ──────────────────────────────────────────────────── */
.strat-card {
  background: var(--elevated); border: 1px solid var(--border);
  border-radius: 12px; padding: 16px; display: flex; flex-direction: column; gap: 8px;
}
.strat-type { font-size: 13px; font-weight: 700; color: var(--text); }
.strat-sub { font-size: 10px; color: var(--text-2); font-family: var(--mono); text-transform: uppercase; letter-spacing: 0.04em; margin-top: 1px; }
.strat-action { font-size: 12px; color: var(--text); }
.strat-meta { display: flex; gap: 10px; flex-wrap: wrap; }
.strat-pill {
  font-family: var(--mono); font-size: 10px; font-weight: 600;
  padding: 2px 8px; border-radius: 4px;
}
.strat-pill.stop   { background: rgba(248,113,113,0.10); color: var(--down);  border: 1px solid rgba(248,113,113,0.20); }
.strat-pill.target { background: rgba(52,211,153,0.10);  color: var(--up);    border: 1px solid rgba(52,211,153,0.20); }
.strat-note { font-size: 11px; color: var(--text-2); }

/* ── ANALYST BAR ────────────────────────────────────────────────────── */
.analyst-bar { display: flex; height: 7px; border-radius: 4px; overflow: hidden; gap: 1px; background: var(--elevated); }
.analyst-buy  { background: var(--up); }
.analyst-hold { background: var(--amber); opacity: 0.85; }
.analyst-sell { background: var(--down); }
.analyst-counts { display: flex; gap: 12px; margin-top: 5px; font-family: var(--mono); font-size: 10px; font-weight: 600; }
.analyst-counts .buy  { color: var(--up); }
.analyst-counts .hold { color: var(--amber); }
.analyst-counts .sell { color: var(--down); }
.analyst-counts .period { margin-left: auto; color: var(--text-2); }

/* ── 52W RANGE BAR ──────────────────────────────────────────────────── */
.range-bar {
  position: relative; height: 5px; border-radius: 3px;
  background: var(--elevated); margin: 8px 0 6px;
}
.range-fill {
  position: absolute; top: 0; left: 0; height: 100%;
  border-radius: 3px;
  background: linear-gradient(90deg, var(--blue), var(--purple));
}
.range-thumb {
  position: absolute; top: -3px; width: 11px; height: 11px;
  border-radius: 50%; background: var(--text);
  border: 2px solid var(--surface); transform: translateX(-50%);
}
.range-labels { display: flex; justify-content: space-between; font-family: var(--mono); font-size: 10px; color: var(--text-2); }

/* ── SUMMARY FOOTER ────────────────────────────────────────────────── */
.summary-card {
  background: linear-gradient(135deg, #13141b, #1a1c25);
  border: 1px solid var(--border-hi);
  border-radius: 16px; padding: 28px 32px;
  display: flex; align-items: center; gap: 32px; flex-wrap: wrap;
}
.summary-text { flex: 1; min-width: 200px; }
.summary-title { font-size: 15px; font-weight: 700; color: var(--text); margin-bottom: 8px; }
.summary-body { font-size: 13px; color: var(--text-2); line-height: 1.65; }
.verdict-block { text-align: center; flex-shrink: 0; }
.verdict-label {
  font-family: var(--mono); font-size: 18px; font-weight: 700;
  padding: 10px 24px; border-radius: 10px;
  display: inline-block;
}
.verdict-label.up   { color: var(--up);    background: rgba(52,211,153,0.12); border: 1px solid rgba(52,211,153,0.30); }
.verdict-label.down { color: var(--down);  background: rgba(248,113,113,0.12); border: 1px solid rgba(248,113,113,0.30); }
.verdict-label.amber{ color: var(--amber); background: rgba(245,185,66,0.12);  border: 1px solid rgba(245,185,66,0.30); }
.verdict-en { font-family: var(--mono); font-size: 10px; color: var(--muted); margin-top: 5px; letter-spacing: 0.08em; }

/* ── FOOTER ────────────────────────────────────────────────────────── */
.footer {
  text-align: center; padding: 24px;
  color: var(--muted); font-family: var(--mono);
  font-size: 10px; letter-spacing: 0.06em;
}

/* ── MA BADGES ──────────────────────────────────────────────────────── */
.ma-badge {
  font-family: var(--mono); font-size: 10px; font-weight: 600;
  padding: 3px 8px; border-radius: 5px;
}
.ma-badge.ma5  { background: rgba(245,185,66,0.10); color: var(--amber); border: 1px solid rgba(245,185,66,0.20); }
.ma-badge.ma20 { background: rgba(122,162,255,0.10); color: var(--blue); border: 1px solid rgba(122,162,255,0.20); }
.ma-badge.ma60 { background: rgba(177,140,255,0.10); color: var(--purple); border: 1px solid rgba(177,140,255,0.20); }
.rsi-badge  { background: rgba(248,113,113,0.08); color: var(--down); border: 1px solid rgba(248,113,113,0.18); font-family: var(--mono); font-size: 10px; font-weight: 600; padding: 3px 8px; border-radius: 5px; }
.vol-badge  { background: rgba(52,211,153,0.08); color: var(--up); border: 1px solid rgba(52,211,153,0.20); font-family: var(--mono); font-size: 10px; font-weight: 600; padding: 3px 8px; border-radius: 5px; }
.badge-row  { display: flex; flex-wrap: wrap; gap: 6px; margin-top: 10px; }

/* ── EARNINGS PILL ──────────────────────────────────────────────────── */
.earnings {
  display: inline-flex; align-items: center; gap: 8px;
  padding: 6px 12px; border-radius: 7px;
  background: rgba(245,185,66,0.08); border: 1px solid rgba(245,185,66,0.30);
  font-family: var(--mono); font-size: 11px; font-weight: 600; color: var(--amber);
}
.pulse {
  width: 6px; height: 6px; border-radius: 50%; background: var(--amber);
  animation: pulse 1.6s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(245,185,66,0.5); }
  50%      { box-shadow: 0 0 0 5px rgba(245,185,66,0); }
}
</style>
</head>
<body>

<!-- TOP BAR -->
<div class="topbar">
  <a href="./index.html" class="back-link">← 返回總覽</a>
  <span class="topbar-ticker">{{ s.ticker }}</span>
  <span class="topbar-name">{{ s.name }}</span>
  <div class="spacer"></div>
  <span class="topbar-date">{{ date }}</span>
</div>

<div class="page-detail">

{# ── HERO CARD ──────────────────────────────────────────────────────────── #}
{%- set chg_class = 'up' if s.price_change_pct >= 0 else 'down' %}
{%- set sc = s.score %}
{%- set sc_class = 'high' if sc >= 60 else ('mid' if sc >= 40 else 'low') %}
{%- set ring_color = '#34d399' if sc >= 60 else ('#f5b942' if sc >= 40 else '#f87171') %}
{%- set logo_grad = 'linear-gradient(135deg,#7aa2ff,#b18cff)' if s.asset_type == 'etf' else 'linear-gradient(135deg,#34d399,#7aa2ff)' %}
{%- set atype = s.asset_type or 'stock' %}

<div class="hero-card">
  <div class="hero-top">
    <div class="hero-logo" style="background:{{ logo_grad }}">
      {{ s.ticker[:2] }}
    </div>
    <div class="hero-id">
      <div class="hero-ticker">{{ s.ticker }}</div>
      <div class="hero-name">{{ s.name }}</div>
      <div class="hero-badges">
        <span class="tag {{ atype }}">{{ atype }}</span>
        <span class="tag market">{{ s.market or 'US' }}</span>
        {% if s.sector and s.sector != 'Unknown' %}
        <span class="tag market">{{ s.sector }}</span>
        {% endif %}
        <span class="tag date">{{ date }}</span>
      </div>
    </div>
    <div class="hero-price-block">
      <div class="hero-price">${{ "%.2f"|format(s.price) }}</div>
      <div class="hero-chg {{ chg_class }}">{{ "%+.2f"|format(s.price_change_pct) }}%</div>
    </div>
  </div>

  <div class="hero-stats">
    <div class="hero-stat">
      <span class="hs-label">開盤</span>
      <span class="hs-val">${{ "%.2f"|format(s.open_price) if s.open_price else '—' }}</span>
    </div>
    <div class="hero-stat">
      <span class="hs-label">日高</span>
      <span class="hs-val" style="color:var(--up)">${{ "%.2f"|format(s.high_price) if s.high_price else '—' }}</span>
    </div>
    <div class="hero-stat">
      <span class="hs-label">日低</span>
      <span class="hs-val" style="color:var(--down)">${{ "%.2f"|format(s.low_price) if s.low_price else '—' }}</span>
    </div>
    <div class="hero-stat">
      <span class="hs-label">昨收</span>
      <span class="hs-val">${{ "%.2f"|format(s.prev_close) if s.prev_close else '—' }}</span>
    </div>
    <div class="hero-stat">
      <span class="hs-label">成交量</span>
      <span class="hs-val">{{ "{:,.0f}M".format(s.volume / 1e6) if s.volume else '—' }}</span>
    </div>
    <div class="hero-stat">
      <span class="hs-label">信號分</span>
      <span class="hs-val" style="color:{{ ring_color }}">{{ sc }}/100</span>
    </div>
  </div>
</div>

{# ── ROW 1: Core Thesis + Fundamentals ──────────────────────────────────── #}
<div class="row-2">

  {# Core Thesis #}
  <div class="card">
    <div class="sec-label">
      <span class="sec-pill">一</span>
      <span class="sec-title">核心結論 Core Thesis</span>
    </div>
    {% if s.ai_view %}
    <p style="font-size:13px;line-height:1.7;color:var(--text)">{{ s.ai_view }}</p>
    {% else %}
    <p style="font-size:12px;color:var(--text-2)">— 無 AI 分析資料 —</p>
    {% endif %}
    {% if s.sentiment and s.sentiment.score is not none %}
    {%- set ss = s.sentiment.score %}
    {%- set sn_cls = 'up' if ss >= 3 else ('down' if ss <= -3 else 'amber') %}
    <div style="margin-top:14px;padding:10px 14px;border-radius:8px;background:var(--elevated);border:1px solid var(--border)">
      <span style="font-family:var(--mono);font-size:10px;color:var(--text-2);text-transform:uppercase;letter-spacing:.04em">新聞情緒</span>
      <span style="font-family:var(--mono);font-size:13px;font-weight:700;color:var(--{{ sn_cls }});margin-left:10px">
        {{ "+" if ss > 0 else "" }}{{ ss }}
      </span>
      <span style="font-size:12px;color:var(--text);margin-left:8px">{{ s.sentiment.summary or '' }}</span>
    </div>
    {% endif %}
    {% if s.next_earnings %}
    <div style="margin-top:10px">
      <span class="earnings"><span class="pulse"></span>Earnings · {{ s.next_earnings }}</span>
    </div>
    {% endif %}
  </div>

  {# Fundamentals #}
  <div class="card">
    <div class="sec-label">
      <span class="sec-pill">二</span>
      <span class="sec-title">公司基本面 Fundamentals</span>
    </div>

    {# Analyst ratings #}
    {%- set ab = s.analyst_buy or 0 %}
    {%- set ah = s.analyst_hold or 0 %}
    {%- set as_ = s.analyst_sell or 0 %}
    {%- set at_ = ab + ah + as_ %}
    {% if at_ > 0 %}
    <div style="margin-bottom:14px">
      <div style="font-family:var(--mono);font-size:10px;font-weight:600;color:var(--text-2);text-transform:uppercase;letter-spacing:.06em;margin-bottom:6px">Analyst Ratings</div>
      <div class="analyst-bar">
        <div class="analyst-buy"  style="flex:{{ ab }}"></div>
        <div class="analyst-hold" style="flex:{{ ah }}"></div>
        <div class="analyst-sell" style="flex:{{ as_ }}"></div>
      </div>
      <div class="analyst-counts">
        <span class="buy">Buy {{ ab }}</span>
        <span class="hold">Hold {{ ah }}</span>
        <span class="sell">Sell {{ as_ }}</span>
        {% if s.analyst_period %}<span class="period">{{ s.analyst_period }}</span>{% endif %}
      </div>
    </div>
    {% endif %}

    {# 52W range #}
    {%- set w52h = s.week52_high or 0 %}
    {%- set w52l = s.week52_low or 0 %}
    {% if w52h and w52l and w52h != w52l %}
      {%- set rpct = ((s.price - w52l) / (w52h - w52l) * 100) | round(1) %}
      {%- set rpct_c = [0, [rpct, 100] | min] | max %}
    <div style="margin-bottom:14px">
      <div style="font-family:var(--mono);font-size:10px;font-weight:600;color:var(--text-2);text-transform:uppercase;letter-spacing:.06em;margin-bottom:4px">52W Range · {{ rpct_c }}% from low</div>
      <div class="range-bar">
        <div class="range-fill" style="width:{{ rpct_c }}%"></div>
        <div class="range-thumb" style="left:{{ rpct_c }}%"></div>
      </div>
      <div class="range-labels">
        <span>L ${{ "%.2f"|format(w52l) }}</span>
        <span>H ${{ "%.2f"|format(w52h) }}</span>
      </div>
    </div>
    {% endif %}

    <div class="check-list">
      <div class="check-item">MA5 {{ s.ma5 }} · MA20 {{ s.ma20 }} · MA60 {{ s.ma60 }}</div>
      <div class="check-item">RSI {{ "%.1f"|format(s.rsi) if s.rsi else '—' }} · Vol {{ "%.2f"|format(s.vol_ratio) if s.vol_ratio else '—' }}×</div>
      {% if s.pe_ratio %}
      <div class="check-item">P/E Ratio {{ "%.1f"|format(s.pe_ratio) }}</div>
      {% endif %}
      {% if s.macd is not none %}
      <div class="check-item">MACD {{ "%+.2f"|format(s.macd) }} · Hist {{ "%+.2f"|format(s.macd_hist) if s.macd_hist is not none else '—' }}</div>
      {% endif %}
    </div>
  </div>

</div><!-- /.row-2 -->

{# ── TECHNICAL ANALYSIS (full-width) ──────────────────────────────────────── #}
<div class="card">
  <div class="sec-label">
    <span class="sec-pill">技</span>
    <span class="sec-title">一 技術面分析 Technical Analysis</span>
    <span class="sec-sub">{{ s.ticker }} · last {{ ohlc_count }} bars</span>
  </div>
  <div class="tech-layout">
    <div class="chart-area">
      {% if has_ohlc %}
        {{ chart_svg | safe }}
        <div class="chart-legend">
          <span><span class="legend-dot" style="background:#f5b942"></span>MA5</span>
          <span><span class="legend-dot" style="background:#7aa2ff"></span>MA20</span>
          <span><span class="legend-dot" style="background:#b18cff"></span>MA60</span>
          <span><span class="legend-dot" style="background:#34d399"></span>Bull candle</span>
          <span><span class="legend-dot" style="background:#f87171"></span>Bear candle</span>
        </div>
      {% else %}
        <div class="no-chart">// No price history available</div>
      {% endif %}
    </div>

    <div class="tech-sidebar">
      {# Score ring #}
      {%- set ring_circ = 282.74 %}
      {%- set ring_dash = ring_circ * (sc / 100) %}
      <div class="ring-card">
        <div class="ring-large">
          <svg width="100" height="100">
            <circle cx="50" cy="50" r="45" stroke="rgba(255,255,255,0.06)" stroke-width="5" fill="none"/>
            <circle cx="50" cy="50" r="45" stroke="{{ ring_color }}" stroke-width="5" fill="none"
              stroke-dasharray="{{ '%.2f'|format(ring_dash) }} {{ '%.2f'|format(ring_circ) }}" stroke-linecap="round"/>
          </svg>
          <div class="ring-num" style="color:{{ ring_color }}">{{ sc }}</div>
        </div>
        <span class="strength-big {{ sc_class }}">{{ s.strength }}</span>
        <span class="breakout-badge" style="background:{{ 'rgba(52,211,153,0.10)' if sc >= 60 else ('rgba(245,185,66,0.10)' if sc >= 40 else 'rgba(248,113,113,0.10)') }};color:{{ ring_color }};border:1px solid {{ ring_color }}40">
          {{ s.strength_en or 'SIGNAL' }}
        </span>
        <div style="font-size:11px;color:var(--text-2);text-align:center">信號分數 {{ sc }}/100</div>
      </div>

      {# Technical signals list #}
      <div style="background:var(--elevated);border:1px solid var(--border);border-radius:12px;padding:14px">
        <div style="font-family:var(--mono);font-size:10px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px">Technical Signals</div>
        {% if s.signals %}
        <div class="check-list">
          {% for sig in s.signals %}
          <div class="check-item">{{ sig }}</div>
          {% endfor %}
        </div>
        {% else %}
        <div style="color:var(--muted);font-size:11px">— no signals —</div>
        {% endif %}
      </div>

      {# MA badge row #}
      <div>
        <div style="font-family:var(--mono);font-size:10px;color:var(--text-2);margin-bottom:6px;text-transform:uppercase;letter-spacing:.04em">Moving Averages</div>
        <div class="badge-row">
          <span class="ma-badge ma5">MA5 · {{ s.ma5 }}</span>
          <span class="ma-badge ma20">MA20 · {{ s.ma20 }}</span>
          <span class="ma-badge ma60">MA60 · {{ s.ma60 }}</span>
        </div>
        <div class="badge-row" style="margin-top:6px">
          <span class="rsi-badge">RSI · {{ "%.1f"|format(s.rsi) if s.rsi else '—' }}</span>
          <span class="vol-badge">Vol · {{ "%.1f"|format(s.vol_ratio) if s.vol_ratio else '—' }}×</span>
        </div>
      </div>
    </div>
  </div>
</div>

{# ── ROW 2: Key Catalysts + AI Analysis ──────────────────────────────────── #}
<div class="row-2">

  <div class="card">
    <div class="sec-label">
      <span class="sec-pill">三</span>
      <span class="sec-title">催化劑 Key Catalysts</span>
    </div>
    <div class="check-list">
      {% if s.signals %}
      {% for sig in s.signals %}
      <div class="num-item"><span style="color:var(--amber);font-weight:700;margin-right:6px">{{ loop.index }}.</span>{{ sig }}</div>
      {% endfor %}
      {% else %}
      <div style="color:var(--muted);font-size:12px">— 技術信號為空 —</div>
      {% endif %}
    </div>
    {% if s.news %}
    <div style="margin-top:14px;padding-top:12px;border-top:1px solid var(--border)">
      <div style="font-family:var(--mono);font-size:10px;font-weight:600;color:var(--text-2);text-transform:uppercase;letter-spacing:.04em;margin-bottom:8px">Latest News</div>
      {% for item in s.news[:3] %}
      <div style="font-size:12px;color:var(--text);padding:7px 9px;background:var(--elevated);border-radius:6px;border-left:2px solid var(--border-hi);margin-bottom:5px;line-height:1.5">
        {{ item.get('title') or item.get('headline') or '' }}
        {%- set src = item.get('publisher') or item.get('source') or '' %}
        {% if src %}<span style="display:block;font-family:var(--mono);font-size:9px;color:var(--text-2);margin-top:3px">{{ src }}</span>{% endif %}
      </div>
      {% endfor %}
    </div>
    {% endif %}
  </div>

  <div class="card">
    <div class="sec-label">
      <span class="sec-pill">四</span>
      <span class="sec-title">AI 影響分析</span>
    </div>
    {% if s.ai_view %}
    <div class="check-list">
      {# Split the ai_view into lines as check items if it has delimiters, else show as paragraph #}
      {% for line in s.ai_view.split('。') if line.strip() %}
      <div class="check-item">{{ line.strip() }}{% if not line.strip().endswith('。') %}{% endif %}</div>
      {% endfor %}
    </div>
    {% else %}
    <p style="font-size:12px;color:var(--text-2)">— 無 AI 分析資料 —</p>
    {% endif %}
  </div>

</div><!-- /.row-2 -->

{# ── ROW 3a: Key Levels + Scenarios + Bull/Bear ───────────────────────────── #}
<div class="row-3">

  {# 六 Key Levels #}
  <div class="card">
    <div class="sec-label">
      <span class="sec-pill">六</span>
      <span class="sec-title">關鍵價位 Key Levels</span>
    </div>
    <table class="levels-table">
      {% for lvl in key_levels %}
      {%- set dot_color = '#f87171' if lvl.tier == 'resistance' else ('#34d399' if lvl.tier == 'support' else '#f5b942') %}
      {%- set val_color = '#f87171' if lvl.tier == 'resistance' else ('#34d399' if lvl.tier == 'support' else '#f5b942') %}
      <tr>
        <td class="level-label">
          <span class="level-dot" style="background:{{ dot_color }}"></span>{{ lvl.l }}
        </td>
        <td class="level-val" style="color:{{ val_color }}">${{ lvl.v }}</td>
      </tr>
      {% else %}
      <tr><td colspan="2" style="color:var(--muted);font-size:12px">— 無法計算 —</td></tr>
      {% endfor %}
    </table>
  </div>

  {# 七 Scenarios #}
  <div class="card">
    <div class="sec-label">
      <span class="sec-pill">七</span>
      <span class="sec-title">未來劇本 Scenarios</span>
    </div>
    <div style="display:flex;flex-direction:column;gap:10px">
      {% for scen in scenarios %}
      {%- set bar_color = '#34d399' if scen.c == 'up' else ('#f87171' if scen.c == 'down' else '#f5b942') %}
      <div class="scenario-card">
        <div class="scen-top">
          <span class="scen-title">{{ scen.i }} {{ scen.t }}</span>
          <span class="prob-pct" style="color:{{ bar_color }}">{{ scen.p }}%</span>
        </div>
        <div class="prob-bar">
          <div class="prob-fill" style="width:{{ scen.p }}%;background:{{ bar_color }}"></div>
        </div>
        <div style="font-size:11px;color:var(--text-2)">{{ scen.desc }}</div>
        <div style="font-family:var(--mono);font-size:10px;color:var(--text);font-weight:600">{{ scen.range }}</div>
      </div>
      {% endfor %}
    </div>
  </div>

  {# 五 Pullback / 52W stats (same slot as JSX 五) #}
  <div class="card">
    <div class="sec-label">
      <span class="sec-pill">五</span>
      <span class="sec-title">歷史回調 Pullback Stats</span>
    </div>
    {%- set w52h = s.week52_high or 0 %}
    {%- set w52l = s.week52_low or 0 %}
    {% if w52h and w52l and w52h != w52l %}
      {%- set rpct = ((s.price - w52l) / (w52h - w52l) * 100) | round(1) %}
      {%- set rpct_c = [0, [rpct, 100] | min] | max %}
      {%- set from_high_pct = ((s.price - w52h) / w52h * 100) | round(1) %}
    <div style="margin-bottom:14px">
      <div style="font-size:12px;color:var(--text-2);margin-bottom:8px">52 週位置</div>
      <div class="range-bar">
        <div class="range-fill" style="width:{{ rpct_c }}%"></div>
        <div class="range-thumb" style="left:{{ rpct_c }}%"></div>
      </div>
      <div class="range-labels">
        <span>L ${{ "%.2f"|format(w52l) }}</span>
        <span>H ${{ "%.2f"|format(w52h) }}</span>
      </div>
      <div style="margin-top:8px;font-family:var(--mono);font-size:12px;color:var(--text)">
        距低點 <span style="color:var(--up)">+{{ rpct_c }}%</span> ·
        距高點 <span style="color:var(--down)">{{ from_high_pct }}%</span>
      </div>
    </div>
    {% else %}
    <div style="color:var(--muted);font-size:12px">— 無 52W 數據 —</div>
    {% endif %}

    {# Support zone #}
    <div style="padding:12px;background:rgba(52,211,153,0.05);border:1px solid rgba(52,211,153,0.15);border-radius:8px;margin-top:10px">
      <div style="font-family:var(--mono);font-size:10px;color:var(--up);font-weight:700;text-transform:uppercase;letter-spacing:.04em;margin-bottom:5px">Support Zone</div>
      {% for lvl in key_levels if lvl.tier == 'support' %}
      <div style="font-family:var(--mono);font-size:12px;color:var(--text)">{{ lvl.l }} · ${{ lvl.v }}</div>
      {% else %}
      <div style="font-size:11px;color:var(--text-2)">Based on MA & 52W data</div>
      {% endfor %}
    </div>
  </div>

</div><!-- /.row-3 -->

{# ── ROW 3b: Bull/Bear Targets + Key Risks + Strategy ─────────────────────── #}
<div class="row-3">

  {# 八 Bull/Bear Targets #}
  <div class="card">
    <div class="sec-label">
      <span class="sec-pill">八</span>
      <span class="sec-title">牛熊情境目標 Targets</span>
    </div>
    <table class="bb-table">
      <thead>
        <tr>
          <th>情境</th>
          <th>觸發條件</th>
          <th>目標區間</th>
        </tr>
      </thead>
      <tbody>
      {% for row in bull_bear %}
      {%- set tc = '#34d399' if row.tier in ('up','up_soft') else ('#f5b942' if row.tier == 'amber' else ('#f87171' if row.tier == 'down' else '#8a8c98')) %}
      <tr>
        <td style="color:{{ tc }};font-weight:600">{{ row.s }}</td>
        <td style="color:var(--text-2)">{{ row.c }}</td>
        <td class="target-val" style="color:{{ tc }}">{{ row.t }}</td>
      </tr>
      {% endfor %}
      </tbody>
    </table>
  </div>

  {# 九 Key Risks #}
  <div class="card">
    <div class="sec-label">
      <span class="sec-pill">九</span>
      <span class="sec-title">主要風險 Key Risks</span>
    </div>
    <div style="display:flex;flex-direction:column;gap:8px;margin-top:4px">
      {% for risk in risks %}
      <div class="warn-item">{{ risk }}</div>
      {% endfor %}
    </div>
  </div>

  {# 十 Strategy #}
  <div class="card">
    <div class="sec-label">
      <span class="sec-pill">十</span>
      <span class="sec-title">投資策略 Strategy</span>
    </div>
    <div style="display:flex;flex-direction:column;gap:10px">
      {% for strat in strategy %}
      <div class="strat-card">
        <div>
          <div class="strat-type">{{ strat.type }}</div>
          <div class="strat-sub">{{ strat.sub }}</div>
        </div>
        <div class="strat-action">{{ strat.action }}</div>
        {% if strat.get('stop') and strat.stop != '—' %}
        <div class="strat-meta">
          <span class="strat-pill stop">STOP {{ strat.stop }}</span>
          {% if strat.get('target') %}<span class="strat-pill target">TARGET {{ strat.target }}</span>{% endif %}
        </div>
        {% elif strat.get('note') %}
        <div class="strat-note">{{ strat.note }}</div>
        {% endif %}
      </div>
      {% endfor %}
    </div>
  </div>

</div><!-- /.row-3 -->

{# ── SUMMARY FOOTER CARD ───────────────────────────────────────────────────── #}
<div class="summary-card">
  <div class="summary-text">
    <div class="summary-title">{{ s.ticker }} · 綜合分析摘要</div>
    <div class="summary-body">
      {{ s.ai_view or ('技術信號分數 ' ~ sc ~ '/100，強度評級：' ~ s.strength ~ '。') }}
    </div>
  </div>
  <div class="verdict-block">
    <div class="verdict-label {{ verdict.cls }}">{{ verdict.label }}</div>
    <div class="verdict-en">{{ verdict.en }}</div>
  </div>
</div>

<div class="footer">⚠ Generated by AI · for research only · not investment advice · trade at your own risk</div>

</div><!-- /.page-detail -->

</body>
</html>
"""


# ── Public API ────────────────────────────────────────────────────────────────

def generate_stock_detail_page(s: dict, date: str, output_dir: str) -> str:
    """Generate a detail HTML page for a single stock.

    Args:
        s:          Stock result dict (same shape as report_generator uses).
        date:       Report date string e.g. "2024/11/14".
        output_dir: Path to the outputs directory.

    Returns:
        Absolute path to the written HTML file.
    """
    ohlc       = s.get("ohlc", [])
    chart_svg  = _build_candle_svg(ohlc) if len(ohlc) >= 10 else ""
    key_levels = _build_key_levels(s)
    scenarios  = _build_scenarios(s)
    bull_bear  = _build_bull_bear_targets(s)
    risks      = _build_risks(s)
    strategy   = _build_strategy(s)
    verdict    = _build_verdict(s)

    from jinja2 import Environment
    env = Environment()

    html = env.from_string(DETAIL_HTML).render(
        s=s,
        date=date,
        chart_svg=chart_svg,
        key_levels=key_levels,
        scenarios=scenarios,
        bull_bear=bull_bear,
        risks=risks,
        strategy=strategy,
        verdict=verdict,
        has_ohlc=bool(chart_svg),
        ohlc_count=len(ohlc),
    )

    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{s['ticker']}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
