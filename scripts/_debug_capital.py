import MetaTrader5 as mt5
from pathlib import Path

# Load allapi2026.txt fallback
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
    if positions:
        for pos in positions:
            print(f"  Ticket={pos.ticket}, Symbol={pos.symbol}, Type={'BUY' if pos.type==0 else 'SELL'}, SL={pos.sl}, TP={pos.tp}, Entry={pos.price_open}")
    
    # Test modification on first position if exists
    if positions and len(positions) > 0:
        pos = positions[0]
        new_sl = pos.price_open
        req = {
            "action": mt5.TRADE_ACTION_SLTP,
            "symbol": pos.symbol,
            "position": pos.ticket,
            "sl": new_sl,
            "tp": pos.tp
        }
        print(f"Testing SL mod on ticket {pos.ticket} (symbol={pos.symbol})...")
        result = mt5.order_send(req)
        if result:
            print(f"  Result: retcode={result.retcode}, comment={result.comment}, order={result.order}, deal={result.deal}")
        else:
            print(f"  Result: order_send returned None")
    
    mt5.shutdown()
else:
    err = mt5.last_error()
    print(f"Init failed: {err}")
