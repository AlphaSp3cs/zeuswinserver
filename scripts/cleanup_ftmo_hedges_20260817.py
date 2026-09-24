#!/usr/bin/env python3
"""
cleanup_ftmo_hedges_20260817.py
Close USDCHF hedge and reduce CVX concentration on FTMO LEFT.
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

def close_ticket(conn, ticket, symbol, volume, price, side):
    si = conn.symbol_info(symbol)
    if not si:
        return {'ticket': ticket, 'status': 'error', 'reason': 'no_symbol_info'}
    price = round_price(symbol, price, si.digits)
    req = {
        'action': conn.TRADE_ACTION_DEAL,
        'symbol': symbol,
        'volume': float(volume),
        'type': conn.ORDER_TYPE_SELL if side == 'buy' else conn.ORDER_TYPE_BUY,
        'price': float(price),
        'deviation': 20,
        'magic': int(datetime.now(timezone.utc).strftime('%Y%m%d%H%M')),
        'comment': 'cleanup_ioc',
        'type_time': conn.ORDER_TIME_GTC,
        'type_filling': conn.ORDER_FILLING_IOC,
        'position': int(ticket),
    }
    res = conn.order_send(req)
    if res is None:
        return {'ticket': ticket, 'status': 'error', 'reason': 'order_send_none'}
    status = 'executed' if res.retcode == conn.TRADE_RETCODE_DONE else 'failed'
    return {'ticket': ticket, 'status': status, 'retcode': int(res.retcode), 'comment': getattr(res, 'comment', ''), 'deal': getattr(res, 'deal', None)}

report = {'ts': TS, 'cleanup': {}, 'notes': []}

ftmo = mt5_connect('ftmo')
info = ftmo.account_info()
report['ftmo'] = {'login': int(info.login), 'server': info.server, 'equity': float(info.equity), 'margin_free': float(info.margin_free)}

ftmo_pos = get_positions(ftmo)
# Close USDCHF hedges: keep only newest short 520803126, close long 520774505 and old short 520793157
usdchf_close = [520774505, 520793157]
for ticket in usdchf_close:
    p = ftmo_pos[ticket]
    tick = ftmo.symbol_info_tick(p['symbol'])
    price = tick.bid if p['type'] == 0 else tick.ask
    r = close_ticket(ftmo, ticket, p['symbol'], p['volume'], price, 'buy' if p['type']==0 else 'sell')
    report['cleanup'][str(ticket)] = r

# Reduce CVX concentration: close older 9-lot 519748549, keep 11-lot new trade
cvx_close = [519748549]
for ticket in cvx_close:
    p = ftmo_pos[ticket]
    tick = ftmo.symbol_info_tick(p['symbol'])
    price = tick.bid if p['type'] == 0 else tick.ask
    r = close_ticket(ftmo, ticket, p['symbol'], p['volume'], price, 'buy' if p['type']==0 else 'sell')
    report['cleanup'][str(ticket)] = r

out = ROOT / 'artifacts' / f'dayshift_cleanup_{TS}.json'
out.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(f'WROTE {out}')
print(json.dumps(report, indent=2))
