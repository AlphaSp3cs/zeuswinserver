#!/usr/bin/env python3
"""
IBKR equity override placement for AMZN/GOOG/MSFT/NVDA/AAPL.
Uses manual bracket with GTC to avoid Error 10349.
"""
import os, json, time
from pathlib import Path
from datetime import datetime, timezone
from ib_insync import IB, Stock, Order

BASE = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
OUT = BASE / 'artifacts' / f'execution_override_ibkr_20260804T{datetime.now(timezone.utc).strftime("%H%M")}Z.json'

SETUPS = [
  {'symbol':'AMZN','side':'SELL','entry':283.91,'sl':284.91393,'tp':281.90214},
  {'symbol':'GOOG','side':'SELL','entry':372.09,'sl':373.24929,'tp':369.77143},
  {'symbol':'MSFT','side':'SELL','entry':487.04,'sl':488.68036,'tp':483.75929},
  {'symbol':'NVDA','side':'SELL','entry':206.51,'sl':207.61286,'tp':204.30429},
  {'symbol':'AAPL','side':'BUY','entry':303.18,'sl':301.96179,'tp':305.61643},
]

def connect():
    ib = IB()
    ib.connect('127.0.0.1', 7497, clientId=99, timeout=15, readonly=False)
    return ib

def place_manual_bracket(ib, setup):
    try:
        contract = Stock(setup['symbol'], 'SMART', 'USD')
        qualified = ib.qualifyContracts(contract)
        if not qualified:
            return {'symbol': setup['symbol'], 'status': 'error', 'reason': 'qualify_failed'}
        c = qualified[0]
        price = round(float(setup['entry']), 2)
        sl = round(float(setup['sl']), 2)
        tp = round(float(setup['tp']), 2)
        account = ib.wrapper.accounts[0] if ib.wrapper.accounts else ''
        parent = Order(action=setup['side'], orderType='MKT', totalQuantity=1, transmit=False, outsideRth=False, tif='GTC', account=account)
        parent_trade = ib.placeOrder(c, parent)
        ib.sleep(2)
        parent_status = parent_trade.orderStatus.status if parent_trade and parent_trade.orderStatus else 'unknown'
        parent_id = parent_trade.order.orderId if parent_trade and parent_trade.order else None
        if not parent_id or parent_status in {'Cancelled','Rejected'}:
            return {'symbol': setup['symbol'], 'side': setup['side'], 'price': price, 'sl': sl, 'tp': tp,
                    'parent_status': parent_status, 'parent_order_id': parent_id, 'overall_status': 'failed'}
        child_tp = Order(action='SELL' if setup['side']=='BUY' else 'BUY', orderType='LMT', lmtPrice=tp, transmit=False, parentId=parent_id, outsideRth=False, tif='GTC', account=account, totalQuantity=1)
        child_sl = Order(action='SELL' if setup['side']=='BUY' else 'BUY', orderType='STP', auxPrice=sl, transmit=True, parentId=parent_id, outsideRth=False, tif='GTC', account=account, totalQuantity=1)
        tp_trade = ib.placeOrder(c, child_tp)
        ib.sleep(1)
        tp_status = tp_trade.orderStatus.status if tp_trade and tp_trade.orderStatus else 'unknown'
        tp_id = tp_trade.order.orderId if tp_trade and tp_trade.order else None
        sl_trade = ib.placeOrder(c, child_sl)
        ib.sleep(1)
        sl_status = sl_trade.orderStatus.status if sl_trade and sl_trade.orderStatus else 'unknown'
        sl_id = sl_trade.order.orderId if sl_trade and sl_trade.order else None
        return {
            'symbol': setup['symbol'], 'side': setup['side'], 'price': price, 'sl': sl, 'tp': tp,
            'parent_status': parent_status, 'parent_order_id': parent_id,
            'tp_status': tp_status, 'tp_order_id': tp_id,
            'sl_status': sl_status, 'sl_order_id': sl_id,
            'overall_status': 'submitted' if parent_status not in {'Cancelled','Rejected'} else 'failed'
        }
    except Exception as e:
        return {'symbol': setup['symbol'], 'status': 'error', 'reason': repr(e)}

def main():
    payload = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'ibkr': {}, 'results': []}
    try:
        ib = connect()
        payload['ibkr']['connected'] = ib.isConnected()
        payload['ibkr']['account'] = ib.wrapper.accounts[0] if ib.wrapper.accounts else None
        if ib.isConnected():
            for s in SETUPS:
                r = place_manual_bracket(ib, s)
                print(r)
                payload['results'].append(r)
                time.sleep(1)
            ib.disconnect()
    except Exception as e:
        payload['ibkr']['error'] = repr(e)
    OUT.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print('WROTE', OUT)
    print(json.dumps(payload, indent=2))

if __name__ == '__main__':
    main()
