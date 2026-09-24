#!/usr/bin/env python3
"""
Equity override placement for FTMO LEFT at 09:30 ET session open.
"""
import time, json
from pathlib import Path
from datetime import datetime, timezone
import MetaTrader5 as mt5

TERMINAL = r'REDACTED-PATH'
LOGIN = int(os.environ.get('FTMO_MT5_LOGIN', '0'))
PW = os.environ.get('FTMO_MT5_PASSWORD', '')
SERVER = os.environ.get('FTMO_MT5_SERVER', '')
BASE = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
OUT = BASE / 'artifacts' / f'execution_override_equity_20260804T0930Z.json'

SETUPS = [
  {'symbol':'AMZN','side':'sell','entry':283.91,'sl':284.91393,'tp':281.90214,'digits':2,'vol':1.0},
  {'symbol':'GOOG','side':'sell','entry':372.09,'sl':373.24929,'tp':369.77143,'digits':2,'vol':1.0},
  {'symbol':'MSFT','side':'sell','entry':487.04,'sl':488.68036,'tp':483.75929,'digits':2,'vol':1.0},
  {'symbol':'NVDA','side':'sell','entry':206.51,'sl':207.61286,'tp':204.30429,'digits':2,'vol':1.0},
  {'symbol':'AAPL','side':'buy','entry':303.18,'sl':301.96179,'tp':305.61643,'digits':2,'vol':1.0},
]

def init_ftmo():
    mt5.shutdown()
    time.sleep(1)
    ok = mt5.initialize(TERMINAL, login=LOGIN, password=PW, server=SERVER)
    if not ok:
        return False, mt5.last_error()
    acct = mt5.account_info()
    if not acct or acct.login != LOGIN:
        mt5.shutdown()
        return False, 'account_mismatch'
    return True, acct

def place(setup):
    mt5.shutdown()
    time.sleep(1)
    ok, err = init_ftmo()
    if not ok:
        return {'symbol': setup['symbol'], 'status': 'error', 'reason': f'init_failed:{err}', 'retcode': None}
    si = mt5.symbol_info(setup['symbol'])
    if not si:
        mt5.shutdown()
        return {'symbol': setup['symbol'], 'status': 'error', 'reason': 'no_symbol_info', 'retcode': None}
    mt5.symbol_select(setup['symbol'], True)
    tick = mt5.symbol_info_tick(setup['symbol'])
    if not tick or tick.bid <= 0 or tick.ask <= 0:
        mt5.shutdown()
        return {'symbol': setup['symbol'], 'status': 'error', 'reason': 'no_tick', 'retcode': None}
    price = round(float(tick.ask if setup['side'] == 'buy' else tick.bid), setup['digits'])
    sl = round(float(setup['sl']), setup['digits'])
    tp = round(float(setup['tp']), setup['digits'])
    req = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': setup['symbol'],
        'volume': float(setup['vol']),
        'type': mt5.ORDER_TYPE_SELL if setup['side'] == 'sell' else mt5.ORDER_TYPE_BUY,
        'price': price,
        'sl': sl,
        'tp': tp,
        'deviation': 20,
        'magic': 20260804,
        'comment': 'equity_override_0930',
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    mt5.shutdown()
    if res is None:
        return {'symbol': setup['symbol'], 'side': setup['side'], 'price': price, 'sl': sl, 'tp': tp, 'status': 'error', 'reason': 'order_send_none', 'retcode': None}
    status = 'executed' if res.retcode == mt5.TRADE_RETCODE_DONE else 'failed'
    return {'symbol': setup['symbol'], 'side': setup['side'], 'volume': setup['vol'], 'price': price, 'sl': sl, 'tp': tp, 'status': status, 'reason': getattr(res,'comment',''), 'retcode': int(res.retcode), 'order': getattr(res,'order',None), 'deal': getattr(res,'deal',None)}

def main():
    ok, info = init_ftmo()
    payload = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'ftmo_init': bool(ok), 'ftmo_account': str(getattr(info,'login',None)) if ok else None, 'results': []}
    if not ok:
        OUT.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        print(json.dumps(payload, indent=2))
        return
    for s in SETUPS:
        print('Placing', s['symbol'], s['side'])
        r = place(s)
        print(r)
        payload['results'].append(r)
        time.sleep(1)
    OUT.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print('WROTE', OUT)
    print(json.dumps(payload, indent=2))

if __name__ == '__main__':
    main()