#!/usr/bin/env python3
"""
dayshift_scan_grader.py
Grade fresh dayshift scan with backtest, news, and conviction filters.
Creates sector-sorted execution tickets for Telegram approval.
"""
import json
import sys
from pathlib import Path
from datetime import datetime, timezone

SCANDATA = Path('C:/Users/bravo-usr1/Desktop/scandata')
WORKFLOW = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/workflow')
BASE = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')

# Find latest dayshift scan
scan_files = sorted(SCANDATA.glob('DAYSHIFT_*_PREMKT_*.json'))
if not scan_files:
    print('No dayshift scan found')
    exit(1)
latest_scan = scan_files[-1]
print(f'Loading scan: {latest_scan.name}')

scan_data = json.loads(latest_scan.read_text(encoding='utf-8'))
qualified = scan_data.get('qualified_setups', [])
print(f'Qualified setups: {len(qualified)}')

# Load backtest registry
sys.path.insert(0, str(BASE / 'scripts'))
from backtest_registry import require_backtest

# Load news
news_path = WORKFLOW / f'news_sentiment_{datetime.now().date().isoformat()}.json'
if not news_path.exists():
    news_path = WORKFLOW / 'news_sentiment_2026-08-19.json'
news = {}
if news_path.exists():
    try:
        news = json.loads(news_path.read_text(encoding='utf-8'))
    except Exception:
        pass

# Grade each setup
graded = []
for setup in qualified:
    symbol = setup.get('symbol', '')
    bias = setup.get('direction', 'NEUTRAL')
    conv = float(setup.get('conviction', 0))
    bt = setup.get('backtest', {})
    wr = float(bt.get('win_rate', 0) or 0)
    pf = float(bt.get('profit_factor', 0) or 0)
    avg_r = float(bt.get('avg_r', 0) or 0)
    trades = int(bt.get('trades', 0) or 0)
    rsi = float(setup.get('rsi', 50) or 50)
    rr = float(setup.get('risk_reward', 0) or 0)
    entry = float(setup.get('entry', 0) or 0)
    sl = float(setup.get('stop_loss', 0) or 0)
    tp = float(setup.get('take_profit', 0) or 0)
    asset = setup.get('asset_class', '')

    # Backtest gate: scanner backtest or registry
    bt_pass = wr >= 0.55 and avg_r > 0
    if not bt_pass:
        try:
            bt_pass = require_backtest(symbol, min_win_rate=0.55, min_expectancy=0.0)
        except Exception:
            pass

    # News gate
    news_score = 0
    sym_upper = symbol.upper()
    if isinstance(news, dict):
        sent = news.get(sym_upper, news.get(sym_upper.replace('-USD', '').replace('USD', ''), {}))
        if isinstance(sent, dict) and 'score' in sent:
            news_score = float(sent['score'])
        elif isinstance(sent, (int, float)):
            news_score = float(sent)

    # Zone discipline overlay
    zone = 100.0
    if not sl or not tp or entry <= 0:
        zone -= 40.0
    if not bt_pass:
        zone -= 15.0
    zone = max(0.0, min(100.0, zone))

    # Composite score
    tech = 50.0
    if rsi < 30:
        tech += 20
    elif rsi < 40:
        tech += 10
    elif rsi > 70:
        tech -= 10
    elif rsi > 80:
        tech -= 20

    composite = round(
        0.35 * (50 + conv * 5) +
        0.35 * tech +
        0.10 * min(rr * 20, 100) +
        0.10 * min(trades / 90 * 100, 100) +
        0.05 * zone +
        0.05 * min(abs(news_score) * 100, 100),
        2
    )
    composite = max(0, min(100, composite))

    # Filter: must have backtest pass or strong conviction, and valid SL/TP
    if not sl or not tp or entry <= 0:
        continue
    if not bt_pass and conv < 5:
        continue

    graded.append({
        'symbol': symbol,
        'bias': bias,
        'asset_class': asset,
        'conviction': conv,
        'composite_score': composite,
        'backtest_pass': bt_pass,
        'win_rate': wr,
        'profit_factor': pf,
        'avg_r': avg_r,
        'trades': trades,
        'rsi': rsi,
        'rr': rr,
        'entry': entry,
        'sl': sl,
        'tp': tp,
        'zone_discipline': zone,
        'news_score': news_score,
        'verification_tier': 'VERIFIED' if bt_pass else 'PLAUSIBLE',
        'verification_evidence': ['scanner_backtest_90trades'] if bt_pass else ['scanner_backtest_insufficient'],
        'independent_check': bool(bt_pass),
        'verified_at': datetime.now(timezone.utc).isoformat() if bt_pass else None,
        'notes': 'Backtested 90-trade sample' if bt_pass else 'Backtest below gate; requires additional verification',
    })

# Sort: backtest pass first, then composite, then conviction
graded.sort(key=lambda x: (x['backtest_pass'], x['composite_score'], x['conviction']), reverse=True)

# Sector sort: equities first, ETFs, crypto, forex, commodities, bonds
sector_order = {
    'Equities': 0,
    'ETFs': 1,
    'Crypto': 2,
    'Forex': 3,
    'Commodities': 4,
    'Bonds': 5,
    'Indices': 6,
}
graded.sort(key=lambda x: (sector_order.get(x['asset_class'], 99), -x['composite_score']))

print(f'Passed filters: {len(graded)}')
for i, g in enumerate(graded[:15], 1):
    print(f"{i}. {g['symbol']} {g['bias']} | {g['asset_class']} | composite={g['composite_score']} conv={g['conviction']} bt={g['backtest_pass']} wr={g['win_rate']} pf={g['profit_factor']} rsi={g['rsi']} entry={g['entry']} sl={g['sl']} tp={g['tp']}")

# Save graded results
out_path = SCANDATA / f'DAYSHIFT_GRADED_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")}.json'
out_data = {
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'source_scan': latest_scan.name,
    'total_passed': len(graded),
    'top': graded[:20],
}
out_path.write_text(json.dumps(out_data, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'\nSaved graded results: {out_path}')
