#!/usr/bin/env python3
"""add_transaction.py — Simple CLI to add portfolio transactions.

Usage
-----
  # Deposit cash
  python add_transaction.py deposit 50000 HKD
  python add_transaction.py deposit 10000 USD

  # Withdraw cash
  python add_transaction.py withdraw 5000 USD

  # Buy shares
  python add_transaction.py buy NVDA 10 125.50 USD
  python add_transaction.py buy NVDA 10 980.00 HKD   # HKD price, auto-converted internally

  # Sell shares
  python add_transaction.py sell NVDA 5 140.00 USD
  python add_transaction.py sell NVDA 5 1090.00 HKD

  # Add a note (wrap in quotes)
  python add_transaction.py buy TSLA 5 200.00 USD "earnings play"

After adding, commit and push — the pipeline regenerates portfolio.html.
"""

import sys
import json
import os
from datetime import date

TRANSACTIONS_FILE = os.path.join("data", "portfolio_transactions.json")
VALID_CURRENCIES  = {"USD", "HKD"}
VALID_TICKERS     = None   # allow any ticker


def _load() -> list:
    try:
        with open(TRANSACTIONS_FILE, encoding="utf-8") as f:
            return json.load(f).get("transactions", [])
    except (FileNotFoundError, json.JSONDecodeError):
        return []


def _save(txns: list) -> None:
    os.makedirs(os.path.dirname(TRANSACTIONS_FILE), exist_ok=True)
    with open(TRANSACTIONS_FILE, "w", encoding="utf-8") as f:
        json.dump({"transactions": txns}, f, ensure_ascii=False, indent=2)


def _today() -> str:
    return date.today().isoformat()


def _err(msg: str) -> None:
    print(f"\n  ❌  {msg}\n")
    sys.exit(1)


def _confirm(msg: str) -> bool:
    ans = input(f"  {msg} [y/N] ").strip().lower()
    return ans in ("y", "yes")


def cmd_deposit(args: list) -> None:
    """deposit <amount> [currency=USD]"""
    if len(args) < 1:
        _err("Usage: deposit <amount> [USD|HKD]\n  e.g. deposit 50000 HKD")
    try:
        amount = float(args[0])
    except ValueError:
        _err(f"Invalid amount: {args[0]}")
    currency = args[1].upper() if len(args) > 1 else "USD"
    if currency not in VALID_CURRENCIES:
        _err(f"Currency must be USD or HKD, got: {currency}")
    notes = args[2] if len(args) > 2 else ""

    txn = {
        "date":     _today(),
        "type":     "deposit",
        "ticker":   None,
        "shares":   amount,
        "price":    None,
        "currency": currency,
        "notes":    notes,
    }
    print(f"\n  ➕  Deposit  {amount:,.2f} {currency}  on {_today()}")
    if notes:
        print(f"      Note: {notes}")
    if _confirm("Add this transaction?"):
        txns = _load()
        txns.append(txn)
        _save(txns)
        print("  ✅  Saved. Push to GitHub to update portfolio.html.\n")
    else:
        print("  Cancelled.\n")


def cmd_withdraw(args: list) -> None:
    """withdraw <amount> [currency=USD]"""
    if len(args) < 1:
        _err("Usage: withdraw <amount> [USD|HKD]")
    try:
        amount = float(args[0])
    except ValueError:
        _err(f"Invalid amount: {args[0]}")
    currency = args[1].upper() if len(args) > 1 else "USD"
    if currency not in VALID_CURRENCIES:
        _err(f"Currency must be USD or HKD, got: {currency}")
    notes = args[2] if len(args) > 2 else ""

    txn = {
        "date":     _today(),
        "type":     "withdraw",
        "ticker":   None,
        "shares":   amount,
        "price":    None,
        "currency": currency,
        "notes":    notes,
    }
    print(f"\n  ➖  Withdraw  {amount:,.2f} {currency}  on {_today()}")
    if _confirm("Add this transaction?"):
        txns = _load()
        txns.append(txn)
        _save(txns)
        print("  ✅  Saved.\n")
    else:
        print("  Cancelled.\n")


