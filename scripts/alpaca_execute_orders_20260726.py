#!/usr/bin/env python3
"""
Alpaca Order Executor - Execute high probability swing trades
"""

import sys, os
sys.path.insert(0, 'C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
os.chdir('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')

from pathlib import Path
import json
import datetime
import requests

# Load .env
env_path = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/.env')
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")

ALPACA_KEY = os.environ.get('ALPACA_API_KEY', '')
ALPACA_SECRET = os.environ.get('ALPACA_API_SECRET', '')
ALPACA_BASE = os.environ.get('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets').rstrip('/')

def main():
    print("="*70)
    print("ALPACA ORDER EXECUTOR")
    print("="*70)
    
    if not ALPACA_KEY or not ALPACA_SECRET:
        print("ERROR: Alpaca credentials not found")
        return
    
    headers = {'Apca-Api-Key-Id': ALPACA_KEY, 'Apca-Api-Secret-Key': ALPACA_SECRET}
    
    # Check account
    resp = requests.get(f'{ALPACA_BASE}/account', headers=headers, timeout=10)
    if resp.status_code != 200:
        print(f"ERROR: Alpaca account check failed: {resp.status_code} {resp.text[:200]}")
        return
    
    account = resp.json()
    print(f"Account: {account.get('id')}")
    print(f"Status: {account.get('status')}")
    print(f"Buying Power: ${account.get('buying_power', 0)}")
    print(f"Equity: ${account.get('equity', 0)}")
    
    # Get current positions
    resp_pos = requests.get(f'{ALPACA_BASE}/positions', headers=headers, timeout=10)
    positions = resp_pos.json() if resp_pos.status_code == 200 else []
    print(f"Current positions: {len(positions)}")
    
    order_results = []
    
    # With $0.89 buying power, we can only place very small fractional orders
    # Let's try to add small positions to high probability symbols
    high_prob_symbols = []
    
    # Check if we have any buying power left
    bp = float(account.get('buying_power', 0))
    if bp < 1.0:
        print(f"\nWARNING: Buying power too low (${bp:.2f}) for new trades")
        print("Skipping Alpaca order placement")
    else:
        # Try to place small fractional orders
        test_symbols = ['SPY', 'QQQ', 'IWM', 'GLD']
        for symbol in test_symbols:
            # Check if already held
            held = any(p['symbol'] == symbol for p in positions)
            if held:
                print(f"  {symbol}: already held, skipping")
                continue
            
            # Calculate quantity for ~$0.50 position
            # We'll need to get current price first
            try:
                # Use last trade price from positions API if available
                # For now, skip price lookup and use fixed small quantity
                qty = 0.001  # Very small fractional
                
                order = {
                    'symbol': symbol,
                    'qty': qty,
                    'side': 'buy',
                    'type': 'market',
                    'time_in_force': 'day',
                }
                
                resp_order = requests.post(
                    f'{ALPACA_BASE}/orders',
                    headers={**headers, 'Content-Type': 'application/json'},
                    json=order,
                    timeout=10
                )
                
                if resp_order.status_code in [200, 201]:
                    result = resp_order.json()
                    order_results.append({
                        'symbol': symbol,
                        'status': 'submitted',
                        'order_id': result.get('id'),
                        'qty': qty,
                    })
                    print(f"  {symbol}: ORDER PLACED (qty={qty})")
                else:
                    order_results.append({
                        'symbol': symbol,
                        'status': 'failed',
                        'error': resp_order.text[:100],
                    })
                    print(f"  {symbol}: FAILED - {resp_order.status_code}")
            except Exception as e:
                print(f"  {symbol}: ERROR - {e}")
    
    # Save results
    results = {
        'timestamp': datetime.datetime.now().isoformat(),
        'account': account,
        'positions_count': len(positions),
        'order_results': order_results,
    }
    
    out = Path('alpaca_execution_results_2026-07-26.json')
    out.write_text(json.dumps(results, indent=2))
    print(f"\nSaved: {out}")
    
    print('\n' + '='*70)
    print('Awuuuu!!!! the pack is finished.')
    print('='*70)


if __name__ == '__main__':
    main()
