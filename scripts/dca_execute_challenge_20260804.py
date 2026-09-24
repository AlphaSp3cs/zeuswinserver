#!/usr/bin/env python3
"""
DCA execution script for FTMO challenge beat plan.
Adds size at predefined levels for confirmed live book trades.
"""
import json, time
from pathlib import Path
from datetime import datetime, timezone
import MetaTrader5 as mt5

TERMINAL = r'C:\Program Files\FTMO MetaTrader 5\terminal64.exe'
LOGIN = int(os.environ.get('FTMO_MT5_LOGIN', '0'))
PW = os.environ.get('FTMO_MT5_PASSWORD', '')
SERVER = os.environ.get('FTMO_MT5_SERVER', '')
BASE = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
OUT = BASE / 'artifacts' / f'dca_execution_20260804T{datetime.now(timezone.utc).strftime("%H%M")}Z.json'

DCA_PLAN = {
  'EURJPY': {'side':'LONG','levels':[180.473,180.241,180.009],'base_sl':179.197,'base_tp':182.506,'base_vol':0.01,'dca_vol':0.01,'max_dca':3},
  'GBPJPY': {'side':'LONG','levels':[210.806,210.508,210.210],'base_sl':209.114,'base_tp':213.628,'base_vol':0.01,'dca_vol':0.01,'max_dca':3},
  'XAGUSD': {'side':'SHORT','levels':[58.855,59.184,59.513],'base_sl':59.17,'base_tp':58.54,'base_vol':0.01,'dca_vol':0.01,'max_dca':3},
}

def init_ftmo():
    mt5.shutdown()
    time.sleep(1)
    ok = mt5.initialize(TERMINAL, login=LOGIN, password=PW, server=SERVER)
    if not ok:
        return False, mt5.last_error()
    acct = mt5.account_info()
    if not acct or acct.login != LOGIN:
        mt5.shutdown()
        return False, 'account_mismatch'
    return True, acct

def round_price(p, digits):
    return round(float(p), digits)

def place_order(symbol, side, price, sl, tp, volume):
    digits = mt5.symbol_info(symbol).digits if mt5.symbol_info(symbol) else 2
    price = round_price(price, digits)
    sl = round_price(sl, digits)
    tp = round_price(tp, digits)
    req = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': symbol,
        'volume': float(volume),
        'type': mt5.ORDER_TYPE_BUY if side == 'LONG' else mt5.ORDER_TYPE_SELL,
        'price': price,
        'sl': sl,
        'tp': tp,
        'deviation': 20,
        'magic': 20260804,
        'comment': 'dca_challenge_plan',
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    if res is None:
        return {'status':'error','error':'order_send_returned_none'}
    return {'status':'executed' if res.retcode == mt5.TRADE_RETCODE_DONE else 'failed', 'retcode': int(res.retcode), 'order': int(res.order), 'deal': int(res.deal), 'volume': volume, 'price': price, 'sl': sl, 'tp': tp}

def main():
    payload = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'ftmo':{}, 'dca':{}}
    ok, err = init_ftmo()
    payload['ftmo'] = {'init': bool(ok), 'error': str(err) if not ok else None}
    if not ok:
        OUT.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        print(json.dumps(payload, indent=2))
        return
    acct = mt5.account_info()
    payload['ftmo']['equity'] = float(acct.equity)
    positions = mt5.positions_get()
    pos_list = [dict(p._asdict()) for p in positions] if positions else []
    payload['ftmo']['positions'] = pos_list
    # Group positions by symbol
    sym_positions = {}
    for p in pos_list:
        sym = p['symbol']
        sym_positions.setdefault(sym, []).append(p)
    for sym, plan in DCA_PLAN.items():
        sym_data = sym_positions.get(sym, [])
        existing = [p for p in sym_data if p['type'] == (0 if plan['side']=='LONG' else 1)]
        total_vol = sum(float(p['volume']) for p in existing)
        dca_count = len(existing) - 1 if len(existing) > 0 else 0
        tick = mt5.symbol_info_tick(sym)
        digits = mt5.symbol_info(sym).digits if mt5.symbol_info(sym) else 2
        current = tick.bid if plan['side']=='LONG' else tick.ask if tick else None
        level_hit = None
        level_idx = None
        for i, lvl in enumerate(plan['levels']):
            if current is not None and ((plan['side']=='LONG' and current <= lvl) or (plan['side']=='SHORT' and current >= lvl)):
                level_hit = lvl
                level_idx = i
                break
        result = {
            'side': plan['side'],
            'current': current,
            'existing_volume': total_vol,
            'dca_count': dca_count,
            'max_dca': plan['max_dca'],
            'level_hit': level_hit,
            'level_index': level_idx,
            'base_sl': plan['base_sl'],
            'base_tp': plan['base_tp'],
            'actions': []
        }
        if level_hit is not None and dca_count < plan['max_dca'] and total_vol < plan['max_dca'] + 1:
            # Check if we already have an order at this level (by comment/price proximity)
            # For simplicity, place one DCA per level
            vol = plan['dca_vol']
            sl = plan['base_sl']
            tp = plan['base_tp']
            res = place_order(sym, plan['side'], level_hit, sl, tp, vol)
            result['actions'].append({'action':'dca_add','level':level_hit,'volume':vol,'result':res})
        payload['dca'][sym] = result
        time.sleep(0.5)
    mt5.shutdown()
    OUT.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print('WROTE', OUT)
    print(json.dumps(payload, indent=2))

if __name__ == '__main__':
    main()