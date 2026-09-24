import os, MetaTrader5 as mt5
login = int(os.getenv('MT5_LOGIN'))
password = os.getenv('MT5_PASSWORD')
server = os.getenv('MT5_SERVER'))
if not mt5.initialize(login=login, password=password, server=server):
    print('init failed:', mt5.last_error())
else:
    symbols = ['SOLUSD','HK50','XAUUSD','XAGUSD']
    for s in symbols:
        info = mt5.symbol_info(s)
        print(f"{s}: contract={info.trade_contract_size} tick_size={info.trade_tick_size} tick_value={info.trade_tick_value} point_value={info.trade_tick_value/info.trade_tick_size if info.trade_tick_size else None}")
    mt5.shutdown()
