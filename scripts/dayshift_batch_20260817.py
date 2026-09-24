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

ftmo = mt5_connect('ftmo')
cap = mt5_connect('capital')
report = {'ts': TS, 'cleanup': {}, 'trades': []}

existing = get_positions(ftmo)
# Close old CVX 1.0 lot duplicate
old_cvx = 520800772
if old_cvx in existing:
    p = existing[old_cvx]
    tick = ftmo.symbol_info_tick(p['symbol'])
    price = tick.bid if p['type'] == 0 else tick.ask
    r = close_ticket(ftmo, old_cvx, p['symbol'], p['volume'], price, 'buy' if p['type']==0 else 'sell')
    report['cleanup']['ftmo_old_cvx'] = r

# FTMO trades
ftmo_trades = [
    {'symbol':'USDCHF','side':'sell','sl':0.81944,'tp':0.80880,'volume':0.01},
    {'symbol':'EURUSD','side':'buy','sl':1.15383,'tp':1.16600,'volume':0.01},
    {'symbol':'GBPUSD','side':'buy','sl':1.34967,'tp':1.36526,'volume':0.01},
    {'symbol':'XAUUSD','side':'buy','sl':4294.27,'tp':4581.22,'volume':0.01},
    {'symbol':'XAGUSD','side':'buy','sl':64.0,'tp':68.0,'volume':0.01},
]
for trade in ftmo_trades:
    key = (trade['symbol'], 0 if trade['side']=='buy' else 1)
    if key in existing:
        report['trades'].append({**trade, 'broker':'ftmo','status':'skipped','reason':'already_open'})
        continue
    r = place_order(ftmo, trade['symbol'], trade['side'], trade['sl'], trade['tp'], trade['volume'])
    r['broker'] = 'ftmo'
    report['trades'].append(r)

existing_cap = get_positions(cap)
cap_trades = [
    {'symbol':'AVAXUSD','side':'sell','sl':6.43,'tp':6.23,'volume':110},
    {'symbol':'XAUUSD','side':'buy','sl':4290.0,'tp':4450.0,'volume':0.01},
    {'symbol':'XAGUSD','side':'buy','sl':64.0,'tp':68.0,'volume':0.01},
    {'symbol':'NATGAS','side':'buy','sl':2.60,'tp':2.90,'volume':0.01},
]
for trade in cap_trades:
    key = (trade['symbol'], 0 if trade['side']=='buy' else 1)
    if key in existing_cap:
        report['trades'].append({**trade, 'broker':'capital','status':'skipped','reason':'already_open'})
        continue
    si = mt5.symbol_info(trade['symbol'])
    cap.symbol_select(trade['symbol'], True)
    tick = mt5.symbol_info_tick(trade['symbol'])
    if not si or not tick or tick.ask <= 0:
        report['trades'].append({**trade, 'broker':'capital','status':'error','reason':'no_symbol_info_or_tick'})
        continue
    d = digits_for_sym(trade['symbol'])
    price = round(tick.ask if trade['side']=='buy' else tick.bid, d)
    vol = valid_volume(si, trade['volume'])
    req = {
        'action': cap.TRADE_ACTION_DEAL,
        'symbol': trade['symbol'],
        'volume': vol,
        'type': cap.ORDER_TYPE_BUY if trade['side']=='buy' else cap.ORDER_TYPE_SELL,
        'price': float(price),
        'deviation': 20,
        'magic': int(datetime.now(timezone.utc).strftime('%Y%m%d%H%M')),
        'comment': 'dayshift_cap_fok',
        'type_time': cap.ORDER_TIME_GTC,
        'type_filling': cap.ORDER_FILLING_FOK,
    }
    res = cap.order_send(req)
    status = 'executed' if res and res.retcode == cap.TRADE_RETCODE_DONE else 'failed'
    result = {'symbol': trade['symbol'], 'side': trade['side'], 'volume': vol, 'price': price,
              'status': status, 'reason': getattr(res, 'comment', ''), 'retcode': int(res.retcode) if res else None,
              'order': getattr(res, 'order', None), 'deal': getattr(res, 'deal', None), 'broker': 'capital'}
    if status == 'executed' and res.order:
        mod = {
            'action': cap.TRADE_ACTION_SLTP,
            'position': int(res.order),
            'sl': round(trade['sl'], d),
            'tp': round(trade['tp'], d),
            'magic': int(datetime.now(timezone.utc).strftime('%Y%m%d%H%M')),
            'comment': 'dayshift_cap_sltp',
        }
        mres = cap.order_send(mod)
        result['sltp_status'] = 'set' if mres and mres.retcode == cap.TRADE_RETCODE_DONE else 'failed'
        result['sltp_retcode'] = int(mres.retcode) if mres else None
        result['sltp_comment'] = getattr(mres, 'comment', None)
        result['sl'] = round(trade['sl'], d)
        result['tp'] = round(trade['tp'], d)
    report['trades'].append(result)

print(json.dumps(report, indent=2))
mt5_shutdown()
