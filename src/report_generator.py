import os
import re
from datetime import datetime, timedelta, timezone
from jinja2 import Template
from stock_detail import generate_stock_detail_page

DASHBOARD_HTML = """<!DOCTYPE html>
<html lang="zh-TW">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">
<title>Signal Monitor · {{ date }}</title>
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
  --flat:      #a0a3ad;
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

/* ── TOP HEADER (sticky) ───────────────────────────────────────────── */
.top {
  position: sticky;
  top: 0;
  z-index: 50;
  background: var(--surface);
  border-bottom: 1px solid var(--border);
  backdrop-filter: blur(12px);
  -webkit-backdrop-filter: blur(12px);
}
.top-row {
  display: flex; align-items: center; gap: 24px;
  padding: 0 24px; height: 60px;
}
.brand { display: flex; align-items: center; gap: 10px; }
.brand-logo {
  width: 28px; height: 28px; border-radius: 8px;
  background: linear-gradient(135deg, var(--blue), var(--purple));
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-weight: 700; font-size: 14px;
  font-family: var(--mono);
}
.brand-title { font-size: 14px; font-weight: 600; letter-spacing: -0.01em; color: var(--text); }
.brand-sub { font-family: var(--mono); font-size: 10px; color: var(--text-2); margin-top: 1px; }

.nav-pills { display: flex; gap: 4px; }
.nav-pill {
  font-size: 13px; padding: 8px 12px; border-radius: 8px;
  color: var(--text-2); text-decoration: none;
  font-weight: 500;
  display: flex; align-items: center; gap: 6px;
  border: 1px solid transparent;
}
.nav-pill:hover { color: var(--text); background: var(--elevated); }
.nav-pill.active {
  color: var(--text); background: var(--elevated);
  border-color: var(--border); font-weight: 600;
}
.nav-badge {
  font-size: 10px; padding: 1px 6px; border-radius: 10px;
  background: var(--blue); color: var(--bg);
  font-weight: 700; font-family: var(--mono);
}
.spacer { flex: 1; }
.searchbox {
  display: flex; align-items: center; gap: 8px;
  background: var(--bg); border: 1px solid var(--border);
  border-radius: 8px; padding: 7px 12px; width: 260px;
  color: var(--muted); font-size: 13px;
}
.searchbox .kbd {
  margin-left: auto; font-family: var(--mono); font-size: 10px;
  color: var(--text-2); padding: 1px 5px;
  border: 1px solid var(--border); border-radius: 4px;
}
.market-open {
  display: flex; align-items: center; gap: 6px;
  padding: 6px 10px; border-radius: 8px; font-size: 12px; font-weight: 600;
  background: rgba(52,211,153,0.10); color: var(--up);
  border: 1px solid rgba(52,211,153,0.25);
  transition: background 0.3s, color 0.3s, border-color 0.3s;
}
.market-open .dot { width: 6px; height: 6px; border-radius: 3px; background: var(--up); animation: pulse 2s infinite; }
.market-open.closed { background: rgba(148,163,184,0.08); color: var(--muted); border-color: rgba(148,163,184,0.2); }
.market-open.closed .dot { background: var(--muted); animation: none; }
@keyframes pulse { 0%,100%{opacity:1} 50%{opacity:0.4} }

/* market strip */
.market-strip {
  display: flex; gap: 28px; padding: 12px 24px; overflow-x: auto;
  border-top: 1px solid var(--border); scrollbar-width: none;
}
.market-strip::-webkit-scrollbar { display: none; }
.market-item { display: flex; flex-direction: column; gap: 2px; min-width: 86px; flex-shrink: 0; }
.market-name { font-size: 11px; color: var(--text-2); }
.market-line { display: flex; align-items: baseline; gap: 6px; }
.market-price { font-family: var(--mono); font-size: 14px; font-weight: 600; color: var(--text); }
.pct { font-family: var(--mono); font-size: 11px; font-weight: 600; }
.pct.up { color: var(--up); }
.pct.down { color: var(--down); }

/* filter bar */
.filter-bar {
  display: flex; align-items: center; gap: 8px;
  padding: 10px 24px; border-top: 1px solid var(--border);
  flex-wrap: wrap;
}
.filter-label { font-size: 11px; color: var(--text-2); font-weight: 500; margin-right: 4px; }
.filter-btn {
  font-size: 12px; padding: 5px 11px; border-radius: 6px;
  color: var(--text-2); background: transparent;
  border: 1px solid var(--border); cursor: pointer;
  font-family: inherit; font-weight: 500;
}
.filter-btn:hover { color: var(--text); border-color: var(--border-hi); }
.filter-btn.active {
  color: var(--text); background: var(--elevated);
  border-color: var(--border-hi); font-weight: 600;
}
.filter-meta { margin-left: auto; font-family: var(--mono); font-size: 11px; color: var(--text-2); }
.filter-sep { width: 1px; height: 18px; background: var(--border); margin: 0 4px; }

/* ── SPY period tabs ────────────────────────────────────────────────── */
.period-tabs { display: flex; gap: 3px; }
.period-tab {
  font-family: var(--mono); font-size: 10px; font-weight: 600;
  padding: 3px 8px; border-radius: 5px; border: 1px solid transparent;
  color: var(--text-2); background: none; cursor: pointer;
}
.period-tab:hover { color: var(--text); background: var(--elevated); }
.period-tab.active { color: var(--blue); background: rgba(122,162,255,0.10); border-color: rgba(122,162,255,0.25); }

/* ── Mobile bottom nav ──────────────────────────────────────────────── */
.mob-nav {
  display: none;
  position: fixed; bottom: 0; left: 0; right: 0; z-index: 100;
  background: var(--surface); border-top: 1px solid var(--border);
  backdrop-filter: blur(16px); -webkit-backdrop-filter: blur(16px);
  padding: 6px 0 env(safe-area-inset-bottom, 8px);
}
.mob-nav-items { display: flex; justify-content: space-around; }
.mob-nav-item {
  display: flex; flex-direction: column; align-items: center; gap: 3px;
  padding: 4px 10px; border-radius: 8px; text-decoration: none;
  color: var(--text-2); font-size: 10px; font-weight: 500; min-width: 52px;
}
.mob-nav-item:hover, .mob-nav-item.active { color: var(--blue); }
.mob-nav-item svg { width: 20px; height: 20px; }
@media (max-width: 768px) {
  .mob-nav { display: block; }
  .page { padding-bottom: 80px !important; }
}

/* ── PAGE GRID ──────────────────────────────────────────────────────── */
.page {
  max-width: 1480px; margin: 0 auto;
  padding: 18px 24px 48px;
  display: flex; flex-direction: column; gap: 16px;
}

/* ── CARDS ──────────────────────────────────────────────────────────── */
.card {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 12px;
  padding: 18px 20px;
}
.card-pad-0 { padding: 0; overflow: hidden; }
.card-head {
  display: flex; align-items: center; justify-content: space-between;
  gap: 10px; padding: 16px 20px; border-bottom: 1px solid var(--border);
}
.card-title { font-size: 14px; font-weight: 600; color: var(--text); letter-spacing: -0.005em; }
.card-sub { font-size: 11px; color: var(--text-2); }

/* ── KPI strip ──────────────────────────────────────────────────────── */
.kpi-strip { display: grid; grid-template-columns: repeat(5, 1fr); gap: 12px; }
@media (max-width: 1100px) { .kpi-strip { grid-template-columns: repeat(3, 1fr); } }
@media (max-width: 640px)  { .kpi-strip { grid-template-columns: repeat(2, 1fr); } }
.kpi { background: var(--surface); border: 1px solid var(--border); border-radius: 12px; padding: 16px; }
.kpi-head { display: flex; align-items: center; justify-content: space-between; }
.kpi-label { font-size: 12px; color: var(--text-2); font-weight: 500; }
.kpi-val { font-size: 26px; font-weight: 700; letter-spacing: -0.02em; margin-top: 8px; }
.kpi-sub { font-family: var(--mono); font-size: 11px; color: var(--text-2); margin-top: 2px; }
.badge {
  font-size: 9px; padding: 2px 7px; border-radius: 10px;
  font-weight: 700; letter-spacing: 0.04em;
}
.badge.up    { background: rgba(52,211,153,0.12); color: var(--up); }
.badge.down  { background: rgba(248,113,113,0.12); color: var(--down); }
.badge.amber { background: rgba(245,185,66,0.12); color: var(--amber); }
.badge.blue  { background: rgba(122,162,255,0.12); color: var(--blue); }

/* ── AI Brief ───────────────────────────────────────────────────────── */
.brief-head { display: flex; align-items: center; gap: 10px; margin-bottom: 4px; }
.brief-icon {
  width: 24px; height: 24px; border-radius: 7px;
  background: linear-gradient(135deg, var(--blue), var(--purple));
  display: flex; align-items: center; justify-content: center;
  color: #fff; font-size: 13px;
}
.brief-title { font-size: 13px; font-weight: 600; }
.brief-meta { font-family: var(--mono); font-size: 10px; color: var(--text-2); }
.brief-grid {
  display: grid; grid-template-columns: 1fr 1fr; gap: 0;
  margin-top: 6px;
}
@media (max-width: 900px) { .brief-grid { grid-template-columns: 1fr; } }
.brief-section {
  display: flex; gap: 10px;
  padding: 14px 0;
  border-top: 1px solid var(--border);
}
.brief-grid > .brief-section:nth-child(odd)  { padding-right: 18px; }
.brief-grid > .brief-section:nth-child(even) { padding-left: 18px; border-left: 1px solid var(--border); }
@media (max-width: 900px) {
  .brief-grid > .brief-section { padding-left: 0; padding-right: 0; border-left: none; }
}
.brief-letter {
  width: 22px; height: 22px; border-radius: 6px; flex-shrink: 0;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--mono); font-size: 11px; font-weight: 800;
  color: var(--bg); margin-top: 1px;
}
.brief-letter.b1 { background: var(--blue); }
.brief-letter.b2 { background: var(--amber); }
.brief-letter.b3 { background: var(--up); }
.brief-letter.b4 { background: var(--purple); }
.brief-body { flex: 1; }
.brief-label {
  font-size: 11px; font-weight: 600; color: var(--text-2);
  letter-spacing: 0.04em; text-transform: uppercase;
}
.brief-text {
  font-size: 12px; line-height: 1.6; color: var(--text);
  margin-top: 4px; white-space: pre-wrap; text-wrap: pretty;
}

/* ── Sector heatmap ─────────────────────────────────────────────────── */
.sector-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(180px, 1fr));
  gap: 10px; margin-top: 12px;
}
.sector-tile {
  border: 1px solid var(--border); border-radius: 10px;
  padding: 14px 16px; position: relative; overflow: hidden;
}
.sector-tile.high { background: rgba(52,211,153,0.08); border-color: rgba(52,211,153,0.25); }
.sector-tile.mid  { background: rgba(245,185,66,0.08); border-color: rgba(245,185,66,0.25); }
.sector-tile.low  { background: rgba(248,113,113,0.08); border-color: rgba(248,113,113,0.25); }
.sector-name {
  font-family: var(--mono); font-size: 10px; font-weight: 700;
  color: var(--text-2); letter-spacing: 0.06em;
  text-transform: uppercase;
}
.sector-avg { font-family: var(--mono); font-size: 28px; font-weight: 700; letter-spacing: -0.02em; margin-top: 6px; }
.sector-avg.high { color: var(--up); }
.sector-avg.mid  { color: var(--amber); }
.sector-avg.low  { color: var(--down); }
.sector-tickers { display: flex; flex-wrap: wrap; gap: 4px; margin-top: 10px; }
.sector-chip {
  font-family: var(--mono); font-size: 10px; font-weight: 600;
  padding: 2px 7px; border-radius: 4px;
}
.sector-chip.high { background: rgba(52,211,153,0.12); color: var(--up); }
.sector-chip.mid  { background: rgba(245,185,66,0.12); color: var(--amber); }
.sector-chip.low  { background: rgba(248,113,113,0.12); color: var(--down); }

/* ── Watchlist table ────────────────────────────────────────────────── */
.wl-wrap { overflow-x: auto; }
.wl {
  width: 100%; border-collapse: collapse;
}
.wl thead tr { background: var(--bg); }
.wl th {
  padding: 10px 14px;
  font-size: 11px; font-weight: 500; color: var(--text-2);
  text-align: right; border-bottom: 1px solid var(--border);
  white-space: nowrap;
}
.wl th.first { text-align: left; }
.wl th.center { text-align: center; }
.wl td {
  padding: 12px 14px;
  border-bottom: 1px solid var(--border);
  vertical-align: middle;
}
.wl tbody tr:last-child td { border-bottom: none; }
.wl tbody tr:hover td { background: rgba(255,255,255,0.02); }

.ticker-cell { display: flex; align-items: center; gap: 10px; }
.ticker-tile {
  width: 32px; height: 32px; border-radius: 8px;
  background: var(--bg); border: 1px solid var(--border);
  display: flex; align-items: center; justify-content: center;
  font-family: var(--mono); font-size: 10px; font-weight: 700; color: var(--text);
  flex-shrink: 0;
}
.ticker-meta { min-width: 0; }
.ticker-sym { font-family: var(--mono); font-size: 12px; font-weight: 600; color: var(--text); }
.ticker-name { font-size: 11px; color: var(--text-2); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; max-width: 180px; }
.num { font-family: var(--mono); font-size: 12px; color: var(--text); text-align: right; }
.num.lg { font-size: 13px; font-weight: 600; }
.pct-chip {
  font-family: var(--mono); font-size: 12px; font-weight: 600;
  padding: 3px 8px; border-radius: 5px; display: inline-block;
}
.pct-chip.up   { color: var(--up);   background: rgba(52,211,153,0.10); border: 1px solid rgba(52,211,153,0.18); }
.pct-chip.down { color: var(--down); background: rgba(248,113,113,0.10); border: 1px solid rgba(248,113,113,0.18); }
.strength-badge {
  font-size: 10px; padding: 3px 8px; border-radius: 10px;
  font-weight: 600; letter-spacing: 0.02em; white-space: nowrap;
  display: inline-block;
}
.strength-badge.high { color: var(--up);    background: rgba(52,211,153,0.10); border: 1px solid rgba(52,211,153,0.25); }
.strength-badge.mid  { color: var(--amber); background: rgba(245,185,66,0.12); border: 1px solid rgba(245,185,66,0.25); }
.strength-badge.low  { color: var(--down);  background: rgba(248,113,113,0.10); border: 1px solid rgba(248,113,113,0.25); }
.ring-cell { display: flex; align-items: center; justify-content: center; }

/* ── Alert timeline ─────────────────────────────────────────────────── */
.timeline { position: relative; padding-left: 26px; margin-top: 4px; }
.timeline::before {
  content: ''; position: absolute; left: 7px; top: 8px; bottom: 8px;
  width: 1px; background: linear-gradient(180deg, var(--blue), var(--border), transparent);
}
.timeline-row {
  display: flex; align-items: center; gap: 12px; padding: 10px 0; position: relative;
}
.timeline-dot {
  position: absolute; left: -23px; top: 14px;
  width: 9px; height: 9px; border-radius: 50%;
  border: 1px solid var(--bg);
}
.timeline-dot.high   { background: var(--up);    box-shadow: 0 0 6px rgba(52,211,153,0.5); }
.timeline-dot.mid    { background: var(--amber); box-shadow: 0 0 6px rgba(245,185,66,0.4); }
.timeline-dot.low    { background: var(--down);  box-shadow: 0 0 6px rgba(248,113,113,0.4); }
.timeline-date { font-family: var(--mono); font-size: 11px; color: var(--text-2); min-width: 92px; }
.timeline-ticker {
  font-family: var(--mono); font-size: 11px; font-weight: 700; color: var(--text);
  background: var(--elevated); border: 1px solid var(--border-hi);
  padding: 2px 8px; border-radius: 4px;
}
.empty-state {
  font-size: 12px; color: var(--text-2); font-family: var(--mono);
  padding: 12px 0;
}

/* ── Stock cards bento ──────────────────────────────────────────────── */
.bento {
  display: grid; grid-template-columns: repeat(2, 1fr); gap: 14px;
  margin-top: 12px;
}
@media (max-width: 1000px) { .bento { grid-template-columns: 1fr; } }
.scard {
  background: var(--surface);
  border: 1px solid var(--border);
  border-radius: 14px;
  padding: 18px 20px;
  display: flex; flex-direction: column; gap: 12px;
}
.scard.high {
  border-color: rgba(52,211,153,0.35);
  box-shadow: inset 0 0 0 1px rgba(52,211,153,0.10);
}
.scard-head { display: flex; align-items: flex-start; justify-content: space-between; gap: 14px; }
.scard-id { display: flex; align-items: center; gap: 12px; }
.scard-tile {
  width: 44px; height: 44px; border-radius: 11px;
  background: var(--bg); border: 1px solid var(--border);
  display: flex; align-items: center; justify-content: center;
  font-family: var(--mono); font-size: 12px; font-weight: 700; color: var(--text);
}
.scard-sym { font-family: var(--mono); font-size: 20px; font-weight: 700; color: var(--text); letter-spacing: -0.01em; line-height: 1; }
.scard-name { font-size: 11px; color: var(--text-2); margin-top: 4px; }
.scard-tags { display: flex; gap: 5px; margin-top: 6px; }
.tag {
  font-family: var(--mono); font-size: 9px; font-weight: 700;
  padding: 2px 7px; border-radius: 4px;
  letter-spacing: 0.04em; text-transform: uppercase;
}
.tag.stock { background: rgba(122,162,255,0.12); color: var(--blue); border: 1px solid rgba(122,162,255,0.25); }
.tag.etf   { background: rgba(177,140,255,0.12); color: var(--purple); border: 1px solid rgba(177,140,255,0.25); }
.tag.market { background: rgba(255,255,255,0.04); color: var(--text-2); border: 1px solid var(--border); }
.scard-price { text-align: right; display: flex; align-items: center; gap: 12px; }
.price-block { text-align: right; }
.price-val { font-family: var(--mono); font-size: 22px; font-weight: 700; letter-spacing: -0.02em; color: var(--text); line-height: 1; }
.price-chg { font-family: var(--mono); font-size: 12px; font-weight: 600; margin-top: 4px; }
.price-chg.up { color: var(--up); }
.price-chg.down { color: var(--down); }

.ring {
  width: 56px; height: 56px; position: relative; flex-shrink: 0;
}
.ring svg { transform: rotate(-90deg); display: block; }
.ring-num {
  position: absolute; inset: 0;
  display: flex; align-items: center; justify-content: center;
  font-family: var(--mono); font-size: 14px; font-weight: 700;
}
.ring.high .ring-num { color: var(--up); }
.ring.mid  .ring-num { color: var(--amber); }
.ring.low  .ring-num { color: var(--down); }

.scard-row { display: flex; flex-wrap: wrap; gap: 6px; align-items: center; }

.ma-badge {
  font-family: var(--mono); font-size: 10px; font-weight: 600;
  padding: 3px 8px; border-radius: 5px;
}
.ma-badge.ma5  { background: rgba(245,185,66,0.10); color: var(--amber); border: 1px solid rgba(245,185,66,0.20); }
.ma-badge.ma20 { background: rgba(122,162,255,0.10); color: var(--blue); border: 1px solid rgba(122,162,255,0.20); }
.ma-badge.ma60 { background: rgba(177,140,255,0.10); color: var(--purple); border: 1px solid rgba(177,140,255,0.20); }
.rsi-badge { background: rgba(248,113,113,0.08); color: var(--down); border: 1px solid rgba(248,113,113,0.18); font-family: var(--mono); font-size: 10px; font-weight: 600; padding: 3px 8px; border-radius: 5px; }
.vol-badge { background: rgba(52,211,153,0.08); color: var(--up); border: 1px solid rgba(52,211,153,0.20); font-family: var(--mono); font-size: 10px; font-weight: 600; padding: 3px 8px; border-radius: 5px; }

.scard-sub {
  font-family: var(--mono); font-size: 10px; font-weight: 600;
  color: var(--text-2); text-transform: uppercase; letter-spacing: 0.06em;
  margin-bottom: 6px;
}
.signals { display: flex; flex-direction: column; gap: 4px; }
.signal-item { font-size: 12px; color: var(--text); line-height: 1.55; padding: 2px 0; text-wrap: pretty; }
.signal-item::before { content: '›'; color: var(--blue); margin-right: 6px; font-weight: 700; }

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

.analyst-bar { display: flex; height: 7px; border-radius: 4px; overflow: hidden; gap: 1px; background: var(--elevated); }
.analyst-buy { background: var(--up); }
.analyst-hold { background: var(--amber); opacity: 0.85; }
.analyst-sell { background: var(--down); }
.analyst-counts { display: flex; gap: 12px; margin-top: 5px; font-family: var(--mono); font-size: 10px; font-weight: 600; }
.analyst-counts .buy  { color: var(--up); }
.analyst-counts .hold { color: var(--amber); }
.analyst-counts .sell { color: var(--down); }
.analyst-counts .period { margin-left: auto; color: var(--text-2); }

.earnings {
  display: flex; align-items: center; gap: 8px;
  padding: 7px 12px; border-radius: 7px;
  background: rgba(245,185,66,0.08); border: 1px solid rgba(245,185,66,0.30);
  font-family: var(--mono); font-size: 11px; font-weight: 600; color: var(--amber);
}
.earnings .pulse {
  width: 6px; height: 6px; border-radius: 50%; background: var(--amber);
  animation: pulse 1.6s ease-in-out infinite;
}
@keyframes pulse {
  0%, 100% { box-shadow: 0 0 0 0 rgba(245,185,66,0.5); }
  50%      { box-shadow: 0 0 0 5px rgba(245,185,66,0); }
}

.sentiment {
  display: inline-flex; align-items: center; justify-content: center;
  width: 34px; height: 34px; border-radius: 50%;
  font-family: var(--mono); font-size: 11px; font-weight: 700;
}
.sentiment.pos { background: rgba(52,211,153,0.12); color: var(--up); border: 1px solid rgba(52,211,153,0.30); }
.sentiment.neg { background: rgba(248,113,113,0.12); color: var(--down); border: 1px solid rgba(248,113,113,0.30); }
.sentiment.neut { background: rgba(255,255,255,0.04); color: var(--text-2); border: 1px solid var(--border); }

.news-list { display: flex; flex-direction: column; gap: 6px; }
.news-item {
  font-size: 11.5px; color: var(--text); line-height: 1.5;
  padding: 8px 10px; background: var(--bg); border-radius: 6px;
  border-left: 2px solid var(--border-hi);
}
.news-pub {
  display: inline-block; font-family: var(--mono); font-size: 9.5px;
  color: var(--text-2); background: var(--surface);
  padding: 1px 6px; border-radius: 3px; margin-top: 4px;
}

.ai-details {
  border-top: 1px solid var(--border); padding-top: 12px;
}
.ai-details summary {
  display: flex; align-items: center; justify-content: space-between;
  cursor: pointer; list-style: none; padding: 4px 0;
}
.ai-details summary::-webkit-details-marker { display: none; }
.ai-label {
  font-family: var(--mono); font-size: 10px; font-weight: 700;
  color: var(--blue); text-transform: uppercase; letter-spacing: 0.08em;
}
.ai-arrow { color: var(--text-2); font-size: 10px; transition: transform 0.2s; }
.ai-details[open] .ai-arrow { transform: rotate(180deg); }
.ai-body { font-size: 12px; color: var(--text); line-height: 1.65; padding-top: 8px; }

.entry {
  padding: 10px 12px; background: rgba(52,211,153,0.06);
  border: 1px solid rgba(52,211,153,0.25); border-radius: 8px;
}
.entry-label {
  font-family: var(--mono); font-size: 10px; font-weight: 700;
  color: var(--up); text-transform: uppercase; letter-spacing: 0.08em;
  margin-bottom: 5px;
}
.entry-body { font-size: 12px; color: var(--text); line-height: 1.65; white-space: pre-wrap; }

.copy-btn {
  font-family: var(--mono); font-size: 11px; font-weight: 600;
  letter-spacing: 0.04em; text-transform: uppercase;
  width: 100%; padding: 9px 0; border-radius: 8px;
  background: rgba(122,162,255,0.08); color: var(--blue);
  border: 1px solid rgba(122,162,255,0.25); cursor: pointer;
}
.copy-btn:hover { background: rgba(122,162,255,0.14); border-color: rgba(122,162,255,0.4); }

/* ── Footer ─────────────────────────────────────────────────────────── */
.footer {
  text-align: center; padding: 24px;
  color: var(--muted); font-family: var(--mono);
  font-size: 10px; letter-spacing: 0.06em;
}

/* Responsive header */
@media (max-width: 900px) {
  .top-row { gap: 14px; padding: 0 14px; }
  .nav-pills { display: none; }
  .searchbox { display: none; }
}

/* ── Page 2-col grid ────────────────────────────────────────────────── */
.page-grid {
  display: grid;
  grid-template-columns: 1fr 380px;
  gap: 16px;
  align-items: start;
}
.page-left  { display: flex; flex-direction: column; gap: 16px; }
.page-right { display: flex; flex-direction: column; gap: 16px; position: sticky; top: 72px; }
.mid-row    { display: grid; grid-template-columns: 1.5fr 1fr 1fr; gap: 12px; }
@media (max-width: 1280px) {
  .page-grid { grid-template-columns: 1fr; }
  .page-right { position: static; }
}
@media (max-width: 900px)  { .mid-row { grid-template-columns: 1fr 1fr; } }
@media (max-width: 600px)  { .mid-row { grid-template-columns: 1fr; } }

/* ── Signal histogram ───────────────────────────────────────────────── */
.hist-bar   { display: flex; align-items: flex-end; gap: 8px; height: 100px; }
.hist-col   { flex: 1; display: flex; flex-direction: column; align-items: center; gap: 4px; }
.hist-num   { font-family: var(--mono); font-size: 12px; font-weight: 600; color: var(--text); }
.hist-rect  { width: 100%; border-radius: 5px 5px 2px 2px; }
.hist-label { font-family: var(--mono); font-size: 9px; color: var(--text-2); text-align: center; }

/* ── Sector rotation compact ────────────────────────────────────────── */
.sr-grid { display: grid; grid-template-columns: repeat(3, 1fr); gap: 4px; margin-top: 10px; }
.sr-cell { padding: 7px 8px; border-radius: 6px; }
.sr-tick { font-family: var(--mono); font-size: 10px; font-weight: 600; color: var(--text); }
.sr-val  { font-family: var(--mono); font-size: 10px; font-weight: 600; }

/* ── Headlines feed ─────────────────────────────────────────────────── */
.hl-list  { display: flex; flex-direction: column; }
.hl-item  { padding: 10px 0; border-bottom: 1px solid var(--border); }
.hl-item:last-child { border-bottom: none; }
.hl-meta  { display: flex; align-items: center; gap: 8px; font-family: var(--mono); font-size: 11px; margin-bottom: 5px; }
.hl-ticker { color: var(--blue); font-weight: 700; padding: 2px 6px; background: rgba(122,162,255,0.10); border-radius: 4px; }
.hl-src   { color: var(--text-2); }
.hl-title { font-size: 12px; color: var(--text); line-height: 1.45; }

/* ── Mobile ≤ 768px ─────────────────────────────────────────────────── */
@media (max-width: 768px) {
  .top-row { height: 52px; padding: 0 14px; }
  .market-strip { padding: 8px 14px; gap: 14px; }
  .filter-bar { padding: 8px 14px; gap: 5px; }
  .filter-meta { display: none; }
  #update-stamp, #auto-refresh-countdown { display: inline !important; font-size: 10px; }
  .page { padding: 12px 12px 40px; }
  .kpi-val { font-size: 20px; }
  .mob-hide { display: none !important; }
  .ticker-name { max-width: 110px; }
  .wl th, .wl td { padding: 10px 8px; }
  .brief-text { font-size: 11px; }
  .scard-sym { font-size: 16px; }
  .card { padding: 14px 14px; }
  .bento { grid-template-columns: 1fr; }
  .sector-grid { grid-template-columns: repeat(2, 1fr); }
  .hist-bar { height: 80px; }
}
@media (max-width: 480px) {
  .kpi-strip { grid-template-columns: repeat(2, 1fr); }
  .mid-row { grid-template-columns: 1fr; }
  .market-item { min-width: 72px; }
  .market-price { font-size: 12px; }
  .kpi-val { font-size: 18px; }
  .filter-btn { font-size: 11px; padding: 4px 8px; }
}

/* ── EXPERT / BEGINNER TOGGLE ──────────────────────────────────────── */
.beginner-only { display: none; }
body.beginner-mode .expert-only  { display: none !important; }
body.beginner-mode .beginner-only { display: block; }

.beg-verdict {
  padding: 10px 14px; border-radius: 8px;
  font-size: 13px; font-weight: 600; line-height: 1.4;
}
.beg-verdict.high { background: rgba(52,211,153,0.10); color: var(--up);   border: 1px solid rgba(52,211,153,0.22); }
.beg-verdict.mid  { background: rgba(245,185,66,0.10); color: var(--amber); border: 1px solid rgba(245,185,66,0.22); }
.beg-verdict.low  { background: rgba(248,113,113,0.10); color: var(--down); border: 1px solid rgba(248,113,113,0.22); }
.beg-explain {
  font-size: 11px; color: var(--text-2); margin-top: 6px; line-height: 1.55;
  padding: 0 2px;
}

/* ── REFRESH BUTTON ────────────────────────────────────────────────── */
.refresh-btn {
  display: inline-flex; align-items: center; gap: 5px;
  font-size: 12px; padding: 5px 11px; border-radius: 6px;
  color: var(--text-2); background: transparent;
  border: 1px solid var(--border); cursor: pointer;
  font-family: inherit; font-weight: 500; transition: color .15s, border-color .15s;
}
.refresh-btn:hover { color: var(--blue); border-color: rgba(122,162,255,0.4); }
.refresh-btn.spinning { opacity: 0.6; pointer-events: none; }
.spin-icon { display: inline-block; font-style: normal; }
.refresh-btn.spinning .spin-icon { animation: spin360 0.7s linear infinite; }
@keyframes spin360 { to { transform: rotate(360deg); } }
</style>
</head>
<body>

<!-- ─── TOP HEADER ─────────────────────────────────────────────────── -->
<header class="top">
  <div class="top-row">
    <div class="brand">
      <div class="brand-logo">S</div>
      <div>
        <div class="brand-title">Signal Monitor</div>
        <div class="brand-sub" id="live-clock">{{ date }} · HKT</div>
      </div>
    </div>

    <nav class="nav-pills">
      <a class="nav-pill active" href="#overview">Overview</a>
      <a class="nav-pill" href="#brief">AI Brief</a>
      <a class="nav-pill" href="#sectors">Sectors</a>
      <a class="nav-pill" href="#watchlist">Watchlist</a>
      <a class="nav-pill" href="#alerts">Alerts{% if alert_history %} <span class="nav-badge">{{ alert_history|length }}</span>{% endif %}</a>
      <a class="nav-pill" href="#stocks">Stocks</a>
      <a class="nav-pill" href="./backtest.html">Backtest</a>
      <a class="nav-pill" href="./paper_trading.html">📋 Paper Trade</a>
      <a class="nav-pill" href="./pattern_backtest.html">🔬 Patterns</a>
      <a class="nav-pill" href="./portfolio.html">💼 Portfolio</a>
      <a class="nav-pill" href="#hkbrief">🇭🇰 港股</a>
    </nav>

    <div class="spacer"></div>

    <div class="searchbox" style="padding:0 12px;cursor:text">
      <span style="font-size:13px;color:var(--muted)">⌕</span>
      <input id="ticker-search" type="text" placeholder="Search ticker…"
        style="flex:1;background:none;border:none;outline:none;color:var(--text);font-family:var(--sans);font-size:13px;padding:7px 0">
      <span class="kbd" id="search-hint">/</span>
    </div>

    <div class="market-open closed" id="market-status">
      <span class="dot"></span>
      <span id="market-label">Checking…</span>
    </div>
  </div>

  <!-- Market strip -->
  <div class="market-strip">
    {% for ticker, m in market.items() %}
    <div class="market-item">
      <span class="market-name">{{ m.name }}</span>
      <div class="market-line">
        <span class="market-price">{{ "{:,.2f}".format(m.price) if m.price >= 1000 else "%.2f"|format(m.price) }}</span>
        <span class="pct {{ m.direction }}">{{ "%+.2f"|format(m.change_pct) }}%</span>
      </div>
    </div>
    {% endfor %}
  </div>

  <!-- Filter bar -->
  <div class="filter-bar">
    <button class="filter-btn active" data-filter="type" data-value="all">All · {{ stocks_sorted|length }}</button>
    <button class="filter-btn" data-filter="type" data-value="stock">Stocks</button>
    <button class="filter-btn" data-filter="type" data-value="etf">ETFs</button>
    <button class="filter-btn" data-filter="score" data-value="70">Signal ≥70</button>
    <button class="filter-btn" data-filter="special" data-value="breakout" class="mob-hide">Breakouts</button>
    <button class="filter-btn mob-hide" data-filter="special" data-value="rsi5070">RSI 50–70</button>
    <button class="filter-btn mob-hide" data-filter="special" data-value="newhigh">New highs</button>
    <span class="filter-sep mob-hide"></span>
    <button class="filter-btn mob-hide" id="sort-btn" data-sort="desc" title="Sort by signal">Signal ↓</button>
    <button class="filter-btn mob-hide" id="view-btn" data-view="cards" title="Toggle view">⊞ Cards</button>
    <span class="filter-sep mob-hide"></span>
    <button class="filter-btn mob-hide" id="mode-toggle" onclick="toggleMode()" title="Switch between Expert and Simple view">📖 Simple</button>
    <button class="refresh-btn" id="refresh-btn" onclick="doRefresh(this)" title="Reload page to get latest prices"><span class="spin-icon">↻</span> Refresh</button>
    <span class="filter-meta" id="filter-count">{{ stocks_sorted|length }} instruments</span>
    <span class="filter-meta" id="update-stamp" style="color:var(--muted)">Updated {{ generated_at }}</span>
    <span class="filter-meta" id="auto-refresh-countdown" style="color:var(--muted);font-size:10px"></span>
  </div>
</header>

<div class="page">

{% set strong_n = (stocks_sorted | selectattr('score', '>=', 70) | list | length) %}
{% set mid_n    = (stocks_sorted | selectattr('score', '>=', 50) | list | length) - strong_n %}
{% set avg_score = (stocks_sorted | sum(attribute='score') / (stocks_sorted|length or 1)) | round(1) %}
{% set up_n = (stocks_sorted | selectattr('price_change_pct', '>=', 0) | list | length) %}
{% set down_n = stocks_sorted|length - up_n %}
{% set bias_class = 'up' if up_n > down_n else ('down' if down_n > up_n else 'amber') %}
{% set bias_label = 'Risk On' if up_n > down_n else ('Risk Off' if down_n > up_n else 'Neutral') %}

<div class="page-grid">

  <!-- ─── LEFT COLUMN ───────────────────────────────────────────── -->
  <div class="page-left">

    <!-- KPI strip -->
    <section id="overview" class="kpi-strip">
      <div class="kpi">
        <div class="kpi-head">
          <span class="kpi-label">Market bias</span>
          <span class="badge {{ bias_class }}">{{ 'BULLISH' if up_n > down_n else ('BEARISH' if down_n > up_n else 'MIXED') }}</span>
        </div>
        <div class="kpi-val" style="color: var(--{{ bias_class }})">{{ bias_label }}</div>
        <div class="kpi-sub">{{ up_n }} up · {{ down_n }} down</div>
      </div>
      <div class="kpi">
        <div class="kpi-head">
          <span class="kpi-label">Strong signals</span>
          <span class="badge blue">≥ 70</span>
        </div>
        <div class="kpi-val">{{ strong_n }} / {{ stocks_sorted|length }}</div>
        <div class="kpi-sub">mid-band (50-69): {{ mid_n }}</div>
      </div>
      <div class="kpi">
        <div class="kpi-head">
          <span class="kpi-label">Avg signal</span>
        </div>
        <div class="kpi-val">{{ avg_score }}</div>
        <div class="kpi-sub">across {{ stocks_sorted|length }} names</div>
      </div>
      <div class="kpi">
        <div class="kpi-head">
          <span class="kpi-label">Fear &amp; Greed</span>
          {% if fg_value is not none %}
            {% if fg_value >= 75 %}
              <span class="badge up">GREED</span>
            {% elif fg_value >= 55 %}
              <span class="badge amber">NEUTRAL+</span>
            {% elif fg_value >= 45 %}
              <span class="badge blue">NEUTRAL</span>
            {% elif fg_value >= 25 %}
              <span class="badge down">FEAR</span>
            {% else %}
              <span class="badge down">EXT FEAR</span>
            {% endif %}
          {% endif %}
        </div>
        <div class="kpi-val" style="{% if fg_value is not none %}color:{% if fg_value >= 60 %}var(--up){% elif fg_value >= 40 %}var(--amber){% else %}var(--down){% endif %}{% endif %}">{{ fg_value if fg_value is not none else '—' }}</div>
        <div class="kpi-sub">{{ fg_label if fg_label else 'CNN index · /100' }}</div>
      </div>
      <div class="kpi">
        <div class="kpi-head">
          <span class="kpi-label">F&amp;G change</span>
          {% if fg_delta is not none %}
            <span class="badge {{ 'up' if fg_delta >= 0 else 'down' }}">{{ '+' if fg_delta >= 0 else '' }}{{ fg_delta }}</span>
          {% endif %}
        </div>
        <div class="kpi-val" style="{% if fg_delta is not none %}color:{% if fg_delta >= 0 %}var(--up){% else %}var(--down){% endif %}{% endif %}">{{ ('+' if fg_delta and fg_delta >= 0 else '') + (fg_delta|string) if fg_delta is not none else '—' }}</div>
        <div class="kpi-sub">vs. past week</div>
      </div>
    </section>

    <!-- Mid-row: SPY chart + Signal distribution + Sector rotation -->
    <div class="mid-row">

      <!-- SPY chart -->
      <div class="card">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px;gap:8px;flex-wrap:wrap">
          <div style="display:flex;align-items:baseline;gap:10px">
            <span style="font-size:13px;color:var(--text);font-weight:600">SPY</span>
            <span style="font-size:11px;color:var(--text-2)">S&amp;P 500 ETF</span>
            {% if market.get('SPY') %}
            <span style="font-family:var(--mono);font-size:16px;font-weight:600;color:var(--text)">{{ "%.2f"|format(market['SPY'].price) }}</span>
            <span style="font-family:var(--mono);font-size:12px;font-weight:600;color:var(--{{ market['SPY'].direction }})">{{ "%+.2f"|format(market['SPY'].change_pct) }}%</span>
            {% endif %}
          </div>
          <div class="period-tabs">
            <button class="period-tab" data-period="1d">1D</button>
            <button class="period-tab active" data-period="1m">1M</button>
            <button class="period-tab" data-period="3m">3M</button>
            <button class="period-tab" data-period="6m">6M</button>
          </div>
        </div>
        <div id="spy-chart-1d" style="display:none">{{ spy_chart_1d | safe }}</div>
        <div id="spy-chart-1m">{{ spy_chart_1m | safe }}</div>
        <div id="spy-chart-3m" style="display:none">{{ spy_chart_3m | safe }}</div>
        <div id="spy-chart-6m" style="display:none">{{ spy_chart_6m | safe }}</div>
      </div>

      <!-- Signal distribution histogram -->
      <div class="card">
        <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:16px">
          <span style="font-size:13px;color:var(--text);font-weight:600">Signal dist.</span>
          <span style="font-size:11px;color:var(--text-2)">avg <b style="color:var(--text)">{{ avg_score }}</b></span>
        </div>
        <div class="hist-bar">
          {% for b in sig_buckets %}
          <div class="hist-col">
            <span class="hist-num">{{ b.n }}</span>
            <div class="hist-rect" style="height:{{ [b.n * 14, 4]|max }}px;background:{{ b.color }};opacity:0.9"></div>
          </div>
          {% endfor %}
        </div>
        <div style="display:flex;margin-top:6px">
          {% for b in sig_buckets %}
          <span class="hist-label" style="flex:1">{{ b.range }}</span>
          {% endfor %}
        </div>
      </div>

      <!-- Sector rotation compact -->
      <div class="card">
        <div style="display:flex;align-items:center;justify-content:space-between">
          <span style="font-size:13px;color:var(--text);font-weight:600">Sector rotation</span>
          <span style="font-size:11px;color:var(--text-2)">{{ sectors|length }} sectors</span>
        </div>
        <div class="sr-grid">
          {% for sec in sectors[:9] %}
            {% if sec.avg_score >= 60 %}
              {% set bg = 'rgba(52,211,153,0.15)' %}{% set vc = 'var(--up)' %}
            {% elif sec.avg_score >= 40 %}
              {% set bg = 'rgba(245,185,66,0.12)' %}{% set vc = 'var(--amber)' %}
            {% else %}
              {% set bg = 'rgba(248,113,113,0.12)' %}{% set vc = 'var(--down)' %}
            {% endif %}
            <div class="sr-cell" style="background:{{ bg }}">
              <div class="sr-tick">{{ sec.name[:6] }}</div>
              <div class="sr-val" style="color:{{ vc }}">{{ sec.avg_score }}</div>
            </div>
          {% endfor %}
        </div>
      </div>

    </div><!-- /.mid-row -->

    <!-- Watchlist table -->
    <section id="watchlist" class="card card-pad-0">
      <div class="card-head">
        <div>
          <span class="card-title">Watchlist</span>
          <span class="card-sub" style="margin-left:8px">{{ stocks_sorted|length }} names · sorted by signal ↓</span>
        </div>
        <span class="card-sub">click ticker → jump to card</span>
      </div>

      <div class="wl-wrap">
      <table class="wl">
        <thead>
          <tr>
            <th class="first">Ticker</th>
            <th class="first">Type</th>
            <th>Last</th>
            <th>Chg</th>
            <th class="mob-hide">RSI</th>
            <th class="mob-hide">MACD H</th>
            <th class="mob-hide">Vol×</th>
            <th class="center">7d</th>
            <th class="center">Signal</th>
            <th class="center">Strength</th>
          </tr>
        </thead>
        <tbody>
          {% for s in stocks_sorted %}
            {% set sc = s.score %}
            {% set sc_class = 'high' if sc >= 60 else ('mid' if sc >= 40 else 'low') %}
            {% set chg_class = 'up' if s.price_change_pct >= 0 else 'down' %}
            {% set color = '#34d399' if sc >= 60 else ('#f5b942' if sc >= 40 else '#f87171') %}
            {% set circ = 100.53 %}
            {% set dash = circ * (sc / 100) %}
            <tr class="lb-row" data-type="{{ s.get('asset_type', 'stock') }}" data-market="{{ s.get('market', 'US') }}" data-score="{{ sc }}" data-rsi="{{ s.rsi or 0 }}" data-price="{{ s.price or 0 }}" data-ma20="{{ s.ma20 or 0 }}" data-ma60="{{ s.ma60 or 0 }}">
              <td>
                <a href="./{{ s.ticker }}.html" style="text-decoration:none;color:inherit">
                  <div class="ticker-cell">
                    <div class="ticker-tile">{{ s.ticker[:2] }}</div>
                    <div class="ticker-meta">
                      <div class="ticker-sym">{{ s.ticker }}</div>
                      <div class="ticker-name">{{ s.name }}</div>
                    </div>
                  </div>
                </a>
              </td>
              <td>
                <span class="tag {{ s.get('asset_type', 'stock') }}">{{ s.get('asset_type', 'stock') }}</span>
              </td>
              <td class="num lg">{{ "%.2f"|format(s.price) }}</td>
              <td><span class="pct-chip {{ chg_class }}">{{ "%+.2f"|format(s.price_change_pct) }}%</span></td>
              <td class="num mob-hide">{{ "%.1f"|format(s.rsi) if s.rsi else '—' }}</td>
              <td class="num mob-hide" style="color: {{ '#34d399' if s.macd_hist and s.macd_hist > 0 else '#f87171' }}">{{ ("%+.2f"|format(s.macd_hist)) if s.macd_hist is not none else '—' }}</td>
              <td class="num mob-hide">{{ "%.2f"|format(s.vol_ratio) }}×</td>
              <td class="ring-cell">
                {% if s.sparkline_svg %}{{ s.sparkline_svg | safe }}{% else %}<span style="color:var(--muted);font-family:var(--mono)">—</span>{% endif %}
              </td>
              <td class="ring-cell">
                <div style="width:40px;height:40px;position:relative">
                  <svg width="40" height="40" style="transform:rotate(-90deg);display:block">
                    <circle cx="20" cy="20" r="16" stroke="rgba(255,255,255,0.06)" stroke-width="2.5" fill="none"/>
                    <circle cx="20" cy="20" r="16" stroke="{{ color }}" stroke-width="2.5" fill="none"
                      stroke-dasharray="{{ '%.2f'|format(dash) }} {{ '%.2f'|format(circ) }}" stroke-linecap="round"/>
                  </svg>
                  <div style="position:absolute;inset:0;display:flex;align-items:center;justify-content:center;font-family:var(--mono);font-size:11px;font-weight:600;color:var(--text)">{{ sc }}</div>
                </div>
              </td>
              <td class="center"><span class="strength-badge {{ sc_class }}">{{ s.strength }}</span></td>
            </tr>
          {% endfor %}
        </tbody>
      </table>
      </div>
    </section>

  </div><!-- /.page-left -->

  <!-- ─── RIGHT SIDEBAR ─────────────────────────────────────────── -->
  <div class="page-right">

    <!-- AI Morning Brief -->
    <section id="brief" class="card">
      <div class="brief-head">
        <div class="brief-icon">✦</div>
        <div>
          <div class="brief-title">AI Morning Brief</div>
          <div class="brief-meta">{{ date }} · gemini-2.5-flash</div>
        </div>
        <span class="badge {{ bias_class }}" style="margin-left:auto">{{ bias_label|upper }}</span>
      </div>
      <div style="margin-top:4px">
        {% for section in brief_sections %}
        <div style="display:flex;gap:10px;padding-top:12px;padding-bottom:12px;{% if not loop.first %}border-top:1px solid var(--border);{% endif %}">
          <div class="brief-letter b{{ loop.index }}">{{ section.label[0] }}</div>
          <div class="brief-body">
            <div class="brief-label">{{ section.label }}</div>
            <div class="brief-text">{{ section.body }}</div>
          </div>
        </div>
        {% endfor %}
      </div>
    </section>

    <!-- Headlines -->
    <section id="headlines" class="card">
      <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:10px">
        <span class="card-title">Headlines</span>
        <span style="font-family:var(--mono);font-size:10px;color:var(--text-2)">finnhub · yfinance</span>
      </div>
      <div class="hl-list">
        {% if headlines %}
          {% for h in headlines[:15] %}
          <div class="hl-item">
            <div class="hl-meta">
              <span class="hl-ticker">{{ h.ticker }}</span>
              {% if h.source %}<span class="hl-src">{{ h.source }}</span>{% endif %}
            </div>
            <div class="hl-title">{{ h.title }}</div>
          </div>
          {% endfor %}
        {% else %}
          <div class="empty-state">// no news available</div>
        {% endif %}
      </div>
    </section>

  </div><!-- /.page-right -->

</div><!-- /.page-grid -->

<!-- ─── SECTOR HEATMAP ─────────────────────────────────────────────── -->
<section id="sectors" class="card">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:4px">
    <div>
      <span class="card-title">Sector signal heatmap</span>
      <span class="card-sub" style="margin-left:10px">avg signal · grouped by GICS sector</span>
    </div>
    <span class="card-sub">{{ sectors|length }} sectors</span>
  </div>
  <div class="sector-grid">
    {% for sector in sectors %}
      {% set avg = sector.avg_score %}
      {% set heat = 'high' if avg >= 60 else ('mid' if avg >= 40 else 'low') %}
      <div class="sector-tile {{ heat }}">
        <div class="sector-name">{{ sector.name }}</div>
        <div class="sector-avg {{ heat }}">{{ avg }}</div>
        <div class="sector-tickers">
          {% for t in sector.tickers %}
            {% set chip = 'high' if t.score >= 60 else ('mid' if t.score >= 40 else 'low') %}
            <span class="sector-chip {{ chip }}">{{ t.ticker }} · {{ t.score }}</span>
          {% endfor %}
        </div>
      </div>
    {% endfor %}
  </div>
</section>

<!-- ─── ALERT HISTORY ─────────────────────────────────────────────── -->
<section id="alerts" class="card">
  <div style="display:flex;align-items:center;justify-content:space-between;margin-bottom:8px">
    <div>
      <span class="card-title">Alert history</span>
      <span class="card-sub" style="margin-left:8px">most recent 10 · threshold ≥ 70</span>
    </div>
  </div>
  {% if alert_history %}
  <div class="timeline">
    {% for a in (alert_history[-10:] | reverse) %}
      {% set ac = 'high' if a.score >= 60 else ('mid' if a.score >= 40 else 'low') %}
      <div class="timeline-row">
        <span class="timeline-dot {{ ac }}"></span>
        <span class="timeline-date">{{ a.date }}</span>
        <span class="timeline-ticker">{{ a.ticker }}</span>
        <span class="num" style="color: {{ '#34d399' if a.score >= 60 else ('#f5b942' if a.score >= 40 else '#f87171') }}; font-size: 13px; font-weight: 700">{{ a.score }}</span>
        <span class="strength-badge {{ ac }}">{{ a.strength }}</span>
      </div>
    {% endfor %}
  </div>
  {% else %}
  <div class="empty-state">// no alert records yet</div>
  {% endif %}
</section>

<!-- ─── STOCK CARDS (per-ticker bento) ────────────────────────────── -->
<section id="stocks">
  <div style="display:flex;align-items:center;justify-content:space-between;padding:0 4px 4px">
    <div>
      <span class="card-title" style="font-size:16px">Stock signals</span>
      <span class="card-sub" style="margin-left:10px">deep-dive per ticker</span>
    </div>
    <span class="card-sub">{{ stocks_sorted|length }} cards</span>
  </div>

  <div class="bento">
  {% for s in stocks_sorted %}
    {% set sc = s.score %}
    {% set sc_class = 'high' if sc >= 60 else ('mid' if sc >= 40 else 'low') %}
    {% set chg_class = 'up' if s.price_change_pct >= 0 else 'down' %}
    {% set high = sc >= 70 %}
    {% set ring_color = '#34d399' if sc >= 60 else ('#f5b942' if sc >= 40 else '#f87171') %}
    {% set ring_circ = 144.5 %}
    {% set ring_dash = ring_circ * (sc / 100) %}
    {% set atype = s.get('asset_type', 'stock') %}

    <article id="stock-{{ s.ticker }}" class="scard{{ ' high' if high else '' }}" data-type="{{ atype }}" data-market="{{ s.get('market', 'US') }}" data-score="{{ sc }}" data-ticker="{{ s.ticker }}" data-rsi="{{ s.rsi or 0 }}" data-price="{{ s.price or 0 }}" data-ma20="{{ s.ma20 or 0 }}" data-ma60="{{ s.ma60 or 0 }}">

      <div class="scard-head">
        <div class="scard-id">
          <div class="scard-tile">{{ s.ticker[:2] }}</div>
          <div>
            <div class="scard-sym">{{ s.ticker }}</div>
            <div class="scard-name">{{ s.name }}</div>
            <div class="scard-tags">
              <span class="tag {{ atype }}">{{ atype }}</span>
              <span class="tag market">{{ s.get('market', 'US') }}</span>
            </div>
          </div>
        </div>
        <div class="scard-price">
          <div class="price-block">
            <div class="price-val">${{ "%.2f"|format(s.price) }}</div>
            <div class="price-chg {{ chg_class }}">{{ "%+.2f"|format(s.price_change_pct) }}%</div>
          </div>
          <div class="ring {{ sc_class }}">
            <svg width="56" height="56">
              <circle cx="28" cy="28" r="23" stroke="rgba(255,255,255,0.06)" stroke-width="3.5" fill="none"/>
              <circle cx="28" cy="28" r="23" stroke="{{ ring_color }}" stroke-width="3.5" fill="none"
                stroke-dasharray="{{ '%.2f'|format(ring_dash) }} {{ '%.2f'|format(ring_circ) }}" stroke-linecap="round"/>
            </svg>
            <div class="ring-num">{{ sc }}</div>
          </div>
        </div>
      </div>

      {% if s.get('price_sparkline_svg') %}
      <div style="display:flex;align-items:center;gap:8px;margin-top:-4px">
        {{ s.price_sparkline_svg | safe }}
        <span style="font-family:var(--mono);font-size:9px;color:var(--text-2)">20d price</span>
      </div>
      {% endif %}

      <div class="scard-row">
        <span class="strength-badge {{ sc_class }}">{{ s.strength }}</span>
        {% if s.get('sentiment') and s.sentiment.score is not none %}
          {% set ss = s.sentiment.score %}
          {% set sn_class = 'pos' if ss >= 3 else ('neg' if ss <= -3 else 'neut') %}
          <span class="sentiment {{ sn_class }}">{{ "+" if ss > 0 else "" }}{{ ss }}</span>
          <span style="font-size:11px;color:var(--text-2);flex:1;min-width:120px">{{ s.sentiment.summary }}</span>
        {% endif %}
      </div>

      <!-- ── Simple view: plain-English verdict ─────────────────────── -->
      <div class="beginner-only">
        <div class="beg-verdict {{ sc_class }}">
          {% if sc >= 80 %}🔥 Strong Buy — Very bullish technical setup ({{ sc }}/100)
          {% elif sc >= 60 %}📈 Buy Signal — Most indicators are pointing up ({{ sc }}/100)
          {% elif sc >= 40 %}⚖️ Mixed Signals — No clear direction ({{ sc }}/100)
          {% elif sc >= 20 %}📉 Caution — More indicators are bearish ({{ sc }}/100)
          {% else %}❄️ Avoid — Technical setup is bearish ({{ sc }}/100)
          {% endif %}
        </div>
        <div class="beg-explain">This score measures 5 technical factors: price trend (MA alignment), momentum (RSI), MACD crossover, volume strength, and how far price is above/below its 60-day average. 100 = all signals bullish.</div>
      </div>

      {% if s.get('next_earnings') %}
      <div class="earnings">
        <span class="pulse"></span>
        Earnings · {{ s.next_earnings }}
      </div>
      {% endif %}

      <div class="expert-only">
      {% set ab = s.get('analyst_buy') %}
      {% set ah = s.get('analyst_hold') %}
      {% set as_ = s.get('analyst_sell') %}
      {% if ab is not none and ah is not none and as_ is not none and (ab + ah + as_) > 0 %}
      <div>
        <div class="scard-sub">Analyst ratings</div>
        <div class="analyst-bar">
          <div class="analyst-buy"  style="flex:{{ ab }}"></div>
          <div class="analyst-hold" style="flex:{{ ah }}"></div>
          <div class="analyst-sell" style="flex:{{ as_ }}"></div>
        </div>
        <div class="analyst-counts">
          <span class="buy">Buy {{ ab }}</span>
          <span class="hold">Hold {{ ah }}</span>
          <span class="sell">Sell {{ as_ }}</span>
          {% if s.get('analyst_period') %}<span class="period">{{ s.analyst_period }}</span>{% endif %}
        </div>
      </div>
      {% endif %}
      </div>

      {% set w52h = s.get('week52_high') %}
      {% set w52l = s.get('week52_low') %}
      {% if w52h and w52l and w52h != w52l %}
        {% set rpct = ((s.price - w52l) / (w52h - w52l) * 100) | round(1) %}
        {% set rpct_clamp = [0, [rpct, 100] | min] | max %}
        <div>
          <div class="scard-sub">52w range · {{ rpct_clamp }}% from low</div>
          <div class="range-bar">
            <div class="range-fill" style="width:{{ rpct_clamp }}%"></div>
            <div class="range-thumb" style="left:{{ rpct_clamp }}%"></div>
          </div>
          <div class="range-labels">
            <span>L ${{ "%.2f"|format(w52l) }}</span>
            <span>H ${{ "%.2f"|format(w52h) }}</span>
          </div>
        </div>
      {% endif %}

      <div class="expert-only">
        <div class="scard-row">
          <span class="ma-badge ma5">MA5 · {{ s.ma5 }}</span>
          <span class="ma-badge ma20">MA20 · {{ s.ma20 }}</span>
          <span class="ma-badge ma60">MA60 · {{ s.ma60 }}</span>
          <span class="rsi-badge">RSI · {{ s.rsi }}</span>
          <span class="vol-badge">Vol · {{ "%.1f"|format(s.vol_ratio) if s.vol_ratio else "—" }}×</span>
          {% if s.get('pe_ratio') %}
          <span class="ma-badge" style="background:rgba(255,255,255,0.04);color:var(--text-2);border:1px solid var(--border)">P/E · {{ "%.1f"|format(s.pe_ratio) }}</span>
          {% endif %}
        </div>
        <div>
          <div class="scard-sub">Technical signals</div>
          <div class="signals">
            {% for sig in s.signals %}<div class="signal-item">{{ sig }}</div>{% endfor %}
          </div>
        </div>
      </div>

      {% if s.get('news') and s.news %}
      <div>
        <div class="scard-sub">Latest news</div>
        <div class="news-list">
          {% for item in s.news[:3] %}
          <div class="news-item">
            {{ item.get('title') or item.get('headline') or '' }}
            {% set src = item.get('publisher') or item.get('source') or '' %}
            {% if src %}<span class="news-pub">{{ src }}</span>{% endif %}
          </div>
          {% endfor %}
        </div>
      </div>
      {% endif %}

      {% if s.ai_view %}
      <details class="ai-details" open>
        <summary>
          <span class="ai-label">✦ AI Analysis</span>
          <span class="ai-arrow">▼</span>
        </summary>
        <div class="ai-body">{{ s.ai_view }}</div>
      </details>
      {% endif %}

      {% if s.entry %}
      <div class="entry">
        <div class="entry-label">Entry timing</div>
        <div class="entry-body">{{ s.entry }}</div>
      </div>
      {% endif %}

      <a href="./{{ s.ticker }}.html" class="copy-btn" style="display:block;text-align:center;text-decoration:none;margin-top:0;color:var(--blue)">
        → 查看詳細分析
      </a>
      <button class="copy-btn"
        data-ticker="{{ s.ticker }}"
        data-price="{{ "%.2f"|format(s.price) }}"
        data-score="{{ sc }}"
        data-entry="{{ s.entry | replace('"', '&quot;') if s.entry else '' }}"
        onclick="copyTradeSetup(this)">⎘ Copy trade setup</button>
    </article>
  {% endfor %}
  </div>
</section>

<div class="footer">⚠ Generated by AI · for research only · not investment advice · trade at your own risk</div>

</div><!-- /.page -->

<!-- ─── HK MORNING BRIEF ──────────────────────────────────────────────── -->
{% if hk_data %}
<section id="hkbrief" class="card" style="max-width:1100px;margin:24px auto;padding:28px 32px">
  <h2 style="margin:0 0 20px;font-size:18px;font-weight:700;letter-spacing:-.3px">🇭🇰 港股盤前分析</h2>

  <!-- HK Indicator Table -->
  <div style="overflow-x:auto;margin-bottom:24px">
    <table style="width:100%;border-collapse:collapse;font-size:13px">
      <thead>
        <tr style="border-bottom:1px solid var(--border)">
          <th style="text-align:left;padding:6px 10px;color:var(--muted);font-weight:600">指標</th>
          <th style="text-align:right;padding:6px 10px;color:var(--muted);font-weight:600">最新價</th>
          <th style="text-align:right;padding:6px 10px;color:var(--muted);font-weight:600">前收</th>
          <th style="text-align:right;padding:6px 10px;color:var(--muted);font-weight:600">漲跌%</th>
        </tr>
      </thead>
      <tbody>
        {% for ticker, d in hk_data.items() %}
        {% set chg = d.get('change_pct') %}
        {% set is_hk = ticker in ['TCEHY','BABA','^HSI','EWH'] %}
        {# HK/China: red=up green=down; US: green=up red=down #}
        {% if chg is not none %}
          {% if is_hk %}
            {% set color = '#ef5350' if chg >= 0 else '#26a69a' %}
          {% else %}
            {% set color = '#26a69a' if chg >= 0 else '#ef5350' %}
          {% endif %}
          {% set arrow = '▲' if chg >= 0 else '▼' %}
        {% else %}
          {% set color = 'var(--muted)' %}
          {% set arrow = '—' %}
        {% endif %}
        <tr style="border-bottom:1px solid var(--border)">
          <td style="padding:7px 10px;font-weight:500">{{ d.get('label', ticker) }}<span style="color:var(--muted);font-size:11px;margin-left:6px">{{ ticker }}</span></td>
          <td style="text-align:right;padding:7px 10px;font-variant-numeric:tabular-nums">
            {% if d.get('price') %}{{ '%.2f'|format(d['price']) }}{% else %}—{% endif %}
          </td>
          <td style="text-align:right;padding:7px 10px;font-variant-numeric:tabular-nums;color:var(--muted)">
            {% if d.get('prev') %}{{ '%.2f'|format(d['prev']) }}{% else %}—{% endif %}
          </td>
          <td style="text-align:right;padding:7px 10px;font-variant-numeric:tabular-nums;font-weight:600;color:{{ color }}">
            {% if chg is not none %}{{ arrow }} {{ '%.2f'|format(chg|abs) }}%{% else %}—{% endif %}
          </td>
        </tr>
        {% endfor %}
      </tbody>
    </table>
    <p style="font-size:11px;color:var(--muted);margin:6px 0 0">🔴港股/中概：紅漲綠跌 · 🟢美股：綠漲紅跌 · 數據延遲，僅供參考</p>
  </div>

  <!-- Gemini HK Brief -->
  {% if hk_brief %}
  <div style="background:var(--surface2);border-radius:10px;padding:20px 22px">
    <pre style="white-space:pre-wrap;font-family:var(--sans);margin:0;font-size:13.5px;line-height:1.75;color:var(--text)">{{ hk_brief }}</pre>
  </div>
  {% endif %}
</section>
{% endif %}

<!-- ─── MOBILE BOTTOM NAV (≤768px) ─────────────────────────────────── -->
<nav class="mob-nav">
  <div class="mob-nav-items">
    <a class="mob-nav-item active" href="#overview">
      <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><rect x="2" y="2" width="7" height="7" rx="1.5"/><rect x="11" y="2" width="7" height="7" rx="1.5"/><rect x="2" y="11" width="7" height="7" rx="1.5"/><rect x="11" y="11" width="7" height="7" rx="1.5"/></svg>
      Overview
    </a>
    <a class="mob-nav-item" href="#watchlist">
      <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><path d="M3 5h14M3 10h14M3 15h14"/></svg>
      Watchlist
    </a>
    <a class="mob-nav-item" href="#stocks">
      <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><polyline points="2,14 6,9 10,12 14,6 18,4"/></svg>
      Signals
    </a>
    <a class="mob-nav-item" href="#brief">
      <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="10" cy="10" r="8"/><path d="M10 6v4l3 2"/></svg>
      AI Brief
    </a>
    <a class="mob-nav-item" href="#sectors">
      <svg viewBox="0 0 20 20" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round"><circle cx="10" cy="10" r="8"/><path d="M10 2v8l5 5"/></svg>
      More
    </a>
  </div>
</nav>

<script>
// Search + keyboard shortcuts
(function() {
  var searchInput = document.getElementById('ticker-search');
  var searchHint  = document.getElementById('search-hint');

  function applySearch(q) {
    q = q.toLowerCase().trim();
    var cards = document.querySelectorAll('.scard');
    var rows  = document.querySelectorAll('.lb-row');
    var visible = 0;
    cards.forEach(function(c) {
      var ticker = (c.dataset.ticker || '').toLowerCase();
      var name   = (c.querySelector('.scard-name') || {}).textContent || '';
      var show   = !q || ticker.includes(q) || name.toLowerCase().includes(q);
      // also respect existing type/score filters
      var t = activeFilters.type === 'all' || c.dataset.type === activeFilters.type;
      var s = activeFilters.score === 0 || parseInt(c.dataset.score) >= activeFilters.score;
      c.style.display = (show && t && s) ? '' : 'none';
      if (show && t && s) visible++;
    });
    rows.forEach(function(r) {
      var ticker = (r.querySelector('.ticker-sym') || {}).textContent || '';
      var name   = (r.querySelector('.ticker-name') || {}).textContent || '';
      var show   = !q || ticker.toLowerCase().includes(q) || name.toLowerCase().includes(q);
      var t = activeFilters.type === 'all' || r.dataset.type === activeFilters.type;
      var s = activeFilters.score === 0 || parseInt(r.dataset.score) >= activeFilters.score;
      r.style.display = (show && t && s) ? '' : 'none';
    });
    var fc = document.getElementById('filter-count');
    if (fc) fc.textContent = visible + ' instruments';
  }

  if (searchInput) {
    searchInput.addEventListener('input', function() { applySearch(this.value); });
  }

  // Keyboard shortcuts
  document.addEventListener('keydown', function(e) {
    // '/' — focus search
    if (e.key === '/' && document.activeElement !== searchInput) {
      e.preventDefault();
      if (searchInput) { searchInput.focus(); searchInput.select(); }
    }
    // Escape — clear search
    if (e.key === 'Escape' && document.activeElement === searchInput) {
      searchInput.value = '';
      applySearch('');
      searchInput.blur();
    }
  });
  if (searchHint) {
    document.addEventListener('focusin', function(e) {
      searchHint.textContent = e.target === searchInput ? 'ESC' : '/';
    });
  }
})();

// Live clock
(function() {
  var el = document.getElementById('live-clock');
  if (!el) return;
  function tick() {
    var now = new Date(new Date().toLocaleString('en-US', { timeZone: 'Asia/Hong_Kong' }));
    var pad = function(n) { return String(n).padStart(2, '0'); };
    var d = now.getFullYear() + '-' + pad(now.getMonth()+1) + '-' + pad(now.getDate());
    var t = pad(now.getHours()) + ':' + pad(now.getMinutes()) + ':' + pad(now.getSeconds());
    el.textContent = d + ' ' + t + ' · HKT';
  }
  tick(); setInterval(tick, 1000);
})();

// Scroll-spy nav
(function() {
  var links = document.querySelectorAll('.nav-pill');
  var sections = Array.prototype.map.call(links, function(l) {
    var h = l.getAttribute('href');
    return h && h.indexOf('#') === 0 ? document.querySelector(h) : null;
  });
  function onScroll() {
    var y = window.scrollY + 140;
    var active = -1;
    sections.forEach(function(s, i) { if (s && s.offsetTop <= y) active = i; });
    links.forEach(function(l, i) { l.classList.toggle('active', i === active); });
  }
  window.addEventListener('scroll', onScroll, { passive: true });
  onScroll();
})();

// Filters
var activeFilters = { type: 'all', score: 0, special: null };
document.querySelectorAll('.filter-btn').forEach(function(btn) {
  btn.addEventListener('click', function() {
    var g = btn.dataset.filter, v = btn.dataset.value;
    if (g === 'score') {
      if (activeFilters.score === parseInt(v)) {
        activeFilters.score = 0;
        btn.classList.remove('active');
      } else {
        activeFilters.score = parseInt(v);
        document.querySelectorAll('.filter-btn[data-filter="score"]').forEach(function(b) { b.classList.remove('active'); });
        btn.classList.add('active');
      }
    } else {
      activeFilters[g] = v;
      document.querySelectorAll('.filter-btn[data-filter="' + g + '"]').forEach(function(b) { b.classList.remove('active'); });
      btn.classList.add('active');
    }
    applyFilters();
  });
});
function passesSpecial(el, sp) {
  if (!sp) return true;
  var score = parseInt(el.dataset.score || 0);
  var rsi   = parseFloat(el.dataset.rsi || 0);
  var price = parseFloat(el.dataset.price || 0);
  var ma20  = parseFloat(el.dataset.ma20 || 0);
  var ma60  = parseFloat(el.dataset.ma60 || 0);
  if (sp === 'breakout') return score >= 70 && price > 0 && ma20 > 0 && price > ma20;
  if (sp === 'rsi5070')  return rsi >= 50 && rsi <= 70;
  if (sp === 'newhigh')  return score >= 75;
  return true;
}
function applyFilters() {
  var searchInput = document.getElementById('ticker-search');
  var q = searchInput ? searchInput.value.toLowerCase().trim() : '';
  var cards = document.querySelectorAll('.scard');
  var rows  = document.querySelectorAll('.lb-row');
  var visible = 0;
  cards.forEach(function(c) {
    var t = activeFilters.type === 'all' || c.dataset.type === activeFilters.type;
    var s = activeFilters.score === 0 || parseInt(c.dataset.score) >= activeFilters.score;
    var sp = passesSpecial(c, activeFilters.special);
    var ticker = (c.dataset.ticker || '').toLowerCase();
    var name   = (c.querySelector('.scard-name') || {}).textContent || '';
    var sq = !q || ticker.includes(q) || name.toLowerCase().includes(q);
    var show = t && s && sp && sq;
    c.style.display = show ? '' : 'none';
    if (show) visible++;
  });
  rows.forEach(function(r) {
    var t = activeFilters.type === 'all' || r.dataset.type === activeFilters.type;
    var s = activeFilters.score === 0 || parseInt(r.dataset.score) >= activeFilters.score;
    var sp = passesSpecial(r, activeFilters.special);
    var ticker = (r.querySelector('.ticker-sym') || {}).textContent || '';
    var name   = (r.querySelector('.ticker-name') || {}).textContent || '';
    var sq = !q || ticker.toLowerCase().includes(q) || name.toLowerCase().includes(q);
    r.style.display = (t && s && sp && sq) ? '' : 'none';
  });
  var fc = document.getElementById('filter-count');
  if (fc) fc.textContent = visible + ' instruments';
}

// SPY period tabs
(function() {
  document.querySelectorAll('.period-tab').forEach(function(tab) {
    tab.addEventListener('click', function() {
      document.querySelectorAll('.period-tab').forEach(function(t) { t.classList.remove('active'); });
      tab.classList.add('active');
      var p = tab.dataset.period;
      ['1d','1m','3m','6m'].forEach(function(id) {
        var el = document.getElementById('spy-chart-' + id);
        if (el) el.style.display = id === p ? '' : 'none';
      });
    });
  });
})();

// Sort toggle
(function() {
  var btn = document.getElementById('sort-btn');
  if (!btn) return;
  btn.addEventListener('click', function() {
    var asc = btn.dataset.sort === 'asc';
    btn.dataset.sort = asc ? 'desc' : 'asc';
    btn.textContent = 'Signal ' + (asc ? '↓' : '↑');
    var bento = document.querySelector('.bento');
    var tbody = document.querySelector('.wl tbody');
    if (bento) {
      var cards = Array.from(bento.children);
      cards.sort(function(a,b) {
        var sa = parseInt(a.dataset.score||0), sb = parseInt(b.dataset.score||0);
        return asc ? sa-sb : sb-sa;
      });
      cards.forEach(function(c) { bento.appendChild(c); });
    }
    if (tbody) {
      var rows = Array.from(tbody.querySelectorAll('.lb-row'));
      rows.sort(function(a,b) {
        var sa = parseInt(a.dataset.score||0), sb = parseInt(b.dataset.score||0);
        return asc ? sa-sb : sb-sa;
      });
      rows.forEach(function(r) { tbody.appendChild(r); });
    }
  });
})();

// ── Expert ↔ Simple mode toggle ─────────────────────────────────────
function toggleMode() {
  var btn  = document.getElementById('mode-toggle');
  var body = document.body;
  var isBeginner = body.classList.toggle('beginner-mode');
  if (btn) btn.textContent = isBeginner ? '🔬 Expert' : '📖 Simple';
  try { localStorage.setItem('signalViewMode', isBeginner ? 'beginner' : 'expert'); } catch(e) {}
}
// Restore saved mode on page load
(function() {
  try {
    if (localStorage.getItem('signalViewMode') === 'beginner') {
      document.body.classList.add('beginner-mode');
      var btn = document.getElementById('mode-toggle');
      if (btn) btn.textContent = '🔬 Expert';
    }
  } catch(e) {}
})();

// ── Market open/closed badge ─────────────────────────────────────────
(function() {
  function updateMarketStatus() {
    var el    = document.getElementById('market-status');
    var label = document.getElementById('market-label');
    if (!el || !label) return;

    // Use America/New_York to handle EDT/EST automatically
    var now   = new Date();
    var parts = new Intl.DateTimeFormat('en-US', {
      timeZone: 'America/New_York',
      weekday: 'short', hour: 'numeric', minute: '2-digit', hour12: false
    }).formatToParts(now);

    var day  = '';
    var hour = 0;
    var min  = 0;
    parts.forEach(function(p) {
      if (p.type === 'weekday') day  = p.value;           // 'Mon'–'Sun'
      if (p.type === 'hour')   hour = parseInt(p.value);
      if (p.type === 'minute') min  = parseInt(p.value);
    });

    var isWeekday = ['Mon','Tue','Wed','Thu','Fri'].indexOf(day) >= 0;
    var mins      = hour * 60 + min;
    var isOpen    = isWeekday && mins >= 570 && mins < 960;  // 9:30–16:00 ET

    el.classList.toggle('closed', !isOpen);
    label.textContent = isOpen ? 'Market Open' : 'Market Closed';
  }

  updateMarketStatus();
  setInterval(updateMarketStatus, 60000);  // re-check every minute
})();

// ── Manual refresh ───────────────────────────────────────────────────
function doRefresh(btn) {
  if (btn) {
    btn.classList.add('spinning');
    btn.disabled = true;
  }
  // Hard reload — bypasses browser cache, picks up latest GitHub Pages deploy
  window.location.reload(true);
}

// ── Auto-refresh every 10 min with countdown display ─────────────────
(function() {
  var AUTO_REFRESH_MS = 10 * 60 * 1000;  // 10 minutes
  var deadline = Date.now() + AUTO_REFRESH_MS;
  var countdownEl = document.getElementById('auto-refresh-countdown');

  function pad(n) { return n < 10 ? '0' + n : '' + n; }

  function tick() {
    var remaining = Math.max(0, deadline - Date.now());
    var mins = Math.floor(remaining / 60000);
    var secs = Math.floor((remaining % 60000) / 1000);
    if (countdownEl) countdownEl.textContent = '· auto ↻ ' + pad(mins) + ':' + pad(secs);
    if (remaining <= 0) {
      window.location.reload(true);
    }
  }

  tick();
  setInterval(tick, 1000);
})();

// View toggle (cards ↔ table)
(function() {
  var btn = document.getElementById('view-btn');
  if (!btn) return;
  btn.addEventListener('click', function() {
    var showTable = btn.dataset.view === 'cards';
    btn.dataset.view = showTable ? 'table' : 'cards';
    btn.textContent = showTable ? '☰ Table' : '⊞ Cards';
    var bento = document.querySelector('.bento');
    var wlSection = document.getElementById('watchlist');
    var stocksSection = document.getElementById('stocks');
    if (bento) bento.style.display = showTable ? 'none' : '';
    if (stocksSection) {
      var header = stocksSection.querySelector('div');
      if (header) header.style.display = showTable ? 'none' : '';
    }
    if (wlSection) wlSection.style.display = showTable ? '' : 'none';
  });
})();

// Special filters: breakout, rsi5070, newhigh
document.querySelectorAll('.filter-btn[data-filter="special"]').forEach(function(btn) {
  btn.addEventListener('click', function() {
    var isActive = btn.classList.contains('active');
    document.querySelectorAll('.filter-btn[data-filter="special"]').forEach(function(b) { b.classList.remove('active'); });
    if (!isActive) {
      btn.classList.add('active');
      activeFilters.special = btn.dataset.value;
    } else {
      activeFilters.special = null;
    }
    applyFilters();
  });
});

// Mobile bottom nav active state on scroll
(function() {
  var navItems = document.querySelectorAll('.mob-nav-item');
  var sections = ['overview','watchlist','stocks','brief','sectors'].map(function(id) {
    return document.getElementById(id);
  });
  function onScroll() {
    var y = window.scrollY + 160;
    var activeIdx = 0;
    sections.forEach(function(s, i) { if (s && s.offsetTop <= y) activeIdx = i; });
    navItems.forEach(function(n, i) { n.classList.toggle('active', i === activeIdx); });
  }
  window.addEventListener('scroll', onScroll, { passive: true });
})();

// Copy trade setup
function copyTradeSetup(btn) {
  var ticker = btn.dataset.ticker;
  var price = btn.dataset.price;
  var score = btn.dataset.score;
  var entry = btn.dataset.entry || '';
  function extract(text, kws) {
    for (var i = 0; i < kws.length; i++) {
      var re = new RegExp(kws[i] + '[\\s：:]*[$＄]?([\\d]+\\.?[\\d]*)');
      var m = text.match(re);
      if (m) return m[1];
    }
    return null;
  }
  var ep = extract(entry, ['買入', '入場', '建議買入', 'buy', 'entry']) || price;
  var sp = extract(entry, ['止損', 'stop', '停損']);
  var tp = extract(entry, ['目標', 'target', '第一目標', '目標價']);
  var text;
  if (sp || tp) {
    text = '[' + ticker + '] ENTRY: $' + ep;
    if (sp) text += ' | STOP: $' + sp;
    if (tp) text += ' | TARGET: $' + tp;
    text += ' | SIGNAL: ' + score + '/100';
  } else {
    text = entry ? ('[' + ticker + '] ' + entry + ' | SIGNAL: ' + score + '/100')
                 : ('[' + ticker + '] PRICE: $' + price + ' | SIGNAL: ' + score + '/100');
  }
  navigator.clipboard.writeText(text).then(function() {
    var orig = btn.textContent;
    btn.textContent = '✓ COPIED';
    btn.style.background = 'rgba(52,211,153,0.12)';
    btn.style.color = 'var(--up)';
    btn.style.borderColor = 'rgba(52,211,153,0.30)';
    setTimeout(function() {
      btn.textContent = orig;
      btn.style.background = '';
      btn.style.color = '';
      btn.style.borderColor = '';
    }, 2000);
  }).catch(function() {
    btn.textContent = '✗ FAILED';
    setTimeout(function() { btn.textContent = '⎘ Copy trade setup'; }, 2000);
  });
}
</script>
</body>
</html>
"""


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


