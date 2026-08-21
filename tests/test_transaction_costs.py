"""Transaction costs, applied on every exit path.

Every P&L figure in the system was gross — no commission, no slippage, no
spread. On a 42-trade record at PF 0.26 that does not flip the conclusion,
but the go-live gate decides real money and an unpriced strategy cannot
support that decision.
"""

import os
import sys
import json

import pytest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

import paper_trading as pt                                          # noqa: E402
from paper_trading import (                                         # noqa: E402
    _side_cost, _net_pnl, _apply_ohlc_stops,
    COMMISSION_MIN, SLIPPAGE_BPS, STOP_LOSS_PCT,
)


# ── The cost model ────────────────────────────────────────────────────────────

def test_small_order_pays_the_commission_floor():
    """10 shares at $10: per-share works out to $0.035, so the $0.35 floor
    applies — and the 1% cap ($1.00 on a $100 trade) is above it."""
    value = 100.0
    cost = _side_cost(10.0, 10.0)
    assert cost == pytest.approx(COMMISSION_MIN + value * SLIPPAGE_BPS / 10_000)


def test_cap_beats_the_floor_on_a_tiny_trade():
    """On a $10 trade the 1% cap ($0.10) is below the $0.35 floor and wins —
    you cannot be charged more than the cap just because of a minimum."""
    cost = _side_cost(10.0, 1.0)
    assert cost < COMMISSION_MIN
    assert cost == pytest.approx(0.10 + 10.0 * SLIPPAGE_BPS / 10_000)


def test_commission_is_capped_at_one_percent():
    """IBKR caps at 1% of trade value; the floor must not exceed it."""
    cost = _side_cost(1.0, 5.0)          # $5 trade — floor would be 7% of it
    assert cost <= 5.0 * 0.01 + 5.0 * SLIPPAGE_BPS / 10_000 + 1e-9


def test_zero_and_negative_inputs_cost_nothing():
    for price, shares in ((0, 10), (10, 0), (-5, 10), (10, -5)):
        assert _side_cost(price, shares) == 0.0


def test_round_trip_on_a_typical_position_is_small_but_real():
    """$1,000 notional: roughly 0.17% round trip, not zero."""
    _net, _gross, costs = _net_pnl(100.0, 108.0, 10.0)
    pct = costs / 1000.0 * 100
    assert 0.05 < pct < 0.5, f"implausible cost {pct:.3f}% of notional"


# ── Direction ─────────────────────────────────────────────────────────────────

def test_costs_reduce_a_winner():
    net, gross, costs = _net_pnl(100.0, 110.0, 10.0)
    assert gross == 100.0
    assert net == pytest.approx(gross - costs)
    assert net < gross


def test_costs_deepen_a_loser():
    net, gross, costs = _net_pnl(100.0, 92.0, 10.0)
    assert gross == -80.0
    assert net < gross, "costs must make a loss worse, not better"


def test_short_direction_inverts_gross_only():
    net, gross, costs = _net_pnl(100.0, 90.0, 10.0, is_short=True)
    assert gross == 100.0          # short profits when price falls
    assert net == pytest.approx(gross - costs)


# ── Applied on the exit paths ─────────────────────────────────────────────────

def _trade():
    return {"ticker": "AAA", "direction": "long", "status": "open",
            "signal_date": "2026-08-01", "entry_price": 100.0, "shares": 10.0,
            "notional": 1000}


def test_history_sweep_records_net_gross_and_costs():
    """Levels are derived from STOP_LOSS_PCT, not written as literals.

    This test asserted a 92.0 fill and an -80.0 gross, both of which encode
    a -8% stop. The 2026-08-22 reset to -3% broke it without anything being
    wrong with the cost model it exists to check.
    """
    t = _trade()
    stop_price = 100.0 * (1 - STOP_LOSS_PCT / 100)
    through    = stop_price - 2.0            # the session trades through the stop
    ohlc = {"AAA": {"2026-08-03": {"open": 99.0, "low": through,
                                   "high": 99.5, "close": through + 1}}}

    _apply_ohlc_stops([t], ohlc, "2026-08-05")

    assert t["costs"] > 0
    assert t["pnl_gross"] == pytest.approx((stop_price - 100.0) * 10.0)
    assert t["pnl"] == pytest.approx(t["pnl_gross"] - t["costs"])
    # The fill is still exactly the stop — only the P&L carries the cost.
    assert t["exit_price"] == pytest.approx(stop_price)


@pytest.fixture
def portfolio(tmp_path, monkeypatch):
    p = tmp_path / "paper_portfolio.json"
    p.write_text(json.dumps({"trades": [_trade()], "last_updated": ""}))
    monkeypatch.setattr(pt, "PORTFOLIO_FILE", str(p))
    return p


def test_intraday_poll_records_costs(portfolio):
    # Priced through the stop, whatever the stop currently is.
    through = 100.0 * (1 - STOP_LOSS_PCT / 100) - 2.0
    pt.update_open_positions(
        [{"ticker": "AAA", "price": through, "open_price": 99.0}], "2026-08-03"
    )

    t = json.loads(portfolio.read_text())["trades"][0]
    assert t["costs"] > 0
    assert t["pnl"] == pytest.approx(t["pnl_gross"] - t["costs"])


def test_net_pnl_is_never_better_than_gross(portfolio):
    """The invariant: costs can only ever hurt."""
    for exit_price in (80.0, 92.0, 100.0, 112.0, 130.0):
        net, gross, costs = _net_pnl(100.0, exit_price, 10.0)
        assert net <= gross
        assert costs >= 0
