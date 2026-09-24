#!/usr/bin/env python3
"""Credential health gate for Pack broker profiles."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
from load_broker_creds import health_check, get

REQUIRED_BROKERS = ['capital', 'alpaca', 'etoro', 'ibkr', 'kraken']
GATE_RESULTS_PATH = Path(__file__).resolve().parent.parent / 'scandata' / 'credential_health_gate.json'
VERIFICATION_RESULTS_PATH = Path(__file__).resolve().parent.parent / 'scandata' / 'broker_verification_results.json'


def _load_verification_results() -> dict:
    if VERIFICATION_RESULTS_PATH.exists():
        try:
            return json.loads(VERIFICATION_RESULTS_PATH.read_text(encoding='utf-8')).get('results', {})
        except Exception:
            return {}
    return {}


def run_gate():
    verify_results = _load_verification_results()
    results = {}
    blocked = []
    for name in REQUIRED_BROKERS:
        result = health_check(name)
        broker = get(name)

        # Mask secrets in output
        result['password_masked'] = '***' if broker.get('password') else ''
        result['private_key_masked'] = '***' if broker.get('private_key') else ''

        # Use live verification status if available
        v = verify_results.get(name, {})
        if v.get('verified'):
            result['status'] = 'ready'
            result['verified'] = True
            result['verification_error'] = None
            if v.get('account_summary'):
                result['account_summary'] = v['account_summary']
        else:
            result['verified'] = False
            result['verification_error'] = v.get('verification_error')
            if result.get('status') == 'incomplete':
                blocked.append(name)
            elif v.get('verification_error'):
                result['status'] = 'ready_but_unverified'
                blocked.append(name)
            else:
                result['status'] = 'unknown'
                blocked.append(name)

        results[name] = result

    blocked = sorted(set(blocked))
    allow_trading = len(blocked) == 0
    output = {
        'timestamp': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
        'results': results,
        'blocked': blocked,
        'allow_trading': allow_trading,
    }
    GATE_RESULTS_PATH.parent.mkdir(parents=True, exist_ok=True)
    GATE_RESULTS_PATH.write_text(json.dumps(output, indent=2), encoding='utf-8')
    return output, blocked


if __name__ == '__main__':
    results, blocked = run_gate()
    print(json.dumps({'blocked': blocked, 'allow_trading': len(blocked) == 0, 'results': results}, indent=2))
    if blocked:
        raise SystemExit(2)
