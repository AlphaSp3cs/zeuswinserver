#!/usr/bin/env python3
import os, math, json, time, MetaTrader5 as mt5
from datetime import datetime
from pathlib import Path

cap = r'C:\Program Files\Capital.com MetaTrader 5\terminal64.exe'
ftmo = r'REDACTED-PATH'
REPORT = []

def now_tag(): return datetime.now().strftime('%H:%M:%S')
def append(section, data): REPORT.append({'time': now_tag(), 'section': section, 'data': data})

def connect(label, terminal):
    mt5.shutdown()
    ok = mt5.initialize(path=terminal, timeout=10000)
    if not ok:
        append('init', {'label': label, 'ok': False, 'error': mt5.last_error()})
        return False
    info = mt5.account_info()
    append('init', {'label': label, 'ok': True, 'login': int(info.login), 'trade_allowed': bool(info.trade_allowed), 'margin_free': round(float(info.margin_free),2)})
    return True

def feasibility(label, symbol):
    info = mt5.symbol_info(symbol)
    if info is None:
        return {'ok': False, 'reason': 'symbol_info=None'}
    if not info.visible:
        mt5.symbol_select(symbol, True)
    tick = mt5.symbol_info_tick(symbol)
    if tick is None or tick.bid <= 0 or tick.ask <= 0:
        return {'ok': False, 'reason': 'tick_zero_or_none'}
    return {
        'ok': True, 'bid': float(tick.bid), 'ask': float(tick.ask),
        'digits': int(info.digits), 'point': float(info.point),
        'trade_mode': int(info.trade_mode), 'filling_mode': int(info.filling_mode),
        'volume_min': float(info.volume_min), 'volume_max': float(info.volume_max),
        'volume_step': float(info.volume_step), 'contract_size': float(getattr(info, 'trade_contract_size', 1.0)),
        'stops_level': float(getattr(info, 'trade_stops_level', 0.0))
    }

def size_by_risk(equity, entry, sl, info):
    risk = equity * 0.01
    dist = abs(entry - sl)
    if dist <= 0:
        return 0.0, 'bad_sl'
    raw = risk / (dist * info['contract_size'])
    step = info['volume_step'] or 0.01
    vmin = info['volume_min'] or step
    qty = max(math.floor(raw / step) * step, vmin)
    qty = min(qty, info['volume_max'])
    if qty < vmin:
        return 0.0, 'sized_below_min'
    return round(qty, 8 if step < 0.001 else 2), 'ok'

def place_order(label, symbol, side, price, sl, tp, volume):
    info = mt5.symbol_info(symbol)
    order_type = mt5.ORDER_TYPE_BUY if side == 'buy' else mt5.ORDER_TYPE_SELL
    preferred = [mt5.ORDER_FILLING_FOK, mt5.ORDER_FILLING_IOC, mt5.ORDER_FILLING_RETURN]
    attempted = []
    last_res = None
    for filling_used in preferred:
        request = {
            'action': mt5.TRADE_ACTION_DEAL, 'symbol': symbol, 'volume': float(volume),
            'type': order_type, 'price': price, 'sl': float(sl), 'tp': float(tp),
            'deviation': 50, 'magic': 20260810, 'comment': f'zeus-auto-{label}',
            'type_time': mt5.ORDER_TIME_GTC, 'type_filling': filling_used,
        }
        res = mt5.order_send(request)
        attempted.append({'filling': int(filling_used), 'retcode': getattr(res, 'retcode', None), 'comment': getattr(res, 'comment', None), 'order': getattr(res, 'order', None), 'deal': getattr(res, 'deal', None)})
        last_res = res
        rc = getattr(res, 'retcode', None)
        if rc in (10009,):
            append('place', {
                'label': label, 'symbol': symbol, 'side': side, 'volume': volume,
                'price': price, 'sl': sl, 'tp': tp,
                'retcode': rc, 'comment': getattr(res, 'comment', None),
                'order': getattr(res, 'order', None), 'deal': getattr(res, 'deal', None),
                'attempts': attempted
            })
            return res
    append('place', {
        'label': label, 'symbol': symbol, 'side': side, 'volume': volume,
        'price': price, 'sl': sl, 'tp': tp,
        'retcode': getattr(last_res, 'retcode', None), 'comment': getattr(last_res, 'comment', None),
        'order': getattr(last_res, 'order', None), 'deal': getattr(last_res, 'deal', None),
        'attempts': attempted
    })
    return last_res

def verify_fill(label, symbol, expected_volume):
    time.sleep(1)
    pos = mt5.positions_get(symbol=symbol)
    filled = None
    if pos:
        for p in pos:
            if p.symbol == symbol and abs(float(p.volume) - float(expected_volume)) < 1e-9:
                filled = {'ticket': int(p.ticket), 'volume': float(p.volume), 'profit': float(p.profit)}
                break
    append('verify', {'label': label, 'symbol': symbol, 'filled': filled})
    return filled

candidates = [
    {'symbol': 'ETHUSD', 'side': 'buy'},
    {'symbol': 'XRPUSD', 'side': 'buy'},
    {'symbol': 'XMRUSD', 'side': 'buy'},
]

cap_ok = connect('CAPITAL_RIGHT', cap)
ftmo_ok = connect('FTMO_LEFT', ftmo)
executed = []
blocked = []

for cand in candidates:
    sym = cand['symbol']
    side = cand['side']
    assigned = None
    feas = None
    for broker in ['CAPITAL_RIGHT', 'FTMO_LEFT']:
        if broker == 'CAPITAL_RIGHT' and not cap_ok:
            continue
        if broker == 'FTMO_LEFT' and not ftmo_ok:
            continue
        feas = feasibility(broker, sym)
        if feas.get('ok'):
            assigned = broker
            break
    if not assigned or not feas:
        blocked.append({'symbol': sym, 'reason': 'no_broker_or_feasibility', 'details': feas})
        continue
    mt5.shutdown()
    if assigned == 'CAPITAL_RIGHT':
        connect('CAPITAL_RIGHT', cap)
    else:
        connect('FTMO_LEFT', ftmo)
    info = mt5.account_info()
    equity = float(info.equity)
    min_stop_dist = max(feas['stops_level'] * 5 * feas['point'], 0.05 if sym != 'XRPUSD' else 0.0005)
    vol, qreason = size_by_risk(equity, feas['ask'], feas['ask'] - min_stop_dist, feas)
    if vol <= 0:
        blocked.append({'symbol': sym, 'broker': assigned, 'reason': qreason})
        continue
    res = place_order(assigned, sym, side, feas['ask'], round(feas['ask'] - min_stop_dist, feas['digits']), round(feas['ask'] + min_stop_dist * 2, feas['digits']), vol)
    rc = getattr(res, 'retcode', None) if res else None
    if rc == 10009:
        fill = verify_fill(assigned, sym, vol)
        executed.append({'symbol': sym, 'broker': assigned, 'retcode': rc, 'fill': fill})
    else:
        blocked.append({'symbol': sym, 'broker': assigned, 'retcode': rc, 'comment': getattr(res, 'comment', None)})

append('summary', {'executed': executed, 'blocked': blocked})
out = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm\workflow\eth_xrp_xmr_spec_repair_20260810.json')
out.write_text(json.dumps(REPORT, indent=2, default=str), encoding='utf-8')
print('WROTE', out)
print('EXECUTED', len(executed))
for e in executed:
    print(e)
print('BLOCKED', len(blocked))
for b in blocked:
    print(b)
mt5.shutdown()