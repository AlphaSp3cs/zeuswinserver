import os, sys, json, traceback, time
from datetime import datetime, timezone
PROJECT = r"C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm"
os.chdir(PROJECT)
sys.path.insert(0, os.path.join(PROJECT, "scripts"))
import MetaTrader5 as mt5

FTMO_PATH = r"C:\Program Files\FTMO Global Markets MT5 Terminal\terminal64.exe"

def try_init(label):
    mt5.shutdown()
    t0 = time.time()
    ok = mt5.initialize(path=FTMO_PATH, login=0, password="", server="", timeout=15000)
    elapsed = round(time.time() - t0, 2)
    err = mt5.last_error() if not ok else None
    ai = mt5.account_info() if ok else None
    res = {
        "label": label,
        "ok": bool(ok),
        "elapsed_sec": elapsed,
        "last_error": str(err) if err else None,
        "login": int(getattr(ai, 'login', 0) or 0) if ai else None,
        "trade_allowed": bool(getattr(ai, 'trade_allowed', False)) if ai else None,
        "equity": float(getattr(ai, 'equity', 0) or 0) if ai else None,
        "balance": float(getattr(ai, 'balance', 0) or 0) if ai else None,
    }
    try:
        positions = mt5.positions_get() or []
        res["positions_count"] = len(positions)
        res["positions"] = [{"symbol": p.symbol, "ticket": int(p.ticket), "profit": float(p.profit), "type": int(p.type)} for p in positions[:20]]
    except Exception as e:
        res["positions_error"] = str(e)
    mt5.shutdown()
    return res

out = {
    "generated": datetime.now(timezone.utc).isoformat(),
    "init1": try_init("init1"),
    "init2": try_init("init2"),
    "init3": try_init("init3"),
}
print(json.dumps(out, indent=2))
