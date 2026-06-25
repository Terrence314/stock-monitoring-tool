import requests
from datetime import datetime


def send_telegram(bot_token: str, chat_id: str, message: str) -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=15)
        return r.json().get("ok", False)
    except Exception as e:
        print(f"  [notifier] Telegram error: {e}")
        return False


def send_health_alert(bot_token: str, chat_id: str, issues: list) -> bool:
    """Send a pipeline degradation alert when the run is unhealthy."""
    lines = [
        "⚠️ <b>股票監控系統｜健康警告</b>",
        f"🕐 {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "",
        "今日報告品質可能受影響，請檢查以下問題：",
        "",
    ]
    for i, issue in enumerate(issues, 1):
        lines.append(f"{i}. {issue}")
    lines += [
        "",
        "👉 請前往 GitHub Actions 查看完整日誌。",
    ]
    return send_telegram(bot_token, chat_id, "\n".join(lines))


def send_exit_alert(bot_token: str, chat_id: str, alerts: list, report_url: str = "",
                    held_tickers: set | None = None) -> bool:
    """Send score-drop exit trigger alerts during price refresh.

    Each alert dict must contain: ticker, prev_score, curr_score, drop,
    price, price_change_pct, strength, prev_strength.
    held_tickers: open paper position tickers — alerts on held positions get
    the same action wording the dashboard Action Box uses.
    """
    if not alerts:
        return True
    held_tickers = held_tickers or set()

    lines = [
        "🚨 <b>Exit Alert｜信號轉弱</b>",
        f"🕐 {datetime.now().strftime('%H:%M HKT')}",
        "",
    ]

    for a in alerts:
        chg  = a.get("price_change_pct", 0)
        arrow = "▲" if chg >= 0 else "▼"
        is_held = a["ticker"] in held_tickers
        lines += [
            f"⚠️ <b>{a['ticker']}</b>  ${a['price']:.2f}  {arrow}{abs(chg):.2f}%",
            f"   信號：{a['prev_score']} → <b>{a['curr_score']}</b>  （↓{a['drop']} pts）",
            f"   {a.get('prev_strength', '')} → {a.get('strength', '')}",
            ("   🔴 你有持倉 — 持倉轉弱，考慮平倉" if is_held
             else "   ℹ️ 冇持倉 — 觀察名單轉弱，毋須行動"),
            "",
        ]

    lines += [
        "━━━━━━━━━━━━━━━━━",
    ]
    if report_url:
        lines.append(f"📄 <a href=\"{report_url}\">查看報告</a>")
    lines.append("\n⚠️ 僅供參考，不構成投資建議")

    return send_telegram(bot_token, chat_id, "\n".join(lines))


def format_daily_message(date: str, morning_brief: str, stocks: list, report_url: str = "",
                         action_box: dict | None = None) -> str:
    sorted_stocks = sorted(stocks, key=lambda x: x["score"], reverse=True)
    top = sorted_stocks[:5]

    lines = [
        "📊 <b>AI 股票監控｜每日報告</b>",
        f"📅 {date}",
        "",
    ]

    # ── 今日行動 — identical to the dashboard Action Box (one source of truth) ──
    if action_box:
        lines += ["━━━━━━━━━━━━━━━━━", "<b>⚡ 今日行動</b>"]
        tripped = action_box.get("breaker_trip")
        if tripped:
            lines.append(f"🛑 斷路器已觸發（本月 {action_box.get('breaker_pct')}%）— "
                         "真錢唔開新倉，下面 BUY 係 📝 紙上練習單")
        buys  = action_box.get("buys", [])
        sells = action_box.get("sells", [])
        for b in buys:
            tag = "📝 " if tripped else ""
            lines.append(
                f"{tag}🟢 <b>BUY {b['ticker']}</b> 買入 ≤ ${b.get('price', 0):.2f}"
            )
            if b.get("stop"):
                lines.append(
                    f"   止損 ${b['stop']:.2f} (−8%) · 目標 ${b.get('target', 0):.2f} (+12%)"
                    f" · 期限 {b.get('expiry', '')}（10 交易日）· $1,000"
                )
        for s in sells:
            lines.append(f"🔴 <b>SELL {s['ticker']}</b> — {s.get('why', '')}，持倉轉弱，考慮平倉")
        if not buys and not sells:
            lines.append("✅ 今日無行動 — 無合資格入場，持倉無賣出訊號")
        lines.append("")

    lines += [
        "━━━━━━━━━━━━━━━━━",
        "<b>🌅 早盤市場簡報</b>",
    ]

    # Truncate brief to the 【I】 section or first 400 chars
    brief_short = morning_brief
    if "【I" in morning_brief:
        idx = morning_brief.index("【I")
        brief_short = morning_brief[idx:idx + 300]
    elif len(morning_brief) > 400:
        brief_short = morning_brief[:400] + "…"
    lines.append(brief_short)

    lines += [
        "",
        "━━━━━━━━━━━━━━━━━",
        "<b>📊 信號強度 Top 5</b>（趨勢排名，非買入指令 — 買咩睇上面「今日行動」）",
        "",
    ]

    for s in top:
        sc = s["score"]
        emoji = "🔥" if sc >= 80 else "📈" if sc >= 60 else "⚖️" if sc >= 40 else "📉"
        chg = s.get("price_change_pct", 0)
        arrow = "▲" if chg >= 0 else "▼"
        lines.append(
            f"{emoji} <b>{s['ticker']}</b>  ${s['price']:.2f}  {arrow}{abs(chg):.2f}%"
            f"  ｜  信號 <b>{sc}/100</b>  {s['strength']}"
        )
        if s.get("ai_view"):
            short_view = s["ai_view"][:80] + "…" if len(s["ai_view"]) > 80 else s["ai_view"]
            lines.append(f"   <i>{short_view}</i>")
        # IBKR position annotation
        _pos = s.get("ibkr_position")
        if _pos:
            _pnl = _pos.get("unrealized_pnl", 0)
            _pnl_str = f"+${_pnl:.2f}" if _pnl >= 0 else f"-${abs(_pnl):.2f}"
            lines.append(f"   📦 持倉 ×{_pos.get('qty')} · 均${_pos.get('avg_cost', 0):.2f} · 浮盈 {_pnl_str}")
        lines.append("")

    if report_url:
        lines += [
            "━━━━━━━━━━━━━━━━━",
            f"📄 <a href=\"{report_url}\">查看完整報告</a>",
        ]

    lines += [
        "",
        "⚠️ 僅供參考，不構成投資建議",
    ]

    return "\n".join(lines)


