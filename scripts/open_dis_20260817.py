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

report = {'ts': TS, 'trades': []}
ftmo = mt5_connect('ftmo')
existing = get_positions(ftmo)

key = ('DIS', 0)
if key in existing:
    report['trades'].append({'symbol':'DIS','side':'buy','broker':'ftmo','status':'skipped','reason':'already_open'})
else:
    si = mt5.symbol_info('DIS')
    ftmo.symbol_select('DIS', True)
    tick = mt5.symbol_info_tick('DIS')
    vol = valid_volume(si, 93)
    price = round(tick.ask, si.digits)
    req = {
        'action': ftmo.TRADE_ACTION_DEAL,
        'symbol': 'DIS',
        'volume': vol,
        'type': ftmo.ORDER_TYPE_BUY,
        'price': float(price),
        'deviation': 20,
        'magic': int(datetime.now(timezone.utc).strftime('%Y%m%d%H%M')),
        'comment': 'dayshift_disk',
        'type_time': ftmo.ORDER_TIME_GTC,
        'type_filling': ftmo.ORDER_FILLING_IOC,
    }
    res = ftmo.order_send(req)
    status = 'executed' if res and res.retcode == ftmo.TRADE_RETCODE_DONE else 'failed'
    result = {'symbol':'DIS','side':'buy','volume':vol,'price':price,'status':status,'reason':getattr(res,'comment',''),'retcode':int(res.retcode) if res else None,'order':getattr(res,'order',None),'deal':getattr(res,'deal',None),'broker':'ftmo'}
    if status == 'executed' and res.order:
        sl = round(price - 1.0, si.digits)
        tp = round(price + 2.0, si.digits)
        mod = {
            'action': ftmo.TRADE_ACTION_SLTP,
            'position': int(res.order),
            'sl': sl,
            'tp': tp,
            'magic': int(datetime.now(timezone.utc).strftime('%Y%m%d%H%M')),
            'comment': 'dayshift_disk_sltp',
        }
        mres = ftmo.order_send(mod)
        result['sltp_status'] = 'set' if mres and mres.retcode == ftmo.TRADE_RETCODE_DONE else 'failed'
        result['sl'] = sl
        result['tp'] = tp
    report['trades'].append(result)

print(json.dumps(report, indent=2))
print('last_error', mt5.last_error())
mt5_shutdown()
