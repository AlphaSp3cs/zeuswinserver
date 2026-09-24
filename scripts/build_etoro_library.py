#!/usr/bin/env python3
"""Build eToro asset database/library from watchlists."""
import json, uuid
from pathlib import Path
import requests

ETORO_BASE = 'https://public-api.etoro.com'
API_KEY = 'sdgdskldFPLGfjHn1421dgnlxdGTbngdflg6290bRjslfihsjhSDsdgGHH25hjf'
USER_KEY = 'eyJjaSI6IjYwY2FiYjBiLTU1OTctNDQ4NS04ZjYzLTdlOWUwNTZlMGJiOCIsImVhbiI6IlVucmVnaXN0ZXJlZEFwcGxpY2F0aW9uIiwiZWsiOiIuVjZ3S2xJOEpTajlrbHRySndMeHMzNEMwMXkuMDFrNG8tWjBScGllYzBCUHBSc1JrR3JocUQ3RHh2Q01wY3QtRURQSlFMTE1UalJiQ0VBNkxUYklhSklULnJkVnFGYjdGcjJSYjZpakhnUV8ifQ__'
BASE = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
WORKFLOW = BASE / 'workflow'

headers = lambda: {
    'x-api-key': API_KEY,
    'x-user-key': USER_KEY,
    'x-request-id': str(uuid.uuid4()),
    'Accept': 'application/json',
}

def fetch_watchlists():
    r = requests.get(f'{ETORO_BASE}/api/v1/watchlists', headers=headers(), timeout=15)
    r.raise_for_status()
    return r.json().get('watchlists', [])

def fetch_watchlist_items(wl_id):
    # Use bulk endpoint which includes market data
    r = requests.get(f'{ETORO_BASE}/api/v1/watchlists', headers=headers(), timeout=15)
    r.raise_for_status()
    for wl in r.json().get('watchlists', []):
        if wl.get('watchlistId') == wl_id:
            return wl.get('items', [])
    return []

def main():
    watchlists = fetch_watchlists()
    print(f'Fetched {len(watchlists)} watchlists')

    instruments = {}
    for wl in watchlists:
        wl_name = wl.get('name', 'Unknown')
        wl_type = wl.get('watchlistType', 'Unknown')
        try:
            items = fetch_watchlist_items(wl.get('watchlistId'))
            print(f'  {wl_name}: {len(items)} items')
            for item in items:
                market = item.get('market') or {}
                sym = (market.get('symbolName') or '').upper().strip()
                iid = str(market.get('id', '')).strip()
                if not sym or not iid:
                    continue
                if sym not in instruments:
                    instruments[sym] = {
                        'id': iid,
                        'displayName': market.get('displayName'),
                        'assetTypeId': market.get('assetTypeId'),
                        'assetTypeSubCategoryId': market.get('assetTypeSubCategoryId'),
                        'exchangeId': market.get('exchangeId'),
                        'sector': wl_name,
                        'sectorType': wl_type,
                    }
        except Exception as e:
            print(f'Error fetching {wl_name}: {e}')

    print(f'Total unique instruments: {len(instruments)}')

    lib = {
        'meta': {
            'source': 'eToro public API /api/v1/watchlists',
            'total_watchlists': len(watchlists),
            'total_instruments': len(instruments),
            'fetched_at': '2026-08-16T03:15:00+00:00',
            'notes': 'Comprehensive eToro asset library with symbol->instrumentID mapping',
        },
        'instruments': instruments,
    }
    out = WORKFLOW / 'etoro_instrument_library.json'
    out.write_text(json.dumps(lib, indent=2), encoding='utf-8')
    print(f'Saved {out}')

    # Update symbol map
    sym_map_path = WORKFLOW / 'etoro_symbol_map.json'
    sym_map = json.loads(sym_map_path.read_text(encoding='utf-8')) if sym_map_path.exists() else {}
    merged = dict(sym_map)
    for sym, info in instruments.items():
        if sym not in merged or not merged[sym].get('id'):
            merged[sym] = info
    sym_map_path.write_text(json.dumps(merged, indent=2), encoding='utf-8')
    print(f'Updated symbol map: {len(merged)} entries')

    # Asset type breakdown
    type_map = {1:'INDEX', 2:'COMMODITY', 4:'FOREX', 5:'EQUITY/ETF', 6:'INDEX_FUTURE', 10:'CRYPTO'}
    types = {}
    for info in instruments.values():
        t = info.get('assetTypeId', 'Unknown')
        types[t] = types.get(t, 0) + 1
    print('Asset type coverage:')
    for t, c in sorted(types.items()):
        print(f'  {t} ({type_map.get(t, "UNKNOWN")}): {c}')

if __name__ == '__main__':
    main()
