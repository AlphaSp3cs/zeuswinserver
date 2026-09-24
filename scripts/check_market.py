import os
import alpaca_trade_api as tradeapi
from datetime import datetime, timezone

# Set up Alpaca API
key = os.getenv('ALPACA_API_KEY')
secret = os.getenv('ALPACA_API_SECRET')
base_url = 'https://paper-api.alpaca.markets'
api = tradeapi.REST(key, secret, base_url, api_version='v2')

# Check market clock
clock = api.get_clock()
print('=== MARKET STATUS ===')
print(f'Timestamp: {clock.timestamp}')
print(f'Is Open: {clock.is_open}')
print(f'Next Open: {clock.next_open}')
print(f'Next Close: {clock.next_close}')

# Check account
account = api.get_account()
print('\n=== ACCOUNT INFO ===')
print(f'Buying Power: ${float(account.buying_power):,.2f}')
print(f'Cash: ${float(account.cash):,.2f}')
print(f'Portfolio Value: ${float(account.portfolio_value):,.2f}')

# Get some key symbols we want to trade
symbols_to_check = ['XLY', 'XLK', 'GLD', 'SLV', 'USO', 'UNG', 'SPY', 'QQQ', 'EFA', 'EEM', 'GLD', 'GDX', 'TLT', 'IEF']
print('\n=== SYMBOL AVAILABILITY ===')
available = []
for symbol in symbols_to_check:
    try:
        asset = api.get_asset(symbol)
        if asset.tradable:
            available.append(symbol)
            print(f'{symbol}: AVAILABLE')
        else:
            print(f'{symbol}: NOT TRADEABLE')
    except Exception as e:
        print(f'{symbol}: ERROR - {str(e)[:50]}')

print(f'\nAvailable symbols: {available}')

# If market is open, get current prices for some symbols
if clock.is_open:
    print('\n=== CURRENT PRICES ===')
    for sym in ['XLY', 'XLK', 'GLD', 'SLV', 'USO', 'UNG']:
        try:
            quote = api.get_latest_trade(sym)
            print(f'{sym}: ${quote.price:.2f}')
        except Exception as e:
            print(f'{sym}: Error getting price - {e}')
else:
    print('\nMarket is closed - checking for recent prices from last close')
    # Could get last trade or bar data if needed
    # For now, just note we can place limit orders for when market opens
