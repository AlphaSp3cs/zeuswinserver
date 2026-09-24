#!/usr/bin/env python3
"""
IBKR Order Specification Generator
Generates ready-to-send order specs for high-probability options/futures.
"""

import sys, os
sys.path.insert(0, 'C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
os.chdir('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')

from pathlib import Path
import json
import datetime
from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order
import time

IBKR_HOST = os.environ.get('IBKR_HOST', '127.0.0.1')
IBKR_PORT = int(os.environ.get('IBKR_PORT', '7497'))
IBKR_CLIENT_ID = int(os.environ.get('IBKR_CLIENT_ID', '1'))
IBKR_ACCOUNT = os.environ.get('IBKR_ACCOUNT', '')

class IBKRContractScanner(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.contracts = {}
        self.done = False
        self.req_id = 0
    
    def nextValidId(self, orderId):
        self.next_order_id = orderId
        self.scan_contracts()
    
    def scan_contracts(self):
        # SPY options chain
        self.req_id += 1
        contract = Contract()
        contract.symbol = 'SPY'
        contract.secType = 'OPT'
        contract.exchange = 'SMART'
        contract.currency = 'USD'
        contract.lastTradeDateOrContractMonth = '202608'
        contract.right = 'C'  # Calls
        contract.strike = 740  # Slightly OTM
        contract.multiplier = '100'
        self.reqContractDetails(self.req_id, contract)
        
        time.sleep(0.5)
        
        # QQQ options chain
        self.req_id += 1
        contract = Contract()
        contract.symbol = 'QQQ'
        contract.secType = 'OPT'
        contract.exchange = 'SMART'
        contract.currency = 'USD'
        contract.lastTradeDateOrContractMonth = '202608'
        contract.right = 'C'
        contract.strike = 690
        contract.multiplier = '100'
        self.reqContractDetails(self.req_id, contract)
        
        time.sleep(0.5)
        
        # TSLA options chain
        self.req_id += 1
        contract = Contract()
        contract.symbol = 'TSLA'
        contract.secType = 'OPT'
        contract.exchange = 'SMART'
        contract.currency = 'USD'
        contract.lastTradeDateOrContractMonth = '202608'
        contract.right = 'P'  # Puts for protective puts
        contract.strike = 300
        contract.multiplier = '100'
        self.reqContractDetails(self.req_id, contract)
        
        time.sleep(0.5)
        
        # AMD options chain
        self.req_id += 1
        contract = Contract()
        contract.symbol = 'AMD'
        contract.secType = 'OPT'
        contract.exchange = 'SMART'
        contract.currency = 'USD'
        contract.lastTradeDateOrContractMonth = '202608'
        contract.right = 'C'
        contract.strike = 540
        contract.multiplier = '100'
        self.reqContractDetails(self.req_id, contract)
        
        time.sleep(0.5)
        
        # SPY puts for hedge
        self.req_id += 1
        contract = Contract()
        contract.symbol = 'SPY'
        contract.secType = 'OPT'
        contract.exchange = 'SMART'
        contract.currency = 'USD'
        contract.lastTradeDateOrContractMonth = '202608'
        contract.right = 'P'
        contract.strike = 720
        contract.multiplier = '100'
        self.reqContractDetails(self.req_id, contract)
        
        self.done = True
        self.disconnect()
    
    def contractDetails(self, reqId, contractDetails):
        key = f"{contractDetails.contract.symbol}_{contractDetails.contract.right}_{contractDetails.contract.strike}"
        self.contracts[key] = {
            'symbol': contractDetails.contract.symbol,
            'right': contractDetails.contract.right,
            'strike': contractDetails.contract.strike,
            'exchange': contractDetails.contract.exchange,
            'min_tick': contractDetails.minTick,
            'multiplier': contractDetails.contract.multiplier,
        }
    
    def contractDetailsEnd(self, reqId):
        pass


def create_order_spec(action, contract, quantity, order_type='LMT', price=None, tif='GTC'):
    """Create an order specification dictionary."""
    order = {
        'action': action,  # BUY/SELL
        'orderType': order_type,  # LMT/MKT/STP
        'totalQuantity': quantity,
        'tif': tif,  # Time in force
    }
    if price:
        order['lmtPrice'] = price
    return order


def main():
    import time
    
    print("="*70)
    print("IBKR ORDER SPECIFICATION GENERATOR")
    print("="*70)
    
    # Scan contracts
    print("\nScanning IBKR for options contract details...")
    app = IBKRContractScanner()
    app.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID + 101)
    
    timeout = 15
    start = time.time()
    while not app.done and time.time() - start < timeout:
        app.run()
        time.sleep(0.2)
    
    print(f"Found {len(app.contracts)} contract specifications")
    
    # Generate order specs
    orders = []
    
    # 1. SPY covered calls: sell 2 contracts (200 shares)
    if any('SPY_C_' in k for k in app.contracts):
        key = [k for k in app.contracts if k.startswith('SPY_C_')][0]
        c = app.contracts[key]
        orders.append({
            'priority': 1,
            'strategy': 'covered_call',
            'symbol': 'SPY',
            'contract': c,
            'order': {
                'action': 'SELL',
                'orderType': 'LMT',
                'totalQuantity': 2,
                'lmtPrice': 8.50,  # Estimate: 1-2% OTM call
                'tif': 'GTC',
            },
            'reason': 'Sell covered calls against 208 SPY shares (2 contracts = 200 shares)',
            'position_covered': 208,
        })
    
    # 2. QQQ covered calls: sell 1 contract (100 shares)
    if any('QQQ_C_' in k for k in app.contracts):
        key = [k for k in app.contracts if k.startswith('QQQ_C_')][0]
        c = app.contracts[key]
        orders.append({
            'priority': 1,
            'strategy': 'covered_call',
            'symbol': 'QQQ',
            'contract': c,
            'order': {
                'action': 'SELL',
                'orderType': 'LMT',
                'totalQuantity': 1,
                'lmtPrice': 7.00,
                'tif': 'GTC',
            },
            'reason': 'Sell covered calls against 100 QQQ shares',
            'position_covered': 100,
        })
    
    # 3. TSLA protective puts: buy 15 contracts (1500 shares)
    if any('TSLA_P_' in k for k in app.contracts):
        key = [k for k in app.contracts if k.startswith('TSLA_P_')][0]
        c = app.contracts[key]
        orders.append({
            'priority': 1,
            'strategy': 'protective_put',
            'symbol': 'TSLA',
            'contract': c,
            'order': {
                'action': 'BUY',
                'orderType': 'LMT',
                'totalQuantity': 15,
                'lmtPrice': 12.00,
                'tif': 'GTC',
            },
            'reason': 'Buy protective puts for 1466 TSLA shares (15 contracts)',
            'position_covered': 1466,
        })
    
    # 4. AMD long calls: buy 12 contracts (1200 shares hedge)
    if any('AMD_C_' in k for k in app.contracts):
        key = [k for k in app.contracts if k.startswith('AMD_C_')][0]
        c = app.contracts[key]
        orders.append({
            'priority': 1,
            'strategy': 'long_call_hedge',
            'symbol': 'AMD',
            'contract': c,
            'order': {
                'action': 'BUY',
                'orderType': 'LMT',
                'totalQuantity': 12,
                'lmtPrice': 5.00,
                'tif': 'GTC',
            },
            'reason': 'Buy calls to hedge -1200 AMD short position',
            'position_covered': 1200,
        })
    
    # 5. SPY puts hedge: buy 2 contracts
    if any('SPY_P_' in k for k in app.contracts):
        key = [k for k in app.contracts if k.startswith('SPY_P_')][0]
        c = app.contracts[key]
        orders.append({
            'priority': 2,
            'strategy': 'buy_put_hedge',
            'symbol': 'SPY',
            'contract': c,
            'order': {
                'action': 'BUY',
                'orderType': 'LMT',
                'totalQuantity': 2,
                'lmtPrice': 3.50,
                'tif': 'GTC',
            },
            'reason': 'Buy SPY puts as portfolio hedge with BP=$2.45M',
        })
    
    results = {
        'timestamp': datetime.datetime.now().isoformat(),
        'ibkr_account': IBKR_ACCOUNT,
        'contracts_found': len(app.contracts),
        'order_specs': orders,
        'execution_ready': True,
    }
    
    out = Path('ibkr_order_specs_2026-07-26.json')
    out.write_text(json.dumps(results, indent=2))
    print(f"\nSaved: {out}")
    
    print('\n' + '='*70)
    print('ORDER SPECIFICATIONS')
    print('='*70)
    for i, o in enumerate(orders, 1):
        print(f"{i}. [{o['strategy'].upper()}] {o['symbol']}")
        print(f"   Action: {o['order']['action']} {o['order']['totalQuantity']} contracts")
        print(f"   Type: {o['order']['orderType']} @ ${o['order']['lmtPrice']}")
        print(f"   Reason: {o['reason']}")
        print()
    
    app.disconnect()
    print("="*70)
    print('Awuuuu!!!! the pack is finished.')
    print("="*70)


if __name__ == '__main__':
    main()
