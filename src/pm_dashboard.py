"""PM Capital Allocation dashboard — entry point.

Runs the market-regime scorer and the watchlist scanner, then writes:

    outputs/pm_allocation.json    machine-readable payload
    outputs/pm-allocation.html    the single-page dashboard

Layout: four cards in a 2x2 grid (信心指數 / 今晚交易 / 長線首選 / 避免交易)
with a full-width action conclusion bar underneath.

Run locally:   python src/pm_dashboard.py
In CI:         .github/workflows/pm_allocation.yml
"""

from __future__ import annotations

import html
import json
import os
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from pm_regime import compute_regime  # noqa: E402
from pm_watchlist import scan  # noqa: E402

REPO_ROOT = Path(__file__).resolve().parent.parent
CONFIG_PATH = REPO_ROOT / "config" / "config.json"
SECRETS_PATH = REPO_ROOT / "config" / "secrets.json"
OUTPUT_DIR = REPO_ROOT / "outputs"
JSON_PATH = OUTPUT_DIR / "pm_allocation.json"
HTML_PATH = OUTPUT_DIR / "pm-allocation.html"

HKT = timezone(timedelta(hours=8))

# Displayed verbatim on the dashboard. The per-ticker signal family this tool
# ranks with has not passed its own out-of-sample gate; the numbers below come
# from Projects/Stock Monitoring Tool - Project A/gate-decision-2026-08-12.md.
PROVENANCE_NOTE = (
    "信號出處:同一套 per-ticker 機械信號,樣本內 17 筆已平倉 — "
    "勝率 35.3% / PF 0.58 / 淨 −$333.91,未通過自身 gate(PASS 需 WR≥45% + PF≥1.0)。"
    "以下標的為排序參考,非已驗證edge。市場制度卡(左上)不依賴該套信號。"
)

BAND_COLORS = {
    "FULL": "--pos",
    "SELECTIVE": "--warn",
    "CASH": "--neg",
}


def load_config() -> dict:
    if not CONFIG_PATH.exists():
        raise FileNotFoundError(f"config not found: {CONFIG_PATH}")
    with CONFIG_PATH.open(encoding="utf-8") as fh:
        return json.load(fh)


def load_finnhub_key() -> str:
    """Env var wins (that is how CI supplies it), then local secrets.json."""
    key = os.getenv("FINNHUB_API_KEY", "").strip()
    if key:
        return key
    if SECRETS_PATH.exists():
        try:
            with SECRETS_PATH.open(encoding="utf-8") as fh:
                return str(json.load(fh).get("finnhub_api_key", "")).strip()
        except (json.JSONDecodeError, OSError) as exc:
            print(f"  [pm_dashboard] could not read secrets.json: {exc}")
    return ""


def build_conclusion(regime: dict, buckets: dict) -> str:
    """One-sentence action conclusion for the bottom bar."""
    band = regime["band"]
    tonight = buckets["tonight"]
    # Counts describe everything that qualified; the lists themselves are capped
    # for readability, so the conclusion must not quote list length as the total.
    long_term_count = buckets["qualified_counts"]["long_term"]

    if band == "CASH":
        return (f"空倉。信心指數 {regime['score']}/100 低於 60,今晚不開新倉 — "
                f"{long_term_count} 隻長線標的維持觀察名單,等指數回到 60 以上再談部署。")
    if band == "SELECTIVE":
        if tonight:
            names = "、".join(row["ticker"] for row in tonight[:3])
            return (f"選擇性部署 25-50%。信心指數 {regime['score']}/100 — "
                    f"只做最高信心嗰幾隻:{names}。每注控制喺總倉 25-50% 以內,其餘現金。")
        return (f"選擇性部署 25-50%,但今晚無標的合格。信心指數 {regime['score']}/100 — "
                f"制度允許入場,個股結構未到位,持現金等 setup。")
    if tonight:
        names = "、".join(row["ticker"] for row in tonight[:4])
        return (f"全倉。信心指數 {regime['score']}/100 高於 75 — "
                f"今晚可執行:{names}。長線首選 {long_term_count} 隻可同步加碼。")
    return (f"全倉制度,但今晚無短線 setup。信心指數 {regime['score']}/100 — "
            f"透過 {long_term_count} 隻長線首選部署,唔好為咗滿倉而硬做短線。")


