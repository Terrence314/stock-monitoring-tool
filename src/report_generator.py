import os
import re
from datetime import datetime, timedelta
from jinja2 import Template

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>SIGNAL MONITOR · {{ date }}</title>
<link rel="preconnect" href="https://fonts.googleapis.com">
<link rel="preconnect" href="https://fonts.gstatic.com" crossorigin>
<link href="https://fonts.googleapis.com/css2?family=JetBrains+Mono:wght@400;500;600;700&family=Inter:wght@400;500;600;700;800;900&display=swap" rel="stylesheet">
<style>
/* ── DESIGN TOKENS ── */
:root {
  --bg-base:      #0a0a0f;
  --bg-surface:   #12121a;
  --bg-elevated:  #1a1a28;
  --border:       #2a2a3d;
  --border-accent:#3d3d5c;
  --text-primary: #e8e8f0;
  --text-secondary:#8888a8;
  --text-muted:   #4a4a6a;
  --accent-blue:  #4d9ef7;
  --accent-green: #00d4a0;
  --accent-red:   #ff4d6a;
  --accent-amber: #f7b84d;
  --accent-purple:#9b6dff;
  --glow-blue:    0 0 20px rgba(77,158,247,0.15);
  --glow-green:   0 0 20px rgba(0,212,160,0.15);
  --glow-red:     0 0 20px rgba(255,77,106,0.12);
  --mono: 'JetBrains Mono', 'Fira Code', monospace;
  --sans: 'Inter', system-ui, sans-serif;
}

/* ── RESET ── */
*, *::before, *::after { box-sizing: border-box; margin: 0; padding: 0; }

body {
  background: var(--bg-base);
  color: var(--text-primary);
  font-family: var(--sans);
  font-size: 13px;
  line-height: 1.5;
  padding: 0 16px 32px;
  padding-top: 158px; /* nav + ticker tape + filter bar */
  min-height: 100vh;
}

/* ── STICKY NAV ── */
.sticky-nav {
  position: fixed;
  top: 0; left: 0; right: 0;
  z-index: 1000;
  background: rgba(10,10,15,0.96);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
  border-bottom: 1px solid transparent;
  background-clip: padding-box;
}
.sticky-nav::after {
  content: '';
  position: absolute;
  inset: 0;
  border-bottom: 1px solid var(--border);
  pointer-events: none;
}

/* Header bar inside nav */
.nav-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 20px;
  height: 48px;
  border-bottom: 1px solid var(--border);
}
.nav-brand {
  font-family: var(--mono);
  font-size: 13px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: 0.08em;
  display: flex;
  align-items: center;
  gap: 8px;
}
.nav-brand-icon { color: var(--accent-blue); font-size: 15px; }
.nav-brand-accent { color: var(--accent-blue); }
.nav-timestamp {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-secondary);
  letter-spacing: 0.04em;
}
.nav-timestamp .tz-label { color: var(--accent-amber); margin-left: 4px; }

/* Nav pill links */
.nav-pills {
  display: flex;
  align-items: center;
  gap: 2px;
  padding: 0 16px;
  height: 36px;
  overflow-x: auto;
  white-space: nowrap;
  scrollbar-width: none;
}
.nav-pills::-webkit-scrollbar { display: none; }
.nav-link {
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 600;
  color: var(--text-muted);
  text-decoration: none;
  padding: 4px 10px;
  border-radius: 4px;
  border: 1px solid transparent;
  flex-shrink: 0;
  letter-spacing: 0.06em;
  transition: color 0.15s, border-color 0.15px, background 0.15s;
}
.nav-link:hover {
  color: var(--accent-blue);
  background: rgba(77,158,247,0.06);
  border-color: rgba(77,158,247,0.2);
}
.nav-link.active {
  color: var(--accent-blue);
  border-color: rgba(77,158,247,0.3);
  box-shadow: 0 0 8px rgba(77,158,247,0.1);
}
.nav-ticker-sep {
  width: 1px;
  height: 14px;
  background: var(--border);
  margin: 0 4px;
  flex-shrink: 0;
}

/* ── TICKER TAPE ── */
.ticker-tape {
  height: 28px;
  background: var(--bg-surface);
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  overflow: hidden;
  position: relative;
}
.ticker-tape::before,
.ticker-tape::after {
  content: '';
  position: absolute;
  top: 0; bottom: 0;
  width: 40px;
  z-index: 2;
  pointer-events: none;
}
.ticker-tape::before { left: 0; background: linear-gradient(90deg, var(--bg-surface), transparent); }
.ticker-tape::after  { right: 0; background: linear-gradient(-90deg, var(--bg-surface), transparent); }
.ticker-tape-inner {
  display: flex;
  gap: 0;
  animation: tape-scroll 40s linear infinite;
  will-change: transform;
}
@keyframes tape-scroll {
  0%   { transform: translateX(0); }
  100% { transform: translateX(-50%); }
}
.tape-item {
  display: flex;
  align-items: center;
  gap: 6px;
  padding: 0 20px;
  border-right: 1px solid var(--border);
  white-space: nowrap;
  flex-shrink: 0;
}
.tape-ticker {
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 700;
  color: var(--text-secondary);
  letter-spacing: 0.06em;
}
.tape-price {
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 600;
  color: var(--text-primary);
}
.tape-chg {
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 600;
}
.tape-chg.up   { color: var(--accent-green); }
.tape-chg.down { color: var(--accent-red); }

/* ── SECTION WRAPPER ── */
.section-wrap {
  max-width: 1400px;
  margin: 0 auto;
}

/* ── PANEL (replaces .card) ── */
.panel {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 20px 24px;
  margin-bottom: 16px;
  position: relative;
  overflow: hidden;
}
.panel::before {
  content: '';
  position: absolute;
  top: 0; left: 0; right: 0;
  height: 1px;
  background: linear-gradient(90deg, transparent, var(--border-accent), transparent);
}
.panel-title {
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 700;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.12em;
  margin-bottom: 16px;
  padding-bottom: 12px;
  border-bottom: 1px solid var(--border);
  display: flex;
  align-items: center;
  gap: 8px;
}
.panel-title-accent {
  width: 3px;
  height: 14px;
  border-radius: 2px;
  flex-shrink: 0;
}
.panel-title-accent.blue   { background: var(--accent-blue); }
.panel-title-accent.green  { background: var(--accent-green); }
.panel-title-accent.amber  { background: var(--accent-amber); }
.panel-title-accent.purple { background: var(--accent-purple); }
.panel-title-accent.red    { background: var(--accent-red); }

