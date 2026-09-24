#!/usr/bin/env python3
"""
weekend_crypto_executor.py
- Reads READY tickets from weekend scanner DB/ticket file
- Executes crypto tickets on broker with direction-aware routing:
  LONG -> Kraken spot / MT5 longs
  SHORT -> Capital_RIGHT MT5 or Kraken API short if enabled
- Enforces 1% max ticket size and capital-aware sizing
- Writes execution report JSON
"""
import json, sqlite3, sys, os
from pathlib import Path
from datetime import datetime, timezone

BASE = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
DB_PATH = BASE / 'workflow' / 'crypto_data.db'
TICKET_FILE = BASE / 'workflow' / 'dca_execution_auto_tickets_20260808.md'
REPORT_DIR = BASE / 'workflow'
BROKER_CREDS = BASE / 'broker_creds.json'

# Fallback: load broker creds from .env if broker_creds.json missing
creds = {}
if BROKER_CREDS.exists():
    try:
        creds = json.loads(BROKER_CREDS.read_text(encoding='utf-8'))
    except Exception:
        creds = {}
if not creds:
    env_path = BASE / '.env'
    if env_path.exists():
        for line in env_path.read_text(encoding='utf-8').splitlines():
            if '=' in line and not line.strip().startswith('#'):
                k, v = line.split('=', 1)
                creds[k.strip().lower()] = v.strip()
    if 'ftmo_mt5_terminal' in creds:
        creds.setdefault('ftmo', {})['path'] = creds.pop('ftmo_mt5_terminal')
    if 'ftmo_mt5_login' in creds:
        creds.setdefault('ftmo', {})['login'] = int(creds.pop('ftmo_mt5_login'))
    if 'ftmo_mt5_password' in creds:
        creds.setdefault('ftmo', {})['password'] = creds.pop('ftmo_mt5_password')
    if 'ftmo_mt5_server' in creds:
        creds.setdefault('ftmo', {})['server'] = creds.pop('ftmo_mt5_server')
    if 'capital_mt5_terminal' in creds:
        creds.setdefault('capital', {})['path'] = creds.pop('capital_mt5_terminal')
    if 'capital_mt5_login' in creds:
        creds.setdefault('capital', {})['login'] = int(creds.pop('capital_mt5_login'))
    if 'capital_mt5_password' in creds:
        creds.setdefault('capital', {})['password'] = creds.pop('capital_mt5_password')
    if 'capital_mt5_server' in creds:
        creds.setdefault('capital', {})['server'] = creds.pop('capital_mt5_server')

try:
    import MetaTrader5 as mt5
    HAS_MT5 = True
except ImportError:
    HAS_MT5 = False

try:
    from winotify import Notification, audio
    HAS_WINOTIFY = True
except ImportError:
    HAS_WINOTIFY = False

# bravo: toasts OFF (Telegram-only law)
import os as _os_dg
if _os_dg.environ.get('OURO_DISABLE_TOAST','').strip().lower() in ('1','true','yes'):
    class _NoToast:
        def __getattr__(self,n): return lambda *a,**k: None
    Notification = _NoToast()
    def _disabled_audio(*a,**k): pass
    audio = type('A',(),{'Default':staticmethod(_disabled_audio),'Reminder':staticmethod(_disabled_audio)})()

def now_iso():
    return datetime.now(timezone.utc).isoformat()

def _send_execution_toast(broker, direction, symbol, size, result):
    if not HAS_WINOTIFY:
        return
    try:
        title = f"WEEKEND CRYPTO EXECUTION: {symbol}"
        if isinstance(result, dict):
            status = result.get('status', 'unknown')
            retcode = result.get('retcode', '')
            price = result.get('price', 0)
            sl = result.get('sl', 0)
            tp = result.get('tp', 0)
            comment = result.get('comment', '')
            msg = (
                f"Broker: {broker} | Dir: {direction}\n"
                f"Size: {size} | Status: {status}\n"
                f"Price: {price} | SL: {sl} | TP: {tp}\n"
                f"Retcode: {retcode} | Comment: {comment}"
            )
        else:
            msg = f"Broker: {broker} | Dir: {direction}\nSize: {size}\nResult: {result}"
        toast = Notification(app_id="Zeus Crypto Weekend Execution", title=title, msg=msg)
        toast.set_audio(audio.Mail, loop=False)
        toast.show()
    except Exception:
        pass

