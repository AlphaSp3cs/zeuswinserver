import os
from alpaca_trade_api import REST
key = os.getenv("ALPACA_API_KEY")
secret = os.getenv("ALPACA_API_SECRET")
base_url = "https://paper-api.alpaca.markets"
api = REST(key, secret, base_url, api_version="v2")
account = api.get_account()
print(f"Alpaca Paper Account: {account.id}")
print(f"Status: {account.status}")
print(f"Buying Power: ${float(account.buying_power):,.2f}")
print(f"Cash: ${float(account.cash):,.2f}")
print(f"Portfolio Value: ${float(account.portfolio_value):,.2f}")
