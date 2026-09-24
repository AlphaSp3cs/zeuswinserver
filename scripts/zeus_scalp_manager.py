#!/usr/bin/env python3
"""
zeus_scalp_manager.py
Active scalping profit manager for open zeus magic=20260727 positions.
- Trails stop into profit
- Breakeven trigger
- Partial close at R:R milestones
- Logs all actions
"""

import json
import sys
from datetime import datetime
from pathlib import Path

import MetaTrader5 as mt5

try:
    from mt5_connect import connect as _mt5_profile_connect, shutdown as _mt5_profile_shutdown
except Exception:  # pragma: no cover
    _mt5_profile_connect = None
    _mt5_profile_shutdown = None

MAGIC = 20260727
BASE_DIR = Path(__file__).resolve().parent
LOG_PATH = BASE_DIR / 'scalp_manager_log.json'
STATE_PATH = BASE_DIR / 'scalp_manager_state.json'
_PROFILE = 'ftmo'


def _connect():
    if _mt5_profile_connect is None:
        if not mt5.initialize():
            print(json.dumps({'error': 'mt5 init failed', 'last_error': mt5.last_error()}))
            sys.exit(1)
        return mt5
    return _mt5_profile_connect(_PROFILE)


def _shutdown(m):
    try:
        if _mt5_profile_shutdown is not None:
            _mt5_profile_shutdown()
        else:
            m.shutdown()
    except Exception:
        pass


def now_iso() -> str:
    return datetime.now().isoformat(timespec='seconds')


def load_state():
    if STATE_PATH.exists():
        try:
            return json.loads(STATE_PATH.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {}


def save_state(state):
    STATE_PATH.write_text(json.dumps(state, indent=2), encoding='utf-8')


def append_log(entry):
    entry['logged_at'] = now_iso()
    if LOG_PATH.exists():
        data = json.loads(LOG_PATH.read_text(encoding='utf-8'))
    else:
        data = {'started_at': now_iso(), 'entries': []}
    data['entries'].append(entry)
    LOG_PATH.write_text(json.dumps(data, indent=2), encoding='utf-8')
    print(f"[SCALP] {entry}")


def get_positions(m):
    positions = m.positions_get() or []
    out = []
    for p in positions:
        if getattr(p, 'magic', None) == MAGIC:
            out.append({
                'ticket': p.ticket,
                'symbol': p.symbol,
                'type': p.type,
                'volume': p.volume,
                'price_open': p.price_open,
                'sl': p.sl,
                'tp': p.tp,
                'profit': p.profit,
                'current_price': p.price_current,
            })
    return out


def trail_ticks(symbol, current_sl, current_price, trail_ticks_count, point):
    if current_sl is None or current_price is None or point is None or point <= 0:
        return None
    info = mt5.symbol_info(symbol)
    if info is None:
        return None
    stops_level = getattr(info, 'trade_stops_level', 0) or 0
    min_dist = max(stops_level * point, point)
    trail_dist = trail_ticks_count * point
    new_sl = round(current_price - trail_dist, info.digits)
    if new_sl >= current_price - min_dist:
        new_sl = round(current_price - min_dist, info.digits)
    if current_sl is not None and new_sl <= current_sl + min_dist:
        return None
    return new_sl


def trail_ticks_short(symbol, current_sl, current_price, trail_ticks_count, point):
    if current_sl is None or current_price is None or point is None or point <= 0:
        return None
    info = mt5.symbol_info(symbol)
    if info is None:
        return None
    stops_level = getattr(info, 'trade_stops_level', 0) or 0
    min_dist = max(stops_level * point, point)
    trail_dist = trail_ticks_count * point
    new_sl = round(current_price + trail_dist, info.digits)
    if new_sl <= current_price + min_dist:
        new_sl = round(current_price + min_dist, info.digits)
    if current_sl is not None and new_sl >= current_sl - min_dist:
        return None
    return new_sl


def modify_position(m, pos, new_sl=None, new_tp=None):
    req = {
        'action': mt5.TRADE_ACTION_SLTP,
        'symbol': pos['symbol'],
        'position': pos['ticket'],
        'sl': new_sl if new_sl is not None else pos['sl'],
        'tp': new_tp if new_tp is not None else pos['tp'],
    }
    r = m.order_send(req)
    return r


def partial_close(m, pos, fraction):
    vol = pos['volume']
    close_vol = round(vol * fraction, 2)
    if close_vol < 0.01:
        return None
    req = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': pos['symbol'],
        'type': mt5.ORDER_TYPE_SELL if pos['type'] == 0 else mt5.ORDER_TYPE_BUY,
        'position': pos['ticket'],
        'volume': close_vol,
        'deviation': 20,
        'magic': MAGIC,
        'comment': 'zeus-partial-close',
        'type_time': mt5.ORDER_TIME_GTC,
    }
    r = m.order_send(req)
    return r