def cmd_buy(args: list) -> None:
    """buy <ticker> <shares> <price> [currency=USD] [notes]"""
    if len(args) < 3:
        _err("Usage: buy <TICKER> <shares> <price> [USD|HKD] [notes]\n  e.g. buy NVDA 10 125.50 USD")
    ticker = args[0].upper()
    try:
        shares = float(args[1])
        price  = float(args[2])
    except ValueError:
        _err("shares and price must be numbers.")
    currency = args[3].upper() if len(args) > 3 and args[3].upper() in VALID_CURRENCIES else "USD"
    notes    = args[4] if len(args) > 4 else (args[3] if len(args) > 3 and args[3].upper() not in VALID_CURRENCIES else "")

    amount = shares * price
    txn = {
        "date":     _today(),
        "type":     "buy",
        "ticker":   ticker,
        "shares":   shares,
        "price":    price,
        "currency": currency,
        "notes":    notes,
    }
    print(f"\n  🟢  BUY  {shares:g} × {ticker}  @  {price:,.4f} {currency}")
    print(f"      Total cost:  {amount:,.2f} {currency}  on {_today()}")
    if notes:
        print(f"      Note: {notes}")
    if _confirm("Add this transaction?"):
        txns = _load()
        txns.append(txn)
        _save(txns)
        print("  ✅  Saved. Push to GitHub to update portfolio.html.\n")
    else:
        print("  Cancelled.\n")


def cmd_sell(args: list) -> None:
    """sell <ticker> <shares> <price> [currency=USD] [notes]"""
    if len(args) < 3:
        _err("Usage: sell <TICKER> <shares> <price> [USD|HKD] [notes]\n  e.g. sell NVDA 5 140.00 USD")
    ticker = args[0].upper()
    try:
        shares = float(args[1])
        price  = float(args[2])
    except ValueError:
        _err("shares and price must be numbers.")
    currency = args[3].upper() if len(args) > 3 and args[3].upper() in VALID_CURRENCIES else "USD"
    notes    = args[4] if len(args) > 4 else (args[3] if len(args) > 3 and args[3].upper() not in VALID_CURRENCIES else "")

    amount = shares * price
    txn = {
        "date":     _today(),
        "type":     "sell",
        "ticker":   ticker,
        "shares":   shares,
        "price":    price,
        "currency": currency,
        "notes":    notes,
    }
    print(f"\n  🔴  SELL  {shares:g} × {ticker}  @  {price:,.4f} {currency}")
    print(f"      Proceeds:  {amount:,.2f} {currency}  on {_today()}")
    if notes:
        print(f"      Note: {notes}")
    if _confirm("Add this transaction?"):
        txns = _load()
        txns.append(txn)
        _save(txns)
        print("  ✅  Saved. Push to GitHub to update portfolio.html.\n")
    else:
        print("  Cancelled.\n")


def cmd_list(_args: list) -> None:
    """list — show all transactions"""
    txns = _load()
    if not txns:
        print("\n  No transactions yet.\n")
        return
    print(f"\n  {'Date':<12} {'Type':<10} {'Ticker':<8} {'Shares/Amt':>12} {'Price':>10} {'Ccy':<5} Notes")
    print("  " + "─" * 72)
    for t in sorted(txns, key=lambda x: x["date"]):
        ticker  = t.get("ticker") or "—"
        shares  = t.get("shares") or "—"
        price   = t.get("price") or "—"
        cur     = t.get("currency", "USD")
        notes   = t.get("notes") or ""
        tp      = t.get("type", "").upper()
        print(f"  {t['date']:<12} {tp:<10} {ticker:<8} {str(shares):>12} {str(price):>10} {cur:<5} {notes}")
    print()


COMMANDS = {
    "deposit":  cmd_deposit,
    "withdraw": cmd_withdraw,
    "buy":      cmd_buy,
    "sell":     cmd_sell,
    "list":     cmd_list,
}


def main():
    if len(sys.argv) < 2 or sys.argv[1] in ("-h", "--help", "help"):
        print(__doc__)
        sys.exit(0)

    cmd = sys.argv[1].lower()
    args = sys.argv[2:]

    if cmd not in COMMANDS:
        print(f"\n  Unknown command: {cmd}")
        print(f"  Valid commands: {', '.join(COMMANDS)}\n")
        sys.exit(1)

    COMMANDS[cmd](args)


if __name__ == "__main__":
    main()
