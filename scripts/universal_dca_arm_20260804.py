#!/usr/bin/env python3
"""
Universal DCA autoreset arm pass: scan all open FTMO positions and ensure DCA/trail metadata is active.
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
TRACK_FILE = BASE / 'dca_tracked_trades.json'
OUT = BASE / 'artifacts' / f'universal_dca_arm_20260804T{datetime.now(timezone.utc).strftime("%H%M")}Z.json'

TRAIL_TO_BREAKEVEN_PCT = 0.02
DCA_TRIGGER_PCT = 0.03
DCA_VOLUME = 0.01
MAX_DCA_COUNT = 3

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

def load_tracked():
    if TRACK_FILE.exists():
        try:
            return json.loads(TRACK_FILE.read_text(encoding='utf-8'))
        except Exception:
            return []
    return []

def save_tracked(data):
    TRACK_FILE.write_text(json.dumps(data, indent=2), encoding='utf-8')

def arm_position(pos):
    ticket = int(pos.identifier)
    symbol = pos.symbol
    digits = mt5.symbol_info(symbol).digits if mt5.symbol_info(symbol) else 2
    entry = round_price(pos.price_open, digits)
    current = round_price(pos.price_current, digits)
    volume = float(pos.volume)
    favorable = current - entry if pos.type == 0 else entry - current
    adverse = entry - current if pos.type == 0 else current - entry
    trail_trigger = entry * TRAIL_TO_BREAKEVEN_PCT
    dca_trigger = entry * DCA_TRIGGER_PCT
    dca_count = 0
    # Parse dca count from comment if present
    comment = pos.comment or ''
    if 'dca_' in comment:
        try:
            dca_count = int(comment.split('dca_')[1].split('_')[0])
        except Exception:
            dca_count = 0
    actions = []
    # Breakeven trail: if favorable move exceeds threshold and SL not at entry, move SL to entry
    if abs(favorable) >= trail_trigger and (pos.sl is None or round_price(pos.sl, digits) != entry):
        req = {
            'action': mt5.TRADE_ACTION_SLTP,
            'position': ticket,
            'sl': entry,
            'tp': round_price(pos.tp, digits),
            'magic': 20260804,
            'comment': 'universal_trail_breakeven',
        }
        res = mt5.order_send(req)
        status = 'executed' if res and res.retcode == mt5.TRADE_RETCODE_DONE else 'failed'
        actions.append({'action':'trail_to_breakeven','ticket':ticket,'new_sl':entry,'status':status,'retcode': int(res.retcode) if res else None})
    # DCA autoreset: if adverse move exceeds threshold and count < max, add one lot
    if adverse >= dca_trigger and dca_count < MAX_DCA_COUNT:
        tick = mt5.symbol_info_tick(symbol)
        if tick and tick.bid > 0:
            price = round_price(tick.bid if pos.type == 1 else tick.ask, digits)
            req = {
                'action': mt5.TRADE_ACTION_DEAL,
                'symbol': symbol,
                'volume': float(DCA_VOLUME),
                'type': mt5.ORDER_TYPE_SELL if pos.type == 0 else mt5.ORDER_TYPE_BUY,
                'price': price,
                'sl': entry,
                'tp': round_price(pos.tp, digits),
                'deviation': 20,
                'magic': 20260804,
                'comment': f'dca_{dca_count+1}_universal',
                'type_time': mt5.ORDER_TIME_GTC,
                'type_filling': mt5.ORDER_FILLING_IOC,
            }
            res = mt5.order_send(req)
            status = 'executed' if res and res.retcode == mt5.TRADE_RETCODE_DONE else 'failed'
            actions.append({'action':'dca_reset','ticket':ticket,'added_volume':DCA_VOLUME,'status':status,'retcode': int(res.retcode) if res else None,'order': getattr(res,'order',None)})
    return {
        'ticket': ticket,
        'symbol': symbol,
        'entry': entry,
        'current': current,
        'volume': volume,
        'favorable_move': favorable,
        'adverse_move': adverse,
        'trail_trigger': trail_trigger,
        'dca_trigger': dca_trigger,
        'dca_count': dca_count,
        'actions': actions,
    }

def main():
    ok, err = init_ftmo()
    payload = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'ftmo_init': bool(ok), 'error': str(err) if not ok else None, 'positions': []}
    if not ok:
        OUT.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        print(json.dumps(payload, indent=2))
        return
    positions = mt5.positions_get()
    if not positions:
        mt5.shutdown()
        payload['positions_count'] = 0
        OUT.write_text(json.dumps(payload, indent=2), encoding='utf-8')
        print(json.dumps(payload, indent=2))
        return
    tracked = load_tracked()
    new_tracked = []
    for pos in positions:
        res = arm_position(pos)
        payload['positions'].append(res)
        new_tracked.append({
            'trade_id': int(pos.identifier),
            'symbol': pos.symbol,
            'entry': res['entry'],
            'sl': round_price(pos.sl, mt5.symbol_info(pos.symbol).digits if mt5.symbol_info(pos.symbol) else 2),
            'tp': round_price(pos.tp, mt5.symbol_info(pos.symbol).digits if mt5.symbol_info(pos.symbol) else 2),
            'volume': res['volume'],
            'broker': 'FTMO',
            'trail_to_breakeven_at_pct': TRAIL_TO_BREAKEVEN_PCT,
            'dca_reset_trigger_pct': DCA_TRIGGER_PCT,
            'dca_reset_volume': DCA_VOLUME,
            'dca_count': res['dca_count'],
            'status': 'tracking'
        })
        time.sleep(0.5)
    save_tracked(new_tracked)
    mt5.shutdown()
    payload['positions_count'] = len(payload['positions'])
    OUT.write_text(json.dumps(payload, indent=2), encoding='utf-8')
    print('WROTE', OUT)
    print(json.dumps(payload, indent=2))

if __name__ == '__main__':
    main()