def reached_milestone(pos, fraction, point):
    current_price = pos['current_price']
    open_price = pos['price_open']
    tp = pos['tp']
    if current_price is None or open_price is None or tp is None or point in (None, 0):
        return False
    risk = abs(open_price - pos['sl']) if pos['sl'] is not None else None
    if risk in (None, 0):
        return False
    reward = abs(tp - open_price)
    if reward == 0:
        return False
    moved = abs(current_price - open_price)
    return moved >= reward * fraction


def run_tick(state, m):
    positions = get_positions(m)
    for pos in positions:
        symbol = pos['symbol']
        info = mt5.symbol_info(symbol)
        if info is None:
            continue
        point = info.point
        current_price = pos['current_price']
        open_price = pos['price_open']
        profit = pos['profit']
        current_sl = pos['sl']
        ticket = pos['ticket']

        tstate = state.get(str(ticket), {})

        if pos['type'] == 0:
            # Long position: trail SL upward in profit
            move_sl = trail_ticks(symbol, current_sl, current_price, 25, point)
            if move_sl is not None and (current_sl is None or move_sl > current_sl):
                r = modify_position(m, pos, new_sl=move_sl)
                if r and r.retcode == 10009:
                    append_log({'ticket': ticket, 'symbol': symbol, 'action': 'trail_sl', 'new_sl': move_sl, 'profit': profit})
                    tstate['last_sl'] = move_sl
                    state[str(ticket)] = tstate

            # Breakeven after +40 ticks
            if not tstate.get('breakeven') and current_price > open_price + 40 * point:
                r = modify_position(m, pos, new_sl=open_price)
                if r and r.retcode == 10009:
                    append_log({'ticket': ticket, 'symbol': symbol, 'action': 'breakeven', 'sl': open_price, 'profit': profit})
                    tstate['breakeven'] = True
                    state[str(ticket)] = tstate

            # Partial close at 50% of TP distance
            if not tstate.get('partial1_closed') and reached_milestone(pos, 0.5, point):
                r = partial_close(m, pos, 0.5)
                if r and r.retcode == 10009:
                    append_log({'ticket': ticket, 'symbol': symbol, 'action': 'partial_close_50pct', 'profit': profit})
                    tstate['partial1_closed'] = True
                    state[str(ticket)] = tstate

        if pos['type'] == 1:
            # Short position: trail SL downward in profit
            move_sl = trail_ticks_short(symbol, current_sl, current_price, 25, point)
            if move_sl is not None and (current_sl is None or move_sl < current_sl):
                r = modify_position(m, pos, new_sl=move_sl)
                if r and r.retcode == 10009:
                    append_log({'ticket': ticket, 'symbol': symbol, 'action': 'trail_sl', 'new_sl': move_sl, 'profit': profit})
                    tstate['last_sl'] = move_sl
                    state[str(ticket)] = tstate

            # Breakeven after -40 ticks
            if not tstate.get('breakeven') and current_price < open_price - 40 * point:
                r = modify_position(m, pos, new_sl=open_price)
                if r and r.retcode == 10009:
                    append_log({'ticket': ticket, 'symbol': symbol, 'action': 'breakeven', 'sl': open_price, 'profit': profit})
                    tstate['breakeven'] = True
                    state[str(ticket)] = tstate

            # Partial close at 50% of TP distance
            if not tstate.get('partial1_closed') and reached_milestone(pos, 0.5, point):
                r = partial_close(m, pos, 0.5)
                if r and r.retcode == 10009:
                    append_log({'ticket': ticket, 'symbol': symbol, 'action': 'partial_close_50pct', 'profit': profit})
                    tstate['partial1_closed'] = True
                    state[str(ticket)] = tstate
    return positions


def main():
    print(json.dumps({'status': 'scalp_manager_running', 'magic': MAGIC}))
    m = _connect()
    try:
        state = load_state()
        positions = run_tick(state, m)
        print(json.dumps({'positions_tracked': len(positions), 'state_keys': list(state.keys())}))
        save_state(state)
    finally:
        _shutdown(m)


if __name__ == '__main__':
    main()
