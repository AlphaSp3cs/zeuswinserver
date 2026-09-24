import MetaTrader5 as mt5
from pathlib import Path

creds = {}
api_path = Path("C:/Users/bravo-usr1/Desktop/allapi2026.txt")
if api_path.exists():
    with open(api_path) as f:
        lines = f.read().splitlines()
    for i, line in enumerate(lines):
        line = line.strip()
        if line.startswith("Capital.com MT5"):
            parts = line.split()
            creds['CAPITAL'] = {
                'login': int(parts[2]),
                'password': parts[3],
                'server': parts[4]
            }

cap = creds.get('CAPITAL', {})
config = {
    "path": r"C:\Program Files\Capital.com MetaTrader 5\terminal64.exe",
    "login": cap.get('login', 1028685),
    "password": cap.get('password', ''),
    "server": cap.get('server', 'Capital.ComBah-Demo')
}

if mt5.initialize(path=config["path"], login=config["login"], password=config["password"], server=config["server"]):
    positions = mt5.positions_get()
    for pos in positions:
        if pos.ticket == 4809937:
            new_sl = round(pos.price_open, 5)
            req1 = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": pos.symbol,
                "position": pos.ticket,
                "sl": new_sl,
                "tp": 0
            }
            print(f"Test 1: tp=0")
            r1 = mt5.order_send(req1)
            print(f"  result: {r1.retcode if r1 else 'None'}, comment: {r1.comment if r1 else 'None'}")
            
            req2 = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": pos.symbol,
                "position": pos.ticket,
                "sl": new_sl,
                "tp": pos.tp
            }
            print(f"Test 2: tp={pos.tp}")
            r2 = mt5.order_send(req2)
            print(f"  result: {r2.retcode if r2 else 'None'}, comment: {r2.comment if r2 else 'None'}")
    mt5.shutdown()
else:
    print(f"Init failed: {mt5.last_error()}")