def _build_area_svg(points: list[float], width: int = 560, height: int = 120) -> str:
    """Return an SVG area chart for the given data points (score trend fallback)."""
    if len(points) < 2:
        return (
            f'<div style="height:{height}px;display:flex;align-items:center;'
            f'justify-content:center;color:#52545e;font-size:11px;'
            f'font-family:monospace">No trend data yet</div>'
        )
    mn, mx = min(points), max(points)
    rng = mx - mn or 1
    n = len(points)
    step = (width - 4) / (n - 1)
    xy = []
    for i, v in enumerate(points):
        x = 2 + i * step
        y = (height - 4) - ((v - mn) / rng) * (height - 8)
        xy.append((x, y))
    color = "#34d399" if points[-1] >= points[0] else "#f87171"
    line_d = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in xy)
    area_d = line_d + f" L {xy[-1][0]:.1f},{height} L {xy[0][0]:.1f},{height} Z"
    return (
        f'<svg width="100%" viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'xmlns="http://www.w3.org/2000/svg" style="display:block;margin-top:4px">'
        f'<path d="{area_d}" fill="{color}" fill-opacity="0.08"/>'
        f'<path d="{line_d}" stroke="{color}" stroke-width="1.5" fill="none" stroke-linejoin="round"/>'
        f'</svg>'
    )


