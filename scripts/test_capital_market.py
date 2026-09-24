import MetaTrader5 as mt5
import os
LOGIN = int(os.environ.get('CAPITAL_MT5_LOGIN', '1028685'))
SERVER = os.environ.get('CAPITAL_MT5_SERVER', 'Capital.com-Demo')
print('init', ok, mt5.last_error())
if ok:
    tick = mt5.symbol_info_tick('BTCUSD')
    req = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': 'BTCUSD',
        'volume': 0.01,
        'type': mt5.ORDER_TYPE_BUY,
        'price': tick.ask,
        'sl': tick.bid - 500,
        'tp': tick.ask + 500,
        'deviation': 20,
        'magic': 20260725,
        'comment': 'test_market',
        'type_time': mt5.TRADE_TIME_GTC,
    }
    res = mt5.order_send(req)
    print('retcode', res.retcode if res else None)
    print('comment', res.comment if res else None)
    mt5.shutdown()
