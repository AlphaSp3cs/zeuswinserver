import MetaTrader5 as mt5
from pathlib import Path
import time

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

print(f"Initializing Capital.com MT5...")
if mt5.initialize(
    path=config["path"],
    login=config["login"],
    password=config["password"],
    server=config["server"]
):
    acc = mt5.account_info()
    print(f"Connected: Balance={acc.balance}, Equity={acc.equity}")
    
    positions = mt5.positions_get()
    print(f"Positions found: {len(positions) if positions else 0}")
    
    # Focus on the failing tickets
    target_tickets = [4809937, 4809938]
    for pos in positions:
        if pos.ticket in target_tickets:
            print(f"\nFound target ticket={pos.ticket}, Symbol={pos.symbol}")
            print(f"  Entry={pos.price_open}, Current={pos.price_current}")
            print(f"  SL={pos.sl}, TP={pos.tp}")
            
            new_sl = round(pos.price_open, 5)
            req = {
                "action": mt5.TRADE_ACTION_SLTP,
                "symbol": pos.symbol,
                "position": pos.ticket,
                "sl": new_sl,
                "tp": pos.tp
            }
            print(f"  Request: sl={new_sl}, tp={pos.tp}")
            result = mt5.order_send(req)
            if result:
                print(f"  Result object: retcode={result.retcode}, comment={result.comment}")
                print(f"  retcode name: {mt5.TRADE_RETCODE_DONE}")
            else:
                print(f"  Result: None (script would say 'order_send returned None')")
    
    mt5.shutdown()
else:
    err = mt5.last_error()
    print(f"Init failed: {err}")
