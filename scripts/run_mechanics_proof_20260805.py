
#!/usr/bin/env python3
"""
run_mechanics_proof_20260805.py
Run mechanics 3-bar proof on current all-sector candidates.
Outputs JSON/MD for review.
"""
import json, sys
from pathlib import Path
from datetime import datetime, timezone

import MetaTrader5 as mt5
import pandas as pd
import numpy as np

# Ensure scripts/ is on path
REPO = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
sys.path.insert(0, str(REPO / 'scripts'))
from market_mechanics_proof import detect_liquidity_grab, detect_vwap_reclaim, detect_exhaustion
from mechanics_three_bar_proof import three_bar_proof

TERMINAL = r'C:\Program Files\FTMO MetaTrader 5\terminal64.exe'
SERVER = os.environ.get('FTMO_MT5_SERVER', '')
LOGIN = int(os.environ.get('FTMO_MT5_LOGIN', '0'))
ART = REPO / 'artifacts' / 'nightshift'
ART.mkdir(parents=True, exist_ok=True)
ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%MZ')
json_path = ART / f'mechanics_proof_{ts}.json'
md_path = ART / f'mechanics_proof_{ts}.md'

try:
    mt5.shutdown()
except Exception:
    pass
init = mt5.initialize(login=LOGIN, server=SERVER, password='', terminal=TERMINAL, portable=False)
if not init:
    print('FTMO init failed:', mt5.last_error())
    sys.exit(1)
info = mt5.account_info()
equity = float(info.equity)

# Load current backtest-positive setups
candidates = [
    ('XAGUSD', 'SHORT'),
    ('XAUUSD', 'SHORT'),
    ('NZDUSD', 'SHORT'),
    ('BTCUSD', 'SHORT'),
    ('USDCAD', 'LONG'),
]

results = []
for sym, direction in candidates:
    si = mt5.symbol_info(sym)
    if not si:
        continue
    mt5.symbol_select(sym, True)
    bars = mt5.copy_rates_from_pos(sym, mt5.TIMEFRAME_H1, 0, 200)
    if bars is None or len(bars) < 30:
        continue
    df = pd.DataFrame(bars)
    df['time'] = pd.to_datetime(df['time'], unit='s')
    df.set_index('time', inplace=True)
    # Normalize columns expected by proof functions
    df = df.rename(columns={'tick_volume': 'tick_volume'})
    d1 = detect_liquidity_grab(df, direction=direction)
    d3 = detect_vwap_reclaim(df, direction=direction)
    d4 = detect_exhaustion(df, direction=direction)
    proof = three_bar_proof(sym, df, direction=direction, candidate_type=d1.get('mechanic_type') if d1.get('pass') else d3.get('mechanic_type') if d3.get('pass') else d4.get('mechanic_type') if d4.get('pass') else 'NONE')
    entry = float(df['close'].iloc[-1])
    atr = float((df['high'] - df['low']).ewm(span=14, adjust=False).mean().iloc[-1])
    point = float(si.point or 0.0001)
    digits = int(si.digits or 5)
    if direction == 'LONG':
        sl = round((entry - 2.0 * atr) / point) * point
        tp = round((entry + 3.0 * atr) / point) * point
    else:
        sl = round((entry + 2.0 * atr) / point) * point
        tp = round((entry - 3.0 * atr) / point) * point
    results.append({
        'symbol': sym,
        'direction': direction,
        'mechanics': {'d1': d1, 'd3': d3, 'd4': d4, 'proof': proof},
        'entry': round(entry, digits),
        'sl': sl,
        'tp': tp,
        'rr': round(abs(tp - entry) / abs(entry - sl), 4) if (sl != entry) else None,
        'atr': round(atr, 5),
        'vwap': round(float(df['vwap'].iloc[-1]), digits) if 'vwap' in df.columns else None,
    })

artifact = {
    'schema_version': '1.0',
    'generated_at': datetime.now(timezone.utc).isoformat(),
    'ftmo_equity': equity,
    'proofs': results,
}
json_path.write_text(json.dumps(artifact, indent=2), encoding='utf-8')
print('JSON', json_path)

lines = []
lines.append('# Mechanics Proof Report')
lines.append(f'Generated: {datetime.now(timezone.utc).isoformat()} UTC')
lines.append(f'FTMO equity: {equity}')
lines.append('')
for r in results:
    sym = r['symbol']
    d = r['direction']
    lines.append(f'## {sym} {d}')
    p = r['mechanics']['proof']
    d1 = r['mechanics']['d1']
    d3 = r['mechanics']['d3']
    d4 = r['mechanics']['d4']
    lines.append(f'- 3-bar proof pass: {p["three_bar_pass"]} confidence={p["confidence"]}')
    lines.append(f'- D1 liquidity: pass={d1["pass"]} confidence={d1.get("confidence",0)} reasons={d1.get("reasons",[])}')
    lines.append(f'- D3 vwap: pass={d3["pass"]} confidence={d3.get("confidence",0)} reasons={d3.get("reasons",[])}')
    lines.append(f'- D4 exhaustion: pass={d4["pass"]} confidence={d4.get("confidence",0)} reasons={d4.get("reasons",[])}')
    lines.append(f'- Entry/SL/TP: {r["entry"]} / {r["sl"]} / {r["tp"]} RR={r["rr"]} ATR={r["atr"]}')
    for t in p.get('tests', []):
        lines.append(f'  - test {t["name"]}: pass={t["pass"]} detail={t.get("detail")}')
    lines.append('')

md_path.write_text('\n'.join(lines), encoding='utf-8')
print('MD', md_path)
mt5.shutdown()