import json, os, sys
from datetime import datetime, timezone
from ib_insync import IB
PROJECT = r"C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm"
os.chdir(PROJECT)
vault = os.path.join(PROJECT, "vault")
os.makedirs(vault, exist_ok=True)
ib = IB()
ib.connect("127.0.0.1", 4002, clientId=2002)
accts = ib.managedAccounts()
acct = accts[0] if accts else None
summary = {}
for row in ib.accountSummary(acct):
    if row.tag in ("NetLiquidation","EquityWithLoanValue","TotalCashValue","AvailableFunds","BuyingPower","ExcessLiquidity","GrossPositionValue","UnrealizedPnl","RealizedPnl"):
        summary[row.tag] = float(row.value)
positions = []
for p in ib.positions():
    positions.append({
        "symbol": p.contract.symbol,
        "secType": p.contract.secType,
        "position": float(p.position),
        "avgCost": float(p.avgCost),
        "unrealized_pnl": float(p.unrealizedPNL),
    })
state = {
    "generated": datetime.now(timezone.utc).isoformat(),
    "connected": ib.isConnected(),
    "account": acct,
    "summary": summary,
    "positions_count": len(positions),
    "positions": positions,
    "conclusion": "executable" if summary.get("AvailableFunds", 0) > 0 else "insufficient_funds",
    "action": "plan_equity_growth_setups",
    "user_action": "None",
    "fallback_route": "IBKR paper executable"
}
with open(os.path.join(vault, "ibkr_state_now.json"), "w") as f:
    json.dump(state, f, indent=2)
print(json.dumps(state, indent=2))
ib.disconnect()
