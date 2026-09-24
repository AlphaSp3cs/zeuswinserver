from pathlib import Path
import MetaTrader5 as mt5

TERMINAL = r"REDACTED-PATH"
try:
    mt5.shutdown()
except Exception:
    pass
ok = mt5.initialize(path=TERMINAL)
print('INIT_OK', ok)
if ok:
    acc = mt5.account_info()
    print('ACCOUNT', getattr(acc,'login',None), getattr(acc,'equity',None))
    pos = mt5.positions_get()
    print('POSITIONS_COUNT', len(pos) if pos else 0)
    positions = []
    if pos:
        for p in pos:
            positions.append({'symbol': p.symbol, 'volume': p.volume, 'type': p.type, 'profit': p.profit})
    print('POSITIONS', positions[:20])
    def info(name):
        r = mt5.symbol_info(name)
        print(name, bool(r), getattr(r, 'bid', None), getattr(r, 'ask', None), getattr(r, 'digits', None))
    for name in ['ETHUSD','AVAXUSD','ADAUSD','SOLUSD','XRPUSD']:
        info(name)
    def rates(name):
        try:
            r = mt5.copy_rates_from_pos(name, mt5.TIMEFRAME_H1, 0, 3)
            print(name, 'RATES', [dict(zip(['time','open','high','low','close','vol','spread','real'],x._asdict().values())) for x in r] if r is not None else None)
        except Exception as e:
            print(name, 'RATES_ERROR', repr(e))
    for name in ['ETHUSD']:
        rates(name)
    try:
        rates('AVAXUSD')
    except Exception as e:
        print('AVAX_RATES_ERROR', repr(e))
    try:
        t = mt5.symbol_info_tick('ETHUSD')
        print('ETHUSD_TICK', t._asdict() if t else None)
    except Exception as e:
        print('ETH_TICK_ERROR', repr(e))
    try:
        t = mt5.symbol_info_tick('AVAXUSD')
        print('AVAXUSD_TICK', t._asdict() if t else None)
    except Exception as e:
        print('AVAX_TICK_ERROR', repr(e))
    mt5.shutdown()
else:
    print('INIT_FAILED')