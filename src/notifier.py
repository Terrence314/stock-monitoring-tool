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
