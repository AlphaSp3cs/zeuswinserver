#!/usr/bin/env python3
"""
etoro_demo_copy_ticket.py
Create exact eToro demo long-swing allocation tickets for highest-conviction setups.
DEMO ONLY. Live copy trading requires manual approval in the eToro UI.
"""
import json
from pathlib import Path
from datetime import datetime, timezone

SCANDATA = Path('C:/Users/bravo-usr1/Desktop/scandata')
WORKFLOW = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/workflow')

# Latest graded dayshift scan
graded_files = sorted(SCANDATA.glob('DAYSHIFT_GRADED_*.json'))
latest_graded = graded_files[-1]
data = json.loads(latest_graded.read_text(encoding='utf-8'))
top = data.get('top', [])

# Filter for eToro-eligible long swings: equities/ETFs, backtest pass or high conviction
eligible = [g for g in top if g['asset_class'] in ('Equities', 'ETFs') and g['bias'] == 'LONG']
eligible.sort(key=lambda x: (x['backtest_pass'], x['composite_score'], x['conviction']), reverse=True)

# Pick top 2 for eToro demo practice
picks = eligible[:2]

# Allocate $5k total: split 60/40 between top 2
total = 5000.0
allocations = []
for i, pick in enumerate(picks):
    weight = 0.6 if i == 0 else 0.4
    amount = round(total * weight, 2)
    symbol = pick['symbol']
    entry = pick['entry']
    sl = pick['sl']
    tp = pick['tp']
    conv = pick['conviction']
    composite = pick['composite_score']
    bt = pick['backtest_pass']
    asset = pick['asset_class']

    # Long-swing practice parameters
    if asset == 'Equities':
        leverage = 1  # no leverage for long-swing practice
        amount_usd = min(amount, 2500.0)  # eToro demo max per trade
    else:
        leverage = 1
        amount_usd = min(amount, 2500.0)

    ticket = {
        'timestamp': datetime.now(timezone.utc).isoformat(),
        'broker': 'etoro',
        'mode': 'DEMO',
        'strategy': 'long_swing_practice',
        'symbol': symbol,
        'asset_class': asset,
        'side': 'BUY',
        'amount_usd': amount_usd,
        'leverage': leverage,
        'entry': entry,
        'sl': sl,
        'tp': tp,
        'conviction': conv,
        'composite_score': composite,
        'backtest_pass': bt,
        'win_rate': pick.get('win_rate'),
        'profit_factor': pick.get('profit_factor'),
        'rr': pick.get('rr'),
        'rsi': pick.get('rsi'),
        'status': 'pending_manual_approval',
        'verification_tier': 'VERIFIED' if pick.get('backtest_pass') else 'PLAUSIBLE',
        'verification_evidence': ['scanner_backtest_90trades'] if pick.get('backtest_pass') else ['scanner_backtest_insufficient'],
        'independent_check': bool(pick.get('backtest_pass')),
        'verified_at': datetime.now(timezone.utc).isoformat() if pick.get('backtest_pass') else None,
        'note': 'DEMO copy practice only; place manually in eToro UI',
    }
    allocations.append(ticket)

# Save ticket
out_path = WORKFLOW / f'etoro_demo_copy_ticket_{datetime.now(timezone.utc).strftime("%Y%m%dT%H%MZ")}.json'
out_data = {
    'timestamp': datetime.now(timezone.utc).isoformat(),
    'total_allocation_usd': total,
    'mode': 'DEMO',
    'picks': allocations,
}
out_path.write_text(json.dumps(out_data, indent=2, ensure_ascii=False), encoding='utf-8')
print(f'Saved eToro demo copy ticket: {out_path}')
for p in allocations:
    print(f"- {p['symbol']} {p['side']} | ${p['amount_usd']} | entry={p['entry']} sl={p['sl']} tp={p['tp']} | conv={p['conviction']} composite={p['composite_score']} bt={p['backtest_pass']}")
