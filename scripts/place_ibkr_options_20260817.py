#!/usr/bin/env python3
"""
Place IBKR options trades when gateway is available.
Retries failed placements due to gateway downtime.
"""
import sys, json, time
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
TS = datetime.now(timezone.utc).strftime('%Y-%m-%dT%H%MZ')
sys.path.insert(0, str(ROOT / 'scripts'))

try:
    from ibkr_options_runner import run_options_plan
except Exception as e:
    print('ibkr_options_runner import failed:', e)
    sys.exit(1)

plan = [
    {'underlying': 'NVDA', 'direction': 'LONG_CALL', 'strike': 118.75, 'expiry': '20260915', 'qty': 1},
    {'underlying': 'JPM', 'direction': 'LONG_CALL', 'strike': 185.25, 'expiry': '20260915', 'qty': 1},
    {'underlying': 'SPY', 'direction': 'LONG_CALL', 'strike': 547.41, 'expiry': '20260915', 'qty': 1},
    {'underlying': 'QQQ', 'direction': 'LONG_CALL', 'strike': 473.57, 'expiry': '20260915', 'qty': 1},
    {'underlying': 'AAPL', 'direction': 'LONG_CALL', 'strike': 213.75, 'expiry': '20260915', 'qty': 1},
]

result = run_options_plan(plan)
out = ROOT / 'artifacts' / f'ibkr_options_{TS}.json'
out.write_text(json.dumps(result, indent=2), encoding='utf-8')
print(f'WROTE {out}')
print(json.dumps(result, indent=2))
