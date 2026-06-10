"""IBKR Gateway connection test — Phase 1.

Run AFTER IB Gateway is logged in (paper account, port 4002).

    python3 src/ibkr_connect_test.py

Checks: connection, account summary, one live quote.
Read-only — places no orders.
"""
from ib_async import IB, Stock

GATEWAY_HOST = "127.0.0.1"
GATEWAY_PORT = 4002          # 4002 = paper Gateway, 4001 = live Gateway
CLIENT_ID    = 7             # any unused integer


def main() -> None:
    ib = IB()
    print(f"Connecting to IB Gateway at {GATEWAY_HOST}:{GATEWAY_PORT} …")
    try:
        ib.connect(GATEWAY_HOST, GATEWAY_PORT, clientId=CLIENT_ID, timeout=10)
    except Exception as e:
        print(f"❌ Connection failed: {e}")
        print("Checklist:")
        print("  1. IB Gateway running and logged in (paper mode)?")
        print("  2. Gateway → Configure → Settings → API → Enable ActiveX/Socket Clients?")
        print("  3. Socket port set to 4002?")
        print("  4. Trusted IP 127.0.0.1 added (or 'Allow connections from localhost only')?")
        return

    print("✅ Connected.")

    # Account summary
    account = ib.managedAccounts()
    print(f"Accounts: {account}")
    summary = ib.accountSummary()
    for row in summary:
        if row.tag in ("NetLiquidation", "TotalCashValue", "BuyingPower", "AvailableFunds"):
            print(f"  {row.tag}: {row.value} {row.currency}")

    # One live quote (delayed if no data subscription — type 3 fallback)
    ib.reqMarketDataType(3)  # 1=live, 3=delayed — works without paid subscription
    contract = Stock("SPY", "SMART", "USD")
    ib.qualifyContracts(contract)
    ticker = ib.reqMktData(contract)
    ib.sleep(3)
    print(f"SPY quote: last={ticker.last} bid={ticker.bid} ask={ticker.ask} (marketDataType=delayed ok)")

    ib.disconnect()
    print("✅ Test complete — gateway ready for streaming.")


if __name__ == "__main__":
    main()
