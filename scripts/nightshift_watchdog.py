#!/usr/bin/env python3
"""
Nightshift Watchdog — self-healing monitor for the autopilot loop.
Runs every minute; if a cycle is overdue, it triggers an immediate run.
Also verifies the scheduled task itself is still enabled and configured.
"""
import json, os, sys, subprocess, time
from pathlib import Path
from datetime import datetime, timezone, timedelta

FIRM = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
AUTO_SCRIPT = FIRM / 'scripts' / 'nightshift_autopilot.py'
STATE_FILE = FIRM / 'workflow' / 'nightshift_state.json'
LOG_FILE = FIRM / 'workflow' / 'nightshift_log.jsonl'
WATCHDOG_LOG = FIRM / 'workflow' / 'nightshift_watchdog.jsonl'
PYTHON = r'C:\Users\bravo-usr1\AppData\Local\Microsoft\WindowsApps\python3.exe'
TASK_NAME = 'OuroTaurus_Nightshift'

CYCLE_SEC = 900
START_ET_HOUR = 18
CUTOFF_ET_HOUR = 8
CUTOFF_ET_MIN = 45
GRACE_SEC = 120  # 2 min grace before declaring a miss

try:
    from workflow.result_ready_toast import _toast as toast
except ImportError:
    def toast(title, msg, urgency='INFO'):
        pass

def now_utc():
    return datetime.now(timezone.utc)

def et_now():
    return now_utc().astimezone(timezone(timedelta(hours=-4)))

def in_window(et):
    return et.hour >= START_ET_HOUR or et.hour < CUTOFF_ET_HOUR or (et.hour == CUTOFF_ET_HOUR and et.minute < CUTOFF_ET_MIN)

def log_json(obj):
    obj['ts'] = now_utc().isoformat()
    with open(WATCHDOG_LOG, 'a', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')

def tail_lines(path, n=50):
    if not path.exists():
        return []
    try:
        with open(path, 'r', encoding='utf-8') as f:
            lines = f.readlines()
        return [l.strip() for l in lines[-n:] if l.strip()]
    except Exception:
        return []

def last_cycle_start():
    lines = tail_lines(LOG_FILE, n=100)
    for line in reversed(lines):
        try:
            obj = json.loads(line)
            if obj.get('event') == 'CYCLE_START':
                return datetime.fromisoformat(obj['ts'])
        except Exception:
            continue
    return None

def trigger_run():
    try:
        res = subprocess.run(
            [PYTHON, str(AUTO_SCRIPT)],
            capture_output=True, text=True, timeout=300,
            cwd=str(FIRM)
        )
        return {
            'returncode': res.returncode,
            'stdout': res.stdout[-500:] if res.stdout else '',
            'stderr': res.stderr[-500:] if res.stderr else '',
        }
    except Exception as e:
        return {'returncode': -1, 'stdout': '', 'stderr': str(e)}

def check_scheduled_task():
    try:
        out = subprocess.check_output(['schtasks', '/query', '/tn', TASK_NAME, '/fo', 'list', '/v'], text=True, timeout=10)
        if TASK_NAME not in out:
            return False, 'task missing'
        if 'Enabled' not in out:
            return False, 'task disabled'
        if '6:00:00 PM' not in out or '15 Minute(s)' not in out or '15 Hour(s)' not in out:
            return False, 'task schedule drift'
        return True, 'ok'
    except Exception as e:
        return False, str(e)

def main():
    now = now_utc()
    et = et_now()
    log_json({'event': 'WATCHDOG_START', 'now_utc': now.isoformat(), 'now_et': et.isoformat()})

    if not in_window(et):
        log_json({'event': 'WATCHDOG_IDLE', 'msg': 'outside window', 'et': et.strftime('%H:%M ET')})
        return

    # 1. Check scheduled task health
    task_ok, task_reason = check_scheduled_task()
    if not task_ok:
        log_json({'event': 'TASK_ANOMALY', 'reason': task_reason})
        toast('Nightshift WATCHDOG', f'Task anomaly: {task_reason}', 'HIGH')

    # 2. Check cycle freshness
    last_start = last_cycle_start()
    overdue = False
    if last_start is None:
        overdue = True
        reason = 'no_cycle_start_found'
    else:
        elapsed = (now - last_start).total_seconds()
        if elapsed > CYCLE_SEC + GRACE_SEC:
            overdue = True
            reason = f'overdue_by_{int(elapsed - CYCLE_SEC)}s'
        else:
            reason = f'ok_{int(elapsed)}s_since_last'

    log_json({'event': 'CYCLE_CHECK', 'last_start': last_start.isoformat() if last_start else None, 'reason': reason})

    if overdue:
        log_json({'event': 'MISSED_CYCLE', 'reason': reason})
        toast('Nightshift MISS', f'Auto-triggering missed cycle: {reason}', 'HIGH')
        run_result = trigger_run()
        log_json({'event': 'RECOVERY_RUN', 'reason': reason, 'result': run_result})
        toast('Nightshift RECOVER', f"Recovery run exit={run_result['returncode']}", 'HIGH')

    # 3. Light state sanity
    try:
        state = json.loads(STATE_FILE.read_text(encoding='utf-8')) if STATE_FILE.exists() else {}
        open_count = len(state.get('open', []))
        if open_count > 4:
            toast('Nightshift STATE', f'Open count {open_count} exceeds max 4', 'HIGH')
    except Exception:
        pass

if __name__ == '__main__':
    main()