def _build_spy_price_svg(ohlc: list[dict], stock: dict, width: int = 560, height: int = 120) -> str:
    """Return an SVG price-line chart for SPY using real OHLC close prices.

    Shows the last 60 bars, with MA20 (blue dashed) and MA60 (purple dashed)
    reference lines, and resistance/support labels at the right edge.
    """
    if not ohlc or len(ohlc) < 5:
        spy_pts = stock.get("sparkline_points", []) if stock else []
        return _build_area_svg(spy_pts, width, height)

    bars = ohlc[-60:]  # last 60 trading days
    closes = [b.get("c", 0) for b in bars]
    n = len(closes)

    # Moving averages
    def _sma(data, period):
        return [
            sum(data[max(0, i - period + 1):i + 1]) / min(i + 1, period)
            for i in range(len(data))
        ]

    ma20 = _sma(closes, 20)
    ma60 = _sma(closes, 60)

    # Price range with 4% padding
    mn = min(closes)
    mx = max(closes)
    rng = mx - mn or mx * 0.01 or 1
    mn -= rng * 0.04
    mx += rng * 0.04
    rng = mx - mn

    pad_l, pad_r = 4, 54
    chart_w = width - pad_l - pad_r

    def cx(i):
        return pad_l + (i / (n - 1)) * chart_w if n > 1 else pad_l

    def cy(price):
        return (height - 4) - ((price - mn) / rng) * (height - 8)

    parts = [
        f'<svg width="100%" viewBox="0 0 {width} {height}" preserveAspectRatio="none" '
        f'xmlns="http://www.w3.org/2000/svg" style="display:block;margin-top:4px">'
    ]

    # Gridlines at 33% and 66%
    for frac in (0.33, 0.66):
        gy = 4 + frac * (height - 8)
        price_at_line = mx - frac * rng
        parts.append(
            f'<line x1="{pad_l}" y1="{gy:.1f}" x2="{pad_l + chart_w}" y2="{gy:.1f}" '
            f'stroke="#23252f" stroke-dasharray="2 4" stroke-width="1"/>'
        )
        parts.append(
            f'<text x="{pad_l + chart_w + 4}" y="{gy + 3:.1f}" '
            f'font-size="9" fill="#52545e" font-family="JetBrains Mono,monospace">'
            f'{price_at_line:.0f}</text>'
        )

    # MA60 line (purple, behind MA20)
    ma60_pts = " ".join(f"{cx(i):.1f},{cy(ma60[i]):.1f}" for i in range(n))
    parts.append(
        f'<polyline points="{ma60_pts}" fill="none" stroke="#b18cff" '
        f'stroke-width="1" stroke-dasharray="3 3" stroke-opacity="0.7"/>'
    )

    # MA20 line (blue)
    ma20_pts = " ".join(f"{cx(i):.1f},{cy(ma20[i]):.1f}" for i in range(n))
    parts.append(
        f'<polyline points="{ma20_pts}" fill="none" stroke="#7aa2ff" '
        f'stroke-width="1" stroke-dasharray="3 3" stroke-opacity="0.8"/>'
    )

    # Price area fill
    price_xy = [(cx(i), cy(closes[i])) for i in range(n)]
    line_d = "M " + " L ".join(f"{x:.1f},{y:.1f}" for x, y in price_xy)
    last_x, last_y = price_xy[-1]
    first_x = price_xy[0][0]
    area_d = line_d + f" L {last_x:.1f},{height} L {first_x:.1f},{height} Z"
    color = "#34d399" if closes[-1] >= closes[0] else "#f87171"
    parts.append(f'<path d="{area_d}" fill="{color}" fill-opacity="0.07"/>')
    parts.append(
        f'<path d="{line_d}" stroke="{color}" stroke-width="1.5" '
        f'fill="none" stroke-linejoin="round"/>'
    )

    # Current price tag at right edge
    cur_y = cy(closes[-1])
    parts.append(
        f'<rect x="{pad_l + chart_w + 2}" y="{cur_y - 7:.1f}" '
        f'width="50" height="13" rx="3" fill="{color}" fill-opacity="0.18"/>'
    )
    parts.append(
        f'<text x="{pad_l + chart_w + 4}" y="{cur_y + 3:.1f}" '
        f'font-size="9" font-weight="700" fill="{color}" '
        f'font-family="JetBrains Mono,monospace">{closes[-1]:.2f}</text>'
    )

    # MA labels at right edge
    ma20_y = cy(ma20[-1])
    parts.append(
        f'<text x="{pad_l + chart_w + 4}" y="{ma20_y + 3:.1f}" '
        f'font-size="8" fill="#7aa2ff" font-family="JetBrains Mono,monospace">M20</text>'
    )
    ma60_y = cy(ma60[-1])
    parts.append(
        f'<text x="{pad_l + chart_w + 4}" y="{ma60_y + 3:.1f}" '
        f'font-size="8" fill="#b18cff" font-family="JetBrains Mono,monospace">M60</text>'
    )

    parts.append("</svg>")
    return "".join(parts)


