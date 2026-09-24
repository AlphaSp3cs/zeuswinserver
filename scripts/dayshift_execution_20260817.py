#!/usr/bin/env python3
"""
dayshift_execution_20260817_v2.py
Places highest-conviction trades for the dayshift session.
Routes: FTMO_LEFT -> CAPITAL_RIGHT -> IBKR options pending gateway -> eToro skip
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
        'comment': 'cleanup_ftmo',
        'type_time': conn.ORDER_TIME_GTC,
        'type_filling': conn.ORDER_FILLING_IOC,
        'position': int(ticket),
    }
    res = conn.order_send(req)
    if res is None:
        return {'ticket': ticket, 'status': 'error', 'reason': 'order_send_none'}
    status = 'executed' if res.retcode == conn.TRADE_RETCODE_DONE else 'failed'
    return {'ticket': ticket, 'status': status, 'retcode': int(res.retcode), 'comment': getattr(res, 'comment', ''), 'deal': getattr(res, 'deal', None)}

def place_order_mt5(conn, sym, side, sl, tp, volume=0.01):
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
    req = {
        'action': conn.TRADE_ACTION_DEAL,
        'symbol': sym,
        'volume': volume,
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
        return {'symbol': sym, 'side': side, 'price': price, 'sl': sl, 'tp': tp, 'status': 'error', 'reason': 'order_send_none'}
    status = 'executed' if res.retcode == conn.TRADE_RETCODE_DONE else 'failed'
    return {'symbol': sym, 'side': side, 'volume': volume, 'price': price, 'sl': sl, 'tp': tp,
            'status': status, 'reason': getattr(res, 'comment', ''), 'retcode': int(res.retcode),
            'order': getattr(res, 'order', None), 'deal': getattr(res, 'deal', None)}

def place_order_capital_fok(conn, sym, side, sl, tp, volume=0.01):
    si = conn.symbol_info(sym)
    if not si:
        return {'symbol': sym, 'side': side, 'status': 'error', 'reason': 'no_symbol_info'}
    conn.symbol_select(sym, True)
    tick = conn.symbol_info_tick(sym)
    if not tick or tick.ask <= 0 or tick.bid <= 0:
        return {'symbol': sym, 'side': side, 'status': 'error', 'reason': 'no_tick'}
    d = digits_for_sym(sym)
    price = round(tick.ask if side == 'buy' else tick.bid, d)
    # open without SL/TP, then modify
    req = {
        'action': conn.TRADE_ACTION_DEAL,
        'symbol': sym,
        'volume': volume,
        'type': conn.ORDER_TYPE_BUY if side == 'buy' else conn.ORDER_TYPE_SELL,
        'price': float(price),
        'deviation': 20,
        'magic': int(datetime.now(timezone.utc).strftime('%Y%m%d%H%M')),
        'comment': 'dayshift_cap',
        'type_time': conn.ORDER_TIME_GTC,
        'type_filling': conn.ORDER_FILLING_FOK,
    }
    res = conn.order_send(req)
    if res is None:
        return {'symbol': sym, 'side': side, 'price': price, 'status': 'error', 'reason': 'order_send_none'}
    status = 'executed' if res.retcode == conn.TRADE_RETCODE_DONE else 'failed'
    result = {'symbol': sym, 'side': side, 'volume': volume, 'price': price,
              'status': status, 'reason': getattr(res, 'comment', ''), 'retcode': int(res.retcode),
              'order': getattr(res, 'order', None), 'deal': getattr(res, 'deal', None)}
    if status == 'executed' and res.order and sl is not None and tp is not None:
        mod = {
            'action': conn.TRADE_ACTION_SLTP,
            'position': int(res.order),
            'sl': round(sl, d),
            'tp': round(tp, d),
            'magic': int(datetime.now(timezone.utc).strftime('%Y%m%d%H%M')),
            'comment': 'dayshift_cap_sltp',
        }
        mres = conn.order_send(mod)
        result['sltp_status'] = 'set' if mres and mres.retcode == conn.TRADE_RETCODE_DONE else 'failed'
        result['sltp_retcode'] = int(mres.retcode) if mres else None
        result['sltp_comment'] = getattr(mres, 'comment', None)
        result['sl'] = round(sl, d)
        result['tp'] = round(tp, d)
    return result

def close_capital_position(conn, ticket, symbol, volume, side):
    si = conn.symbol_info(symbol)
    if not si:
        return {'ticket': ticket, 'status': 'error', 'reason': 'no_symbol_info'}
    conn.symbol_select(symbol, True)
    tick = conn.symbol_info_tick(symbol)
    price = round(tick.bid if side == 0 else tick.ask, si.digits)
    req = {
        'action': conn.TRADE_ACTION_DEAL,
        'symbol': symbol,
        'volume': float(volume),
        'type': conn.ORDER_TYPE_SELL if side == 0 else conn.ORDER_TYPE_BUY,
        'price': float(price),
        'deviation': 20,
        'magic': int(datetime.now(timezone.utc).strftime('%Y%m%d%H%M')),
        'comment': 'cleanup_cap_fok',
        'type_time': conn.ORDER_TIME_GTC,
        'type_filling': conn.ORDER_FILLING_FOK,
        'position': int(ticket),
    }
    res = conn.order_send(req)
    if res is None:
        return {'ticket': ticket, 'status': 'error', 'reason': 'order_send_none'}
    status = 'executed' if res.retcode == conn.TRADE_RETCODE_DONE else 'failed'
    return {'ticket': ticket, 'status': status, 'retcode': int(res.retcode), 'comment': getattr(res, 'comment', ''), 'deal': getattr(res, 'deal', None)}

report = {'ts': TS, 'cleanup': {}, 'trades': [], 'notes': []}

# Connect FTMO
try:
    ftmo = mt5_connect('ftmo')
    info = ftmo.account_info()
    report['ftmo'] = {'login': int(info.login), 'server': info.server, 'equity': float(info.equity), 'margin_free': float(info.margin_free)}
except Exception as e:
    report['ftmo'] = {'error': str(e)}
    ftmo = None

# Connect Capital
try:
    cap = mt5_connect('capital')
    info = cap.account_info()
    report['capital'] = {'login': int(info.login), 'server': info.server, 'equity': float(info.equity), 'margin_free': float(info.margin_free)}
except Exception as e:
    report['capital'] = {'error': str(e)}
    cap = None

# FTMO cleanup: close duplicate/high-loss groups
if ftmo:
    ftmo_pos = get_positions(ftmo)
    targets = []
    seen = {}
    for ticket, p in ftmo_pos.items():
        key = (p['symbol'], p['type'])
        if key in seen:
            targets.append({'ticket': ticket, 'symbol': p['symbol'], 'type': p['type'], 'volume': p['volume'], 'reason': 'duplicate'})
        else:
            seen[key] = ticket
    for ticket, p in ftmo_pos.items():
        if p['profit'] < -10 and ticket not in [t['ticket'] for t in targets]:
            targets.append({'ticket': ticket, 'symbol': p['symbol'], 'type': p['type'], 'volume': p['volume'], 'reason': 'high_loss', 'profit': p['profit']})
    report['cleanup']['ftmo_targets'] = targets
    for t in targets:
        sym = t['symbol']
        tick = ftmo.symbol_info_tick(sym)
        price = tick.bid if t['type'] == 0 else tick.ask
        r = close_ticket(ftmo, t['ticket'], sym, t['volume'], price, 'buy' if t['type']==0 else 'sell')
        r['reason'] = t['reason']
        report['cleanup'].setdefault('ftmo_results', []).append(r)

# Capital cleanup: close worst/naked tickets using FOK
if cap:
    cap_pos = get_positions(cap)
    targets = []
    for ticket, p in cap_pos.items():
        naked = (p['sl'] == 0 and p['tp'] == 0)
        big_loss = p['profit'] < -20
        if naked or big_loss:
            targets.append({'ticket': ticket, 'symbol': p['symbol'], 'type': p['type'], 'volume': p['volume'], 'reason': 'naked' if naked else 'big_loss', 'profit': p['profit']})
    report['cleanup']['capital_targets'] = targets
    for t in targets:
        r = close_capital_position(cap, t['ticket'], t['symbol'], t['volume'], t['type'])
        r['reason'] = t['reason']
        report['cleanup'].setdefault('capital_results', []).append(r)

# FTMO new trades
ftmo_trades = [
    {'symbol': 'CVX', 'side': 'buy', 'sl': 197.10, 'tp': 203.70, 'volume': 11},
    {'symbol': 'DIS', 'side': 'buy', 'sl': 105.65, 'tp': 108.05, 'volume': 93},
    {'symbol': 'USDCHF', 'side': 'sell', 'sl': 0.81944, 'tp': 0.80880, 'volume': 0.01},
]
if ftmo:
    existing = get_positions(ftmo)
    for trade in ftmo_trades:
        key = (trade['symbol'], 0 if trade['side']=='buy' else 1)
        if key in existing:
            report['trades'].append({**trade, 'broker': 'ftmo', 'status': 'skipped', 'reason': 'already_open'})
            continue
        r = place_order_mt5(ftmo, trade['symbol'], trade['side'], trade['sl'], trade['tp'], trade['volume'])
        r['broker'] = 'ftmo'
        report['trades'].append(r)

# Capital new trades
cap_trades = [
    {'symbol': 'XRPUSD', 'side': 'buy', 'sl': 0.97854, 'tp': 1.00691, 'volume': 0.01},
]
if cap:
    existing = get_positions(cap)
    for trade in cap_trades:
        key = (trade['symbol'], 0 if trade['side']=='buy' else 1)
        if key in existing:
            report['trades'].append({**trade, 'broker': 'capital', 'status': 'skipped', 'reason': 'already_open'})
            continue
        r = place_order_capital_fok(cap, trade['symbol'], trade['side'], trade['sl'], trade['tp'], trade['volume'])
        r['broker'] = 'capital'
        report['trades'].append(r)

# IBKR options plan
report['ibkr_options_plan'] = {
    'status': 'pending_ibkr_online',
    'note': 'IBKR gateway refused on 127.0.0.1:7497. Open TWS/IBG before placing options.',
    'plan': [
        {'underlying': 'NVDA', 'direction': 'LONG_CALL', 'strike': 118.75, 'expiry': '20260915', 'qty': 1},
        {'underlying': 'JPM', 'direction': 'LONG_CALL', 'strike': 185.25, 'expiry': '20260915', 'qty': 1},
        {'underlying': 'SPY', 'direction': 'LONG_CALL', 'strike': 547.41, 'expiry': '20260915', 'qty': 1},
        {'underlying': 'QQQ', 'direction': 'LONG_CALL', 'strike': 473.57, 'expiry': '20260915', 'qty': 1},
        {'underlying': 'AAPL', 'direction': 'LONG_CALL', 'strike': 213.75, 'expiry': '20260915', 'qty': 1},
    ]
}

out = ROOT / 'artifacts' / f'dayshift_exec_{TS}.json'
out.write_text(json.dumps(report, indent=2), encoding='utf-8')
print(f'WROTE {out}')
print(json.dumps(report, indent=2))
