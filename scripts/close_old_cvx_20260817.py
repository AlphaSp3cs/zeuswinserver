#!/usr/bin/env python3
import sys, json
from pathlib import Path
from datetime import datetime, timezone
ROOT = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
TS = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%MZ')
sys.path.insert(0, str(ROOT / 'scripts'))
from mt5_connect import connect as mt5_connect, shutdown as mt5_shutdown
import MetaTrader5 as mt5

def digits_for_sym(sym):
    s = sym.upper()
    if any(k in s for k in ['JPY']): return 3
    if any(k in s for k in ['XAU','XAG']): return 2
    if any(k in s for k in ['BTC','ETH']): return 2
    if any(k in s for k in ['US30','US500','NAS100']): return 1
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

report = {'ts': TS, 'cleanup': {}, 'trades': []}

ftmo = mt5_connect('ftmo')
existing = get_positions(ftmo)

old_cvx = 520800772
if old_cvx in existing:
    p = existing[old_cvx]
    tick = ftmo.symbol_info_tick(p['symbol'])
    price = tick.bid if p['type'] == 0 else tick.ask
    r = close_ticket(ftmo, old_cvx, p['symbol'], p['volume'], price, 'buy' if p['type']==0 else 'sell')
    report['cleanup']['ftmo_old_cvx'] = r

print(json.dumps(report, indent=2))
mt5_shutdown()