def _send_execution_summary(results):
    if not HAS_WINOTIFY:
        return
    try:
        executed = [r for r in results if isinstance(r.get('result'), dict) and r['result'].get('status') == 'executed']
        failed = [r for r in results if isinstance(r.get('result'), dict) and r['result'].get('status') == 'failed']
        blocked = [r for r in results if isinstance(r.get('result'), dict) and r['result'].get('status') == 'blocked']
        payload_only = [r for r in results if isinstance(r.get('result'), dict) and r['result'].get('status') == 'payload_only']

        title = f"Weekend Crypto Execution: {len(executed)} placed"
        parts = [f"Executed: {len(executed)}", f"Failed: {len(failed)}", f"Blocked: {len(blocked)}", f"Payload only: {len(payload_only)}"]
        msg = '\n'.join(parts)
        toast = Notification(app_id="Zeus Crypto Weekend Execution", title=title, msg=msg)
        toast.set_audio(audio.Mail, loop=False)
        toast.show()
    except Exception:
        pass

def load_tickets():
    tickets = []
    try:
        if DB_PATH.exists():
            conn = sqlite3.connect(str(DB_PATH))
            conn.row_factory = sqlite3.Row
            cur = conn.cursor()
            cur.execute("SELECT * FROM dca_tickets WHERE status='READY' ORDER BY created_at DESC")
            tickets = [dict(r) for r in cur.fetchall()]
            conn.close()
    except Exception:
        tickets = []
    if not tickets and TICKET_FILE.exists():
        text = TICKET_FILE.read_text(encoding='utf-8')
        for line in text.splitlines():
            if line.startswith('| CRYPTO-'):
                parts = [p.strip() for p in line.strip('|').split('|')]
                if len(parts) >= 11:
                    tickets.append({
                        'ticket_id': parts[0],
                        'symbol': parts[1],
                        'asset_type': parts[2],
                        'broker': parts[3],
                        'entry': float(parts[4]) if parts[4] else 0,
                        'sl': float(parts[5]) if parts[5] else 0,
                        'tp1': float(parts[6]) if parts[6] else 0,
                        'tp2': float(parts[7]) if parts[7] else 0,
                        'size': float(parts[8]) if parts[8] else 0,
                        'urgency': parts[9],
                        'status': parts[10],
                        'direction': 'LONG',
                        'grade': None,
                        'score': None,
                    })
    return tickets

def mt5_init(terminal, login, password, server):
    if not HAS_MT5:
        return None
    try:
        mt5.shutdown()
    except Exception:
        pass
    ok = mt5.initialize(terminal, login=int(login), password=password, server=server)
    if not ok:
        return None
    acc = mt5.account_info()
    if acc is None:
        return None
    return {'acc': acc, 'equity': float(acc.equity), 'login': int(acc.login)}

def send_mt5(state, symbol, direction, volume, entry, sl, tp, comment='WEEKEND_CRYPTO'):
    if state is None:
        return None
    info = mt5.symbol_info(symbol)
    if info is None:
        return {'status': 'blocked', 'reason': 'no_symbol_info', 'symbol': symbol}
    mt5.symbol_select(symbol, True)
    tick = mt5.symbol_info_tick(symbol)
    if tick is None or (direction == 'LONG' and tick.ask <= 0) or (direction == 'SHORT' and tick.bid <= 0):
        return {'status': 'blocked', 'reason': 'no_quote', 'symbol': symbol}
    price = round(float(tick.ask), info.digits) if direction == 'LONG' else round(float(tick.bid), info.digits)
    otype = mt5.ORDER_TYPE_BUY if direction == 'LONG' else mt5.ORDER_TYPE_SELL
    req = {
        'action': mt5.TRADE_ACTION_DEAL,
        'symbol': symbol,
        'volume': float(volume),
        'type': otype,
        'price': price,
        'sl': float(sl),
        'tp': float(tp),
        'deviation': 20,
        'magic': 20260814,
        'comment': comment,
        'type_time': mt5.ORDER_TIME_GTC,
    }
    res = mt5.order_send(req)
    return {
        'status': 'executed' if int(getattr(res, 'retcode', -1)) == 10009 else 'failed',
        'retcode': int(getattr(res, 'retcode', -1)),
        'order': int(getattr(res, 'order', 0) or 0),
        'deal': int(getattr(res, 'deal', 0) or 0),
        'price': price,
        'volume': float(volume),
        'sl': float(sl),
        'tp': float(tp),
        'symbol': symbol,
        'direction': direction,
        'comment': getattr(res, 'comment', ''),
    }

