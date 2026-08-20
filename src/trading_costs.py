"""Transaction costs — the single source for every module that prices a trade.

Was private to paper_trading.py. The backtests had no cost model at all, which
made them not merely optimistic but directively wrong: day_trading_backtest
reported the ORB variant at +0.139%/trade over 1,060 trades and +147.4% total,
and a round trip costs more than 0.139%. The strategy it recommended loses
money. pattern_backtest had the same gap.

A backtest that omits costs does not rank strategies conservatively — it ranks
them by turnover, because the strategies it flatters most are the ones that
trade most. That is the opposite of what a backtest is for.

Defaults follow IBKR's US tiered schedule. Tune here, nowhere else.
"""

COMMISSION_PER_SHARE = 0.0035   # USD per share, per side
COMMISSION_MIN       = 0.35     # USD floor, per side
COMMISSION_MAX_PCT   = 1.0      # capped at 1% of trade value, per side
SLIPPAGE_BPS         = 5.0      # basis points per side (0.05%)

# What a percent-only backtest assumes each ticket is worth. The floor and the
# cap are both absolute, so cost-as-a-percentage depends on ticket size and a
# percent-only backtest cannot derive it. This is the engine's own sizing:
# roughly 7-12% of an account near $5,000. Small tickets pay proportionally
# more — at $500 the $0.35 floor alone is 0.07% per side.
DEFAULT_NOTIONAL_USD = 500.0


def side_cost(price: float, shares: float) -> float:
    """Commission + slippage for ONE side of a trade, in dollars."""
    if not price or not shares or price <= 0 or shares <= 0:
        return 0.0
    value = price * shares
    commission = min(
        max(COMMISSION_PER_SHARE * shares, COMMISSION_MIN),
        value * COMMISSION_MAX_PCT / 100,
    )
    return commission + value * SLIPPAGE_BPS / 10_000


def round_trip_cost(entry_price: float, exit_price: float, shares: float) -> float:
    """Total dollar cost of entering and exiting a position."""
    return side_cost(entry_price, shares) + side_cost(exit_price, shares)


def net_pnl(entry_price: float, exit_price: float, shares: float,
            is_short: bool = False) -> tuple[float, float, float]:
    """Return (net_pnl, gross_pnl, costs) for a closed position."""
    gross = ((entry_price - exit_price) * shares if is_short
             else (exit_price - entry_price) * shares)
    costs = round_trip_cost(entry_price, exit_price, shares)
    return round(gross - costs, 2), round(gross, 2), round(costs, 2)


def round_trip_pct(entry_price: float, exit_price: float,
                   notional_usd: float = DEFAULT_NOTIONAL_USD) -> float:
    """Round-trip cost as a percentage of the entry notional.

    For backtests that track pnl in percent and never form a share count.
    Subtract the result from a trade's gross pnl_pct.

    Prices are per-share, so shares follow from the ticket size. A backtest
    that skips this step is quoting a gross return as if it were net.
    """
    if not entry_price or entry_price <= 0 or notional_usd <= 0:
        return 0.0
    shares = notional_usd / entry_price
    return round_trip_cost(entry_price, exit_price, shares) / notional_usd * 100
