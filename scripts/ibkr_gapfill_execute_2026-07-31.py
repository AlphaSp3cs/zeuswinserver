#!/usr/bin/env python3
"""
ibkr_gapfill_execute_2026-07-31.py
Execute ETF proxy gaps via IBKR using gateway live quotes.
Manual bracket construction to avoid ib_insync.bracketOrder kwargs mismatch.
"""
import json, time, sys
from pathlib import Path
from datetime import datetime, timezone
from ib_insync import IB, Stock, Order

BASE = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
sys.path.insert(0, str(BASE))
creds = json.loads((BASE/'broker_creds.json').read_text())

ETF_SETUPS = [
    {'symbol':'TLT','direction':'LONG','entry':82.78,'sl':82.52928571,'tp':83.28142857,'rsi14':13.93,'rr':2.0,'volume':100,'conId':15547841},
    {'symbol':'XLE','direction':'SHORT','entry':58.96,'sl':59.40285714,'tp':58.07428571,'rsi14':71.39,'rr':2.0,'volume':100,'conId':4215217},
    {'symbol':'GLD','direction':'LONG','entry':377.18,'sl':374.43428571,'tp':382.67142857,'rsi14':64.2,'rr':2.0,'volume':100,'conId':51529211},
    {'symbol':'SLV','direction':'SHORT','entry':53.5,'sl':54.155,'tp':52.19,'rsi14':65.25,'rr':2.0,'volume':100,'conId':39039301},
    {'symbol':'USO','direction':'SHORT','entry':127.46,'sl':129.39642857,'tp':123.58714286,'rsi14':72.58,'rr':2.0,'volume':100,'conId':418893644},
    {'symbol':'RB','direction':'SHORT','entry':46.98,'sl':47.01142857,'tp':46.91714286,'rsi14':81.82,'rr':2.0,'volume':100,'conId':794639079},
    {'symbol':'SPY','direction':'LONG','entry':630.0,'sl':627.0,'tp':636.0,'rsi14':50.0,'rr':2.0,'volume':100,'conId':756733},
    {'symbol':'QQQ','direction':'LONG','entry':590.0,'sl':586.7,'tp':596.0,'rsi14':50.0,'rr':2.0,'volume':100,'conId':320227571},
]

def ibkr_last(ib, contract):
    try:
        ib.qualifyContracts(contract)
        tick = ib.reqMktData(contract, '', False, False)
        ib.sleep(0.3)
        price = tick.last if tick.last and tick.last > 0 else (tick.bid if tick.bid and tick.bid > 0 else tick.ask)
        ib.cancelMktData(tick)
        return float(price) if price and price > 0 else None
    except Exception:
        return None

def connect():
    ib = IB()
    try:
        ib.connect(creds['ibkr']['host'], int(creds['ibkr']['port']), clientId=14, timeout=20, readonly=False)
        return ib
    except Exception as e:
        print('IB connect failed:', e)
        return None

ib = connect()
if not ib:
    print('No IBKR connection')
    sys.exit(1)
print('IBKR connected')

results = []
for etf in ETF_SETUPS:
    contract = Stock(conId=etf['conId'], exchange='SMART', currency='USD')
    ib.qualifyContracts(contract)
    price = ibkr_last(ib, contract)
    if price is None:
        print(etf['symbol'], 'no IBKR live quote')
        results.append({'symbol':etf['symbol'],'status':'blocked','reason':'no_live_quote'})
        continue
    qty = int(etf['volume'])
    action = 'BUY' if etf['direction']=='LONG' else 'SELL'
    tp = float(etf['tp']); sl = float(etf['sl'])
    try:
        parent = Order(orderId=ib.client.getReqId(), action=action, totalQuantity=qty, orderType='MKT', transmit=False, outsideRth=False)
        tp_order = Order(orderId=ib.client.getReqId(), action=('SELL' if action=='BUY' else 'BUY'), totalQuantity=qty, orderType='LMT', lmtPrice=tp, transmit=False, outsideRth=False, parentId=parent.orderId)
        sl_order = Order(orderId=ib.client.getReqId(), action=('SELL' if action=='BUY' else 'BUY'), totalQuantity=qty, orderType='STP', auxPrice=sl, transmit=True, outsideRth=False, parentId=parent.orderId)
        for o in (parent, tp_order, sl_order):
            ib.placeOrder(contract, o)
        results.append({'symbol':etf['symbol'],'status':'submitted','direction':etf['direction'],'price':price,'sl':sl,'tp':tp,'volume':qty,'ids':[parent.orderId, tp_order.orderId, sl_order.orderId]})
        print(etf['symbol'], 'submitted manual bracket', action, qty)
    except Exception as e:
        print(etf['symbol'], 'manual bracket failed', e)
        results.append({'symbol':etf['symbol'],'status':'failed','error':str(e)})
    time.sleep(0.5)
ib.disconnect()
out = BASE/'ibkr_gapfill_execution_report_2026-07-31.json'
out.write_text(json.dumps({'timestamp_utc':datetime.now(timezone.utc).isoformat(),'results':results}, indent=2))
print('WROTE', out, {k: sum(1 for r in results if r.get('status')==k) for k in ['submitted','failed','blocked']})