/* ── MARKET OVERVIEW ── */
#market-overview {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(150px, 1fr));
  gap: 10px;
  margin-bottom: 16px;
}
.market-card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 10px;
  padding: 14px 16px;
  position: relative;
  overflow: hidden;
  transition: transform 0.15s, box-shadow 0.15s;
}
.market-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--glow-blue);
}
.market-card.up   { border-left: 2px solid var(--accent-green); }
.market-card.down { border-left: 2px solid var(--accent-red); }
.market-card.up::after {
  content: '';
  position: absolute;
  top: 0; right: 0; bottom: 0;
  width: 40%;
  background: linear-gradient(-90deg, rgba(0,212,160,0.04), transparent);
  pointer-events: none;
}
.market-card.down::after {
  content: '';
  position: absolute;
  top: 0; right: 0; bottom: 0;
  width: 40%;
  background: linear-gradient(-90deg, rgba(255,77,106,0.04), transparent);
  pointer-events: none;
}
.market-name  {
  font-family: var(--mono);
  font-size: 9px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-bottom: 6px;
}
.market-price {
  font-family: var(--mono);
  font-size: 18px;
  font-weight: 700;
  color: var(--text-primary);
  margin-bottom: 2px;
  letter-spacing: -0.02em;
}
.market-chg {
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 600;
  display: flex;
  align-items: center;
  gap: 3px;
}
.market-chg.up   { color: var(--accent-green); }
.market-chg.down { color: var(--accent-red); }

/* ── MORNING BRIEF ── */
.brief-grid {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 12px;
}
@media(max-width:700px){ .brief-grid { grid-template-columns: 1fr; } }
.brief-section {
  background: var(--bg-elevated);
  border-radius: 8px;
  padding: 14px 16px;
  border-left: 2px solid transparent;
}
.brief-section:nth-child(1) { border-left-color: var(--accent-blue); }
.brief-section:nth-child(2) { border-left-color: var(--accent-purple); }
.brief-section:nth-child(3) { border-left-color: var(--accent-amber); }
.brief-section:nth-child(4) { border-left-color: var(--accent-green); }
.brief-label {
  font-family: var(--mono);
  font-size: 9px;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.12em;
  margin-bottom: 8px;
  color: var(--text-secondary);
}
.brief-section:nth-child(1) .brief-label { color: var(--accent-blue); }
.brief-section:nth-child(2) .brief-label { color: var(--accent-purple); }
.brief-section:nth-child(3) .brief-label { color: var(--accent-amber); }
.brief-section:nth-child(4) .brief-label { color: var(--accent-green); }
.brief-body {
  font-size: 12px;
  color: var(--text-primary);
  line-height: 1.75;
  white-space: pre-wrap;
}

/* ── SECTOR HEATMAP ── */
.sector-heatmap-grid {
  display: flex;
  flex-wrap: wrap;
  gap: 10px;
}
.sector-block {
  border-radius: 10px;
  padding: 14px 16px;
  min-width: 160px;
  flex: 1;
  position: relative;
  overflow: hidden;
  border: 1px solid var(--border);
  transition: transform 0.15s;
}
.sector-block:hover { transform: translateY(-1px); }
.sector-block.heat-high {
  background: linear-gradient(135deg, rgba(0,212,160,0.08), rgba(0,212,160,0.02));
  border-color: rgba(0,212,160,0.2);
}
.sector-block.heat-mid {
  background: linear-gradient(135deg, rgba(247,184,77,0.07), rgba(247,184,77,0.02));
  border-color: rgba(247,184,77,0.18);
}
.sector-block.heat-low {
  background: linear-gradient(135deg, rgba(255,77,106,0.07), rgba(255,77,106,0.02));
  border-color: rgba(255,77,106,0.18);
}
.sector-name {
  font-family: var(--mono);
  font-size: 9px;
  font-weight: 700;
  color: var(--text-secondary);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-bottom: 6px;
}
.sector-avg {
  font-family: var(--mono);
  font-size: 28px;
  font-weight: 700;
  margin-bottom: 8px;
  letter-spacing: -0.03em;
}
.sector-avg.high { color: var(--accent-green); }
.sector-avg.mid  { color: var(--accent-amber); }
.sector-avg.low  { color: var(--accent-red); }
.sector-tickers { display: flex; flex-wrap: wrap; gap: 4px; }
.sector-ticker-chip {
  font-family: var(--mono);
  font-size: 9px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 3px;
  letter-spacing: 0.04em;
}
.sector-ticker-chip.high { background: rgba(0,212,160,0.12); color: var(--accent-green); border: 1px solid rgba(0,212,160,0.2); }
.sector-ticker-chip.mid  { background: rgba(247,184,77,0.1);  color: var(--accent-amber); border: 1px solid rgba(247,184,77,0.2); }
.sector-ticker-chip.low  { background: rgba(255,77,106,0.1);  color: var(--accent-red); border: 1px solid rgba(255,77,106,0.18); }

