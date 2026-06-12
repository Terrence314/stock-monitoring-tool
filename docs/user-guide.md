# 📘 Stock Monitoring Tool — Complete User Guide
> Version 2026-06-12 · for Terrence · everything in one document

---

## 1. What This Platform Is

A personal investment decision system. It watches ~250 US stocks + 10 HK tickers,
scores them 0–100 daily with technical indicators, suggests specific buy/sell
actions, simulates trades with virtual money, and pings your Telegram when
real-time trigger points hit.

**The one rule that governs everything: the system NEVER trades automatically.
Every action is a suggestion. You confirm or ignore. Money only moves when
your hands move it.**

### The 4 layers

| Layer | Runs | Where | Job |
|---|---|---|---|
| Daily analysis | 1×/day (~8am HKT) | GitHub Actions (cloud) | Score everything, AI brief, suggestions, Telegram daily message |
| Price refresh | every 15 min | GitHub Actions (cloud) | Update dashboard prices, exit alerts, paper TP/SL |
| Stream engine | every tick, 9:25pm–4:10am HKT | Your Mac + IB Gateway | Real-time buy/sell trigger alerts to Telegram |
| Live charts | real-time | Browser (TradingView embed) | Visual confirmation on ticker pages |

---

## 2. Your Daily Routine (2 minutes)

1. Open **https://terrence314.github.io/stock-monitoring-tool/**
2. Read the **⚡ 今日行動 Action Box** at the top:
   - 🟢 **BUY XXX — $1,000 · 止損−5% · 持有≤10日** → agree? Place the paper trade in IBKR. Disagree? Skip.
   - 🔴 **SELL XXX — 持倉轉弱** → consider closing that position
   - ✅ **今日無行動** → close the page. Done.
3. Check the two status lines under the actions:
   - **斷路器 (circuit breaker)** — monthly PnL vs −5% limit. If 🛑 TRIPPED: no new buys this month, period.
   - **真錢門檻 (go-live gate)** — Day N/60, win rate, PnL. This decides when real money starts.

That's the whole routine. Everything below is reference.

---

## 3. Dashboard Sections — Top to Bottom

| Section | What it tells you | How to use |
|---|---|---|
| **⚡ 今日行動 Action Box** | Exact actions for today | The only must-read. See §2 |
| **KPI strip** | Market bias, strong signal count, avg score, Fear & Greed | One-glance market mood. Hover any tile for explanation |
| **Watchlist table** | Your 31 core tickers ranked by score | Click any ticker → detail page. Hover column headers for meanings |
| **Morning Brief** | Gemini AI's daily market summary (中文) | Context read, 1 min |
| **Headlines** | News affecting your tickers | Skim |
| **Sector heatmap** | Which sectors strong/weak (🟢≥60 🟡40-59 🔴<40) | Spot rotation — buy strength, avoid weakness |
| **Alert history** | Recent exit alerts fired | Audit trail |
| **Favourites** | Tickers you starred | Personal shortlist |
| **ETF panel** | Core ETFs ranked | For index-level positioning |
| **Tier 2 stock cards** | Top 50 scorers, full analysis each | Deep dive when Action Box names a ticker. 📖 How-to-Read guide at section top |
| **Universe leaderboard** | Top 100 of the 250-ticker scan | Discovery — what's rising before it hits Tier 2 |
| **HK Morning Brief** | 港股 summary, red=up convention | HK session context |

### Ticker detail page (click any ticker)
- **Candlestick chart** — 64 days, MA5/20/60, volume, MACD
- **即時圖表 Live Chart** — real-time TradingView, 5-min candles (auto-loads on scroll)
- **Score ring + breakdown** — why this score, factor by factor
- **Technical signals** — every active signal in plain language
- **Key levels / scenarios / strategy** — support, resistance, entry plans
- **Entry verdict chip** — GO 🟢 / WAIT 🟡 / SKIP 🔴 / BREAKOUT 🚀 etc.

---

## 4. The Scoring System (0–100)

5 factors × 20 points each:

| Factor | Full marks when |
|---|---|
| ① Trend | Price > MA5 > MA20 > MA60 (多頭排列) |
| ② RSI | 45–70 and rising (sweet spot — momentum without overheating) |
| ③ MACD | Golden cross above zero line, histogram expanding |
| ④ Volume | ≥1.5× the 20-day average (爆量) |
| ⑤ MA60 distance | >5% above MA60 (穩站中期成本之上) |

