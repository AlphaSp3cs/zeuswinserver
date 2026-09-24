import MetaTrader5 as mt5
from datetime import datetime, timezone
import json, os
LOGIN = int(os.environ.get('CAPITAL_MT5_LOGIN', '1028685'))
SERVER = os.environ.get('CAPITAL_MT5_SERVER', 'Capital.com-Demo')
print('init', ok, mt5.last_error())
if ok:
    acc = mt5.account_info()
    print('acct', acc.login, acc.server, acc.equity)
    info = mt5.symbol_info('BTCUSD')
    tick = mt5.symbol_info_tick('BTCUSD')
    print('BTCUSD visible', info.visible, 'trade_mode', info.trade_mode)
    req = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': 'BTCUSD',
        'volume': 0.01,
        'type': mt5.ORDER_TYPE_BUY_LIMIT,
        'price': tick.ask - info.trade_tick_size*10,
        'sl': tick.bid - 500,
        'tp': tick.ask + 500,
        'deviation': 20,
        'magic': 20260725,
        'comment': 'test_capital',
        'type_time': mt5.ORDER_TIME_GTC,
    }
    res = mt5.order_send(req)
    print('send', res)
    print('retcode', res.retcode if res else None, 'comment', res.comment if res else None)
    mt5.shutdown()
