import os, MetaTrader5 as mt5
login = int(os.getenv('MT5_LOGIN'))
password = os.getenv('MT5_PASSWORD')
server = os.getenv('MT5_SERVER'))
# Try FTMO terminal
path = r'REDACTED-PATH'
ok = mt5.initialize(path=path, login=login, server=server, password=password)
print('FTMO init:', ok, mt5.last_error())
if ok:
    acc = mt5.account_info()
    print('Account:', acc.login, acc.server, acc.equity)
    mt5.shutdown()