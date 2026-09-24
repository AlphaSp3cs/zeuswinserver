import MetaTrader5 as mt5
import os
login = int(os.environ.get('MT5_LOGIN', '0'))
server = os.environ.get('MT5_SERVER', '')
password = os.environ.get('MT5_PASSWORD', '')
print(f'Login={login} Server={server}')
try:
    mt5.shutdown()
except:
    pass
# Try to see if terminal path can be auto-found
ok = mt5.initialize()
if not ok:
    print('Auto-init failed:', mt5.last_error())
else:
    acc = mt5.account_info()
    print('Connected to:', getattr(acc, 'server', 'unknown'), 'login:', getattr(acc, 'login', 'unknown'))
    mt5.shutdown()
