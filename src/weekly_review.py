"""weekly_review.py — Weekly paper trading performance review.

Runs every Sunday. Reads paper_portfolio.json, computes key metrics,
projects Day 60 trajectory, sends Telegram summary, saves JSON report.

Usage:
    python3 src/weekly_review.py

ALERTS ONLY — this module never places orders.
"""
import json
import os
import sys
from datetime import datetime, date

PORTFOLIO_FILE   = os.path.join("outputs", "paper_portfolio.json")
REVIEW_FILE      = os.path.join("outputs", "weekly_review.json")
CONFIG_FILE      = os.path.join("config", "config.json")
SECRETS_FILE     = os.path.join("config", "secrets.json")

# Validation gate thresholds (must match active-projects.md go-live gate)
GATE_WIN_RATE    = 50.0   # %
GATE_PROFIT_FACTOR = 1.3


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _profit_factor(closed: list) -> float:
    gross_win  = sum(t["pnl"] for t in closed if (t.get("pnl") or 0) > 0)
    gross_loss = sum(abs(t["pnl"]) for t in closed if (t.get("pnl") or 0) < 0)
    if gross_loss == 0:
        return gross_win if gross_win > 0 else 0.0
    return round(gross_win / gross_loss, 3)


def _avg_hold(closed: list) -> float:
    holds = []
    for t in closed:
        if t.get("signal_date") and t.get("exit_date"):
            try:
                d1 = datetime.strptime(t["signal_date"], "%Y-%m-%d").date()
                d2 = datetime.strptime(t["exit_date"],   "%Y-%m-%d").date()
                holds.append((d2 - d1).days)
            except ValueError:
                pass
    return round(sum(holds) / len(holds), 1) if holds else 0.0


def _exit_breakdown(closed: list) -> dict:
    reasons = {}
    for t in closed:
        r = t.get("exit_reason") or "unknown"
        reasons[r] = reasons.get(r, 0) + 1
    return reasons


def _paper_start_date(trades: list) -> str | None:
    valid = [t["signal_date"] for t in trades if t.get("signal_date")]
    return min(valid) if valid else None


def _days_into_validation(start_str: str) -> int:
    try:
        start = datetime.strptime(start_str, "%Y-%m-%d").date()
        return (date.today() - start).days
    except ValueError:
        return 0


def _project_day60(closed: list, days_elapsed: int) -> dict:
    """Linear projection of win rate and profit factor at Day 60."""
    if days_elapsed <= 0 or not closed:
        return {"win_rate": None, "profit_factor": None, "trades": None}
    rate = len(closed) / days_elapsed       # trades per day
    projected_count = round(rate * 60)
    # Assume same win rate / PF holds — directional only
    wins = [t for t in closed if (t.get("pnl") or 0) > 0]
    wr   = len(wins) / len(closed) * 100
    pf   = _profit_factor(closed)
    return {
        "win_rate":      round(wr, 1),
        "profit_factor": pf,
        "trades":        projected_count,
    }


def _go_live_status(win_rate: float, profit_factor: float, days: int) -> str:
    gate_met = win_rate >= GATE_WIN_RATE or profit_factor >= GATE_PROFIT_FACTOR
    if days < 14:
        return "🕐 Too early — need more data"
    if gate_met:
        return "✅ On track for go-live"
    if win_rate >= GATE_WIN_RATE - 5 or profit_factor >= GATE_PROFIT_FACTOR - 0.1:
        return "⚠️ Watch — borderline"
    return "🔴 Off track — review strategy"


