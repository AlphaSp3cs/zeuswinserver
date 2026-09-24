import os, sys, json, traceback
from datetime import datetime, timezone
PROJECT = r"C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm"
os.chdir(PROJECT)
sys.path.insert(0, os.path.join(PROJECT, "scripts"))
import MetaTrader5 as mt5

FTMO_PATH = r"C:\Program Files\FTMO Global Markets MT5 Terminal\terminal64.exe"
TICKET = 521145636
SYM = "EURUSD"
mt5.shutdown()
ok = mt5.initialize(path=FTMO_PATH, login=0, password="", server="", timeout=15000)
print(json.dumps({"init": ok, "last_error": str(mt5.last_error()) if not ok else None}, indent=2))
if not ok:
    sys.exit(1)
ai = mt5.account_info()
print(json.dumps({"login": int(ai.login), "trade_allowed": bool(ai.trade_allowed), "balance": float(ai.balance), "equity": float(ai.equity)}, indent=2))
positions = mt5.positions_get(ticket=TICKET) or []
print(json.dumps({"positions_found": len(positions), "positions": [{"ticket": int(p.ticket), "symbol": p.symbol, "profit": float(p.profit), "type": int(p.type), "volume": float(p.volume)} for p in positions]}, indent=2))
if not positions:
    sys.exit(0)
p = positions[0]
order_type = mt5.ORDER_TYPE_SELL if p.type in (mt5.ORDER_TYPE_BUY, 0) else mt5.ORDER_TYPE_BUY
tick = mt5.symbol_info_tick(SYM)
price = tick.bid if order_type == mt5.ORDER_TYPE_SELL else tick.ask
req = {
    "action": mt5.TRADE_ACTION_DEAL,
    "symbol": SYM,
    "volume": p.volume,
    "type": order_type,
    "position": p.ticket,
    "price": price,
    "deviation": 20,
    "magic": 20260819,
    "comment": "start_fresh_close_profit_probe",
    "type_time": mt5.ORDER_TIME_GTC,
    "type_filling": mt5.ORDER_FILLING_FOK,
}
print(json.dumps({"req": {k: (float(v) if isinstance(v, (int, float)) else v) for k, v in req.items()}}, indent=2))
r = mt5.order_send(req)
status = "CLOSED" if r and r.retcode == 10009 else f"FAILED_{getattr(r,'retcode',None)}"
print(json.dumps({"status": status, "retcode": getattr(r, 'retcode', None), "price_open": getattr(r, 'price_open', None), "comment": getattr(r, 'comment', None)}, indent=2))
mt5.shutdown()
