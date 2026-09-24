#!/usr/bin/env python3
import sys, json
from pathlib import Path
from datetime import datetime, timezone

sys.path.insert(0, r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm\scripts')
from edge_engine_v1 import load_learning, scan_universe

learn = load_learning()
weights = learn.get('weights', {})
setups = scan_universe(weights)

# Output directory
out_dir = Path(r'C:\Users\bravo-usr1\Desktop\scandata')
out_dir.mkdir(parents=True, exist_ok=True)
ts = datetime.now(timezone.utc).strftime('%Y%m%dT%H%MZ')
out_json = out_dir / f'edge_scan_{ts}.json'
out_md = out_dir / f'edge_scan_{ts}.md'

# Dedupe by symbol+side keeping highest conviction
best = {}
for s in setups:
    key = (s.get('symbol'), s.get('side'))
    if key not in best or s.get('conviction', 0) > best[key].get('conviction', 0):
        best[key] = s

final = sorted(best.values(), key=lambda x: x.get('conviction', 0), reverse=True)
out_json.write_text(json.dumps(final, indent=2))

# Write markdown report
lines = [
    f'# Edge Engine Scan {ts}',
    '',
    f'Total setups: {len(setups)}',
    f'Unique symbol+side: {len(final)}',
    '',
    '| Symbol | Side | Conviction | Score | RSI | Entry | SL | TP | Hold |',
    '|--------|------|------------|-------|-----|-------|----|----|------|'
]
for s in final[:30]:
    sym = s.get('symbol', '')
    side = s.get('side', '')
    conv = s.get('conviction', 0)
    score = s.get('score', 0)
    rsi = s.get('rsi', '')
    entry = s.get('entry', '')
    sl = s.get('sl', '')
    tp = s.get('tp', '')
    hold = s.get('hold', '')
    lines.append(f"| {sym} | {side} | {conv:.2f} | {score:.2f} | {rsi} | {entry} | {sl} | {tp} | {hold} |")

out_md.write_text('\n'.join(lines))

print(f'Wrote {len(final)} setups to {out_json}')
print(f'Report: {out_md}')
