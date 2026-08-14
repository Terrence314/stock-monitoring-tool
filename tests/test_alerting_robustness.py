"""Alert-delivery and data-integrity fixes.

A. Telegram runs parse_mode=HTML. A single unescaped `<` or `&` in
   Gemini-generated text makes the API reject the WHOLE message with 400, so
   one stray character silently dropped the entire day's alert.
B. send_telegram gave up after one attempt with only a print to a CI log.
C. IBKR returns +/-DBL_MAX when a field is unavailable. dailyPnL of
   -1.7976931348623157e+308 was stored as-is and compared against the -$20
   daily-loss threshold, firing a catastrophic-looking false alert.
D. The circuit breaker counted every open position's full lifetime unrealized
   P&L into whatever month happened to be current.
"""

import os
import sys
import json
import tempfile
from datetime import date

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import notifier as nf                                                # noqa: E402
import ibkr_sync                                                     # noqa: E402
import signal_validator as sv                                        # noqa: E402
from report_generator import _build_action_box                       # noqa: E402


# ── A. HTML escaping ──────────────────────────────────────────────────────────

def test_esc_neutralises_html_metacharacters():
    assert nf.esc("a < b & c") == "a &lt; b &amp; c"


def test_esc_truncates_before_escaping():
    """Cutting after escaping could slice an entity like &amp; in half."""
    out = nf.esc("&" * 50, limit=10)
    assert out.endswith("…")
    assert "&amp" in out and out.count("&amp;") == 10


def _stock(**kw):
    base = {"ticker": "AAA", "score": 80, "price": 10.0, "strength": "強",
            "price_change_pct": 1.0}
    base.update(kw)
    return base


def test_ai_view_cannot_break_the_message():
    msg = nf.format_daily_message(
        "2026-08-02", "brief",
        [_stock(ai_view="EPS <consensus> & margin risk")],
    )
    assert "<consensus>" not in msg
    assert "&lt;consensus&gt;" in msg


def test_morning_brief_is_escaped():
    msg = nf.format_daily_message("2026-08-02", "risk <b>rising</b> & broad", [_stock()])
    assert "risk &lt;b&gt;rising&lt;/b&gt; &amp; broad" in msg


def test_message_tags_stay_balanced_with_hostile_input():
    msg = nf.format_daily_message(
        "2026-08-02", "<i>unclosed", [_stock(strength="a<b", ai_view="x & y")],
    )
    assert msg.count("<b>") == msg.count("</b>")
    assert msg.count("<i>") == msg.count("</i>")


# ── B. Retry ──────────────────────────────────────────────────────────────────

class _Resp:
    def __init__(self, ok, status=200, desc=""):
        self._ok, self.status_code, self._desc = ok, status, desc

    def json(self):
        return {"ok": self._ok, "description": self._desc}


def test_send_retries_then_succeeds(monkeypatch):
    calls = []

    def fake_post(url, json=None, timeout=None):
        calls.append(json)
        return _Resp(len(calls) >= 2)

    monkeypatch.setattr(nf.requests, "post", fake_post)
    monkeypatch.setattr(nf.time, "sleep", lambda *_: None)

    assert nf.send_telegram("t", "c", "hi") is True
    assert len(calls) == 2


def test_400_falls_back_to_plain_text(monkeypatch):
    seen = []

    def fake_post(url, json=None, timeout=None):
        seen.append(json)
        return _Resp(False, 400, "can't parse entities")

    monkeypatch.setattr(nf.requests, "post", fake_post)
    monkeypatch.setattr(nf.time, "sleep", lambda *_: None)

    nf.send_telegram("t", "c", "hi")
    assert "parse_mode" in seen[0]
    assert "parse_mode" not in seen[-1], "never retried without HTML"


# ── C. IBKR sentinel ──────────────────────────────────────────────────────────

def test_dbl_max_sentinel_becomes_none():
    assert ibkr_sync._num(-1.7976931348623157e+308) is None
    assert ibkr_sync._num(1.7976931348623157e+308) is None