def _build_price_sparkline_svg(ohlc: list, width: int = 80, height: int = 28) -> str:
    """Tiny inline SVG showing close price trend for last 20 bars."""
    bars = (ohlc or [])[-20:]
    closes = [b.get("c", 0) for b in bars if b.get("c", 0) > 0]
    if len(closes) < 2:
        return ""
    mn, mx = min(closes), max(closes)
    rng = mx - mn or mn * 0.01 or 1
    n = len(closes)
    step = (width - 4) / (n - 1)
    pts = " ".join(
        f"{2 + i * step:.1f},{height - 4 - ((v - mn) / rng) * (height - 8):.1f}"
        for i, v in enumerate(closes)
    )
    color = "#34d399" if closes[-1] >= closes[0] else "#f87171"
    return (
        f'<svg width="{width}" height="{height}" viewBox="0 0 {width} {height}" '
        f'xmlns="http://www.w3.org/2000/svg">'
        f'<polyline points="{pts}" fill="none" stroke="{color}" '
        f'stroke-width="1.5" stroke-linejoin="round" stroke-linecap="round"/>'
        f'</svg>'
    )


def _build_sig_buckets(stocks: list) -> list[dict]:
    """Return signal score distribution buckets for the histogram."""
    buckets = [
        {"range": "0–20",   "lo": 0,  "hi": 20,  "color": "#f87171", "n": 0},
        {"range": "20–40",  "lo": 20, "hi": 40,  "color": "#ff8a4d", "n": 0},
        {"range": "40–60",  "lo": 40, "hi": 60,  "color": "#f5b942", "n": 0},
        {"range": "60–80",  "lo": 60, "hi": 80,  "color": "#80c97f", "n": 0},
        {"range": "80–100", "lo": 80, "hi": 101, "color": "#34d399", "n": 0},
    ]
    for s in stocks:
        sc = s.get("score", 0)
        for b in buckets:
            if b["lo"] <= sc < b["hi"]:
                b["n"] += 1
                break
    return buckets


