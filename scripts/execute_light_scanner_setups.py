#!/usr/bin/env python3
"""
execute_light_scanner_setups.py
- Reads the latest light scanner setups
- Routes trades by broker per operator rules:
  FTMO LEFT: direct signed-in terminal, set trades only
  Capital RIGHT MT5: direct signed-in terminal, set trades only
  IBKR: local gateway port 4002
  Kraken: REST private API
  Binance: REST private API
  Coinbase: REST private API
  Polymarket: REST API
  eToro: DEMO ONLY via public API
  Hyperliquid: SKIPPED pending funding
No credential re-entry for pre-authenticated desktop sessions.
"""
import json, sys, time, uuid, traceback, hashlib, hmac, base64, urllib.parse, urllib.request
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
WORKFLOW = BASE / 'workflow'
SCANDATA = BASE / 'scandata'
ARTIFACTS = BASE / 'artifacts'
CREDS_PATH = BASE / '.broker_creds_secure.json'

# Add scripts to path
sys.path.insert(0, str(BASE / 'scripts'))

import requests
_creds = json.loads(CREDS_PATH.read_text(encoding='utf-8')) if CREDS_PATH.exists() else {}

# Broker routing config
FTMO_PATH = r'C:\Program Files\FTMO Global Markets MT5 Terminal\terminal64.exe'
CAPITAL_PATH = _creds.get('capital', {}).get('path') or r'C:\Program Files\Capital.com MetaTrader 5\terminal64.exe'
IBKR_HOST = '127.0.0.1'
IBKR_PORT = 4002
IBKR_CLIENT_ID = 2004

ETORO_API_KEY = _creds.get('etoro', {}).get('api_key', '')
ETORO_USER_KEY = _creds.get('etoro', {}).get('user_key', '')
ETORO_BASE = 'https://public-api.etoro.com'
KRAKEN_KEY = _creds.get('kraken', {}).get('api_key', '') or _creds.get('kraken', {}).get('key', '')
KRAKEN_SECRET = _creds.get('kraken', {}).get('api_secret', '') or _creds.get('kraken', {}).get('secret', '')
BINANCE_KEY = _creds.get('binance', {}).get('api_key', '') or _creds.get('binance', {}).get('key', '')
BINANCE_SECRET = _creds.get('binance', {}).get('api_secret', '') or _creds.get('binance', {}).get('secret', '')
COINBASE_KEY = _creds.get('coinbase', {}).get('api_key', '') or _creds.get('coinbase', {}).get('key', '')
COINBASE_SECRET = _creds.get('coinbase', {}).get('api_secret', '') or _creds.get('coinbase', {}).get('secret', '')
POLYMARKET_KEY = _creds.get('polymarket', {}).get('api_key', '') or _creds.get('polymarket', {}).get('key', '')

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

def place_etoro_demo_order(instrument_id, action, amount_usd=25.0, leverage=1, sl=None, tp=None):
    """Place a demo market order on eToro with optional SL/TP. DEMO ONLY."""
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
    if sl is not None:
        payload['stopLossRate'] = str(sl)
    if tp is not None:
        payload['takeProfitRate'] = str(tp)
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
        ib.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID, timeout=10)
        if not ib.isConnected():
            print('IBKR connection failed')
            return None
        print('IBKR connected: account', ib.accountValues()[0].value if ib.accountValues() else 'unknown')
        return ib
    except Exception as e:
        print(f'IBKR connection error: {e}')
        return None