def _esc(value) -> str:
    return html.escape(str(value), quote=True)


def _gauge_svg(score: float, band: str) -> str:
    """Semicircular gauge. 0-100 maps to a 180-degree sweep."""
    radius, circumference = 80, 3.14159 * 80
    filled = circumference * max(0.0, min(1.0, score / 100))
    color_var = BAND_COLORS.get(band, "--warn")
    return f"""
    <svg viewBox="0 0 200 118" class="gauge" role="img"
         aria-label="市場信心指數 {_esc(score)} 分,滿分 100">
      <path d="M 20 100 A {radius} {radius} 0 0 1 180 100" fill="none"
            stroke="var(--line)" stroke-width="14" stroke-linecap="round"/>
      <path d="M 20 100 A {radius} {radius} 0 0 1 180 100" fill="none"
            stroke="var({color_var})" stroke-width="14" stroke-linecap="round"
            stroke-dasharray="{filled:.1f} {circumference:.1f}"/>
      <text x="100" y="88" text-anchor="middle" class="gauge-score">{_esc(score)}</text>
      <text x="100" y="110" text-anchor="middle" class="gauge-max">/ 100</text>
    </svg>"""


def _component_rows(components: dict) -> str:
    labels = {"spy": "SPY 趨勢", "qqq": "QQQ 趨勢",
              "vix": "VIX 波動", "sector": "板塊輪動"}
    rows = []
    for key, label in labels.items():
        comp = components[key]
        pct = comp["score"] / comp["max"] * 100 if comp["max"] else 0
        rows.append(f"""
        <div class="component">
          <div class="component-head">
            <span>{_esc(label)}</span>
            <span class="mono">{_esc(comp['score'])} / {_esc(comp['max'])}</span>
          </div>
          <div class="bar"><span style="width:{pct:.0f}%"></span></div>
          <p class="component-detail">{_esc(comp['detail'])}</p>
        </div>""")
    return "".join(rows)


def _more_note(shown: int, qualified: int) -> str:
    """Say so when the card is showing a capped slice, not the full set."""
    if qualified <= shown:
        return ""
    return f'<p class="notes">另有 {qualified - shown} 隻合格但未列出,只顯示信心分最高 {shown} 隻。</p>'


def _trade_rows(rows: list[dict], show_strategy: bool, qualified: int = 0) -> str:
    if not rows:
        return '<p class="empty">今日無合格標的。</p>'
    out = []
    for row in rows:
        strategy = (f'<p class="strategy">{_esc(row["strategy"])}</p>'
                    if show_strategy else "")
        change = row.get("change_20d_pct")
        change_class = "pos" if (change or 0) >= 0 else "neg"
        change_text = f"{change:+.1f}%" if change is not None else "—"
        # "Qualified", not "listed" — the tonight card is capped, so a name can
        # pass the short-term test without appearing there.
        overlap = ('<span class="overlap">短線亦合格</span>'
                   if row.get("also_tonight") else "")
        out.append(f"""
        <li class="row">
          <div class="row-head">
            <div>
              <span class="ticker">{_esc(row['ticker'])}</span>
              <span class="name">{_esc(row['name'])}</span>
              {overlap}
            </div>
            <div class="row-metrics">
              <span class="mono">${_esc(row['price'])}</span>
              <span class="mono {change_class}">{_esc(change_text)}</span>
              <span class="conviction">{_esc(row['conviction'])}</span>
            </div>
          </div>
          {strategy}
          <p class="notes">{_esc(' · '.join(row['notes']))}</p>
        </li>""")
    return f'<ul class="rows">{"".join(out)}</ul>{_more_note(len(rows), qualified)}'


def _avoid_rows(rows: list[dict], qualified: int = 0) -> str:
    if not rows:
        return '<p class="empty">無標的觸發避免條件。</p>'
    out = []
    for row in rows:
        out.append(f"""
        <li class="row">
          <div class="row-head">
            <div>
              <span class="ticker">{_esc(row['ticker'])}</span>
              <span class="name">{_esc(row['name'])}</span>
            </div>
            <span class="conviction low">{_esc(row['conviction'])}</span>
          </div>
          <p class="notes">{_esc(row['reason'])}</p>
        </li>""")
    return f'<ul class="rows">{"".join(out)}</ul>{_more_note(len(rows), qualified)}'


