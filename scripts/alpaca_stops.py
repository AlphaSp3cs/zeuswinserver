import requests
import json
from datetime import datetime

API_BASE = "https://paper-api.alpaca.markets/v2"
HEADERS = {
    "APCA-API-KEY-ID": "PKXJMRKXOJILYBZ6TMFAKHQDZY",
    "APCA-API-SECRET-KEY": "7KQioWBVjuwTRAGZCBm3xBVFsn4wBQZr6cwUrSXME2WE",
    "Content-Type": "application/json"
}

def log(msg):
    print(f"[{datetime.now().strftime(chr(37)+"H:"+chr(37)+"M:"+chr(37)+"S")}] {msg}", flush=True)

log("Fetching open positions...")
resp = requests.get(f"{API_BASE}/positions", headers=HEADERS)
positions = resp.json()
if isinstance(positions, dict) and "error" in positions:
    positions = []
elif not isinstance(positions, list):
    positions = []
log(f"Found {len(positions)} open positions")

log("Fetching open orders...")
resp = requests.get(f"{API_BASE}/orders", params={"status": "open"}, headers=HEADERS)
orders = resp.json()
if isinstance(orders, dict) and "error" in orders:
    orders = []
elif not isinstance(orders, list):
    orders = []
log(f"Found {len(orders)} open orders")

orders_by_symbol = {}
for o in orders:
    sym = o.get("symbol", "")
    orders_by_symbol.setdefault(sym, []).append(o)

results = []

for pos in positions:
    symbol = pos.get("symbol", "")
    qty = float(pos.get("qty", 0))
    avg_entry = float(pos.get("avg_entry_price", 0))
    current_price = float(pos.get("current_price", 0))
    market_value = float(pos.get("market_value", 0))
    if current_price == 0 and market_value and qty != 0:
        current_price = abs(market_value / qty)
    in_profit = current_price > avg_entry
    log(f"
Processing {symbol}: qty={qty}, avg_entry={avg_entry}, current={current_price}")
    if symbol == "LINKUSD":
        log(f"  SKIP {symbol} - crypto stop orders not supported")
        results.append({"symbol": symbol, "qty": qty, "avg_entry": avg_entry, "current": round(current_price, 2), "stop": "N/A (crypto)", "in_profit": in_profit, "action": "SKIPPED"})
        continue
    existing = orders_by_symbol.get(symbol, [])
    for o in existing:
        otype = o.get("type", "").lower()
        if otype in ("stop", "stop_limit", "take_profit", "limit") or "stop" in otype:
            order_id = o["id"]
            log(f"  Cancelling order {order_id} ({otype})")
            del_resp = requests.delete(f"{API_BASE}/orders/{order_id}", headers=HEADERS)
            log(f"    Status: {del_resp.status_code}")
    if in_profit:
        stop_val = max(avg_entry * 1.001, avg_entry + 0.01)
        stop_price = round(stop_val, 2)
        if stop_price >= current_price:
            stop_price = round(current_price * 0.999, 2)
    else:
        stop_price = round(current_price * 0.97, 2)
    stop_price = round(stop_price, 2)
    log(f"  in_profit={in_profit}, stop={stop_price}")
    order_data = {
        "symbol": symbol,
        "qty": str(abs(qty)),
        "side": "sell",
        "type": "stop",
        "time_in_force": "day",
        "stop_price": stop_price,
        "order_class": "simple"
    }
    place_resp = requests.post(f"{API_BASE}/orders", headers=HEADERS, json=order_data)
    order_result = place_resp.json()
    if place_resp.status_code in (200, 201) and isinstance(order_result, dict) and not order_result.get("error"):
        log(f"  STOP order placed: id={order_result.get(chr(105)+"d")}, stop_price={stop_price}")
        results.append({"symbol": symbol, "qty": qty, "avg_entry": round(avg_entry, 2), "current": round(current_price, 2), "stop": stop_price, "in_profit": in_profit, "action": "PLACED"})
    else:
        err_msg = order_result.get("message", str(order_result)) if isinstance(order_result, dict) else str(order_result)
        log(f"  FAILED: {place_resp.status_code} {err_msg}")
        results.append({"symbol": symbol, "qty": qty, "avg_entry": round(avg_entry, 2), "current": round(current_price, 2), "stop": f"FAILED ({err_msg})", "in_profit": in_profit, "action": "FAILED"})

print("
" + "="*90)
print("FINAL STOP-LOSS RE-ARM REPORT")
print("="*90)
print(f"{'Symbol':<12} {'Qty':>10} {'Entry':>10} {'Current':>10} {'Stop':>10} {'In Profit':>10} {'Action':>10}")
print("-"*90)
for r in results:
    qty_str = f"{r['qty']:.4f}"
    in_profit_str = "YES" if r['in_profit'] else "NO"
    print(f"{r['symbol']:<12} {qty_str:>10} {str(r['avg_entry']):>10} {str(r['current']):>10} {str(r['stop']):>10} {in_profit_str:>10} {r['action']:>10}")
print("="*90)
placed = sum(1 for r in results if r['action'] == 'PLACED')
skipped = sum(1 for r in results if r['action'] == 'SKIPPED')
failed = sum(1 for r in results if r['action'] == 'FAILED')
print(f"Total: {len(results)} | Placed: {placed} | Skipped: {skipped} | Failed: {failed}")
