#!/usr/bin/env python3
"""
practice_trades_etoro_demo.py
Place small practice demo trades on eToro based on master graded setups.
Uses existing verified endpoint: POST /api/v2/trading/execution/demo/orders
"""
import json, uuid, sys
from pathlib import Path
from datetime import datetime, timezone

import requests

BASE_FIRM = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
WORKFLOW = BASE_FIRM / 'workflow'
SYMBOL_MAP = WORKFLOW / 'etoro_symbol_map.json'
SCANDATA = Path(r'C:\Users\bravo-usr1\Desktop\scandata')

ETORO_BASE = 'https://public-api.etoro.com'
CREDS_PATH = BASE_FIRM / '.broker_creds_secure.json'
_creds = json.loads(CREDS_PATH.read_text(encoding='utf-8')) if CREDS_PATH.exists() else {}
ETORO_API_KEY = _creds.get('etoro', {}).get('api_key', '')
ETORO_USER_KEY = _creds.get('etoro', {}).get('user_key', '')

SETUPS = [
    {
        'symbol': 'ETH/USD',
        'side': 'buy',
        'composite_score': 66,
        'source': 'master_grader',
        'amount_usd': 100.0,
    },
    {
        'symbol': 'DOGEUSD',
        'side': 'buy',
        'composite_score': 66,
        'source': 'master_grader',
        'amount_usd': 100.0,
    },
]


def headers():
    return {
        'x-request-id': str(uuid.uuid4()),
        'x-api-key': ETORO_API_KEY,
        'x-user-key': ETORO_USER_KEY,
        'Accept': 'application/json',
    }


def load_symbol_map():
    if SYMBOL_MAP.exists():
        return json.loads(SYMBOL_MAP.read_text(encoding='utf-8'))
    return {}


def find_instrument_id(symbol: str, symbol_map: dict):
    norm = symbol.upper().replace('-USD', '').replace('USD', '').strip()
    for key in [norm, symbol.upper(), f'{norm}-USD']:
        info = symbol_map.get(key)
        if info:
            return info.get('id')
    return None


def place_demo_order(instrument_id, action, amount, leverage=1, stop_loss=None, take_profit=None):
    url = f'{ETORO_BASE}/api/v2/trading/execution/demo/orders'
    payload = {
        'action': 'open',
        'transaction': action.lower(),
        'instrumentID': int(instrument_id) if str(instrument_id).isdigit() else instrument_id,
        'orderType': 'mkt',
        'leverage': leverage,
        'amount': amount,
        'orderCurrency': 'usd',
    }
    if stop_loss:
        payload['stopLossRate'] = stop_loss
    if take_profit:
        payload['takeProfitRate'] = take_profit
    r = requests.post(url, headers=headers(), json=payload, timeout=15)
    return {
        'status_code': r.status_code,
        'response': r.text[:500],
        'url': url,
        'payload': payload,
    }


def main():
    dry_run = '--dryrun' in sys.argv
    if not ETORO_API_KEY or not ETORO_USER_KEY or '...' in ETORO_USER_KEY or len(ETORO_USER_KEY) < 100:
        print('SKIP: eToro credentials missing or truncated in .broker_creds_secure.json')
        out = {
            'ts': datetime.now(timezone.utc).isoformat(),
            'broker': 'etoro_demo',
            'dry_run': dry_run,
            'results': [{
                'symbol': setup['symbol'],
                'status': 'SKIP',
                'reason': 'missing or truncated eToro user_key in .broker_creds_secure.json',
                'setup': setup,
            } for setup in SETUPS],
        }
        SCANDATA.mkdir(parents=True, exist_ok=True)
        out_path = SCANDATA / f'practice_trades_etoro_demo_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")}.json'
        out_path.write_text(json.dumps(out, indent=2, default=str), encoding='utf-8')
        print(f'Wrote {out_path}')
        return

    symbol_map = load_symbol_map()
    print(f'Loaded eToro symbol map: {len(symbol_map)} entries')
    me = requests.get(f'{ETORO_BASE}/api/v1/me', headers=headers(), timeout=15)
    print(f'/api/v1/me status={me.status_code}')
    if me.status_code != 200:
        out = {
            'ts': datetime.now(timezone.utc).isoformat(),
            'broker': 'etoro_demo',
            'dry_run': dry_run,
            'auth_status': me.status_code,
            'auth_body': me.text[:300],
            'results': [{
                'symbol': setup['symbol'],
                'status': 'SKIP',
                'reason': f'eToro auth failed: HTTP {me.status_code}',
                'setup': setup,
            } for setup in SETUPS],
        }
        SCANDATA.mkdir(parents=True, exist_ok=True)
        out_path = SCANDATA / f'practice_trades_etoro_demo_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")}.json'
        out_path.write_text(json.dumps(out, indent=2, default=str), encoding='utf-8')
        print(f'Wrote {out_path}')
        return
    results = []
    for setup in SETUPS:
        sym = setup['symbol']
        instr_id = find_instrument_id(sym, symbol_map)
        if not instr_id:
            results.append({**setup, 'status': 'SKIP', 'reason': f'no instrument id for {sym}'})
            print(f"SKIP {sym}: no instrument id")
            continue
        res = place_demo_order(
            instrument_id=instr_id,
            action=setup['side'],
            amount=setup['amount_usd'],
            leverage=1,
        )
        status = 'PLACED' if res.get('status_code') == 200 else 'FAILED'
        out = {
            **setup,
            'status': status,
            'instrument_id': instr_id,
            'status_code': res.get('status_code'),
            'response': res.get('response'),
        }
        results.append(out)
        print(f"{'[DRYRUN] ' if dry_run else ''}{status} {sym} -> eToro ID {instr_id}: {res.get('status_code')}")
    out = {
        'ts': datetime.now(timezone.utc).isoformat(),
        'broker': 'etoro_demo',
        'dry_run': dry_run,
        'results': results,
    }
    out_path = SCANDATA / f'practice_trades_etoro_demo_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")}.json'
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding='utf-8')
    print(f'Wrote {out_path}')


if __name__ == '__main__':
    main()
