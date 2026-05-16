import requests


def send_telegram(bot_token: str, chat_id: str, message: str) -> bool:
    url = f"https://api.telegram.org/bot{bot_token}/sendMessage"
    payload = {"chat_id": chat_id, "text": message, "parse_mode": "HTML"}
    try:
        r = requests.post(url, json=payload, timeout=15)
        return r.json().get("ok", False)
    except Exception as e:
        print(f"  [notifier] Telegram error: {e}")
        return False


def format_daily_message(date: str, morning_brief: str, stocks: list, report_url: str = "") -> str:
    sorted_stocks = sorted(stocks, key=lambda x: x["score"], reverse=True)
    top = sorted_stocks[:5]

    lines = [
        "📊 <b>AI 股票監控｜每日報告</b>",
        f"📅 {date}",
        "",
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
        "<b>🏆 今日 Top 5 信號</b>",
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
