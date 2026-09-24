import requests, json, sys, math

BASE = "https://paper-api.alpaca.markets/v2"
KEY = "PKXJMRKXOJILYBZ6TMFAKHQDZY"
SEC = "7KQioWBVjuwTRAGZCBm3xBVFsn4wBQZr6cwUrSXME2WE"
HEADERS = {"APCA-API-KEY-ID": KEY, "APCA-API-SECRET-KEY": SEC}

def get_positions():
    r = requests.get(f"{BASE}/positions", headers=HEADERS)
    r.raise_for_status()
    return r.json()

def get_orders(symbol=None):
    params = {}
    if symbol:
        params["symbol"] = symbol
    r = requests.get(f"{BASE}/orders", headers=HEADERS, params=params)
    r.raise_for_status()
    return r.json()

def cancel_order(order_id):
    r = requests.delete(f"{BASE}/orders/{order_id}", headers=HEADERS)
    return r.status_code

def place_stop(symbol, qty, side, stop_price):
    data = {
        "symbol": symbol,
        "qty": qty,
        "side": side,
        "type": "stop",
        "time_in_force": "day",
        "order_class": "simple",
        "stop_price": stop_price,
    }
    r = requests.post(f"{BASE}/orders", headers=HEADERS, json=data)
    if r.status_code not in (200, 201):
        print(f"  ERROR placing stop for {symbol}: {r.status_code} {r.text}")
        return None
    return r.json()

positions = get_positions()
print(json.dumps(positions, indent=2))

results = []
for pos in positions:
    symbol = pos.get("symbol")
    avg_entry = float(pos.get("avg_entry_price", 0))
    qty = pos.get("qty", "0")
    side = "sell" if float(qty) > 0 else "buy"
    current = float(pos.get("current_price", 0) or 0)
    if current == 0:
        continue
    if symbol == "LINKUSD":
        print(f"SKIP {symbol}: crypto stop not supported on this API build")
        continue
    if current > avg_entry:
        stop = round(max(avg_entry * 1.001, avg_entry + 0.01), 2)
        if stop >= current:
            stop = round(current * 0.999, 2)
    else:
        stop = round(current * 0.97, 2)
    open_orders = get_orders(symbol=symbol)
    for o in open_orders:
        oid = o.get("id")
        print(f"Canceling order {oid} for {symbol}")
        cancel_order(oid)
    order = place_stop(symbol, qty, side, stop)
    status = "OK" if order else "FAIL"
    results.append({"symbol": symbol, "entry": avg_entry, "current": current, "stop": stop, "in_profit": current > avg_entry, "status": status})

print("\nFINAL REPORT")
print(f"{'Symbol':<10} {'Entry':>10} {'Current':>10} {'Stop':>10} {'InProfit':>8} {'Status':>8}")
for r in results:
    profit = "YES" if r["in_profit"] else "NO"
    print(f"{r['symbol']:<10} {r['entry']:10.4f} {r['current']:10.4f} {r['stop']:10.4f} {profit:>8} {r['status']:>8}")
