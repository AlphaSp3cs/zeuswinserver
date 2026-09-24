#!/usr/bin/env python3
"""
Master Shift Scheduler — dispatches to nightshift, dayshift, or crypto weekend
based on ET time + weekday. Exact user-specified cycle:

  - Dayshift:       Mon-Fri 08:30-16:00 ET
  - Nightshift:     Sun 17:05 -> Fri 08:29 ET, plus Mon-Fri 16:00-23:59 ET
  - Crypto weekend: Fri 16:00 ET -> Sun 17:00 ET (overrides nightshift)

Priority: crypto_weekend > dayshift > nightshift
"""
import json, sys, os, datetime, warnings
from pathlib import Path

warnings.filterwarnings("ignore")

try:
    from winotify import Notification, audio
    HAS_WINOTIFY = True
except Exception:
    HAS_WINOTIFY = False
    import os as _os_dg
    if _os_dg.environ.get('OURO_DISABLE_TOAST','').strip().lower() in ('1','true','yes'):
        HAS_WINOTIFY = False  # bravo: toasts OFF, Telegram-only

BASE = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
SCRIPTS = BASE / 'scripts'
STATE_FILE = BASE / 'workflow' / 'master_shift_state.json'

def et_now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-4)))

def toast(title, msg, urgency='INFO'):
    if not HAS_WINOTIFY:
        return
    try:
        n = Notification(app_id="Zeus Shift Scheduler", title=title, msg=msg)
        if urgency == 'HIGH':
            n.set_audio(audio.Default, loop=False)
        n.show()
    except Exception:
        pass

def choose_mode(et):
    weekday = et.weekday()  # Mon=0 ... Sun=6

    # 1. Crypto weekend: Fri 16:00 -> Sun 17:00 ET
    if weekday == 4 and et.hour >= 16:
        return 'crypto_weekend'
    if weekday == 5:
        return 'crypto_weekend'
    if weekday == 6 and et.hour < 17:
        return 'crypto_weekend'

    # 2. Dayshift: Mon-Fri 08:30-15:59 ET
    if weekday < 5 and ((et.hour == 8 and et.minute >= 30) or (et.hour > 8 and et.hour < 16)):
        return 'dayshift'

    # 3. Nightshift:
    #    - Sun 17:05-23:59 ET
    #    - Mon-Fri 00:00-08:29 ET
    #    - Mon-Thu 16:00-23:59 ET
    #    - Fri 00:00-08:29 ET
    if weekday == 6 and (et.hour >= 17 and et.minute >= 5):
        return 'nightshift'
    if weekday < 5 and (et.hour < 8 or (et.hour == 8 and et.minute < 30)):
        return 'nightshift'
    if weekday < 4 and et.hour >= 16:  # Mon-Thu 16:00+
        return 'nightshift'
    if weekday == 4 and et.hour < 8:  # Fri 00:00-08:29
        return 'nightshift'

    return 'idle'

def dispatch(mode):
    import subprocess
    mapping = {
        'nightshift': SCRIPTS / 'unified_autopilot.py',
        'dayshift': SCRIPTS / 'unified_autopilot.py',
        'crypto_weekend': SCRIPTS / 'unified_autopilot.py',
    }
    target = mapping.get(mode)
    if not target or not target.exists():
        return {'mode': mode, 'status': 'MISSING_SCRIPT', 'path': str(target)}
    try:
        r = subprocess.run(
            [sys.executable, str(target)],
            capture_output=True, text=True, timeout=600
        )
        return {
            'mode': mode,
            'status': 'OK' if r.returncode == 0 else 'FAILED',
            'returncode': r.returncode,
            'stdout': r.stdout[-2000:],
            'stderr': r.stderr[-1000:],
        }
    except subprocess.TimeoutExpired:
        return {'mode': mode, 'status': 'TIMEOUT'}
    except Exception as e:
        return {'mode': mode, 'status': 'EXCEPTION', 'error': str(e)}

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {'last_mode': None, 'last_run': None, 'runs': {}}

def save_state(state, mode, result):
    state['last_mode'] = mode
    state['last_run'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    runs = state.get('runs', {})
    runs[mode] = {'last': state['last_run'], 'status': result.get('status')}
    state['runs'] = runs
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding='utf-8')

def main():
    et = et_now()
    mode = choose_mode(et)
    now = datetime.datetime.now(datetime.timezone.utc)
    print(f"[master] now_utc={now.isoformat()} now_et={et.strftime('%A %H:%M ET')} -> mode={mode}")
    if mode == 'idle':
        msg = f"Outside shift windows. Now {et.strftime('%H:%M ET')} {et.strftime('%A')}."
        print(f"[master] {msg}")
        toast('Shift IDLE', msg, 'INFO')
        return
    toast('Shift START', f"{mode} @ {et.strftime('%A %H:%M ET')}", 'HIGH')
    result = dispatch(mode)
    state = load_state()
    save_state(state, mode, result)
    status = result.get('status')
    summary = f"{mode} | {status}"
    print(f"[master] mode={mode} status={status}")
    if result.get('stdout'):
        print(result['stdout'][-800:])
    if result.get('stderr'):
        print(result['stderr'][-400:])
    toast('Shift ' + ('OK' if status == 'OK' else status.upper()), summary, 'HIGH' if status != 'OK' else 'INFO')

if __name__ == '__main__':
    main()