def _collect_headlines(stocks: list) -> list[dict]:
    """Collect deduplicated top headlines from all stocks."""
    seen: set[str] = set()
    headlines = []
    for s in stocks:
        news = s.get("news") or []
        for item in news[:2]:
            title = (item.get("title") or item.get("headline") or "").strip()
            if not title or title in seen:
                continue
            seen.add(title)
            headlines.append({
                "ticker": s["ticker"],
                "title": title,
                "source": (item.get("publisher") or item.get("source") or "")[:25],
            })
        if len(headlines) >= 20:
            break
    return headlines


def generate_dashboard(
    date: str,
    market_overview: dict,
    morning_brief: str,
    stock_results: list,
    output_dir: str = "outputs",
    score_history: dict | None = None,
    alert_history: list | None = None,
    fear_greed: dict | None = None,
    hk_brief: str = "",
    hk_data: dict | None = None,
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

    sig_buckets = _build_sig_buckets(stocks_sorted)
    headlines = _collect_headlines(stocks_sorted)

    # Attach price sparklines to each stock dict
    for stk in stocks_sorted:
        stk["price_sparkline_svg"] = _build_price_sparkline_svg(stk.get("ohlc", []))

    # Fear & Greed
    fg = fear_greed or {}
    fg_value = fg.get("value")
    fg_label = fg.get("label", "")
    fg_prev  = fg.get("prev_week")
    fg_delta = (fg_value - fg_prev) if (fg_value is not None and fg_prev is not None) else None

    # SPY period charts (1D=5bars, 1M=22bars, 3M=66bars, 6M=all)
    spy_stock = next((s for s in stocks_sorted if s["ticker"] == "SPY"), None)
    spy_ohlc  = spy_stock.get("ohlc", []) if spy_stock else []
    spy_chart_1d = _build_spy_price_svg(spy_ohlc[-5:]  if spy_ohlc else [], spy_stock, width=560, height=120)
    spy_chart_1m = _build_spy_price_svg(spy_ohlc[-22:] if spy_ohlc else [], spy_stock, width=560, height=120)
    spy_chart_3m = _build_spy_price_svg(spy_ohlc[-66:] if spy_ohlc else [], spy_stock, width=560, height=120)
    spy_chart_6m = _build_spy_price_svg(spy_ohlc,                           spy_stock, width=560, height=120)

    html = Template(DASHBOARD_HTML).render(
        date=date,
        generated_at=datetime.now(tz=timezone(timedelta(hours=8))).strftime("%b %d %H:%M HKT"),
        market=market_overview,
        brief_sections=brief_sections,
        stocks_sorted=stocks_sorted,
        sectors=sectors,
        alert_history=alert_history or [],
        sig_buckets=sig_buckets,
        headlines=headlines,
        spy_chart_1d=spy_chart_1d,
        spy_chart_1m=spy_chart_1m,
        spy_chart_3m=spy_chart_3m,
        spy_chart_6m=spy_chart_6m,
        fg_value=fg_value,
        fg_label=fg_label,
        fg_delta=fg_delta,
        hk_brief=hk_brief,
        hk_data=hk_data or {},
    )

    filename = f"report_{datetime.now().strftime('%Y%m%d')}.html"
    path = os.path.join(output_dir, filename)
    with open(path, "w", encoding="utf-8") as f:
        f.write(html)

    # Always overwrite index.html for GitHub Pages
    latest_path = os.path.join(output_dir, "index.html")
    with open(latest_path, "w", encoding="utf-8") as f:
        f.write(html)

    # Generate per-stock detail pages
    ticker_list = [s["ticker"] for s in stocks_sorted]
    for stk in stocks_sorted:
        try:
            generate_stock_detail_page(stk, date, output_dir, ticker_list=ticker_list)
        except Exception as exc:
            print(f"  [detail] {stk.get('ticker', '?')} skipped: {exc}")

    return path
