import os
from datetime import datetime
from jinja2 import Template

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>AI 股票監控系統 · {{ date }}</title>
<style>
:root {
  --bg:      #0d1117;
  --card:    #161b22;
  --card2:   #1c2230;
  --border:  #2d3748;
  --gold:    #f6c90e;
  --green:   #2ecc71;
  --red:     #e74c3c;
  --blue:    #3b82f6;
  --purple:  #a78bfa;
  --orange:  #f97316;
  --text:    #e2e8f0;
  --muted:   #8892a4;
}
* { box-sizing: border-box; margin: 0; padding: 0; }
body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang TC', sans-serif; font-size: 13px; padding: 14px; }

/* ── HEADER ── */
.header { background: linear-gradient(135deg,#0f1923,#1a2535); border: 1px solid var(--border); border-radius: 12px; padding: 16px 20px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
.header-left h1 { font-size: 22px; font-weight: 900; color: #fff; }
.header-left .sub { font-size: 12px; color: var(--muted); margin-top: 3px; }
.header-right { display: flex; gap: 8px; align-items: center; }
.date-badge { background: var(--gold); color: #000; font-weight: 800; font-size: 12px; padding: 4px 10px; border-radius: 6px; }
.lang-btn { background: var(--card2); border: 1px solid var(--border); color: var(--text); font-size: 11px; padding: 4px 10px; border-radius: 6px; cursor: pointer; }

/* ── MARKET OVERVIEW ── */
.market-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(130px, 1fr)); gap: 8px; margin-bottom: 12px; }
.market-card { background: var(--card); border: 1px solid var(--border); border-radius: 8px; padding: 10px 12px; }
.market-card.up   { border-left: 3px solid var(--green); }
.market-card.down { border-left: 3px solid var(--red); }
.market-name  { font-size: 10px; color: var(--muted); font-weight: 600; text-transform: uppercase; }
.market-price { font-size: 16px; font-weight: 800; color: var(--text); margin: 2px 0; }
.market-chg   { font-size: 12px; font-weight: 700; }
.market-chg.up   { color: var(--green); }
.market-chg.down { color: var(--red); }

/* ── SECTION CARD ── */
.card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; margin-bottom: 12px; }
.card-title { font-size: 12px; font-weight: 800; color: var(--gold); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 12px; padding-bottom: 8px; border-bottom: 1px solid var(--border); display: flex; align-items: center; gap: 6px; }
.card-title .icon { font-size: 15px; }

/* ── MORNING BRIEF ── */
.brief-grid { display: grid; grid-template-columns: 1fr 1fr; gap: 10px; }
@media(max-width:700px){ .brief-grid { grid-template-columns: 1fr; } }
.brief-section { background: var(--card2); border-radius: 8px; padding: 12px 14px; }
.brief-label { font-size: 10px; font-weight: 800; color: var(--gold); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 6px; }
.brief-body { font-size: 12px; color: var(--text); line-height: 1.6; white-space: pre-wrap; }

/* ── LEADERBOARD ── */
.lb-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.lb-table th { background: var(--card2); color: var(--muted); padding: 7px 10px; text-align: left; font-weight: 700; border-bottom: 1px solid var(--border); font-size: 11px; text-transform: uppercase; }
.lb-table td { padding: 8px 10px; border-bottom: 1px solid rgba(45,55,72,0.4); vertical-align: middle; }
.lb-table tr:last-child td { border-bottom: none; }
.lb-table tr:hover td { background: rgba(255,255,255,0.02); }
.ticker-cell { font-weight: 800; font-size: 14px; color: #fff; }
.name-cell   { font-size: 11px; color: var(--muted); }
.price-cell  { font-weight: 700; }
.chg-pos { color: var(--green); font-weight: 700; }
.chg-neg { color: var(--red);   font-weight: 700; }
.score-bar-wrap { display: flex; align-items: center; gap: 8px; }
.score-bar { height: 6px; border-radius: 3px; background: var(--card2); flex: 1; overflow: hidden; }
.score-fill { height: 100%; border-radius: 3px; }
.score-fill.high   { background: linear-gradient(90deg,var(--green),#27ae60); }
.score-fill.mid    { background: linear-gradient(90deg,var(--gold),var(--orange)); }
.score-fill.low    { background: linear-gradient(90deg,var(--red),#c0392b); }
.score-num { font-weight: 800; font-size: 13px; min-width: 28px; }
.score-num.high { color: var(--green); }
.score-num.mid  { color: var(--gold); }
.score-num.low  { color: var(--red); }
.strength-badge { font-size: 11px; font-weight: 700; padding: 2px 8px; border-radius: 4px; white-space: nowrap; }
.strength-buy   { background: rgba(46,204,113,0.15); color: var(--green); }
.strength-neut  { background: rgba(246,201,14,0.12); color: var(--gold); }
.strength-sell  { background: rgba(231,76,60,0.15);  color: var(--red); }

/* ── STOCK CARDS ── */
.stock-grid { display: grid; grid-template-columns: repeat(auto-fill, minmax(340px, 1fr)); gap: 12px; }
.stock-card { background: var(--card); border: 1px solid var(--border); border-radius: 10px; padding: 14px 16px; }
.sc-header { display: flex; justify-content: space-between; align-items: flex-start; margin-bottom: 10px; }
.sc-ticker { font-size: 18px; font-weight: 900; color: #fff; }
.sc-name   { font-size: 11px; color: var(--muted); margin-top: 1px; }
.sc-price  { text-align: right; }
.sc-price-val { font-size: 20px; font-weight: 900; color: var(--gold); }
.sc-price-chg { font-size: 12px; font-weight: 700; margin-top: 1px; }
.sc-badges { display: flex; gap: 6px; flex-wrap: wrap; margin-bottom: 10px; }
.ma-badge { font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 4px; }
.ma5  { background: rgba(246,201,14,0.15); color: var(--gold); }
.ma20 { background: rgba(59,130,246,0.15);  color: var(--blue); }
.ma60 { background: rgba(167,139,250,0.15); color: var(--purple); }
.rsi-badge { background: rgba(249,115,22,0.15); color: var(--orange); font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 4px; }
.vol-badge { background: rgba(46,204,113,0.12); color: var(--green); font-size: 10px; font-weight: 700; padding: 2px 7px; border-radius: 4px; }
.sc-signals { margin-bottom: 10px; }
.signal-item { font-size: 11px; color: var(--text); line-height: 1.6; }
.sc-divider { border: none; border-top: 1px solid var(--border); margin: 10px 0; }
.sc-ai-label { font-size: 10px; font-weight: 800; color: var(--blue); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
.sc-ai-body  { font-size: 11px; color: var(--text); line-height: 1.6; }
.sc-score-row { display: flex; align-items: center; gap: 8px; margin-bottom: 10px; }

/* ── FOOTER ── */
.footer { text-align: center; padding: 16px; color: var(--muted); font-size: 11px; margin-top: 4px; }
</style>
</head>
<body>

<!-- HEADER -->
<div class="header">
  <div class="header-left">
    <h1>📊 AI 股票監控系統</h1>
    <div class="sub">每日技術面分析 · AI 市場判讀 · 信號評分</div>
  </div>
  <div class="header-right">
    <div class="date-badge">{{ date }}</div>
  </div>
</div>

<!-- MARKET OVERVIEW -->
<div class="market-grid">
{% for ticker, m in market.items() %}
  <div class="market-card {{ m.direction }}">
    <div class="market-name">{{ m.name }}</div>
    <div class="market-price">{{ "%.2f"|format(m.price) }}</div>
    <div class="market-chg {{ m.direction }}">{{ "%+.2f"|format(m.change_pct) }}%</div>
  </div>
{% endfor %}
</div>

<!-- MORNING BRIEF -->
<div class="card">
  <div class="card-title"><span class="icon">🌅</span>早盤市場簡報（F→G→H→I）</div>
  <div class="brief-grid">
    {% for section in brief_sections %}
    <div class="brief-section">
      <div class="brief-label">{{ section.label }}</div>
      <div class="brief-body">{{ section.body }}</div>
    </div>
    {% endfor %}
  </div>
</div>

<!-- SIGNAL LEADERBOARD -->
<div class="card">
  <div class="card-title"><span class="icon">🏆</span>信號排行榜</div>
  <table class="lb-table">
    <thead>
      <tr>
        <th>股票</th>
        <th>現價</th>
        <th>漲跌</th>
        <th>信號分數</th>
        <th>強弱</th>
        <th>RSI</th>
        <th>MACD Hist</th>
        <th>量比</th>
      </tr>
    </thead>
    <tbody>
    {% for s in stocks_sorted %}
      {% set sc = s.score %}
      {% set sc_class = "high" if sc >= 60 else ("mid" if sc >= 40 else "low") %}
      {% set chg_class = "chg-pos" if s.price_change_pct >= 0 else "chg-neg" %}
      {% set str_class = "strength-buy" if sc >= 60 else ("strength-neut" if sc >= 40 else "strength-sell") %}
      <tr>
        <td>
          <div class="ticker-cell">{{ s.ticker }}</div>
          <div class="name-cell">{{ s.name }}</div>
        </td>
        <td class="price-cell">${{ "%.2f"|format(s.price) }}</td>
        <td class="{{ chg_class }}">{{ "%+.2f"|format(s.price_change_pct) }}%</td>
        <td>
          <div class="score-bar-wrap">
            <div class="score-bar"><div class="score-fill {{ sc_class }}" style="width:{{ sc }}%"></div></div>
            <span class="score-num {{ sc_class }}">{{ sc }}</span>
          </div>
        </td>
        <td><span class="strength-badge {{ str_class }}">{{ s.strength }}</span></td>
        <td>{{ s.rsi if s.rsi else "—" }}</td>
        <td>{{ "%.2f"|format(s.macd_hist) if s.macd_hist else "—" }}</td>
        <td>{{ "%.1f"|format(s.vol_ratio) if s.vol_ratio else "—" }}×</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
</div>

<!-- STOCK CARDS -->
<div class="card">
  <div class="card-title"><span class="icon">📈</span>個股詳情</div>
  <div class="stock-grid">
  {% for s in stocks_sorted %}
    {% set sc = s.score %}
    {% set sc_class = "high" if sc >= 60 else ("mid" if sc >= 40 else "low") %}
    {% set chg_class = "chg-pos" if s.price_change_pct >= 0 else "chg-neg" %}
    <div class="stock-card">
      <div class="sc-header">
        <div>
          <div class="sc-ticker">{{ s.ticker }}</div>
          <div class="sc-name">{{ s.name }}</div>
        </div>
        <div class="sc-price">
          <div class="sc-price-val">${{ "%.2f"|format(s.price) }}</div>
          <div class="sc-price-chg {{ chg_class }}">{{ "%+.2f"|format(s.price_change_pct) }}%</div>
        </div>
      </div>

      <div class="sc-score-row">
        <div class="score-bar" style="flex:1"><div class="score-fill {{ sc_class }}" style="width:{{ sc }}%"></div></div>
        <span class="score-num {{ sc_class }}">{{ sc }}/100</span>
        <span class="strength-badge {{ 'strength-buy' if sc >= 60 else ('strength-neut' if sc >= 40 else 'strength-sell') }}">{{ s.strength }}</span>
      </div>

      <div class="sc-badges">
        <span class="ma-badge ma5">MA5: {{ s.ma5 }}</span>
        <span class="ma-badge ma20">MA20: {{ s.ma20 }}</span>
        <span class="ma-badge ma60">MA60: {{ s.ma60 }}</span>
        <span class="rsi-badge">RSI: {{ s.rsi }}</span>
        <span class="vol-badge">量比: {{ "%.1f"|format(s.vol_ratio) if s.vol_ratio else "—" }}×</span>
      </div>

      <div class="sc-signals">
        {% for sig in s.signals %}
        <div class="signal-item">{{ sig }}</div>
        {% endfor %}
      </div>

      {% if s.ai_view %}
      <hr class="sc-divider">
      <div class="sc-ai-label">🤖 AI 快速判讀</div>
      <div class="sc-ai-body">{{ s.ai_view }}</div>
      {% endif %}
    </div>
  {% endfor %}
  </div>
</div>

<div class="footer">⚠️ 本報告由 AI 自動生成，僅供參考，不構成投資建議。投資有風險，請審慎評估。</div>

</body>
</html>"""


def _parse_brief(raw: str) -> list[dict]:
    """Split the F→G→H→I morning brief into 4 sections."""
    labels = {
        "F": "F・市場消息整理",
        "G": "G・市場情緒判讀",
        "H": "H・技術面關鍵價位",
        "I": "I・今日交易計畫",
    }
    sections = []
    current_key = None
    current_lines = []

    for line in raw.split("\n"):
        matched = None
        for key in labels:
            if f"【{key}" in line or f"**{key}" in line or line.strip().startswith(f"{key}・") or line.strip().startswith(f"[{key}"):
                matched = key
                break
        if matched:
            if current_key:
                sections.append({"label": labels[current_key], "body": "\n".join(current_lines).strip()})
            current_key = matched
            current_lines = []
        else:
            if current_key:
                clean = line.replace("**", "").replace("【", "").replace("】", "")
                current_lines.append(clean)

    if current_key:
        sections.append({"label": labels[current_key], "body": "\n".join(current_lines).strip()})

    if not sections:
        sections = [{"label": "早盤分析", "body": raw}]

    return sections


def generate_dashboard(
    date: str,
    market_overview: dict,
    morning_brief: str,
    stock_results: list,
    output_dir: str = "outputs",
) -> str:
    os.makedirs(output_dir, exist_ok=True)

    stocks_sorted = sorted(stock_results, key=lambda x: x["score"], reverse=True)
    brief_sections = _parse_brief(morning_brief)

    html = Template(DASHBOARD_HTML).render(
        date=date,
        market=market_overview,
        brief_sections=brief_sections,
        stocks_sorted=stocks_sorted,
    )

    filename = f"report_{datetime.now().strftime('%Y%m%d')}.html"
    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    # Always overwrite latest.html for GitHub Pages
    latest_path = os.path.join(output_dir, "index.html")
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(html)

    return path
