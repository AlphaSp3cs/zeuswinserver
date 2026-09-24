#!/usr/bin/env python3
"""
alpaca_etoro_demo_20260817.py
Places dayshift setups on Alpaca and eToro using existing scans.
"""
import json, uuid, requests, sys
from pathlib import Path
from datetime import datetime, timezone

BASE_FIRM = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
ARTIFACTS = BASE_FIRM / 'artifacts'
NOW = datetime.now(timezone.utc).strftime('%Y%m%dT%H%MZ')

creds = json.loads((BASE_FIRM / '.broker_creds_secure.json').read_text())

# ========================= ALPACA =========================
ALPACA = creds['alpaca']
ALPACA_HEADERS = {
    'APCA-API-KEY-ID': ALPACA['api_key'],
    'APCA-API-SECRET-KEY': ALPACA['secret_key'],
}
ALPACA_BASE = ALPACA['base_url'].rstrip('/')

ALPACA_TRADES = [
    {'symbol': 'KO',   'side': 'buy',  'qty': 0.01, 'limit': 87.70,  'sl': 86.95, 'tp': 89.22},
    {'symbol': 'DIS',  'side': 'buy',  'qty': 0.01, 'limit': 106.85, 'sl': 105.65,'tp': 109.25},
    {'symbol': 'CVX',  'side': 'buy',  'qty': 0.01, 'limit': 199.90, 'sl': 197.10,'tp': 207.50},
    {'symbol': 'TLT',  'side': 'sell', 'qty': 0.01, 'limit': 82.04,  'sl': 82.70, 'tp': 80.72},
]


def alpaca_submit_bracket(trade):
    payload = {
        'symbol': trade['symbol'],
        'qty': str(trade['qty']),
        'side': trade['side'],
        'type': 'limit',
        'time_in_force': 'day',
        'limit_price': str(trade['limit']),
        'order_class': 'bracket',
        'stop_loss': {'stop_price': str(trade['sl']), 'limit_price': str(trade['sl'])},
        'take_profit': {'limit_price': str(trade['tp'])},
    }
    r = requests.post(f"{ALPACA_BASE}/orders", headers=ALPACA_HEADERS, json=payload, timeout=20)
    return {'symbol': trade['symbol'], 'status_code': r.status_code, 'response': r.text[:500], 'payload': payload}


# ========================= ETORO =========================
ETORO_BASE = 'https://public-api.etoro.com'
ETORO_API_KEY = creds['etoro']['api_key']
ETORO_USER_KEY = creds['etoro']['user_key']
ETORO_SYMBOL_MAP = json.loads((BASE_FIRM / 'workflow' / 'etoro_symbol_map.json').read_text()) if (BASE_FIRM / 'workflow' / 'etoro_symbol_map.json').exists() else {}


def etoro_headers():
    return {
        'x-request-id': str(uuid.uuid4()),
        'x-api-key': ETORO_API_KEY,
        'x-user-key': ETORO_USER_KEY,
        'Accept': 'application/json',
    }


def etoro_instrument_id(symbol):
    norm = symbol.upper().replace('-USD','').replace('USD','').replace('/','').strip()
    for key in [norm, symbol.upper().replace('/',''), f'{norm}-USD']:
        info = ETORO_SYMBOL_MAP.get(key)
        if info:
            return info.get('id')
    return None


def etoro_place_demo(symbol, side, amount_usd, sl=None, tp=None):
    instrument_id = etoro_instrument_id(symbol)
    if instrument_id is None:
        return {'symbol': symbol, 'status_code': 0, 'response': 'SKIP: no instrument_id in symbol map'}
    payload = {
        'action': 'open',
        'transaction': side.lower(),
        'instrumentID': int(instrument_id) if str(instrument_id).isdigit() else instrument_id,
        'orderType': 'mkt',
        'leverage': 1,
        'amount': amount_usd,
        'orderCurrency': 'usd',
    }
    if sl is not None:
        payload['stopLossRate'] = sl
    if tp is not None:
        payload['takeProfitRate'] = tp
    url = f'{ETORO_BASE}/api/v2/trading/execution/demo/orders'
    r = requests.post(url, headers=etoro_headers(), json=payload, timeout=15)
    return {'symbol': symbol, 'instrument_id': instrument_id, 'status_code': r.status_code, 'response': r.text[:500], 'payload': payload}


def main():
    results = []
    for t in ALPACA_TRADES:
        try:
            res = alpaca_submit_bracket(t)
            results.append({'broker': 'alpaca', **res})
            print(f"ALPACA {t['symbol']}: {res['status_code']} {res['response'][:120]}")
        except Exception as e:
            results.append({'broker': 'alpaca', 'symbol': t['symbol'], 'status_code': 0, 'response': str(e)})
            print(f"ALPACA {t['symbol']} EXCEPTION: {e}")

    etoro_trades = [
        {'symbol': 'ETH/USD', 'side': 'buy', 'amount_usd': 100.0},
        {'symbol': 'DOGEUSD', 'side': 'buy', 'amount_usd': 100.0},
        {'symbol': 'AVAX-USD', 'side': 'buy', 'amount_usd': 100.0},
    ]
    for t in etoro_trades:
        try:
            res = etoro_place_demo(t['symbol'], t['side'], t['amount_usd'])
            results.append({'broker': 'etoro_demo', **res})
            print(f"ETORO {t['symbol']}: {res['status_code']} {res['response'][:120]}")
        except Exception as e:
            results.append({'broker': 'etoro_demo', 'symbol': t['symbol'], 'status_code': 0, 'response': str(e)})
            print(f"ETORO {t['symbol']} EXCEPTION: {e}")

    out = {'ts': datetime.now(timezone.utc).isoformat(), 'brokers': ['alpaca', 'etoro_demo'], 'results': results}
    out_path = ARTIFACTS / f'alpaca_etoro_demo_{NOW}.json'
    out_path.write_text(json.dumps(out, indent=2, default=str), encoding='utf-8')
    print(f'\nWrote {out_path}')


if __name__ == '__main__':
    main()
