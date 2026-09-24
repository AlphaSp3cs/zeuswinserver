import os
from alpaca_trade_api import REST
import sys

key = os.environ.get('ALPACA_API_KEY')
secret = os.environ.get('ALPACA_SECRET_KEY')
print("Key:", key)
print("Secret:", secret)
if not key or not secret:
    print("Missing env")
    sys.exit(1)
api = REST(key, secret, 'https://paper-api.alpaca.markets', api_version='v2')
try:
    acc = api.get_account()
    print("Account:", acc)
except Exception as e:
    print("Error:", e)