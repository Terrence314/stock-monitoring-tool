"""stock_detail.py — Per-ticker HTML detail page generator.

Generates outputs/TICKER.html for each stock using the V1 terminal dark aesthetic.
Called from report_generator.generate_dashboard() after the main index.html is written.
"""

import os
import math
from datetime import datetime, timezone, timedelta
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

def _build_candle_svg(ohlc: list, width: int = 760, height: int = 400, markers: list | None = None) -> str:
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

    # ── Signal markers (BUY ▲ below bar / SELL ▼ above bar) ──────────────────
    if markers:
        date_idx = {b.get("d"): i for i, b in enumerate(ohlc) if b.get("d")}
        for m in markers:
            mi = date_idx.get(m.get("d"))
            if mi is None:
                continue
            mx = bx(mi)
            label = m.get("label", "")
            if m.get("side") == "buy":
                ty = px(lows[mi]) + 6
                parts.append(
                    f'<polygon points="{mx:.1f},{ty:.1f} {mx-5:.1f},{ty+8:.1f} {mx+5:.1f},{ty+8:.1f}" '
                    f'fill="#34d399" stroke="#0b0c10" stroke-width="0.5">'
                    f'<title>🟢 {m.get("d","")} {label}</title></polygon>'
                )
            else:
                ty = px(highs[mi]) - 6
                parts.append(
                    f'<polygon points="{mx:.1f},{ty:.1f} {mx-5:.1f},{ty-8:.1f} {mx+5:.1f},{ty-8:.1f}" '
                    f'fill="#f87171" stroke="#0b0c10" stroke-width="0.5">'
                    f'<title>🔴 {m.get("d","")} {label}</title></polygon>'
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


# ── Pullback SVG ──────────────────────────────────────────────────────────────

def _build_pullback_svg(ohlc: list, width: int = 440, height: int = 150) -> str:
    """Area chart of close prices with peak + max-drawdown annotations."""
    if not ohlc or len(ohlc) < 10:
        return ""
    closes = [b.get("c", 0) for b in ohlc]
    n = len(closes)

    # Running peak and drawdown at each bar
    running_max = closes[0]
    peak_idx = 0
    drawdowns = []
    for i, c in enumerate(closes):
        if c > running_max:
            running_max = c
            peak_idx = i
        drawdowns.append((c - running_max) / running_max * 100 if running_max else 0)

    max_dd   = min(drawdowns)
    trough_idx = drawdowns.index(max_dd)
    cur_dd   = drawdowns[-1]

    # Determine a secondary drawdown (another trough ≥ 5% besides the deepest)
    sec_dd = 0.0
    sec_idx = -1
    for i, d in enumerate(drawdowns):
        if d <= -5 and d != max_dd and abs(d - max_dd) > 3:
            if d < sec_dd or sec_dd == 0.0:
                sec_dd = d
                sec_idx = i

    mn = min(closes) * 0.97
    mx = max(closes) * 1.03
    rng = mx - mn or 1

    pl, pr, pt, pb = 10, 10, 14, 18
    cw = width - pl - pr
    ch = height - pt - pb

    def cx(i): return pl + (i / (n - 1)) * cw if n > 1 else pl
    def cy(p): return pt + ch - ((p - mn) / rng) * ch

    xy = [(cx(i), cy(closes[i])) for i in range(n)]
    line_d = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    area_d = (line_d + f" L {xy[-1][0]:.1f},{pt + ch}"
              + f" L {xy[0][0]:.1f},{pt + ch} Z")

    color = "#34d399" if closes[-1] >= closes[0] else "#f87171"
    parts = [
        f'<svg width="100%" viewBox="0 0 {width} {height}" '
        f'preserveAspectRatio="none" xmlns="http://www.w3.org/2000/svg">'
    ]

    # Support zone shading (bottom 22% of chart area)
    sz_y = pt + ch * 0.72
    parts.append(
        f'<rect x="{pl}" y="{sz_y:.1f}" width="{cw}" '
        f'height="{pt + ch - sz_y:.1f}" fill="rgba(52,211,153,0.06)" rx="3"/>'
    )

    # Area + line
    parts.append(f'<path d="{area_d}" fill="{color}" fill-opacity="0.10"/>')
    parts.append(
        f'<path d="{line_d}" stroke="{color}" stroke-width="1.5" '
        f'fill="none" stroke-linejoin="round"/>'
    )

    # Peak marker
    px_, py_ = xy[peak_idx]
    parts.append(
        f'<circle cx="{px_:.1f}" cy="{py_:.1f}" r="3.5" '
        f'fill="#f5b942" stroke="#0b0c10" stroke-width="1.5"/>'
    )
    peak_price = closes[peak_idx]
    parts.append(
        f'<text x="{px_:.1f}" y="{py_ - 6:.1f}" text-anchor="middle" '
        f'font-size="9" fill="#f5b942" font-family="JetBrains Mono,monospace" font-weight="700">'
        f'{peak_price:.2f}</text>'
    )

    # Max drawdown annotation
    if max_dd < -5:
        tx, ty = xy[trough_idx]
        mid_x = (px_ + tx) / 2
        mid_y = (py_ + ty) / 2 - 6
        parts.append(
            f'<line x1="{px_:.1f}" y1="{py_:.1f}" x2="{tx:.1f}" y2="{ty:.1f}" '
            f'stroke="#f87171" stroke-dasharray="2 2" stroke-width="1" stroke-opacity="0.7"/>'
        )
        parts.append(
            f'<text x="{mid_x:.1f}" y="{mid_y:.1f}" text-anchor="middle" '
            f'font-size="9" fill="#f87171" font-family="JetBrains Mono,monospace" font-weight="700">'
            f'{max_dd:.0f}%</text>'
        )

    # Secondary drawdown annotation
    if sec_dd <= -5 and sec_idx >= 0:
        sx, sy = xy[sec_idx]
        # Find the peak before this secondary trough
        prev_peak = max(closes[:sec_idx + 1]) if sec_idx > 0 else closes[0]
        prev_pk_y = cy(prev_peak)
        prev_pk_x = cx(closes.index(prev_peak))
        parts.append(
            f'<text x="{sx:.1f}" y="{sy - 5:.1f}" text-anchor="middle" '
            f'font-size="8" fill="#ff8a4d" font-family="JetBrains Mono,monospace" font-weight="600">'
            f'{sec_dd:.0f}%</text>'
        )

    # Current drawdown (if meaningful)
    if cur_dd < -5:
        ex, ey = xy[-1]
        parts.append(
            f'<text x="{ex - 3:.1f}" y="{ey - 6:.1f}" text-anchor="end" '
            f'font-size="9" fill="#f87171" font-family="JetBrains Mono,monospace">'
            f'{cur_dd:.0f}%</text>'
        )

    parts.append("</svg>")
    return "".join(parts)


# ── Core Bullet Parser ────────────────────────────────────────────────────────

def _parse_core_bullets(ai_view: str, signals: list) -> list[str]:
    """Extract 4–6 concise bullet points for the core thesis box."""
    bullets = []
    if ai_view:
        for line in ai_view.split("\n"):
            clean = line.strip().lstrip("•·－–-*›→「」【】").strip()
            # Skip blank, very short, or header-like lines
            if 15 < len(clean) < 120 and not clean.endswith("：") and not clean.endswith(":"):
                bullets.append(clean)
            if len(bullets) >= 5:
                break
    # Supplement with technical signals if fewer than 3 bullets
    for sig in (signals or []):
        if sig and len(sig) > 10 and sig not in bullets:
            bullets.append(sig)
        if len(bullets) >= 5:
            break
    return bullets[:5]


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
<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">
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

/* ── CORE THESIS BULLETS ──────────────────────────────────────────── */
.core-bullets { display: flex; flex-direction: column; gap: 8px; margin-top: 4px; }
.core-bullet {
  display: flex; align-items: flex-start; gap: 10px;
  font-size: 13px; line-height: 1.55; color: var(--text);
  padding: 8px 10px; background: var(--elevated);
  border-radius: 7px; border-left: 2px solid var(--blue);
}
.core-bullet::before {
  content: '›'; color: var(--blue); font-size: 14px;
  font-weight: 700; line-height: 1.4; flex-shrink: 0;
}

/* ── KEY LEVEL BOXES ──────────────────────────────────────────────── */
.level-boxes { display: flex; flex-direction: column; gap: 6px; margin-top: 4px; }
.lbox {
  display: flex; align-items: center; justify-content: space-between;
  padding: 9px 14px; border-radius: 8px;
  font-size: 12px; font-weight: 600; border: 1px solid transparent;
}
.lbox-label { font-size: 12px; color: var(--text); }
.lbox-val { font-family: var(--mono); font-size: 13px; font-weight: 700; }
.lbox.resistance {
  background: rgba(248,113,113,0.10); border-color: rgba(248,113,113,0.30);
}
.lbox.resistance .lbox-label { color: #fca5a5; }
.lbox.resistance .lbox-val   { color: var(--down); }
.lbox.support {
  background: rgba(52,211,153,0.09); border-color: rgba(52,211,153,0.25);
}
.lbox.support .lbox-label { color: #6ee7b7; }
.lbox.support .lbox-val   { color: var(--up); }
.lbox.neutral {
  background: rgba(122,162,255,0.09); border-color: rgba(122,162,255,0.25);
}
.lbox.neutral .lbox-label { color: #93c5fd; }
.lbox.neutral .lbox-val   { color: var(--blue); }
.lbox-tier-tag {
  font-family: var(--mono); font-size: 9px; font-weight: 700;
  letter-spacing: 0.04em; padding: 1px 6px; border-radius: 3px;
  margin-left: 8px;
}
.lbox.resistance .lbox-tier-tag { background: rgba(248,113,113,0.15); color: var(--down); }
.lbox.support    .lbox-tier-tag { background: rgba(52,211,153,0.12);  color: var(--up); }
.lbox.neutral    .lbox-tier-tag { background: rgba(122,162,255,0.12); color: var(--blue); }

/* ── SCENARIO CARDS (enhanced) ───────────────────────────────────── */
.scen-cards { display: flex; flex-direction: column; gap: 8px; }
.scen-card-v2 {
  padding: 12px 14px; border-radius: 10px;
  border: 1px solid var(--border);
}
.scen-card-v2.up   { background: rgba(52,211,153,0.06); border-color: rgba(52,211,153,0.20); }
.scen-card-v2.down { background: rgba(248,113,113,0.06); border-color: rgba(248,113,113,0.20); }
.scen-card-v2.amber { background: rgba(245,185,66,0.06); border-color: rgba(245,185,66,0.20); }
.scen-head { display: flex; align-items: center; justify-content: space-between; gap: 8px; margin-bottom: 6px; }
.scen-icon-title { display: flex; align-items: center; gap: 8px; font-size: 13px; font-weight: 600; }
.scen-pct { font-family: var(--mono); font-size: 13px; font-weight: 700; }
.scen-pbar { height: 4px; background: var(--elevated); border-radius: 2px; margin-bottom: 6px; }
.scen-pfill { height: 100%; border-radius: 2px; }
.scen-range { font-family: var(--mono); font-size: 11px; font-weight: 600; margin-top: 4px; }
.scen-desc-v2 { font-size: 11px; color: var(--text-2); line-height: 1.4; }

/* ── REPORT SUBTITLE BADGE ───────────────────────────────────────── */
.report-badge {
  display: inline-flex; align-items: center; gap: 6px;
  font-family: var(--mono); font-size: 10px; font-weight: 700;
  letter-spacing: 0.06em; text-transform: uppercase;
  padding: 3px 10px; border-radius: 10px;
  background: linear-gradient(90deg, rgba(122,162,255,0.15), rgba(177,140,255,0.15));
  border: 1px solid rgba(177,140,255,0.30);
  color: var(--purple);
}

/* ── PULLBACK SECTION ANNOTATIONS ───────────────────────────────── */
.pullback-stats {
  display: flex; gap: 8px; flex-wrap: wrap; margin-top: 10px;
}
.pb-stat {
  padding: 6px 10px; border-radius: 7px; text-align: center;
  background: var(--elevated); border: 1px solid var(--border);
}
.pb-stat-val { font-family: var(--mono); font-size: 14px; font-weight: 700; }
.pb-stat-lbl { font-size: 10px; color: var(--text-2); margin-top: 2px; }

/* ── Mobile ≤ 768px ──────────────────────────────────────────────────── */
@media (max-width: 768px) {
  .page        { padding: 12px 12px 40px; }
  .hero-ticker { font-size: 24px !important; }
  .hero-price  { font-size: 24px !important; }
  .back-link   { font-size: 12px !important; padding: 8px 0 !important; }
  .section-label { font-size: 9px !important; padding: 2px 7px !important; }
  .card        { padding: 14px; }
  .targets-tbl { font-size: 11px; }
  .targets-tbl td { padding: 8px 8px; }
  .chart-area  { overflow-x: auto; }
  .chart-area svg { min-width: 560px; width: 760px !important; }
  .hero-stats  { grid-template-columns: repeat(3, 1fr) !important; }
}
@media (max-width: 480px) {
  .hero-ticker { font-size: 20px !important; }
  .hero-price  { font-size: 20px !important; }
  .hero-stats  { grid-template-columns: repeat(2, 1fr) !important; }
  .badge-row   { gap: 4px; }
}
</style>
</head>
<body>

<!-- TOP BAR -->
<div class="topbar">
  <a href="./index.html" class="back-link">← 返回</a>
  {% if prev_ticker %}
  <a href="./{{ prev_ticker }}.html" class="back-link" title="Previous: {{ prev_ticker }}" style="padding:5px 9px">‹ {{ prev_ticker }}</a>
  {% endif %}
  <span class="topbar-ticker">{{ s.ticker }}</span>
  <span class="topbar-name" style="display:none" id="topbar-fullname">{{ s.name }}</span>
  <div class="spacer"></div>
  {% if next_ticker %}
  <a href="./{{ next_ticker }}.html" class="back-link" title="Next: {{ next_ticker }}" style="padding:5px 9px">{{ next_ticker }} ›</a>
  {% endif %}
  <span class="topbar-date">{{ date }}</span>
  {% if generated_at %}<span class="topbar-date" style="opacity:0.65" title="When this page was generated — refresh to get the latest">· updated {{ generated_at }}</span>{% endif %}
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
      <div style="margin-top:10px">
        <span class="report-badge">✦ 綜合研判報告</span>
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
    {% if core_bullets %}
    <div class="core-bullets">
      {% for b in core_bullets %}
      <div class="core-bullet">{{ b }}</div>
      {% endfor %}
    </div>
    {% elif s.ai_view %}
    <p style="font-size:13px;line-height:1.7;color:var(--text)">{{ s.ai_view }}</p>
    {% else %}
    <p style="font-size:12px;color:var(--text-2)">— 無 AI 分析資料 —</p>
    {% endif %}
    {% if s.sentiment and s.sentiment.score is not none %}
    {%- set ss = s.sentiment.score %}
    {%- set sn_cls = 'up' if ss >= 3 else ('down' if ss <= -3 else 'amber') %}
    <div style="margin-top:12px;padding:9px 12px;border-radius:8px;background:var(--elevated);border:1px solid var(--border);display:flex;align-items:center;gap:10px">
      <span style="font-family:var(--mono);font-size:10px;color:var(--text-2);text-transform:uppercase;letter-spacing:.04em">新聞情緒</span>
      <span style="font-family:var(--mono);font-size:14px;font-weight:700;color:var(--{{ sn_cls }})">
        {{ "+" if ss > 0 else "" }}{{ ss }}
      </span>
      <span style="font-size:12px;color:var(--text)">{{ s.sentiment.summary or '' }}</span>
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

      {# Score indicator breakdown — mirrors actual 5-factor scoring in technical_analysis.py #}
      <div style="background:var(--elevated);border:1px solid var(--border);border-radius:12px;padding:14px">
        <div style="font-family:var(--mono);font-size:10px;font-weight:700;color:var(--text-2);text-transform:uppercase;letter-spacing:.06em;margin-bottom:10px">Score Breakdown <span style="font-weight:400;opacity:.5">(5 × 20 = 100)</span></div>
        {#- F1: Trend alignment -#}
        {%- set _c = s.price if s.price else 0 %}
        {%- set _f1 = 20 if (s.ma5 and s.ma20 and s.ma60 and _c > s.ma5 and s.ma5 > s.ma20 and s.ma20 > s.ma60)
                     else (12 if (s.ma20 and s.ma60 and _c > s.ma20 and s.ma20 > s.ma60)
                     else (5 if (s.ma60 and _c > s.ma60) else 0)) %}
        {#- F2: RSI -#}
        {%- set _rsi = s.rsi or 50 %}
        {%- set _f2 = 20 if _rsi >= 45 and _rsi <= 70
                     else (10 if _rsi >= 30 and _rsi < 45
                     else (8 if _rsi < 30
                     else (5 if _rsi > 75 else 0))) %}
        {#- F3: MACD -#}
        {%- set _mh = s.macd_hist or 0 %}
        {%- set _f3 = 20 if (_mh > 0 and s.macd and s.macd > 0)
                     else (12 if _mh > 0
                     else (8 if _mh < 0 and _mh > -0.1
                     else 0)) %}
        {#- F4: Volume -#}
        {%- set _vr = s.vol_ratio or 0 %}
        {%- set _f4 = 20 if _vr >= 1.5 else (10 if _vr >= 1.0 else 0) %}
        {#- F5: MA60 distance -#}
        {%- set _f5 = 0 %}
        {%- if s.ma60 and s.ma60 > 0 and s.price %}
          {%- set _dist = (s.price - s.ma60) / s.ma60 * 100 %}
          {%- set _f5 = 20 if _dist > 5 else (12 if _dist > 0 else 0) %}
        {%- endif %}
        {%- set items = [
          ('① Trend',  _f1, 20, 'MA stack alignment — price > MA5 > MA20 > MA60'),
          ('② RSI',    _f2, 20, '45–70 rising = 20 · 30–45 = 10 · <30 oversold = 8'),
          ('③ MACD',   _f3, 20, 'Golden cross expanding = 20 · cross only = 12 · converging = 8'),
          ('④ Volume', _f4, 20, '≥1.5× = 20 · 1.0–1.5× = 10 · <1.0× = 0'),
          ('⑤ MA60',   _f5, 20, '>5% above MA60 = 20 · above = 12 · below = 0'),
        ] %}
        {%- set score_est = _f1 + _f2 + _f3 + _f4 + _f5 %}
        {% for label, pts, max_pts, tip in items %}
        {%- set pct = (pts / max_pts * 100) | round %}
        {%- set bar_c = '#34d399' if pts >= 12 else ('#fbbf24' if pts > 0 else '#52545e') %}
        <div style="display:flex;align-items:center;gap:8px;margin-bottom:6px" title="{{ tip }}">
          <span style="font-family:var(--mono);font-size:9px;color:var(--text-2);min-width:64px">{{ label }}</span>
          <div style="flex:1;height:4px;background:var(--border);border-radius:2px;overflow:hidden">
            <div style="height:100%;width:{{ pct }}%;background:{{ bar_c }};border-radius:2px;transition:width .3s"></div>
          </div>
          <span style="font-family:var(--mono);font-size:9px;font-weight:700;color:{{ bar_c }};min-width:24px;text-align:right">{{ pts }}</span>
        </div>
        {% endfor %}
        <div style="border-top:1px solid var(--border);margin-top:4px;padding-top:4px;display:flex;justify-content:space-between;font-family:var(--mono);font-size:9px;color:var(--text-2)">
          <span>Estimated</span>
          <span style="font-weight:700;color:{{ '#34d399' if score_est >= 75 else ('#fbbf24' if score_est >= 50 else 'var(--text-2)') }}">{{ score_est }}/100</span>
        </div>
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
          {%- if s.get('bb_pct') is not none and s.bb_pct is not none %}
          {%- set _bp = s.bb_pct %}
          {%- set _bc = '#60a5fa' if _bp < 0.20 else ('#34d399' if _bp <= 0.60 else ('#fb923c' if _bp <= 0.85 else '#f87171')) %}
          <span style="font-family:var(--mono);font-size:10px;font-weight:600;padding:3px 7px;border-radius:5px;color:{{ _bc }};background:{{ _bc }}14;border:1px solid {{ _bc }}33"
                title="BB %B: {{ '%.2f'|format(_bp) }} — 0=lower band, 1=upper band. {% if s.get('bb_squeeze') %}⚡ SQUEEZE active{% elif _bp < 0.20 %}Near lower band{% elif _bp <= 0.60 %}Mid-range{% elif _bp <= 0.85 %}Approaching upper{% else %}Near upper band{% endif %}">
            BB {{ "%.2f"|format(_bp) }}{% if s.get('bb_squeeze') %} ⚡{% endif %}</span>
          {%- endif %}
          {%- if s.get('kd_k') is not none and s.kd_k is not none %}
          {%- set _kd = s.kd_k %}
          {%- set _kdc = '#60a5fa' if _kd < 20 else ('#2dd4bf' if _kd < 30 else ('#94a3b8' if _kd < 70 else ('#fb923c' if _kd < 80 else '#f87171'))) %}
          <span style="font-family:var(--mono);font-size:10px;font-weight:600;padding:3px 7px;border-radius:5px;color:{{ _kdc }};background:{{ _kdc }}14;border:1px solid {{ _kdc }}33"
                title="KD(9,3,3): K={{ '%.1f'|format(_kd) }} · D={{ '%.1f'|format(s.kd_d) if s.kd_d else '—' }}. {% if s.get('kd_golden_cross_low') %}🎯 Bottom golden cross{% elif s.get('kd_oversold') %}🔵 Oversold zone{% elif _kd > 80 %}Overbought{% else %}Neutral{% endif %}">
            KD · {{ "%.0f"|format(_kd) }}{% if s.get('kd_golden_cross_low') %} 🎯{% elif s.get('kd_oversold') %} 🔵{% endif %}</span>
          {%- endif %}
        </div>
      </div>
    </div>
  </div>
</div>

{# ── LIVE CHART (TradingView real-time embed, loads on scroll into view) ─── #}
<div class="card" id="live-chart-card">
  <div class="sec-label">
    <span class="sec-pill">live</span>
    <span class="sec-title">即時圖表 Live Chart</span>
    <span class="sec-sub">TradingView 即時報價 · real-time via CBOE BZX · 5-min candles</span>
  </div>
  <div id="tv-chart-container" style="height:480px;margin-top:12px;border-radius:12px;overflow:hidden;background:var(--elevated)">
    <div id="tv-chart-inner" style="height:100%;display:flex;align-items:center;justify-content:center;color:var(--text-2);font-family:var(--mono);font-size:11px">loading live chart…</div>
  </div>
</div>
<script>
(function() {
  var card = document.getElementById('live-chart-card');
  if (!card) return;
  var loaded = false;
  function loadWidget() {
    if (loaded) return;
    loaded = true;
    var inner = document.getElementById('tv-chart-inner');
    inner.textContent = '';
    inner.style.display = 'block';
    var s = document.createElement('script');
    s.src = 'https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js';
    s.async = true;
    s.innerHTML = JSON.stringify({
      symbol: '{{ tv_symbol }}',
      interval: '5',
      timezone: 'Asia/Hong_Kong',
      theme: 'dark',
      style: '1',
      locale: 'zh_TW',
      hide_top_toolbar: false,
      hide_legend: false,
      allow_symbol_change: false,
      studies: ['MASimple@tv-basicstudies'],
      autosize: true
    });
    inner.appendChild(s);
  }
  if ('IntersectionObserver' in window) {
    var io = new IntersectionObserver(function(entries) {
      if (entries[0].isIntersecting) { loadWidget(); io.disconnect(); }
    }, { rootMargin: '200px' });
    io.observe(card);
  } else {
    loadWidget();
  }
})();
</script>

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
    <div class="level-boxes">
      {% for lvl in key_levels %}
      <div class="lbox {{ lvl.tier }}">
        <span class="lbox-label">
          {{ lvl.l }}
          <span class="lbox-tier-tag">{{ '壓力' if lvl.tier == 'resistance' else ('支撐' if lvl.tier == 'support' else '關鍵') }}</span>
        </span>
        <span class="lbox-val">${{ lvl.v }}</span>
      </div>
      {% else %}
      <div style="color:var(--muted);font-size:12px;padding:10px 0">— 無法計算 —</div>
      {% endfor %}
    </div>
  </div>

  {# 七 Scenarios #}
  <div class="card">
    <div class="sec-label">
      <span class="sec-pill">七</span>
      <span class="sec-title">未來劇本 Scenarios</span>
    </div>
    <div class="scen-cards">
      {% for scen in scenarios %}
      {%- set bar_color = '#34d399' if scen.c == 'up' else ('#f87171' if scen.c == 'down' else '#f5b942') %}
      <div class="scen-card-v2 {{ scen.c }}">
        <div class="scen-head">
          <div class="scen-icon-title">
            <span>{{ scen.i }}</span>
            <span style="color:{{ bar_color }}">{{ scen.t }}</span>
          </div>
          <span class="scen-pct" style="color:{{ bar_color }}">{{ scen.p }}%</span>
        </div>
        <div class="scen-pbar">
          <div class="scen-pfill" style="width:{{ scen.p }}%;background:{{ bar_color }}"></div>
        </div>
        <div class="scen-desc-v2">{{ scen.desc }}</div>
        <div class="scen-range" style="color:{{ bar_color }}">目標：{{ scen.range }}</div>
      </div>
      {% endfor %}
    </div>
  </div>

  {# 五 Pullback Stats #}
  <div class="card">
    <div class="sec-label">
      <span class="sec-pill">五</span>
      <span class="sec-title">歷史回調統計（日線）</span>
    </div>
    {% if pullback_svg %}
    {{ pullback_svg | safe }}
    {% endif %}

    {%- set w52h = s.week52_high or 0 %}
    {%- set w52l = s.week52_low or 0 %}
    <div class="pullback-stats">
      {% if w52h %}
      <div class="pb-stat">
        <div class="pb-stat-val" style="color:var(--amber)">${{ "%.2f"|format(w52h) }}</div>
        <div class="pb-stat-lbl">52W 高點</div>
      </div>
      {% endif %}
      {% if w52l %}
      <div class="pb-stat">
        <div class="pb-stat-val" style="color:var(--down)">${{ "%.2f"|format(w52l) }}</div>
        <div class="pb-stat-lbl">52W 低點</div>
      </div>
      {% endif %}
      {% if w52h and w52l and w52h != w52l %}
      {%- set from_high = ((s.price - w52h) / w52h * 100) | round(1) %}
      <div class="pb-stat">
        <div class="pb-stat-val" style="color:{{ 'var(--down)' if from_high < 0 else 'var(--up)' }}">{{ '%+.1f'|format(from_high) }}%</div>
        <div class="pb-stat-lbl">距高點</div>
      </div>
      {% endif %}
    </div>

    {# Support zone tag #}
    {% set supports = key_levels | selectattr('tier', 'equalto', 'support') | list %}
    {% if supports %}
    <div style="padding:10px 12px;background:rgba(52,211,153,0.06);border:1px solid rgba(52,211,153,0.18);border-radius:8px;margin-top:10px">
      <div style="font-family:var(--mono);font-size:9px;color:var(--up);font-weight:700;text-transform:uppercase;letter-spacing:.06em;margin-bottom:5px">關鍵支撐帶</div>
      {% for lvl in supports %}
      <div style="font-family:var(--mono);font-size:12px;color:var(--text)">{{ lvl.l }} · ${{ lvl.v }}</div>
      {% endfor %}
    </div>
    {% endif %}
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
<div class="summary-card" style="
  background: linear-gradient(135deg, var(--surface) 60%, var(--elevated));
  border: 1px solid var(--border-hi);
  border-radius: 14px; padding: 22px 28px;
  display: flex; align-items: center; gap: 24px; flex-wrap: wrap;
">
  <div class="summary-text" style="flex:1; min-width:200px">
    <div class="summary-title" style="font-size:11px;font-family:var(--mono);color:var(--text-2);text-transform:uppercase;letter-spacing:.06em;margin-bottom:8px">
      ✦ {{ s.ticker }} · 綜合分析摘要
    </div>
    <div class="summary-body" style="font-size:13px;line-height:1.7;color:var(--text)">
      {% for b in core_bullets[:2] %}{{ b }}{% if not loop.last %}　{% endif %}{% endfor %}
      {% if not core_bullets %}{{ s.ai_view or ('技術信號分數 ' ~ sc ~ '/100，強度評級：' ~ s.strength ~ '。') }}{% endif %}
    </div>
  </div>
  <div class="verdict-block" style="text-align:center;flex-shrink:0">
    <div class="verdict-label {{ verdict.cls }}" style="font-size:20px;font-weight:800;letter-spacing:-0.01em">{{ verdict.label }}</div>
    <div class="verdict-en" style="font-family:var(--mono);font-size:11px;color:var(--text-2);margin-top:4px">{{ verdict.en }}</div>
    <div style="font-family:var(--mono);font-size:10px;margin-top:6px;color:var(--{{ verdict.cls }});opacity:0.7">信號 {{ sc }}/100</div>
  </div>
</div>

<div class="footer">⚠ Generated by AI · for research only · not investment advice · trade at your own risk</div>

</div><!-- /.page-detail -->

</body>
</html>
"""


# ── Public API ────────────────────────────────────────────────────────────────

def generate_stock_detail_page(
    s: dict,
    date: str,
    output_dir: str,
    ticker_list: list[str] | None = None,
    markers: list | None = None,
) -> str:
    """Generate a detail HTML page for a single stock.

    Args:
        s:           Stock result dict (same shape as report_generator uses).
        date:        Report date string e.g. "2024/11/14".
        output_dir:  Path to the outputs directory.
        ticker_list: Ordered list of all tickers (by score desc) for prev/next nav.

    Returns:
        Absolute path to the written HTML file.
    """
    ohlc          = s.get("ohlc", [])
    chart_svg     = _build_candle_svg(ohlc, markers=markers) if len(ohlc) >= 10 else ""

    # TradingView symbol — map HK tickers (0700.HK -> HKEX:700), US pass-through
    _tk = s["ticker"]
    if _tk.upper().endswith(".HK"):
        tv_symbol = "HKEX:" + str(int(_tk[:-3]))
    else:
        tv_symbol = _tk
    pullback_svg  = _build_pullback_svg(ohlc) if len(ohlc) >= 10 else ""
    key_levels    = _build_key_levels(s)
    scenarios     = _build_scenarios(s)
    bull_bear     = _build_bull_bear_targets(s)
    risks         = _build_risks(s)
    strategy      = _build_strategy(s)
    verdict       = _build_verdict(s)
    core_bullets  = _parse_core_bullets(s.get("ai_view", ""), s.get("signals", []))

    # Prev / next navigation
    prev_ticker = next_ticker = None
    if ticker_list and s["ticker"] in ticker_list:
        idx = ticker_list.index(s["ticker"])
        if idx > 0:
            prev_ticker = ticker_list[idx - 1]
        if idx < len(ticker_list) - 1:
            next_ticker = ticker_list[idx + 1]

    from jinja2 import Environment
    env = Environment()

    generated_at = datetime.now(tz=timezone(timedelta(hours=8))).strftime("%b %d %H:%M HKT")

    html = env.from_string(DETAIL_HTML).render(
        s=s,
        date=date,
        generated_at=generated_at,
        chart_svg=chart_svg,
        pullback_svg=pullback_svg,
        key_levels=key_levels,
        scenarios=scenarios,
        bull_bear=bull_bear,
        risks=risks,
        strategy=strategy,
        verdict=verdict,
        core_bullets=core_bullets,
        has_ohlc=bool(chart_svg),
        ohlc_count=len(ohlc),
        prev_ticker=prev_ticker,
        next_ticker=next_ticker,
        tv_symbol=tv_symbol,
    )

    os.makedirs(output_dir, exist_ok=True)
    path = os.path.join(output_dir, f"{s['ticker']}.html")
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)
    return path
