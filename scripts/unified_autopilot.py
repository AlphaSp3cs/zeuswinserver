#!/usr/bin/env python3
"""
Unified Autopilot
- Single entry point for all shifts: dayshift, nightshift, crypto_weekend
- Auto-detects active shift from ET time
- Runs unified scan pipeline
- Adds broker anticipation insights to signals
- Routes trades to best available broker
- Logs all signals, broker selections, and placements
"""
import json, time, sys, datetime, warnings, importlib.util
from pathlib import Path

warnings.filterwarnings("ignore")

BASE_FIRM = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
WORKFLOW = BASE_FIRM / 'workflow'
STATE_FILE = WORKFLOW / 'unified_autopilot_state.json'
LOG_FILE = WORKFLOW / 'unified_autopilot_log.jsonl'

# Shift windows in ET
SHIFT_WINDOWS = {
    'dayshift': {
        'days': [0, 1, 2, 3, 4],  # Mon-Fri
        'start': (8, 30),
        'end': (16, 0),
    },
    'nightshift': {
        'days': [0, 1, 2, 3, 4, 6],  # Mon-Fri + Sun
        'start': (16, 0),
        'end': (8, 30),
        'overnight': True,
        'extra_days': {6: (17, 5)},  # Sun 17:05+
    },
    'crypto_weekend': {
        'days': [4, 5, 6],  # Fri, Sat, Sun
        'start': (16, 0),
        'end': (17, 0),
        'sunday_cutoff': 17,
    }
}

# Broker routing rules by asset class
BROKER_ROUTING = {
    'crypto': {
        'primary': ['KRAKEN', 'ETORO', 'ALPACA'],
        'secondary': ['IBKR'],
        'fallback': ['FTMO_LEFT', 'CAPITAL_RIGHT'],
    },
    'equity': {
        'primary': ['ALPACA', 'IBKR'],
        'secondary': ['IBKR'],
        'fallback': ['FTMO_LEFT', 'CAPITAL_RIGHT'],
    },
    'etf': {
        'primary': ['ALPACA', 'IBKR'],
        'secondary': ['IBKR'],
        'fallback': ['FTMO_LEFT', 'CAPITAL_RIGHT'],
    },
    'forex': {
        'primary': ['FTMO_LEFT', 'CAPITAL_RIGHT'],
        'secondary': ['IBKR'],
        'fallback': [],
    },
    'commodity': {
        'primary': ['FTMO_LEFT', 'CAPITAL_RIGHT'],
        'secondary': ['IBKR'],
        'fallback': [],
    },
    'index': {
        'primary': ['FTMO_LEFT', 'CAPITAL_RIGHT'],
        'secondary': ['IBKR'],
        'fallback': [],
    },
    'options': {
        'primary': ['IBKR'],
        'secondary': ['ALPACA'],
        'fallback': [],
    },
    'futures': {
        'primary': ['IBKR'],
        'secondary': [],
        'fallback': [],
    },
}

def et_now():
    return datetime.datetime.now(datetime.timezone(datetime.timedelta(hours=-4)))

def in_window(et, shift_name):
    window = SHIFT_WINDOWS.get(shift_name)
    if not window:
        return False
    weekday = et.weekday()
    hour, minute = et.hour, et.minute
    current_minutes = hour * 60 + minute

    if shift_name == 'crypto_weekend':
        if weekday == 4 and current_minutes >= 16 * 60:
            return True
        if weekday == 5:
            return True
        if weekday == 6 and current_minutes < 17 * 60:
            return True
        return False

    if shift_name == 'dayshift':
        if weekday not in window['days']:
            return False
        start_minutes = window['start'][0] * 60 + window['start'][1]
        end_minutes = window['end'][0] * 60 + window['end'][1]
        return start_minutes <= current_minutes < end_minutes

    if shift_name == 'nightshift':
        if weekday in window['extra_days']:
            eh, em = window['extra_days'][weekday]
            if current_minutes >= eh * 60 + em:
                return True
        if weekday not in window['days']:
            return False
        start_minutes = window['start'][0] * 60 + window['start'][1]
        end_minutes = window['end'][0] * 60 + window['end'][1]
        if window.get('overnight'):
            return current_minutes >= start_minutes or current_minutes < end_minutes
        return start_minutes <= current_minutes < end_minutes

    return False

def choose_shift(et):
    # Priority: crypto_weekend > dayshift > nightshift
    if in_window(et, 'crypto_weekend'):
        return 'crypto_weekend'
    if in_window(et, 'dayshift'):
        return 'dayshift'
    if in_window(et, 'nightshift'):
        return 'nightshift'
    return 'idle'

