"""signal_validator.py — Loop 2: Pre-Telegram BUY Signal Validator

Runs 3 checks before any BUY alert fires to Telegram.
If a check fails, the BUY is blocked and the reason is logged.

  Check 1 — Duplicate position guard
            Ticker already has an open position in paper_portfolio.json?
            (safety net — _build_action_box already filters these, but
            portfolio state can change between action_box build and Telegram send)

  Check 2 — Gate conditions re-check
            Verdict must contain GO / BREAKOUT ↑ / BREAKOUT 🚀 AND score >= 70.
            (double-checks action_box entries against live stock_results)

  Check 3 — Risk day gate
            (a) Earnings within ±1 trading day for this ticker → block
            (b) FOMC decision day today or tomorrow → warn (not block)
            (c) Options expiry Friday (monthly) → add caution tag

Usage in main.py:
    from signal_validator import validate_signals
    _ab, _blocked = validate_signals(_ab, stock_results, portfolio_path)

Returns:
    (validated_action_box, blocked_list)
    validated_action_box: same structure as input, with blocked BUYs removed
    blocked_list: list of dicts — {ticker, reason, original_buy}
"""

import os
import json
import logging
from datetime import date, datetime, timedelta

import yfinance as yf

logger = logging.getLogger(__name__)

# ── Config ─────────────────────────────────────────────────────────────────────

PORTFOLIO_FILE   = os.path.join("outputs", "paper_portfolio.json")
VALIDATOR_LOG    = os.path.join("outputs", "signal_validator_log.json")
BUY_THRESHOLD    = 70
EARNINGS_WINDOW  = 1   # trading days; block if earnings within this many days

# 2026 FOMC decision dates (day 2 of each 2-day meeting — when rate decision drops).
# Source: federalreserve.gov/monetarypolicy/fomccalendars.htm
# Update this list each January when the Fed publishes the new year's schedule.
# Decision days (2nd day of each meeting), verified against
# https://www.federalreserve.gov/monetarypolicy/fomccalendars.htm on 2026-07-04.
# Update every January.
FOMC_DATES_2026 = {
    date(2026, 1, 28),
    date(2026, 3, 18),
    date(2026, 4, 29),
    date(2026, 6, 17),
    date(2026, 7, 29),
    date(2026, 9, 16),
    date(2026, 10, 28),
    date(2026, 12, 9),
}


# ── Helpers ────────────────────────────────────────────────────────────────────

def _load_open_tickers(portfolio_path: str = PORTFOLIO_FILE) -> set:
    """Return set of tickers with status='open' in the paper portfolio."""
    try:
        with open(portfolio_path, encoding="utf-8") as f:
            trades = json.load(f).get("trades", [])
        # t.get(): one malformed row must not raise and wipe the guard for all tickers
        return {t.get("ticker") for t in trades
                if t.get("status") == "open" and t.get("ticker")}
    except (FileNotFoundError, json.JSONDecodeError, AttributeError):
        return set()


def _get_earnings_date(ticker: str) -> date | None:
    """Fetch next earnings date via yfinance. Returns None if unavailable."""
    try:
        cal = yf.Ticker(ticker).calendar
        if cal is None:
            return None
        # yfinance returns a dict or DataFrame depending on version
        if isinstance(cal, dict):
            ed = cal.get("Earnings Date")
            if ed is None:
                return None
            # Can be a list or a single value
            if isinstance(ed, (list, tuple)):
                ed = ed[0]
            if hasattr(ed, "date"):
                return ed.date()
            if isinstance(ed, str):
                return datetime.strptime(ed[:10], "%Y-%m-%d").date()
        # DataFrame case (older yfinance)
        if hasattr(cal, "loc"):
            row = cal.T.get("Earnings Date")
            if row is not None:
                val = row.iloc[0] if hasattr(row, "iloc") else row
                if hasattr(val, "date"):
                    return val.date()
    except Exception as e:
        logger.debug(f"  [validator] earnings fetch failed for {ticker}: {e}")
    return None


def _trading_day_delta(today: date, target: date) -> int:
    """Signed count of weekdays (Mon-Fri) from today to target.
    Positive = target in the future. US market holidays not modeled —
    a holiday counts as a trading day, which errs on the blocking side."""
    if target == today:
        return 0
    step = 1 if target > today else -1
    d, n = today, 0
    while d != target:
        d += timedelta(days=step)
        if d.weekday() < 5:
            n += step
    return n


def _is_earnings_risk(ticker: str, today: date, window: int = EARNINGS_WINDOW) -> tuple[bool, str]:
    """Return (is_risky, reason_string)."""
    ed = _get_earnings_date(ticker)
    if ed is None:
        return False, ""
    # Trading-day distance, not calendar days: Friday earnings before a Monday
    # run is 1 trading day away and must block (calendar delta of 3 missed it).
    delta = _trading_day_delta(today, ed)
    if abs(delta) <= window:
        direction = "today" if delta == 0 else (f"in {delta} trading day(s)" if delta > 0 else f"{abs(delta)} trading day(s) ago")
        return True, f"earnings {direction} ({ed})"
    return False, ""


