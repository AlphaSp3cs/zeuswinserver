#!/usr/bin/env python3
import sys
from pathlib import Path
ROOT = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
sys.path.insert(0, str(ROOT / 'scripts'))
from mt5_connect import connect as mt5_connect, shutdown as mt5_shutdown
import MetaTrader5 as mt5

ftmo = mt5_connect('ftmo')
sym='CVX'
si=mt5.symbol_info(sym)
ftmo.symbol_select(sym, True)
tick=mt5.symbol_info_tick(sym)
print('filling', si.filling_mode, 'digits', si.digits, 'point', si.point, 'vol_min', si.volume_min, 'vol_step', si.volume_step, 'vol_max', si.volume_max)

# Try without SL/TP
for vol in [1.0, 2.0, 5.0, 10.0]:
    req = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': sym,
        'volume': float(vol),
        'type': mt5.ORDER_TYPE_BUY,
        'price': round(tick.ask, si.digits),
        'deviation': 20,
        'magic': 20260817,
        'comment': f'cvx_voltest_{vol}',
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': mt5.ORDER_FILLING_IOC,
    }
    res = ftmo.order_send(req)
    print('vol', vol, 'retcode', res.retcode if res else None, 'comment', getattr(res, 'comment', None), 'order', getattr(res, 'order', None), 'last_err', mt5.last_error())
    if res and res.retcode == mt5.TRADE_RETCODE_DONE:
        print('EXECUTED vol', vol)
        break
mt5.shutdown()
