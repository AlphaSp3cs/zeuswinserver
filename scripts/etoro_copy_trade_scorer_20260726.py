#!/usr/bin/env python3
"""
eToro Copy Trade Scorer
Scores Popular Investment Portfolios by recent performance across major sectors.
"""

import sys, os
sys.path.insert(0, 'C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
os.chdir('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
from pathlib import Path
import json
import datetime
import requests

# Load .env
env_path = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/.env')
if env_path.exists():
    with open(env_path) as f:
        for line in f:
            line = line.strip()
            if not line or line.startswith('#') or '=' not in line:
                continue
            k, v = line.split('=', 1)
            os.environ[k.strip()] = v.strip().strip('"').strip("'")

ETORO_KEY = os.environ.get('ETORO_API_KEY', '')
ETORO_USER_KEY = os.environ.get('ETORO_USER_KEY', '')
ETORO_BASE = 'https://public-api.etoro.com/api/v1'

SECTOR_KEYWORDS = {
    'crypto': ['bitcoin', 'btc', 'eth', 'ethereum', 'sol', 'solana', 'xrp', 'ripple', 'ada', 'cardano', 'doge', 'dogecoin'],
    'indices': ['spy', 'qqq', 'dow', 'nasdaq', 's&p', 'russel', 'ftse', 'dax'],
    'commodities': ['gold', 'silver', 'oil', 'wti', 'brent', 'copper', 'natgas', 'natural gas'],
    'fx': ['usd', 'eur', 'gbp', 'jpy', 'aud', 'nzd', 'cad'],
}


def classify_sector(name: str):
    l = name.lower()
    for sector, kws in SECTOR_KEYWORDS.items():
        if any(k in l for k in kws):
            return sector
    return 'other'


def main():
    print("="*70)
    print("ETORO COPY TRADE SCORER")
    print("="*70)

    if not ETORO_KEY or not ETORO_USER_KEY:
        print("Missing eToro credentials")
        return

    headers = {'x-api-key': ETORO_KEY, 'x-user-key': ETORO_USER_KEY}

    # Try Popular Investment Portfolios / top traders
    portfolios = []
    for path in ['/trading/info/portfolios', '/trading/info/top-portfolios', '/trading/info/popular- portfolios']:
        url = ETORO_BASE + path
        try:
            r = requests.get(url, headers=headers, timeout=15)
            if r.status_code == 200:
                data = r.json()
                if isinstance(data, list):
                    portfolios = data
                elif isinstance(data, dict):
                    portfolios = data.get('portfolios', data.get('items', []))
                print(f"Loaded {len(portfolios)} portfolios from {path}")
                break
        except Exception as e:
            print(f"Error fetching {path}: {e}")

    if not portfolios:
        print("No portfolio data available from tested endpoints; save empty result set and stop.")
        out = {
            'timestamp': datetime.datetime.now().isoformat(),
            'portfolios': [],
            'top_scores': [],
            'selected_sectors': ['crypto', 'indices', 'commodities'],
            'note': 'no portfolio data returned'
        }
        Path('etoro_copy_trade_scores_2026-07-26.json').write_text(json.dumps(out, indent=2))
        print("Awuuuu!!!! the pack is finished.")
        return

    scored = []
    for p in portfolios:
        name = p.get('name', p.get('displayName', ''))
        returns = p.get('returns', p.get('performance', {}))
        if isinstance(returns, dict):
            short_term = returns.get('7d', returns.get('1M', returns.get('1W', 0)))
            mid_term = returns.get('1M', returns.get('3M', 0))
            long_term = returns.get('3M', returns.get('6M', returns.get('YTD', 0)))
        else:
            short_term = mid_term = long_term = 0
        score = (float(short_term or 0) + float(mid_term or 0) + float(long_term or 0))
        sector = classify_sector(name)
        scored.append({
            'name': name,
            'id': p.get('id', p.get('instrumentId')),
            'sector': sector,
            'short_term': short_term,
            'mid_term': mid_term,
            'long_term': long_term,
            'score': score,
        })

    scored.sort(key=lambda x: x['score'], reverse=True)

    # Select one per user-requested sector
    selected_sectors = ['crypto', 'indices', 'commodities']
    top_scores = []
    for sector in selected_sectors:
        picks = [s for s in scored if s['sector'] == sector]
        if picks:
            top_scores.append(picks[0])

    # If sector is empty, add best remaining
    if len(top_scores) < len(selected_sectors):
        for s in scored:
            if s not in top_scores:
                top_scores.append(s)
            if len(top_scores) >= len(selected_sectors):
                break

    out = {
        'timestamp': datetime.datetime.now().isoformat(),
        'portfolios': scored,
        'top_scores': top_scores,
        'selected_sectors': selected_sectors,
    }
    Path('etoro_copy_trade_scores_2026-07-26.json').write_text(json.dumps(out, indent=2))
    print("Saved etoro_copy_trade_scores_2026-07-26.json")
    print('\nTop copy-trade candidates:')
    for i, s in enumerate(top_scores, 1):
        print(f"{i}. [{s['sector'].upper():12}] {s['name']:40} score={s['score']:>7.2f}")

    print("\nAwuuuu!!!! the pack is finished.")


if __name__ == '__main__':
    main()
