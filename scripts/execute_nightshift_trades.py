#!/usr/bin/env python3
"""
execute_nightshift_trades.py
- Loads latest comprehensive sector scan
- Filters high conviction (>=7) longs and shorts
- Attempts to place demo trades on eToro and live trades on IBKR (port 4002)
- Uses small fixed size for safety
"""
import json, sys, time, uuid
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
WORKFLOW = BASE / 'workflow'
SCANDATA = BASE / 'scandata'
CREDS_PATH = BASE / '.broker_creds_secure.json'

# Add scripts to path
sys.path.insert(0, str(BASE / 'scripts'))

# Load eToro credentials
import requests
_creds = json.loads(CREDS_PATH.read_text(encoding='utf-8')) if CREDS_PATH.exists() else {}
ETORO_API_KEY = _creds.get('etoro', {}).get('api_key', '')
ETORO_USER_KEY = _creds.get('etoro', {}).get('user_key', '')
ETORO_BASE = 'https://public-api.etoro.com'

def etoro_headers():
    return {
        'x-request-id': str(uuid.uuid4()),
        'x-api-key': ETORO_API_KEY,
        'x-user-key': ETORO_USER_KEY,
        'Accept': 'application/json',
    }

def load_symbol_map():
    sym_path = WORKFLOW / 'etoro_symbol_map.json'
    if sym_path.exists():
        return json.loads(sym_path.read_text(encoding='utf-8'))
    return {}

def find_etoro_instrument_id(symbol: str, symbol_map: dict):
    """Convert common symbol formats to eToro instrument ID"""
    norm = symbol.upper().replace('-USD', '').replace('USD', '').strip()
    for key in [norm, symbol.upper(), f'{norm}-USD']:
        info = symbol_map.get(key)
        if info:
            return info.get('id')
    return None

def place_etoro_demo_order(instrument_id, action, amount_usd=50.0, leverage=1):
    """Place a small demo market order on eToro"""
    url = f'{ETORO_BASE}/api/v2/trading/execution/demo/orders'
    payload = {
        'action': 'open',
        'transaction': action.lower(),
        'instrumentID': int(instrument_id) if str(instrument_id).isdigit() else instrument_id,
        'orderType': 'mkt',
        'leverage': leverage,
        'amount': amount_usd,
        'orderCurrency': 'usd',
    }
    try:
        r = requests.post(url, headers=etoro_headers(), json=payload, timeout=15)
        return {
            'status_code': r.status_code,
            'response': r.text[:500],
            'payload': payload,
        }
    except Exception as e:
        return {'status_code': 0, 'response': str(e), 'payload': payload}

# IBKR connection
from ib_insync import *
def connect_ibkr():
    ib = IB()
    try:
        ib.connect('127.0.0.1', 4002, clientId=2002, timeout=10)
        if not ib.isConnected():
            print('IBKR connection failed')
            return None
        print('IBKR connected: account', ib.accountValues()[0].value if ib.accountValues() else 'unknown')
        return ib
    except Exception as e:
        print(f'IBKR connection error: {e}')
        return None

def place_ibkr_order(ib, symbol, action, quantity=0.01):
    """Place a market order on IBKR
    For forex: quantity in lots (0.01 = micro lot)
    For stocks: quantity in shares
    For crypto: depends on contract
    We'll try to determine contract type.
    """
    try:
        # Determine contract type
        if symbol.endswith('=X') or '/' in symbol:
            # Forex pair
            if '/' in symbol:
                base, quote = symbol.split('/')
            else:
                base = symbol.replace('=X', '')[:3]
                quote = symbol.replace('=X', '')[3:6]
            contract = Forex(f'{base}{quote}')
        elif symbol.endswith('=F'):
            # Futures
            contract = Futures(symbol[:-2], '202609', 'CME')  # approximate
        elif '-' in symbol and 'USD' in symbol:
            # Crypto pair like BTC-USD -> we need to map to a crypto contract
            # IBKR offers crypto via Paxos or others, but let's skip for now
            print(f'Skipping crypto {symbol} on IBKR (not supported)')
            return None
        else:
            # Assume stock
            contract = Stock(symbol, 'SMART', 'USD')
        
        # Get market data to validate
        ib.reqMarketDataType(4)  # frozen data
        ticker = ib.reqMktData(contract, '', False, False)
        time.sleep(2)  # wait for data
        if ticker.bid == -1 or ticker.ask == -1:
            print(f'No market data for {symbol}')
            ib.cancelMktData(contract)
            return None
        
        # Create order
        action = 'BUY' if action.lower() == 'buy' else 'SELL'
        order = MarketOrder(action, quantity)
        order.transmit = True
        
        # Place trade
        trade = ib.placeOrder(contract, order)
        print(f'Placed IBKR order: {action} {quantity} {symbol} @ ~{ticker.marketPrice()}')
        
        # Wait a bit for fill
        time.sleep(3)
        if trade.orderStatus.status == 'Filled':
            print(f'  Filled: avg price {trade.orderStatus.avgFillPrice}')
        else:
            print(f'  Status: {trade.orderStatus.status}')
        
        # Clean up
        ib.cancelMktData(contract)
        return trade
    except Exception as e:
        print(f'IBKR order error for {symbol}: {e}')
        import traceback; traceback.print_exc()
        return None