def main():
    tickets = load_tickets()
    if not tickets:
        print('No READY tickets found')
        return

    cap_state = None
    ftmo_state = None
    if HAS_MT5:
        cap = creds.get('capital', {})
        cap_state = mt5_init(cap.get('path'), cap.get('login'), cap.get('password'), cap.get('server'))
        if cap_state:
            print(f"CAPITAL_RIGHT init ok equity={cap_state['equity']}")
        else:
            print('CAPITAL_RIGHT init failed')
        ft = creds.get('ftmo', {})
        ftmo_state = mt5_init(ft.get('path'), ft.get('login'), ft.get('password'), ft.get('server'))
        if ftmo_state:
            print(f"FTMO_LEFT init ok equity={ftmo_state['equity']}")
        else:
            print('FTMO_LEFT init failed')

    results = []
    skipped_low_conviction = 0
    for t in tickets:
        broker = t.get('broker', 'KRAKEN')
        symbol = t.get('symbol', '')
        direction = t.get('direction', 'LONG')
        size = float(t.get('size', 0) or 0)
        entry = float(t.get('entry', 0) or 0)
        sl = float(t.get('sl', 0) or 0)
        tp1 = float(t.get('tp1', 0) or 0)
        tp2 = float(t.get('tp2', 0) or 0)
        mt5_sym = f"{symbol}USD"

        # High-conviction gating: only execute when multiple criteria align
        grade = (t.get('grade') or '').upper()
        urgency = (t.get('urgency') or '').upper()
        score = t.get('score')
        has_grade = grade in ('ACCUMULATE', 'A+')
        has_urgency = urgency == 'HIGH'
        has_score = isinstance(score, (int, float)) and score >= 7
        has_mid_score = isinstance(score, (int, float)) and score >= 5
        # Require at least 2 of 3 signals, or a top-tier single signal
        confidence_signals = sum([bool(has_grade), bool(has_urgency), bool(has_score)])
        is_high_conviction = (
            has_grade
            or has_score
            or (has_urgency and has_mid_score and confidence_signals >= 2)
        )
        # Legacy tickets without grade/score metadata default to skip
        if not grade and score is None:
            is_high_conviction = False
        if not is_high_conviction:
            skipped_low_conviction += 1
            print(f"SKIP {broker} {direction} {mt5_sym} reason=low_conviction grade={grade or 'None'} urgency={urgency} score={score}")
            results.append({
                'ticket_id': t.get('ticket_id'),
                'symbol': mt5_sym,
                'direction': direction,
                'broker': broker,
                'entry': entry,
                'sl': sl,
                'tp1': tp1,
                'tp2': tp2,
                'requested_size': size,
                'executed_size': 0,
                'result': {'status': 'skipped', 'reason': 'low_conviction'},
            })
            continue

        # enforce 1% size cap per broker equity
        state = None
        if broker == 'CAPITAL_RIGHT':
            state = cap_state
        elif broker == 'FTMO_LEFT':
            state = ftmo_state
        if state:
            max_size = state['equity'] * 0.01
            if size > max_size:
                size = max_size

        res = None
        if broker in ('CAPITAL_RIGHT', 'FTMO_LEFT') and state:
            tp = tp2 if tp2 > 0 else tp1
            res = send_mt5(state, mt5_sym, direction, size, entry, sl, tp, comment='WEEKEND_CRYPTO')
        else:
            res = {
                'status': 'payload_only',
                'reason': 'api_key_missing_or_broker_unsupported',
                'symbol': mt5_sym,
                'direction': direction,
                'entry': entry,
                'sl': sl,
                'tp1': tp1,
                'tp2': tp2,
                'volume': size,
            }

        results.append({
            'ticket_id': t.get('ticket_id'),
            'symbol': mt5_sym,
            'direction': direction,
            'broker': broker,
            'entry': entry,
            'sl': sl,
            'tp1': tp1,
            'tp2': tp2,
            'requested_size': float(t.get('size', 0) or 0),
            'executed_size': size if res and res.get('status') == 'executed' else 0,
            'result': res,
        })
        print(f"{broker} {direction} {mt5_sym} size={size} -> {res.get('status') if isinstance(res, dict) else res} retcode={res.get('retcode') if isinstance(res, dict) else ''}")
        _send_execution_toast(broker, direction, mt5_sym, size, res)

    out = REPORT_DIR / f'weekend_crypto_execution_{datetime.now(timezone.utc).strftime("%Y-%m-%dT%H%M%SZ")}.json'
    out.write_text(json.dumps({'timestamp_utc': now_iso(), 'results': results, 'skipped_low_conviction': skipped_low_conviction}, indent=2), encoding='utf-8')
    print('WROTE', out)
    _send_execution_summary(results)
    if skipped_low_conviction:
        print(f'SKIPPED {skipped_low_conviction} low-conviction ticket(s)')

    if HAS_MT5:
        try:
            mt5.shutdown()
        except Exception:
            pass

if __name__ == '__main__':
    main()