def determine_contract_and_quantity(symbol):
    """Determine IBKR contract type and suggested quantity based on symbol."""
    sym_upper = symbol.upper()
    # Forex pairs: contain '/' or end with '=X', or are known 6-char forex majors
    FOREX_MAJORS = {'EURUSD','GBPUSD','USDJPY','AUDUSD','NZDUSD','USDCAD','USDCHF','EURJPY','EURGBP','GBPJPY','AUDJPY','AUDNZD','AUDCAD','CADJPY','CHFJPY','NZDJPY','EURCHF','EURCAD','EURAUD','GBPCHF','GBPAUD','GBPCAD','GBPNZD','NZDCHF','NZDCAD','USDTRY','USDZAR','USDMXN','USDCNY','USDSGD','USDHKD','USDTHB','USDSEK','USDNOK','USDDKK','USDPLN','USDKRW','USDPHP','USDHKD'}
    if '/' in sym_upper or sym_upper.endswith('=X') or sym_upper in FOREX_MAJORS:
        if '/' in sym_upper:
            base, quote = sym_upper.split('/')
            contract = Forex(f'{base}{quote}', exchange='IDEALPRO')
        elif sym_upper.endswith('=X'):
            base = sym_upper.replace('=X', '')[:3]
            quote = sym_upper.replace('=X', '')[3:6]
            contract = Forex(f'{base}{quote}', exchange='IDEALPRO')
        else:
            contract = Forex(sym_upper, exchange='IDEALPRO')
        quantity = 0.01
        return contract, quantity
    # Spot metals as CFDs
    if sym_upper in ('XAUUSD', 'XAGUSD'):
        contract = CFD(sym_upper)
        quantity = 1
        return contract, quantity
    # Futures: end with '=F'
    if sym_upper.endswith('=F'):
        root = sym_upper[:-2]
        from datetime import datetime
        now = datetime.now()
        year = now.year
        month = now.month + 1
        if month > 12:
            month = 1
            year += 1
        month_map = {1:'F',2:'G',3:'H',4:'J',5:'K',6:'M',7:'N',8:'Q',9:'U',10:'V',11:'X',12:'Z'}
        month_letter = month_map[month]
        known_futures = {
            'ES': ('CME', 'E-mini S&P 500'),
            'NQ': ('CME', 'E-mini Nasdaq-100'),
            'RTY': ('CME', 'E-mini Russell 2000'),
            'YM': ('CME', 'Mini Dow'),
            'GC': ('NYMEX', 'Gold'),
            'SI': ('NYMEX', 'Silver'),
            'CL': ('NYMEX', 'Crude Oil'),
            'NG': ('NYMEX', 'Natural Gas'),
            'ZC': ('CBOT', 'Corn'),
            'ZS': ('CBOT', 'Soybeans'),
            'ZW': ('CBOT', 'Wheat'),
            '6E': ('CME', 'Euro FX'),
            '6J': ('CME', 'Japanese Yen'),
            '6B': ('CME', 'British Pound'),
        }
        if root in known_futures:
            exchange = known_futures[root][0]
        else:
            exchange = 'CME'
        contract = Futures(root, f'{year}{month_letter}', exchange, currency='USD')
        quantity = 1
        return contract, quantity
    # Crypto like BTC-USD: skip on IBKR wrapper
    if '-' in sym_upper and 'USD' in sym_upper:
        print(f'Skipping crypto {symbol} on IBKR (not supported)')
        return None, None
    # Options: simple detection for equity options if format is suitable
    # This wrapper does not build complex option contracts; skip here.
    # Assume stock/ETF
    contract = Stock(sym_upper, 'SMART', 'USD')
    return contract, None

