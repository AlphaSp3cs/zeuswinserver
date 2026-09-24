#!/usr/bin/env python3
"""
Quick Alpaca connection test with fresh credentials
"""
import os
from alpaca_trade_api import REST
import sys

# Load credentials directly from the file we know is correct
with open('/c/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/allapi2026.txt', 'r') as f:
    lines = f.readlines()
    api_key = None
    secret_key = None
    for line in lines:
        if line.startswith('key ') and 'PKVNQKZUHYABWMIDJYLCMG6XQV' in line:
            api_key = line.split()[1]
        elif line.startswith('secret ') and '5hDg2Jang2XmQfecaLzdNLEFXK5ZvAemVB5nQKNWD4eE' in line:
            secret_key = line.split()[1]

print(f"API Key: {api_key}")
print(f"Secret Key: {secret_key}")

if not api_key or not secret_key:
    print("ERROR: Could not extract credentials from allapi2026.txt")
    sys.exit(1)

# Test connection
api = REST(api_key, secret_key, 'https://paper-api.alpaca.markets', api_version='v2')
try:
    account = api.get_account()
    print("SUCCESS: Alpaca connection established")
    print(f"Account ID: {account.id}")
    print(f"Status: {account.status}")
    print(f"Buying Power: ${float(account.buying_power):,.2f}")
    print(f"Cash: ${float(account.cash):,.2f}")
    print(f"Portfolio Value: ${float(account.portfolio_value):,.2f}")
except Exception as e:
    print(f"ERROR: {e}")
    print(f"Error type: {type(e).__name__}")