def render_html(payload: dict) -> str:
    regime = payload["regime"]
    buckets = payload["watchlist"]
    counts = buckets["qualified_counts"]
    band_color = BAND_COLORS.get(regime["band"], "--warn")

    suppressed = ('<p class="suppressed">市場制度為空倉 — 今晚交易已被制度規則封鎖,'
                  '無論個股信心分幾高。</p>' if buckets["suppressed_by_regime"] else "")

    return f"""<!doctype html>
<html lang="zh-HK">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>PM Capital Allocation</title>
<style>
  :root {{
    --bg: #0d1117; --card: #161b22; --line: #262d36;
    --text: #e6edf3; --text-2: #8b949e;
    --pos: #3fb950; --neg: #f85149; --warn: #d29922; --accent: #58a6ff;
    --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 24px 20px 48px;
    background: var(--bg); color: var(--text);
    font-family: -apple-system, BlinkMacSystemFont, "Segoe UI",
                 "PingFang HK", "Noto Sans CJK HK", sans-serif;
    line-height: 1.5;
  }}
  .wrap {{ max-width: 1180px; margin: 0 auto; }}
  header {{ display:flex; flex-wrap:wrap; align-items:baseline;
            justify-content:space-between; gap:8px; margin-bottom:6px; }}
  h1 {{ font-size: 20px; margin: 0; letter-spacing: .01em; }}
  .stamp {{ font-family: var(--mono); font-size: 12px; color: var(--text-2); }}
  .provenance {{
    margin: 14px 0 20px; padding: 10px 14px; border-radius: 8px;
    border: 1px solid rgba(210,153,34,.35); background: rgba(210,153,34,.08);
    color: #e3b341; font-size: 12.5px;
  }}
  .grid {{ display: grid; grid-template-columns: repeat(2, minmax(0,1fr)); gap: 16px; }}
  .card {{
    background: var(--card); border: 1px solid var(--line);
    border-radius: 12px; padding: 18px 20px; min-width: 0;
  }}
  .card h2 {{ font-size: 14px; margin: 0 0 14px; color: var(--text-2);
              font-weight: 600; letter-spacing: .04em; }}
  .band {{ text-align:center; margin-bottom: 4px; }}
  .band-label {{ font-size: 26px; font-weight: 700; color: var(--{band_color[2:]}); }}
  .band-deploy {{ font-family: var(--mono); font-size: 13px; color: var(--text-2); }}
  .gauge {{ width: 100%; max-width: 260px; display:block; margin: 0 auto 6px; }}
  .gauge-score {{ fill: var(--text); font-size: 34px; font-weight: 700;
                  font-family: var(--mono); }}
  .gauge-max {{ fill: var(--text-2); font-size: 12px; font-family: var(--mono); }}
  .component {{ margin-top: 12px; }}
  .component-head {{ display:flex; justify-content:space-between;
                     font-size: 12.5px; margin-bottom: 4px; }}
  .bar {{ height: 5px; border-radius: 3px; background: var(--line); overflow: hidden; }}
  .bar span {{ display:block; height:100%; background: var(--accent); }}
  .component-detail {{ margin: 4px 0 0; font-size: 11.5px; color: var(--text-2); }}
  .rows {{ list-style:none; margin:0; padding:0; }}
  .row {{ padding: 10px 0; border-top: 1px solid var(--line); }}
  .row:first-child {{ border-top: none; padding-top: 0; }}
  .row-head {{ display:flex; justify-content:space-between;
               align-items:center; gap: 10px; flex-wrap: wrap; }}
  .ticker {{ font-family: var(--mono); font-weight: 700; font-size: 14px; }}
  .name {{ color: var(--text-2); font-size: 12px; margin-left: 6px; }}
  .row-metrics {{ display:flex; align-items:center; gap: 10px; }}
  .mono {{ font-family: var(--mono); font-size: 12.5px; }}
  .pos {{ color: var(--pos); }} .neg {{ color: var(--neg); }}
  .conviction {{
    font-family: var(--mono); font-size: 13px; font-weight: 700;
    background: rgba(88,166,255,.14); color: var(--accent);
    padding: 2px 8px; border-radius: 6px;
  }}
  .conviction.low {{ background: rgba(248,81,73,.14); color: var(--neg); }}
  .overlap {{ font-size: 10.5px; color: var(--accent); margin-left: 6px;
              border: 1px solid rgba(88,166,255,.35); border-radius: 4px;
              padding: 1px 5px; white-space: nowrap; }}
  .strategy {{ margin: 6px 0 0; font-size: 12.5px; color: var(--text); }}
  .notes {{ margin: 4px 0 0; font-size: 11.5px; color: var(--text-2); }}
  .empty {{ color: var(--text-2); font-size: 13px; margin: 0; }}
  .suppressed {{ color: var(--neg); font-size: 12.5px; margin: 0 0 10px; }}
  .conclusion {{
    margin-top: 16px; padding: 18px 22px; border-radius: 12px;
    background: var(--card); border: 1px solid var(--line);
    border-left: 4px solid var(--{band_color[2:]});
  }}
  .conclusion h2 {{ font-size: 12px; margin: 0 0 8px; color: var(--text-2);
                    letter-spacing: .06em; }}
  .conclusion p {{ margin: 0; font-size: 15px; }}
  footer {{ margin-top: 18px; font-family: var(--mono);
            font-size: 11px; color: var(--text-2); }}
  @media (max-width: 820px) {{ .grid {{ grid-template-columns: 1fr; }} }}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <h1>PM Capital Allocation</h1>
    <span class="stamp">{_esc(payload['generated_at_hkt'])} HKT</span>
  </header>
  <p class="provenance">{_esc(PROVENANCE_NOTE)}</p>

  <div class="grid">
    <section class="card">
      <h2>市場信心指數</h2>
      {_gauge_svg(regime['score'], regime['band'])}
      <div class="band">
        <div class="band-label">{_esc(regime['label'])}</div>
        <div class="band-deploy">建議部署 {_esc(regime['deploy_pct'])}</div>
      </div>
      {_component_rows(regime['components'])}
    </section>

    <section class="card">
      <h2>今晚交易</h2>
      {suppressed}
      {_trade_rows(buckets['tonight'], True, counts['tonight'])}
    </section>

    <section class="card">
      <h2>長線首選</h2>
      {_trade_rows(buckets['long_term'], False, counts['long_term'])}
    </section>

    <section class="card">
      <h2>避免交易</h2>
      {_avoid_rows(buckets['avoid'], counts['avoid'])}
    </section>
  </div>

  <section class="conclusion">
    <h2>行動結論</h2>
    <p>{_esc(payload['conclusion'])}</p>
  </section>

  <footer>
    掃描 {_esc(buckets['scanned'])} 隻 · Finnhub 即時報價 {_esc(buckets['live_quote_count'])} 隻 ·
    歷史與 VIX 來自 yfinance{_esc(payload['degraded_note'])}
  </footer>
</div>
</body>
</html>
"""


