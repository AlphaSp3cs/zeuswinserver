"""Connect to live IBKR Gateway (paper, 7497) read-only. List account equity,
available cash, and a few tradeable contracts to prove routing works."""
from ib_insync import IB, Stock, Crypto, Forex, CFD, Index, Contract
import sys

ib = IB()
try:
    ib.connect('127.0.0.1', 7497, clientId=99, timeout=15)
except Exception as e:
    print("IBKR CONNECT FAILED:", repr(e)); sys.exit(1)
print("IBKR CONNECTED. clientId=99")

acct = ib.managedAccounts()[0]
print("account:", acct)
sm = ib.accountSummary(acct)
d = {s.tag: (s.value, s.currency) for s in sm}
for t in ['NetLiquidation','TotalCashValue','BuyingPower','EquityWithLoanValue','AvailableFunds','MaintMarginReq']:
    if t in d: print(f"  {t}: {d[t][0]} {d[t][1]}")

# prove we can resolve contracts for each class (no order, just qualify)
tests = {
    'STOCK': Stock('AAPL','SMART','USD'),
    'ETF':   Stock('SPY','SMART','USD'),
    'CRYPTO': Crypto('BTC','PAXOS','USD'),
    'FOREX': Forex('EURUSD'),
    'INDEX': Index('US500','CBOE'),
}
for name, c in tests.items():
    try:
        ib.qualifyContracts(c)
        print(f"  QUALIFY {name}: OK -> {c}")
    except Exception as e:
        print(f"  QUALIFY {name}: {e}")
ib.disconnect()
print("IBKR DISCONNECTED (read-only session)")