Score bands: **80+ 強力做多 🔥 · 60+ 偏多 📈 · 40+ 中性 ⚖️ · 20+ 偏空 📉 · <20 強力做空 ❄️**

Supplementary signals (don't change score, except noted):
- **S1 trend signals** — EMA200 slope, EMA stack, 52-week-high distance, S1 入場訊號 (healthy pullback entry)
- **Overextension penalty** — 1-month gain >25% → score −10 (chase risk)
- **KD(9,3,3)** — bottom golden cross 🎯, oversold 🔵
- **Bollinger** — squeeze ⚡, breakout 🚀, walking bands, band touches
- **均線 context** — 假跌破洗盤 ⚡ (false breakdown = opportunity), 真轉弱 🔴 (true weakness = exit)

---

## 4b. One BUY Rule Everywhere (alignment, updated 2026-06-13)

Every surface now uses the SAME definition of a buy:
**verdict GO ✅ / BREAKOUT ↑ AND score ≥ 70** — with exact order ticket
(買入 ≤ entry · 止損 −8% · 目標 +12% · 期限 10 交易日).

| Surface | What you see |
|---|---|
| Dashboard ⚡ 今日行動 | Order tickets (the master copy) |
| Daily Telegram | Identical 今日行動 section, same numbers |
| Night stream engine | Triggers fire at score ≥70 with same ticket attached |
| Paper engine (auto) | Only enters GO/BREAKOUT↑ stocks — measures the strategy you're told to follow |

High score alone never triggers a buy anywhere — score tables are
labeled 「排名，非買入指令」. Exit alerts say 持倉轉弱 only if you actually
hold the ticker; otherwise 毋須行動. When the circuit breaker is tripped,
every BUY everywhere carries 📝 紙上練習單.

---

## 5. Telegram Alerts — What Each Message Means

| Message | Source | Meaning | Your move |
|---|---|---|---|
| Daily brief (morning) | Daily pipeline | Market summary + top signals | Read with coffee |
| 🔴 Exit alert | 15-min refresh | A high-score ticker's score collapsed | Check if you hold it |
| 📡 引擎上線 (9:25pm) | Stream engine | Night monitoring started | Nothing — confirmation |
| 🟢 BUY trigger | Stream engine | Price reclaimed MA20 or broke yesterday's high (both score≥70, same bar as Action Box) | Tap link → check live chart → decide |
| 🔴 SELL trigger | Stream engine | Held position broke MA20 | Consider exit |
| ⚠️ SELL trigger | Stream engine | Held position −3% from session high | Consider exit / tighten stop |
| 📡 引擎下線 (4:10am) | Stream engine | US session over | Sleep well |
| ⚠️ 引擎無法啟動 | Stream engine | IB Gateway wasn't open | Open Gateway, rerun |

Alert hygiene: 4-hour cooldown per ticker per rule — you get ONE ping per event, not spam.

---

## 6. Paper Trading & The Road to Real Money

### How the simulator works
- Opens $1,000 virtual positions on score ≥70 (long only, no shorts)
- Auto-closes: +8% take profit / −5% stop loss / 10 trading days max hold
- SPY regime gate: bear market (SPY score <40) = no new buys
- Track record on the paper trading page (linked from dashboard)

### The go-live gate (started 2026-06-11)
Real money unlocks ONLY when ALL of these are true:
1. **60 days** of validation elapsed (earliest ~Aug 10)
2. **Win rate >50%** on trades closed in the window
3. **Total PnL positive**
4. Circuit breaker not tripped

Progress shows in the Action Box daily. The decision makes itself from data.

### When gate opens — the plan
- Start under HK$50k, ~HK$8k per position
- Same rules as paper: −5% stop, ≤10 day hold, max 5-6 concurrent positions
- −5% monthly circuit breaker stays — tool shows 🛑 STOP TRADING, you stop

---

## 7. IBKR Setup Reference

| Item | Value |
|---|---|
| Account | DUQ582346 (paper — "DU" prefix = demo) |
| Username | tcpaper314 |
| Gateway port | 4002 (paper; live 4001 never configured) |
| Login mode | Paper Trading, IB API |
| Critical settings | API enabled, port 4002, **Read-Only API ON** (blocks all order placement at gateway level), Auto restart on |
| VPN | OFF when logging in (IBKR blocks some VPN regions) |

### Commands
```bash
# Test gateway connection
cd ~/Documents/stock-monitoring-tool && python3 src/ibkr_connect_test.py

# Start stream engine manually
python3 -u src/ibkr_stream_alerts.py

# Engine log
tail -f outputs/stream.log

# Auto-start on/off (loaded = starts 9:25pm Mon-Fri automatically)
launchctl load   ~/Library/LaunchAgents/com.terrence.ibkr-stream.plist
launchctl unload ~/Library/LaunchAgents/com.terrence.ibkr-stream.plist
```

### Secrets
`config/secrets.json` (gitignored, never leaves your Mac) holds the Telegram
bot token + chat id for local alerts. GitHub Actions uses repo secrets separately.

---

## 8. Data Honesty — What's Real, What's Not

| Component | Status |
|---|---|
| Prices, indicators, scores | ✅ Real market data (yfinance daily + 15-min; IBKR feed at night, ~15-min delayed on free tier) |
| BUY/SELL suggestions | ✅ Real rule-based signals — every one traceable to indicator conditions. NOT AI guesses |
| AI morning brief | ✅ Real Gemini analysis of real data — context, not trade instructions |
| Money | ❌ 100% virtual until go-live gate passes |
| Performance tracking | ✅ Real record of the virtual trades — the evidence base |

**Suggestions are real signals but unproven predictions — that's what the
60-day gate measures.** Quotes upgrade to true real-time with IBKR's
US data bundle (~US$4.50/mo) — decide after the validation period.

---

## 9. Troubleshooting

| Problem | Fix |
|---|---|
| Dashboard 404 | Go to https://terrence314.github.io/stock-monitoring-tool/ directly (old cache-bust bug, fixed) |
| Dashboard stale | Hard refresh Cmd+Shift+R, or tap ↻ button |
| No 引擎上線 message at 9:25pm | Gateway not open/logged in. Check `outputs/stream.err.log` |
| "Cannot reach IB Gateway" | Open Gateway, login paper mode, retry |
| Gateway login fails | VPN off, Region Asia/Pacific, username tcpaper314 |
| No Telegram at all | Check `config/secrets.json` values; test: `python3 src/ibkr_connect_test.py` |
| Badge/streak missing on dashboard | Fixed (price_refresh preserves badges) — hard refresh |
| Ticker page missing live chart | Page regenerates on daily run only; wait for next morning |

---

## 10. File Map (where things live)

```
stock-monitoring-tool/
├── src/
│   ├── main.py                 ← daily pipeline entry
│   ├── price_refresh.py        ← 15-min refresh entry
│   ├── ibkr_stream_alerts.py   ← night stream engine
│   ├── ibkr_connect_test.py    ← gateway diagnostic
│   ├── technical_analysis.py   ← scoring + all indicators
│   ├── report_generator.py     ← dashboard (incl. Action Box)
│   ├── stock_detail.py         ← per-ticker pages
│   ├── paper_trading.py        ← virtual trading sim
│   ├── tier2_manager.py        ← top-50 list + badges
│   └── …
├── config/
│   ├── config.json             ← watchlist, settings (public)
│   └── secrets.json            ← Telegram creds (gitignored)
├── outputs/                    ← generated site + state files
└── docs/
    ├── user-guide.md           ← this file
    └── day-trading-runbook.md  ← one-page night workflow
```

---

## 11. Glossary (quick)

- **多頭排列** — bullish MA stack: price > MA5 > MA20 > MA60
- **均線 MA** — average cost over N days; trend position tool, not buy signal
- **RSI** — momentum 0-100; >70 overbought, <30 oversold
- **MACD 金叉** — momentum turning up (golden cross)
- **BB squeeze ⚡** — volatility compressed, big move loading
- **KD 金叉 🎯** — bottom reversal signal in oversold zone
- **假跌破 (洗盤)** — fake breakdown that recovers fast = shakeout, often opportunity
- **真轉弱** — breaks MA20, can't reclaim, volume dies = real weakness
- **RelVol / Vol×** — today's volume vs 20-day average
- **Tier 2** — top 50 scorers from the 250-ticker universe
- **NEW / 🔥Xd / ↩RETURN** — first day on list / X-day streak / returned after dropping off
