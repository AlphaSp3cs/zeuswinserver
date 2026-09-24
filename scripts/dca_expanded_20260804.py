#!/usr/bin/env python3
"""
Expanded DCA builder for confirmed FTMO challenge trends.
Adds size at ATR-based levels below current price for EURJPY/GBPJPY longs.
Safe to run multiple times; idempotent.
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
OUT = BASE / 'artifacts' / f'dca_expanded_20260804T{datetime.now(timezone.utc).strftime("%H%M")}Z.json'
TRACKER = BASE / 'dca_tracked_trades.json'

# Confirmed trends with ATR-based DCA levels
DCA_PLAN = {
  'EURJPY': {
    'side': 'LONG',
    'base_entry': 180.473,
    'base_sl': 179.197,
    'base_tp': 182.506,
    'base_vol': 0.01,
    'dca_vol': 0.01,
    'max_dca': 5,
    'atr_mult': 0.5,  # half ATR between levels
  },
  'GBPJPY': {
    'side': 'LONG',
    'base_entry': 210.806,
    'base_sl': 209.114,
    'base_tp': 213.628,
    'base_vol': 0.01,
    'dca_vol': 0.01,
    'max_dca': 5,
    'atr_mult': 0.5,
  },
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

def get_atr(symbol, period=14, bars=50):
    rates = mt5.copy_rates_from_pos(symbol, mt5.TIMEFRAME_H1, 0, bars)
    if rates is None or len(rates) < period + 1:
        return None
    highs = [r['high'] for r in rates]
    lows = [r['low'] for r in rates]
    closes = [r['close'] for r in rates]
    trs = []
    for i in range(1, len(rates)):
        tr = max(highs[i]-lows[i], abs(highs[i]-closes[i-1]), abs(lows[i]-closes[i-1]))
        trs.append(tr)
    return sum(trs[-period:]) / period

def round_price(p, digits):
    return round(float(p), digits)

def place_limit_buy(symbol, price, sl, tp, volume):
    digits = mt5.symbol_info(symbol).digits if mt5.symbol_info(symbol) else 2
    price = round_price(price, digits)
    sl = round_price(sl, digits)
    tp = round_price(tp, digits)
    req = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': symbol,
        'volume': float(volume),
        'type': mt5.ORDER_TYPE_BUY,
        'price': price,
        'sl': sl,
        'tp': tp,
        'deviation': 20,
        'magic': 20260804,
        'comment': 'dca_expanded',
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    if res is None:
        return {'status':'error','error':'order_send_returned_none'}
    return {'status':'executed' if res.retcode == mt5.TRADE_RETCODE_DONE else 'failed', 'retcode': int(res.retcode), 'order': int(res.order), 'deal': int(res.deal), 'volume': volume, 'price': price, 'sl': sl, 'tp': tp}

def load_tracker():
    if TRACKER.exists():
        return json.loads(TRACKER.read_text(encoding='utf-8'))
    return []

def save_tracker(data):
    TRACKER.write_text(json.dumps(data, indent=2), encoding='utf-8')

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
    tracker = load_tracker()

    for sym, plan in DCA_PLAN.items():
        atr = get_atr(sym)
        if atr is None:
            payload['dca'][sym] = {'error': 'atr_unavailable'}
            continue

        digits = mt5.symbol_info(sym).digits if mt5.symbol_info(sym) else 2
        tick = mt5.symbol_info_tick(sym)
        current = tick.bid if plan['side'] == 'LONG' else tick.ask

        # Count existing positions for this symbol
        sym_pos = [p for p in pos_list if p['symbol'] == sym and p['type'] == (0 if plan['side']=='LONG' else 1)]
        total_vol = sum(float(p['volume']) for p in sym_pos)
        dca_count = max(0, len(sym_pos) - 1)  # exclude base position

        # Build DCA levels below current price
        levels = []
        for i in range(1, plan['max_dca'] + 1):
            lvl = round_price(plan['base_entry'] - i * plan['atr_mult'] * atr, digits)
            levels.append(lvl)

        # Find next level to add: lowest level below current that hasn't been filled
        next_level = None
        for lvl in levels:
            if current > lvl:  # price is above this level, so it could be hit
                # Check if we already have a position near this level
                already = any(abs(float(p['price_open']) - lvl) < atr * 0.25 for p in sym_pos)
                if not already:
                    next_level = lvl
                    break

        result = {
            'side': plan['side'],
            'current': current,
            'atr': round(atr, digits),
            'existing_volume': total_vol,
            'dca_count': dca_count,
            'max_dca': plan['max_dca'],
            'levels': levels,
            'next_level': next_level,
            'base_sl': plan['base_sl'],
            'base_tp': plan['base_tp'],
            'actions': []
        }

        if next_level is not None and dca_count < plan['max_dca']:
            # Place limit buy at next level
            res = place_limit_buy(sym, next_level, plan['base_sl'], plan['base_tp'], plan['dca_vol'])
            result['actions'].append({'action': 'dca_add', 'level': next_level, 'volume': plan['dca_vol'], 'result': res})
            if res.get('status') == 'executed':
                tracker.append({
                    'timestamp': datetime.now(timezone.utc).isoformat(),
                    'symbol': sym,
                    'side': plan['side'],
                    'ticket': res.get('order'),
                    'deal': res.get('deal'),
                    'price': next_level,
                    'volume': plan['dca_vol'],
                    'sl': plan['base_sl'],
                    'tp': plan['base_tp'],
                    'type': 'dca_expanded',
                    'status': 'open'
                })

        payload['dca'][sym] = result
        time.sleep(0.5)

    save_tracker(tracker)
    mt5.shutdown()
    OUT.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print('WROTE', OUT)
    print(json.dumps(payload, indent=2))

if __name__ == '__main__':
    main()