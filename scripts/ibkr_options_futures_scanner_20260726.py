#!/usr/bin/env python3
"""
IBKR Options & Futures Chain Scanner
Scans for high probability options setups on existing positions
and futures opportunities
"""

import sys, os
sys.path.insert(0, 'C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
os.chdir('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')

from pathlib import Path
import json
import datetime
import time

# Load .env
env_path = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/.env')
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            key, value = line.split('=', 1)
            os.environ[key.strip()] = value.strip().strip('"').strip("'")

from ibapi.client import EClient
from ibapi.wrapper import EWrapper
from ibapi.contract import Contract
from ibapi.common import BarData

IBKR_HOST = os.environ.get('IBKR_HOST', '127.0.0.1')
IBKR_PORT = int(os.environ.get('IBKR_PORT', '7497'))
IBKR_CLIENT_ID = int(os.environ.get('IBKR_CLIENT_ID', '1'))
IBKR_ACCOUNT = os.environ.get('IBKR_ACCOUNT', '')

class IBKROptionsScanner(EWrapper, EClient):
    def __init__(self):
        EClient.__init__(self, self)
        self.positions = []
        self.account_values = {}
        self.options_chains = {}
        self.futures_chains = {}
        self.contract_details = {}
        self.done = False
        self.next_order_id = None
        self.req_id = 0
    
    def nextValidId(self, orderId):
        self.next_order_id = orderId
        self.reqPositions()
    
    def position(self, account, contract, position, avgCost):
        self.positions.append({
            'account': account,
            'symbol': contract.symbol,
            'sec_type': contract.secType,
            'exchange': contract.exchange,
            'position': position,
            'avg_cost': avgCost,
        })
    
    def positionEnd(self):
        # Now get account values
        self.reqAccountSummary()
    
    def accountSummary(self, reqId, account, tag, value, currency):
        self.account_values[tag] = {'account': account, 'value': value, 'currency': currency}
    
    def accountSummaryEnd(self, reqId):
        # Scan options for existing stock positions
        self.scan_options_for_positions()
    
    def scan_options_for_positions(self):
        stock_symbols = list(set([p['symbol'] for p in self.positions if p['sec_type'] == 'STK' and p['position'] != 0]))
        print(f"Scanning options for {len(stock_symbols)} stocks: {stock_symbols}")
        
        for sym in stock_symbols[:8]:  # Limit to 8 to avoid overload
            self.req_id += 1
            contract = Contract()
            contract.symbol = sym
            contract.secType = 'STK'
            contract.exchange = 'SMART'
            contract.currency = 'USD'
            self.reqContractDetails(self.req_id, contract)
            time.sleep(0.3)
        
        # Also scan futures
        futures_symbols = ['MES', 'MNQ', 'ES', 'NQ', 'GC', 'SI', 'CL', 'NG']
        for sym in futures_symbols:
            self.req_id += 1
            contract = Contract()
            contract.symbol = sym
            contract.secType = 'FUT'
            contract.exchange = 'GLOBEX'
            contract.currency = 'USD'
            # Use current front month
            contract.lastTradeDateOrContractMonth = '202609'
            self.reqContractDetails(self.req_id, contract)
            time.sleep(0.3)
        
        self.done = True
        self.disconnect()
    
    def contractDetails(self, reqId, contractDetails):
        symbol = contractDetails.contract.symbol
        sec_type = contractDetails.contract.secType
        
        info = {
            'symbol': symbol,
            'exchange': contractDetails.contract.exchange,
            'currency': contractDetails.contract.currency,
            'min_tick': contractDetails.minTick,
            'multiplier': contractDetails.contract.multiplier,
        }
        
        if sec_type == 'STK':
            if symbol not in self.options_chains:
                self.options_chains[symbol] = []
            self.options_chains[symbol].append(info)
        elif sec_type == 'FUT':
            if symbol not in self.futures_chains:
                self.futures_chains[symbol] = []
            self.futures_chains[symbol].append(info)
    
    def contractDetailsEnd(self, reqId):
        pass


def main():
    print("="*70)
    print("IBKR OPTIONS & FUTURES SCANNER")
    print("="*70)
    
    app = IBKROptionsScanner()
    app.connect(IBKR_HOST, IBKR_PORT, clientId=IBKR_CLIENT_ID + 100)
    
    timeout = 15
    start = time.time()
    while not app.done and time.time() - start < timeout:
        app.run()
        time.sleep(0.2)
    
    results = {
        'timestamp': datetime.datetime.now().isoformat(),
        'ibkr_account': IBKR_ACCOUNT,
        'positions': app.positions,
        'account_values': app.account_values,
        'options_chains': app.options_chains,
        'futures_chains': app.futures_chains,
    }
    
    out = Path('ibkr_options_futures_scan_2026-07-26.json')
    out.write_text(json.dumps(results, indent=2))
    print(f"\nSaved: {out}")
    
    print(f"\nIBKR Account:")
    for k in ['NetLiquidation', 'BuyingPower', 'Cash', 'EquityWithLoanValue']:
        if k in app.account_values:
            v = app.account_values[k]
            print(f"  {k}: {v['value']} {v['currency']}")
    
    print(f"\nExisting Positions ({len(app.positions)}):")
    for p in app.positions:
        print(f"  {p['symbol']:12} {p['sec_type']:8} pos={p['position']:>6} avgCost={p['avg_cost']:>10.2f}")
    
    print(f"\nOptions Chains Available: {len(app.options_chains)} symbols")
    for sym, chains in app.options_chains.items():
        print(f"  {sym}: {len(chains)} exchanges")
    
    print(f"\nFutures Chains Available: {len(app.futures_chains)} symbols")
    for sym, chains in app.futures_chains.items():
        print(f"  {sym}: {len(chains)} contracts")
    
    app.disconnect()
    print("\n" + "="*70)
    print('Awuuuu!!!! the pack is finished.')
    print("="*70)


if __name__ == '__main__':
    main()
