import os, sys, json
from datetime import datetime, timezone
PROJECT = r"C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm"
os.chdir(PROJECT)
sys.path.insert(0, os.path.join(PROJECT, "scripts"))
import MetaTrader5 as mt5

FTMO_PATH = r"C:\Program Files\FTMO Global Markets MT5 Terminal\terminal64.exe"
TARGETS = [("ADAUSD", 521187864), ("LTCUSD", 521187867)]
LOG = []
for sym, ticket in TARGETS:
    mt5.shutdown()
    ok = mt5.initialize(path=FTMO_PATH, login=0, password="", server="", timeout=15000)
    if not ok:
        LOG.append({"symbol": sym, "ticket": ticket, "status": "INIT_FAIL"})
        continue
    pos = mt5.positions_get(ticket=ticket)
    if not pos:
        LOG.append({"symbol": sym, "ticket": ticket, "status": "NO_POSITION"})
        continue
    p = pos[0]
    order_type = mt5.ORDER_TYPE_SELL if p.type in (mt5.ORDER_TYPE_BUY, 0) else mt5.ORDER_TYPE_BUY
    tick = mt5.symbol_info_tick(sym)
    price = tick.bid if order_type == mt5.ORDER_TYPE_SELL else tick.ask
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": sym,
        "volume": p.volume,
        "type": order_type,
        "position": p.ticket,
        "price": price,
        "deviation": 20,
        "magic": 20260819,
        "comment": "loser_review_close",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }
    r = mt5.order_send(req)
    status = "CLOSED" if r and r.retcode == 10009 else f"FAILED_{getattr(r,'retcode',None)}"
    LOG.append({"symbol": sym, "ticket": ticket, "status": status, "profit_before": float(p.profit), "price": float(price)})
    mt5.shutdown()

# Balance snapshot
mt5.initialize(path=FTMO_PATH, login=0, password="", server="", timeout=15000)
ai = mt5.account_info()
positions = mt5.positions_get() or []
mt5.shutdown()
out = {
    "generated": datetime.now(timezone.utc).isoformat(),
    "results": LOG,
    "post_close_balance": {
        "balance": float(ai.balance),
        "equity": float(ai.equity),
        "remaining_positions": len(positions)
    }
}
print(json.dumps(out, indent=2))
