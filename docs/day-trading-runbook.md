# Day Trading Runbook — 一頁看懂

> The whole system on one page. Updated 2026-06-11.

## The Loop (your nightly workflow)

```
1. 引擎自動上線 9:25pm HKT (launchd) ─── Telegram: "📡 引擎上線"
2. 觸發訊號 → Telegram ping 你 ──────── 🟢 BUY / 🔴 SELL + 連結
3. 點連結 → ticker 詳情頁 ───────────── 看即時 TradingView 圖確認
4. 你決定 → IBKR 手動下 paper 單 ────── 系統永不自動交易
5. 引擎自動下線 4:10am HKT ──────────── Telegram: "📡 引擎下線"
```

**You only do steps 3-4. Everything else is automatic.**

## Daily prerequisites (one-time each day)

| Check | How |
|---|---|
| IB Gateway open + logged in (paper) | Green rows in Gateway window. Set Configure → Lock and Exit → Auto restart so it survives overnight |
| Daily analysis ran | Telegram daily brief arrived = yes |

## The 4 trigger rules

| Alert | Condition | Suggested action |
|---|---|---|
| 🟢 MA20 reclaim | Price crosses back above MA20, score ≥70 | Consider entry — confirm on live chart volume |
| 🚀 Breakout | Price breaks yesterday's high, score ≥70 | Consider entry — strongest signal |
| 🔴 MA20 break | Price drops below MA20 | Consider exit if holding |
| ⚠️ Drawdown | −3% from session high | Consider exit / tighten stop |

4h cooldown per ticker per rule — one ping each, no spam.
All 8 open paper positions always monitored regardless of score.

## Commands

```bash
# Manual start (any time Gateway is up)
cd ~/Documents/stock-monitoring-tool && python3 -u src/ibkr_stream_alerts.py

# Check engine log
tail -f ~/Documents/stock-monitoring-tool/outputs/stream.log

# Connection sanity check
python3 src/ibkr_connect_test.py

# Enable / disable nightly auto-start
launchctl load   ~/Library/LaunchAgents/com.terrence.ibkr-stream.plist
launchctl unload ~/Library/LaunchAgents/com.terrence.ibkr-stream.plist
```

## Layers (what runs where)

| Layer | Cadence | Job |
|---|---|---|
| Daily analysis (GitHub Actions) | 1×/day | Scores 250 tickers, sets MA20/score levels, Telegram brief |
| Price refresh (GitHub Actions) | 15 min | Dashboard prices, exit alerts, paper TP/SL |
| **Stream engine (your Mac)** | **every tick** | **Real-time buy/sell triggers vs daily levels** |
| TradingView embed (browser) | real-time | Visual confirmation on detail pages |

## Safety rails

- Paper account DUQ582346 only (port 4002 — live port 4001 never configured)
- Gateway Read-Only API ON — order placement physically blocked
- Engine code contains zero order functions — alerts only
- Quotes 15-min delayed (free). Real-time upgrade: IBKR → Market Data
  Subscriptions → US Securities Snapshot Bundle (~US$4.50/mo) — no code change needed

## Troubleshooting

| Symptom | Fix |
|---|---|
| "Connection failed" | Gateway not running / not logged in. Open Gateway first |
| No startup Telegram at 9:25pm | `launchctl list \| grep ibkr` — reload plist; check stream.err.log |
| Alerts seem stale | Free tier = 15-min delayed quotes. Expected |
| Gateway logged out overnight | Configure → Lock and Exit → enable Auto restart |
