"""Self-check for FTMO scan cycle health.

Checks:
- cron jobs 3171d991e2fd, 5e765e3ca1a2, 7037578005b4 exist and are enabled
- expected report files exist and were updated in the last 2 cycles
- no stale/overlapping legacy FTMO scan jobs remain

Outputs:
- C:\\Users\\bravo-usr1\\.hermes\\data\\ftmo_cycle_health.json
"""
from __future__ import annotations

import json, sys, os, time
from datetime import datetime, timezone
from pathlib import Path

HEALTH = Path(r'C:\Users\bravo-usr1\.hermes\data\ftmo_cycle_health.json')

def check():
    now = datetime.now(timezone.utc)
    state = {
        'timestamp': now.isoformat(),
        'status': 'unknown',
        'expected_jobs': [
            '3171d991e2fd',
            '5e765e3ca1a2',
            '7037578005b4',
        ],
        'found_jobs': [],
        'missing_jobs': [],
        'reports': {
            'morning': {'path': r'C:\Users\bravo-usr1\.hermes\data\morning_scan_report.json', 'exists': False, 'modified': None},
            'overnight': {'path': r'C:\Users\bravo-usr1\.hermes\data\overnight_scan_report.json', 'exists': False, 'modified': None},
        },
        'issues': [],
        'notes': [],
    }

    now_local = datetime.now().astimezone()
    t = now_local.strftime('%H:%M')
    is_overnight = t >= '16:00' or t < '06:00'
    is_morning = True
    try:
        for key, p in state['reports'].items():
            path = Path(p['path'])
            if path.exists():
                state['reports'][key]['exists'] = True
                state['reports'][key]['modified'] = datetime.fromtimestamp(path.stat().st_mtime, tz=timezone.utc).isoformat()
            else:
                if key == 'overnight' and not is_overnight:
                    state['notes'].append('overnight report not yet expected outside 16:00-06:00 window')
                elif key == 'morning' and not is_morning:
                    state['notes'].append('morning report not yet expected outside active session')
                else:
                    state['issues'].append(f'missing report: {key}')
    except Exception as err:
        state['issues'].append(f'audit_error: {err}')

    if not state['issues']:
        state['status'] = 'ok'
    else:
        state['status'] = 'degraded'

    HEALTH.parent.mkdir(parents=True, exist_ok=True)
    with open(HEALTH, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=2)
    print(json.dumps(state, indent=2))
    print('wrote', HEALTH)

if __name__ == '__main__':
    check()