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
    
    for pos in positions:
        entry = pos.price_open
        current = pos.price_current
        if pos.type == mt5.POSITION_TYPE_BUY:
            pnl_pct = ((current - entry) / entry) * 100
        else:
            pnl_pct = ((entry - current) / entry) * 100
        
        print(f"  Ticket={pos.ticket}, Symbol={pos.symbol}, Type={'BUY' if pos.type==0 else 'SELL'}, Entry={entry}, Current={current}, PnL%={pnl_pct:.4f}%, SL={pos.sl}, TP={pos.tp}")
    
    # Test calculate_new_sl logic for LINKUSD ticket 4809937
    for pos in positions:
        if pos.ticket == 4809937:
            entry = pos.price_open
            current = pos.price_current
            if pos.type == mt5.POSITION_TYPE_BUY:
                pnl_pct = ((current - entry) / entry) * 100
            else:
                pnl_pct = ((entry - current) / entry) * 100
            print(f"\nLINKUSD debug:")
            print(f"  entry={entry}, current={current}")
            print(f"  pnl_pct={pnl_pct:.4f}%")
            print(f"  pnl_pct >= 2? {pnl_pct >= 2}")
            print(f"  round(pnl_pct, 2) = {round(pnl_pct, 2)}")
            if 2 <= pnl_pct < 5:
                print(f"  Would trigger BREAKEVEN: new_sl = {entry}")
            elif pnl_pct >= 5:
                print(f"  Would trigger TRAIL_2%: new_sl = {current * 0.98}")
            else:
                print(f"  No action (pnl < 2%)")
    
    mt5.shutdown()
else:
    err = mt5.last_error()
    print(f"Init failed: {err}")
