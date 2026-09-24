import json, os, sys, traceback, time
from datetime import datetime, timezone
PROJECT = r"C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm"
os.chdir(PROJECT)
sys.path.insert(0, os.path.join(PROJECT, "scripts"))
import MetaTrader5 as mt5

FTMO_PATH = r"C:\Program Files\FTMO Global Markets MT5 Terminal\terminal64.exe"

def mt5_state(label):
    mt5.shutdown()
    ok = mt5.initialize(path=FTMO_PATH, login=0, password="", server="", timeout=15000)
    state = {"label": label, "ok": bool(ok), "last_error": str(mt5.last_error()) if not ok else None}
    if ok:
        ai = mt5.account_info()
        state.update({
            "login": int(getattr(ai, 'login', 0) or 0),
            "trade_allowed": bool(getattr(ai, 'trade_allowed', False)),
            "equity": float(getattr(ai, 'equity', 0) or 0),
            "balance": float(getattr(ai, 'balance', 0) or 0),
        })
        try:
            state["positions_count"] = len(mt5.positions_get() or [])
        except Exception as e:
            state["positions_error"] = str(e)
    mt5.shutdown()
    return state

def send_order(sym, ticket, volume, order_type):
    mt5.shutdown()
    ok = mt5.initialize(path=FTMO_PATH, login=0, password="", server="", timeout=15000)
    if not ok:
        return {"status": "INIT_FAIL", "error": str(mt5.last_error())}
    tick = mt5.symbol_info_tick(sym)
    if tick is None:
        return {"status": "NO_TICK"}
    price = tick.bid if order_type == mt5.ORDER_TYPE_SELL else tick.ask
    req = {
        "action": mt5.TRADE_ACTION_DEAL,
        "symbol": sym,
        "volume": volume,
        "type": order_type,
        "position": ticket,
        "price": price,
        "deviation": 20,
        "magic": 20260819,
        "comment": "start_fresh_close_profit_v4",
        "type_time": mt5.ORDER_TIME_GTC,
        "type_filling": mt5.ORDER_FILLING_FOK,
    }
    r = mt5.order_send(req)
    status = "CLOSED" if r and r.retcode == 10009 else f"FAILED_{getattr(r,'retcode',None)}"
    mt5.shutdown()
    return {"status": status, "retcode": getattr(r, 'retcode', None), "price": float(price)}

out = {
    "generated": datetime.now(timezone.utc).isoformat(),
    "state": mt5_state("before"),
    "attempts": [],
    "state_after": mt5_state("after")
}
for sym, ticket in [("ETHUSD", 521145632), ("EURUSD", 521145636), ("LTCUSD", 521187867)]:
    mt5.shutdown()
    ok = mt5.initialize(path=FTMO_PATH, login=0, password="", server="", timeout=15000)
    if not ok:
        out["attempts"].append({"symbol": sym, "ticket": ticket, "status": "INIT_FAIL"})
        continue
    positions = mt5.positions_get(ticket=ticket) or []
    mt5.shutdown()
    if not positions:
        out["attempts"].append({"symbol": sym, "ticket": ticket, "status": "NO_POSITION"})
        continue
    p = positions[0]
    order_type = mt5.ORDER_TYPE_SELL if p.type in (mt5.ORDER_TYPE_BUY, 0) else mt5.ORDER_TYPE_BUY
    out["attempts"].append({"symbol": sym, "ticket": ticket, "result": send_order(sym, ticket, p.volume, order_type)})

print(json.dumps(out, indent=2))
