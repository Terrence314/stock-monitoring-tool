"""Guards for the signal study's arithmetic.

The study exists to answer whether the engine's entry signals lose because of
the market regime or because they measure a level instead of a rate of change.
A quiet bug in any of these four helpers would not crash anything — it would
produce a confident, wrong answer, which is worse.

The first version of this study had no benchmark at all. Over a rising
two-year window every long signal printed +0.6%, which looked like an edge and
was just the market. That is the same defect the backtests in this repo had,
reproduced by the person who had just finished writing it up.
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import signal_research as sr                                       # noqa: E402


# ── _rising: n consecutive increases ─────────────────────────────────────────

def test_rising_needs_every_step_to_increase():
    s = pd.Series([1.0, 2.0, 3.0, 2.5, 3.5])
    r2 = sr._rising(s, 2)
    assert bool(r2.iloc[2]) is True       # 1 -> 2 -> 3
    assert bool(r2.iloc[3]) is False      # 3 -> 2.5 breaks it
    assert bool(r2.iloc[4]) is False      # 2.5 -> 3.5 is only one step up


def test_rising_is_stricter_as_n_grows():
    s = pd.Series([1.0, 2.0, 3.0, 4.0])
    assert bool(sr._rising(s, 1).iloc[3]) is True
    assert bool(sr._rising(s, 3).iloc[3]) is True
    assert bool(sr._rising(s, 4).iloc[3]) is False   # not enough history


def test_a_flat_series_is_not_rising():
    s = pd.Series([2.0] * 5)
    assert not sr._rising(s, 1).iloc[-1]


# ── Efficiency ratio: the trend / chop separator ─────────────────────────────

def test_a_straight_line_is_perfectly_efficient():
    s = pd.Series(range(1, 40), dtype=float)
    assert sr._efficiency_ratio(s, 10).iloc[-1] == pytest.approx(1.0)


def test_pure_oscillation_is_inefficient():
    """Up-down-up-down travels far and arrives nowhere — the definition of chop."""
    s = pd.Series([10.0, 11.0] * 20)
    assert sr._efficiency_ratio(s, 10).iloc[-1] == pytest.approx(0.0, abs=1e-9)


def test_a_choppy_advance_scores_between_the_two():
    s = pd.Series([10, 11, 10.5, 12, 11.5, 13, 12.5, 14, 13.5, 15, 14.5] * 3,
                  dtype=float)
    er = sr._efficiency_ratio(s, 10).iloc[-1]
    assert 0.0 < er < 1.0


def test_the_trend_threshold_is_pinned():
    """Moving it silently re-cuts every result in the study."""
    assert sr.ER_TRENDING == 0.30
    assert sr.ER_WINDOW == 20


# ── The variants are wired to the right conditions ───────────────────────────

def test_state_and_event_variants_differ_by_persistence():
    """The whole level-vs-event question depends on these two not being equal.

    A state is true for every day of a trend; the event is true only on the
    day it turns. If a refactor made them the same, the study would compare a
    variant against itself and report no difference.
    """
    idx = pd.date_range("2026-01-01", periods=5, freq="D")
    f = pd.DataFrame({"ma5":  [1.0, 3.0, 3.0, 3.0, 3.0],
                      "ma20": [2.0, 2.0, 2.0, 2.0, 2.0]}, index=idx)
    state = sr.VARIANTS["golden_cross_STATE"](f)
    event = sr.VARIANTS["golden_cross_EVENT"](f)
    assert list(state) == [False, True, True, True, True]
    assert list(event) == [False, True, False, False, False]


def test_the_engine_combo_requires_all_three_conditions():
    """It must mirror what the live engine actually buys on, or the study is
    measuring a strategy nobody runs."""
    idx = pd.date_range("2026-01-01", periods=2, freq="D")
    f = pd.DataFrame({"ma5": [3.0, 3.0], "ma20": [2.0, 2.0],
                      "macd": [1.0, 1.0], "macd_signal": [0.5, 2.0],
                      "close": [10.0, 10.0], "ma60": [9.0, 9.0]}, index=idx)
    out = sr.VARIANTS["engine_combo_STATE"](f)
    assert bool(out.iloc[0]) is True
    assert bool(out.iloc[1]) is False     # macd fell below signal


def test_every_variant_is_callable_and_returns_a_boolean_mask():
    idx = pd.date_range("2026-01-01", periods=30, freq="D")
    n = len(idx)
    f = pd.DataFrame({c: [1.0] * n for c in
                      ["close", "ma5", "ma20", "ma60", "rsi",
                       "macd", "macd_signal", "hist", "k", "d"]}, index=idx)
    for name, fn in sr.VARIANTS.items():
        out = fn(f)
        assert len(out) == n, name
        assert out.dropna().isin([True, False]).all(), name


# ── Settings that make results comparable ────────────────────────────────────

def test_the_cooldown_matches_the_hold_period():
    """Without it, a state variant logs ten overlapping entries where the
    engine could hold one position — which would rank variants by how often
    they fire rather than by how well they do."""
    assert sr.COOLDOWN == sr.HOLD_DAYS


def test_the_hold_period_matches_the_live_engine():
    from paper_trading import HOLD_DAYS
    assert sr.HOLD_DAYS == HOLD_DAYS, (
        "the study must hold for as long as the engine does, or its numbers "
        "cannot be compared to the engine's record"
    )
