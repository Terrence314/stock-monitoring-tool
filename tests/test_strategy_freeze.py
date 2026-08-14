"""The validation window must stop resetting.

It moved three times in one month — 2026-06-11 → 07-17 → 08-05 → 08-09 — and
every move was individually justified: the risk model really had changed, so
the prior sample really was measuring something else. But each reset returns
the trade counter to zero, and with a 30-trade floor against a 60-day clock
the gate could never mature. The strategy improved faster than evidence about
it accumulated, so real money never arrived.

Terrence's decision on 2026-08-15: freeze the strategy, then count. Entry and
exit logic is final; only genuine defects get fixed, and a defect fix does not
invalidate the sample because the sample was always meant to measure the
intended rules rather than the buggy ones.

These tests exist to make a silent reset impossible. If you are here because
one failed, the question is not "how do I make it pass" — it is "am I
deliberately discarding every trade counted so far, and does Terrence agree?"
"""

import os
import sys
from datetime import date, datetime

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from report_generator import (                                        # noqa: E402
    GATE_START_DATE, STRATEGY_FROZEN_ON, GATE_DAYS, GATE_MIN_TRADES,
)


def test_window_start_is_the_freeze_date():
    """The two must move together, or not at all."""
    assert GATE_START_DATE == STRATEGY_FROZEN_ON, (
        "GATE_START_DATE drifted from STRATEGY_FROZEN_ON. Moving the window "
        "discards every trade counted so far — see this module's docstring."
    )


def test_freeze_date_is_pinned():
    """A literal, so any change shows up as a deliberate diff in review."""
    assert STRATEGY_FROZEN_ON == "2026-08-09"


def test_freeze_date_is_a_real_date_and_not_in_the_future():
    d = datetime.strptime(STRATEGY_FROZEN_ON, "%Y-%m-%d").date()
    assert d <= date.today(), "cannot freeze a strategy starting in the future"


def test_gate_terms_are_unchanged():
    """The floor and clock Terrence agreed to. Quietly lowering either is the
    same evasion as resetting the window."""
    assert GATE_MIN_TRADES == 30
    assert GATE_DAYS == 60


def test_the_window_can_actually_complete():
    """Sanity: the floor must be reachable inside the clock at a plausible
    entry rate. 30 trades in 60 calendar days needs ~0.7 entries per trading
    day, which the engine's 5-position cap and 10-day holds permit.

    This is the arithmetic that made the previous setup impossible once
    resets are removed — it is worth asserting rather than assuming.
    """
    trading_days = GATE_DAYS * 5 / 7
    required_per_day = GATE_MIN_TRADES / trading_days
    assert required_per_day < 1.0, (
        f"needs {required_per_day:.2f} closed trades per trading day — "
        "not achievable with a 5-position cap and 10-day holds"
    )