def place_ibkr_order_with_sl_tp(ib, symbol, action, sl, tp):
    """Place a market order with attached stop loss and take profit as OCA bracket.
    Returns list of trades if successful, else None."""
    try:
        # Determine contract and get initial quantity suggestion
        contract_info = determine_contract_and_quantity(symbol)
        if contract_info[0] is None:
            return None
        contract, quantity_suggested = contract_info
        
        # Qualify the contract
        ib.qualifyContracts(contract)
        # Get market data to validate and get price
        ib.reqMarketDataType(4)  # frozen data
        ticker = ib.reqMktData(contract, '', False, False)
        start = time.time()
        while time.time() - start < 5 and (ticker.bid == -1 or ticker.ask == -1):
            time.sleep(0.1)
        if ticker.bid == -1 or ticker.ask == -1:
            print(f'No market data for {symbol}')
            ib.cancelMktData(contract)
            return None
        
        # Determine quantity if not already set
        quantity = quantity_suggested
        if quantity is None:
            # For stocks, we want to adjust quantity based on price to keep risk similar.
            # We'll use a fixed risk amount in USD (e.g., $50) and calculate quantity based on stop distance.
            # But we don't have the stop distance yet? We have sl and tp from setup.
            # We'll use the entry price from setup (passed in? we don't have it here).
            # Actually, we have entry from the setup, but we don't have it in this function.
            # We'll change the function signature to include entry? Let's adjust.
            # Instead, we'll use a default quantity of 1 for stocks and later we can adjust in the caller.
            # For simplicity, we'll use 1 share for stocks.
            quantity = 1
            # If the stock price is very high, we might want less.
            # We'll use the mid price to adjust.
            mid_price = (ticker.bid + ticker.ask) / 2
            if mid_price > 1000:
                quantity = 1
            elif mid_price > 500:
                quantity = 2
            elif mid_price > 100:
                quantity = 5
            else:
                quantity = 10
        
        # Create bracket order: market order with attached stop loss and limit profit
        action = 'BUY' if action.lower() == 'buy' else 'SELL'
        # Market order
        parent = MarketOrder(action, quantity)
        parent.transmit = False  # We will transmit the whole bracket together
        # Stop loss order
        stop_loss = StopOrder('SELL' if action == 'BUY' else 'BUY', quantity, sl)
        stop_loss.parent = parent
        stop_loss.transmit = False
        # Take profit order
        take_profit = LimitOrder('SELL' if action == 'BUY' else 'BUY', quantity, tp)
        take_profit.parent = parent
        take_profit.transmit = True  # Transmit the whole bracket when this is sent
        
        # Place the bracket using the helper method if available, otherwise manual
        try:
            trades = ib.placeOrderBracket(parent, stop_loss, take_profit)
        except AttributeError:
            # Fallback: place each order and link via ocaGroup
            ocaGroup = f'OCA_{uuid.uuid4()}'
            parent.ocaGroup = ocaGroup
            parent.ocaType = 1  # 1 = cancel remaining on fill
            stop_loss.ocaGroup = ocaGroup
            stop_loss.ocaType = 1
            take_profit.ocaGroup = ocaGroup
            take_profit.ocaType = 1
            trades = [
                ib.placeOrder(contract, parent),
                ib.placeOrder(contract, stop_loss),
                ib.placeOrder(contract, take_profit)
            ]
        
        print(f'Placed IBKR bracket for {symbol}: {action} {quantity} @ market, SL={sl}, TP={tp}')
        
        # Wait a bit for fill
        time.sleep(3)
        # Check the parent order status robustly
        status = 'failed'
        fill_price = None
        if trades and len(trades) > 0:
            parent_trade = trades[0]
            try:
                raw_status = parent_trade.orderStatus.status
            except Exception:
                raw_status = None
            if raw_status == 'Filled':
                status = 'placed'
                try:
                    fill_price = parent_trade.orderStatus.avgFillPrice
                except Exception:
                    fill_price = None
            else:
                status = 'pending'
                print(f'  Parent status: {raw_status}')
        else:
            print('  No trades returned')
        
        # Clean up
        ib.cancelMktData(contract)
        return trades, fill_price
    except Exception as e:
        print(f'IBKR order error for {symbol}: {e}')
        traceback.print_exc()
        return None, None

def place_kraken_order(symbol, side, volume, sl=None, tp=None):
    if not KRAKEN_KEY or not KRAKEN_SECRET:
        return {'status': 'skipped', 'reason': 'missing_kraken_creds'}
    return {'status': 'skipped', 'reason': 'kraken_execution_not_implemented'}


def place_binance_order(symbol, side, quantity, sl=None, tp=None):
    if not BINANCE_KEY or not BINANCE_SECRET:
        return {'status': 'skipped', 'reason': 'missing_binance_creds'}
    return {'status': 'skipped', 'reason': 'binance_execution_not_implemented'}


def place_coinbase_order(symbol, side, size, sl=None, tp=None):
    if not COINBASE_KEY or not COINBASE_SECRET:
        return {'status': 'skipped', 'reason': 'missing_coinbase_creds'}
    return {'status': 'skipped', 'reason': 'coinbase_execution_not_implemented'}