def main():
    # Load latest comprehensive scan
    scan_files = list(WORKFLOW.glob('comprehensive_all_sector_scan_*.json'))
    if not scan_files:
        print('No scan files found')
        return
    latest_scan = max(scan_files, key=lambda p: p.stat().st_mtime)
    print(f'Loading scan: {latest_scan.name}')
    scan_data = json.loads(latest_scan.read_text())
    
    longs = [s for s in scan_data.get('longs', []) if s.get('conviction', 0) >= 7]
    shorts = [s for s in scan_data.get('shorts', []) if s.get('conviction', 0) >= 7]
    
    print(f'High conviction longs: {len(longs)}')
    print(f'High conviction shorts: {len(shorts)}')
    
    # Setup eToro
    symbol_map = load_symbol_map()
    print(f'eToro symbol map loaded: {len(symbol_map)} entries')
    
    # Setup IBKR
    ib = connect_ibkr()
    if not ib:
        print('IBKR not connected, skipping IBKR trades')
    
    results = []
    
    # Process longs
    for setup in longs[:5]:  # limit to first 5 for safety
        symbol = setup['ticker']
        conviction = setup['conviction']
        price = setup['price']
        print(f'\nProcessing LONG {symbol} (conv {conviction}, price {price})')
        
        # eToro
        etoro_id = find_etoro_instrument_id(symbol, symbol_map)
        if etoro_id:
            print(f'  eToro instrument ID: {etoro_id}')
            etoro_res = place_etoro_demo_order(etoro_id, 'buy', amount_usd=25.0)
            print(f'  eToro result: {etoro_res["status_code"]} {etoro_res["response"][:100]}')
            results.append({
                'symbol': symbol,
                'action': 'LONG',
                'broker': 'etoro',
                'status': 'placed' if etoro_res['status_code'] == 200 else 'failed',
                'conviction': conviction,
                'price': price,
                'details': etoro_res
            })
        else:
            print(f'  eToro: no instrument ID found for {symbol}')
        
        # IBKR
        if ib:
            trade = place_ibkr_order(ib, symbol, 'buy', quantity=0.01 if '=' in symbol or len(symbol) <= 6 else 1)
            results.append({
                'symbol': symbol,
                'action': 'LONG',
                'broker': 'ibkr',
                'status': 'placed' if trade and trade.orderStatus.status == 'Filled' else 'failed',
                'conviction': conviction,
                'price': price,
                'details': trade.orderStatus.status if trade else 'error'
            })
    
    # Process shorts (similar)
    for setup in shorts[:5]:
        symbol = setup['ticker']
        conviction = setup['conviction']
        price = setup['price']
        print(f'\nProcessing SHORT {symbol} (conv {conviction}, price {price})')
        
        # eToro
        etoro_id = find_etoro_instrument_id(symbol, symbol_map)
        if etoro_id:
            print(f'  eToro instrument ID: {etoro_id}')
            etoro_res = place_etoro_demo_order(etoro_id, 'sell', amount_usd=25.0)
            print(f'  eToro result: {etoro_res["status_code"]} {etoro_res["response"][:100]}')
            results.append({
                'symbol': symbol,
                'action': 'SHORT',
                'broker': 'etoro',
                'status': 'placed' if etoro_res['status_code'] == 200 else 'failed',
                'conviction': conviction,
                'price': price,
                'details': etoro_res
            })
        else:
            print(f'  eToro: no instrument ID found for {symbol}')
        
        # IBKR
        if ib:
            trade = place_ibkr_order(ib, symbol, 'sell', quantity=0.01 if '=' in symbol or len(symbol) <= 6 else 1)
            results.append({
                'symbol': symbol,
                'action': 'SHORT',
                'broker': 'ibkr',
                'status': 'placed' if trade and trade.orderStatus.status == 'Filled' else 'failed',
                'conviction': conviction,
                'price': price,
                'details': trade.orderStatus.status if trade else 'error'
            })
    
    # Disconnect IBKR
    if ib:
        ib.disconnect()
        print('\nIBKR disconnected')
    
    # Save results
    out_path = SCANDATA / f'nightshift_trades_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")}.json'
    out_path.write_text(json.dumps(results, indent=2, default=str), encoding='utf-8')
    print(f'\nResults written to {out_path}')
    
    # Print summary
    placed = [r for r in results if r['status'] == 'placed']
    failed = [r for r in results if r['status'] == 'failed']
    print(f'Summary: {len(placed)} placed, {len(failed)} failed')

if __name__ == '__main__':
    main()