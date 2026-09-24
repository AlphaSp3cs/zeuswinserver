#!/usr/bin/env python3
"""
High-conviction all-sector scanner for Capital.com RIGHT MT5 universe.
Scans: all forex pairs, commodities, indices, crypto.
Applies: trend verification, ATR-based SL/TP, backtest, tradegate.
Output: JSON + Markdown report with only high-conviction setups.
"""
import json, time, math
from pathlib import Path
from datetime import datetime, timezone
import MetaTrader5 as mt5

TERMINAL = r'C:\Program Files\Capital.com MetaTrader 5\terminal64.exe'
BASE = Path('C:/Users/bravo-usr1/Desktop/OuroTaurus Trade Firm')
TS = datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')
JSON_OUT = BASE / 'artifacts' / f'high_conviction_scan_{TS}.json'
REPORT_OUT = BASE / 'high_conviction_report.md'

# MT5 timeframes
TF = mt5.TIMEFRAME_H1
HIST_BARS = 200
VWAP_PERIOD = 20

def calc_ema(closes, period):
    ema = [closes[0]]
    k = 2 / (period + 1)
    for c in closes[1:]:
        ema.append(c * k + ema[-1] * (1 - k))
    return ema

def calc_atr(highs, lows, closes, period=14):
    tr = []
    for i in range(1, len(closes)):
        h = max(highs[i], closes[i-1])
        l = min(lows[i], closes[i-1])
        tr.append(h - l)
    if len(tr) < period:
        return sum(tr) / len(tr) if tr else 0.0
    return sum(tr[-period:]) / period

def calc_vwap(rates):
    tp_vol = 0.0
    vol = 0.0
    for r in rates[-VWAP_PERIOD:]:
        tp = (r['high'] + r['low'] + r['close']) / 3
        tp_vol += tp * r['real_volume']
        vol += r['real_volume']
    return tp_vol / vol if vol > 0 else None

def calc_rsi(closes, period=14):
    deltas = [closes[i] - closes[i-1] for i in range(1, len(closes))]
    gains = [d if d > 0 else 0 for d in deltas]
    losses = [-d if d < 0 else 0 for d in deltas]
    avg_gain = sum(gains[-period:]) / period
    avg_loss = sum(losses[-period:]) / period
    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100 - (100 / (1 + rs))

def backtest_simple(symbol, rates, side, sl, tp, holding_bars=24):
    wins = 0
    losses = 0
    trades = 0
    closes = [r['close'] for r in rates]
    highs = [r['high'] for r in rates]
    lows = [r['low'] for r in rates]
    for i in range(len(rates) - holding_bars):
        entry = closes[i]
        if side == 'LONG':
            for j in range(i+1, i+1+holding_bars):
                if lows[j] <= sl:
                    losses += 1
                    trades += 1
                    break
                if highs[j] >= tp:
                    wins += 1
                    trades += 1
                    break
        else:
            for j in range(i+1, i+1+holding_bars):
                if highs[j] >= sl:
                    losses += 1
                    trades += 1
                    break
                if lows[j] <= tp:
                    wins += 1
                    trades += 1
                    break
    if trades == 0:
        return 0, 0, 0
    win_rate = wins / trades
    expectancy = (win_rate * (tp - entry)) - ((1 - win_rate) * (entry - sl))
    return win_rate, expectancy, trades

def tradegate(win_rate, expectancy, rsi, price, ema20, ema50, vwap, atr):
    reasons = []
    if win_rate < 0.36:
        reasons.append('win_rate_low')
    if expectancy <= 0:
        reasons.append('expectancy_negative')
    if rsi is not None and (rsi < 30 or rsi > 85):
        reasons.append('rsi_extreme')
    if atr == 0:
        reasons.append('atr_zero')
    if ema20 is None or ema50 is None:
        reasons.append('missing_ema')
    return len(reasons) == 0, reasons

# Initialize
mt5.shutdown()
time.sleep(1)
ok = mt5.initialize(TERMINAL)
if not ok:
    print('init failed', mt5.last_error())
    exit(1)

symbols = [s.name for s in mt5.symbols_get() if s.visible]
forex = [s for s in symbols if any(x in s for x in ['USD','EUR','GBP','JPY','AUD','NZD','CHF','CAD'])]
commodities = [s for s in symbols if any(x in s for x in ['XAU','XAG','USOIL','UKOIL','NATGAS','GAS','COPPER','WHEAT','CORN','SOY'])]
indices = [s for s in symbols if any(x in s for x in ['US500','DE40','HK50','JP225','UK100','US100','US30'])]
crypto = [s for s in symbols if any(x in s for x in ['BTC','ETH','XRP','SOL','DOGE','DOT','ADA','LINK','BNB','LTC'])]