def test_real_values_survive():
    assert ibkr_sync._num(-12.345) == -12.35
    assert ibkr_sync._num(None) is None


def test_unknown_daily_pnl_does_not_fire_a_loss_alert():
    out = nf.format_ibkr_pnl_alert(
        [{"ticker": "AAA", "qty": 10, "avg_cost": 100.0, "market_price": 101.0,
          "unrealized_pnl": 10.0, "daily_pnl": None, "market_value": 1010.0}],
        [], daily_loss_threshold=-20.0,
    )
    assert out is None, "unknown daily P&L must not read as a loss"


def test_short_position_drawdown_keeps_its_sign():
    """Negative qty used to flip cost_basis and report a losing short as a gain."""
    out = nf.format_ibkr_pnl_alert(
        [{"ticker": "AAA", "qty": -10, "avg_cost": 100.0, "market_price": 130.0,
          "unrealized_pnl": -300.0, "daily_pnl": -5.0, "market_value": -1300.0}],
        [], drawdown_pct_threshold=-10.0,
    )
    assert out is not None and "浮虧" in out


# ── D. Breaker month attribution ──────────────────────────────────────────────

def _gate_dir(trades):
    d = tempfile.mkdtemp()
    with open(os.path.join(d, "paper_portfolio.json"), "w") as f:
        json.dump({"trades": trades}, f)
    return d


def test_open_position_from_a_previous_month_is_excluded():
    stale = {"ticker": "OLD", "status": "open", "signal_date": "2026-05-02",
             "entry_price": 100.0, "current_price": 40.0, "shares": 10.0,
             "notional": 1000}

    box = _build_action_box([], _gate_dir([stale]))

    assert box["breaker_pct"] == 0.0
    assert box["breaker_usd"] == 0.0


def test_breaker_measures_the_account_not_turnover():
    """The denominator moved from capital DEPLOYED to account equity.

    Dividing by turnover made the breaker weaker the more you traded — 50
    trades x $1,000 losing $2,400 read as -4.8% and did not trip, while the
    same loss is a -52% drawdown on a ~USD 4,650 account. A circuit breaker
    has to measure the account it protects.
    """
    this_month = date.today().strftime("%Y-%m")
    t = {"ticker": "AAA", "status": "closed", "signal_date": this_month + "-02",
         "exit_date": this_month + "-05", "pnl": -80.0, "notional": 1000}

    box = _build_action_box([], _gate_dir([t]))

    assert box["breaker_usd"] == -80.0
    assert box["breaker_equity"] > 0
    assert box["breaker_basis"] in ("ibkr", "fallback")
    assert box["breaker_pct"] == pytest.approx(-80.0 / box["breaker_equity"] * 100, abs=0.01)


def test_breaker_does_not_weaken_as_turnover_grows():
    """Same dollar loss must give the same percentage regardless of how many
    trades produced it — the exact property turnover-weighting destroyed."""
    this_month = date.today().strftime("%Y-%m")

    def _loss_over(n_trades):
        per = -240.0 / n_trades
        rows = [{"ticker": f"T{i}", "status": "closed",
                 "signal_date": this_month + "-02", "exit_date": this_month + "-05",
                 "pnl": per, "notional": 1000} for i in range(n_trades)]
        return _build_action_box([], _gate_dir(rows))["breaker_pct"]

    assert _loss_over(1) == pytest.approx(_loss_over(12), abs=0.01)


# ── FOMC table expiry ─────────────────────────────────────────────────────────

def test_uncovered_year_warns_instead_of_silently_passing():
    risky, reason = sv._is_fomc_risk(date(2027, 3, 17))
    assert risky is True
    assert "2027" in reason


def test_covered_year_still_evaluates_normally():
    known = sorted(sv.FOMC_DATES_2026)[0]
    assert sv._is_fomc_risk(known)[0] is True
    assert sv._is_fomc_risk(date(2026, 2, 10))[0] is False
