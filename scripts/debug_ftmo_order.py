#!/usr/bin/env python3
import sys
from pathlib import Path
ROOT = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
sys.path.insert(0, str(ROOT / 'scripts'))
from mt5_connect import connect as mt5_connect, shutdown as mt5_shutdown
import MetaTrader5 as mt5

ftmo = mt5_connect('ftmo')
for sym in ['CVX','DIS','USDCHF','XOM','JPM','BA','NVDA','AAPL','MSFT']:
    si = mt5.symbol_info(sym)
    if not si:
        print(sym, 'NO symbol_info')
        continue
    ftmo.symbol_select(sym, True)
    tick = mt5.symbol_info_tick(sym)
    print(sym, 'select', si.select, 'visible', si.visible, 'filling', si.filling_mode, 'bid', tick.bid if tick else None, 'ask', tick.ask if tick else None, 'trade', getattr(si,'trade_mode',None))
print('last_error', mt5.last_error())

# Try a test order on CVX with explicit retcode check
sym='CVX'
si=mt5.symbol_info(sym)
ftmo.symbol_select(sym, True)
tick=mt5.symbol_info_tick(sym)
print('CVX order test:')
req = {
    'action': mt5.TRADE_ACTION_DEAL,
    'symbol': sym,
    'volume': 1,
    'type': mt5.ORDER_TYPE_BUY,
    'price': round(tick.ask, si.digits),
    'sl': round(tick.ask - 1.0, si.digits),
    'tp': round(tick.ask + 2.0, si.digits),
    'deviation': 20,
    'magic': 20260817,
    'comment': 'cvx_test',
    'type_time': mt5.ORDER_TIME_GTC,
    'type_filling': mt5.ORDER_FILLING_IOC,
}
res = ftmo.order_send(req)
print('res is None?', res is None)
print('last_error after send:', mt5.last_error())
if res is not None:
    print('retcode', res.retcode, 'comment', getattr(res, 'comment', None), 'order', getattr(res, 'order', None), 'deal', getattr(res, 'deal', None))
else:
    # maybe retcode is available via last_error?
    err = mt5.last_error()
    print('last_error tuple', err)
mt5.shutdown()