all_universe = {
    'forex': forex,
    'commodities': commodities,
    'indices': indices,
    'crypto': crypto,
}

scan_results = {'timestamp_utc': datetime.now(timezone.utc).isoformat(), 'universe': {}}
high_conviction = []

for category, sym_list in all_universe.items():
    scan_results['universe'][category] = []
    for symbol in sym_list:
        rates = mt5.copy_rates_from_pos(symbol, TF, 0, HIST_BARS)
        if rates is None or len(rates) < 50:
            continue
        closes = [r['close'] for r in rates]
        highs = [r['high'] for r in rates]
        lows = [r['low'] for r in rates]
        ema20 = calc_ema(closes, 20)[-1]
        ema50 = calc_ema(closes, 50)[-1]
        atr = calc_atr(highs, lows, closes)
        vwap = calc_vwap(rates)
        rsi = calc_rsi(closes)
        price = closes[-1]
        side = None
        if price > ema20 > ema50:
            side = 'LONG'
        elif price < ema20 < ema50:
            side = 'SHORT'
        sl_long = price - 1.5 * atr if side == 'LONG' else None
        tp_long = price + 3.0 * atr if side == 'LONG' else None
        sl_short = price + 1.5 * atr if side == 'SHORT' else None
        tp_short = price - 3.0 * atr if side == 'SHORT' else None
        if side:
            win_rate, expectancy, trades = backtest_simple(symbol, rates, side, sl_long or sl_short, tp_long or tp_short)
        else:
            win_rate, expectancy, trades = 0, 0, 0
        passed, reasons = tradegate(win_rate, expectancy, rsi, price, ema20, ema50, vwap, atr)
        entry = {
            'symbol': symbol,
            'price': price,
            'atr': atr,
            'rsi': rsi,
            'vwap': vwap,
            'ema20': ema20,
            'ema50': ema50,
            'side': side,
            'formations': ['trend_aligned'] if side else [],
            'backtest': {'win_rate': round(win_rate, 2), 'expectancy': round(expectancy, 2), 'trades': trades},
            'tradegate': {'pass': passed, 'reasons': reasons},
            'sl_long': sl_long,
            'tp_long': tp_long,
            'sl_short': sl_short,
            'tp_short': tp_short,
        }
        scan_results['universe'][category].append(entry)
        if passed and side:
            high_conviction.append(entry)
    time.sleep(0.1)

mt5.shutdown()

# Save JSON
JSON_OUT.write_text(json.dumps(scan_results, indent=2), encoding='utf-8')

# Build report
lines = []
lines.append('# High Conviction Market Scan Report')
lines.append(f'Generated: {datetime.now(timezone.utc).isoformat()}')
lines.append(f'Universe: {len(symbols)} symbols across {len(all_universe)} categories')
lines.append('')
lines.append('## High Conviction Setups')
if not high_conviction:
    lines.append('No setups passed tradegate.')
else:
    for s in high_conviction:
        sl = s['sl_long'] if s['side'] == 'LONG' else s['sl_short']
        tp = s['tp_long'] if s['side'] == 'LONG' else s['tp_short']
        lines.append(f"- {s['symbol']} {s['side']} | price={s['price']} | ATR={s['atr']:.5f} | RSI={s['rsi']:.2f} | SL={sl:.5f} | TP={tp:.5f} | win_rate={s['backtest']['win_rate']} | expectancy={s['backtest']['expectancy']}")
lines.append('')
lines.append('## Scan Summary by Category')
for cat, items in scan_results['universe'].items():
    total = len(items)
    candidates = sum(1 for i in items if i['side'])
    high = sum(1 for i in items if i['tradegate']['pass'])
    lines.append(f"- {cat}: {total} scanned, {candidates} candidates, {high} high-conviction")
lines.append('')
lines.append('## Execution Notes')
lines.append('All SL/TP zones are ATR-based. Use limit entries where possible.')
lines.append('Cross-broker execution pending IBKR bracket verification.')

report_text = '\n'.join(lines)
REPORT_OUT.write_text(report_text, encoding='utf-8')
print('WROTE', JSON_OUT)
print('WROTE', REPORT_OUT)
print(json.dumps({'high_conviction_count': len(high_conviction), 'high_conviction': high_conviction}, indent=2))
