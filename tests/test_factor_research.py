"""Guards for the cross-sectional factor study.

The study's conclusion is negative, and the way it got there matters more than
the result: the pre-registered factor looked strong (+4.97 vs the null control,
quarterly, out of sample) until the per-period breakdown showed the mean was
two quarters of one semiconductor run. Remove the best two of 22 and it is
+0.38 -- zero, like everything before it.

That is survivorship bias behaving exactly as expected. The universe was picked
in 2026; STX/MU/LRCX are in it *because* they had that run, and a momentum
factor selects them just before it.

These tests pin the arithmetic that produced that finding, and the two design
choices that made it visible: the null control, and non-overlapping rebalances.
"""

import os
import sys

import pandas as pd
import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import factor_research as fr                                       # noqa: E402


# ── Factor construction ──────────────────────────────────────────────────────

def test_return_helper_skips_the_recent_window():
    """12-1 momentum SKIPS the last month; that skip is the specification.

    Without it the factor picks up short-term reversal, which this study also
    measured separately and found to have the opposite sign out of sample.
    """
    c = pd.Series([100.0] * 300)
    c.iloc[-21:] = 200.0                       # all the move is in the last month
    r = fr._ret(c, 252, 21)
    assert r.iloc[-1] == pytest.approx(0.0), (
        "a move inside the skipped window must not register"
    )


def test_return_helper_measures_the_formation_window():
    c = pd.Series([100.0] * 300)
    c.iloc[-100:] = 150.0                      # move lands before the skip
    assert fr._ret(c, 252, 21).iloc[-1] == pytest.approx(0.5)


@pytest.mark.parametrize("name", list(fr.FACTORS))
def test_every_factor_ranks_higher_as_better(name):
    """nlargest() picks the basket, so a factor whose sign is inverted would
    systematically buy the worst names and look like a discovery."""
    idx = pd.date_range("2020-01-01", periods=300, freq="D")
    rising = pd.Series([100.0 + i for i in range(300)], index=idx)
    falling = pd.Series([400.0 - i for i in range(300)], index=idx)
    closes = pd.DataFrame({"UP": rising, "DOWN": falling})
    vols = pd.DataFrame({"UP": [1e6] * 300, "DOWN": [1e6] * 300}, index=idx)
    out = fr.FACTORS[name](closes, vols).iloc[-1]
    if name in ("reversal_1m", "low_vol_60"):
        return                                  # deliberately contrarian / not directional
    assert out["UP"] >= out["DOWN"], f"{name} ranks the falling name higher"


# ── The controls that made the negative result trustworthy ───────────────────

def test_the_primary_factor_is_pre_registered():
    """Naming it before the run is what stops 'test seven, report the best'."""
    assert fr.PRIMARY == "mom_12_1"
    assert fr.PRIMARY in fr.FACTORS


def test_the_windows_do_not_overlap():
    (_, is_end), (oos_start, _) = fr.WINDOWS["in-sample"], fr.WINDOWS["oos-fresh"]
    assert is_end <= oos_start


def test_the_hold_periods_are_long_enough_for_the_factor():
    """A 12-month factor against a 10-day forward return asks a different
    question. The first attempt used the engine's 10-day hold and produced
    4 rebalances per window, on which one factor printed t=+5.05."""
    assert min(fr.HOLDS.values()) >= 21


def test_selection_is_a_fixed_basket_not_a_decile():
    """108 survivors cannot support decile sorts -- a top decile is ~11 names
    and mostly noise. TOP_N also has to match the live book to be actionable."""
    from paper_trading import MAX_OPEN_POSITIONS
    assert fr.TOP_N == MAX_OPEN_POSITIONS


def test_the_ticket_size_matches_the_real_book():
    """Costs are ticket-size dependent; a wrong ticket silently re-prices the
    whole study. $937 is the live IBKR book over 5 slots."""
    assert 800 < fr.TICKET_USD < 1100


def test_costs_are_charged_on_every_rebalance():
    """Each rebalance turns the basket, so each one pays a round trip. A study
    that charges once is quoting a gross return."""
    import inspect
    body = inspect.getsource(fr._evaluate)
    assert "- cost" in body, "rebalance returns must be net of costs"
    assert "round_trip_pct" in inspect.getsource(fr)


def test_the_null_control_holds_the_whole_universe():
    """The factor is only interesting if it beats owning every name in the
    same survivor-biased list. Sharing the universe is what makes the
    vs-NULL column readable when the absolute alpha is not."""
    import inspect
    body = inspect.getsource(fr._evaluate)
    assert "NULL_whole_universe" in body
    assert "for p in names" in body, "the control must span the full universe"
