import os
import re
from datetime import datetime, timedelta
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
body { background: var(--bg); color: var(--text); font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', 'PingFang TC', sans-serif; font-size: 13px; padding: 14px; padding-top: 58px; }

/* ── STICKY NAV ── */
.sticky-nav {
  position: fixed;
  top: 0; left: 0; right: 0;
  z-index: 1000;
  background: rgba(13,17,23,0.95);
  backdrop-filter: blur(8px);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 4px;
  padding: 0 14px;
  height: 44px;
  overflow-x: auto;
  white-space: nowrap;
  scrollbar-width: none;
}
.sticky-nav::-webkit-scrollbar { display: none; }
.nav-brand { font-size: 13px; font-weight: 900; color: var(--gold); margin-right: 8px; flex-shrink: 0; }
.nav-link {
  font-size: 11px;
  color: var(--muted);
  text-decoration: none;
  padding: 4px 10px;
  border-radius: 5px;
  flex-shrink: 0;
  transition: background 0.15s, color 0.15s;
}
.nav-link:hover { background: var(--card2); color: var(--text); }

/* ── HEADER ── */
.header { background: linear-gradient(135deg,#0f1923,#1a2535); border: 1px solid var(--border); border-radius: 12px; padding: 16px 20px; margin-bottom: 12px; display: flex; justify-content: space-between; align-items: center; flex-wrap: wrap; gap: 12px; }
.header-left h1 { font-size: 22px; font-weight: 900; color: #fff; }
.header-left .sub { font-size: 12px; color: var(--muted); margin-top: 3px; }
.header-right { display: flex; gap: 8px; align-items: center; }
.date-badge { background: var(--gold); color: #000; font-weight: 800; font-size: 12px; padding: 4px 10px; border-radius: 6px; }

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
.brief-body { font-size: 12px; color: var(--text); line-height: 1.7; white-space: pre-wrap; }

/* ── SECTOR HEATMAP ── */
.sector-grid { display: flex; flex-wrap: wrap; gap: 10px; }
.sector-block { background: var(--card2); border-radius: 8px; padding: 10px 14px; min-width: 180px; flex: 1; }
.sector-name { font-size: 11px; font-weight: 800; color: var(--muted); margin-bottom: 4px; }
.sector-avg  { font-size: 18px; font-weight: 900; margin-bottom: 6px; }
.sector-avg.high { color: var(--green); }
.sector-avg.mid  { color: var(--gold); }
.sector-avg.low  { color: var(--red); }
.sector-tickers { display: flex; flex-wrap: wrap; gap: 4px; }
.sector-ticker-chip { font-size: 10px; font-weight: 700; padding: 2px 6px; border-radius: 4px; }
.sector-ticker-chip.high { background: rgba(46,204,113,0.15); color: var(--green); }
.sector-ticker-chip.mid  { background: rgba(246,201,14,0.12);  color: var(--gold); }
.sector-ticker-chip.low  { background: rgba(231,76,60,0.15);   color: var(--red); }

/* ── LEADERBOARD ── */
.lb-table-wrap { overflow-x: auto; }
.lb-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.lb-table th { background: var(--card2); color: var(--muted); padding: 7px 10px; text-align: left; font-weight: 700; border-bottom: 1px solid var(--border); font-size: 11px; text-transform: uppercase; white-space: nowrap; }
.lb-table td { padding: 8px 10px; border-bottom: 1px solid rgba(45,55,72,0.4); vertical-align: middle; }
.lb-table tr:last-child td { border-bottom: none; }
.lb-table tr:hover td { background: rgba(255,255,255,0.02); }
.ticker-cell { font-weight: 800; font-size: 14px; color: #fff; }
.name-cell   { font-size: 11px; color: var(--muted); }
.price-cell  { font-weight: 700; }
.chg-pos { color: var(--green); font-weight: 700; }
.chg-neg { color: var(--red);   font-weight: 700; }
.score-bar-wrap { display: flex; align-items: center; gap: 8px; }
.score-bar { height: 6px; border-radius: 3px; background: var(--card2); flex: 1; overflow: hidden; min-width: 60px; }
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
.sparkline-cell { min-width: 68px; }

/* ── ALERT HISTORY ── */
.alert-table { width: 100%; border-collapse: collapse; font-size: 12px; }
.alert-table th { background: var(--card2); color: var(--muted); padding: 6px 10px; text-align: left; font-weight: 700; border-bottom: 1px solid var(--border); font-size: 11px; text-transform: uppercase; }
.alert-table td { padding: 7px 10px; border-bottom: 1px solid rgba(45,55,72,0.3); }
.alert-table tr:last-child td { border-bottom: none; }

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

/* ── ENTRY / TIMING SECTION ── */
.sc-entry-section { border-top: 1px solid var(--border); margin-top: 10px; padding-top: 10px; }
.sc-entry-label { font-size: 10px; font-weight: 800; color: var(--gold); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 4px; }
.sc-entry-body { font-size: 11px; color: var(--text); line-height: 1.7; white-space: pre-wrap; }

/* ── NEWS FEED ── */
.sc-news { margin-bottom: 10px; }
.sc-news-label { font-size: 10px; font-weight: 800; color: var(--purple); text-transform: uppercase; letter-spacing: 0.5px; margin-bottom: 5px; }
.sc-news-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 4px; }
.sc-news-item { font-size: 10px; color: var(--text); line-height: 1.4; padding: 4px 6px; background: var(--card2); border-radius: 4px; }
.sc-news-publisher { font-size: 9px; color: var(--muted); margin-top: 1px; }

/* ── SENTIMENT BADGE ── */
.sentiment-circle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  font-size: 12px;
  font-weight: 900;
  flex-shrink: 0;
}
.sentiment-pos  { background: rgba(46,204,113,0.2);  color: var(--green);  border: 1px solid rgba(46,204,113,0.4); }
.sentiment-neg  { background: rgba(231,76,60,0.2);   color: var(--red);    border: 1px solid rgba(231,76,60,0.4); }
.sentiment-neut { background: rgba(136,146,164,0.2); color: var(--muted);  border: 1px solid rgba(136,146,164,0.3); }
.sc-sentiment-row { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 10px; }
.sc-sentiment-text { font-size: 11px; color: var(--text); line-height: 1.5; flex: 1; }
.sc-sentiment-label { font-size: 9px; font-weight: 800; color: var(--muted); text-transform: uppercase; letter-spacing: 0.4px; }

/* ── ANALYST TARGET ── */
.sc-analyst-row { font-size: 11px; color: var(--muted); display: flex; gap: 12px; flex-wrap: wrap; margin-bottom: 8px; }
.sc-analyst-row strong { color: var(--text); }

/* ── COPY BUTTON ── */
.copy-btn {
  display: block;
  width: 100%;
  margin-top: 10px;
  padding: 6px 0;
  background: rgba(59,130,246,0.12);
  border: 1px solid rgba(59,130,246,0.3);
  border-radius: 6px;
  color: var(--blue);
  font-size: 11px;
  font-weight: 700;
  cursor: pointer;
  transition: background 0.15s, color 0.15s;
  text-align: center;
}
.copy-btn:hover { background: rgba(59,130,246,0.22); }

/* ── FOOTER ── */
.footer { text-align: center; padding: 16px; color: var(--muted); font-size: 11px; margin-top: 4px; }
</style>
</head>
<body>

<!-- STICKY NAV -->
<nav class="sticky-nav">
  <span class="nav-brand">📊 股票監控</span>
  <a class="nav-link" href="#market-overview">大盤</a>
  <a class="nav-link" href="#morning-brief">早盤簡報</a>
  <a class="nav-link" href="#sector-heatmap">板塊</a>
  <a class="nav-link" href="#leaderboard">排行榜</a>
  <a class="nav-link" href="#alert-history">警示歷史</a>
  <a class="nav-link" href="#stock-cards">個股詳情</a>
  {% for s in stocks_sorted %}
  <a class="nav-link" href="#stock-{{ s.ticker }}">{{ s.ticker }}</a>
  {% endfor %}
</nav>

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
<div id="market-overview" class="market-grid">
{% for ticker, m in market.items() %}
  <div class="market-card {{ m.direction }}">
    <div class="market-name">{{ m.name }}</div>
    <div class="market-price">{{ "%.2f"|format(m.price) }}</div>
    <div class="market-chg {{ m.direction }}">{{ "%+.2f"|format(m.change_pct) }}%</div>
  </div>
{% endfor %}
</div>

<!-- MORNING BRIEF -->
<div id="morning-brief" class="card">
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

<!-- SECTOR HEATMAP -->
<div id="sector-heatmap" class="card">
  <div class="card-title"><span class="icon">🗺️</span>板塊熱力圖</div>
  <div class="sector-grid">
  {% for sector in sectors %}
    {% set avg = sector.avg_score %}
    {% set avg_class = "high" if avg >= 60 else ("mid" if avg >= 40 else "low") %}
    <div class="sector-block">
      <div class="sector-name">{{ sector.name }}</div>
      <div class="sector-avg {{ avg_class }}">{{ avg }}</div>
      <div class="sector-tickers">
        {% for t in sector.tickers %}
          {% set t_class = "high" if t.score >= 60 else ("mid" if t.score >= 40 else "low") %}
          <span class="sector-ticker-chip {{ t_class }}">{{ t.ticker }} {{ t.score }}</span>
        {% endfor %}
      </div>
    </div>
  {% endfor %}
  </div>
</div>

<!-- SIGNAL LEADERBOARD -->
<div id="leaderboard" class="card">
  <div class="card-title"><span class="icon">🏆</span>信號排行榜</div>
  <div class="lb-table-wrap">
  <table class="lb-table">
    <thead>
      <tr>
        <th>股票</th>
        <th>現價</th>
        <th>漲跌</th>
        <th>信號分數</th>
        <th>趨勢</th>
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
        <td class="sparkline-cell">
          {% if s.sparkline_points and s.sparkline_points|length >= 2 %}
            {{ s.sparkline_svg | safe }}
          {% else %}
            <span style="color:var(--muted)">—</span>
          {% endif %}
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
</div>

<!-- ALERT HISTORY -->
<div id="alert-history" class="card">
  <div class="card-title"><span class="icon">🚨</span>警示歷史</div>
  {% if alert_history %}
  <table class="alert-table">
    <thead>
      <tr>
        <th>日期</th>
        <th>股票</th>
        <th>分數</th>
        <th>強弱</th>
      </tr>
    </thead>
    <tbody>
    {% for a in alert_history[-10:] | reverse %}
      {% set a_class = "high" if a.score >= 60 else ("mid" if a.score >= 40 else "low") %}
      <tr>
        <td style="color:var(--muted)">{{ a.date }}</td>
        <td><strong>{{ a.ticker }}</strong></td>
        <td class="score-num {{ a_class }}">{{ a.score }}</td>
        <td><span class="strength-badge {{ 'strength-buy' if a.score >= 60 else ('strength-neut' if a.score >= 40 else 'strength-sell') }}">{{ a.strength }}</span></td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
  {% else %}
  <p style="color:var(--muted);font-size:12px;">暫無警示記錄。</p>
  {% endif %}
</div>

<!-- STOCK CARDS -->
<div id="stock-cards" class="card">
  <div class="card-title"><span class="icon">📈</span>個股詳情</div>
  <div class="stock-grid">
  {% for s in stocks_sorted %}
    {% set sc = s.score %}
    {% set sc_class = "high" if sc >= 60 else ("mid" if sc >= 40 else "low") %}
    {% set chg_class = "chg-pos" if s.price_change_pct >= 0 else "chg-neg" %}
    <div id="stock-{{ s.ticker }}" class="stock-card">
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
        {% if s.get('sentiment') and s.sentiment.score is not none %}
          {% set sent_score = s.sentiment.score %}
          {% set sent_class = "sentiment-pos" if sent_score >= 3 else ("sentiment-neg" if sent_score <= -3 else "sentiment-neut") %}
          {% set sent_sign = "+" if sent_score > 0 else "" %}
          <span class="sentiment-circle {{ sent_class }}" title="新聞情緒：{{ sent_sign }}{{ sent_score }}">{{ sent_sign }}{{ sent_score }}</span>
        {% endif %}
      </div>

      {% if s.get('sentiment') and s.sentiment.score is not none %}
      <div class="sc-sentiment-row">
        <div>
          <div class="sc-sentiment-label">新聞情緒分析</div>
          <div class="sc-sentiment-text">{{ s.sentiment.summary }}</div>
        </div>
      </div>
      {% endif %}

      {% if s.get('analyst_recom') or s.get('target_price') %}
      <div class="sc-analyst-row">
        {% if s.target_price %}
        <span>分析師目標價：<strong>${{ s.target_price }}</strong></span>
        {% endif %}
        {% if s.analyst_recom %}
        <span>評級：<strong>{{ s.analyst_recom }}</strong></span>
        {% endif %}
      </div>
      {% endif %}

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

      {% if s.get('news') and s.news %}
      <hr class="sc-divider">
      <div class="sc-news">
        <div class="sc-news-label">📰 最新新聞</div>
        <ul class="sc-news-list">
          {% for item in s.news %}
          <li class="sc-news-item">
            {{ item.title }}
            {% if item.publisher %}
            <div class="sc-news-publisher">{{ item.publisher }}</div>
            {% endif %}
          </li>
          {% endfor %}
        </ul>
      </div>
      {% endif %}

      {% if s.ai_view %}
      <hr class="sc-divider">
      <div class="sc-ai-label">🤖 AI 快速判讀</div>
      <div class="sc-ai-body">{{ s.ai_view }}</div>
      {% endif %}

      {% if s.entry %}
      <div class="sc-entry-section">
        <div class="sc-entry-label">⏱ 擇時建議</div>
        <div class="sc-entry-body">{{ s.entry }}</div>
      </div>
      {% endif %}

      <button
        class="copy-btn"
        data-ticker="{{ s.ticker }}"
        data-price="{{ "%.2f"|format(s.price) }}"
        data-score="{{ sc }}"
        data-entry="{{ s.entry | replace('"', '&quot;') }}"
        onclick="copyTradeSetup(this)"
      >複製交易設置</button>
    </div>
  {% endfor %}
  </div>
</div>

<div class="footer">⚠️ 本報告由 AI 自動生成，僅供參考，不構成投資建議。投資有風險，請審慎評估。</div>

<script>
function copyTradeSetup(btn) {
  const ticker  = btn.dataset.ticker;
  const price   = btn.dataset.price;
  const score   = btn.dataset.score;
  const entry   = btn.dataset.entry || "";

  // Try to parse entry/stop/target from AI text
  function extractPrice(text, keywords) {
    for (const kw of keywords) {
      // Match keyword followed by optional spaces/colon then a dollar sign or plain number
      const re = new RegExp(kw + '[\\s：:]*[$＄]?([\\d]+\\.?[\\d]*)');
      const m = text.match(re);
      if (m) return m[1];
    }
    // Generic $ or ＄ price pattern near keyword
    return null;
  }

  const entryPrice  = extractPrice(entry, ['買入', '入場', '建議買入', 'buy', 'entry']) || price;
  const stopPrice   = extractPrice(entry, ['止損', 'stop', '停損']);
  const targetPrice = extractPrice(entry, ['目標', 'target', '第一目標', '目標價']);

  let text;
  if (stopPrice || targetPrice) {
    text = `[${ticker}] 入場：$${entryPrice}`;
    if (stopPrice)   text += ` | 止損：$${stopPrice}`;
    if (targetPrice) text += ` | 目標：$${targetPrice}`;
    text += ` | 信號：${score}/100`;
  } else {
    // Fallback: copy full entry text or price+score
    text = entry
      ? `[${ticker}] ${entry} | 信號：${score}/100`
      : `[${ticker}] 現價：$${price} | 信號：${score}/100`;
  }

  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.textContent;
    btn.textContent = "已複製 ✓";
    btn.style.background = "rgba(46,204,113,0.18)";
    btn.style.color = "var(--green)";
    setTimeout(() => {
      btn.textContent = orig;
      btn.style.background = "";
      btn.style.color = "";
    }, 2000);
  }).catch(() => {
    btn.textContent = "複製失敗";
    setTimeout(() => { btn.textContent = "複製交易設置"; }, 2000);
  });
}
</script>
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
            if (
                f"【{key}" in line
                or f"**{key}" in line
                or line.strip().startswith(f"{key}・")
                or line.strip().startswith(f"[{key}")
            ):
                matched = key
                break
        if matched:
            if current_key:
                body = "\n".join(current_lines)
                # Trim leading/trailing blank lines, collapse 3+ blank lines to 1
                body = re.sub(r"\n{3,}", "\n\n", body).strip()
                sections.append({"label": labels[current_key], "body": body})
            current_key = matched
            current_lines = []
        else:
            if current_key:
                clean = line.replace("**", "").replace("【", "").replace("】", "")
                current_lines.append(clean)

    if current_key:
        body = "\n".join(current_lines)
        body = re.sub(r"\n{3,}", "\n\n", body).strip()
        sections.append({"label": labels[current_key], "body": body})

    if not sections:
        body = re.sub(r"\n{3,}", "\n\n", raw).strip()
        sections = [{"label": "早盤分析", "body": body}]

    return sections


def _build_sparkline_svg(points: list[float], width: int = 60, height: int = 20) -> str:
    """Return an inline SVG polyline for the given score points."""
    if len(points) < 2:
        return ""
    mn, mx = min(points), max(points)
    rng = mx - mn or 1  # avoid divide-by-zero
    step = (width - 4) / (len(points) - 1)

    coords = []
    for i, v in enumerate(points):
        x = 2 + i * step
        y = height - 2 - ((v - mn) / rng) * (height - 4)
        coords.append(f"{x:.1f},{y:.1f}")

    color = "#2ecc71" if points[-1] >= points[0] else "#e74c3c"
    pts_str = " ".join(coords)
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<polyline points="{pts_str}" fill="none" stroke="{color}" '
        f'stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>'
        f'</svg>'
    )


def _build_sparklines(stocks_sorted: list, score_history: dict) -> None:
    """Attach sparkline_points and sparkline_svg to each stock dict in-place."""
    # Sort history dates ascending, keep last 7
    sorted_dates = sorted(score_history.keys())[-7:]

    for s in stocks_sorted:
        ticker = s["ticker"]
        pts = []
        for d in sorted_dates:
            day_scores = score_history.get(d, {})
            if ticker in day_scores:
                pts.append(float(day_scores[ticker]))
        s["sparkline_points"] = pts
        s["sparkline_svg"] = _build_sparkline_svg(pts) if len(pts) >= 2 else ""


def _build_sector_groups(stocks_sorted: list) -> list[dict]:
    """Group stocks by sector and compute average score per sector."""
    sectors: dict[str, list] = {}
    for s in stocks_sorted:
        sec = s.get("sector") or "Unknown"
        sectors.setdefault(sec, []).append(s)

    result = []
    for name, members in sectors.items():
        avg = round(sum(m["score"] for m in members) / len(members))
        result.append({
            "name": name,
            "avg_score": avg,
            "tickers": [{"ticker": m["ticker"], "score": m["score"]} for m in members],
        })
    # Sort by average score descending
    result.sort(key=lambda x: x["avg_score"], reverse=True)
    return result


def generate_dashboard(
    date: str,
    market_overview: dict,
    morning_brief: str,
    stock_results: list,
    output_dir: str = "outputs",
    score_history: dict | None = None,
    alert_history: list | None = None,
) -> str:
    os.makedirs(output_dir, exist_ok=True)

    stocks_sorted = sorted(stock_results, key=lambda x: x["score"], reverse=True)
    brief_sections = _parse_brief(morning_brief)

    # Sparklines
    if score_history:
        _build_sparklines(stocks_sorted, score_history)
    else:
        for s in stocks_sorted:
            s["sparkline_points"] = []
            s["sparkline_svg"] = ""

    # Sector heatmap
    sectors = _build_sector_groups(stocks_sorted)

    html = Template(DASHBOARD_HTML).render(
        date=date,
        market=market_overview,
        brief_sections=brief_sections,
        stocks_sorted=stocks_sorted,
        sectors=sectors,
        alert_history=alert_history or [],
    )

    filename = f"report_{datetime.now().strftime('%Y%m%d')}.html"
    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    # Always overwrite index.html for GitHub Pages
    latest_path = os.path.join(output_dir, "index.html")
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(html)

    return path
