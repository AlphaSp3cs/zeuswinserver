#!/usr/bin/env python3
"""
Backtest the exact buy_plan_tomorrow entries and write report.
"""
import json
from pathlib import Path
from datetime import datetime, timezone
import yfinance as yf

WORKSPACE = Path(r'C:\Users\bravo-usr1\Desktop\OuroTaurus Trade Firm')
PLAN = [
    {'ticker':'NEE','entry':84.26,'sl':83.24,'tp':85.28},
    {'ticker':'SPGI','entry':403.50,'sl':398.38,'tp':408.62},
    {'ticker':'O','entry':62.15,'sl':61.45,'tp':62.85},
    {'ticker':'MCO','entry':471.16,'sl':465.35,'tp':476.97},
    {'ticker':'AXP','entry':341.63,'sl':338.89,'tp':344.37},
]

def backtest_symbol(yf_sym, entry, sl, tp, lookback='730d', interval='1d'):
    tk = yf.Ticker(yf_sym)
    hist = tk.history(period=lookback, interval=interval, auto_adjust=True)
    if hist is None or hist.empty or len(hist) < 20:
        return {'windows':0,'wins':0,'losses':0,'win_rate':0.0,'avg_rr':0.0,'max_dd':0.0,'error':'insufficient_history'}
    closes = hist['Close'].tolist()
    highs = hist['High'].tolist()
    lows = hist['Low'].tolist()
    wins = losses = 0
    rr_list = []
    peak = closes[0]
    max_dd = 0.0
    for i in range(1, len(closes)):
        c = closes[i]
        h = highs[i]
        l = lows[i]
        hit_sl = l <= sl
        hit_tp = h >= tp
        if hit_sl and hit_tp:
            if (tp-entry) < (entry-sl):
                wins += 1
                rr_list.append(abs(tp-entry)/abs(entry-sl))
            else:
                losses += 1
                rr_list.append(-1.0)
        elif hit_sl:
            losses += 1
            rr_list.append(-1.0)
        elif hit_tp:
            wins += 1
            rr_list.append(abs(tp-entry)/abs(entry-sl))
        if c > peak:
            peak = c
        dd = (peak - c) / peak if peak > 0 else 0.0
        if dd > max_dd:
            max_dd = dd
    total = wins + losses
    return {
        'windows': total,
        'wins': wins,
        'losses': losses,
        'win_rate': round(wins/total, 4) if total else 0.0,
        'avg_rr': round(sum(rr_list)/len(rr_list), 4) if rr_list else 0.0,
        'max_dd': round(max_dd, 4),
        'error': None,
    }

results = []
for p in PLAN:
    sym = p['ticker']
    yf_sym = sym
    try:
        tk = yf.Ticker(yf_sym)
        info = tk.info
        sector = info.get('sector','') or info.get('industry','') or 'Equity'
        name = info.get('shortName', sym)
    except Exception:
        sector, name = 'Equity', sym
    bt = backtest_symbol(yf_sym, p['entry'], p['sl'], p['tp'])
    out = {**p, 'symbol': sym, 'yf': yf_sym, 'sector': sector, 'name': name, 'backtest': bt}
    results.append(out)
    print(sym, bt)

report = {
    'timestamp_utc': datetime.now(timezone.utc).isoformat(),
    'plan_file': str(WORKSPACE / 'buy_plan_tomorrow.md'),
    'results': results,
}
path = WORKSPACE / 'backtest_buy_plan_20260807.json'
path.write_text(json.dumps(report, indent=2))
print('WROTE', path)

md = ['# Buy Plan Backtest — 2026-08-07','',f'- Source: `buy_plan_tomorrow.md`','- Window: ~2y daily bars from fixed entry/SL/TP','']
for r in results:
    b = r['backtest']
    md.append(f"## {r['symbol']} ({r['name']}) | {r['sector']}")
    md.append(f"- Entry {r['entry']} | SL {r['sl']} | TP {r['tp']} | RR 2.0")
    md.append(f"- windows={b['windows']} wins={b['wins']} losses={b['losses']} win_rate={b['win_rate']} avg_rr={b['avg_rr']} max_dd={b['max_dd']}")
    md.append('')
md_path = WORKSPACE / 'backtest_buy_plan_20260807.md'
md_path.write_text('\n'.join(md))
print('WROTE', md_path)
