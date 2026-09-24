#!/usr/bin/env python3
"""
Sonar scanner — runs every 30 min via Windows Task Scheduler.
Pre-market 09:00 ET: scan + draft limit orders.
09:30 ET: execute if market open and limits not filled.
"""
import os, sys, json, subprocess
from pathlib import Path
from datetime import datetime, timezone, timedelta

EASTERN = timezone(timedelta(hours=-4))  # EDT; adjust if EST
BASE = Path(__file__).resolve().parent
ENV = BASE / '.env'
ARTIFACTS = BASE / 'artifacts'
ARTIFACTS.mkdir(exist_ok=True)

def load_env():
    if not ENV.exists():
        return
    for line in ENV.read_text().splitlines():
        if '=' in line and not line.strip().startswith('#'):
            k, v = line.split('=', 1)
            os.environ.setdefault(k.strip(), v.strip())

def now_et():
    return datetime.now(EASTERN)

def is_pre_market():
    t = now_et()
    return t.hour == 9 and t.minute < 30  # 09:00–09:29 ET

def is_market_open():
    t = now_et()
    # Simplified: NYSE 09:30–16:00 ET Mon–Fri
    return t.weekday() < 5 and ((t.hour == 9 and t.minute >= 30) or (t.hour >= 10 and t.hour < 16))

def run_scan():
    """Run the all-sector scanner script and return the latest scan JSON path."""
    scan_script = BASE / '_tmp_all_sector_scan_exec.py'
    if not scan_script.exists():
        return None
    try:
        subprocess.run([sys.executable, str(scan_script)], cwd=str(BASE), check=True, capture_output=True, text=True)
        # Find latest scan file
        scans = sorted(BASE.glob('all_sector_scan_*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
        return scans[0] if scans else None
    except subprocess.CalledProcessError as e:
        return None

def draft_limit_orders(scan_path):
    if not scan_path or not scan_path.exists():
        return []
    try:
        data = json.loads(scan_path.read_text())
        candidates = data.get('top_candidates', [])[:15]
    except Exception:
        return []
    orders = []
    for c in candidates:
        if c.get('expectancy', -1) > 0 and c.get('win_rate', 0) >= 0.45 and c.get('rr', 0) >= 1.99:
            orders.append({
                'symbol': c['symbol'],
                'side': c['side'],
                'entry': c.get('entry'),
                'sl': c.get('sl'),
                'tp': c.get('tp'),
                'type': 'LIMIT',
                'status': 'drafted',
            })
    return orders

def execute_orders(scan_path):
    if not scan_path or not scan_path.exists():
        return []
    exec_script = BASE / '_exec_multi_broker_2026-08-03.py'
    if not exec_script.exists():
        return []
    try:
        subprocess.run([sys.executable, str(exec_script)], cwd=str(BASE), check=True, capture_output=True, text=True)
        arts = sorted(ARTIFACTS.glob('execution_multi_broker_*.json'), key=lambda p: p.stat().st_mtime, reverse=True)
        return [str(arts[0])] if arts else []
    except subprocess.CalledProcessError as e:
        return []

def check_xrp_swing_alert():
    try:
        import MetaTrader5 as mt5
        FTMO_TERMINAL = os.environ.get('FTMO_MT5_TERMINAL')
        FTMO_LOGIN = int(os.environ.get('FTMO_MT5_LOGIN', 0))
        FTMO_PW = os.environ.get('FTMO_MT5_PASSWORD')
        FTMO_SERVER = os.environ.get('FTMO_MT5_SERVER')
        mt5.shutdown()
        if not mt5.initialize(FTMO_TERMINAL, login=FTMO_LOGIN, password=FTMO_PW, server=FTMO_SERVER):
            return None
        si = mt5.symbol_info('XRPUSD')
        mt5.symbol_select('XRPUSD', True)
        tick = mt5.symbol_info_tick('XRPUSD')
        if not si or not tick or tick.bid <= 0:
            mt5.shutdown()
            return None
        price = float(tick.bid)
        mt5.shutdown()
        alerts = []
        if abs(price - 1.0775) < 0.0020:
            alerts.append('XRPUSD near 4H EMA50 resistance 1.0775 — watch for rejection/break')
        if abs(price - 1.0642) < 0.0020:
            alerts.append('XRPUSD near 20-bar low 1.0642 — watch for reversal confirmation')
        if abs(price - 1.0921) < 0.0030:
            alerts.append('XRPUSD near 4H 50-bar high 1.0921 — potential swing TP zone')
        return alerts
    except Exception:
        return None

def alert_telegram(message: str):
    bot_token = os.environ.get('HERMES_TELEGRAM_BOT_TOKEN')
    chat_id = os.environ.get('HERMES_TELEGRAM_USER_ID')
    if not bot_token or not chat_id:
        return
    try:
        import requests
        requests.post(f'https://api.telegram.org/bot{bot_token}/sendMessage', json={'chat_id': chat_id, 'text': message, 'parse_mode': 'Markdown'}, timeout=15)
    except Exception:
        pass

def main():
    load_env()
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%MZ')
    scan_path = run_scan()
    if scan_path:
        print(f'SCAN {scan_path.name}')
    else:
        print('SCAN_FAILED')

    report = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'scan_file': str(scan_path) if scan_path else None}
    mode = 'pre_market' if is_pre_market() else ('market_open' if is_market_open() else 'off_hours')
    report['mode'] = mode

    if mode == 'pre_market':
        limits = draft_limit_orders(scan_path)
        report['drafted_limits'] = limits
        print('DRAFTED', len(limits), 'limits')
        if limits:
            alert_telegram(f'Sonar pre-market: drafted {len(limits)} limit orders at 09:00 ET')
    elif mode == 'market_open':
        arts = execute_orders(scan_path)
        report['execution_artifacts'] = arts
        print('EXECUTED', len(arts), 'artifacts')
        if arts:
            alert_telegram(f'Sonar market-open: executed orders at 09:30 ET, artifacts: {arts}')
    else:
        report['note'] = 'off-hours; scan only'

    xrp_alerts = check_xrp_swing_alert()
    report['xrp_alerts'] = xrp_alerts
    if xrp_alerts:
        alert_telegram('XRPUSD swing alert: ' + ' | '.join(xrp_alerts))

    out = ARTIFACTS / f'sonar_scan_{ts}.json'
    out.write_text(json.dumps(report, indent=2), encoding='utf-8')
    print('WROTE', out)

if __name__ == '__main__':
    main()