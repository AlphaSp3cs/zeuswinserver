#!/usr/bin/env python3
"""
IBKR Paper Order Watch — Check status of specific order IDs and report fills.
"""
import sys, time, json
from pathlib import Path
import datetime

BASE = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
WORKFLOW = BASE / 'workflow'

try:
    from ib_insync import IB
    IBKR_AVAILABLE = True
except ImportError:
    IBKR_AVAILABLE = False
    print("ib_insync not available")
    sys.exit(1)

# Target order IDs from the corrected top-5 execution + nightshift SELL routing
TARGET_ORDERS = {
    184: {"symbol": "GBPUSD", "side": "BUY", "entry": 1.3551, "sl": 1.3508, "tp": 1.3594},
    186: {"symbol": "AUDUSD", "side": "BUY", "entry": 0.7091, "sl": 0.7059, "tp": 0.7123},
    188: {"symbol": "NZDUSD", "side": "BUY", "entry": 0.5897, "sl": 0.5866, "tp": 0.5928},
    190: {"symbol": "NZDJPY", "side": "BUY", "entry": 93.847, "sl": 93.276, "tp": 94.418},
    192: {"symbol": "GBPAUD", "side": "SELL", "entry": 1.9108, "sl": 1.9172, "tp": 1.9044},
    196: {"symbol": "USDNOK", "side": "SELL", "entry": 9.43011, "sl": 9.5058, "tp": 9.31282},
    200: {"symbol": "GBPNZD", "side": "SELL", "entry": 2.29457, "sl": 2.3061, "tp": 2.27283},
    204: {"symbol": "USDSGD", "side": "SELL", "entry": 1.27775, "sl": 1.2820, "tp": 1.26851},
}

def check_orders():
    ib = IB()
    try:
        ib.connect('127.0.0.1', 4002, clientId=2002, timeout=10)
        if not ib.isConnected():
            print("IBKR not connected on 4002")
            return []
        
        results = []
        trades = ib.trades()
        
        for order_id, info in TARGET_ORDERS.items():
            trade = next((t for t in trades if t.orderStatus.orderId == order_id), None)
            if trade:
                contract = trade.contract
                order = trade.order
                status = trade.orderStatus.status
                filled = trade.orderStatus.filled
                avg_fill = trade.orderStatus.avgFillPrice
                
                results.append({
                    "order_id": order_id,
                    "symbol": info["symbol"],
                    "side": info["side"],
                    "entry": info["entry"],
                    "sl": info["sl"],
                    "tp": info["tp"],
                    "status": status,
                    "filled": filled,
                    "avg_fill": avg_fill,
                    "broker": "IBKR_PAPER",
                    "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                })
            else:
                results.append({
                    "order_id": order_id,
                    "symbol": info["symbol"],
                    "side": info["side"],
                    "entry": info["entry"],
                    "sl": info["sl"],
                    "tp": info["tp"],
                    "status": "NOT_FOUND",
                    "filled": 0,
                    "avg_fill": None,
                    "broker": "IBKR_PAPER",
                    "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat()
                })
        
        return results
    except Exception as e:
        print(f"IBKR error: {e}")
        return []
    finally:
        try:
            ib.disconnect()
        except Exception:
            pass

if __name__ == "__main__":
    results = check_orders()
    
    print("=== IBKR Paper Order Watch ===")
    print(f"Checked: {datetime.datetime.now(datetime.timezone.utc).isoformat()}")
    print()
    
    for r in results:
        status = r["status"]
        filled = r["filled"]
        avg = r["avg_fill"]
        
        if status in ("Filled",):
            print(f"✓ {r['symbol']:12} {r['side']:4} FILLED {filled} @ {avg}")
        elif status in ("Submitted", "PendingSubmit"):
            print(f"⏳ {r['symbol']:12} {r['side']:4} SUBMITTED — waiting for market")
        elif status == "Cancelled":
            print(f"✗ {r['symbol']:12} {r['side']:4} CANCELLED")
        else:
            print(f"? {r['symbol']:12} {r['side']:4} {status}")
    
    # Save results
    out_file = WORKFLOW / f'ibkr_order_watch_{datetime.datetime.now(datetime.timezone.utc).strftime("%Y%m%dT%H%M%SZ")}.json'
    with open(out_file, 'w', encoding='utf-8') as f:
        json.dump({"orders": results, "checked_at": datetime.datetime.now(datetime.timezone.utc).isoformat()}, f, indent=2)
    
    # Count statuses
    filled = sum(1 for r in results if r["status"] == "Filled")
    submitted = sum(1 for r in results if r["status"] in ("Submitted", "PendingSubmit"))
    cancelled = sum(1 for r in results if r["status"] == "Cancelled")
    
    print(f"\nSummary: {filled} filled, {submitted} submitted, {cancelled} cancelled")
    print(f"Saved: {out_file}")
    
    # Exit with code for cron/monitoring
    if filled == len(results):
        sys.exit(0)  # All filled
    elif cancelled > 0:
        sys.exit(2)  # Some cancelled
    else:
        sys.exit(1)  # Still pending
