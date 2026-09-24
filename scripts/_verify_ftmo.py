import os, sys, json, traceback
from datetime import datetime, timezone
PROJECT = r"C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm"
os.chdir(PROJECT)
sys.path.insert(0, os.path.join(PROJECT, "scripts"))
import MetaTrader5 as mt5
FTMO_PATH = r"C:\Program Files\FTMO Global Markets MT5 Terminal\terminal64.exe"
mt5.shutdown()
ok = mt5.initialize(path=FTMO_PATH, login=0, password="", server="", timeout=15000)
print(json.dumps({"init": ok, "last_error": str(mt5.last_error()) if not ok else None, "trade_allowed": bool(mt5.account_info().trade_allowed), "login": int(mt5.account_info().login)}, indent=2))
positions = mt5.positions_get() or []
print(json.dumps({"positions_count": len(positions), "positions": [{"ticket": int(p.ticket), "symbol": p.symbol, "profit": float(p.profit), "volume": float(p.volume), "type": int(p.type)} for p in positions]}, indent=2))
history = mt5.history_deals_get(datetime(2026,8,18), datetime(2026,8,20)) or []
print(json.dumps({"history_deals": len(history), "deals": [{"ticket": int(d.ticket), "symbol": d.symbol, "profit": float(d.profit), "type": int(d.type), "entry": int(d.entry)} for d in history[-20:]]}, indent=2))
mt5.shutdown()
