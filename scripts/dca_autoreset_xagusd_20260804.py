#!/usr/bin/env python3
"""
DCA autoreset + breakeven trail monitor for FTMO LEFT XAGUSD override ticket.
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

# Target ticket from clean XAGUSD override
TICKET = 511198110
SYMBOL = 'XAGUSD'
DIGITS = 3

# Parameters
TRAIL_TO_BREAKEVEN_PCT = 0.02   # 2% favorable move -> SL -> entry
DCA_TRIGGER_PCT = 0.03          # 3% adverse move -> add 1 lot
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

def load_tracked():
    if TRACK_FILE.exists():
        try:
            return json.loads(TRACK_FILE.read_text(encoding='utf-8'))
        except Exception:
            return []
    return []

def save_tracked(data):
    TRACK_FILE.write_text(json.dumps(data, indent=2), encoding='utf-8')

def get_position(ticket):
    positions = mt5.positions_get(ticket=ticket)
    if positions:
        return positions[0]
    return None

def round_price(p, digits):
    return round(float(p), digits)

def modify_sl_tp(ticket, sl, tp, digits):
    req = {
        'action': mt5.TRADE_ACTION_SLTP,
        'position': int(ticket),
        'sl': round_price(sl, digits),
        'tp': round_price(tp, digits),
        'magic': 20260804,
        'comment': 'dca_trail_modify',
    }
    res = mt5.order_send(req)
    if res is None:
        return {'status':'error','reason':'order_send_none'}
    status = 'executed' if res.retcode == mt5.TRADE_RETCODE_DONE else 'failed'
    return {'status': status, 'reason': getattr(res,'comment',''), 'retcode': int(res.retcode)}

def place_sell(symbol, volume, sl, tp, digits, comment='dca_reset'):
    tick = mt5.symbol_info_tick(symbol)
    if not tick or tick.bid <= 0:
        return {'status':'error','reason':'no_tick'}
    price = round_price(tick.bid, digits)
    req = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': symbol,
        'volume': float(volume),
        'type': mt5.ORDER_TYPE_SELL,
        'price': price,
        'sl': round_price(sl, digits),
        'tp': round_price(tp, digits),
        'deviation': 20,
        'magic': 20260804,
        'comment': comment,
        'type_time': mt5.ORDER_TIME_GTC,
        'type_filling': mt5.ORDER_FILLING_IOC,
    }
    res = mt5.order_send(req)
    if res is None:
        return {'status':'error','reason':'order_send_none'}
    status = 'executed' if res.retcode == mt5.TRADE_RETCODE_DONE else 'failed'
    return {'status': status, 'reason': getattr(res,'comment',''), 'retcode': int(res.retcode), 'order': getattr(res,'order',None), 'deal': getattr(res,'deal',None), 'price': price}

def run_once():
    ok, err = init_ftmo()
    if not ok:
        print(json.dumps({'status':'error','reason':f'init_failed:{err}'}, indent=2))
        return
    pos = get_position(TICKET)
    if not pos:
        print(json.dumps({'status':'error','reason':'position_not_found','ticket':TICKET}, indent=2))
        mt5.shutdown()
        return
    entry = round_price(pos.price_open, DIGITS)
    sl = round_price(pos.sl, DIGITS)
    tp = round_price(pos.tp, DIGITS)
    current = round_price(pos.price_current, DIGITS)
    volume = float(pos.volume)
    # For SELL: favorable move = current < entry; adverse = current > entry
    favorable_move = entry - current
    adverse_move = current - entry
    trail_trigger = entry * TRAIL_TO_BREAKEVEN_PCT
    dca_trigger = entry * DCA_TRIGGER_PCT
    dca_count = int(pos.comment.split('dca_')[1].split('_')[0]) if 'dca_' in pos.comment else 0
    actions = []
    # Breakeven trail
    if not pos.sl or pos.sl != entry:
        if favorable_move >= trail_trigger:
            r = modify_sl_tp(TICKET, entry, tp, DIGITS)
            actions.append({'action':'trail_to_breakeven','ticket':TICKET,'new_sl':entry,'result':r})
    # DCA autoreset
    if dca_count < MAX_DCA_COUNT and adverse_move >= dca_trigger:
        # Place additional SELL
        place_res = place_sell(SYMBOL, DCA_VOLUME, entry, tp, DIGITS, comment=f'dca_{dca_count+1}_reset')
        actions.append({'action':'dca_reset','ticket':TICKET,'new_lot':DCA_VOLUME,'result':place_res})
    mt5.shutdown()
    payload = {
        'timestamp_utc': datetime.now(timezone.utc).isoformat(),
        'ticket': TICKET,
        'symbol': SYMBOL,
        'entry': entry,
        'current': current,
        'sl': sl,
        'tp': tp,
        'volume': volume,
        'favorable_move': favorable_move,
        'adverse_move': adverse_move,
        'trail_trigger': trail_trigger,
        'dca_trigger': dca_trigger,
        'dca_count': dca_count,
        'actions': actions,
        'status': 'ok'
    }
    # Update tracked trades
    tracked = load_tracked()
    updated = False
    for item in tracked:
        if isinstance(item, dict) and item.get('trade_id') == TICKET:
            item['last_check_utc'] = payload['timestamp_utc']
            item['trailed_to_breakeven'] = sl == entry
            item['dca_count'] = dca_count
            updated = True
            break
    if not updated:
        tracked.append({
            'trade_id': TICKET,
            'symbol': SYMBOL,
            'entry': entry,
            'sl': sl,
            'tp': tp,
            'volume': volume,
            'broker': 'FTMO',
            'trail_to_breakeven_at_pct': TRAIL_TO_BREAKEVEN_PCT,
            'dca_reset_trigger_pct': DCA_TRIGGER_PCT,
            'dca_reset_volume': DCA_VOLUME,
            'dca_count': dca_count,
            'status': 'tracking'
        })
    save_tracked(tracked)
    print(json.dumps(payload, indent=2))

if __name__ == '__main__':
    run_once()