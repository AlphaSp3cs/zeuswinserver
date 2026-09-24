import MetaTrader5 as mt5
import os
LOGIN = int(os.environ.get('CAPITAL_MT5_LOGIN', '1028685'))
SERVER = os.environ.get('CAPITAL_MT5_SERVER', 'Capital.com-Demo')
print('init', ok, mt5.last_error())
if ok:
    positions = mt5.positions_get() or []
    print('positions count', len(positions))
    for p in positions:
        print(p.symbol, p.volume, p.profit)
    mt5.shutdown()