def _is_fomc_risk(today: date) -> tuple[bool, str]:
    """Return (is_risky, reason_string). Warns on FOMC day and day before."""
    tomorrow = today + timedelta(days=1)
    if today in FOMC_DATES_2026:
        return True, f"FOMC decision day ({today})"
    if tomorrow in FOMC_DATES_2026:
        return True, f"FOMC tomorrow ({tomorrow}) — elevated vol risk"
    return False, ""


def _is_options_expiry(today: date) -> bool:
    """True if today is monthly options expiry (3rd Friday of the month)."""
    if today.weekday() != 4:   # not a Friday
        return False
    # 3rd Friday: day is between 15 and 21
    return 15 <= today.day <= 21


def _check_gate_conditions(buy: dict, stock_results: list) -> tuple[bool, str]:
    """Re-verify verdict + score against live stock_results."""
    ticker = buy.get("ticker", "")
    stock = next((s for s in stock_results if s.get("ticker") == ticker), None)
    if stock is None:
        return False, "ticker not found in stock_results"
    score = stock.get("score", 0)
    label = (stock.get("entry_verdict") or {}).get("label", "")
    if score < BUY_THRESHOLD:
        return False, f"score {score} < {BUY_THRESHOLD}"
    if not ("GO" in label or "BREAKOUT ↑" in label or "BREAKOUT 🚀" in label):
        return False, f"verdict '{label}' not GO/BREAKOUT ↑"
    return True, ""


# ── Main validator ─────────────────────────────────────────────────────────────

def validate_signals(
    action_box: dict,
    stock_results: list,
    portfolio_path: str = PORTFOLIO_FILE,
) -> tuple[dict, list]:
    """
    Validate each BUY in action_box against 3 checks.
    Returns (updated_action_box, blocked_list).
    """
    today = date.today()
    open_tickers = _load_open_tickers(portfolio_path)
    fomc_risk, fomc_reason = _is_fomc_risk(today)
    opex = _is_options_expiry(today)

    validated_buys = []
    blocked = []
    caution_tags = []

    # Global caution flags (don't block, just tag the message)
    if fomc_risk:
        caution_tags.append(f"⚠️ {fomc_reason}")
    if opex:
        caution_tags.append("⚠️ Monthly options expiry — expect elevated vol")

    for buy in action_box.get("buys", []):
        ticker = buy.get("ticker", "")
        block_reasons = []

        # Check 1: duplicate position guard
        if ticker in open_tickers:
            block_reasons.append(f"already in open position")

        # Check 2: gate conditions re-check
        gate_ok, gate_reason = _check_gate_conditions(buy, stock_results)
        if not gate_ok:
            block_reasons.append(f"gate fail — {gate_reason}")

        # Check 3a: earnings risk
        earn_risk, earn_reason = _is_earnings_risk(ticker, today)
        if earn_risk:
            block_reasons.append(earn_reason)

        if block_reasons:
            reason_str = " | ".join(block_reasons)
            blocked.append({
                "ticker":       ticker,
                "reason":       reason_str,
                "original_buy": buy,
                "blocked_at":   datetime.now().strftime("%Y-%m-%d %H:%M"),
            })
            logger.info(f"  [validator] ❌ BLOCKED {ticker}: {reason_str}")
        else:
            # Pass — annotate with any global caution tags
            if caution_tags:
                buy = {**buy, "caution": " | ".join(caution_tags)}
            validated_buys.append(buy)
            logger.info(f"  [validator] ✅ PASSED  {ticker}")

    # Rebuild action_box with only validated buys
    updated_box = {
        **action_box,
        "buys":       validated_buys,
        "no_action":  not validated_buys and not action_box.get("sells"),
        "validator":  {
            "ran_at":       datetime.now().strftime("%Y-%m-%d %H:%M"),
            "passed":       len(validated_buys),
            "blocked":      len(blocked),
            "blocked_list": [{"ticker": b["ticker"], "reason": b["reason"]} for b in blocked],
            "caution_tags": caution_tags,
        },
    }

    # Persist log
    _append_validator_log(today.isoformat(), validated_buys, blocked, caution_tags)

    return updated_box, blocked


# ── Logging ────────────────────────────────────────────────────────────────────

def _append_validator_log(date_str: str, passed: list, blocked: list, cautions: list) -> None:
    """Append today's validation run to outputs/signal_validator_log.json."""
    try:
        try:
            with open(VALIDATOR_LOG, encoding="utf-8") as f:
                log = json.load(f)
        except (FileNotFoundError, json.JSONDecodeError):
            log = []

        log.append({
            "date":     date_str,
            "ran_at":   datetime.now().strftime("%Y-%m-%d %H:%M"),
            "passed":   [b.get("ticker") for b in passed],
            "blocked":  [{"ticker": b["ticker"], "reason": b["reason"]} for b in blocked],
            "cautions": cautions,
        })

        # Keep last 60 entries
        log = log[-60:]
        os.makedirs(os.path.dirname(VALIDATOR_LOG) or ".", exist_ok=True)
        # Atomic write: tmp + os.replace so a crash mid-write can't truncate the log
        tmp_path = VALIDATOR_LOG + ".tmp"
        with open(tmp_path, "w", encoding="utf-8") as f:
            json.dump(log, f, ensure_ascii=False, indent=2)
        os.replace(tmp_path, VALIDATOR_LOG)
    except Exception as e:
        logger.warning(f"  [validator] log write failed: {e}")