def place_polymarket_order(market, side, size_usd, sl=None, tp=None):
    if not POLYMARKET_KEY:
        return {'status': 'skipped', 'reason': 'missing_polymarket_creds'}
    return {'status': 'skipped', 'reason': 'polymarket_execution_not_implemented'}


def main():
    # Load latest light scanner setups
    setup_files = list(WORKFLOW.glob('light_scanner_setups_*.json'))
    if not setup_files:
        print('No setup files found')
        return
    latest_setup = max(setup_files, key=lambda p: p.stat().st_mtime)
    print(f'Loading setups: {latest_setup.name}')
    setup_data = json.loads(latest_setup.read_text())
    
    setups = setup_data.get('setups', [])
    print(f'Loaded {len(setups)} setups')
    
    # Setup eToro
    symbol_map = load_symbol_map()
    print(f'eToro symbol map loaded: {len(symbol_map)} entries')
    
    # Setup IBKR
    ib = connect_ibkr()
    if not ib:
        print('IBKR not connected, skipping IBKR trades')
    
    results = []
    # We'll also prepare a list of trades for the artifact file (light_exec_*.json)
    artifact_trades = []
    
    # Process each setup (limit to first 5 for safety)
    for setup in setups[:5]:
        symbol = setup['symbol']
        side = setup['side']
        entry = setup['entry']
        sl = setup['sl']
        tp = setup['tp']
        score = setup['score']
        broker = (setup.get('broker') or '').lower()
        print(f'\nProcessing {symbol} {side.upper()} (score {score}) broker={broker}')
        print(f'  Entry: {entry}, SL: {sl}, TP: {tp}')

        if broker == 'hyperliquid':
            print('  Hyperliquid: skipped pending funding')
            results.append({'symbol': symbol, 'side': side, 'broker': 'hyperliquid', 'status': 'skipped', 'reason': 'pending_funding', 'entry': entry, 'sl': sl, 'tp': tp, 'score': score, 'timestamp': datetime.now(timezone.utc).isoformat()})
            continue
        elif broker == 'kraken':
            res = place_kraken_order(symbol, side, 0.0, sl=sl, tp=tp)
            results.append({'symbol': symbol, 'side': side, 'broker': 'kraken', 'status': res.get('status'), 'reason': res.get('reason'), 'entry': entry, 'sl': sl, 'tp': tp, 'score': score, 'timestamp': datetime.now(timezone.utc).isoformat()})
            continue
        elif broker == 'binance':
            res = place_binance_order(symbol, side, 0.0, sl=sl, tp=tp)
            results.append({'symbol': symbol, 'side': side, 'broker': 'binance', 'status': res.get('status'), 'reason': res.get('reason'), 'entry': entry, 'sl': sl, 'tp': tp, 'score': score, 'timestamp': datetime.now(timezone.utc).isoformat()})
            continue
        elif broker == 'coinbase':
            res = place_coinbase_order(symbol, side, 0.0, sl=sl, tp=tp)
            results.append({'symbol': symbol, 'side': side, 'broker': 'coinbase', 'status': res.get('status'), 'reason': res.get('reason'), 'entry': entry, 'sl': sl, 'tp': tp, 'score': score, 'timestamp': datetime.now(timezone.utc).isoformat()})
            continue
        elif broker == 'polymarket':
            res = place_polymarket_order(symbol, side, 0.0, sl=sl, tp=tp)
            results.append({'symbol': symbol, 'side': side, 'broker': 'polymarket', 'status': res.get('status'), 'reason': res.get('reason'), 'entry': entry, 'sl': sl, 'tp': tp, 'score': score, 'timestamp': datetime.now(timezone.utc).isoformat()})
            continue
        elif broker in ('ftmo', 'capital'):
            print(f'  {broker.upper()}: handled by direct signed-in terminal; no credential entry')
            results.append({'symbol': symbol, 'side': side, 'broker': broker, 'status': 'skipped_direct_terminal', 'reason': 'operator_direct_terminal', 'entry': entry, 'sl': sl, 'tp': tp, 'score': score, 'timestamp': datetime.now(timezone.utc).isoformat()})
            continue
        
        # eToro
        etoro_id = find_etoro_instrument_id(symbol, symbol_map)
        if etoro_id:
            print(f'  eToro instrument ID: {etoro_id}')
            etoro_res = place_etoro_demo_order(etoro_id, side, amount_usd=25.0, sl=sl, tp=tp)
            print(f'  eToro result: {etoro_res["status_code"]} {etoro_res["response"][:100]}')
            result = {
                'symbol': symbol,
                'side': side,
                'broker': 'etoro',
                'status': 'placed' if etoro_res['status_code'] == 200 else 'failed',
                'entry': entry,
                'sl': sl,
                'tp': tp,
                'score': score,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'details': etoro_res
            }
            results.append(result)
            if etoro_res['status_code'] == 200:
                # For eToro, we don't have fill price; we'll use the entry from setup.
                artifact_trades.append({
                    'broker': 'etoro',
                    'symbol': symbol,
                    'side': side,
                    'price': entry,
                    'sl': sl,
                    'tp': tp,
                    'ts': datetime.now(timezone.utc).isoformat(),
                    'status': 'executed'
                })
        else:
            print(f'  eToro: no instrument ID found for {symbol}')
            result = {
                'symbol': symbol,
                'side': side,
                'broker': 'etoro',
                'status': 'failed',
                'reason': 'no instrument id',
                'entry': entry,
                'sl': sl,
                'tp': tp,
                'score': score,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            results.append(result)
        
        # IBKR
        if ib:
            trades, fill_price = place_ibkr_order_with_sl_tp(ib, symbol, side, sl, tp)
            raw_statuses = []
            if trades and len(trades) > 0:
                for t in trades:
                    try:
                        raw_statuses.append(t.orderStatus.status)
                    except Exception:
                        raw_statuses.append('unknown')
            if any(s in ('Filled', 'PendingSubmit', 'Submitted') for s in raw_statuses):
                status = 'placed'
            else:
                status = 'failed'
            result = {
                'symbol': symbol,
                'side': side,
                'broker': 'ibkr',
                'status': status,
                'entry': entry,
                'sl': sl,
                'tp': tp,
                'score': score,
                'timestamp': datetime.now(timezone.utc).isoformat(),
                'fill_price': fill_price,
                'details': raw_statuses if raw_statuses else 'error'
            }
            results.append(result)
            if status == 'placed':
                # For IBKR placed trades, we add to artifact trades for backtesting
                artifact_trades.append({
                    'broker': 'ibkr',
                    'symbol': symbol,
                    'side': side,
                    'price': entry,
                    'sl': sl,
                    'tp': tp,
                    'ts': datetime.now(timezone.utc).isoformat(),
                    'status': 'executed'
                })
        else:
            result = {
                'symbol': symbol,
                'side': side,
                'broker': 'ibkr',
                'status': 'failed',
                'reason': 'no ibkr connection',
                'entry': entry,
                'sl': sl,
                'tp': tp,
                'score': score,
                'timestamp': datetime.now(timezone.utc).isoformat()
            }
            results.append(result)
    
    # Disconnect IBKR
    if ib:
        ib.disconnect()
        print('\nIBKR disconnected')
    
    # Save results to scandata
    out_path = SCANDATA / f'executed_light_setups_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")}.json'
    out_path.write_text(json.dumps(results, indent=2, default=str), encoding='utf-8')
    print(f'\nResults written to {out_path}')
    
    # Also write artifact file for backtesting (light_exec_*.json)
    if artifact_trades:
        artifact_path = ARTIFACTS / f'light_exec_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")}.json'
        artifact_data = {
            'ts': datetime.now(timezone.utc).isoformat(),
            'results': artifact_trades
        }
        artifact_path.write_text(json.dumps(artifact_data, indent=2, default=str), encoding='utf-8')
        print(f'Artifact file written to {artifact_path}')
    
    # Print summary
    placed = [r for r in results if r['status'] == 'placed']
    failed = [r for r in results if r['status'] == 'failed']
    print(f'Summary: {len(placed)} placed, {len(failed)} failed')

if __name__ == '__main__':
    main()