def build_review() -> dict:
    portfolio = _load(PORTFOLIO_FILE, {})
    all_trades = portfolio.get("trades", [])
    closed     = [t for t in all_trades if t.get("status") == "closed"
                  and "force_close" not in (t.get("exit_reason") or "")]

    start_date   = _paper_start_date(all_trades)
    days_elapsed = _days_into_validation(start_date) if start_date else 0

    wins     = [t for t in closed if (t.get("pnl") or 0) > 0]
    losses   = [t for t in closed if (t.get("pnl") or 0) <= 0]
    win_rate = round(len(wins) / len(closed) * 100, 1) if closed else 0.0
    pf       = _profit_factor(closed)
    total_pnl = round(sum(t.get("pnl") or 0 for t in closed), 2)
    avg_win   = round(sum(t.get("pnl") or 0 for t in wins) / len(wins), 2) if wins else 0
    avg_loss  = round(sum(t.get("pnl") or 0 for t in losses) / len(losses), 2) if losses else 0
    avg_hold  = _avg_hold(closed)
    exits     = _exit_breakdown(closed)
    projected = _project_day60(closed, days_elapsed)
    status    = _go_live_status(win_rate, pf, days_elapsed)

    return {
        "generated_at":    datetime.now().strftime("%Y-%m-%d %H:%M"),
        "paper_start":     start_date,
        "days_elapsed":    days_elapsed,
        "days_remaining":  max(0, 60 - days_elapsed),
        "total_trades":    len(all_trades),
        "closed_trades":   len(closed),
        "open_trades":     len([t for t in all_trades if t.get("status") == "open"]),
        "win_rate":        win_rate,
        "profit_factor":   pf,
        "total_pnl":       total_pnl,
        "avg_win":         avg_win,
        "avg_loss":        avg_loss,
        "avg_hold_days":   avg_hold,
        "exit_breakdown":  exits,
        "projected_day60": projected,
        "go_live_status":  status,
    }


def format_telegram(r: dict) -> str:
    day  = r["days_elapsed"]
    left = r["days_remaining"]
    wr   = r["win_rate"]
    pf   = r["profit_factor"]
    pnl  = r["total_pnl"]
    n    = r["closed_trades"]
    proj = r["projected_day60"]
    exits = r["exit_breakdown"]
    status = r["go_live_status"]

    exit_lines = "\n".join(
        f"  • {k}: {v}" for k, v in sorted(exits.items(), key=lambda x: -x[1])
    ) or "  • none yet"

    proj_line = ""
    if proj.get("win_rate") is not None:
        proj_line = (
            f"\n📈 <b>Day 60 Projection</b>\n"
            f"  Win rate: {proj['win_rate']:.1f}% · PF: {proj['profit_factor']:.2f}"
        )

    pnl_str = f"+${pnl:.2f}" if pnl >= 0 else f"-${abs(pnl):.2f}"

    return (
        f"📊 <b>Weekly Review — Day {day}/60</b>\n"
        f"({left} days to go-live gate)\n\n"
        f"<b>Performance</b>\n"
        f"  Closed trades: {n}\n"
        f"  Win rate: <b>{wr:.1f}%</b> (gate: ≥50%)\n"
        f"  Profit factor: <b>{pf:.2f}x</b> (gate: ≥1.3)\n"
        f"  Total P&L: {pnl_str}\n\n"
        f"<b>Exit breakdown</b>\n{exit_lines}"
        f"{proj_line}\n\n"
        f"<b>Go-live status</b>: {status}"
    )


def main():
    # Load secrets → env vars
    secrets = _load(SECRETS_FILE, {})
    bot_token = os.getenv("TELEGRAM_BOT_TOKEN") or secrets.get("telegram_bot_token", "")
    chat_id   = os.getenv("TELEGRAM_CHAT_ID")   or secrets.get("telegram_chat_id", "")

    r = build_review()

    # Save JSON report
    os.makedirs("outputs", exist_ok=True)
    with open(REVIEW_FILE, "w", encoding="utf-8") as f:
        json.dump(r, f, indent=2, ensure_ascii=False)
    print(f"✅ Weekly review saved → {REVIEW_FILE}")

    # Print summary
    print(f"\nDay {r['days_elapsed']}/60 | WR {r['win_rate']:.1f}% | PF {r['profit_factor']:.2f}x | PnL ${r['total_pnl']:.2f}")
    print(f"Status: {r['go_live_status']}")
    print(f"Exits: {r['exit_breakdown']}")

    # Send Telegram
    if bot_token and chat_id:
        msg = format_telegram(r)
        sys.path.insert(0, os.path.join(os.path.dirname(__file__)))
        from notifier import send_telegram
        ok = send_telegram(bot_token, chat_id, msg)
        print("✅ Telegram sent" if ok else "❌ Telegram failed")
    else:
        print("⚠️ No Telegram credentials — skipping send")
        print("\n" + format_telegram(r))


if __name__ == "__main__":
    main()
