#!/usr/bin/env python3
"""
Trailing Stop-Loss Monitor - Quick analysis from collected data
"""

import json
from datetime import datetime, timezone
from pathlib import Path

AUDIT_DIR = Path('/c/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm/audit_logs')
AUDIT_DIR.mkdir(parents=True, exist_ok=True)

# FTMO positions from earlier
ftmo_positions = [
    {'symbol': 'XRPUSD', 'type': 'SELL', 'volume': 0.02, 'price_open': 1.0871, 'sl': 1.1400, 'tp': 1.06, 'profit': -2.62, 'ticket': 1},
    {'symbol': 'SOLUSD', 'type': 'SELL', 'volume': 0.02, 'price_open': 73.88, 'sl': 80.0, 'tp': 70.1, 'profit': -1.10, 'ticket': 2},
    {'symbol': 'EURCZK', 'type': 'BUY', 'volume': 0.01, 'price_open': 24.1483, 'sl': 23.8, 'tp': 24.4, 'profit': -0.96, 'ticket': 3},
    {'symbol': 'NEOUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 2.05, 'sl': 1.88, 'tp': 2.01, 'profit': -1.40, 'ticket': 4},
    {'symbol': 'GRTUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 0.01577, 'sl': 0.01577, 'tp': 0.01766, 'profit': 4.40, 'ticket': 5},
    {'symbol': 'ALGUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 0.0863, 'sl': 0.082, 'tp': 0.094, 'profit': -2.30, 'ticket': 6},
    {'symbol': 'SANUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 0.0445, 'sl': 0.0423, 'tp': 0.0485, 'profit': 0.50, 'ticket': 7},
    {'symbol': 'ICPUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 2.13, 'sl': 2.03, 'tp': 2.34, 'profit': 2.10, 'ticket': 8},
    {'symbol': 'ETCUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 6.567, 'sl': 6.317, 'tp': 7.067, 'profit': 1.19, 'ticket': 9},
    {'symbol': 'SOLUSD', 'type': 'BUY', 'volume': 0.1, 'price_open': 74.22, 'sl': 69.22, 'tp': 81.72, 'profit': 1.80, 'ticket': 10},
    {'symbol': 'DOGEUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 0.0719, 'sl': 0.06471, 'tp': 0.10066, 'profit': 0.61, 'ticket': 11},
    {'symbol': 'SOLUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 74.29, 'sl': 66.86, 'tp': 104.01, 'profit': 0.11, 'ticket': 12},
    {'symbol': 'DOTUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 0.822, 'sl': 0.699, 'tp': 1.028, 'profit': -0.80, 'ticket': 13},
    {'symbol': 'ADAUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 0.1651, 'sl': 0.1403, 'tp': 0.2064, 'profit': -0.40, 'ticket': 14},
    {'symbol': 'XRPUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 1.1029, 'sl': 0.93747, 'tp': 1.37863, 'profit': -0.42, 'ticket': 15},
    {'symbol': 'DOTUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 0.821, 'sl': 0.698, 'tp': 1.026, 'profit': -0.70, 'ticket': 16},
    {'symbol': 'DOGEUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 0.07278, 'sl': 0.06186, 'tp': 0.09098, 'profit': -0.27, 'ticket': 17},
    {'symbol': 'ADAUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 0.1651, 'sl': 0.1403, 'tp': 0.2064, 'profit': -0.40, 'ticket': 18},
    {'symbol': 'XRPUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 1.1029, 'sl': 0.93747, 'tp': 1.37863, 'profit': -0.42, 'ticket': 19},
]

# Capital.com positions
capital_positions = [
    {'symbol': 'SOLUSD', 'type': 'BUY', 'volume': 0.65, 'price_open': 76.596, 'sl': 72.7598, 'tp': 95.7366, 'profit': -1.56, 'ticket': 100},
    {'symbol': 'HK50', 'type': 'BUY', 'volume': 0.01, 'price_open': 24969.5, 'sl': 24169.5, 'tp': 26569.5, 'profit': 0.01, 'ticket': 101},
    {'symbol': 'XAUUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 4123.0, 'sl': 4000.0, 'tp': 4400.0, 'profit': -70.01, 'ticket': 102},
    {'symbol': 'XAGUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 59.22, 'sl': 56.0, 'tp': 66.5, 'profit': -53.15, 'ticket': 103},
    {'symbol': 'DOGEUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 0.0719467, 'sl': 0.0647545, 'tp': 0.1007292, 'profit': 0.00, 'ticket': 104},
    {'symbol': 'SOLUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 74.4406, 'sl': 66.9951, 'tp': 104.2146, 'profit': 0.00, 'ticket': 105},
    {'symbol': 'DOTUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 0.8234, 'sl': 0.6999, 'tp': 1.0293, 'profit': 0.00, 'ticket': 106},
    {'symbol': 'ADAUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 0.16528, 'sl': 0.14049, 'tp': 0.2066, 'profit': 0.00, 'ticket': 107},
    {'symbol': 'AVAXUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 6.6553, 'sl': 5.657, 'tp': 8.3191, 'profit': 0.00, 'ticket': 108},
    {'symbol': 'LINKUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 8.42533, 'sl': 7.16153, 'tp': 10.53166, 'profit': 0.00, 'ticket': 109},
    {'symbol': 'XRPUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 1.10482, 'sl': 0.9391, 'tp': 1.38103, 'profit': 0.00, 'ticket': 110},
    {'symbol': 'DOTUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 0.8225, 'sl': 0.6991, 'tp': 1.0281, 'profit': 0.00, 'ticket': 111},
    {'symbol': 'ADAUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 0.16549, 'sl': 0.14067, 'tp': 0.20686, 'profit': 0.00, 'ticket': 112},
    {'symbol': 'AVAXUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 6.6709, 'sl': 5.6703, 'tp': 8.3386, 'profit': 0.00, 'ticket': 113},
    {'symbol': 'DOGEUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 0.0729179, 'sl': 0.06198, 'tp': 0.0911471, 'profit': 0.00, 'ticket': 114},
    {'symbol': 'SOLUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 74.6478, 'sl': 63.4521, 'tp': 93.3119, 'profit': 0.00, 'ticket': 115},
    {'symbol': 'XRPUSD', 'type': 'BUY', 'volume': 0.01, 'price_open': 1.10562, 'sl': 0.93978, 'tp': 1.38203, 'profit': 0.00, 'ticket': 116},
]

def calc_pnl_pct(pos):
    entry = pos['price_open']
    volume = pos['volume']
    profit = pos['profit']
    position_value = entry * volume
    if position_value > 0:
        return (profit / position_value) * 100
    return 0

BREAKEVEN_THRESHOLD_PCT = 2.0
TRAIL_THRESHOLD_PCT = 5.0
TRAIL_DISTANCE_PCT = 2.0

all_adjustments = []

for broker_name, positions in [('FTMO', ftmo_positions), ('CAPITAL', capital_positions)]:
    print(f'Checking {broker_name}: {len(positions)} positions')
    for pos in positions:
        pnl_pct = calc_pnl_pct(pos)
        if pnl_pct > BREAKEVEN_THRESHOLD_PCT:
            entry = pos['price_open']
            side = pos['type']
            current_sl = pos['sl']
            
            # Estimate current price from PnL
            if side == 'BUY':
                current_price = entry + (pos['profit'] / pos['volume'])
            else:
                current_price = entry - (pos['profit'] / pos['volume'])
            
            new_sl = None
            if pnl_pct > TRAIL_THRESHOLD_PCT:
                if side == 'BUY':
                    new_sl = current_price * (1 - TRAIL_DISTANCE_PCT / 100)
                    if current_sl > 0 and new_sl <= current_sl:
                        new_sl = None
                else:
                    new_sl = current_price * (1 + TRAIL_DISTANCE_PCT / 100)
                    if current_sl > 0 and new_sl >= current_sl:
                        new_sl = None
                reason = f'TRAIL: PnL {pnl_pct:.2f}% > {TRAIL_THRESHOLD_PCT}%'
            elif pnl_pct > BREAKEVEN_THRESHOLD_PCT:
                new_sl = entry
                if side == 'BUY':
                    if current_sl > 0 and new_sl <= current_sl:
                        new_sl = None
                else:
                    if current_sl > 0 and new_sl >= current_sl:
                        new_sl = None
                reason = f'BREAKEVEN: PnL {pnl_pct:.2f}% > {BREAKEVEN_THRESHOLD_PCT}%'
            
            if new_sl is not None:
                print(f'  {pos["symbol"]} ({side}): PnL {pnl_pct:.2f}% -> New SL: {new_sl:.5f} (was {current_sl})')
                all_adjustments.append({
                    'broker': broker_name,
                    'symbol': pos['symbol'],
                    'ticket': pos['ticket'],
                    'side': side,
                    'volume': pos['volume'],
                    'entry_price': entry,
                    'current_price': round(current_price, 5),
                    'unrealized_pnl_pct': round(pnl_pct, 2),
                    'old_sl': current_sl,
                    'new_sl': round(new_sl, 5),
                    'action': 'trail' if pnl_pct > TRAIL_THRESHOLD_PCT else 'breakeven',
                    'reason': reason
                })

audit_data = {
    'run_timestamp': datetime.now(timezone.utc).isoformat(),
    'parameters': {
        'breakeven_threshold_pct': BREAKEVEN_THRESHOLD_PCT,
        'trail_threshold_pct': TRAIL_THRESHOLD_PCT,
        'trail_distance_pct': TRAIL_DISTANCE_PCT
    },
    'adjustments': all_adjustments,
    'summary': {
        'total_positions_checked': len(ftmo_positions) + len(capital_positions),
        'adjustments_identified': len(all_adjustments),
        'ftmo_positions': len(ftmo_positions),
        'capital_positions': len(capital_positions)
    }
}

timestamp = datetime.now(timezone.utc).strftime('%Y%m%d_%H%M%S')
audit_file = AUDIT_DIR / f'trail_sl_{timestamp}.json'
with open(audit_file, 'w') as f:
    json.dump(audit_data, f, indent=2)

print(f'\nAudit log saved: {audit_file}')
print(f'Total adjustments identified: {len(all_adjustments)}')