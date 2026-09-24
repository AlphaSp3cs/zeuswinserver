#!/usr/bin/env python3
"""Build master asset universe mapped to all configured brokers."""
import json
from pathlib import Path
from collections import defaultdict
import requests

BASE = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
WORKFLOW = BASE / 'workflow'

def load_json(path):
    if path.exists():
        try:
            return json.loads(path.read_text(encoding='utf-8'))
        except Exception:
            return {}
    return {}

def norm(s):
    return (s or '').upper().strip()

def main():
    broker_symbols = defaultdict(set)

    # 1) capital_right from file
    cap = load_json(WORKFLOW / 'capital_right_tradeable_symbols_20260812.json')
    if isinstance(cap, dict):
        for s in cap.get('tradeable', []):
            broker_symbols['CAPITAL_RIGHT'].add(norm(s))
    elif isinstance(cap, list):
        for s in cap:
            broker_symbols['CAPITAL_RIGHT'].add(norm(s))

    # 2) alpaca from file
    alp = load_json(WORKFLOW / 'alpaca_tradeable_assets_20260812.json')
    if isinstance(alp, dict):
        for key in ['equities', 'crypto', 'tradable']:
            val = alp.get(key)
            if isinstance(val, list):
                for s in val:
                    broker_symbols['ALPACA'].add(norm(s))
    elif isinstance(alp, list):
        for s in alp:
            broker_symbols['ALPACA'].add(norm(s))

    # 3) etoro from instrument library
    etoro_lib = load_json(WORKFLOW / 'etoro_instrument_library.json')
    for sym, info in (etoro_lib.get('instruments') or {}).items():
        broker_symbols['ETORO'].add(norm(sym))

    # 4) crypto universe
    crypto_univ = load_json(WORKFLOW / 'crypto_universe_20260809.json')
    crypto_symbols = set()
    for s in (crypto_univ.get('symbols') or []):
        crypto_symbols.add(norm(s))

    # 5) Try Kraken public asset pairs endpoint
    try:
        r = requests.get('https://api.kraken.com/0/public/AssetPairs', timeout=15)
        if r.status_code == 200:
            data = r.json()
            pairs = data.get('result', {})
            for pair, info in pairs.items():
                wsname = info.get('wsname', '')
                if wsname and '/' in wsname:
                    base, quote = wsname.split('/')
                    broker_symbols['KRAKEN'].add(norm(base))
                    broker_symbols['KRAKEN'].add(norm(quote))
    except Exception as e:
        print(f'Kraken fetch failed: {e}')

    # 6) Try IBKR from existing snapshot
    ibkr_snap = load_json(WORKFLOW / 'live_universe_snapshot_20260812.json')
    if isinstance(ibkr_snap, dict):
        for key in ['stocks', 'etfs', 'options', 'futures', 'indices']:
            for s in (ibkr_snap.get(key) or []):
                if isinstance(s, str):
                    broker_symbols['IBKR'].add(norm(s))
                elif isinstance(s, dict):
                    broker_symbols['IBKR'].add(norm(s.get('symbol') or s.get('ticker') or ''))

    # 7) Add known FTMO symbols from memory/config patterns
    ftmo_known = [
        'NVDA', 'V', 'CVX', 'JNJ', 'JPM', 'BAC', 'XOM',
        'EURUSD', 'GBPUSD', 'USDJPY', 'XAUUSD', 'XAGUSD',
        'US30', 'US500', 'DE40', 'UK100', 'JP225',
        'BTCUSD', 'ETHUSD', 'SOLUSD', 'DOGEUSD', 'XRPUSD',
    ]
    for s in ftmo_known:
        broker_symbols['FTMO_LEFT'].add(norm(s))

    # Build master universe
    all_symbols = set()
    for syms in broker_symbols.values():
        all_symbols.update(syms)
    all_symbols.update(crypto_symbols)

    universe = {}
    for sym in sorted(all_symbols):
        if not sym:
            continue
        brokers = [b for b, syms in broker_symbols.items() if sym in syms]
        etoro_info = (etoro_lib.get('instruments') or {}).get(sym)
        universe[sym] = {
            'symbol': sym,
            'brokers': sorted(brokers),
            'broker_count': len(brokers),
            'in_crypto_universe': sym in crypto_symbols,
            'etoro_id': etoro_info.get('id') if etoro_info else None,
            'etoro_asset_type': etoro_info.get('assetTypeId') if etoro_info else None,
            'etoro_sector': etoro_info.get('sector') if etoro_info else None,
            'display_name': etoro_info.get('displayName') if etoro_info else None,
        }

    total = len(universe)
    multi = sum(1 for v in universe.values() if v['broker_count'] > 1)
    uniq = sum(1 for v in universe.values() if v['broker_count'] == 1)
    none_broker = sum(1 for v in universe.values() if v['broker_count'] == 0)

    out = {
        'meta': {
            'total_symbols': total,
            'multi_broker': multi,
            'single_broker': uniq,
            'no_broker': none_broker,
            'crypto_universe_coverage': sum(1 for v in universe.values() if v['in_crypto_universe']),
            'brokers': sorted(broker_symbols.keys()),
            'sources': [
                'capital_right_tradeable_symbols_20260812.json',
                'alpaca_tradeable_assets_20260812.json',
                'etoro_instrument_library.json',
                'crypto_universe_20260809.json',
                'Kraken /0/public/AssetPairs',
                'live_universe_snapshot_20260812.json',
                'ftmo_known from memory',
            ],
        },
        'universe': universe,
    }

    out_path = WORKFLOW / 'master_asset_universe.json'
    out_path.write_text(json.dumps(out, indent=2), encoding='utf-8')
    print(f'Saved {out_path}')
    print(f'Total: {total} | multi-broker: {multi} | single-broker: {uniq} | no-broker: {none_broker}')

    broker_cov = defaultdict(int)
    for v in universe.values():
        for b in v['brokers']:
            broker_cov[b] += 1
    print('Broker coverage:')
    for b, c in sorted(broker_cov.items(), key=lambda x: -x[1]):
        print(f'  {b}: {c}')

if __name__ == '__main__':
    main()
