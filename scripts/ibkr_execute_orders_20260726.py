#!/usr/bin/env python3
"""
IBKR Order Executor - Execute swing trade orders
Priority: SPY covered call -> QQQ covered call -> TSLA protective put -> AMD hedge -> SPY hedge
"""

import sys, os
sys.path.insert(0, 'C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
os.chdir('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')

from pathlib import Path
import json
import datetime
import time

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

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.order import Order

IBKR_HOST = os.environ.get('IBKR_HOST', '127.0.0.1')
IBKR_PORT = int(os.environ.get('IBKR_PORT', '7497'))
IBKR_CLIENT_ID = int(os.environ.get('IBKR_CLIENT_ID', '1'))
IBKR_ACCOUNT = os.environ.get('IBKR_ACCOUNT', '')


class IBKRExecutor(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.next_order_id = None
        self.order_status = {}
        self.executions = []
        self.done = False
        self.errors = []
        self.orders_ready = False
    
    def nextValidId(self, orderId):
        self.next_order_id = orderId
        self.orders_ready = True
    
    def orderStatus(self, orderId, status, filled, remaining, avgFillPrice,
                    permId, parentId, lastFillPrice, clientId, whyHeld, mktCapPrice):
        self.order_status[orderId] = {
            'status': status,
            'filled': filled,
            'remaining': remaining,
            'avgFillPrice': avgFillPrice,
            'lastFillPrice': lastFillPrice,
        }
        print(f"  Order {orderId}: {status} filled={filled} remaining={remaining} avg={avgFillPrice}")
    
    def execDetails(self, reqId, contract, execution):
        self.executions.append({
            'exec_id': execution.execId,
            'order_id': execution.orderId,
            'symbol': contract.symbol,
            'side': execution.side,
            'shares': execution.shares,
            'price': execution.price,
            'time': execution.time,
        })
        print(f"  Execution: {contract.symbol} {execution.side} {execution.shares} @ {execution.price}")
    
    def execDetailsEnd(self, reqId):
        if self.executions:
            self.done = True
            self.disconnect()
    
    def error(self, reqId, errorCode, errorString, advancedOrderRejectJson=None):
        self.errors.append({
            'req_id': reqId,
            'code': errorCode,
            'message': errorString,
        })
        if errorCode not in [2104, 2106, 2158]:  # Ignore common warnings
            print(f"  Error {errorCode}: {errorString}")

    def execute_orders(self):
        pass


def make_contract(symbol, sec_type='STK', exchange='SMART', currency='USD', **kwargs):
    c = Contract()
    c.symbol = symbol
    c.secType = sec_type
    c.exchange = exchange
    c.currency = currency
    for k, v in kwargs.items():
        setattr(c, k, v)
    return c


def make_order(action, total_quantity, order_type='LMT', lmt_price=None, tif='GTC'):
    o = Order()
    o.action = action
    o.orderType = order_type
    o.totalQuantity = total_quantity
    o.tif = tif
    if lmt_price:
        o.lmtPrice = lmt_price
    return o


def main():
    print("="*70)
    print("IBKR ORDER EXECUTOR")
    print(f"Account: {IBKR_ACCOUNT}")
    print(f"Host: {IBKR_HOST}:{IBKR_PORT}")
    print("="*70)
    
    executor = IBKRExecutor()
    executor.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID + 200)
    
    order_results = []
    
    # Wait for next valid ID
    timeout = 8
    start = time.time()
    while not executor.orders_ready and time.time() - start < timeout:
        executor.run()
        time.sleep(0.2)
    
    if executor.next_order_id is None:
        print("ERROR: Could not get next valid order ID")
        return
    
    print(f"Next order ID: {executor.next_order_id}")
    
    # Load order specs
    specs_path = Path('ibkr_order_specs_2026-07-26.json')
    specs = {}
    if specs_path.exists():
        with open(specs_path) as f:
            specs = json.load(f)
    
    # Define orders to execute
    orders_to_send = [
        {
            'name': 'SPY Covered Call',
            'contract': make_contract('SPY', sec_type='OPT', exchange='SMART',
                                     lastTradeDateOrContractMonth='202608', right='C',
                                     strike=740, multiplier='100'),
            'order': make_order('SELL', 2, lmt_price=8.50),
            'priority': 1,
        },
        {
            'name': 'QQQ Covered Call',
            'contract': make_contract('QQQ', sec_type='OPT', exchange='SMART',
                                     lastTradeDateOrContractMonth='202608', right='C',
                                     strike=690, multiplier='100'),
            'order': make_order('SELL', 1, lmt_price=7.00),
            'priority': 1,
        },
        {
            'name': 'TSLA Protective Put',
            'contract': make_contract('TSLA', sec_type='OPT', exchange='SMART',
                                     lastTradeDateOrContractMonth='202608', right='P',
                                     strike=300, multiplier='100'),
            'order': make_order('BUY', 15, lmt_price=12.00),
            'priority': 1,
        },
        {
            'name': 'AMD Long Call Hedge',
            'contract': make_contract('AMD', sec_type='OPT', exchange='SMART',
                                     lastTradeDateOrContractMonth='202608', right='C',
                                     strike=540, multiplier='100'),
            'order': make_order('BUY', 12, lmt_price=5.00),
            'priority': 1,
        },
        {
            'name': 'SPY Put Hedge',
            'contract': make_contract('SPY', sec_type='OPT', exchange='SMART',
                                     lastTradeDateOrContractMonth='202608', right='P',
                                     strike=720, multiplier='100'),
            'order': make_order('BUY', 2, lmt_price=3.50),
            'priority': 2,
        },
    ]
    
    # Sort by priority
    orders_to_send.sort(key=lambda x: x['priority'])
    
    print(f"\nSending {len(orders_to_send)} orders...")
    
    for i, order_spec in enumerate(orders_to_send, 1):
        name = order_spec['name']
        contract = order_spec['contract']
        order = order_spec['order']
        
        print(f"\n[{i}/{len(orders_to_send)}] {name}")
        print(f"  Contract: {contract.symbol} {contract.secType} {contract.right} strike={contract.strike}")
        print(f"  Order: {order.action} {order.totalQuantity} {order.orderType} @ {getattr(order, 'lmtPrice', 'N/A')}")
        
        order_id = executor.next_order_id
        executor.placeOrder(order_id, contract, order)
        
        order_results.append({
            'order_id': order_id,
            'name': name,
            'symbol': contract.symbol,
            'sec_type': contract.secType,
            'action': order.action,
            'quantity': order.totalQuantity,
            'order_type': order.orderType,
            'price': getattr(order, 'lmtPrice', None),
            'submitted_at': datetime.datetime.now().isoformat(),
        })
        
        # Increment order ID for next order
        executor.next_order_id += 1
        time.sleep(0.5)
    
    # Wait for executions
    print("\nWaiting for order confirmations...")
    time.sleep(5)
    
    # Run once more to capture any delayed responses
    executor.run()
    
    # Save results
    results = {
        'timestamp': datetime.datetime.now().isoformat(),
        'account': IBKR_ACCOUNT,
        'orders_sent': len(order_results),
        'orders': order_results,
        'executions': executor.executions,
        'order_statuses': executor.order_status,
        'errors': executor.errors,
        'success': len(executor.errors) == 0 or all(e['code'] in [2104, 2106, 2158] for e in executor.errors),
    }
    
    out = Path('ibkr_execution_results_2026-07-26.json')
    out.write_text(json.dumps(results, indent=2))
    print(f"\nSaved: {out}")
    
    print('\n' + '='*70)
    print('EXECUTION SUMMARY')
    print('='*70)
    print(f"Orders sent: {len(order_results)}")
    print(f"Executions received: {len(executor.executions)}")
    print(f"Errors: {len([e for e in executor.errors if e['code'] not in [2104, 2106, 2158]])}")
    
    for o in order_results:
        status = executor.order_status.get(o['order_id'], {})
        print(f"  {o['name']:25} ID={o['order_id']} status={status.get('status', 'pending')}")
    
    executor.disconnect()
    print('\n' + '='*70)
    print('Awuuuu!!!! the pack is finished.')
    print('='*70)


if __name__ == '__main__':
    main()
