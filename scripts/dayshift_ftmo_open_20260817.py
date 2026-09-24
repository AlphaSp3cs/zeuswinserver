#!/usr/bin/env python3
"""
dayshift_ftmo_open_v3_20260817.py
Open highest-conviction trades on FTMO LEFT using valid lot sizes.
"""
import json, sys
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
TS = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%MZ')
sys.path.insert(0, str(ROOT / 'scripts'))
from mt5_connect import connect as mt5_connect, shutdown as mt5_shutdown
import MetaTrader5 as mt5

def digits_for_sym(sym):
    s = sym.upper()
    if any(k in s for k in ['JPY','JP225']): return 3
    if any(k in s for k in ['XAU','XAG','XPT','XPD']): return 2
    if any(k in s for k in ['BTC','ETH']): return 2
    if any(k in s for k in ['US30','US500','NAS100','UK100','GER40','HK50','ES','NQ','YM','RTY']): return 1
    return 5

def round_price(sym, price, digits=None):
    d = digits if digits is not None else digits_for_sym(sym)
    return round(float(price), d)

def get_positions(conn):
    pos = conn.positions_get()
    m = {}
    if pos:
        for p in pos:
            m[int(p.ticket)] = {
                'ticket': int(p.ticket), 'symbol': p.symbol, 'type': int(p.type),
                'volume': float(p.volume), 'price_open': float(p.price_open),
                'sl': float(getattr(p, 'sl', 0) or 0), 'tp': float(getattr(p, 'tp', 0) or 0),
                'profit': float(p.profit),
            }
    return m

def valid_volume(si, desired):
    vmin = float(si.volume_min)
    vmax = float(si.volume_max)
    vstep = float(si.volume_step)
    vol = max(vmin, min(float(desired), vmax))
    vol = round((vol - vmin) / vstep) * vstep + vmin
    if vol < vmin or vol > vmax:
        vol = vmin
    return float(vol)

def place_order(conn, sym, side, sl, tp, volume=0.01):
    si = conn.symbol_info(sym)
    if not si:
        return {'symbol': sym, 'side': side, 'status': 'error', 'reason': 'no_symbol_info'}
    conn.symbol_select(sym, True)
    tick = conn.symbol_info_tick(sym)
    if not tick or tick.ask <= 0 or tick.bid <= 0:
        return {'symbol': sym, 'side': side, 'status': 'error', 'reason': 'no_tick'}
    d = digits_for_sym(sym)
    price = round(tick.ask if side == 'buy' else tick.bid, d)
    sl = round(sl, d); tp = round(tp, d)
    vol = valid_volume(si, volume)
    req = {
        'action': conn.TRADE_ACTION_DEAL,
        'symbol': sym,
        'volume': vol,
        'type': conn.ORDER_TYPE_BUY if side == 'buy' else conn.ORDER_TYPE_SELL,
        'price': float(price),
        'sl': float(sl),
        'tp': float(tp),
        'deviation': 20,
        'magic': int(datetime.now(timezone.utc).strftime('%Y%m%d%H%M')),
        'comment': 'dayshift_ioc',
        'type_time': conn.ORDER_TIME_GTC,
        'type_filling': conn.ORDER_FILLING_IOC,
    }
    res = conn.order_send(req)
    if res is None:
        return {'symbol': sym, 'side': side, 'price': price, 'sl': sl, 'tp': tp, 'volume': vol, 'status': 'error', 'reason': 'order_send_none'}
    status = 'executed' if res.retcode == conn.TRADE_RETCODE_DONE else 'failed'
    return {'symbol': sym, 'side': side, 'volume': vol, 'price': price, 'sl': sl, 'tp': tp,
            'status': status, 'reason': getattr(res, 'comment', ''), 'retcode': int(res.retcode),
            'order': getattr(res, 'order', None), 'deal': getattr(res, 'deal', None)}

report = {'ts': TS, 'trades': [], 'notes': []}

try:
    ftmo = mt5_connect('ftmo')
    info = ftmo.account_info()
    report['ftmo'] = {'login': int(info.login), 'server': info.server, 'equity': float(info.equity), 'margin_free': float(info.margin_free)}
except Exception as e:
    report['ftmo'] = {'error': str(e)}
    ftmo = None

if not ftmo:
    print(json.dumps(report, indent=2))
    sys.exit(1)

trades = [
    {'symbol': 'CVX', 'side': 'buy', 'entry': 201.46, 'sl': 197.10, 'tp': 203.70, 'volume': 11},
    {'symbol': 'DIS', 'side': 'buy', 'entry': 105.84, 'sl': 105.65, 'tp': 108.05, 'volume': 93},
    {'symbol': 'USDCHF', 'side': 'sell', 'entry': 0.80952, 'sl': 0.81944, 'tp': 0.80880, 'volume': 0.01},
]

existing = get_positions(ftmo)
for trade in trades:
    key = (trade['symbol'], 0 if trade['side']=='buy' else 1)
    if key in existing:
        report['trades'].append({**trade, 'broker': 'ftmo', 'status': 'skipped', 'reason': 'already_open'})
        continue
    r = place_order(ftmo, trade['symbol'], trade['side'], trade['sl'], trade['tp'], trade['volume'])
    r['broker'] = 'ftmo'
    report['trades'].append(r)

out = ROOT / 'artifacts' / f'dayshift_ftmo_open_{TS}.json'
out.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(f'WROTE {out}')
print(json.dumps(report, indent=2))
