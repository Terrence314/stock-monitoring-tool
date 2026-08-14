"""PM Capital Allocation dashboard — entry point.

Runs the market-regime scorer and the watchlist scanner, then writes:

    outputs/pm_allocation.json    machine-readable payload
    outputs/pm-allocation.html    the single-page dashboard

Layout follows the executive-brief reference: a navy title bar, four status
cards in one row (信心指數 / 今晚交易 / 長線首選 / 避免交易) each carrying a
single headline pick, then a coloured 行動結論 bar over a three-column
summary strip. The index breakdown sits below the brief as secondary detail.

Conviction is shown on a 0-10 scale ("Conv 6.3") per the reference; the
confidence index stays 0-100. Both scales are deliberate.

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
MISSING = "—"

# Displayed verbatim on the dashboard. The per-ticker signal family this tool
# ranks with has not passed its own out-of-sample gate; the numbers below come
# from Projects/Stock Monitoring Tool - Project A/gate-decision-2026-08-12.md.
PROVENANCE_NOTE = (
    "信號出處:同一套 per-ticker 機械信號,樣本內 17 筆已平倉 — "
    "勝率 35.3% / PF 0.58 / 淨 −$333.91,未通過自身 gate(PASS 需 WR≥45% + PF≥1.0)。"
    "以下標的為排序參考,非已驗證 edge。市場制度卡(第一格)不依賴該套信號。"
)

# Per-band accent + status dot. The dot is the reference's own convention.
BAND_STYLE = {
    "FULL": {"accent": "#1E7B34", "dot": "🟢", "tint": "#F1F8F2"},
    "SELECTIVE": {"accent": "#8A5A00", "dot": "🟡", "tint": "#FFFCF3"},
    "CASH": {"accent": "#B02418", "dot": "🔴", "tint": "#FDF2F1"},
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


def to_conviction_10(conviction_100: float | None) -> str:
    """Reference shows conviction on 0-10 ("Conv 6.3"); the scorer works in 0-100."""
    if conviction_100 is None:
        return MISSING
    return f"{conviction_100 / 10:.1f}"


def build_conclusion(regime: dict, buckets: dict) -> str:
    """One-sentence action conclusion for the bar under the cards."""
    band = regime["band"]
    tonight = buckets["tonight"]
    long_term_count = buckets["qualified_counts"]["long_term"]

    if band == "CASH":
        return (f"空倉。信心指數 {regime['score']}/100 低於 60,今晚不開新倉 — "
                f"{long_term_count} 隻長線標的維持觀察名單,等指數回到 60 以上再談部署。")
    if band == "SELECTIVE":
        if tonight:
            return (f"可選擇性部署 Selective。信心指數 {regime['score']}/100 — "
                    f"只做首選 {tonight[0]['ticker']},倉位控制喺 25-50%,其餘現金。")
        return (f"可選擇性部署 Selective,但今晚無標的合格。信心指數 {regime['score']}/100 — "
                f"制度允許入場,個股結構未到位,持現金等 setup。")
    if tonight:
        names = "、".join(row["ticker"] for row in tonight[:4])
        return (f"全倉 Full。信心指數 {regime['score']}/100 高於 75 — "
                f"今晚可執行:{names}。長線首選 {long_term_count} 隻可同步加碼。")
    return (f"全倉制度,但今晚無短線 setup。信心指數 {regime['score']}/100 — "
            f"透過 {long_term_count} 隻長線首選部署,唔好為咗滿倉而硬做短線。")


def _esc(value) -> str:
    return html.escape(str(value), quote=True)


def _overflow(rows: list[dict], qualified: int) -> str:
    """Name the picks the headline card had to leave out, without detail."""
    rest = [row["ticker"] for row in rows[1:]]
    if not rest:
        return ""
    hidden = qualified - len(rows)
    tail = f" +{hidden}" if hidden > 0 else ""
    return f'<p class="card-more">其餘:{_esc("、".join(rest))}{_esc(tail)}</p>'


def _card(label: str, dot: str, headline: str, accent: str,
          support: str, note: str = "", tint: str = "",
          overflow: str = "") -> str:
    """One status card. `headline` is the single pick the brief leads with."""
    style = f'border-color:{accent};'
    if tint:
        style += f'background:{tint};'
    note_html = f'<p class="card-note">{_esc(note)}</p>' if note else ""
    return f"""
      <section class="card" style="{style}">
        <p class="card-label">{_esc(label)}</p>
        <p class="card-headline" style="color:{accent}">
          <span class="dot" aria-hidden="true">{dot}</span>{_esc(headline)}
        </p>
        <p class="card-support">{_esc(support)}</p>
        {note_html}
        {overflow}
      </section>"""


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


def _build_cards(regime: dict, buckets: dict) -> str:
    style = BAND_STYLE.get(regime["band"], BAND_STYLE["SELECTIVE"])
    counts = buckets["qualified_counts"]

    tonight = buckets["tonight"]
    long_term = buckets["long_term"]
    avoid = buckets["avoid"]

    regime_card = _card(
        label="PM 信心指數",
        dot=style["dot"],
        headline=f"{regime['score']}",
        accent=style["accent"],
        support=f"{regime['band']} · Deploy {regime['deploy_pct']}",
        note=regime["instruction"],
    )

    if tonight:
        top = tonight[0]
        tonight_card = _card(
            label="今晚交易",
            dot="",
            headline=top["ticker"],
            accent="#8A5A00",
            support=f"{top['strategy'].split(' — ')[0]} · Conv {to_conviction_10(top['conviction'])}",
            note=f"${top['price']} · {top['name']}",
            tint="#FFFCF3",
            overflow=_overflow(tonight, counts["tonight"]),
        )
    else:
        tonight_card = _card(
            label="今晚交易", dot="", headline="NO TRADE", accent="#6B6B6B",
            support=f"Conv {MISSING}",
            note="今晚無標的通過短線條件。" if regime["band"] != "CASH"
                 else "空倉制度封鎖今晚交易。",
            tint="#F4F4F4",
        )

    if long_term:
        top = long_term[0]
        long_card = _card(
            label="長線首選",
            dot="🟢",
            headline=top["ticker"],
            accent="#1E7B34",
            support=f"{top['name']} · Score {to_conviction_10(top['conviction'])}",
            note=f"${top['price']} · 120 日 {top['change_120d_pct']}%"
                 if top["change_120d_pct"] is not None else f"${top['price']}",
            tint="#F1F8F2",
            overflow=_overflow(long_term, counts["long_term"]),
        )
    else:
        long_card = _card(
            label="長線首選", dot="", headline=MISSING, accent="#6B6B6B",
            support=f"Score {MISSING}", note="無標的通過長線條件。", tint="#F4F4F4",
        )

    if avoid:
        top = avoid[0]
        avoid_card = _card(
            label="避免交易",
            dot="🔴",
            headline=top["ticker"],
            accent="#B02418",
            support="NO TRADE",
            note=top["reason"],
            tint="#FDF2F1",
            overflow=_overflow(avoid, counts["avoid"]),
        )
    else:
        avoid_card = _card(
            label="避免交易", dot="", headline=MISSING, accent="#6B6B6B",
            support="—", note="無標的觸發避免條件。", tint="#F4F4F4",
        )

    return regime_card + tonight_card + long_card + avoid_card


def render_html(payload: dict) -> str:
    regime = payload["regime"]
    buckets = payload["watchlist"]
    style = BAND_STYLE.get(regime["band"], BAND_STYLE["SELECTIVE"])

    tonight = buckets["tonight"]
    avoid = buckets["avoid"]
    pick_text = (f"{tonight[0]['ticker']} {tonight[0]['strategy'].split(' — ')[0]}"
                 if tonight else "無 — 今晚不開新倉")
    avoid_text = avoid[0]["ticker"] if avoid else MISSING

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
    --navy: #1F3864;
    --accent: {style['accent']};
    --page: #FFFFFF;
    --ink: #1A1A1A;
    --ink-2: #6B6B6B;
    --line: #D8D8D8;
    --strip: #F2F2F2;
    --mono: ui-monospace, SFMono-Regular, "SF Mono", Menlo, monospace;
  }}
  * {{ box-sizing: border-box; }}
  body {{
    margin: 0; padding: 28px 24px 40px;
    background: var(--page); color: var(--ink);
    font-family: -apple-system, BlinkMacSystemFont, "Helvetica Neue", Arial,
                 "PingFang HK", "Noto Sans CJK HK", sans-serif;
    line-height: 1.45;
  }}
  .wrap {{ max-width: 1200px; margin: 0 auto; }}

  .titlebar {{ background: var(--navy); color: #fff; padding: 20px 26px;
               border-radius: 3px; }}
  .titlebar h1 {{ margin: 0; font-size: 19px; font-weight: 400;
                  letter-spacing: .16em; text-transform: uppercase; }}
  .titlebar p {{ margin: 6px 0 0; font-size: 18px; font-weight: 700;
                 letter-spacing: .02em; }}
  .titlebar .light {{ font-weight: 400; }}

  .cards {{ display: grid; grid-template-columns: repeat(4, minmax(0, 1fr));
            gap: 16px; margin-top: 22px; }}
  .card {{ border: 2px solid var(--line); border-radius: 3px;
           padding: 16px 18px 18px; min-width: 0; }}
  .card-label {{ margin: 0; font-size: 14px; color: var(--ink-2); }}
  .card-headline {{ margin: 8px 0 4px; font-size: 28px; font-weight: 700;
                    letter-spacing: .01em; word-break: break-word; }}
  .dot {{ margin-right: 10px; font-size: 20px; vertical-align: 1px; }}
  .card-support {{ margin: 0; font-size: 15px; font-weight: 700; }}
  .card-note {{ margin: 4px 0 0; font-size: 13px; color: var(--ink-2); }}
  .card-more {{ margin: 8px 0 0; font-size: 12px; color: var(--ink-2);
                border-top: 1px solid var(--line); padding-top: 6px; }}

  .conclusion {{ margin-top: 22px; background: var(--accent); color: #fff;
                 padding: 13px 22px; border-radius: 3px 3px 0 0;
                 font-size: 16px; font-weight: 700; }}
  .summary {{ background: var(--strip); display: grid;
              grid-template-columns: repeat(3, minmax(0, 1fr));
              gap: 16px; padding: 16px 22px; border-radius: 0 0 3px 3px; }}
  .summary div {{ font-size: 15px; }}
  .summary b {{ font-weight: 700; }}
  .summary .muted {{ color: var(--ink-2); }}
  .summary .danger {{ color: #B02418; font-weight: 700; }}
  .suppressed {{ margin: 12px 0 0; color: #B02418; font-size: 13px; }}

  .detail {{ margin-top: 30px; border-top: 1px solid var(--line);
             padding-top: 20px; }}
  .detail h2 {{ font-size: 13px; margin: 0 0 14px; color: var(--ink-2);
                letter-spacing: .08em; text-transform: uppercase; }}
  .components {{ display: grid; grid-template-columns: repeat(4, minmax(0,1fr));
                 gap: 18px; }}
  .component-head {{ display: flex; justify-content: space-between;
                     font-size: 13px; margin-bottom: 5px; }}
  .bar {{ height: 5px; border-radius: 3px; background: var(--line);
          overflow: hidden; }}
  .bar span {{ display: block; height: 100%; background: var(--navy); }}
  .component-detail {{ margin: 5px 0 0; font-size: 11.5px; color: var(--ink-2); }}
  .mono {{ font-family: var(--mono); }}

  .provenance {{ margin: 22px 0 0; padding: 11px 15px; border-radius: 3px;
                 border: 1px solid #E0C48A; background: #FFFBF0;
                 color: #7A5200; font-size: 12.5px; }}
  footer {{ margin-top: 14px; font-family: var(--mono); font-size: 11px;
            color: var(--ink-2); }}

  @media (max-width: 1000px) {{
    .cards, .components {{ grid-template-columns: repeat(2, minmax(0,1fr)); }}
    .summary {{ grid-template-columns: 1fr; gap: 8px; }}
  }}
  @media (max-width: 560px) {{
    .cards, .components {{ grid-template-columns: 1fr; }}
  }}
</style>
</head>
<body>
<div class="wrap">
  <header class="titlebar">
    <h1>PM Capital Allocation Dashboard</h1>
    <p>{_esc(payload['generated_at_hkt'])} HKT <span class="light">· EXECUTIVE BRIEF</span></p>
  </header>

  <div class="cards">{_build_cards(regime, buckets)}</div>

  <div class="conclusion">行動結論:{style['dot']} {_esc(payload['conclusion_short'])}</div>
  <div class="summary">
    <div><b>首選:</b> <span class="muted">{_esc(pick_text)}</span></div>
    <div><b>建議部署:</b> {_esc(regime['deploy_pct'])}</div>
    <div><b>避免:</b> <span class="danger">{_esc(avoid_text)}</span></div>
  </div>
  {suppressed}

  <section class="detail">
    <h2>信心指數組成</h2>
    <div class="components">{_component_rows(regime['components'])}</div>
    <p class="provenance">{_esc(PROVENANCE_NOTE)}</p>
    <footer>
      掃描 {_esc(buckets['scanned'])} 隻 · Finnhub 即時報價 {_esc(buckets['live_quote_count'])} 隻 ·
      歷史與 VIX 來自 yfinance · 合格數 今晚 {_esc(buckets['qualified_counts']['tonight'])} /
      長線 {_esc(buckets['qualified_counts']['long_term'])} /
      避免 {_esc(buckets['qualified_counts']['avoid'])}{_esc(payload['degraded_note'])}
    </footer>
  </section>
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

    conclusion = build_conclusion(regime, buckets)
    payload = {
        "generated_at_hkt": datetime.now(HKT).strftime("%Y-%m-%d %H:%M"),
        "generated_at_utc": datetime.now(timezone.utc).isoformat(timespec="seconds"),
        "regime": regime,
        "watchlist": buckets,
        "conclusion": conclusion,
        # The bar shows the lead clause; the full sentence stays in the JSON.
        "conclusion_short": conclusion.split("。")[0],
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
