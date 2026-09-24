#!/usr/bin/env python3
"""Validate coingecko_id_map in capital_com_crypto_universe.json via CoinGecko search API."""
import json, urllib.request, urllib.parse, time
from pathlib import Path

PATH = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm\data_raw\capital_com_crypto_universe.json')
BASE = 'https://api.coingecko.com/api/v3/search'
HDR = {'Accept':'application/json','User-Agent':'Mozilla/5.0 (compatible; Zeus/1.0)'}

data = json.loads(PATH.read_text(encoding='utf-8'))
cmap = data.get('coingecko_id_map', {})
symbols = data.get('assets', [])

results = []
bad = []
for sym in symbols:
    cid = cmap.get(sym)
    if not cid:
        bad.append((sym, 'MISSING'))
        continue
    # fetch coin by id to verify exact symbol match
    try:
        url = f'{BASE}?query={urllib.parse.quote(cid)}'
        req = urllib.request.Request(url, headers=HDR)
        with urllib.request.urlopen(req, timeout=15) as r:
            js = json.loads(r.read().decode())
        coins = js.get('coins', [])
        match = None
        for c in coins:
            if c.get('id') == cid:
                match = c
                break
        if match and match.get('symbol', '').upper() == sym.upper():
            results.append((sym, cid, 'OK', match.get('symbol')))
        elif match:
            results.append((sym, cid, 'SYMBOL_MISMATCH', match.get('symbol')))
            bad.append((sym, f'{cid} -> symbol={match.get("symbol")}'))
        else:
            results.append((sym, cid, 'ID_NOT_FOUND', None))
            bad.append((sym, f'{cid} not found'))
    except Exception as e:
        results.append((sym, cid, 'ERROR', str(e)))
        bad.append((sym, f'ERROR: {e}'))
    time.sleep(0.25)

print(f'Checked {len(symbols)} assets, bad={len(bad)}')
for sym, info in bad:
    print(f'  {sym}: {info}')

out = {
    'ts': __import__('datetime').datetime.now(__import__('datetime').timezone.utc).isoformat(),
    'total': len(symbols),
    'bad_count': len(bad),
    'bad': [{'symbol': s, 'issue': i} for s, i in bad],
    'ok_count': len(symbols) - len(bad),
}
out_path = PATH.with_name('coingecko_validation.json')
out_path.write_text(json.dumps(out, indent=2), encoding='utf-8')
print(f'Wrote {out_path}')
