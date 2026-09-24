#!/usr/bin/env python3
"""
Nightshift Auto Status — reads autopilot state/log and pushes a Windows toast summary.
Scheduled separately from the main autopilot loop so it reports after each cycle.
"""
import json, sys
from pathlib import Path
from datetime import datetime, timezone, timedelta

BASE = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
sys.path.insert(0, str(BASE))
try:
    from workflow.result_ready_toast import _toast as toast
except ImportError:
    def toast(title, msg, urgency='INFO'):
        pass

STATE_FILE = BASE / 'workflow' / 'nightshift_state.json'
LOG_FILE = BASE / 'workflow' / 'nightshift_log.jsonl'

def load_json(path):
    if not path.exists():
        return None
    try:
        return json.loads(path.read_text(encoding='utf-8'))
    except Exception:
        return None

def tail_lines(path, n=20):
    if not path.exists():
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        return [l.strip() for l in lines[-n:] if l.strip()]
    except Exception:
        return []

def summarize():
    state = load_json(STATE_FILE) or {}
    lines = tail_lines(LOG_FILE, n=20)
    events = []
    for l in lines:
        try:
            events.append(json.loads(l))
        except Exception:
            pass

    cycles = state.get('cycles', 0)
    open_pos = state.get('open', [])
    brokers = state.get('broker_state', {})
    last_run = state.get('last_run', 'never')

    placed = sum(1 for e in events if e.get('event') == 'TICKET_PLACED')
    closed = sum(1 for e in events if e.get('event') == 'MAX_HOLD_CLOSE')
    failed = sum(1 for e in events if e.get('event') == 'TICKET_FAIL')
    outside = sum(1 for e in events if e.get('event') == 'OUTSIDE_WINDOW')

    if outside:
        status = 'IDLE'
        detail = 'Outside nightshift window.'
    elif failed and not placed:
        status = 'BLOCKED'
        detail = f'Broker/exec failures: {failed}'
    else:
        status = 'ACTIVE'
        detail = f'Placed={placed} Closed={closed} Failed={failed}'

    broker_names = ', '.join(brokers.keys()) if brokers else 'none'
    if open_pos:
        symbols = ', '.join(p.get('symbol', '?') for p in open_pos[:3])
        if len(open_pos) > 3:
            symbols += f' +{len(open_pos)-3} more'
        detail += f' Open={symbols}'

    title = f'Nightshift {status}'
    msg = f'Cycles={cycles} {detail} Brokers={broker_names} Last={last_run}'
    print(title)
    print(msg)
    try:
        toast(title, msg, urgency='HIGH' if status == 'BLOCKED' else 'INFO')
    except Exception:
        pass

if __name__ == '__main__':
    summarize()
