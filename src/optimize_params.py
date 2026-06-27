"""optimize_params.py — Optuna-based parameter optimizer.

Reads paper trading history + strategy backtest results, then uses Optuna
to find optimal signal_threshold, stop_loss_pct, and take_profit_pct.

Usage:
    python3 src/optimize_params.py            # 100 trials, print result
    python3 src/optimize_params.py --apply    # apply best params to config.json
    python3 src/optimize_params.py --trials 200

ALERTS ONLY — never places orders. Optimization is advisory.
"""
import json
import os
import sys

PORTFOLIO_FILE  = os.path.join("outputs", "paper_portfolio.json")
BACKTEST_FILE   = os.path.join("outputs", "strategy_backtest.json")
CONFIG_FILE     = os.path.join("config", "config.json")


def _load(path, default):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f)
    except (OSError, json.JSONDecodeError):
        return default


def _profit_factor(trades: list, threshold: float, stop_pct: float, target_pct: float) -> float:
    """Simulate trades filtered by score threshold with given stop/target params."""
    gross_win = gross_loss = 0.0
    for t in trades:
        if t.get("score", 0) < threshold:
            continue
        raw = t.get("pnl_pct", 0)
        # Simulate: if trade would have hit stop/target at new levels
        if raw <= -stop_pct:
            gross_loss += stop_pct
        elif raw >= target_pct:
            gross_win += target_pct
        else:
            if raw >= 0:
                gross_win += raw
            else:
                gross_loss += abs(raw)
    if gross_loss == 0:
        return gross_win if gross_win > 0 else 0.0
    return gross_win / gross_loss


def _win_rate(trades: list, threshold: float, stop_pct: float, target_pct: float) -> float:
    """Win rate of trades filtered by score and simulated with new params."""
    wins = total = 0
    for t in trades:
        if t.get("score", 0) < threshold:
            continue
        raw = t.get("pnl_pct", 0)
        pnl = -stop_pct if raw <= -stop_pct else (target_pct if raw >= target_pct else raw)
        total += 1
        if pnl > 0:
            wins += 1
    return (wins / total * 100) if total > 0 else 0.0


def run_optimization(n_trials: int = 100) -> dict:
    try:
        import optuna
        optuna.logging.set_verbosity(optuna.logging.WARNING)
    except ImportError:
        print("❌ optuna not installed. Run: pip install optuna")
        sys.exit(1)

    # Load trade data
    portfolio = _load(PORTFOLIO_FILE, {})
    trades    = [t for t in portfolio.get("trades", []) if t.get("status") == "closed"]

    backtest  = _load(BACKTEST_FILE, {})
    bt_trades = backtest.get("trades_A", [])

    # Combine: paper trades have score, backtest trades have more history
    # Use paper trades for score-based optimization, bt_trades for volume
    all_trades = trades  # paper trades have score field

    if len(all_trades) < 4:
        print(f"⚠️  Only {len(all_trades)} closed trades — optimization may not be reliable.")
        print("   Run the tool longer to accumulate more paper trade history.")

    def objective(trial):
        threshold  = trial.suggest_float("signal_threshold", 55, 85, step=5)
        stop_pct   = trial.suggest_float("stop_loss_pct",    5,  12, step=1)
        target_pct = trial.suggest_float("take_profit_pct",  8,  20, step=2)

        pf = _profit_factor(all_trades, threshold, stop_pct, target_pct)
        wr = _win_rate(all_trades, threshold, stop_pct, target_pct)

        # Filter out degenerate results
        filtered = [t for t in all_trades if t.get("score", 0) >= threshold]
        if len(filtered) < 2:
            return 0.0

        # Combined objective: profit factor weighted with win rate
        # PF > 1.0 is breakeven; target > 1.3
        return pf * 0.7 + (wr / 100) * 0.3

    study = optuna.create_study(direction="maximize")
    study.optimize(objective, n_trials=n_trials, show_progress_bar=False)

    best = study.best_params
    best_val = study.best_value

    # Compute final metrics with best params
    best_pf = _profit_factor(all_trades, best["signal_threshold"],
                              best["stop_loss_pct"], best["take_profit_pct"])
    best_wr = _win_rate(all_trades, best["signal_threshold"],
                         best["stop_loss_pct"], best["take_profit_pct"])
    filtered_count = sum(1 for t in all_trades if t.get("score",0) >= best["signal_threshold"])

    return {
        "signal_threshold":  int(best["signal_threshold"]),
        "stop_loss_pct":     best["stop_loss_pct"],
        "take_profit_pct":   best["take_profit_pct"],
        "profit_factor":     round(best_pf, 3),
        "win_rate":          round(best_wr, 1),
        "trades_qualified":  filtered_count,
        "total_trades":      len(all_trades),
        "n_trials":          n_trials,
        "objective_score":   round(best_val, 4),
    }


def apply_to_config(result: dict) -> None:
    cfg = _load(CONFIG_FILE, {})
    cfg.setdefault("analysis", {})["signal_threshold_alert"] = result["signal_threshold"]
    with open(CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(cfg, f, indent=2, ensure_ascii=False)
    print(f"✅ config.json updated: signal_threshold_alert → {result['signal_threshold']}")


def main():
    args = sys.argv[1:]
    n_trials = 100
    apply    = "--apply" in args
    for i, a in enumerate(args):
        if a == "--trials" and i + 1 < len(args):
            n_trials = int(args[i + 1])

    print(f"\n📊 Optuna parameter optimization ({n_trials} trials)…")
    print("   Optimizing: signal_threshold · stop_loss_pct · take_profit_pct")
    print()

    result = run_optimization(n_trials)

    print("═" * 48)
    print(f"  Best parameters found:")
    print(f"  signal_threshold   : {result['signal_threshold']} (was 70)")
    print(f"  stop_loss_pct      : −{result['stop_loss_pct']:.0f}% (was −8%)")
    print(f"  take_profit_pct    : +{result['take_profit_pct']:.0f}% (was +12%)")
    print(f"")
    print(f"  Profit factor  : {result['profit_factor']:.2f}x")
    print(f"  Win rate       : {result['win_rate']:.1f}%")
    print(f"  Trades used    : {result['trades_qualified']}/{result['total_trades']}")
    print("═" * 48)

    if result["trades_qualified"] < 4:
        print("\n⚠️  Too few trades to be statistically meaningful.")
        print("   Results are directional only. Accumulate more paper trade history.")

    if apply:
        apply_to_config(result)
        print("\nRun the pipeline to apply new threshold to live signals.")
    else:
        print(f"\nTo apply: python3 src/optimize_params.py --apply")


if __name__ == "__main__":
    main()
