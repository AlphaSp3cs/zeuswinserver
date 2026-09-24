import os
import alpaca_trade_api as tradeapi

api = tradeapi.REST(
    os.getenv('ALPACA_API_KEY'),
    os.getenv('ALPACA_API_SECRET'),
    base_url='https://paper-api.alpaca.markets',
    api_version='v2'
)
print('Account ID:', api.get_account().account_number)
print('Market clock:', api.get_clock())
print('\nOpen orders:')
for o in api.list_orders(status='open'):
    print(f'{o.symbol} {o.side} {o.qty} @ {o.limit_price} (id: {o.id})')
print('\nPositions:')
for p in api.list_positions():
    print(f'{p.symbol}: {float(p.qty):.6f} shares')
