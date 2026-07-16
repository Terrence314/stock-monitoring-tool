"""Tests for validator Check 4 — AI bull/bear Review + Verdict (2026-07-17).

Ported from the seb.ai trading-workflow Review/Verdict stages: before a BUY
alert fires, the model must build the strongest bull case AND bear case from
the day's data and return APPROVED / NEEDS_REVIEW / REJECTED. REJECTED blocks
the alert; NEEDS_REVIEW tags it; API failure fails safe (alert still fires,
tagged as unreviewed).

Run: python3 tests/test_ai_review.py
No pytest dependency — plain asserts, exits non-zero on failure.
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import signal_validator as sv


STOCK = {
    "ticker": "TEST", "score": 85, "price": 100.0, "rsi": 62, "macd": 1.2,
    "entry_verdict": {"label": "GO ✅", "reason": "trend up"},
    "signals": ["MA5 > MA20", "vol 1.8x"],
}
BUY = {"ticker": "TEST", "price": 100.0, "score": 85,
       "reason": "Score 85", "stop": 92.0, "target": 112.0}


def test_rejected_verdict_blocks():
    fake = lambda prompt: "多頭理據…\n空頭理據…\nVERDICT: REJECTED"
    verdict, summary = sv._ai_review(BUY, STOCK, fake)
    assert verdict == "REJECTED", f"got {verdict}"


def test_approved_verdict_passes():
    fake = lambda prompt: "分析內容\nVERDICT: APPROVED"
    verdict, _ = sv._ai_review(BUY, STOCK, fake)
    assert verdict == "APPROVED"


def test_needs_review_with_space_or_underscore():
    for text in ("VERDICT: NEEDS_REVIEW", "VERDICT: NEEDS REVIEW"):
        verdict, _ = sv._ai_review(BUY, STOCK, lambda p, t=text: t)
        assert verdict == "NEEDS_REVIEW", f"got {verdict} for {text!r}"


def test_unparseable_response_fails_safe():
    verdict, _ = sv._ai_review(BUY, STOCK, lambda p: "garbled nonsense")
    assert verdict == "UNAVAILABLE"


def test_api_exception_fails_safe():
    def boom(prompt):
        raise RuntimeError("API down")
    verdict, _ = sv._ai_review(BUY, STOCK, boom)
    assert verdict == "UNAVAILABLE"


def test_validate_signals_blocks_rejected_buy(tmp_dir="/tmp"):
    """End-to-end: REJECTED AI verdict removes the buy from the action box."""
    import tempfile, json
    action_box = {"buys": [dict(BUY)], "sells": [], "no_action": False}
    stock_results = [dict(STOCK)]

    with tempfile.TemporaryDirectory() as td:
        empty_portfolio = os.path.join(td, "pp.json")
        with open(empty_portfolio, "w") as f:
            json.dump({"trades": []}, f)

        orig_earn = sv._get_earnings_date
        sv._get_earnings_date = lambda ticker: None
        orig_log = sv.VALIDATOR_LOG
        sv.VALIDATOR_LOG = os.path.join(td, "log.json")
        try:
            box, blocked = sv.validate_signals(
                action_box, stock_results, portfolio_path=empty_portfolio,
                ai_call=lambda p: "VERDICT: REJECTED",
            )
        finally:
            sv._get_earnings_date = orig_earn
            sv.VALIDATOR_LOG = orig_log

    assert box["buys"] == [], f"rejected buy must be removed, got {box['buys']}"
    assert blocked and "AI review REJECTED" in blocked[0]["reason"], blocked


def test_validate_signals_unreviewed_buy_still_fires():
    """Fail-safe: AI error must NOT block the buy — tag it instead."""
    import tempfile, json
    action_box = {"buys": [dict(BUY)], "sells": [], "no_action": False}
    stock_results = [dict(STOCK)]

    def boom(prompt):
        raise RuntimeError("API down")

    with tempfile.TemporaryDirectory() as td:
        empty_portfolio = os.path.join(td, "pp.json")
        with open(empty_portfolio, "w") as f:
            json.dump({"trades": []}, f)

        orig_earn = sv._get_earnings_date
        sv._get_earnings_date = lambda ticker: None
        orig_log = sv.VALIDATOR_LOG
        sv.VALIDATOR_LOG = os.path.join(td, "log.json")
        try:
            box, blocked = sv.validate_signals(
                action_box, stock_results, portfolio_path=empty_portfolio,
                ai_call=boom,
            )
        finally:
            sv._get_earnings_date = orig_earn
            sv.VALIDATOR_LOG = orig_log

    assert len(box["buys"]) == 1, "AI failure must fail safe (buy passes)"
    assert "AI review unavailable" in box["buys"][0].get("caution", "")


def test_no_ai_call_keeps_legacy_behavior():
    """ai_call=None → checks 1-3 only, no AI fields added."""
    import tempfile, json
    action_box = {"buys": [dict(BUY)], "sells": [], "no_action": False}
    with tempfile.TemporaryDirectory() as td:
        empty_portfolio = os.path.join(td, "pp.json")
        with open(empty_portfolio, "w") as f:
            json.dump({"trades": []}, f)
        orig_earn = sv._get_earnings_date
        sv._get_earnings_date = lambda ticker: None
        orig_log = sv.VALIDATOR_LOG
        sv.VALIDATOR_LOG = os.path.join(td, "log.json")
        try:
            box, blocked = sv.validate_signals(
                action_box, [dict(STOCK)], portfolio_path=empty_portfolio,
            )
        finally:
            sv._get_earnings_date = orig_earn
            sv.VALIDATOR_LOG = orig_log
    assert len(box["buys"]) == 1
    assert "ai_review" not in box["buys"][0]


if __name__ == "__main__":
    fns = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for fn in fns:
        try:
            fn()
            print(f"  ✅ {fn.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"  ❌ {fn.__name__}: {e}")
    print(f"\n{len(fns) - failed}/{len(fns)} passed")
    sys.exit(1 if failed else 0)
