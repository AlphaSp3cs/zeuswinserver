#!/usr/bin/env python3
"""
Multi-Broker Position Check - Alpaca, eToro, IBKR
Loads credentials from .env and queries each broker for open positions.
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

results = {
    'timestamp': datetime.datetime.now().isoformat(),
    'brokers': {},
    'positions': {},
}

# ========== ALPACA ==========
ALPACA_KEY = os.environ.get('ALPACA_API_KEY', '')
ALPACA_SECRET = os.environ.get('ALPACA_API_SECRET', '')
ALPACA_BASE = os.environ.get('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets').rstrip('/')

results['brokers']['alpaca'] = {'connected': False}
if ALPACA_KEY and ALPACA_SECRET:
    try:
        headers = {'Apca-Api-Key-Id': ALPACA_KEY, 'Apca-Api-Secret-Key': ALPACA_SECRET}
        
        # Check account
        resp = requests.get(f'{ALPACA_BASE}/account', headers=headers, timeout=10)
        if resp.status_code == 200:
            account = resp.json()
            results['brokers']['alpaca'] = {
                'connected': True,
                'account': account,
            }
            
            # Get positions
            resp_pos = requests.get(f'{ALPACA_BASE}/positions', headers=headers, timeout=10)
            if resp_pos.status_code == 200:
                positions = resp_pos.json()
                results['positions']['alpaca'] = []
                for p in positions:
                    results['positions']['alpaca'].append({
                        'symbol': p.get('symbol'),
                        'qty': p.get('qty'),
                        'avg_entry_price': p.get('avg_entry_price'),
                        'market_value': p.get('market_value'),
                        'unrealized_pl': p.get('unrealized_pl'),
                        'side': 'LONG' if float(p.get('qty', 0)) > 0 else 'SHORT',
                    })
        else:
            results['brokers']['alpaca']['status_code'] = resp.status_code
            results['brokers']['alpaca']['error'] = resp.text[:200]
    except Exception as e:
        results['brokers']['alpaca']['error'] = str(e)
else:
    results['brokers']['alpaca']['reason'] = 'no credentials'

# ========== ETORO ==========
ETORO_KEY = os.environ.get('ETORO_API_KEY', '')
ETORO_USER_KEY = os.environ.get('ETORO_USER_KEY', '')
ETORO_BASE = 'https://public-api.etoro.com/api/v1'

results['brokers']['etoro'] = {'connected': False}
if ETORO_KEY and ETORO_USER_KEY:
    try:
        headers = {'x-api-key': ETORO_KEY, 'x-user-key': ETORO_USER_KEY}
        
        # Get demo and real positions
        positions = []
        etoro_fatal = False
        for account_type in ['demo', 'real']:
            resp = requests.get(f'{ETORO_BASE}/trading/info/{account_type}/pnl', headers=headers, timeout=10)
            if resp.status_code == 401:
                # Key is dead/exhausted — tell the user to get a new one (once).
                etoro_fatal = True
                try:
                    from etoro_auth import notify_key_exhausted
                    notify_key_exhausted(
                        detail=f"HTTP 401 from /trading/info/{account_type}/pnl — eToro key rejected",
                        provider="eToro",
                    )
                except Exception:
                    pass
                break
            if resp.status_code == 200:
                data = resp.json()
                client_portfolio = data.get('clientPortfolio', {})
                for pos in client_portfolio.get('positions', []):
                    # Skip copy-trade mirrors
                    if pos.get('mirrorID', 0) > 0:
                        continue
                    positions.append({
                        'broker': f'etoro_{account_type}',
                        'position_id': pos.get('positionID'),
                        'instrument_id': pos.get('instrumentID'),
                        'symbol': pos.get('instrumentDisplayName', ''),
                        'direction': pos.get('direction', ''),
                        'units': pos.get('units', 0),
                        'open_rate': pos.get('openRate', 0),
                        'current_rate': pos.get('currentRate', 0),
                        'unrealized_pl': pos.get('pl', 0),
                        'leverage': pos.get('leverage', 1),
                    })
        
        results['brokers']['etoro'] = {
            'connected': not etoro_fatal,
            'total_positions': len(positions),
        }
        if etoro_fatal:
            results['brokers']['etoro']['error'] = 'key_exhausted_401'
            results['brokers']['etoro']['action'] = 'get_new_api_key'
        results['positions']['etoro'] = positions
    except Exception as e:
        results['brokers']['etoro']['error'] = str(e)
else:
    results['brokers']['etoro']['reason'] = 'no credentials'

# ========== IBKR ==========
IBKR_HOST = os.environ.get('IBKR_HOST', '127.0.0.1')
IBKR_PORT = int(os.environ.get('IBKR_PORT', '7497'))
IBKR_CLIENT_ID = int(os.environ.get('IBKR_CLIENT_ID', '1'))
IBKR_ACCOUNT = os.environ.get('IBKR_ACCOUNT', '')

results['brokers']['ibkr'] = {'connected': False}
try:
    from ibapi.client import EClient
    from ibapi.wrapper import EWrapper
    
    class IBKRPuller(EWrapper, EClient):
        def __init__(self):
            EClient.__init__(self, self)
            self.positions = []
            self.account_values = {}
            self.done = False
        
        def nextValidId(self, orderId):
            # Request account values
            self.reqPositions()
        
        def position(self, account, contract, position, avgCost):
            self.positions.append({
                'account': account,
                'symbol': contract.symbol,
                'sec_type': contract.secType,
                'exchange': contract.exchange,
                'position': position,
                'avg_cost': avgCost,
            })
        
        def positionEnd(self):
            self.done = True
            self.disconnect()
    
    app = IBKRPuller()
    app.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID)
    
    # Wait for data
    import time
    timeout = 5
    start = time.time()
    while not app.done and time.time() - start < timeout:
        app.run()
        time.sleep(0.1)
    
    if app.positions:
        results['brokers']['ibkr'] = {
            'connected': True,
            'account': IBKR_ACCOUNT,
            'total_positions': len(app.positions),
        }
        results['positions']['ibkr'] = app.positions
    else:
        results['brokers']['ibkr'] = {
            'connected': True,
            'account': IBKR_ACCOUNT,
            'total_positions': 0,
            'note': 'connected but no positions returned',
        }
    
    app.disconnect()
except ImportError:
    results['brokers']['ibkr']['reason'] = 'ibapi not installed'
except Exception as e:
    results['brokers']['ibkr']['error'] = str(e)

# ========== SAVE & REPORT ==========
out = Path('all_broker_positions_2026-07-26.json')
out.write_text(json.dumps(results, indent=2))
print('Saved:', out)

print('\n' + '='*70)
print('ALL BROKER POSITIONS SUMMARY')
print('='*70)
print(f"Timestamp: {results['timestamp']}")
print(f"\nBroker Connectivity:")
for broker, data in results['brokers'].items():
    status = '✅ CONNECTED' if data.get('connected') else '❌ FAILED'
    reason = data.get('reason', data.get('error', ''))
    print(f"  {broker}: {status}" + (f" ({reason})" if reason else ""))
    if data.get('total_positions'):
        print(f"    Positions: {data['total_positions']}")

print(f"\nPositions by Broker:")
for broker, positions in results['positions'].items():
    print(f"\n  {broker.upper()}: {len(positions)} positions")
    for p in positions:
        if broker == 'etoro':
            print(f"    {p['symbol']:20} {p['direction']:6} units={p['units']} PnL={p['unrealized_pl']}")
        elif broker == 'ibkr':
            print(f"    {p['symbol']:20} {p['sec_type']:8} pos={p['position']} avgCost={p['avg_cost']}")
        else:
            print(f"    {p}")

print('\n' + '='*70)
print('Awuuuu!!!! the pack is finished.')
print('='*70)