def format_ibkr_pnl_alert(positions: list, stock_results: list,
                           daily_loss_threshold: float = -20.0,
                           drawdown_pct_threshold: float = -10.0) -> str | None:
    """Build Telegram alert for IBKR positions with P&L warnings or sell signals.

    Returns None if nothing worth alerting.
    ALERTS ONLY — never places orders.
    """
    sig_map = {s["ticker"]: s for s in stock_results}
    lines = []

    for p in positions:
        ticker   = p.get("ticker", "")
        qty      = p.get("qty", 0)
        avg      = p.get("avg_cost", 0)
        price    = p.get("market_price", 0)
        upnl     = p.get("unrealized_pnl", 0)
        dpnl     = p.get("daily_pnl", 0)
        mktval   = p.get("market_value", 0)

        alerts = []

        # 1. Daily loss threshold
        if dpnl < daily_loss_threshold:
            alerts.append(f"📉 今日虧損 ${dpnl:.2f}")

        # 2. Unrealized drawdown %
        cost_basis = avg * qty
        if cost_basis > 0:
            drawdown_pct = (upnl / cost_basis) * 100
            if drawdown_pct < drawdown_pct_threshold:
                alerts.append(f"⚠️ 浮虧 {drawdown_pct:.1f}%（成本 ${cost_basis:.2f}）")

        # 3. Sell signal from technical analysis
        sig = sig_map.get(ticker)
        if sig:
            score = sig.get("score", 0)
            sell_sigs = sig.get("sell_signals", [])
            ta_signals = sig.get("signals", [])
            # Check for bearish signals in signal list
            bearish = [s for s in ta_signals if any(w in s for w in ["❌", "🔴", "死叉", "跌穿", "爆量下跌"])]
            if sell_sigs:
                alerts.append(f"🔴 賣出訊號：{sell_sigs[0][:60]}")
            elif bearish:
                alerts.append(f"⚠️ 偏空信號：{bearish[0][:60]}")
            if score < 30 and qty > 0:
                alerts.append(f"📊 信號評分偏低 {score}/100 — 持倉需留意")

        if alerts:
            pnl_str = f"+${upnl:.2f}" if upnl >= 0 else f"-${abs(upnl):.2f}"
            dpnl_str = f"+${dpnl:.2f}" if dpnl >= 0 else f"-${abs(dpnl):.2f}"
            lines.append(
                f"📦 <b>{ticker}</b>  ×{qty} · 均${avg:.2f} · 現${price:.2f}"
                f"  ｜  浮盈 <b>{pnl_str}</b>  今日 {dpnl_str}"
            )
            for a in alerts:
                lines.append(f"   {a}")
            lines.append("")

    if not lines:
        return None

    header = [
        "🏦 <b>IBKR 持倉預警</b>",
        "",
    ]
    footer = ["⚠️ 僅供參考，不構成投資建議"]
    return "\n".join(header + lines + footer)
