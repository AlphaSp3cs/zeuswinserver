import os
import alpaca_trade_api as tradeapi

# Set up Alpaca API
key = os.getenv('ALPACA_API_KEY')
secret = os.getenv('ALPACA_API_SECRET')
base_url = 'https://paper-api.alpaca.markets'
api = tradeapi.REST(key, secret, base_url, api_version='v2')

# Check market clock
clock = api.get_clock()
print('=== CURRENT MARKET STATUS ===')
print(f'Is Open: {clock.is_open}')
print(f'Next Open: {clock.next_open}')

# Check account
account = api.get_account()
print(f'Buying Power: ${float(account.buying_power):,.2f}')

# Check open orders
print('\n=== OPEN ORDERS ===')
try:
    orders = api.list_orders(status='open')
    for o in orders:
        print(f'{o.symbol} {o.side} {o.qty} @ {o.limit_price} ({o.id})')
except Exception as e:
    print(f'Error: {e}')

# Check positions
print('\n=== CURRENT POSITIONS ===')
try:
    positions = api.list_positions()
    for p in positions:
        print(f'{p.symbol}: {float(p.qty):.6f} shares')
except Exception as e:
    print(f'Error: {e}')
