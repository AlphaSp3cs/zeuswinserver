#!/usr/bin/env python3
"""Canonical broker credential loader for OuroTaurus Trade Firm."""
import json
import os
from pathlib import Path

BASE = Path(__file__).resolve().parent.parent
SECURE = BASE / '.broker_creds_secure.json'
DOTENV = BASE / '.env'


def _load_dotenv(path: Path) -> dict:
    env = {}
    if not path.exists():
        return env
    for line in path.read_text(encoding='utf-8').splitlines():
        line = line.strip()
        if not line or line.startswith('#') or '=' not in line:
            continue
        key, _, value = line.partition('=')
        env[key.strip()] = value.strip()
    return env


def _coerce_bool(value: str) -> bool:
    return str(value).strip().lower() in {'1', 'true', 'yes', 'y', 'on'}


def get(name: str) -> dict:
    """Return broker config dict for `name`, preferring secure JSON, falling back to .env."""
    secure = {}
    if SECURE.exists():
        try:
            secure = json.loads(SECURE.read_text(encoding='utf-8'))
        except Exception:
            secure = {}
    broker = secure.get(name, {})
    env = _load_dotenv(DOTENV)

    # Map common env var sets onto canonical keys
    if name.lower() == 'alpaca':
        broker.setdefault('api_key', env.get('ALPACA_API_KEY_ID', ''))
        broker.setdefault('secret_key', env.get('ALPACA_API_SECRET_KEY', ''))
        broker.setdefault('base_url', env.get('ALPACA_BASE_URL', 'https://paper-api.alpaca.markets/v2'))
        broker.setdefault('account', env.get('ALPACA_ACCOUNT', ''))
        broker.setdefault('paper', True)
    elif name.lower() == 'etoro':
        broker.setdefault('api_key', env.get('ETORO_API_KEY', ''))
        broker.setdefault('user_key', env.get('ETORO_USER_KEY', ''))
        broker.setdefault('base_url', env.get('ETORO_BASE_URL', 'https://public-api.etoro.com'))
        broker.setdefault('mode', (env.get('ETORO_MODE') or 'demo').lower().strip())
    elif name.lower() == 'ibkr':
        broker.setdefault('host', env.get('IBKR_HOST', '127.0.0.1'))
        broker.setdefault('port', int(env.get('IBKR_PORT', broker.get('port', '4002'))))
        broker.setdefault('account', env.get('IBKR_ACCOUNT', broker.get('account', '')))
        broker.setdefault('client_id', int(env.get('IBKR_CLIENT_ID', broker.get('client_id', '2002'))))
    elif name.lower() == 'kraken':
        broker.setdefault('api_key', env.get('KRAKEN_API_KEY', ''))
        broker.setdefault('private_key', env.get('KRAKEN_PRIVATE_KEY', ''))
        broker.setdefault('base_url', 'https://api.kraken.com')
    elif name.lower() == 'capital':
        broker.setdefault('login', env.get('CAPITAL_MT5_LOGIN', ''))
        broker.setdefault('password', env.get('CAPITAL_MT5_PASSWORD', ''))
        broker.setdefault('server', env.get('CAPITAL_MT5_SERVER', ''))
        broker.setdefault('terminal', env.get('CAPITAL_MT5_TERMINAL', ''))
    return broker


def mask(text: str) -> str:
    text = text or ''
    text = text.strip()
    if len(text) <= 8:
        return '***'
    return text[:4] + '...' + text[-4:]


def health_check(name: str) -> dict:
    """Lightweight broker health check. No secret material is returned."""
    broker = get(name)
    result = {
        'broker': name,
        'has_api_key': bool(broker.get('api_key') or broker.get('public_key')),
        'has_secret': bool(broker.get('secret_key') or broker.get('private_key')),
        'has_password': bool(broker.get('password')),
        'account': broker.get('account', ''),
        'base_url': broker.get('base_url', ''),
        'status': 'unknown',
        'verified': False,
    }
    if name.lower() == 'capital':
        result['status'] = 'ready' if all([broker.get('login'), broker.get('password'), broker.get('server'), broker.get('terminal')]) else 'incomplete'
        result['verified'] = result['status'] == 'ready'
    elif name.lower() == 'alpaca':
        present = all([broker.get('api_key'), broker.get('secret_key'), broker.get('base_url')])
        result['status'] = 'ready_but_unverified' if present else 'incomplete'
        result['verified'] = False
    elif name.lower() == 'etoro':
        present = all([broker.get('api_key'), broker.get('user_key')])
        result['status'] = 'ready_but_unverified' if present else 'incomplete'
        result['verified'] = False
    elif name.lower() == 'ibkr':
        present = all([broker.get('host'), broker.get('port'), broker.get('account')])
        result['status'] = 'ready_but_unverified' if present else 'incomplete'
        result['verified'] = False
    elif name.lower() == 'kraken':
        present = all([broker.get('api_key'), broker.get('private_key')])
        result['status'] = 'ready_but_unverified' if present else 'incomplete'
        result['verified'] = False
    return result


if __name__ == '__main__':
    import json
    names = ['capital', 'alpaca', 'etoro', 'ibkr', 'kraken']
    print(json.dumps({n: health_check(n) for n in names}, indent=2))