def anticipate_broker(signal):
    """Add broker anticipation insights to signals based on asset class."""
    asset_type = signal.get('asset_type', 'CRYPTO').lower()
    symbol = signal.get('symbol', '')

    # Determine asset class
    if asset_type == 'crypto' or '-USD' in symbol.upper() or 'USD' in symbol.upper():
        asset_class = 'crypto'
    elif any(x in symbol.upper() for x in ['SPY', 'QQQ', 'IWM', 'DIA', 'XLK', 'XLF', 'XLE', 'XLV', 'XLY', 'XLI', 'XLU', 'XLP', 'XLRE', 'XLB', 'GLD', 'SLV', 'TLT', 'IEF', 'AGG', 'HYG', 'USO', 'DBA', 'UNG', 'KRE', 'XRT', 'SMH', 'ARKK']):
        asset_class = 'etf'
    elif any(x in symbol.upper() for x in ['ES=F', 'NQ=F', 'YM=F', 'RTY=F', 'ZN=F', 'ZF=F', 'ZT=F']):
        asset_class = 'futures'
    elif any(x in symbol.upper() for x in ['^TNX']):
        asset_class = 'index'
    elif any(x in symbol.upper() for x in ['EURUSD', 'GBPUSD', 'USDJPY', 'AUDUSD', 'USDCAD', 'USDCHF', 'NZDUSD']):
        asset_class = 'forex'
    elif any(x in symbol.upper() for x in ['GC=F', 'SI=F', 'HG=F', 'PL=F', 'PA=F', 'CL=F', 'NG=F', 'BZ=F', 'ZC=F', 'ZS=F', 'ZW=F', 'KC=F']):
        asset_class = 'commodity'
    else:
        asset_class = 'equity'

    routing = BROKER_ROUTING.get(asset_class, {'primary': ['IBKR'], 'secondary': [], 'fallback': []})
    signal['asset_class'] = asset_class
    signal['anticipated_broker_primary'] = routing['primary'][0] if routing['primary'] else None
    signal['anticipated_broker_secondary'] = routing['secondary'][0] if routing['secondary'] else None
    signal['anticipated_broker_fallback'] = routing['fallback'][0] if routing['fallback'] else None
    signal['broker_routing_insight'] = f"{asset_class} -> primary={routing['primary'][0] if routing['primary'] else 'N/A'}, secondary={routing['secondary'][0] if routing['secondary'] else 'N/A'}"
    return signal

def load_unified_pipeline():
    """Load unified scan pipeline module."""
    spec = importlib.util.spec_from_file_location('scan_pipeline', str(BASE_FIRM / 'scripts' / 'scan_pipeline.py'))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod

def run_shift(shift_name):
    """Run the appropriate scanner for the shift and add broker insights."""
    print(f"[unified] Running shift: {shift_name}")
    log_json({'event': 'SHIFT_START', 'shift': shift_name})

    # Dispatch scanner via subprocess; capture results
    try:
        import subprocess
        scanner_map = {
            'crypto_weekend': BASE_FIRM / 'scripts' / 'weekend_crypto_scanner.py',
            'dayshift': BASE_FIRM / 'scripts' / 'dayshift_autopilot.py',
            'nightshift': BASE_FIRM / 'scripts' / 'nightshift_autopilot.py',
        }
        scanner_path = scanner_map.get(shift_name)
        if not scanner_path or not scanner_path.exists():
            log_json({'event': 'SHIFT_ERROR', 'shift': shift_name, 'error': 'missing scanner'})
            return {'status': 'MISSING_SCANNER', 'signals': []}
        r = subprocess.run([sys.executable, str(scanner_path)], capture_output=True, text=True, timeout=600)
        status = 'OK' if r.returncode == 0 else 'FAILED'
        stdout = r.stdout[-4000:] if r.stdout else ''
        stderr = r.stderr[-1000:] if r.stderr else ''
        log_json({'event': 'SHIFT_SCAN_COMPLETE', 'shift': shift_name, 'status': status, 'stdout': stdout, 'stderr': stderr})
        return {'status': status, 'signals': [], 'scan_result': {'stdout': stdout, 'stderr': stderr}}
    except subprocess.TimeoutExpired:
        log_json({'event': 'SHIFT_TIMEOUT', 'shift': shift_name})
        return {'status': 'TIMEOUT', 'signals': []}
    except Exception as e:
        log_json({'event': 'SHIFT_ERROR', 'shift': shift_name, 'error': str(e)})
        return {'status': 'EXCEPTION', 'error': str(e), 'signals': []}

def log_json(obj):
    obj['ts'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    with LOG_FILE.open('a', encoding='utf-8') as f:
        f.write(json.dumps(obj, ensure_ascii=False) + '\n')

def save_state(state, shift, result):
    state['last_shift'] = shift
    state['last_run'] = datetime.datetime.now(datetime.timezone.utc).isoformat()
    state['last_status'] = result.get('status')
    runs = state.get('runs', {})
    runs[shift] = {
        'last': state['last_run'],
        'status': result.get('status'),
        'signals': len(result.get('signals', [])),
    }
    state['runs'] = runs
    STATE_FILE.write_text(json.dumps(state, indent=2), encoding='utf-8')

def load_state():
    if STATE_FILE.exists():
        try:
            return json.loads(STATE_FILE.read_text(encoding='utf-8'))
        except Exception:
            pass
    return {'last_shift': None, 'last_run': None, 'runs': {}}

def main():
    et = et_now()
    shift = choose_shift(et)
    print(f"[unified] now_utc={datetime.datetime.now(datetime.timezone.utc).isoformat()} now_et={et.strftime('%A %H:%M ET')} -> shift={shift}")

    state = load_state()

    if shift == 'idle':
        msg = f"Outside shift windows. Now {et.strftime('%H:%M ET')} {et.strftime('%A')}."
        print(f"[unified] {msg}")
        log_json({'event': 'IDLE', 'msg': msg})
        return

    log_json({'event': 'SHIFT_DISPATCH', 'shift': shift})
    result = run_shift(shift)
    save_state(state, shift, result)

    status = result.get('status', 'unknown')
    summary = f"{shift} | {status} | signals={len(result.get('signals', []))}"
    print(f"[unified] {summary}")

    # Show broker anticipation for top signals
    signals = result.get('signals', [])
    if signals:
        print("\nTop signals with broker anticipation:")
        for sig in sorted(signals, key=lambda x: x.get('score') or 0, reverse=True)[:5]:
            print(f"  {sig.get('symbol')} | {sig.get('direction')} | score={sig.get('score')} | {sig.get('broker_routing_insight')}")

if __name__ == '__main__':
    main()
