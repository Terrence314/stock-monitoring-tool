"""Every backtest must price its trades. None of them did.

day_trading_backtest reported the ORB variant at +0.139%/trade over 1,060
trades and +147.4% total, with no cost model anywhere in the file. A round
trip on a $500 ticket costs about 0.24%, so the strategy it recommended was
in fact losing money on every trade. pattern_backtest had the same gap, and
it ranks patterns by win rate — so patterns whose edge is thinner than one
round trip were sorting above patterns that actually clear it.

Omitting costs does not make a backtest conservative. It ranks strategies by
turnover, because the ones it flatters most are the ones that trade most.
That is the exact opposite of what a backtest is for, and it is worst for
intraday strategies, where the per-trade edge is smallest and the trade count
is largest.
"""

import os
import re
import sys

import pytest

SRC = os.path.join(os.path.dirname(__file__), "..", "src")
sys.path.insert(0, SRC)

from trading_costs import (                                        # noqa: E402
    COMMISSION_MIN, DEFAULT_NOTIONAL_USD, SLIPPAGE_BPS,
    net_pnl, round_trip_cost, round_trip_pct, side_cost,
)


# ── The model ─────────────────────────────────────────────────────────────────

def test_small_tickets_pay_the_commission_floor():
    """100 shares at $0.0035 is $0.35 — exactly the floor, not below it."""
    assert side_cost(10.0, 10) == pytest.approx(COMMISSION_MIN + 100 * 0.0005)


def test_the_one_percent_cap_beats_the_floor_on_tiny_trades():
    """A $10 ticket pays 1% ($0.10), not the $0.35 floor — the cap wins."""
    cost = side_cost(10.0, 1)
    assert cost == pytest.approx(0.10 + 10.0 * SLIPPAGE_BPS / 10_000)


def test_large_tickets_pay_per_share_not_the_floor():
    assert side_cost(100.0, 1000) == pytest.approx(3.5 + 100_000 * 0.0005)


@pytest.mark.parametrize("price,shares", [(0, 10), (10, 0), (-5, 10), (10, -5)])
def test_degenerate_inputs_cost_nothing_rather_than_raising(price, shares):
    assert side_cost(price, shares) == 0.0


def test_round_trip_is_both_sides():
    assert round_trip_cost(100.0, 110.0, 10) == pytest.approx(
        side_cost(100.0, 10) + side_cost(110.0, 10))


def test_net_pnl_subtracts_costs_from_gross():
    net, gross, costs = net_pnl(100.0, 110.0, 10)
    assert gross == 100.0
    assert costs > 0
    assert net == pytest.approx(gross - costs)


def test_a_short_profits_when_price_falls():
    net, gross, _ = net_pnl(100.0, 90.0, 10, is_short=True)
    assert gross == 100.0 and net < gross


# ── The percent helper the backtests use ─────────────────────────────────────

def test_cost_percent_is_independent_of_share_price():
    """Only ticket size moves it — $500 of a $50 stock costs the same as
    $500 of a $200 stock, because the floor is per order, not per share."""
    assert round_trip_pct(50.0, 50.0, 500) == pytest.approx(
        round_trip_pct(200.0, 200.0, 500), abs=1e-9)


def test_smaller_tickets_pay_proportionally_more():
    """The $0.35 floor is absolute, so it hurts small tickets most. This is
    why a percent-only backtest cannot infer its own cost rate."""
    assert (round_trip_pct(100.0, 100.0, 250)
            > round_trip_pct(100.0, 100.0, 1000)
            > round_trip_pct(100.0, 100.0, 5000))


def test_the_default_ticket_costs_about_a_quarter_percent():
    """The number that flips the day-trading result. If this drifts, the
    conclusions in outputs/strategy-diagnosis_2026-08-20.md drift with it."""
    assert round_trip_pct(100.0, 100.0, DEFAULT_NOTIONAL_USD) == pytest.approx(0.24, abs=0.01)


def test_costs_are_never_negative_or_free():
    for notional in (100, 500, 5000):
        assert round_trip_pct(100.0, 105.0, notional) > 0


@pytest.mark.parametrize("entry", [0, -1])
def test_a_bad_entry_price_costs_nothing_rather_than_raising(entry):
    assert round_trip_pct(entry, 100.0, 500) == 0.0


# ── The engine and the backtests must agree ──────────────────────────────────

def test_paper_trading_uses_the_shared_model():
    """Not a copy. A second copy is how the two drift apart."""
    import paper_trading as pt
    import trading_costs as tc
    assert pt._side_cost is tc.side_cost
    assert pt._net_pnl is tc.net_pnl


@pytest.mark.parametrize("module", ["day_trading_backtest", "pattern_backtest"])
def test_every_backtest_imports_the_cost_model(module):
    """The regression guard. A backtest that does not import this module is
    quoting gross returns as net — see this file's docstring."""
    with open(os.path.join(SRC, f"{module}.py"), encoding="utf-8") as f:
        body = f.read()
    assert re.search(r"from trading_costs import|import trading_costs", body), (
        f"{module}.py prices its trades at zero"
    )
    assert "round_trip_pct" in body, f"{module}.py imports costs but never applies them"


def test_day_trading_backtest_reports_net_and_gross_separately():
    """Net alone hides how big the drag is; gross alone is the original bug."""
    import day_trading_backtest as dt
    t = dt._priced(100.0, 101.0, "target")
    assert t["pnl_pct_gross"] == pytest.approx(1.0)
    assert t["cost_pct"] > 0
    assert t["pnl_pct"] == pytest.approx(t["pnl_pct_gross"] - t["cost_pct"], abs=0.01)
    assert t["pnl_pct"] < t["pnl_pct_gross"]


def test_a_trade_smaller_than_its_costs_is_booked_as_a_loss():
    """The reclassification that moved the ORB win rate. A +0.1% gross scalp
    does not clear a 0.24% round trip and must not count as a win."""
    import day_trading_backtest as dt
    t = dt._priced(100.0, 100.1, "time")
    assert t["pnl_pct_gross"] > 0
    assert t["pnl_pct"] < 0


def test_the_three_published_figures_reconcile():
    """net == gross - costs at the printed precision.

    All three go into paper_portfolio.json together. Rounding them off the raw
    values independently let them disagree by a cent: a -$30.00 gross with
    $1.685 of costs published as net -31.68, where subtracting the printed
    figures gives -31.69. Surfaced when the stop moved to -3% and a fixture
    landed on that boundary.
    """
    for entry, exit_, shares in [
        (100.0, 97.0, 10.0), (100.0, 92.0, 10.0), (250.0, 262.5, 4.0),
        (37.76, 34.74, 26.5), (7.5, 7.1, 133.0), (1000.0, 1060.0, 0.5),
    ]:
        net, gross, costs = net_pnl(entry, exit_, shares)
        assert net == pytest.approx(gross - costs, abs=1e-9), (
            f"{entry}->{exit_} x{shares}: {net} != {gross} - {costs}"
        )


def test_reconciliation_holds_for_shorts_too():
    net, gross, costs = net_pnl(100.0, 97.0, 10.0, is_short=True)
    assert net == pytest.approx(gross - costs, abs=1e-9)
