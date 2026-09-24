#!/usr/bin/env python3
"""
Unified Scan Pipeline
- Replaces duplicate scanners: weekend_crypto_scanner.py, fresh_all_sector_scan_*.py,
  nightshift_scan_exec_*.py, dayshift_autopilot.py, htf_conviction_scan.py, etc.
- Single entry point for all modes: crypto_weekend, dayshift, nightshift, htf
- Reads universe/data from canonical sources, writes to workflow/ with UTC timestamps
- Upgrade: carry-forward memory + dedupe + backtest-aware state
"""
import json, time, sqlite3, sys
from pathlib import Path
from datetime import datetime, timezone

BASE_FIRM = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
WORKFLOW = BASE_FIRM / 'workflow'
DB_PATH = WORKFLOW / 'crypto_data.db'
UNIVERSE_FILE = WORKFLOW / 'crypto_universe_20260809.json'
WHALE_FILE = WORKFLOW / 'whale_investor_tracker.json'
SCAN_STATE = WORKFLOW / 'scan_state_latest.json'
LOG_PATH = WORKFLOW / 'scan_pipeline_log.jsonl'

# Carry-forward memory upgrade
try:
    from scripts.carry_forward_memory import (
        load_scan_state,
        save_scan_state,
        dedupe_setups,
        mark_carried,
        load_trade_memory,
        save_trade_memory,
        setup_key,
    )
    MEMORY_ENABLED = True
except Exception:
    MEMORY_ENABLED = False

# Supported modes
MODES = ['crypto_weekend', 'dayshift', 'nightshift', 'htf']

def now_utc():
    return datetime.now(timezone.utc)

def uts(dt=None):
    return (dt or now_utc()).strftime('%Y%m%dT%H%MZ')

def log_event(mode, event, **fields):
    entry = {'ts': now_utc().isoformat(), 'mode': mode, 'event': event, **fields}
    with LOG_PATH.open('a', encoding='utf-8') as f:
        f.write(json.dumps(entry) + '\n')

def load_universe():
    if UNIVERSE_FILE.exists():
        return json.loads(UNIVERSE_FILE.read_text(encoding='utf-8'))
    return {'assets': [], 'sectors': {}}

def load_whale_tracker():
    if WHALE_FILE.exists():
        return json.loads(WHALE_FILE.read_text(encoding='utf-8'))
    return {'whales': {}, 'sentiment': {}}

def run_scan(mode: str):
    if mode not in MODES:
        raise ValueError(f'Unknown mode: {mode}. Valid: {MODES}')

    log_event(mode, 'SCAN_START')
    start = time.time()
    result = {
        'mode': mode,
        'ts': now_utc().isoformat(),
        'filename_ts': uts(),
        'status': 'pending',
        'assets_scanned': 0,
        'setups_found': 0,
        'errors': []
    }

    try:
        # Delegate to mode-specific logic
        if mode == 'crypto_weekend':
            try:
                from weekend_crypto_scanner import WeekendCryptoScanner
            except ImportError:
                from scripts.weekend_crypto_scanner import WeekendCryptoScanner
            scanner = WeekendCryptoScanner()
            scanner.run_cycle()
            data = {
                'assets_scanned': len(scanner.scan_results) if hasattr(scanner, 'scan_results') else 0,
                'setups_found': len(scanner.tickets_this_cycle),
                'signals': scanner.signals if hasattr(scanner, 'signals') else [],
            }
        elif mode == 'dayshift':
            try:
                from dayshift_autopilot import run_cycle
            except ImportError:
                from scripts.dayshift_autopilot import run_cycle
            data = run_cycle()
            data = {
                'assets_scanned': len(data.get('scanned', [])) if isinstance(data, dict) else 0,
                'setups_found': len(data.get('setups', data.get('tickets', []))) if isinstance(data, dict) else 0,
                'signals': data.get('signals', []) if isinstance(data, dict) else [],
            }
        elif mode == 'nightshift':
            try:
                from nightshift_autopilot import run_nightshift_scan
            except ImportError:
                from scripts.nightshift_autopilot import run_nightshift_scan
            data = run_nightshift_scan(WORKFLOW)
        elif mode == 'htf':
            try:
                from htf_conviction_scan import run_htf_scan
            except ImportError:
                from scripts.htf_conviction_scan import run_htf_scan
            data = run_htf_scan(WORKFLOW)
        else:
            data = {}

        result.update(data or {})
        result['status'] = 'ok'
        elapsed = time.time() - start
        result['elapsed_sec'] = round(elapsed, 2)
        log_event(mode, 'SCAN_END', status=result['status'], setups=result.get('setups_found', 0), elapsed=elapsed)
    except Exception as e:
        result['status'] = 'failed'
        result['errors'].append(str(e))
        log_event(mode, 'SCAN_ERROR', error=str(e))
        # Fallback: try legacy scanner if available
        try:
            try:
                from weekend_crypto_scanner import WeekendCryptoScanner
            except ImportError:
                from scripts.weekend_crypto_scanner import WeekendCryptoScanner
            scanner = WeekendCryptoScanner()
            scanner.run_cycle()
            data = {
                'assets_scanned': len(scanner.scan_results) if hasattr(scanner, 'scan_results') else 0,
                'setups_found': len(scanner.tickets_this_cycle),
                'signals': scanner.signals if hasattr(scanner, 'signals') else [],
            }
            result['status'] = 'ok_fallback'
            result.update(data or {})
            log_event(mode, 'FALLBACK_OK')
        except Exception:
            pass

    # Upgrade: carry-forward memory and dedupe
    try:
        if MEMORY_ENABLED and isinstance(result, dict):
            prev_state = load_scan_state()
            prior_keys = prev_state.get('carried_setups', []) + prev_state.get('duplicate_keys', [])
            signals = result.get('signals', [])
            if signals:
                unique_signals, new_keys = dedupe_setups(signals, prior_keys)
                result['signals'] = unique_signals
                result['setups_found'] = len(unique_signals)
                prev_state['duplicate_keys'] = list(dict.fromkeys(prior_keys + new_keys))
                mark_carried(prev_state, unique_signals)
                save_scan_state(prev_state)
    except Exception:
        pass

    # Update state
    try:
        SCAN_STATE.write_text(json.dumps(result, indent=2), encoding='utf-8')
    except Exception:
        pass
    return result

if __name__ == '__main__':
    mode = sys.argv[1] if len(sys.argv) > 1 else 'crypto_weekend'
    res = run_scan(mode)
    print(json.dumps(res, indent=2, default=str))
