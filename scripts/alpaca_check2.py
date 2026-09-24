from alpaca_trade_api import REST
import os
key = os.environ.get('ALPACA_KEY', '')
secret = os.environ.get('ALPACA_SECRET', '')
if not key or not secret:
    print('Missing env vars')
    exit(1)
api = REST(key, secret, 'https://paper-api.alpaca.markets', api_version='v2')
try:
    acc = api.get_account()
    print('Alpaca status:', acc.status)
    print('Portfolio_value:', float(acc.portfolio_value))
    print('Buying_power:', float(acc.buying_power))
    print('Equity:', float(acc.equity))
except Exception as e:
    print('Alpaca error:', str(e)[:200])