/* ── LEADERBOARD ── */
.lb-table-wrap { overflow-x: auto; }
.lb-table {
  width: 100%;
  border-collapse: collapse;
  font-size: 12px;
}
.lb-table th {
  background: var(--bg-elevated);
  color: var(--text-muted);
  padding: 10px 12px;
  text-align: left;
  font-family: var(--mono);
  font-weight: 600;
  font-size: 9px;
  letter-spacing: 0.1em;
  text-transform: uppercase;
  border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.lb-table td {
  padding: 10px 12px;
  border-bottom: 1px solid rgba(42,42,61,0.6);
  vertical-align: middle;
}
.lb-table tbody tr:nth-child(odd) td  { background: rgba(26,26,40,0.3); }
.lb-table tbody tr:nth-child(even) td { background: transparent; }
.lb-table tbody tr:hover td {
  background: var(--bg-elevated);
  transition: background 0.1s;
}
.lb-table tbody tr:nth-child(1) td { border-left: 2px solid var(--accent-blue); }
.lb-table tbody tr:nth-child(2) td { border-left: 2px solid rgba(77,158,247,0.5); }
.lb-table tbody tr:nth-child(3) td { border-left: 2px solid rgba(77,158,247,0.25); }
.lb-table tr:last-child td { border-bottom: none; }

.ticker-cell {
  font-family: var(--mono);
  font-weight: 700;
  font-size: 14px;
  color: var(--text-primary);
  letter-spacing: 0.03em;
}
.name-cell   { font-size: 11px; color: var(--text-secondary); margin-top: 1px; }
.price-cell  { font-family: var(--mono); font-weight: 600; font-size: 13px; }
.chg-pos { color: var(--accent-green); font-family: var(--mono); font-weight: 600; }
.chg-neg { color: var(--accent-red);   font-family: var(--mono); font-weight: 600; }

.score-bar-wrap { display: flex; align-items: center; gap: 8px; min-width: 120px; }
.score-bar {
  height: 4px;
  border-radius: 2px;
  background: var(--bg-elevated);
  flex: 1;
  overflow: hidden;
  min-width: 60px;
}
.score-fill { height: 100%; border-radius: 2px; }
.score-fill.high { background: linear-gradient(90deg, var(--accent-green), #00ff9d); }
.score-fill.mid  { background: linear-gradient(90deg, var(--accent-amber), #ffdc7a); }
.score-fill.low  { background: linear-gradient(90deg, var(--accent-red), #ff8fa0); }
.score-num {
  font-family: var(--mono);
  font-weight: 700;
  font-size: 13px;
  min-width: 28px;
  text-align: right;
}
.score-num.high { color: var(--accent-green); }
.score-num.mid  { color: var(--accent-amber); }
.score-num.low  { color: var(--accent-red); }

.strength-badge {
  font-family: var(--mono);
  font-size: 9px;
  font-weight: 700;
  padding: 3px 8px;
  border-radius: 3px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
  white-space: nowrap;
}
.strength-buy  { background: rgba(0,212,160,0.1); color: var(--accent-green); border: 1px solid rgba(0,212,160,0.25); }
.strength-neut { background: rgba(247,184,77,0.1); color: var(--accent-amber); border: 1px solid rgba(247,184,77,0.25); }
.strength-sell { background: rgba(255,77,106,0.1); color: var(--accent-red); border: 1px solid rgba(255,77,106,0.22); }
.sparkline-cell { min-width: 72px; }

/* ── ALERT HISTORY — Timeline ── */
.alert-timeline {
  display: flex;
  flex-direction: column;
  gap: 0;
  position: relative;
  padding-left: 24px;
}
.alert-timeline::before {
  content: '';
  position: absolute;
  left: 7px; top: 8px; bottom: 8px;
  width: 1px;
  background: linear-gradient(180deg, var(--accent-blue), var(--border), transparent);
}
.alert-entry {
  display: flex;
  align-items: flex-start;
  gap: 12px;
  padding: 10px 0;
  position: relative;
}
.alert-dot {
  position: absolute;
  left: -21px;
  top: 14px;
  width: 9px;
  height: 9px;
  border-radius: 50%;
  flex-shrink: 0;
  border: 1px solid var(--bg-base);
}
.alert-dot.high   { background: var(--accent-green); box-shadow: 0 0 6px rgba(0,212,160,0.5); }
.alert-dot.mid    { background: var(--accent-amber); box-shadow: 0 0 6px rgba(247,184,77,0.4); }
.alert-dot.low    { background: var(--accent-red);   box-shadow: 0 0 6px rgba(255,77,106,0.4); }
.alert-date {
  font-family: var(--mono);
  font-size: 10px;
  color: var(--text-muted);
  white-space: nowrap;
  padding-top: 1px;
  min-width: 80px;
}
.alert-ticker-pill {
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 700;
  color: var(--text-primary);
  background: var(--bg-elevated);
  border: 1px solid var(--border-accent);
  padding: 1px 8px;
  border-radius: 4px;
}
.alert-no-data {
  font-size: 12px;
  color: var(--text-muted);
  font-family: var(--mono);
  padding: 8px 0;
}

/* ── STOCK CARDS BENTO ── */
#stock-cards .panel-title { margin-bottom: 20px; }
.stock-bento {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 14px;
}
@media(max-width:768px) { .stock-bento { grid-template-columns: 1fr; } }

.stock-card {
  background: var(--bg-surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 20px;
  position: relative;
  overflow: hidden;
  transition: transform 0.18s, box-shadow 0.18s;
}
.stock-card:hover {
  transform: translateY(-2px);
  box-shadow: var(--glow-blue);
}
.stock-card.signal-high {
  border-color: rgba(0,212,160,0.35);
  box-shadow: var(--glow-green), inset 0 0 0 1px rgba(0,212,160,0.12);
  transform: translateY(-2px);
}
.stock-card.signal-high:hover {
  box-shadow: 0 0 30px rgba(0,212,160,0.22), inset 0 0 0 1px rgba(0,212,160,0.2);
}

/* Card header strip */
.sc-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  margin-bottom: 14px;
}
.sc-ticker {
  font-family: var(--mono);
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.01em;
  line-height: 1;
}
.sc-name {
  font-size: 11px;
  color: var(--text-secondary);
  margin-top: 4px;
  max-width: 160px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}
.sc-header-right { display: flex; align-items: flex-start; gap: 10px; }
.sc-price  { text-align: right; }
.sc-price-val {
  font-family: var(--mono);
  font-size: 22px;
  font-weight: 700;
  color: var(--text-primary);
  letter-spacing: -0.02em;
  line-height: 1;
}
.sc-price-chg {
  font-family: var(--mono);
  font-size: 12px;
  font-weight: 600;
  margin-top: 4px;
  text-align: right;
}
.sc-price-chg.chg-pos { color: var(--accent-green); }
.sc-price-chg.chg-neg { color: var(--accent-red); }

/* Score badge circle */
.sc-score-badge {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  width: 52px;
  height: 52px;
  border-radius: 50%;
  flex-shrink: 0;
  position: relative;
}
.sc-score-badge::before {
  content: '';
  position: absolute;
  inset: -1px;
  border-radius: 50%;
  background: conic-gradient(var(--badge-color, var(--accent-blue)) calc(var(--score-pct, 0) * 1%), var(--border) 0);
  z-index: 0;
}
.sc-score-badge::after {
  content: '';
  position: absolute;
  inset: 3px;
  border-radius: 50%;
  background: var(--bg-surface);
  z-index: 1;
}
.sc-score-badge-inner {
  position: relative;
  z-index: 2;
  display: flex;
  flex-direction: column;
  align-items: center;
}
.sc-score-num {
  font-family: var(--mono);
  font-size: 14px;
  font-weight: 700;
  line-height: 1;
}
.sc-score-label {
  font-family: var(--mono);
  font-size: 7px;
  font-weight: 600;
  color: var(--text-muted);
  letter-spacing: 0.06em;
  text-transform: uppercase;
  margin-top: 1px;
}
.score-high-badge .sc-score-num { color: var(--accent-green); }
.score-high-badge { --badge-color: var(--accent-green); filter: drop-shadow(0 0 6px rgba(0,212,160,0.4)); }
.score-mid-badge  .sc-score-num { color: var(--accent-amber); }
.score-mid-badge  { --badge-color: var(--accent-amber); }
.score-low-badge  .sc-score-num { color: var(--accent-red); }
.score-low-badge  { --badge-color: var(--accent-red); }

/* Data row */
.sc-data-row {
  display: flex;
  align-items: center;
  gap: 8px;
  margin-bottom: 12px;
  flex-wrap: wrap;
}

/* Score bar inline */
.sc-score-bar-wrap { display: flex; align-items: center; gap: 8px; margin-bottom: 12px; }
.sc-score-bar {
  flex: 1;
  height: 5px;
  border-radius: 3px;
  background: var(--bg-elevated);
  overflow: hidden;
}
.sc-score-bar-fill {
  height: 100%;
  border-radius: 3px;
  transition: width 0.6s ease;
}
.sc-score-bar-fill.high { background: linear-gradient(90deg, var(--accent-green), #00ff9d); }
.sc-score-bar-fill.mid  { background: linear-gradient(90deg, var(--accent-amber), #ffdc7a); }
.sc-score-bar-fill.low  { background: linear-gradient(90deg, var(--accent-red), #ff8fa0); }

/* Sentiment circle */
.sentiment-circle {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 34px;
  height: 34px;
  border-radius: 50%;
  font-family: var(--mono);
  font-size: 11px;
  font-weight: 700;
  flex-shrink: 0;
}
.sentiment-pos  { background: rgba(0,212,160,0.12); color: var(--accent-green); border: 1px solid rgba(0,212,160,0.3); }
.sentiment-neg  { background: rgba(255,77,106,0.12); color: var(--accent-red);   border: 1px solid rgba(255,77,106,0.3); }
.sentiment-neut { background: rgba(136,136,168,0.1); color: var(--text-secondary); border: 1px solid var(--border); }

.sc-sentiment-row { display: flex; align-items: flex-start; gap: 10px; margin-bottom: 12px; }
.sc-sentiment-text { font-size: 11px; color: var(--text-primary); line-height: 1.55; flex: 1; }
.sc-sentiment-label { font-family: var(--mono); font-size: 9px; font-weight: 600; color: var(--text-muted); text-transform: uppercase; letter-spacing: 0.08em; margin-bottom: 2px; }

/* Earnings warning pulse */
.sc-earnings-warn {
  display: flex;
  align-items: center;
  gap: 6px;
  background: rgba(247,184,77,0.08);
  border: 1px solid rgba(247,184,77,0.3);
  border-radius: 6px;
  padding: 6px 10px;
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 700;
  color: var(--accent-amber);
  margin-bottom: 10px;
  letter-spacing: 0.04em;
}
.earnings-pulse {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--accent-amber);
  animation: pulse-amber 1.6s ease-in-out infinite;
  flex-shrink: 0;
}
@keyframes pulse-amber {
  0%, 100% { box-shadow: 0 0 0 0 rgba(247,184,77,0.5); }
  50%       { box-shadow: 0 0 0 5px rgba(247,184,77,0); }
}

/* Analyst bar */
.sc-analyst-section { margin-bottom: 12px; }
.sc-analyst-label {
  font-family: var(--mono);
  font-size: 9px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 5px;
}
.sc-analyst-bar-wrap {
  display: flex;
  height: 7px;
  border-radius: 4px;
  overflow: hidden;
  width: 100%;
  gap: 1px;
  background: var(--bg-elevated);
}
.sc-analyst-bar-buy  { background: var(--accent-green); }
.sc-analyst-bar-hold { background: var(--accent-amber); opacity: 0.8; }
.sc-analyst-bar-sell { background: var(--accent-red); }
.sc-analyst-counts {
  display: flex;
  gap: 10px;
  margin-top: 4px;
  font-family: var(--mono);
  font-size: 9px;
  font-weight: 600;
}
.sc-analyst-count-buy  { color: var(--accent-green); }
.sc-analyst-count-hold { color: var(--accent-amber); }
.sc-analyst-count-sell { color: var(--accent-red); }
.sc-analyst-period { font-size: 9px; color: var(--text-muted); margin-left: auto; }

/* 52-week range */
.sc-52w-section { margin-bottom: 12px; }
.sc-52w-label {
  font-family: var(--mono);
  font-size: 9px;
  font-weight: 600;
  color: var(--text-muted);
  text-transform: uppercase;
  letter-spacing: 0.08em;
  margin-bottom: 6px;
}
.sc-52w-track {
  height: 4px;
  border-radius: 2px;
  background: var(--bg-elevated);
  width: 100%;
  position: relative;
  margin-bottom: 4px;
}
.sc-52w-fill {
  height: 100%;
  border-radius: 2px;
  background: linear-gradient(90deg, var(--accent-blue), var(--accent-purple));
  position: absolute;
  top: 0; left: 0;
}
.sc-52w-thumb {
  width: 10px;
  height: 10px;
  border-radius: 50%;
  background: var(--text-primary);
  border: 2px solid var(--bg-surface);
  box-shadow: 0 0 6px rgba(255,255,255,0.2);
  position: absolute;
  top: -3px;
  transform: translateX(-50%);
}
.sc-52w-labels {
  display: flex;
  justify-content: space-between;
  font-family: var(--mono);
  font-size: 9px;
  color: var(--text-muted);
}

/* PE ratio */
.sc-pe-row {
  font-family: var(--mono);
  font-size: 11px;
  color: var(--text-secondary);
  margin-bottom: 10px;
}
.sc-pe-row strong { color: var(--text-primary); }

/* Badges row */
.sc-badges { display: flex; gap: 5px; flex-wrap: wrap; margin-bottom: 10px; }
.ma-badge {
  font-family: var(--mono);
  font-size: 9px;
  font-weight: 600;
  padding: 2px 7px;
  border-radius: 3px;
  letter-spacing: 0.04em;
}
.ma5  { background: rgba(247,184,77,0.1); color: var(--accent-amber); border: 1px solid rgba(247,184,77,0.2); }
.ma20 { background: rgba(77,158,247,0.1); color: var(--accent-blue);  border: 1px solid rgba(77,158,247,0.2); }
.ma60 { background: rgba(155,109,255,0.1); color: var(--accent-purple); border: 1px solid rgba(155,109,255,0.2); }
.rsi-badge { background: rgba(255,77,106,0.08); color: var(--accent-red); border: 1px solid rgba(255,77,106,0.18); font-family: var(--mono); font-size: 9px; font-weight: 600; padding: 2px 7px; border-radius: 3px; }
.vol-badge { background: rgba(0,212,160,0.08); color: var(--accent-green); border: 1px solid rgba(0,212,160,0.2); font-family: var(--mono); font-size: 9px; font-weight: 600; padding: 2px 7px; border-radius: 3px; }

/* Signals */
.sc-signals { margin-bottom: 12px; }
.signal-item {
  font-size: 11px;
  color: var(--text-secondary);
  line-height: 1.65;
  padding: 1px 0;
}
.signal-item::before { content: '›'; color: var(--accent-blue); margin-right: 5px; }

/* Divider */
.sc-divider { border: none; border-top: 1px solid var(--border); margin: 12px 0; }

/* Collapsible AI sections */
.sc-collapsible { margin-bottom: 10px; }
.sc-collapsible-trigger {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 6px;
  cursor: pointer;
  padding: 6px 0;
  border-bottom: 1px solid var(--border);
  margin-bottom: 0;
  user-select: none;
  list-style: none;
}
.sc-collapsible-trigger::-webkit-details-marker { display: none; }
.sc-ai-label {
  font-family: var(--mono);
  font-size: 9px;
  font-weight: 700;
  color: var(--accent-blue);
  text-transform: uppercase;
  letter-spacing: 0.1em;
}
.sc-collapsible-arrow {
  font-size: 9px;
  color: var(--text-muted);
  transition: transform 0.2s;
}
details[open] .sc-collapsible-arrow { transform: rotate(180deg); }
.sc-ai-body {
  font-size: 11px;
  color: var(--text-primary);
  line-height: 1.65;
  padding: 8px 0 0;
}

/* Entry section */
.sc-entry-section { border-top: 1px solid var(--border); margin-top: 12px; padding-top: 12px; }
.sc-entry-label {
  font-family: var(--mono);
  font-size: 9px;
  font-weight: 700;
  color: var(--accent-green);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-bottom: 5px;
}
.sc-entry-body { font-size: 11px; color: var(--text-primary); line-height: 1.7; white-space: pre-wrap; }

/* News feed */
.sc-news { margin-bottom: 12px; }
.sc-news-label {
  font-family: var(--mono);
  font-size: 9px;
  font-weight: 700;
  color: var(--accent-purple);
  text-transform: uppercase;
  letter-spacing: 0.1em;
  margin-bottom: 7px;
}
.sc-news-list { list-style: none; padding: 0; margin: 0; display: flex; flex-direction: column; gap: 5px; }
.sc-news-item {
  font-size: 11px;
  color: var(--text-primary);
  line-height: 1.45;
  padding: 6px 8px;
  background: var(--bg-elevated);
  border-radius: 5px;
  border-left: 2px solid var(--border-accent);
}
.sc-news-publisher {
  display: inline-block;
  font-family: var(--mono);
  font-size: 9px;
  color: var(--text-muted);
  background: var(--bg-base);
  padding: 1px 6px;
  border-radius: 3px;
  margin-top: 3px;
}

/* Copy button */
.copy-btn {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 6px;
  width: 100%;
  margin-top: 14px;
  padding: 8px 0;
  background: rgba(77,158,247,0.06);
  border: 1px solid rgba(77,158,247,0.2);
  border-radius: 6px;
  color: var(--accent-blue);
  font-family: var(--mono);
  font-size: 10px;
  font-weight: 600;
  letter-spacing: 0.06em;
  cursor: pointer;
  transition: background 0.15s, box-shadow 0.15s, border-color 0.15s;
  text-transform: uppercase;
}
.copy-btn:hover {
  background: rgba(77,158,247,0.12);
  border-color: rgba(77,158,247,0.4);
  box-shadow: var(--glow-blue);
}

/* ── FOOTER ── */
.footer {
  text-align: center;
  padding: 20px;
  color: var(--text-muted);
  font-family: var(--mono);
  font-size: 10px;
  letter-spacing: 0.06em;
  margin-top: 8px;
}

/* ── RESPONSIVE ── */
@media(max-width:768px) {
  body { padding: 0 10px 24px; }
  #market-overview { grid-template-columns: repeat(auto-fill, minmax(120px, 1fr)); }
  .stock-bento { grid-template-columns: 1fr; }
  .lb-table-wrap { overflow-x: auto; }
}

/* ── FILTER BAR ── */
.filter-bar {
  position: sticky;
  top: 88px;
  z-index: 90;
  background: var(--bg-base);
  border-bottom: 1px solid var(--border);
  padding: 10px 24px;
  display: flex;
  align-items: center;
  gap: 24px;
  backdrop-filter: blur(12px);
}
.filter-label {
  font-family: 'JetBrains Mono', monospace;
  font-size: 10px;
  color: var(--text-muted);
  letter-spacing: 0.1em;
  margin-right: 8px;
}
.filter-btn {
  font-family: 'JetBrains Mono', monospace;
  font-size: 11px;
  padding: 4px 12px;
  border: 1px solid var(--border);
  background: transparent;
  color: var(--text-secondary);
  border-radius: 4px;
  cursor: pointer;
  transition: all 150ms;
  margin-right: 6px;
}
.filter-btn:hover { border-color: var(--accent-blue); color: var(--accent-blue); }
.filter-btn.active { background: var(--accent-blue); border-color: var(--accent-blue); color: #fff; }
.filter-group { display: flex; align-items: center; }
.filter-summary { margin-left: auto; font-family: 'JetBrains Mono', monospace; font-size: 11px; color: var(--text-muted); }

/* ── ASSET TYPE / MARKET BADGES ── */
.asset-badge {
  font-family: var(--mono);
  font-size: 8px;
  font-weight: 700;
  padding: 2px 6px;
  border-radius: 3px;
  letter-spacing: 0.06em;
  text-transform: uppercase;
}
.asset-badge-stock { background: rgba(77,158,247,0.12); color: var(--accent-blue); border: 1px solid rgba(77,158,247,0.25); }
.asset-badge-etf   { background: rgba(155,109,255,0.12); color: var(--accent-purple); border: 1px solid rgba(155,109,255,0.25); }
.asset-badge-market { background: rgba(136,136,168,0.08); color: var(--text-secondary); border: 1px solid var(--border); }

/* ── HIGH-SIGNAL PULSE KEYFRAME ── */
@keyframes pulse-green {
  0%, 100% { box-shadow: var(--glow-green), inset 0 0 0 1px rgba(0,212,160,0.12); }
  50%       { box-shadow: 0 0 28px rgba(0,212,160,0.28), inset 0 0 0 1px rgba(0,212,160,0.2); }
}
.stock-card.signal-high {
  animation: pulse-green 3s ease-in-out infinite;
}
</style>
</head>
<body>

<!-- STICKY NAV -->
<nav class="sticky-nav">
  <div class="nav-header">
    <div class="nav-brand">
      <span class="nav-brand-icon">▲</span>
      SIGNAL<span class="nav-brand-accent">MONITOR</span>
    </div>
    <div class="nav-timestamp" id="live-clock">
      {{ date }} <span class="tz-label">HKT</span>
    </div>
  </div>
  <div class="nav-pills">
    <a class="nav-link" href="#market-overview">[MARKET]</a>
    <a class="nav-link" href="#morning-brief">[BRIEF]</a>
    <a class="nav-link" href="#sector-heatmap">[SECTORS]</a>
    <a class="nav-link" href="#leaderboard">[SIGNALS]</a>
    <a class="nav-link" href="#alert-history">[ALERTS]</a>
    <a class="nav-link" href="#stock-cards">[CARDS]</a>
    <span class="nav-ticker-sep"></span>
    {% for s in stocks_sorted %}
    <a class="nav-link" href="#stock-{{ s.ticker }}">{{ s.ticker }}</a>
    {% endfor %}
  </div>

  <!-- Ticker tape -->
  <div class="ticker-tape">
    <div class="ticker-tape-inner" id="tape-inner">
      {% for ticker, m in market.items() %}
      <div class="tape-item">
        <span class="tape-ticker">{{ ticker }}</span>
        <span class="tape-price">{{ "%.2f"|format(m.price) }}</span>
        <span class="tape-chg {{ m.direction }}">{{ "%+.2f"|format(m.change_pct) }}% {{ "▲" if m.direction == "up" else "▼" }}</span>
      </div>
      {% endfor %}
      {% for s in stocks_sorted %}
      <div class="tape-item">
        <span class="tape-ticker">{{ s.ticker }}</span>
        <span class="tape-price">${{ "%.2f"|format(s.price) }}</span>
        <span class="tape-chg {{ 'up' if s.price_change_pct >= 0 else 'down' }}">{{ "%+.2f"|format(s.price_change_pct) }}% {{ "▲" if s.price_change_pct >= 0 else "▼" }}</span>
      </div>
      {% endfor %}
      {# Duplicate for seamless loop #}
      {% for ticker, m in market.items() %}
      <div class="tape-item">
        <span class="tape-ticker">{{ ticker }}</span>
        <span class="tape-price">{{ "%.2f"|format(m.price) }}</span>
        <span class="tape-chg {{ m.direction }}">{{ "%+.2f"|format(m.change_pct) }}% {{ "▲" if m.direction == "up" else "▼" }}</span>
      </div>
      {% endfor %}
      {% for s in stocks_sorted %}
      <div class="tape-item">
        <span class="tape-ticker">{{ s.ticker }}</span>
        <span class="tape-price">${{ "%.2f"|format(s.price) }}</span>
        <span class="tape-chg {{ 'up' if s.price_change_pct >= 0 else 'down' }}">{{ "%+.2f"|format(s.price_change_pct) }}% {{ "▲" if s.price_change_pct >= 0 else "▼" }}</span>
      </div>
      {% endfor %}
    </div>
  </div>
</nav>

<!-- FILTER BAR -->
<div class="filter-bar">
  <div class="filter-group">
    <span class="filter-label">TYPE</span>
    <button class="filter-btn active" data-filter="type" data-value="all">ALL</button>
    <button class="filter-btn" data-filter="type" data-value="stock">STOCKS</button>
    <button class="filter-btn" data-filter="type" data-value="etf">ETFs</button>
  </div>
  <div class="filter-group">
    <span class="filter-label">MARKET</span>
    <button class="filter-btn active" data-filter="market" data-value="all">ALL</button>
    <button class="filter-btn" data-filter="market" data-value="US">🇺🇸 US</button>
  </div>
  <div class="filter-summary">
    <span id="filter-count">{{ stocks_sorted | length }} instruments</span>
  </div>
</div>

<div class="section-wrap">

<!-- MARKET OVERVIEW -->
<div id="market-overview">
{% for ticker, m in market.items() %}
  <div class="market-card {{ m.direction }}">
    <div class="market-name">{{ m.name }}</div>
    <div class="market-price">{{ "%.2f"|format(m.price) }}</div>
    <div class="market-chg {{ m.direction }}">{{ "▲" if m.direction == "up" else "▼" }} {{ "%+.2f"|format(m.change_pct) }}%</div>
  </div>
{% endfor %}
</div>

<!-- MORNING BRIEF -->
<div id="morning-brief" class="panel">
  <div class="panel-title">
    <span class="panel-title-accent blue"></span>
    MORNING BRIEF — F·G·H·I
  </div>
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
<div id="sector-heatmap" class="panel">
  <div class="panel-title">
    <span class="panel-title-accent purple"></span>
    SECTOR HEATMAP
  </div>
  <div class="sector-heatmap-grid">
  {% for sector in sectors %}
    {% set avg = sector.avg_score %}
    {% set avg_class = "high" if avg >= 60 else ("mid" if avg >= 40 else "low") %}
    {% set heat_class = "heat-high" if avg >= 60 else ("heat-mid" if avg >= 40 else "heat-low") %}
    <div class="sector-block {{ heat_class }}">
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
<div id="leaderboard" class="panel">
  <div class="panel-title">
    <span class="panel-title-accent amber"></span>
    SIGNAL LEADERBOARD
  </div>
  <div class="lb-table-wrap">
  <table class="lb-table">
    <thead>
      <tr>
        <th>TICKER</th>
        <th>PRICE</th>
        <th>CHG%</th>
        <th>SCORE</th>
        <th>TREND</th>
        <th>SIGNAL</th>
        <th>RSI</th>
        <th>MACD HIST</th>
        <th>VOL RATIO</th>
      </tr>
    </thead>
    <tbody>
    {% for s in stocks_sorted %}
      {% set sc = s.score %}
      {% set sc_class = "high" if sc >= 60 else ("mid" if sc >= 40 else "low") %}
      {% set chg_class = "chg-pos" if s.price_change_pct >= 0 else "chg-neg" %}
      {% set str_class = "strength-buy" if sc >= 60 else ("strength-neut" if sc >= 40 else "strength-sell") %}
      <tr class="lb-row" data-type="{{ s.get('asset_type', 'stock') }}" data-market="{{ s.get('market', 'US') }}">
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
            <span style="color:var(--text-muted);font-family:var(--mono)">—</span>
          {% endif %}
        </td>
        <td><span class="strength-badge {{ str_class }}">{{ s.strength }}</span></td>
        <td style="font-family:var(--mono)">{{ s.rsi if s.rsi else "—" }}</td>
        <td style="font-family:var(--mono)">{{ "%.2f"|format(s.macd_hist) if s.macd_hist else "—" }}</td>
        <td style="font-family:var(--mono)">{{ "%.1f"|format(s.vol_ratio) if s.vol_ratio else "—" }}×</td>
      </tr>
    {% endfor %}
    </tbody>
  </table>
  </div>
</div>

<!-- ALERT HISTORY -->
<div id="alert-history" class="panel">
  <div class="panel-title">
    <span class="panel-title-accent red"></span>
    ALERT HISTORY
  </div>
  {% if alert_history %}
  <div class="alert-timeline">
    {% for a in alert_history[-10:] | reverse %}
      {% set a_class = "high" if a.score >= 60 else ("mid" if a.score >= 40 else "low") %}
      {% set str_class = "strength-buy" if a.score >= 60 else ("strength-neut" if a.score >= 40 else "strength-sell") %}
      <div class="alert-entry">
        <span class="alert-dot {{ a_class }}"></span>
        <span class="alert-date">{{ a.date }}</span>
        <span class="alert-ticker-pill">{{ a.ticker }}</span>
        <span class="score-num {{ a_class }}" style="font-size:12px">{{ a.score }}</span>
        <span class="strength-badge {{ str_class }}">{{ a.strength }}</span>
      </div>
    {% endfor %}
  </div>
  {% else %}
  <div class="alert-no-data">// NO ALERT RECORDS</div>
  {% endif %}
</div>

<!-- STOCK CARDS -->
<div id="stock-cards" class="panel">
  <div class="panel-title">
    <span class="panel-title-accent green"></span>
    STOCK SIGNALS
  </div>
  <div class="stock-bento">
  {% for s in stocks_sorted %}
    {% set sc = s.score %}
    {% set sc_class = "high" if sc >= 60 else ("mid" if sc >= 40 else "low") %}
    {% set badge_class = "score-high-badge" if sc >= 60 else ("score-mid-badge" if sc >= 40 else "score-low-badge") %}
    {% set chg_class = "chg-pos" if s.price_change_pct >= 0 else "chg-neg" %}
    {% set high_signal = sc >= 70 %}
    <div id="stock-{{ s.ticker }}" class="stock-card{{ ' signal-high' if high_signal else '' }}" data-type="{{ s.get('asset_type', 'stock') }}" data-market="{{ s.get('market', 'US') }}">

      <!-- Card header -->
      <div class="sc-header">
        <div>
          <div class="sc-ticker">{{ s.ticker }}</div>
          <div class="sc-name">{{ s.name }}</div>
          <div style="display:flex;gap:4px;margin-top:5px;">
            {% set atype = s.get('asset_type', 'stock') %}
            <span class="asset-badge {{ 'asset-badge-stock' if atype == 'stock' else 'asset-badge-etf' }}">{{ atype | upper }}</span>
            <span class="asset-badge asset-badge-market">🇺🇸 {{ s.get('market', 'US') }}</span>
          </div>
        </div>
        <div class="sc-header-right">
          <div class="sc-price">
            <div class="sc-price-val">${{ "%.2f"|format(s.price) }}</div>
            <div class="sc-price-chg {{ chg_class }}">{{ "▲" if s.price_change_pct >= 0 else "▼" }} {{ "%+.2f"|format(s.price_change_pct) }}%</div>
          </div>
          <div class="sc-score-badge {{ badge_class }}" style="--score-pct:{{ sc }}">
            <div class="sc-score-badge-inner">
              <span class="sc-score-num">{{ sc }}</span>
              <span class="sc-score-label">/ 100</span>
            </div>
          </div>
        </div>
      </div>

      <!-- Score bar + strength + sentiment -->
      <div class="sc-score-bar-wrap">
        <div class="sc-score-bar"><div class="sc-score-bar-fill {{ sc_class }}" style="width:{{ sc }}%"></div></div>
        <span class="strength-badge {{ 'strength-buy' if sc >= 60 else ('strength-neut' if sc >= 40 else 'strength-sell') }}">{{ s.strength }}</span>
        {% if s.get('sentiment') and s.sentiment.score is not none %}
          {% set sent_score = s.sentiment.score %}
          {% set sent_class = "sentiment-pos" if sent_score >= 3 else ("sentiment-neg" if sent_score <= -3 else "sentiment-neut") %}
          {% set sent_sign = "+" if sent_score > 0 else "" %}
          <span class="sentiment-circle {{ sent_class }}" title="News Sentiment: {{ sent_sign }}{{ sent_score }}">{{ sent_sign }}{{ sent_score }}</span>
        {% endif %}
      </div>

      {% if s.get('sentiment') and s.sentiment.score is not none %}
      <div class="sc-sentiment-row">
        <div>
          <div class="sc-sentiment-label">NEWS SENTIMENT</div>
          <div class="sc-sentiment-text">{{ s.sentiment.summary }}</div>
        </div>
      </div>
      {% endif %}

      {# ── Earnings warning ── #}
      {% if s.get('next_earnings') %}
      <div class="sc-earnings-warn">
        <span class="earnings-pulse"></span>
        EARNINGS: {{ s.next_earnings }}
      </div>
      {% endif %}

      {# ── Analyst rating bar ── #}
      {% set ab = s.get('analyst_buy') %}
      {% set ah = s.get('analyst_hold') %}
      {% set as_ = s.get('analyst_sell') %}
      {% if ab is not none and ah is not none and as_ is not none %}
        {% set total = (ab + ah + as_) | int %}
        {% if total > 0 %}
        <div class="sc-analyst-section">
          <div class="sc-analyst-label">ANALYST RATINGS</div>
          <div class="sc-analyst-bar-wrap">
            <div class="sc-analyst-bar-buy"  style="flex:{{ ab }}"></div>
            <div class="sc-analyst-bar-hold" style="flex:{{ ah }}"></div>
            <div class="sc-analyst-bar-sell" style="flex:{{ as_ }}"></div>
          </div>
          <div class="sc-analyst-counts">
            <span class="sc-analyst-count-buy">BUY {{ ab }}</span>
            <span class="sc-analyst-count-hold">HOLD {{ ah }}</span>
            <span class="sc-analyst-count-sell">SELL {{ as_ }}</span>
            {% if s.get('analyst_period') %}
            <span class="sc-analyst-period">{{ s.analyst_period }}</span>
            {% endif %}
          </div>
        </div>
        {% endif %}
      {% endif %}

      {# ── 52-week range ── #}
      {% set w52h = s.get('week52_high') %}
      {% set w52l = s.get('week52_low') %}
      {% if w52h and w52l and w52h != w52l %}
        {% set pct = ((s.price - w52l) / (w52h - w52l) * 100) | round(1) %}
        {% set pct_clamp = [0, [pct, 100] | min] | max %}
        <div class="sc-52w-section">
          <div class="sc-52w-label">52W RANGE — {{ pct_clamp }}% FROM LOW</div>
          <div class="sc-52w-track">
            <div class="sc-52w-fill" style="width:{{ pct_clamp }}%"></div>
            <div class="sc-52w-thumb" style="left:{{ pct_clamp }}%"></div>
          </div>
          <div class="sc-52w-labels">
            <span>L ${{ "%.2f"|format(w52l) }}</span>
            <span>H ${{ "%.2f"|format(w52h) }}</span>
          </div>
        </div>
      {% endif %}

      {# ── P/E ratio ── #}
      {% if s.get('pe_ratio') %}
      <div class="sc-pe-row">P/E RATIO: <strong>{{ "%.1f"|format(s.pe_ratio) }}</strong></div>
      {% endif %}

      <div class="sc-badges">
        <span class="ma-badge ma5">MA5: {{ s.ma5 }}</span>
        <span class="ma-badge ma20">MA20: {{ s.ma20 }}</span>
        <span class="ma-badge ma60">MA60: {{ s.ma60 }}</span>
        <span class="rsi-badge">RSI: {{ s.rsi }}</span>
        <span class="vol-badge">VOL: {{ "%.1f"|format(s.vol_ratio) if s.vol_ratio else "—" }}×</span>
      </div>

      <div class="sc-signals">
        {% for sig in s.signals %}
        <div class="signal-item">{{ sig }}</div>
        {% endfor %}
      </div>

      {% if s.get('news') and s.news %}
      <hr class="sc-divider">
      <div class="sc-news">
        <div class="sc-news-label">LATEST NEWS</div>
        <ul class="sc-news-list">
          {% for item in s.news %}
          <li class="sc-news-item">
            {{ item.get('title') or item.get('headline') or '' }}
            {% set src = item.get('publisher') or item.get('source') or '' %}
            {% if src %}
            <span class="sc-news-publisher">{{ src }}</span>
            {% endif %}
          </li>
          {% endfor %}
        </ul>
      </div>
      {% endif %}

      {% if s.ai_view %}
      <hr class="sc-divider">
      <details class="sc-collapsible" open>
        <summary class="sc-collapsible-trigger">
          <span class="sc-ai-label">AI ANALYSIS</span>
          <span class="sc-collapsible-arrow">▼</span>
        </summary>
        <div class="sc-ai-body">{{ s.ai_view }}</div>
      </details>
      {% endif %}

      {% if s.entry %}
      <div class="sc-entry-section">
        <div class="sc-entry-label">ENTRY TIMING</div>
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
      >⎘ COPY TRADE SETUP</button>
    </div>
  {% endfor %}
  </div>
</div>

<div class="footer">⚠ GENERATED BY AI · FOR REFERENCE ONLY · NOT INVESTMENT ADVICE · TRADE AT YOUR OWN RISK</div>

</div><!-- /section-wrap -->

<script>
// Live clock update
(function() {
  function updateClock() {
    const el = document.getElementById('live-clock');
    if (!el) return;
    const now = new Date();
    const hkt = new Date(now.toLocaleString('en-US', { timeZone: 'Asia/Hong_Kong' }));
    const pad = n => String(n).padStart(2, '0');
    const dateStr = `${hkt.getFullYear()}-${pad(hkt.getMonth()+1)}-${pad(hkt.getDate())}`;
    const timeStr = `${pad(hkt.getHours())}:${pad(hkt.getMinutes())}:${pad(hkt.getSeconds())}`;
    el.innerHTML = `${dateStr} ${timeStr} <span class="tz-label">HKT</span>`;
  }
  updateClock();
  setInterval(updateClock, 1000);
})();

// Nav active state on scroll
(function() {
  const links = document.querySelectorAll('.nav-link');
  const sections = Array.from(links)
    .map(l => { const href = l.getAttribute('href'); return href && href.startsWith('#') ? document.querySelector(href) : null; })
    .filter(Boolean);
  function onScroll() {
    const scrollY = window.scrollY + 130;
    let active = null;
    sections.forEach((sec, i) => {
      if (sec && sec.offsetTop <= scrollY) active = i;
    });
    links.forEach((l, i) => l.classList.toggle('active', i === active));
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
})();

// Copy trade setup
function copyTradeSetup(btn) {
  const ticker  = btn.dataset.ticker;
  const price   = btn.dataset.price;
  const score   = btn.dataset.score;
  const entry   = btn.dataset.entry || "";

  function extractPrice(text, keywords) {
    for (const kw of keywords) {
      const re = new RegExp(kw + '[\\s：:]*[$＄]?([\\d]+\\.?[\\d]*)');
      const m = text.match(re);
      if (m) return m[1];
    }
    return null;
  }

  const entryPrice  = extractPrice(entry, ['買入', '入場', '建議買入', 'buy', 'entry']) || price;
  const stopPrice   = extractPrice(entry, ['止損', 'stop', '停損']);
  const targetPrice = extractPrice(entry, ['目標', 'target', '第一目標', '目標價']);

  let text;
  if (stopPrice || targetPrice) {
    text = `[${ticker}] ENTRY: $${entryPrice}`;
    if (stopPrice)   text += ` | STOP: $${stopPrice}`;
    if (targetPrice) text += ` | TARGET: $${targetPrice}`;
    text += ` | SIGNAL: ${score}/100`;
  } else {
    text = entry
      ? `[${ticker}] ${entry} | SIGNAL: ${score}/100`
      : `[${ticker}] PRICE: $${price} | SIGNAL: ${score}/100`;
  }

  navigator.clipboard.writeText(text).then(() => {
    const orig = btn.innerHTML;
    btn.innerHTML = "✓ COPIED";
    btn.style.background = "rgba(0,212,160,0.12)";
    btn.style.color = "var(--accent-green)";
    btn.style.borderColor = "rgba(0,212,160,0.3)";
    setTimeout(() => {
      btn.innerHTML = orig;
      btn.style.background = "";
      btn.style.color = "";
      btn.style.borderColor = "";
    }, 2000);
  }).catch(() => {
    btn.innerHTML = "✗ FAILED";
    setTimeout(() => { btn.innerHTML = "⎘ COPY TRADE SETUP"; }, 2000);
  });
}

// Filter bar
const activeFilters = { type: 'all', market: 'all' };

document.querySelectorAll('.filter-btn').forEach(btn => {
  btn.addEventListener('click', () => {
    const filterGroup = btn.dataset.filter;
    const value = btn.dataset.value;
    activeFilters[filterGroup] = value;

    document.querySelectorAll(`.filter-btn[data-filter="${filterGroup}"]`).forEach(b => b.classList.remove('active'));
    btn.classList.add('active');

    applyFilters();
  });
});

function applyFilters() {
  const cards = document.querySelectorAll('.stock-card');
  const rows = document.querySelectorAll('.lb-row[data-type]');
  let visible = 0;

  cards.forEach(card => {
    const typeMatch = activeFilters.type === 'all' || card.dataset.type === activeFilters.type;
    const marketMatch = activeFilters.market === 'all' || card.dataset.market === activeFilters.market;
    const show = typeMatch && marketMatch;
    card.style.display = show ? '' : 'none';
    if (show) visible++;
  });

  rows.forEach(row => {
    const typeMatch = activeFilters.type === 'all' || row.dataset.type === activeFilters.type;
    const marketMatch = activeFilters.market === 'all' || row.dataset.market === activeFilters.market;
    row.style.display = (typeMatch && marketMatch) ? '' : 'none';
  });

  document.getElementById('filter-count').textContent = `${visible} instruments`;
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
