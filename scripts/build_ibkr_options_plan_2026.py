#!/usr/bin/env python3
"""
IBKR September/October 2026 options plan builder with global expiry context.
"""
import json
from pathlib import Path
from datetime import datetime, timezone

ROOT = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
ARTIFACTS = ROOT / 'artifacts'
NOW = datetime.now(timezone.utc).strftime('%Y%m%dT%H%MZ')

# Standard expiry conventions:
# - U.S. equity/index monthly options: third Friday of the month
# - U.S. weekly equity/index options: every Friday
# - European equity options: typically third Friday (varies by exchange)
# - Asian options: typically second Thursday or end-of-month
# - Cryptocurrency options: often end-of-day Friday or end-of-month
# - Quadruple witching (stock + index + single-stock + ETF): March/June/Sept/Dec third Fridays

# September 2026
# Labor Day = Sept 7, 2026 (Monday, US market closed)
# Third Friday = Sept 18, 2026
# September is a QUADRUPLE WITCHING month

# October 2026
# Third Friday = Oct 16, 2026

MONTHLY_EXPS = ['20260918', '20261016']
WEEKLY_EXPS = [
    '20260821', '20260828',
    '20260904', '20260911', '20260918',
    '20260925',
    '20261002', '20261009', '20261016',
]

# Underlyings from current dayshift setups + existing IBKR positions
UNDERLYINGS = [
    {'symbol': 'SPY',  'target': 547.41, 'qty': 1},
    {'symbol': 'QQQ',  'target': 473.57, 'qty': 1},
    {'symbol': 'NVDA', 'target': 118.75, 'qty': 1},
    {'symbol': 'AAPL', 'target': 213.75, 'qty': 1},
    {'symbol': 'JPM',  'target': 185.25, 'qty': 1},
]

# Known working exchanges from prior IBKR option qualification
OPTION_EXCHANGES = ['CBOE', 'ARCA', 'AMEX', 'ISE', 'PHLX', 'SMART']

plan = []
for u in UNDERLYINGS:
    sym = u['symbol']
    target = float(u['target'])
    for exp in MONTHLY_EXPS + WEEKLY_EXPS:
        # Build candidate strikes: ATM ± offsets sized by price level
        if target >= 200:
            offsets = [0, 2.5, 5, 7.5, 10]
        elif target >= 100:
            offsets = [0, 1.25, 2.5, 5, 7.5]
        elif target >= 50:
            offsets = [0, 1, 2, 2.5, 5]
        else:
            offsets = [0, 0.5, 1, 2.5, 5]

        for right in ['C', 'P']:
            for offset in offsets:
                if right == 'C':
                    strike = round(target + offset, 2)
                else:
                    strike = round(target - offset, 2)
                if strike <= 0:
                    continue
                plan.append({
                    'underlying': sym,
                    'direction': 'LONG_CALL' if right == 'C' else 'LONG_PUT',
                    'strike': strike,
                    'expiry': exp,
                    'qty': u['qty'],
                    'exchanges': OPTION_EXCHANGES,
                    'status': 'PENDING',
                    'note': f'ATM±{offset} for {sym} {right}',
                })

# Deduplicate by underlying+right+expiry+strike
seen = set()
deduped = []
for leg in plan:
    key = (leg['underlying'], leg['direction'], leg['expiry'], leg['strike'])
    if key not in seen:
        seen.add(key)
        deduped.append(leg)

plan = deduped

out = {
    'ts': datetime.now(timezone.utc).isoformat(),
    'name': 'sept_oct_2026_options_plan',
    'market_context': {
        'quadruple_witching': '2026-09-18 is a quadruple witching date',
        'labor_day_us': '2026-09-07 US markets closed for Labor Day',
        'expiry_rules': {
            'us_equity_index_monthly': 'Third Friday of the month',
            'us_weekly': 'Every Friday',
            'european_equity': 'Typically third Friday, varies by exchange',
            'asian_equity': 'Typically second Thursday or end-of-month',
            'crypto': 'Often end-of-day Friday or end-of-month',
        },
        'note': 'September 2026 is a quadruple witching month - expect elevated volatility around expiration',
    },
    'monthly_expiries': MONTHLY_EXPS,
    'weekly_expiries': WEEKLY_EXPS,
    'underlyings': UNDERLYINGS,
    'legs': plan,
    'execution_notes': [
        'Use ibkr_options_run_20260817.py with reqSecDefOptParams + fallback weeklys.',
        'If monthly chain empty on 20260918/20261016, fallback to nearest weekly with valid conId.',
        'Prefer CBOE/ARCA/AMEX based on prior successful qualification.',
        'Place market orders only after qualifying exact conId.',
        'September 18, 2026 is quadruple witching - monitor for increased volatility',
    ],
}

out_path = ARTIFACTS / f'ibkr_options_plan_sept_oct_2026_{NOW}.json'
out_path.write_text(json.dumps(out, indent=2, default=str), encoding='utf-8')
print(f'WROTE {out_path}')
print(f'Total legs: {len(plan)}')
print(f'Sample:')
for leg in plan[:10]:
    print(' ', leg['underlying'], leg['direction'], leg['strike'], leg['expiry'])
