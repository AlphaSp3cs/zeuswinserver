#!/usr/bin/env python3
"""Zeus recheck + workflow test. Validates FTMO pending orders against trend/DD
and confirms broker waterfall for gap symbols. Challenge-account mandate:
DROP only if rechecked wrong trend OR projected DD breach."""
import MetaTrader5 as mt5, os, json, time

FTMO = 'C:/Program Files/FTMO Global Markets MT5 Terminal/terminal64.exe'

def load_scan():
    import glob, datetime
    base = 'C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/loads/Scan protocol'
    fs = sorted(glob.glob(base + '/sector_scan_results_*.json'))
    return json.loads(open(fs[-1]).read()) if fs else {}

scan = load_scan()
longs = {c['symbol']: c for c in scan.get('qualified_longs', [])}
shorts = {c['symbol']: c for c in scan.get('qualified_shorts', [])}

print('=== FTMO PENDING ORDER RECHECK ===')
if mt5.initialize(path=FTMO):
    acc = mt5.account_info()
    eq = acc.equity
    daily_start = eq  # proxy; real challenge tracks day-open equity
    daily_dd_cap = eq * 0.05
    total_dd_cap = acc.balance * 0.10
    print(f"Equity ${eq:.2f} | DAILY DD cap ${daily_dd_cap:.2f} | TOTAL DD cap ${total_dd_cap:.2f}")
    orders = mt5.orders_get() or []
    keep, drop = [], []
    for o in orders:
        sym = o.symbol
        tick = mt5.symbol_info_tick(sym)
        bid = tick.bid if tick else None
        ask = tick.ask if tick else None
        # Recheck logic
        entry = o.price_open
        sl = o.sl
        tp = o.tp
        # Wrong trend: for a BUY_LIMIT, if price already blew through SL -> invalid
        wrong_trend = (bid is not None and bid <= sl)
        # Projected DD if filled: risk = |entry-sl|*vol*csize
        info = mt5.symbol_info(sym)
        csize = info.trade_contract_size if info else 1
        risk = abs(entry - sl) * o.volume_initial * csize
        dd_breach = risk > daily_dd_cap  # single ticket exceeds daily cap
        verdict = 'KEEP'
        reason = 'valid limit, trend intact'
        if wrong_trend:
            verdict = 'DROP'; reason = 'price <= SL (wrong trend)'
        elif dd_breach:
            verdict = 'DROP'; reason = f'risk ${risk:.0f} > daily cap ${daily_dd_cap:.0f}'
        (drop if verdict == 'DROP' else keep).append((sym, verdict, reason, risk))
        print(f"  {sym:8} entry={entry} sl={sl} tp={tp} bid={bid} risk=${risk:.0f} -> {verdict} ({reason})")
    print(f"\nKEEP: {len(keep)} | DROP: {len(drop)}")
    if drop:
        print("Would cancel:", [d[0] for d in drop])
    mt5.shutdown()

print('\n=== BROKER WATERFALL TEST (5 gap symbols) ===')
gaps = ['ZEC', 'AAVE', 'AVAX', 'WLD', 'NEAR']
# FTMO
if mt5.initialize(path=FTMO):
    syms = {s.name for s in mt5.symbols_get()}
    ftmo_has = {g: f'{g}USD' in syms for g in gaps}
    mt5.shutdown()
else:
    ftmo_has = {g: False for g in gaps}
print('FTMO carries:', ftmo_has)

# Kraken balance
import re, krakenex
txt = open('C:/Users/bravo-usr1/Desktop/api2026v2.txt').read()
ak = re.search(r'apikey\*\s*(\S+)', txt).group(1).strip()
pk = re.search(r'private key\*\s*(\S+)', txt).group(1).strip()
k = krakenex.API(key=ak, secret=pk)
kr = k.query_private('Balance')
kr_bal = sum(float(v) for v in kr['result'].values())
kr_pairs = {g: f'{g}USD' for g in gaps if f'{g}USD' in (k.query_public('AssetPairs').get('result') or {})}
print(f'Kraken balance ${kr_bal:.2f} | pairs: {kr_pairs}')

# Alpaca BP
import requests
akey = re.search(r'key\*\s*(PK\S+)', txt).group(1).strip()
asec = re.search(r'secret\*\s*(EP\S+)', txt).group(1).strip()
h = {'APCA-API-KEY-ID': akey, 'APCA-API-SECRET-KEY': asec}
ar = requests.get('https://paper-api.alpaca.markets/v2/account', headers=h, timeout=15).json()
alp_bp = float(ar.get('buying_power', 0))
alp_pairs = {}
for g in gaps:
    r = requests.get(f'https://paper-api.alpaca.markets/v2/assets/{g}USD', headers=h, timeout=10)
    alp_pairs[g] = (r.status_code == 200 and r.json().get('tradable'))
print(f'Alpaca BP ${alp_bp:.2f} | tradable: {alp_pairs}')

print('\n=== WATERFALL VERDICT ===')
for g in gaps:
    route = 'NONE'
    if ftmo_has.get(g):
        route = 'FTMO'
    elif kr_bal > 10:
        route = 'KRAKEN'
    elif alp_bp > 10:
        route = 'ALPACA'
    print(f"  {g:5} -> {route} (FTMO={ftmo_has.get(g)} Kraken=${kr_bal:.0f} Alpaca=${alp_bp:.0f})")