def main() -> int:
    config = load_config()
    watchlist = config.get("watchlist", [])
    if not watchlist:
        print("[pm_dashboard] config.json has an empty watchlist — nothing to scan")
        return 1

    print("[pm_dashboard] computing market regime...")
    regime = compute_regime()
    print(f"  score {regime['score']}/100 → {regime['band']} ({regime['label']})")

    print(f"[pm_dashboard] scanning {len(watchlist)} watchlist entries...")
    buckets = scan(watchlist, regime["band"], load_finnhub_key())
    print(f"  tonight={len(buckets['tonight'])} "
          f"long_term={len(buckets['long_term'])} avoid={len(buckets['avoid'])}")

    degraded = regime["degraded_components"]
    degraded_note = f" · 降級組件: {', '.join(degraded)}" if degraded else ""

    payload = {
        "generated_at_hkt": datetime.now(HKT).strftime("%Y-%m-%d %H:%M"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "regime": regime,
        "watchlist": buckets,
        "conclusion": build_conclusion(regime, buckets),
        "degraded_note": degraded_note,
        "provenance": PROVENANCE_NOTE,
    }

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    JSON_PATH.write_text(json.dumps(payload, ensure_ascii=False, indent=2),
                         encoding="utf-8")
    HTML_PATH.write_text(render_html(payload), encoding="utf-8")

    print(f"[pm_dashboard] wrote {JSON_PATH}")
    print(f"[pm_dashboard] wrote {HTML_PATH}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
