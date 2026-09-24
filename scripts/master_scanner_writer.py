#!/usr/bin/env python3
"""
master_scanner_writer.py
Always writes scan outputs to C:\\Users\\bravo-usr1\\Desktop\\scandata with UTC timestamped filenames.
Canonical scan data folder per user mandate.
"""
import json
from pathlib import Path
from datetime import datetime, timezone

SCANDATA = Path(r'C:\Users\bravo-usr1\Desktop\scandata')
SCANDATA.mkdir(parents=True, exist_ok=True)

def filename(prefix: str, ext: str = 'json') -> str:
    ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%MZ')
    return f'{prefix}_{ts}.{ext}'

def write_json(prefix: str, payload: dict) -> Path:
    p = SCANDATA / filename(prefix, 'json')
    p.write_text(json.dumps(payload, indent=2, default=str), encoding='utf-8')
    return p

def write_text(prefix: str, text: str, ext: str = 'txt') -> Path:
    p = SCANDATA / filename(prefix, ext)
    p.write_text(text, encoding='utf-8')
    return p

def write_markdown(prefix: str, md: str) -> Path:
    return write_text(prefix, md, ext='md')

if __name__ == '__main__':
    print(f'Scanner writer ready. scandata={SCANDATA}')
    print('Example files:')
    for fn in [
        filename('CRYPTO_SCAN', 'json'),
        filename('CRYPTO_SCAN', 'md'),
        filename('RANKED_SETUPS', 'json'),
    ]:
        print(' ', SCANDATA / fn)
